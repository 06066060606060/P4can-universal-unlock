// Exercise the boot gate through the actual NimBLE DHKey API boundary.
#include <cassert>
#include <cstdint>
#include <cstring>
static int fakeRc = 0, calls = 0;
static bool corrupt = false;
static uint8_t nibble(char c) { return c <= '9' ? c - '0' : c - 'a' + 10; }
static void littleEndian(const char *hex, uint8_t *out) {
  for (unsigned i = 0; i < 32; ++i)
    out[31 - i] = uint8_t(nibble(hex[i*2]) * 16 + nibble(hex[i*2+1]));
}
extern "C" int ble_sm_alg_gen_dhkey(const uint8_t *x, const uint8_t *y,
                                    const uint8_t *priv, uint8_t *out) {
  ++calls;
  uint8_t expected[32];
  littleEndian("1ea1f0f01faf1d9609592284f19e4c0047b58afd8615a69f559077b22faaa190", expected);
  assert(std::memcmp(x, expected, 32) == 0);
  littleEndian("4c55f33e429dad377356703a9ab85160472d1130e28e36765f89aff915b1214a", expected);
  assert(std::memcmp(y, expected, 32) == 0);
  littleEndian("3f49f6d4a3c55f3874c9b3e3d2103f504aff607beb40b7995899b8a6cd3c1abd", expected);
  assert(std::memcmp(priv, expected, 32) == 0);
  littleEndian("ec0234a357c8ad05341010a60a397d9b99796b13b4f866f1868d34f373bfa698", out);
  if (corrupt) out[12] ^= 1;
  return fakeRc;
}
#if __has_include("../p4_ble_crypto.h")
#include "../p4_ble_crypto.h"
#else
// Baseline behavior: no known-answer gate before pairing.
static bool p4BleCryptoSelfTest() { return true; }
#endif
int main() {
  assert(p4BleCryptoSelfTest());
  corrupt = true;
  assert(!p4BleCryptoSelfTest());
  corrupt = false;
  fakeRc = -1;
  assert(!p4BleCryptoSelfTest());
  fakeRc = 7;
  assert(!p4BleCryptoSelfTest());
  assert(calls == 4);
}
