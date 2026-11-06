"""Build the P4 OTA BIN and matching source ZIP through the workspace publisher."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FQBN='esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-path',type=Path)
    args=parser.parse_args()
    publisher=next((p/'tools/build_ota.py' for p in ROOT.parents if (p/'tools/build_ota.py').is_file()),None)
    if publisher is None:
        raise SystemExit('Workspace tools/build_ota.py is required for paired OTA publication. Place this source package under firmware/universal/ in the Tesla Unlock workspace. Arduino IDE can also compile the sketch directly with the documented board settings.')
    subprocess.run([sys.executable,str(ROOT/'tools/build_dashboard.py')],check=True)
    cmd=[sys.executable,str(publisher),'--package',str(ROOT),'--fqbn',FQBN]
    if args.build_path is not None:cmd+=['--build-path',str(args.build_path.resolve())]
    subprocess.run(cmd,cwd=publisher.parents[1],check=True)

if __name__=='__main__':
    main()
