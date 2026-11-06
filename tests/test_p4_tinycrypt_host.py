"""Execute actual TinyCrypt C with only its ESP ECC HAL replaced.

The v5.5.5 fixture preserves the original per-translation-unit SOC visibility:
ecc.c sees SOC_ECC_SUPPORTED through esp_tinycrypt_port.h, whereas ecc_dh.c
does not. Globally defining that macro would accidentally hide the regression.
The peripheral callback implements raw little-endian P-256 arithmetic, without
knowing the expected secret; all fixed-code ECDH runs execute the C ladder.
"""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import random
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(os.environ.get("P4_BLE_TEST_PACKAGE", Path(__file__).resolve().parents[1]))
TESTS = Path(__file__).resolve().parent
FIXTURE = TESTS / "fixtures/tinycrypt_v555"
FAKES = TESTS / "p4_tinycrypt_fakes"
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

# Bluetooth Core Secure Connections sample P-256 key pair and DHKey. TinyCrypt
# takes BE bytes here; the surrounding NimBLE adapter reverses its LE buffers.
PRIVATE_A = 0x3F49F6D4A3C55F3874C9B3E3D2103F504AFF607BEB40B7995899B8A6CD3C1ABD
PUBLIC_B = (0x1EA1F0F01FAF1D9609592284F19E4C0047B58AFD8615A69F559077B22FAAA190,
            0x4C55F33E429DAD377356703A9AB85160472D1130E28E36765F89AFF915B1214A)
DHKEY = bytes.fromhex("ec0234a357c8ad05341010a60a397d9b99796b13b4f866f1868d34f373bfa698")


def valid_point(point):
    if point is None:
        return False
    x, y = point
    return 0 <= x < P and 0 <= y < P and (y*y - x*x*x + 3*x - B) % P == 0


def add(left, right):
    """Independent affine P-256 reference using Python's modular inverse."""
    if left is None:
        return right
    if right is None:
        return left
    x1, y1 = left
    x2, y2 = right
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if left == right:
        slope = ((3*x1*x1 - 3) * pow(2*y1, -1, P)) % P
    else:
        slope = ((y2-y1) * pow((x2-x1) % P, -1, P)) % P
    x3 = (slope*slope-x1-x2) % P
    return x3, (slope*(x1-x3)-y1) % P


def multiply(scalar, point):
    result = None
    while scalar:
        if scalar & 1:
            result = add(result, point)
        point = add(point, point)
        scalar >>= 1
    return result


def point_bytes(point):
    return b"".join(coordinate.to_bytes(32, "big") for coordinate in point)


U8 = ctypes.c_uint8
BUFFER = ctypes.POINTER(U8)
MUL_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, U8)
VERIFY_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, BUFFER, BUFFER, U8)
RNG_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, BUFFER, ctypes.c_uint)


class TinyCrypt:
    def __init__(self, source, include, output):
        # Upstream's hardware-only old branch leaves software parameters and
        # helpers unused. Suppress only those vendor diagnostics, keeping other
        # warnings fatal. No global SOC_* define or forced SOC include is used.
        compiler = shlex.split(os.environ.get("CC", "cc"))
        paths = [source / "ecc.c", source / "ecc_dh.c", source / "ecc_dsa.c",
                 source / "esp_tinycrypt_port.c"]
        if not paths[0].exists():
            paths = [source / "src/ecc.c", source / "src/ecc_dh.c",
                     source / "src/ecc_dsa.c", source / "port/esp_tinycrypt_port.c"]
        port = paths[-1].parent
        command = compiler + ["-std=c99", "-O2", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                              "-Wno-unused-function", "-Wno-unused-parameter",
                              "-I", str(FAKES), "-I", str(include), "-I", str(port)]
        command += [str(path) for path in paths] + [str(FAKES / "ecc_hal_fake.c"), "-o", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError("TinyCrypt host compilation failed (INVALID-RED):\n" + result.stdout + result.stderr)
        self.lib = ctypes.CDLL(str(output))
        self.lib.uECC_secp256r1.restype = ctypes.c_void_p
        self.curve = self.lib.uECC_secp256r1()
        self.lib.uECC_shared_secret.argtypes = [BUFFER, BUFFER, BUFFER, ctypes.c_void_p]
        self.lib.uECC_compute_public_key.argtypes = [BUFFER, BUFFER, ctypes.c_void_p]
        self.lib.uECC_valid_public_key.argtypes = [BUFFER, ctypes.c_void_p]
        self.lib.uECC_set_rng.argtypes = [RNG_CALLBACK]
        self.lib.test_set_callbacks.argtypes = [MUL_CALLBACK, VERIFY_CALLBACK]
        self.errors = []
        self.hal_inputs = []

        def verify(px, py, size):
            return int(size == 32 and valid_point((int.from_bytes(px[:size], "little"),
                                                  int.from_bytes(py[:size], "little"))))

        def mul(k, px, py, rx, ry, size):
            try:
                assert size == 32, "P-256 peripheral input width"
                scalar = int.from_bytes(k[:size], "little")
                point = (int.from_bytes(px[:size], "little"), int.from_bytes(py[:size], "little"))
                self.hal_inputs.append((scalar, point))
                if not valid_point(point):
                    return -1
                product = multiply(scalar, point)
                if product is None:
                    return -1
                ctypes.memmove(rx, product[0].to_bytes(size, "little"), size)
                ctypes.memmove(ry, product[1].to_bytes(size, "little"), size)
                return 0
            except Exception as exc:
                self.errors.append(repr(exc))
                return -1

        def rng(dest, size):
            # Test-only nonzero blinding value, not a production entropy source.
            ctypes.memset(dest, 0, size)
            dest[0] = 7
            return 1

        self.mul_callback = MUL_CALLBACK(mul)
        self.verify_callback = VERIFY_CALLBACK(verify)
        self.rng_callback = RNG_CALLBACK(rng)
        self.lib.test_set_callbacks(self.mul_callback, self.verify_callback)
        self.reset()

    def reset(self, blinded=False):
        self.errors.clear()
        self.hal_inputs.clear()
        self.lib.test_reset_stats()
        self.lib.uECC_set_rng(self.rng_callback if blinded else RNG_CALLBACK())

    def shared_secret(self, private, public):
        secret = (U8 * 32)()
        result = self.lib.uECC_shared_secret((U8 * 64).from_buffer_copy(point_bytes(public)),
                                             (U8 * 32).from_buffer_copy(private.to_bytes(32, "big")),
                                             secret, self.curve)
        return result, bytes(secret)

    def public_key(self, private):
        public = (U8 * 64)()
        result = self.lib.uECC_compute_public_key((U8 * 32).from_buffer_copy(private.to_bytes(32, "big")),
                                                  public, self.curve)
        return result, bytes(public)

    def validate(self, public):
        return self.lib.uECC_valid_public_key((U8 * 64).from_buffer_copy(point_bytes(public)), self.curve)


class TinyCryptHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="p4-tinycrypt-host-")
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        cls.before = TinyCrypt(FIXTURE, FIXTURE / "include", directory / "before.so")
        production = ROOT / "src/p4_tinycrypt"
        cls.current = (TinyCrypt(production, ROOT / "third_party/tinycrypt/include", directory / "current.so")
                       if (production / "ecc.c").exists() else cls.before)

    def check_boundary(self, implementation):
        self.assertEqual(implementation.errors, [])
        self.assertEqual(implementation.lib.test_lock_depth(), 0)

    def test_01_bluetooth_core_ecdh_known_answer(self):
        self.assertTrue(valid_point(PUBLIC_B))
        self.assertEqual(multiply(PRIVATE_A, PUBLIC_B)[0].to_bytes(32, "big"), DHKEY)
        self.current.reset()
        result, secret = self.current.shared_secret(PRIVATE_A, PUBLIC_B)
        self.check_boundary(self.current)
        self.assertEqual(result, 1)
        self.assertEqual(secret, DHKEY,
                         "actual TinyCrypt ECDH must match the Bluetooth Core DHKey; IDF v5.5.5 truncates its regularized scalar")
        self.assertEqual(self.current.lib.test_mul_calls(), 0,
                         "257-bit regularized ECDH must remain on the C software ladder")

    def test_02_v555_characterization_reproduces_scalar_truncation(self):
        self.before.reset()
        result, broken = self.before.shared_secret(PRIVATE_A, PUBLIC_B)
        self.check_boundary(self.before)
        self.assertEqual(result, 1)
        self.assertNotEqual(broken, DHKEY)
        self.assertEqual(self.before.lib.test_mul_calls(), 1)
        truncated = (PRIVATE_A + N) % (1 << 256)
        self.assertEqual(self.before.hal_inputs, [(truncated, PUBLIC_B)])
        self.assertEqual(broken, multiply(truncated, PUBLIC_B)[0].to_bytes(32, "big"))
        self.assertEqual(self.before.lib.test_constant_time(), 1)

    def test_03_differential_ecdh_with_and_without_random_initial_z(self):
        generator = random.Random(0x553293)
        # The upstream co-Z ladder rejects 1, n-1 and n-2. Their
        # fail-closed behavior is characterized separately below; realistic
        # key sizes and ordinary small scalars must match the affine reference.
        vectors = [(2, 3), (3, 7), (17, 19), (N//2, 23), (N-3, 29)]
        vectors += [(generator.randrange(1, N), generator.randrange(2, N)) for _ in range(8)]
        for blinded in (False, True):
            self.current.reset(blinded=blinded)
            for private, peer_private in vectors:
                with self.subTest(blinded=blinded, private=hex(private)):
                    peer = multiply(peer_private, G)
                    expected = multiply(private, peer)[0].to_bytes(32, "big")
                    result, secret = self.current.shared_secret(private, peer)
                    self.assertEqual((result, secret), (1, expected))
            self.check_boundary(self.current)
            self.assertEqual(self.current.lib.test_mul_calls(), 0)

    def test_04_canonical_public_keys_use_constant_time_hardware_boundary(self):
        self.current.reset()
        for private in (1, 2, PRIVATE_A, N-1):
            with self.subTest(private=hex(private)):
                self.assertEqual(self.current.public_key(private), (1, point_bytes(multiply(private, G))))
                self.assertEqual(self.current.hal_inputs[-1], (private, G))
        self.check_boundary(self.current)
        self.assertEqual(self.current.lib.test_mul_calls(), 4)
        self.assertEqual(self.current.lib.test_constant_time(), 1)

    def test_05_public_point_validation_rejects_invalid_points(self):
        self.current.reset()
        self.assertEqual(self.current.validate(PUBLIC_B), 0)
        self.assertEqual(self.current.validate(multiply(2, G)), 0)
        self.assertGreaterEqual(self.current.lib.test_verify_calls(), 2)
        for invalid in ((0, 0), (P, PUBLIC_B[1]), (PUBLIC_B[0], P),
                        (PUBLIC_B[0], PUBLIC_B[1] ^ 1), (1, 1)):
            with self.subTest(invalid=invalid):
                self.assertNotEqual(self.current.validate(invalid), 0)
        self.check_boundary(self.current)

    def test_06_original_fixture_matches_pinned_upstream(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        for relative, evidence in manifest["files"].items():
            with self.subTest(source=relative):
                self.assertEqual(hashlib.sha256((FIXTURE / relative).read_bytes()).hexdigest(), evidence["sha256"])

    def test_07_upstream_degenerate_scalars_fail_closed(self):
        for blinded in (False, True):
            for private in (1, N-1, N-2):
                with self.subTest(blinded=blinded, private=hex(private)):
                    self.current.reset(blinded=blinded)
                    self.assertEqual(self.current.shared_secret(private, PUBLIC_B), (0, bytes(32)))
                    self.assertEqual(self.current.lib.test_mul_calls(), 0)
                    self.check_boundary(self.current)


if __name__ == "__main__":
    unittest.main()
