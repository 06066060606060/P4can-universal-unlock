"""Verify the actual P4 ELF and map bind NimBLE to the package's fixed TinyCrypt."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    'EccPoint_mult': 'ecc.c.o',
    'uECC_shared_secret': 'ecc_dh.c.o',
    'uECC_make_key': 'ecc_dh.c.o',
    'uECC_valid_public_key': 'ecc.c.o',
    'uECC_set_rng': 'ecc.c.o',
    'esp_tinycrypt_calc_ecc_mult': 'esp_tinycrypt_port.c.o',
    'esp_tinycrypt_verify_ecc_point': 'esp_tinycrypt_port.c.o',
}

def elf_functions(data):
    if len(data) < 52 or data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected little-endian ELF32')
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if header[2] != 243 or header[11] != 40:
        raise ValueError('Expected RISC-V ELF32 with section headers')
    sections = [struct.unpack_from('<IIIIIIIIII', data, header[6] + i*40)
                for i in range(header[12])]
    functions = {}
    for section in sections:
        if section[1] != 2:  # SHT_SYMTAB
            continue
        if section[9] != 16 or section[6] >= len(sections):
            raise ValueError('Invalid ELF symbol table')
        strings = sections[section[6]]
        table = data[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4], section[4]+section[5], 16):
            name, value, size, info, _, index = struct.unpack_from('<IIIBBH', data, offset)
            if info == 0x12 and index != 0:  # strong global STT_FUNC
                end = table.find(b'\0', name)
                if end < 0:
                    raise ValueError('Invalid ELF symbol name')
                functions[table[name:end].decode('ascii')] = value
    return functions

def verify_map(text, functions):
    for member in ('ecc.c.obj', 'ecc_dh.c.obj', 'ecc_dsa.c.obj', 'esp_tinycrypt_port.c.obj'):
        if 'libbt.a(' + member + ')' in text:
            raise ValueError('Stock TinyCrypt archive member still linked: ' + member)
    owners = {}
    required = dict(REQUIRED, ble_sm_alg_gen_dhkey='native')
    for symbol, object_name in required.items():
        pattern = r'^ \.text\.' + re.escape(symbol) + r'\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+([^\n]+)$'
        matches = [(int(m[1],16), int(m[2],16), m[3].strip())
                   for m in re.finditer(pattern, text, re.MULTILINE) if int(m[1],16)]
        if len(matches) != 1 or matches[0][1] == 0:
            raise ValueError('Missing/ambiguous live function: ' + symbol)
        address, _, owner = matches[0]
        if functions.get(symbol) != address:
            raise ValueError('ELF/map function address mismatch: ' + symbol)
        expected = '/sketch/src/p4_tinycrypt/' + object_name
        if object_name == 'native':
            if not owner.endswith('/libbt.a(ble_sm_alg.c.obj)'):
                raise ValueError('NimBLE DHKey adapter was replaced')
        elif not owner.endswith(expected):
            raise ValueError('Wrong TinyCrypt owner for ' + symbol + ': ' + owner)
        owners[symbol] = {'address': hex(address), 'owner': owner}
    return owners

def verify_sources(root):
    manifest = json.loads((root/'third_party/tinycrypt/UPSTREAM.json').read_text())
    if manifest['commit'] != '9fd7cb7e606a06111e1b14be7f4e00d77d9cf3dd':
        raise ValueError('Unexpected TinyCrypt upstream commit')
    checked = {}
    for relative in ('src/ecc.c','src/ecc_dh.c','src/ecc_dsa.c',
                     'port/esp_tinycrypt_port.c','port/esp_tinycrypt_port.h'):
        local = root/'src/p4_tinycrypt'/Path(relative).name
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        if digest != manifest['sources']['after/'+relative]['sha256']:
            raise ValueError('TinyCrypt source differs from upstream: ' + relative)
        checked[str(local.relative_to(root))] = digest
    return checked

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    args = parser.parse_args()
    try:
        sources = verify_sources(ROOT)
        elf = args.elf.read_bytes()
        map_path = args.elf.with_suffix('.map')
        owners = verify_map(map_path.read_text(), elf_functions(elf))
    except (OSError, ValueError, KeyError, struct.error) as exc:
        raise SystemExit('P4 crypto link verification failed: ' + str(exc))
    print(json.dumps({'crypto_commit': '9fd7cb7e606a06111e1b14be7f4e00d77d9cf3dd',
                      'elf_sha256': hashlib.sha256(elf).hexdigest(),
                      'map_sha256': hashlib.sha256(map_path.read_bytes()).hexdigest(),
                      'native_nimble_fixed_tinycrypt': True, 'functions': owners,
                      'upstream_source_sha256': sources}, indent=2))

if __name__ == '__main__':
    main()
