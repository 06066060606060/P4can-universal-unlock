"""Contract checks for live crypto ownership, upstream integrity and boot gating."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('p4_crypto_link',ROOT/'tools/verify_p4_crypto.py')
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

class CryptoLink(unittest.TestCase):
    def setUp(self):
        self.functions={}
        self.map=''
        for i,(name,obj) in enumerate(dict(checker.REQUIRED,ble_sm_alg_gen_dhkey='native').items()):
            address=0x40000000+i*0x100
            self.functions[name]=address
            owner='/sdk/lib/libbt.a(ble_sm_alg.c.obj)' if obj=='native' else '/tmp/build with space/sketch/src/p4_tinycrypt/'+obj
            self.map+=' .text.'+name+'\n                '+hex(address)+' 0x40 '+owner+'\n'

    def test_actual_upstream_files_are_byte_exact(self):
        self.assertEqual(len(checker.verify_sources(ROOT)),5)

    def test_all_required_owners_match_live_elf_symbols(self):
        self.assertEqual(len(checker.verify_map(self.map,self.functions)),8)

    def test_stock_members_are_rejected_even_when_discarded(self):
        for old in ('ecc.c.obj','ecc_dh.c.obj','ecc_dsa.c.obj','esp_tinycrypt_port.c.obj'):
            with self.assertRaisesRegex(ValueError,'Stock TinyCrypt'):
                checker.verify_map(self.map+'\n/sdk/lib/libbt.a('+old+')',self.functions)

    def test_missing_wrong_owner_and_stale_map_are_rejected(self):
        for bad in (self.map.replace('uECC_shared_secret','missing'),
                    self.map.replace('/sketch/src/p4_tinycrypt/ecc_dh.c.o','/other/ecc_dh.c.o'),
                    self.map.replace('0x40000100','0x40000104'),
                    self.map.replace('libbt.a(ble_sm_alg.c.obj)','libother.a(fake.c.obj)')):
            with self.assertRaises(ValueError):checker.verify_map(bad,self.functions)
        with self.assertRaises(ValueError):checker.verify_map(self.map+self.map,self.functions)

    def test_elf_function_values_are_read_from_binary(self):
        strings=b'\0uECC_shared_secret\0'
        symbols=bytes(16)+struct.pack('<IIIBBH',1,0x40000100,64,0x12,0,3)
        offset=52+4*40
        sections=bytes(40)
        sections+=struct.pack('<IIIIIIIIII',0,3,0,0,offset,len(strings),0,0,1,0)
        sections+=struct.pack('<IIIIIIIIII',0,2,0,0,offset+len(strings),len(symbols),1,0,4,16)
        sections+=struct.pack('<IIIIIIIIII',0,1,6,0x40000000,0,0x1000,0,0,4,0)
        header=struct.pack('<16sHHIIIIIHHHHHH',b'\x7fELF\x01\x01'+bytes(10),2,243,1,0,0,52,0,52,0,0,40,4,0)
        image=header+sections+strings+symbols
        self.assertEqual(checker.elf_functions(image),{'uECC_shared_secret':0x40000100})
        with self.assertRaises(ValueError):checker.elf_functions(b'not-an-elf')

    def test_api_gate_is_independent_of_heavy_diagnostics(self):
        s=(ROOT/'s3xy_ble.h').read_text()
        self.assertIn('jw.boolean("cryptoSelfTestChecked", cryptoChecked);',s)
        self.assertIn('jw.boolean("cryptoSelfTestOk", cryptoReady);',s)
        self.assertLess(s.index('const bool cryptoOk = p4BleCryptoSelfTest();'),s.index('p4BleSecurityConfigure();'))
        # The native security policy keeps bonding and Secure Connections enabled.
        security=(ROOT/'p4_ble_security.h').read_text()
        self.assertIn('ble_hs_cfg.sm_sc = 1;',security)
        self.assertIn('ble_hs_cfg.sm_bonding = 1;',security)

if __name__=='__main__':unittest.main()
