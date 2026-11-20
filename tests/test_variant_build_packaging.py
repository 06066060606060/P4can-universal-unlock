"""Exercise variant packaging with a fake compiler; never compile firmware."""
from pathlib import Path
import tempfile, subprocess, shutil, hashlib
project=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='p4-build-test-') as tmp:
 root=Path(tmp)/'P4-CAN-Universal-v9.99.0';root.mkdir()
 for name in ['Compile-P4-Variants.ps1','tools/prepare_chinese_build.py','tools/build_dashboard.py']:
  p=root/name;p.parent.mkdir(exist_ok=True);shutil.copy(project/name,p)
 (root/'P4-CAN-Universal-v9.99.0.ino').write_text('// mock')
 (root/'dashboard_source.html').write_text('original dashboard')
 (root/'index_html.h').write_text('original header')
 (root/'zh-CN').mkdir();(root/'zh-CN/dashboard_source.zh-CN.html').write_bytes('<html>\u4e2d\u6587</html>'.encode())
 before={p.relative_to(root):hashlib.sha256(p.read_bytes()).digest() for p in root.rglob('*') if p.is_file()}
 (root/'fake.py').write_text('''import sys,gzip,re
from pathlib import Path
p=Path(sys.argv[sys.argv.index('--output-dir')+1]);p.mkdir(parents=True,exist_ok=True)
sketch=Path(sys.argv[-1]);name=next(sketch.glob('*.ino')).name
if '.zh-CN' in str(p):
 data=bytes(int(v,16) for v in re.findall(r'0x([0-9A-Fa-f]{2})',(sketch/'index_html.h').read_text()))
 assert gzip.decompress(data)==(sketch/'zh-CN/dashboard_source.zh-CN.html').read_bytes()
 assert (sketch/'dashboard_source.html').read_bytes()==gzip.decompress(data)
else: assert (sketch/'index_html.h').read_text()=='original header'
for suffix in ['bin','merged.bin','bootloader.bin','partitions.bin']:
 (p/(name+'.'+suffix)).write_bytes(b'test-firmware')
''')
 cli=root/'fake-cli.cmd';cli.write_text('@echo off\npython "%~dp0fake.py" %*\nexit /b %errorlevel%\n')
 result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'Compile-P4-Variants.ps1'),'-ArduinoCli',str(cli)],capture_output=True,text=True)
 assert result.returncode==0,result.stdout+result.stderr
 expected={f'P4-CAN-Universal-v9.99.0{lang}.{kind}.{rev}{suffix}' for lang in ['', '.zh-CN'] for kind,suffix in [('OTA','.bin'),('FULLFLASH','.merged.bin')] for rev in ['REV1.X','REV3.X']}
 assert {p.name for p in (root/'Final-Build').iterdir()}==expected
 assert not (root/'build_variants').exists(), 'Successful builds must remove temporary build_variants'
 for name,digest in before.items():assert hashlib.sha256((root/name).read_bytes()).digest()==digest,name
print('PASS: four simulated builds, eight final binaries, Chinese gzip matches source, originals unchanged, version derived from renamed sketch')
