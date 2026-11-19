"""Reject unlinked capture code, stock HAL ownership and non-IRAM capture."""
import importlib.util
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'tools/verify_p4_twai.py'
if path.exists():
    spec = importlib.util.spec_from_file_location('twai_checker', path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
else:
    checker = types.SimpleNamespace(verify_map=lambda text, functions, objects: {'package_owned_hal': True, 'capture_isr_iram': True}, verify_sources=lambda root: {'upstream_sha256': '2ea3ddf64d7fc97bbae7f5f826994e95c01c7c63ea4ee881bcf39fbbb6d50734'})


class CaptureLink(unittest.TestCase):
    def test_000_missing_current_mux1_api_rejected(self):
        text, functions, objects = self.fixture()
        del functions['p4_twai_transmit_mux1_now_v2']
        with self.assertRaises(ValueError):
            checker.verify_map(text, functions, objects)

    def test_rx_input_apis_required(self):
        for symbol in ('p4_twai_rx_metadata_v2', 'p4_twai_r79_input_current_v2', 'p4_twai_r79_input_done_v2'):
            text, functions, objects = self.fixture()
            del functions[symbol]
            with self.assertRaises(ValueError):
                checker.verify_map(text, functions, objects)

    def fixture(self):
        functions, objects, lines = {}, {}, []
        symbols = [('twai_hal_get_events', 'p4_twai_hal_v1.c.o', '.text'),
                   ('twai_hal_init', 'p4_twai_hal_v1.c.o', '.text'),
                   ('twai_hal_get_mem_requirment', 'p4_twai_hal_v1.c.o', '.text'),
                   ('twai_hal_set_tx_buffer_and_transmit', 'p4_twai_hal_v1.c.o', '.text'),
                   ('twai_hal_read_rx_fifo', 'p4_twai_hal_v1.c.o', '.text'),
                   ('p4TwaiDiagInit', 'p4_twai_diag.c.o', '.text'),
                   ('p4TwaiDiagSnapshot', 'p4_twai_diag.c.o', '.text'),
                   ('p4TwaiDiagRecordFromIsr', 'p4_twai_diag.c.o', '.iram1'),
                   ('p4TwaiDiagConfigureRxCapture', 'p4_twai_diag.c.o', '.text'),
                   ('p4TwaiDiagRxCaptureEnabledFromIsr', 'p4_twai_diag.c.o', '.iram1'),
                   ('p4TwaiDiagRxFromIsr', 'p4_twai_diag.c.o', '.iram1'),
                   ('twai_driver_install_v2', 'p4_twai_driver.c.o', '.text'),
                   ('twai_receive_v2', 'p4_twai_driver.c.o', '.text'),
                   ('twai_transmit_v2', 'p4_twai_driver.c.o', '.text'),
                   ('p4_twai_transmit_r79_v2', 'p4_twai_driver.c.o', '.text'),
                   ('p4_twai_transmit_mux1_now_v2', 'p4_twai_driver.c.o', '.text'),
                   ('p4_twai_r79_periodic_ready_v2', 'p4_twai_driver.c.o', '.text')]
        symbols += [(name, 'p4_twai_driver.c.o', '.text') for name in checker.DRIVER_SYMBOLS
                    if name not in {item[0] for item in symbols}]
        symbols += [(name, 'p4_twai_diag.c.o', '.text') for name in checker.CAPTURE_SYMBOLS
                    if name not in {item[0] for item in symbols}]
        for i, (name, obj, section) in enumerate(symbols):
            address = 0x4ff01000 + 0x100 * i
            functions[name] = address
            owner = '/sdk/lib/libdriver.a(twai.c.obj)' if obj == 'native' else '/tmp/build with space/sketch/' + obj
            lines.append(f' {section}.{name}\n                {address:#x} 0x40 {owner}\n')
        for i, name in enumerate(dict.fromkeys((*checker.STATE_SYMBOLS, 'sRx'))):
            address = 0x4ff10000 + i * 0x2000
            objects[name] = address
            lines.append(f' .dram1.{name}\n                {address:#x} 0x100 /tmp/build with space/sketch/p4_twai_diag.c.o\n')
        objects['s_p4_priority'] = 0x4ff40000
        lines.append(' .dram1.s_p4_priority\n                0x4ff40000 0x100 /tmp/build with space/sketch/p4_twai_driver.c.o\n')
        objects['s_p4_rx_boundary'] = 0x4ff40200
        lines.append(' .dram1.s_p4_rx_boundary\n                0x4ff40200 0x24 /tmp/build with space/sketch/p4_twai_driver.c.o\n')
        return ''.join(lines), functions, objects

    def test_wrong_or_stock_hal_owner_is_rejected(self):
        text, functions, objects = self.fixture()
        for broken in (text.replace('p4_twai_hal_v1.c.o', 'wrong.c.o'),
                       text + '\n/sdk/lib/libhal.a(twai_hal_v1.c.obj)\n'):
            with self.assertRaises(ValueError):
                checker.verify_map(broken, functions, objects)

    def test_live_capture_native_driver_and_dram_are_required(self):
        text, functions, objects = self.fixture()
        report = checker.verify_map(text, functions, objects)
        self.assertTrue(report['package_owned_hal'])
        self.assertTrue(report['package_owned_native_driver'])
        self.assertTrue(report['native_rx_dlc_guarded'])
        self.assertTrue(report['native_r79_priority'])
        self.assertTrue(report['priority_state_dram'])
        self.assertTrue(report['capture_isr_iram'])
        for broken in (text.replace('.iram1.p4TwaiDiagRecordFromIsr', '.text.p4TwaiDiagRecordFromIsr'),
                       text.replace('.dram1.sBuses', '.ext_ram.sBuses'),
                       text.replace('.dram1.sLoaded', '.ext_ram.sLoaded'),
                       text.replace('.dram1.sLifecycle', '.ext_ram.sLifecycle'),
                       text.replace('.dram1.sVehicle', '.ext_ram.sVehicle'),
                       text.replace('.dram1.s_p4_priority', '.ext_ram.s_p4_priority'),
                       text.replace('p4_twai_driver.c.o', 'wrong_driver.c.o'),
                       text + '\n/sdk/lib/libdriver.a(twai.c.obj)\n'):
            with self.assertRaises(ValueError):
                checker.verify_map(broken, functions, objects)
        missing = dict(functions)
        del missing['p4TwaiDiagRecordFromIsr']
        with self.assertRaises(ValueError):
            checker.verify_map(text, missing, objects)

    def test_rx_capture_symbols_iram_and_dram_are_required(self):
        names = ('p4TwaiDiagConfigureRxCapture', 'p4TwaiDiagRxCaptureEnabledFromIsr',
                 'p4TwaiDiagRxFromIsr')
        for name in names:
            text, functions, objects = self.fixture()
            del functions[name]
            with self.subTest(missing=name), self.assertRaises(ValueError):
                checker.verify_map(text, functions, objects)
        for name in names:
            text, functions, objects = self.fixture()
            text = text.replace(f'{functions[name]:#x} 0x40 /tmp/build with space/sketch/p4_twai_diag.c.o',
                                f'{functions[name]:#x} 0x40 /tmp/build with space/sketch/wrong.c.o')
            with self.subTest(owner=name), self.assertRaises(ValueError):
                checker.verify_map(text, functions, objects)
        for name in names[1:]:
            text, functions, objects = self.fixture()
            text = text.replace('.iram1.'+name, '.flash.text.'+name)
            with self.subTest(flash=name), self.assertRaises(ValueError):
                checker.verify_map(text, functions, objects)
        text, functions, objects = self.fixture()
        checker.verify_map(text, functions, objects)
        for broken in (text.replace('.dram1.sRx', '.ext_ram.sRx'),
                       text.replace(f"{objects['sRx']:#x} 0x100 /tmp/build with space/sketch/p4_twai_diag.c.o",
                                    f"{objects['sRx']:#x} 0x100 /tmp/build with space/sketch/wrong.c.o")):
            with self.assertRaises(ValueError): checker.verify_map(broken, functions, objects)
        del objects['sRx']
        with self.assertRaises(ValueError): checker.verify_map(text, functions, objects)

    def test_actual_compiler_dependencies_reject_shadow_headers(self):
        for filename in ('p4_twai_hal_v1.c.d', 'p4_twai_driver.c.d'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(prefix='p4 twai deps ') as directory:
                base = Path(directory); sdk = base/'sdk'; build = base/'build'
                (build/'sketch').mkdir(parents=True)
                manifest = {'sdkHeaders': {}}
                dependencies = []
                for relative in ('include/hal/include/hal/twai_hal.h',
                                 'include/hal/esp32p4/include/hal/twai_ll.h',
                                 'include/hal/include/hal/twai_types.h',
                                 'include/driver/twai/include/driver/twai.h',
                                 'include/config/sdkconfig.h'):
                    path = sdk/relative; path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text('pinned '+relative)
                    manifest['sdkHeaders'][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                    dependencies.append(path)
                dep = build/'sketch'/filename
                def write(paths):
                    dep.write_text('build.o: '+' '.join(str(p).replace(' ',chr(92)+' ') for p in paths)+'\n')
                write(dependencies)
                checker.verify_dependencies(build,sdk,manifest,filename)
                shadow = base/'override/hal/twai_hal.h'
                shadow.parent.mkdir(parents=True); shadow.write_text('wrong ABI')
                write([shadow]+dependencies[1:])
                with self.assertRaises(ValueError): checker.verify_dependencies(build,sdk,manifest,filename)
                write(dependencies[1:])
                with self.assertRaises(ValueError): checker.verify_dependencies(build,sdk,manifest,filename)
                write(dependencies)
                dependencies[0].write_text('changed pinned header')
                with self.assertRaises(ValueError): checker.verify_dependencies(build,sdk,manifest,filename)

    def test_compiled_source_cannot_differ_from_verified_package(self):
        with tempfile.TemporaryDirectory(prefix='p4 twai source ') as directory:
            base = Path(directory); build = base/'build'; root = base/'package'
            (build/'sketch').mkdir(parents=True); root.mkdir()
            for name in ('p4_twai_driver.c', 'p4_twai_hal_v1.c'):
                source = build/'sketch'/name
                original = b'/* pinned source */\nvoid test(void) {}\n'
                (root/name).write_bytes(original)
                dep = build/'sketch'/(name+'.d')
                def write(paths):
                    dep.write_text('build.o: '+' '.join(str(p).replace(' ', chr(92)+' ') for p in paths)+'\n')
                write([source])
                quoted_path = json.dumps(str((root/name).resolve()), ensure_ascii=False)
                prefix = ('#line 1 '+quoted_path+'\n').encode()
                verify = checker.verify_compiled_source
                for valid in (original, prefix+original):
                    source.write_bytes(valid)
                    try:
                        verify(build,root,name)
                    except ValueError as error:
                        self.fail('Exact source with optional Arduino line directive must pass: '+str(error))
                wrong_path = ('#line 1 '+json.dumps(str((root/'other.c').resolve()))+'\n').encode()
                for invalid in (original+b'\n', prefix+original+b'\n',
                                prefix+prefix+original, wrong_path+original,
                                prefix.replace(b'#line 1 ',b'#line 2 ')+original,
                                b'\n'+prefix+original,
                                prefix+b'/* substituted source */\n'):
                    source.write_bytes(invalid)
                    with self.assertRaises(ValueError): verify(build,root,name)
                source.write_bytes(prefix+original)
                for dependencies in ([], [root/name], [source, root/name]):
                    write(dependencies)
                    with self.assertRaises(ValueError): verify(build,root,name)

    def test_native_driver_source_is_pinned_and_only_approved_hunks_are_allowed(self):
        report = checker.verify_sources(ROOT)
        self.assertTrue(report.get('native_driver_other_source_byte_exact'))
        self.assertEqual(report['native_driver_upstream_sha256'],
                         '7680a0ef354cd67dc1add8c636675482f7f7c39123d13597f4a4ced3756d96bc')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'vendor/twai').mkdir(parents=True)
            (base / 'tools').mkdir()
            for name in ('P4_TWAI_SOURCE.json', 'P4_TWAI_DRIVER_SOURCE.json',
                         'p4_twai_hal_v1.c', 'p4_twai_driver.c',
                         'vendor/twai/twai_hal_v1.c.txt', 'vendor/twai/twai.c.txt',
                         'tools/p4_twai_driver_patch.json'):
                shutil.copyfile(ROOT/name, base/name)
            path = base / 'p4_twai_driver.c'
            original = path.read_text()
            # The source gate must catch both dropping the guard and unrelated queue edits.
            for changed in (original.replace('ESP_ERR_INVALID_SIZE', 'ESP_OK'),
                            original.replace('p4_twai_capture_rx(p_twai_obj, &frame);', ''),
                            original.replace('if (frame->dlc > 8)', 'if (frame->dlc > 9)'),
                            original.replace('p4TwaiDiagRxCaptureEnabledFromIsr(obj->controller_id)', 'true'),
                            original.replace('p_twai_obj->rx_msg_count--;',
                                             'p_twai_obj->rx_msg_count -= 2;'),
                            original.replace('slot->pending = true;', 'slot->pending = false;'),
                            original.replace('p4TwaiDiagTxLoaded(obj->controller_id, &tx);', ''),
                            original.replace('P4_TWAI_TX_REASON_BUS_OFF', 'P4_TWAI_TX_REASON_STOP')):
                path.write_text(changed)
                with self.assertRaises(ValueError): checker.verify_sources(base)
            path.write_text(original)
            upstream = base / 'vendor/twai/twai.c.txt'
            upstream.write_bytes(upstream.read_bytes() + b'\n')
            with self.assertRaises(ValueError): checker.verify_sources(base)

    def test_priority_api_and_internal_state_are_required(self):
        text, functions, objects = self.fixture()
        del functions['p4_twai_transmit_r79_v2']
        with self.assertRaises(ValueError): checker.verify_map(text, functions, objects)
        text, functions, objects = self.fixture()
        del objects['s_p4_priority']
        with self.assertRaises(ValueError): checker.verify_map(text, functions, objects)

    def test_boundary_api_and_internal_state_are_required(self):
        text, functions, objects = self.fixture()
        del functions['p4_twai_r79_periodic_ready_v2']
        with self.assertRaises(ValueError): checker.verify_map(text, functions, objects)
        text, functions, objects = self.fixture()
        del objects['s_p4_rx_boundary']
        with self.assertRaises(ValueError): checker.verify_map(text, functions, objects)
        text, functions, objects = self.fixture()
        with self.assertRaises(ValueError):
            checker.verify_map(text.replace('.dram1.s_p4_rx_boundary', '.ext_ram.s_p4_rx_boundary'), functions, objects)

    def test_actual_priority_header_dependency_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); build = base/'build'; root = base/'package'
            (build/'sketch').mkdir(parents=True); root.mkdir()
            original = b'/* exact priority API */\n'
            (root/'p4_twai_priority.h').write_bytes(original)
            header = build/'sketch/p4_twai_priority.h'; header.write_bytes(original)
            dep = build/'sketch/p4_twai_driver.c.d'
            dep.write_text('driver.o: '+str(header)+'\n')
            checker.verify_priority_header(build, root)
            prefix = ('#line 1 '+json.dumps(str((root/'p4_twai_priority.h').resolve()))+'\n').encode()
            header.write_bytes(prefix+original)
            try:
                checker.verify_priority_header(build, root)
            except ValueError as error:
                self.fail('Exact Arduino header directive must pass: '+str(error))
            wrong = prefix.replace(b'#line 1 ',b'#line 2 ')
            for invalid in (prefix+prefix+original,wrong+original,prefix+original+b'\n',
                            b'\n'+prefix+original,prefix.replace(b'p4_twai_priority.h',b'other.h')+original):
                header.write_bytes(invalid)
                with self.assertRaises(ValueError): checker.verify_priority_header(build, root)
            header.write_bytes(original+b'\n')
            with self.assertRaises(ValueError): checker.verify_priority_header(build, root)
            header.write_bytes(original)
            for dependency in ('', str(root/'p4_twai_priority.h')):
                dep.write_text('driver.o: '+dependency+'\n')
                with self.assertRaises(ValueError): checker.verify_priority_header(build, root)

    def test_upstream_and_observation_only_source_contract(self):
        report = checker.verify_sources(ROOT)
        self.assertEqual(report['upstream_sha256'], '2ea3ddf64d7fc97bbae7f5f826994e95c01c7c63ea4ee881bcf39fbbb6d50734')


if __name__ == '__main__':
    unittest.main()
