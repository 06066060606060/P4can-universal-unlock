"""Gate P4 artifacts on package HAL/driver ownership, ISR placement and pinned sources."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct

UPSTREAM_SHA = '2ea3ddf64d7fc97bbae7f5f826994e95c01c7c63ea4ee881bcf39fbbb6d50734'
UPSTREAM_COMMIT = 'b774170ff46c393eeb5e495ea37936038d3f4f4f'
DRIVER_UPSTREAM_SHA = '7680a0ef354cd67dc1add8c636675482f7f7c39123d13597f4a4ced3756d96bc'
DRIVER_SYMBOLS = ('twai_driver_install_v2', 'twai_receive_v2', 'twai_transmit_v2', 'p4_twai_transmit_r79_v2', 'p4_twai_transmit_mux1_now_v2', 'p4_twai_r79_periodic_ready_v2', 'p4_twai_rx_metadata_v2', 'p4_twai_r79_input_current_v2', 'p4_twai_r79_input_done_v2')
DRIVER_PATCH_SHA = 'bab505b5723f649a47be5b0d1327548c703767d4f6c214cfa1ff6eaf39ef0edb'
DRIVER_RX_GUARD = ('    // Reject malformed raw DLC before the remaining-byte count can underflow.\n'
                   '    TWAI_CHECK(message->data_length_code <= TWAI_FRAME_MAX_LEN, ESP_ERR_INVALID_SIZE);\n')
HAL_SYMBOLS = ('twai_hal_get_events', 'twai_hal_init', 'twai_hal_get_mem_requirment',
               'twai_hal_set_tx_buffer_and_transmit', 'twai_hal_read_rx_fifo')
CAPTURE_SYMBOLS = ('p4TwaiDiagInit', 'p4TwaiDiagSnapshot', 'p4TwaiDiagRecordFromIsr',
                   'p4TwaiDiagPublishVehicleContext', 'p4TwaiDiagTxQueued',
                   'p4TwaiDiagTxLoaded', 'p4TwaiDiagTxCancelled', 'p4TwaiDiagTxRetire',
                   'p4TwaiDiagConfigureRxCapture', 'p4TwaiDiagRxCaptureEnabledFromIsr',
                   'p4TwaiDiagRxFromIsr')
CAPTURE_ISR_SYMBOLS = ('p4TwaiDiagRecordFromIsr', 'p4TwaiDiagRxCaptureEnabledFromIsr',
                       'p4TwaiDiagRxFromIsr')
STATE_SYMBOLS = ('sBuses', 'sMux', 'sReady', 'sBootId', 'sInvalidBus', 'sEpoch', 'sRevision',
                 'sLifecycle', 'sLoaded', 'sVehicle', 'sRx')
GUARD = '\n#include "p4_twai_diag.h"\n#if !CONFIG_IDF_TARGET_ESP32P4\n#error "Package TWAI error capture is pinned to ESP32-P4"\n#endif\n'


def verify_sources(root):
    manifest = json.loads((root / 'P4_TWAI_SOURCE.json').read_text())
    original = (root / 'vendor/twai/twai_hal_v1.c.txt').read_bytes()
    if manifest['commit'] != UPSTREAM_COMMIT or manifest['tag'] != 'v5.5.5':
        raise ValueError('Unexpected TWAI upstream identity')
    if hashlib.sha256(original).hexdigest() != UPSTREAM_SHA or manifest['sha256'] != UPSTREAM_SHA:
        raise ValueError('Pinned TWAI upstream source changed')
    source = (root / 'p4_twai_hal_v1.c').read_text()
    start = source.index('static inline void p4_twai_capture_error(')
    end = source.index('\n}\n\n', start) + len('\n}\n\n')
    helper = source[start:end]
    if hashlib.sha256(helper.encode()).hexdigest() != manifest['captureHelperSha256']:
        raise ValueError('TWAI capture helper changed')
    canonical = (source[:start] + source[end:]).replace(GUARD, '', 1)
    canonical = canonical.replace(
        'p4_twai_capture_error(hal_ctx, &type, &dir, &seg);    //Decode error interrupt',
        'twai_ll_parse_err_code_cap(hal_ctx->dev, &type, &dir, &seg);    //Decode error interrupt', 1)
    if canonical.encode() != original:
        raise ValueError('HAL behavior changed outside the capture-only adapter')
    if source.count('p4_twai_capture_error(hal_ctx, &type, &dir, &seg)') != 1:
        raise ValueError('Capture adapter must have one existing ECC consumer')
    driver_manifest = json.loads((root / 'P4_TWAI_DRIVER_SOURCE.json').read_text())
    driver_original = (root / 'vendor/twai/twai.c.txt').read_bytes()
    if driver_manifest['commit'] != UPSTREAM_COMMIT or driver_manifest['tag'] != 'v5.5.5':
        raise ValueError('Unexpected native TWAI upstream identity')
    if (hashlib.sha256(driver_original).hexdigest() != DRIVER_UPSTREAM_SHA or
            driver_manifest['sha256'] != DRIVER_UPSTREAM_SHA or
            driver_manifest['bytes'] != len(driver_original)):
        raise ValueError('Pinned native TWAI upstream source changed')
    patch_bytes = (root / 'tools/p4_twai_driver_patch.json').read_bytes()
    if hashlib.sha256(patch_bytes).hexdigest() != DRIVER_PATCH_SHA:
        raise ValueError('Native driver approved patch changed')
    expected = driver_original.decode()
    boundary = len(expected)
    for hunk in reversed(json.loads(patch_bytes)):
        offset, before, after = hunk['offset'], hunk['before'], hunk['after']
        if not 0 <= offset <= offset + len(before) <= boundary or expected[offset:offset+len(before)] != before:
            raise ValueError('Native driver patch is not an exact nonoverlapping upstream hunk')
        expected = expected[:offset] + after + expected[offset+len(before):]
        boundary = offset
    if (root / 'p4_twai_driver.c').read_bytes() != expected.encode():
        raise ValueError('Native driver changed outside approved RX/priority/diagnostic hunks')
    return {'native_driver_upstream_sha256': DRIVER_UPSTREAM_SHA,
            'native_driver_other_source_byte_exact': True,
            'native_driver_patch_sha256': DRIVER_PATCH_SHA,
            'upstream_sha256': UPSTREAM_SHA, 'commit': UPSTREAM_COMMIT,
            'capture_helper_sha256': manifest['captureHelperSha256'],
            'other_hal_source_byte_exact': True}


def sections(text):
    pattern = r'^ (\.[^\s]+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+([^\n]+)$'
    return [(m[1], int(m[2], 16), int(m[3], 16), m[4].strip())
            for m in re.finditer(pattern, text, re.MULTILINE)
            if int(m[2], 16) and int(m[3], 16)]


def verify_map(text, functions, objects):
    if 'libhal.a(twai_hal_v1.c.obj)' in text:
        raise ValueError('Stock TWAI HAL archive object remains linked')
    if 'libdriver.a(twai.c.obj)' in text:
        raise ValueError('Stock TWAI driver archive object remains linked')
    inputs = sections(text)
    result = {'functions': {}, 'state': {}}
    for name in HAL_SYMBOLS + CAPTURE_SYMBOLS + DRIVER_SYMBOLS:
        if name not in functions:
            raise ValueError('Missing live TWAI function: ' + name)
        address = functions[name]
        expected = ('/sketch/p4_twai_hal_v1.c.o' if name in HAL_SYMBOLS else
                    '/sketch/p4_twai_driver.c.o' if name in DRIVER_SYMBOLS else
                    '/sketch/p4_twai_diag.c.o')
        owners = [item for item in inputs
                  if item[1] <= address < item[1] + item[2] and item[3].endswith(expected)]
        if len(owners) != 1:
            raise ValueError('Missing/ambiguous/wrong TWAI owner: ' + name)
        section, _, _, owner = owners[0]
        if name in CAPTURE_ISR_SYMBOLS and not section.startswith('.iram'):
            raise ValueError('TWAI capture ISR is not in IRAM: ' + name)
        result['functions'][name] = {'address': hex(address), 'section': section, 'owner': owner}
    for name in STATE_SYMBOLS:
        addresses = objects.get(name, [])
        if isinstance(addresses, int):
            addresses = [addresses]
        owners = [item for address in addresses for item in inputs
                  if item[1] <= address < item[1] + item[2] and
                  item[3].endswith('/sketch/p4_twai_diag.c.o') and item[0].startswith('.dram')]
        if len(owners) != 1:
            raise ValueError('Missing/ambiguous/non-DRAM capture state: ' + name)
        result['state'][name] = {'section': owners[0][0], 'bytes': owners[0][2]}
    for name, key in (('s_p4_priority', 'priority_state'),
                      ('s_p4_rx_boundary', 'rx_boundary_state')):
        addresses = objects.get(name, [])
        if isinstance(addresses, int):
            addresses = [addresses]
        owners = [item for address in addresses for item in inputs
                  if item[1] <= address < item[1] + item[2] and
                  item[3].endswith('/sketch/p4_twai_driver.c.o') and item[0].startswith('.dram')]
        if len(owners) != 1:
            raise ValueError('Missing/ambiguous/non-DRAM native state: ' + name)
        result[key] = {'section': owners[0][0], 'bytes': owners[0][2]}
    result.update(rx_capture_isr_iram=True, rx_capture_state_dram=True,
                  controller_loaded_tx_context=True, r79_lifecycle_dram=True,
                  native_r79_priority=True, priority_state_dram=True, rx_boundary_state_dram=True, package_owned_hal=True, capture_isr_iram=True, capture_state_dram=True,
                  package_owned_native_driver=True, native_rx_dlc_guarded=True)
    return result


def elf_symbols(data):
    if len(data) < 52 or data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected little-endian ELF32')
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if header[2] != 243 or header[11] != 40:
        raise ValueError('Expected RISC-V ELF32')
    tables = [struct.unpack_from('<IIIIIIIIII', data, header[6] + i * 40)
              for i in range(header[12])]
    functions, objects = {}, {}
    for table in tables:
        if table[1] != 2:
            continue
        if table[9] != 16 or table[6] >= len(tables):
            raise ValueError('Malformed ELF symbol table')
        strings = tables[table[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for offset in range(table[4], table[4] + table[5], 16):
            name, address, size, info, _, index = struct.unpack_from('<IIIBBH', data, offset)
            if not index or not address:
                continue
            end = names.find(b'\0', name)
            if end < 0:
                raise ValueError('Malformed ELF symbol name')
            key = names[name:end].decode('ascii')
            if info & 15 == 2 and info >> 4 in (1, 2):
                functions[key] = address
            elif info & 15 == 1:
                objects.setdefault(key, []).append(address)
    return functions, objects


def dependency_paths(build, filename):
    dependency_file = build / ('sketch/' + filename)
    text = dependency_file.read_text().replace('\\\n', ' ')
    if ':' not in text:
        raise ValueError('Malformed TWAI compiler dependency file')
    return [Path(name).resolve() for name in shlex.split(text.split(':', 1)[1])]


def verify_dependencies(build, sdk, manifest, filename='p4_twai_hal_v1.c.d'):
    dependencies = dependency_paths(build, filename)
    checked = {}
    for relative, expected in manifest['sdkHeaders'].items():
        if not relative.endswith('.h'):
            continue
        suffix = ('/hal/' + Path(relative).name if '/hal/' in relative else
                  '/' + Path(relative).name)
        selected = sorted({p for p in dependencies if p.as_posix().endswith(suffix)})
        wanted = (sdk / relative).resolve()
        if selected != [wanted]:
            raise ValueError('Missing/shadow TWAI compiler dependency: ' + relative)
        if hashlib.sha256(wanted.read_bytes()).hexdigest() != expected:
            raise ValueError('Actual compiled SDK header changed: ' + relative)
        checked[relative] = {'path': str(wanted), 'sha256': expected}
    return checked


def verify_compiled_source(build, root, filename, dependency_file=None):
    dependencies = dependency_paths(build, dependency_file or filename + '.d')
    selected = sorted({p for p in dependencies if p.name == filename})
    compiled = (build / 'sketch' / filename).resolve()
    if selected != [compiled]:
        raise ValueError('Missing/shadow TWAI compiler source: ' + filename)
    actual = compiled.read_bytes()
    original = (root / filename).read_bytes()
    # Arduino prepends one location directive when copying sketch C/header files.
    # Accept only the exact original path/line and otherwise preserve every byte.
    quoted_path = json.dumps(str((root / filename).resolve()), ensure_ascii=False)
    prefix = ('#line 1 ' + quoted_path + '\n').encode()
    if actual not in (original, prefix + original):
        raise ValueError('Compiled TWAI source differs from pinned package: ' + filename)
    return {'path': str(compiled), 'sha256': hashlib.sha256(actual).hexdigest(),
            'package_sha256': hashlib.sha256(original).hexdigest(),
            'arduino_line_directive': actual == prefix + original}


def verify_priority_header(build, root):
    # Use the same exact copy validation for C sources and included headers.
    return verify_compiled_source(build, root, 'p4_twai_priority.h', 'p4_twai_driver.c.d')


def verify_image(root, elf_path):
    source = verify_sources(root)
    text = elf_path.with_suffix('.map').read_text()
    functions, objects = elf_symbols(elf_path.read_bytes())
    report = verify_map(text, functions, objects)
    # Both legacy driver and HAL now belong to the package. Obtain the real SDK
    # from the compiler's dependency list, never from a guessed tool location.
    dependencies = dependency_paths(elf_path.parent, 'p4_twai_driver.c.d')
    configs = sorted({p for p in dependencies if p.name == 'sdkconfig.h'})
    suffix = '/qio_qspi/include/sdkconfig.h'
    if len(configs) != 1 or not configs[0].as_posix().endswith(suffix):
        raise ValueError('Missing/ambiguous native TWAI SDK configuration dependency')
    sdk = Path(configs[0].as_posix().removesuffix(suffix))
    manifest = json.loads((root / 'P4_TWAI_SOURCE.json').read_text())
    driver_manifest = json.loads((root / 'P4_TWAI_DRIVER_SOURCE.json').read_text())
    sdk_headers = dict(manifest['sdkHeaders'])
    for relative, expected in driver_manifest['sdkHeaders'].items():
        if relative in sdk_headers and sdk_headers[relative] != expected:
            raise ValueError('Inconsistent SDK pin: ' + relative)
        sdk_headers[relative] = expected
    for relative, expected in sdk_headers.items():
        if hashlib.sha256((sdk / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned SDK ABI/config changed: ' + relative)
    actual_headers = verify_dependencies(elf_path.parent, sdk, manifest)
    driver_headers = verify_dependencies(elf_path.parent, sdk, driver_manifest, 'p4_twai_driver.c.d')
    compiled_sources = {name: verify_compiled_source(elf_path.parent, root, name)
                        for name in ('p4_twai_driver.c', 'p4_twai_hal_v1.c')}
    report.update(source=source, sdk_abi_sha256=sdk_headers,
                  actual_priority_header=verify_priority_header(elf_path.parent, root),
                  actual_compiled_sources=compiled_sources,
                  actual_compiler_dependencies=actual_headers,
                  actual_native_driver_dependencies=driver_headers)
    return report
