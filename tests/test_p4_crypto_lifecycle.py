"""Execute the production mapper initialization with a failed/successful DHKey KAT."""
from pathlib import Path
import importlib.util
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pairing_block_helper', ROOT/'tests/test_s3xy_pairing_host.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

PREAMBLE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#define S3XY_DIAGNOSTICS_ENABLED 0
#define portENTER_CRITICAL(x) (++lockDepth)
#define portEXIT_CRITICAL(x) (--lockDepth)
static int lockDepth=0, initCalls=0, katCalls=0, stopCalls=0;
static bool master=true, network=true, katOk=false, host=false, observer=false;
static bool s3xyCryptoChecked=false, s3xyCryptoReady=false, s3xyBleInitialized=false;
static bool s3xyBootBondRepairArmed=false;
static int s3xyBootLocalBondCount=0;
static char s3xyDiscoveryError[64]={};
static int s3xyAdvertisedCallbacks=0;
static bool s3xyBluetoothMasterIsEnabled(){return master;}
static bool p4NetworkAllowsBle(){return network;}
static bool p4BleCryptoSelfTest(){assert(lockDepth==0&&host);++katCalls;return katOk;}
static bool p4BleSecurityInit(){assert(host);observer=true;return true;}
static void p4BleSecurityShutdown(){assert(host&&observer&&lockDepth==0);observer=false;}
static void p4BleSecurityConfigure(){assert(host&&s3xyCryptoReady);}
static void s3xyLogPush(int,const char*){}
static int s3xyLocalBondCount(){return 0;}
static uint8_t s3xyRegisteredCount(){return 0;}
constexpr int S3XY_LOG_ERROR=1,S3XY_LOG_SECURITY=2,ESP_IO_CAP_NONE=0,ESP_BLE_ENC_KEY_MASK=1,ESP_BLE_ID_KEY_MASK=2;
struct BLEScan{void setAdvertisedDeviceCallbacks(int*){}void setActiveScan(bool){}void setInterval(int){}void setWindow(int){}};
struct BLEDevice{
 static bool init(const char*){assert(lockDepth==0);++initCalls;host=true;return true;}
 static void deinit(bool release){assert(!release&&host&&!observer&&lockDepth==0);host=false;++stopCalls;}
 static BLEScan*getScan(){static BLEScan scan;return &scan;}
};
struct BLESecurity{static void setCapability(int){}static void setKeySize(int){}static void setInitEncryptionKey(int){}static void setRespEncryptionKey(int){}static void setForceAuthentication(bool){}static void resetSecurity(){}};
'''
MAIN = r'''
int main(){
 assert(!s3xyMapperInit());
 assert(s3xyCryptoChecked&&!s3xyCryptoReady&&!s3xyBleInitialized);
 assert(!host&&!observer&&stopCalls==1);
 assert(!s3xyMapperInit()&&initCalls==1&&katCalls==1);
 // Simulate a new boot with the corrected calculation.
 s3xyCryptoChecked=false;katOk=true;
 assert(s3xyMapperInit());
 assert(host&&observer&&s3xyBleInitialized&&s3xyCryptoReady);
 assert(katCalls==2);
 p4BleSecurityShutdown();BLEDevice::deinit(false);s3xyBleInitialized=false;
 assert(s3xyMapperInit()&&katCalls==2); // cached success on Master OFF/ON
 assert(lockDepth==0);
}
'''
class CryptoLifecycle(unittest.TestCase):
    def test_failed_kat_releases_host_and_blocks_retry(self):
        source = (ROOT/'s3xy_ble.h').read_text()
        block = helper.source_block(source, 'static bool s3xyMapperInit() {')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'init.cpp'; binary=Path(temp)/'init'
            path.write_text(PREAMBLE+block+MAIN)
            compile=subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-Wall','-Wextra','-Werror',str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,'INVALID-RED: '+compile.stdout+compile.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
