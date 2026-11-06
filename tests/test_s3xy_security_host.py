"""Production call-site and package-local security adapter with fake radio/time."""
from pathlib import Path
import os
import hashlib
import json
import re
import subprocess
import tempfile
import unittest

ROOT=Path(os.environ.get('P4_BLE_TEST_PACKAGE',Path(__file__).resolve().parents[1]))

PREAMBLE=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>
#define CONFIG_NIMBLE_ENABLED 1
#define portMUX_INITIALIZER_UNLOCKED 0
using portMUX_TYPE=int;
static int lockDepth=0;
#define portENTER_CRITICAL(x) (++lockDepth)
#define portEXIT_CRITICAL(x) (--lockDepth)
#define pdMS_TO_TICKS(x) (x)
constexpr uint16_t BLE_HS_CONN_HANDLE_NONE=0xffff;
constexpr int BLE_HS_EALREADY=2,BLE_HS_ENOENT=5,BLE_HS_EDONE=14;
constexpr int BLE_HS_ERR_HCI_BASE=0x200,BLE_ERR_PINKEY_MISSING=6;
enum{BLE_GAP_EVENT_CONNECT=1,BLE_GAP_EVENT_ENC_CHANGE,BLE_GAP_EVENT_PARING_COMPLETE,BLE_GAP_EVENT_DISCONNECT};
struct ble_addr_t{uint8_t type=0,val[6]={};};
struct ble_gap_conn_desc{uint16_t conn_handle=7;struct{uint8_t encrypted=0,authenticated=0,bonded=0;}sec_state;ble_addr_t peer_id_addr;};
struct ble_gap_event{
 int type=0;
 struct{uint16_t conn_handle=7;int status=0;}connect,enc_change,pairing_complete;
 struct{int reason=0;ble_gap_conn_desc conn;}disconnect;
};
using ble_gap_event_fn=int(ble_gap_event*,void*);
struct ble_gap_event_listener{ble_gap_event_fn* fn=nullptr;void* arg=nullptr;};
static ble_gap_event_listener* listener=nullptr;
static uint32_t nowMs=0;
static bool connected=true,allowed=true;
static ble_gap_conn_desc connection;
static int initRc=0,startCount=0,deleteCount=0,legacyCalls=0;
struct {int sm_bonding=0,sm_mitm=0,sm_sc=0;} ble_hs_cfg;
struct BLESecurity {
 static bool enabled;
 static void setCapability(int){}
 static void setAuthenticationMode(bool b,bool m,bool sc){enabled=b||m||sc;ble_hs_cfg.sm_bonding=b;ble_hs_cfg.sm_mitm=m;ble_hs_cfg.sm_sc=sc;}
 static void setKeySize(int){}
 static void setInitEncryptionKey(int){}
 static void setRespEncryptionKey(int){}
 static void setForceAuthentication(bool){}
 static void resetSecurity(){}
};
bool BLESecurity::enabled=false;
constexpr int ESP_IO_CAP_NONE=0,ESP_BLE_ENC_KEY_MASK=1,ESP_BLE_ID_KEY_MASK=2;
struct ble_npl_event{void(*fn)(ble_npl_event*)=nullptr;void*arg=nullptr;};
struct ble_npl_eventq{};
static ble_npl_eventq eventq;
static ble_npl_event* pendingEvent=nullptr;
void ble_npl_event_init(ble_npl_event*e,void(*fn)(ble_npl_event*),void*arg){e->fn=fn;e->arg=arg;}
ble_npl_eventq* nimble_port_get_dflt_eventq(){return &eventq;}
void ble_npl_eventq_put(ble_npl_eventq*,ble_npl_event*e){assert(lockDepth==0);assert(pendingEvent==nullptr);pendingEvent=e;}
static std::function<void()> tick;
static std::function<void(int)> onStart;
uint32_t millis(){return nowMs;}
void vTaskDelay(uint32_t ms){assert(lockDepth==0);nowMs+=ms;if(tick)tick();}
int ble_gap_event_listener_register(ble_gap_event_listener*l,ble_gap_event_fn*f,void*a){assert(lockDepth==0);l->fn=f;l->arg=a;listener=l;return 0;}
int ble_gap_event_listener_unregister(ble_gap_event_listener*l){assert(lockDepth==0);assert(listener==l);listener=nullptr;return 0;}
int ble_gap_conn_find(uint16_t handle,ble_gap_conn_desc*d){assert(lockDepth==0);if(!connected||handle!=7)return BLE_HS_ENOENT;*d=connection;return 0;}
int ble_gap_security_initiate(uint16_t handle){assert(lockDepth==0);assert(handle==7);++startCount;if(onStart)onStart(startCount);return initRc;}
int ble_store_util_delete_peer(const ble_addr_t*){assert(lockDepth==0);++deleteCount;return 0;}
struct LegacyUnbounded:std::runtime_error{LegacyUnbounded():runtime_error("legacy secureConnection entered indefinite SDK wait"){} };
class BLEClient{public:bool isConnected(){return connected;}uint16_t getConnId(){return connected?7:BLE_HS_CONN_HANDLE_NONE;}bool secureConnection(){++legacyCalls;throw LegacyUnbounded();}};
static bool s3xySecurityMayRun(){return allowed;}
static void emit(int type,int status,uint16_t handle=7){
 ble_gap_event e;e.type=type;e.enc_change.conn_handle=handle;e.enc_change.status=status;
 e.pairing_complete.conn_handle=handle;e.pairing_complete.status=status;
 e.disconnect.conn.conn_handle=handle;e.disconnect.reason=status;
 if(listener)listener->fn(&e,listener->arg);
}
'''

MAIN=r'''
static void reset(uint32_t start=0){
 nowMs=start;connected=allowed=true;connection={};initRc=startCount=deleteCount=legacyCalls=0;tick=nullptr;onStart=nullptr;
}
static void require(bool ok,const char*what){if(!ok){fprintf(stderr,"ASSERTION: %s\n",what);std::abort();}}
int main(){
 BLEClient instance;auto*client=&instance;
 char securityError[64]={};P4BleSecurityResult securityResult;
 require(p4BleSecurityInit(),"listener registration");
 CONFIG_SECURITY
 require(!BLESecurity::enabled,"protected ATT errors must not reenter the SDK indefinite security wait");
 require(ble_hs_cfg.sm_bonding==1&&ble_hs_cfg.sm_sc==1&&ble_hs_cfg.sm_mitm==0,"native bonding and Secure Connections stay enabled");
 reset();p4BleSecurityBeginAttempt();connection.sec_state.encrypted=1;
 require(CALL_SECURITY,"an already encrypted peer must succeed without waiting for another completion");
 require(startCount==0&&legacyCalls==0,"already encrypted must not restart authentication");
 reset();p4BleSecurityBeginAttempt();tick=[&](){if(nowMs>=30){connection.sec_state.encrypted=1;emit(BLE_GAP_EVENT_ENC_CHANGE,0);}};
 require(CALL_SECURITY,"fresh encryption completes");require(startCount==1&&nowMs==30,"one bounded security initiation");
 reset();p4BleSecurityBeginAttempt();tick=[&](){emit(BLE_GAP_EVENT_ENC_CHANGE,0);};
 require(!CALL_SECURITY,"successful event without actual encryption is not secure");
 require(nowMs==10000&&std::string(securityError).find("timeout")!=std::string::npos,"10 second timeout");
 reset();p4BleSecurityBeginAttempt();tick=[&](){emit(BLE_GAP_EVENT_PARING_COMPLETE,5);};
 require(!CALL_SECURITY,"SMP rejection must fail");require(std::string(securityError).find("sm=5")!=std::string::npos,"SMP reason survives");require(deleteCount==0,"unrelated security error must preserve bonds");CHECK_PROBE
 reset();p4BleSecurityBeginAttempt();tick=[&](){emit(BLE_GAP_EVENT_DISCONNECT,0x213);connected=false;};
 require(!CALL_SECURITY,"disconnect must fail");require(std::string(securityError).find("d=531")!=std::string::npos,"disconnect reason survives");
 reset();p4BleSecurityBeginAttempt();tick=[&](){if(startCount==1)emit(BLE_GAP_EVENT_ENC_CHANGE,518);else{connection.sec_state.encrypted=1;emit(BLE_GAP_EVENT_ENC_CHANGE,0);}};
 require(CALL_SECURITY,"confirmed missing key permits one fresh repair");require(startCount==2&&deleteCount==1,"repair starts security again exactly once");
 reset();p4BleSecurityBeginAttempt();tick=[&](){emit(BLE_GAP_EVENT_ENC_CHANGE,518);};
 require(!CALL_SECURITY,"repeated missing-key failure must terminate");require(startCount==2&&deleteCount==1,"missing-key repair cannot loop or repeatedly erase");
 reset();p4BleSecurityBeginAttempt();tick=[&](){emit(BLE_GAP_EVENT_ENC_CHANGE,5,99);if(nowMs>=30){connection.sec_state.encrypted=1;emit(BLE_GAP_EVENT_ENC_CHANGE,0);}};
 require(CALL_SECURITY,"another peer's error must not poison the active attempt");
 reset(0xfffffff0u);p4BleSecurityBeginAttempt();uint32_t initial=nowMs;
 require(!CALL_SECURITY,"timeout across rollover");require(uint32_t(nowMs-initial)==10000,"deadline is wrap safe");
 reset();p4BleSecurityBeginAttempt();tick=[&](){allowed=false;};
 require(!CALL_SECURITY,"shutdown cancels authentication");require(nowMs<=10&&std::string(securityError).find("cancel")!=std::string::npos,"cancellation is prompt");
 reset();p4BleSecurityBeginAttempt();initRc=13;
 require(!CALL_SECURITY,"initiation errors fail immediately");require(nowMs==0&&std::string(securityError).find("13")!=std::string::npos,"initiation code survives");
 reset();tick=[&](){if(pendingEvent){auto*e=pendingEvent;pendingEvent=nullptr;e->fn(e);}};
 require(p4BleAwaitHostIdle(1000),"scan result deletion waits for host queue barrier");
 require(nowMs==10&&pendingEvent==nullptr,"host callback barrier was actually drained");
 reset();require(!p4BleAwaitHostIdle(1000),"wedged host barrier is bounded");
 require(p4BleHostDrainIsPending(),"timed out barrier stays pending and blocks unsafe reuse");
 auto*queued=pendingEvent;pendingEvent=nullptr;queued->fn(queued);
 require(!p4BleHostDrainIsPending(),"late host completion safely clears persistent barrier");
 p4BleSecurityShutdown();require(listener==nullptr,"listener is removed before BLE teardown");
 require(p4BleSecurityInit(),"same-boot reinitialization");p4BleSecurityShutdown();
 puts("PASS: bounded security, actual encryption, error codes, peer isolation, one adapter repair, host barrier and listener lifecycle");
}
'''

class SecurityHost(unittest.TestCase):
 def _run_production_call(self, probe=False):
  source=(ROOT/'s3xy_ble.h').read_text()
  call=re.search(r'const bool secureNow = (.*);',source).group(1)
  if probe:
   call=re.search(r'const bool probeSecure = ([\s\S]*?);',source).group(1).strip()
   start=source.index('  const bool probeSecure = ')
   after=source[source.index(';',start)+1:]
   if after.lstrip().startswith('portENTER_CRITICAL'):
    end=after.index('portEXIT_CRITICAL(&s3xyMux);')+len('portEXIT_CRITICAL(&s3xyMux);')
    call='([&](){bool result='+call+';'+after[:end]+'return result;}())'
   call=call.replace('s3xyProbeClient','client').replace('probeError','securityError').replace('probeResult','securityResult')
  init=source.index('static bool s3xyMapperInit() {')
  config=source[source.index('  BLESecurity::setCapability',init):source.index('  BLEScan *scan',init)]
  header=ROOT/'p4_ble_security.h'
  if header.exists():
   adapter='#include "p4_ble_security.h"\n'
  else:
   # Legacy source has no adapter. Its actual consumer expression above invokes
   # BLEClient::secureConnection(), whose characterized lost-event wait is modeled.
   adapter='struct P4BleSecurityResult{};static bool p4BleSecurityInit(){return true;}static void p4BleSecurityBeginAttempt(){}static void p4BleSecurityShutdown(){}\n'
  if 'p4BleAwaitHostIdle' not in source:
   adapter+='static bool p4BleAwaitHostIdle(uint32_t){return true;}static bool p4BleHostDrainIsPending(){return false;}\n'
  adapter+='static char s3xyLastProbeError[64]={};static P4BleSecurityResult s3xyLastProbeSecurity;static int s3xyMux=0;\n'
  check='require(std::string(s3xyLastProbeError).find("sm=5")!=std::string::npos,"probe failure is retained outside heavy logs");' if probe else ''
  cpp=PREAMBLE+adapter+MAIN.replace('CALL_SECURITY',call).replace('CONFIG_SECURITY',config).replace('CHECK_PROBE',check)
  with tempfile.TemporaryDirectory() as temp:
   file=Path(temp)/'security.cpp';file.write_text(cpp)
   binary=Path(temp)/'security'
   compile=subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-I',str(ROOT),str(file),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(compile.returncode,0,compile.stdout+compile.stderr)
   result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   print(result.stdout,end='')

 def test_package_identity_and_preserved_net2_runtime(self):
  version=ROOT.name.replace('P4-CAN-Universal-','',1)
  sketch=ROOT/(ROOT.name+'.ino')
  actual=re.search(r'^#define FW_VERSION "([^"\n]+)"',sketch.read_text(),re.M).group(1)
  self.assertEqual(actual,version)
  baseline=json.loads((ROOT/'SOURCE_BASELINE.json').read_text())
  self.assertEqual(baseline['source_fw_version'],'v3.29.1-P4-3TWAI-net2')
  for relative in baseline['preserved_runtime_members']+['dashboard_source.html']:
   self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),baseline['original_source_sha256'][relative],relative)

 def test_operational_security_call(self):
  self._run_production_call()

 def test_identity_probe_security_call_and_diagnostics(self):
  self._run_production_call(probe=True)

if __name__=='__main__':unittest.main()
