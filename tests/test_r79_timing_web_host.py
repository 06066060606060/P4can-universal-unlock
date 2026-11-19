"""Run actual HTTP serializers against an immutable journal fixture."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include "r79_timing_capture_pure.h"
#define FW_VERSION "v3.29.4"
#define CONTENT_LENGTH_UNKNOWN ((size_t)-1)
using p4_r79_timing::Snapshot;
using p4_r79_timing::Event;
struct Client {bool connected(){return true;}};
struct Server {
 int status=0;std::string body,type;Client peer;
 void send(int code,const char*t,const char*b){status=code;type=t;body=b;}
 void sendContent(const char*b){body+=b;}
 void sendHeader(const char*,const char*){}
 void setContentLength(size_t){}
 Client& client(){return peer;}
} server;
static Snapshot state={1,2,32768,3,4,100,200,false,false};
static bool lease=false,allocFailed=false,allowStart=true,expireDuringExport=false;
static unsigned exportCalls=0;
static std::vector<Event> rows;
namespace p4_r79_driver { struct State {uint32_t bootId=77,lost=2,failures=1;bool saturated=false,pending=false,allocationFailed=false;}; static State state; }
static bool driverPrepared=true;
bool p4R79TimingDriverPrepare(){return driverPrepared;}
void p4R79TimingDriverStarted(){}
void p4R79TimingDriverPoll(bool=false){}
const char* p4CanRoleName(uint8_t bus){return bus==0?"VEHICLE":bus==1?"BODY":"PARTY";}

int64_t esp_timer_get_time(){return 200;}
Snapshot p4R79TimingSnapshot(){return state;}
bool p4R79TimingExportBusy(){return lease;}
bool p4R79TimingAllocationFailed(){return allocFailed;}
bool p4R79TimingStart(){if(!allowStart)return false;state.active=true;return true;}
void p4R79TimingStop(){state.active=false;}
bool p4R79TimingBeginExport(Snapshot& s){++exportCalls;if(expireDuringExport)state.active=false;if(lease||state.active)return false;lease=true;s=state;return true;}
void p4R79TimingEndExport(){lease=false;}
bool p4R79TimingRead(uint32_t i,Event& e){if(i>=rows.size())return false;e=rows[i];return true;}
const char* p4R79TimingStageName(uint8_t k){return k==1?"RX":"TX_REJECTED";}
#include "r79_timing_web.h"
int main(){
 Event rx{};rx.sequence=1;rx.timeUs=110;rx.bus=0;rx.mux=1;rx.kind=1;rx.dlc=8;rx.data[0]=1;rx.data[7]=0xab;
 Event tx=rx;tx.sequence=2;tx.timeUs=140;tx.callUs=120;tx.callId=7;tx.kind=4;tx.waitTicks=2;tx.result=263;tx.rxSequence=1;tx.rxUs=110;tx.readyMask=15;tx.reason=p4_r79_timing::DRIVER_ERROR;
 rows={rx,tx};
 httpP4R79TimingStatus();assert(server.status==200&&server.body.find("\"dropped\":3")!=std::string::npos&&server.body.find("\"completionMeasured\":false")!=std::string::npos);
 allowStart=false;httpP4R79TimingStart();assert(server.status==409);
 allocFailed=true;httpP4R79TimingStart();assert(server.status==503);
 allocFailed=false;allowStart=true;httpP4R79TimingStart();assert(server.status==200&&state.active);
 httpP4R79TimingCsv();assert(server.status==409&&!lease);
 httpP4R79TimingStop();assert(server.status==200&&!state.active);
 httpP4R79TimingCsv();assert(server.status==200&&server.type=="text/csv"&&!lease);
 assert(server.body.find("# firmware,v3.29.4")!=std::string::npos);
 assert(server.body.find(",rx_event_seq,rx_observed_us,rx_to_event_us,driver_call_us,gate_reason,ready_mask,imported_us,error_seq,ecc,tec,rec,status")!=std::string::npos);
 assert(server.body.find("# dropped,3")!=std::string::npos);
 assert(server.body.find("# boot_id,77")!=std::string::npos);
 assert(server.body.find("# bus,0=VEHICLE 1=BODY 2=PARTY")!=std::string::npos);
 assert(server.body.find(",1,110,30,20,DRIVER_ERROR,15,")!=std::string::npos);
 assert(server.body.find("session,event_seq,observed_us,elapsed_us,stage,bus,mux,call_id,call_started_us,wait_ticks,result,dlc,data_hex")!=std::string::npos);
 assert(server.body.find("1,1,110,10,RX,0,1,0,0,0,0,8,01000000000000AB")!=std::string::npos);
 assert(server.body.find("1,2,140,40,TX_REJECTED,0,1,7,120,2,263,8,01000000000000AB")!=std::string::npos);
 state.active=true;expireDuringExport=true;const auto exportsBefore=exportCalls;
 httpP4R79TimingCsv();assert(server.status==409&&exportCalls==exportsBefore&&!lease);
 expireDuringExport=false;state.active=false;
 // Maximum-value metadata and extended rows must remain complete CSV.
 state={UINT32_MAX,1,32768,UINT32_MAX,UINT32_MAX,UINT64_MAX-1000,UINT64_MAX-1,false,false};
 Event maximum{};maximum.sequence=UINT32_MAX;maximum.timeUs=UINT64_MAX-2;maximum.callUs=UINT64_MAX-999;
 maximum.callId=maximum.waitTicks=maximum.rxSequence=maximum.readyMask=maximum.errorSeq=UINT32_MAX;
 maximum.ecc=maximum.tec=maximum.rec=maximum.status=UINT32_MAX;maximum.importedUs=UINT64_MAX;
 maximum.rxUs=UINT64_MAX-1000;maximum.kind=4;maximum.bus=1;maximum.dlc=8;
 maximum.reason=p4_r79_timing::ALL_CONTROLLERS_NOT_READY;maximum.result=INT32_MIN;
 memset(maximum.data,255,8);rows={maximum};
 p4_r79_driver::state.bootId=p4_r79_driver::state.lost=p4_r79_driver::state.failures=UINT32_MAX;
 p4_r79_driver::state.saturated=p4_r79_driver::state.pending=true;
 httpP4R79TimingStatus();assert(server.status==200&&server.body.back()=='}');
 httpP4R79TimingCsv();assert(server.status==200&&!lease);
 assert(server.body.find("# ready_mask,")!=std::string::npos&&server.body.find("ALL_CONTROLLERS_NOT_READY")!=std::string::npos);
 const auto rowStart=server.body.find("\n4294967295,4294967295,");assert(rowStart!=std::string::npos);
 const auto tail=server.body.substr(rowStart+1);assert(std::count(tail.begin(),tail.end(),',')==24&&tail.back()=='\n');
 driverPrepared=false;httpP4R79TimingStart();assert(server.status==503);
 puts("PASS: actual HTTP status/start/stop/export, backpressure errors and exact CSV provenance");
}
'''
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'web.cpp';out=Path(td)/'web';src.write_text(CODE)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)

# Retired feature routes must be absent, while ordinary TLSSC remains available.
web=(ROOT/'web_api.h').read_text()
logic=(ROOT/'vehicle_logic.h').read_text()
for retired_route in ('/api/features/banned', '/api/features/tlssc-restore'):
 assert retired_route not in web, 'retired feature endpoint remains reachable: '+retired_route
for retired_runtime in ('bannedCar', 'tlsscRestoreEnabled', 'doInjectTlsscRestore'):
 assert not any(retired_runtime in (ROOT/name).read_text() for name in
                ('web_api.h','vehicle_logic.h','can_runtime.h','p4can_core_state.h','p4can_forward.h')), retired_runtime
assert 'static void doInjectTLSSC' in logic or 'static bool doInjectTLSSC' in logic or 'tlsscEnabled' in logic
assert 'server.hasArg("section")' in web, 'system diagnostics ignores requested section'
assert 'heap_caps_get_minimum_free_size' in web, 'memory diagnostics omits measured low water mark'
# The promoted AP Control may be configured without exposing the LAB menu.
ap_update=web[web.index('static void httpR79ApControlUpdate()'):web.index('static void httpR79Stats()',web.index('static void httpR79ApControlUpdate()'))]
assert 'if (!labMenuEnabled)' not in ap_update, 'promoted AP Control still requires LAB menu visibility'
assert 'r79ApControlApply(next)' in ap_update

# Compile actual selected HTTP serializers with measured-provider spies. The
# legacy recovery body is isolated so requesting memory cannot touch TWAI/NVS.
def function(source, signature):
 start=source.index(signature)
 begin=source.index('{',start)
 depth=1;end=begin+1
 while depth:
  if source[end]=='{': depth+=1
  elif source[end]=='}': depth-=1
  end+=1
 return source[start:end]

DIAG=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <map>
#include <vector>
class String:public std::string {
public:
 using std::string::string;
 using std::string::operator+=;
 String(const std::string&s):std::string(s){}
 String& operator+=(unsigned long n){append(std::to_string(n));return *this;}
 String& operator+=(long n){append(std::to_string(n));return *this;}
};
#include "json_writer_arduino.h"
static int heapCalls=0,systemCalls=0,wirelessCalls=0,recoveryCalls=0,bleCalls=0;
struct {uint32_t getFreeHeap(){++heapCalls;return 900;} uint32_t getMinFreeHeap(){++heapCalls;return 800;} uint32_t getMaxAllocHeap(){++heapCalls;return 700;}} ESP;
constexpr uint32_t MALLOC_CAP_INTERNAL=1,MALLOC_CAP_8BIT=2,MALLOC_CAP_SPIRAM=4;
uint32_t heap_caps_get_total_size(uint32_t cap){++heapCalls;return cap==3?10000:20000;}
uint32_t heap_caps_get_free_size(uint32_t cap){++heapCalls;return cap==3?8000:17000;}
uint32_t heap_caps_get_minimum_free_size(uint32_t cap){++heapCalls;return cap==3?6000:14000;}
uint32_t heap_caps_get_largest_free_block(uint32_t cap){++heapCalls;return cap==3?5000:13000;}
uint32_t millis(){return 5000;}
constexpr uint8_t P4_CAN_COUNT=3;
constexpr uint32_t CAN_TRAFFIC_UI_FRESH_MS=1500;
static const char* p4CanRoleName(uint8_t bus){return bus==0?"VEHICLE":bus==1?"BODY":"PARTY";}
static uint32_t p4CanTxPins[]={20,22,26},p4CanRxPins[]={21,23,27};
static bool p4CanGpioValid=true;
static uint32_t p4CanState[]={1,2,1},p4CanLastRxMs[]={4990,0,2000};
static uint32_t p4CanStatusMs[]={4900,0,2900};
static uint32_t p4CanRxCount[3]={},p4CanTxAccepted[3]={},p4CanTxRejected[3]={};
static uint32_t p4CanBusOffCount[3]={},p4CanMissed[3]={},p4CanOverrun[3]={};
static uint32_t p4CanRxPolls[3]={},p4CanTec[3]={},p4CanRec[3]={},p4CanTxQueued[3]={},p4CanRxQueued[3]={};
static uint32_t p4CanBusErrors[3]={},p4CanArbLost[3]={},p4CanDriverTxFailed[3]={};
static uint32_t p4CanRecoveries[3]={},p4CanRecoveryFailures[3]={},p4CanInitError[3]={},p4CanLastRxResult[3]={};
static bool p4CanOnline[]={true,false,true},p4CanPassive[]={false,true,false};
using esp_err_t=int;
const char* esp_err_to_name(int){return "ESP_OK";}
uint32_t p4CanConfiguredBitrate(uint8_t){return 500000;}
constexpr bool S3XY_DIAGNOSTICS_ENABLED=true;
constexpr unsigned S3XY_LOG_MAX=64;
static void systemCoreWriteStatus(JsonWriterArduino&jw){++systemCalls;jw.u32("uptimeS",5);}
static void systemWirelessWriteStatus(JsonWriterArduino&jw){++wirelessCalls;jw.string("networkState","READY");}
static void systemRecoveryWriteStatus(JsonWriterArduino&jw){++recoveryCalls;jw.u32("runtimeStatsResetCount",2);}
static String s3xyStatsToJson(){++bleCalls;return "{\"bluetoothEnabled\":true}";}
struct Server {
 std::map<std::string,String> args;int status=0;String body;
 bool hasArg(const char*k){return args.count(k);}
 String arg(const char*k){return args[k];}
 void send(int c,const char*,const String&b){status=c;body=b;}
} server;
static void clearCalls(){heapCalls=systemCalls=wirelessCalls=recoveryCalls=bleCalls=0;}
'''
# Share the same timing descriptor used by production installation/export.
can_source=(ROOT/'p4_can.h').read_text()
timing_source=can_source[can_source.index('struct P4CanTimingConfiguration {'):can_source.index('static bool p4CanInstall(')]
DIAG=DIAG.replace('uint32_t p4CanConfiguredBitrate(uint8_t){return 500000;}',
    '#include "tests/fakes/driver/twai.h"\nconstexpr uint8_t P4_CHASSIS=1;\nstatic bool activeProfileIsYl(){return true;}\n'+timing_source)
DIAG_MAIN=r'''
int main(){
 assert(p4CanConfiguredBitrate(0)==500000 && p4CanConfiguredBitrate(3)==0);
 p4CanGpioValid=false;server.args={{"section","can1"}};httpSystemStats();
 assert(server.body.find("\"can1TxPin\":null")!=std::string::npos&&server.body.find("\"can1RxPin\":null")!=std::string::npos);
 p4CanGpioValid=true;
 for(const char*s:{"system","memory","wireless","ble","can1","can2","can3","recovery",""})assert(systemStatsSectionValid(s));
 assert(systemStatsSectionValid(nullptr));assert(!systemStatsSectionValid("can4"));assert(!systemStatsSectionValid("System"));
 for(const char*s:{"system","memory","wireless","ble","can1","can2","can3","recovery"}){
  clearCalls();server.args={{"section",s}};httpSystemStats();assert(server.status==200);
  std::string group=s;
  assert(systemCalls==(group=="system"));assert(wirelessCalls==(group=="wireless"));assert(recoveryCalls==(group=="recovery"));assert(bleCalls==(group=="ble"));assert(heapCalls==(group=="memory"?11:0));
  if(group=="memory"){
   for(const char*field:{"\"internalRamFreeBytes\":8000","\"internalRamMinFreeBytes\":6000","\"internalRamLargestBlockBytes\":5000","\"psramTotalBytes\":20000","\"psramFreeBytes\":17000","\"psramMinFreeBytes\":14000","\"psramLargestBlockBytes\":13000"})assert(server.body.find(field)!=std::string::npos);
   assert(server.body.find("can1")==std::string::npos);assert(server.body.find("uptimeS")==std::string::npos);
  }
  if(group.substr(0,3)=="can"){
   for(int bus=1;bus<=3;bus++)assert((server.body.find("can"+std::to_string(bus)+"Name")!=std::string::npos)==(bus==s[3]-'0'));
   assert(server.body.find("\"can"+std::string(1,s[3])+"Bitrate\":500000")!=std::string::npos);
   assert(server.body.find("RxCounterLifetime\":\"BOOT")!=std::string::npos);
   assert(server.body.find("AppCounterLifetime\":\"RESET_STATS")!=std::string::npos);
   assert(server.body.find("DriverCounterLifetime\":\"DRIVER_INSTALL")!=std::string::npos);
  }
 }
 p4CanBusErrors[1]=261;server.args={{"section","can2"},{"view","errors"}};httpSystemStats();
 assert(server.body.find("\"can2ErrorCountersFrozen\":true")!=std::string::npos);
 assert(server.body.find("\"can2BusErrors\":261")!=std::string::npos);
 for(const char*view:{"status","traffic","errors","recovery"}){
  server.args={{"section","can1"},{"view",view}};httpSystemStats();assert(server.status==200);
  const std::string v=view;
  for(const char*field:{"State","Ready","StatusSeen","StatusAgeMs"})assert(server.body.find("can1"+std::string(field))!=std::string::npos);
  assert((server.body.find("can1Bitrate")!=std::string::npos)==(v=="status"));
  assert((server.body.find("can1RxCount")!=std::string::npos)==(v=="traffic"));
  assert((server.body.find("can1Tec")!=std::string::npos)==(v=="errors"));
  assert((server.body.find("can1Recoveries")!=std::string::npos)==(v=="recovery"));
 }
 for(const char*view:{"", "STATUS", "unknown"}){
  clearCalls();server.args={{"section","can1"},{"view",view}};httpSystemStats();assert(server.status==400&&heapCalls==0&&recoveryCalls==0&&bleCalls==0);
 }
 server.args={{"section","memory"},{"view","status"}};httpSystemStats();assert(server.status==400);
 server.args={{"view","status"}};httpSystemStats();assert(server.status==400);
 server.args={{"section","can3"}};httpSystemStats();assert(server.body.find("\"can3StatusSeen\":true")!=std::string::npos&&server.body.find("\"can3StatusAgeMs\":2100")!=std::string::npos);
 server.args={{"section","can2"}};httpSystemStats();assert(server.body.find("\"can2StatusSeen\":false")!=std::string::npos);
 clearCalls();server.args={{"section","unknown"}};httpSystemStats();assert(server.status==400&&heapCalls==0&&recoveryCalls==0&&systemCalls==0&&bleCalls==0);
 for(bool explicitEmpty:{false,true}){
  clearCalls();server.args.clear();if(explicitEmpty)server.args["section"]="";httpSystemStats();
  assert(server.status==200&&heapCalls==11&&systemCalls==1&&wirelessCalls==1&&recoveryCalls==1&&bleCalls==1);
  assert(server.body.find("can1Name")!=std::string::npos&&server.body.find("can3Name")!=std::string::npos);
 }
 puts("PASS: actual section HTTP selection, measured numeric heaps, CAN identity/bitrate/lifetime/staleness, invalid 400 and full backward response");
}
'''
selected='\n'.join(function(web, signature) for signature in (
 'static bool systemStatsSectionValid(', 'static void systemMemoryWriteStatus(',
 'static void p4CanWriteStatus(', 'static String systemStatsToJson(',
 'static void httpSystemStats()'))
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'diag.cpp';out=Path(td)/'diag';src.write_text(DIAG+selected+DIAG_MAIN)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)

# Execute the actual persisted blob writer and the complete read/publish prefix
# (the following code configures unrelated features). Retired byte values and
# scalar-key values may never influence active settings or a write result.
store_source=function(logic,'static bool featureCfgPersistCandidate(')
load_source=function(logic,'static void featureCfgLoad()')
load_prefix=load_source[:load_source.index('    portENTER_CRITICAL(&blinkAMux)')]+'}\n'
assert 'bytes[2]' not in load_source and 'bytes[4]' not in load_source
assert 'prefs.getBool("banned"' not in load_source and 'prefs.getBool("tlRestore"' not in load_source
snapshot=logic[logic.index('struct FeatureCfgSnapshot {'):logic.index('static FeatureCfgSnapshot featureCfgRuntimeSnapshot()')]
STORE=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
static bool featureConfigNvsReadOk=true,featureCfgReadOk=true;
static bool labMenuEnabled=false,doorOpenCancelEnabled=false;
static bool readFound=true,readOk=true,writeOk=true,cleanupOpens=true,cleanupSucceeds=true;
static uint8_t incoming[14]={1,1,255,1,255,1,2,1,0x34,0x12,3,1,0x78,0x56};
static std::vector<uint8_t> saved;
static std::vector<std::string> readKeys,removed;
struct CheckedPreferences {
 bool begin(const char*,bool){return true;}
 void end(){}
 bool ok(){return readOk;}
 bool isKey(const char*k){readKeys.push_back(k);return true;}
 bool getBool(const char*k,bool){readKeys.push_back(k);return true;}
 uint8_t getUChar(const char*k,uint8_t d){readKeys.push_back(k);return d;}
 uint16_t getUShort(const char*k,uint16_t d){readKeys.push_back(k);return d;}
};
struct Preferences {
 bool begin(const char*,bool){return cleanupOpens;}
 bool remove(const char*k){removed.push_back(k);return cleanupSucceeds;}
 void end(){}
};
constexpr uint8_t AP_DRIVE_REGEN_REDUCED_RAW=1,NAG_RIGHT_SCROLL_PATTERN_DEFAULT=1;
constexpr uint16_t AP_RIGHT_SCROLL_DEFAULT_INTERVAL_S_PURE=5;
bool nvsCheckedReadBlob(const char*,const char*,uint8_t*b,size_t n,bool&found){assert(n==14);found=readFound;if(found)memcpy(b,incoming,n);return readOk;}
bool nvsCheckedWriteBlob(const char*,const char*,const uint8_t*b,size_t n){assert(n==14);if(writeOk)saved.assign(b,b+n);return writeOk;}
uint16_t featureNvsU16(const uint8_t*b){return b[0]|(uint16_t(b[1])<<8);}
uint16_t apRightScrollIntervalSanitizePure(uint16_t n){return n;}
uint8_t nagRightScrollPatternSanitize(uint8_t n){return n;}
bool activeProfileBodyControlsSupported(){return true;}
bool activeProfileIsYl(){return false;}
bool activeProfileApDriveProfileSupported(){return true;}
bool apDriveRegenRawSelectablePure(uint8_t n){return n<=3;}
'''
STORE_MAIN=r'''
int main(){
 for(bool blob:{false,true}){
  readFound=blob;readKeys.clear();labMenuEnabled=doorOpenCancelEnabled=false;featureCfgLoad();
  assert(labMenuEnabled&&doorOpenCancelEnabled&&featureCfgReadOk);
  for(const auto&key:readKeys)assert(key!="banned"&&key!="tlRestore");
 }
 FeatureCfgSnapshot value={true,true,true,2,true,0x1234,3,true,0x5678};
 assert(featureCfgPersistCandidate(value));
 const std::vector<uint8_t> expected={1,1,0,1,0,1,2,1,0x34,0x12,3,1,0x78,0x56};
 assert(saved==expected);assert(removed==std::vector<std::string>({"banned","tlRestore"}));
 cleanupSucceeds=false;assert(featureCfgPersistCandidate(value)&&saved==expected);
 cleanupOpens=false;assert(featureCfgPersistCandidate(value)&&saved==expected);
 removed.clear();writeOk=false;assert(!featureCfgPersistCandidate(value)&&removed.empty());
 writeOk=true;featureCfgReadOk=false;assert(!featureCfgPersistCandidate(value));
 puts("PASS: retired blob offsets ignored/zeroed, active offsets unchanged, scalar keys unread, best-effort retirement and durable write errors");
}
'''
# Prefix locals intentionally include settings owned by the unexecuted continuation.
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'store.cpp';out=Path(td)/'store';src.write_text(STORE+snapshot+load_prefix+store_source+STORE_MAIN)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-Wno-unused-variable','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)

AP=r'''
static bool labMenuEnabled=false,applyOk=true;
static int applies=0;
struct R79ApGateConfigPure{bool enabled;uint8_t mode;uint8_t delaySeconds;bool allowManualDriving;};
static R79ApGateConfigPure applied={};
bool r79DelayTextParsePure(const char*t,uint16_t maximum,uint16_t&out){
 if(!t||!*t)return false;uint32_t n=0;
 for(;*t;++t){if(*t<'0'||*t>'9')return false;n=n*10+(*t-'0');if(n>maximum)return false;}
 out=(uint16_t)n;return true;
}
bool r79ApControlApply(const R79ApGateConfigPure&next){++applies;applied=next;return applyOk;}
String r79ApControlStatsToJson(){return "{\"enabled\":true}";}
'''
AP_MAIN=r'''
int main(){
 assert(!labMenuEnabled);
 server.args={{"enabled","1"},{"mode","1"},{"delaySeconds","4"},{"allowManualDriving","0"}};
 httpR79ApControlUpdate();assert(server.status==200&&applies==1&&applied.enabled&&applied.mode==1&&applied.delaySeconds==4&&!applied.allowManualDriving);
 applyOk=false;httpR79ApControlUpdate();assert(server.status==503&&applies==2);
 server.args["delaySeconds"]="99";httpR79ApControlUpdate();assert(server.status==400&&applies==2);
 server.args.erase("enabled");httpR79ApControlUpdate();assert(server.status==400&&applies==2);
 puts("PASS: promoted AP Control stores while LAB hidden, and retains field validation/apply failure handling");
}
'''
# Reuse the HTTP fixture without the independent diagnostic providers.
ap_preamble=DIAG[:DIAG.index('static int heapCalls=')]+DIAG[DIAG.index('struct Server {'):DIAG.index('static void clearCalls()')]
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'ap.cpp';out=Path(td)/'ap';src.write_text(ap_preamble+AP+function(web,'static void httpR79ApControlUpdate()')+AP_MAIN)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)

WIRELESS=r'''
static bool p4NetworkPinsReady=false,p4NetworkWifiStarted=false,p4NetworkApStarted=false;
static uint32_t p4NetworkHostVersion[3]={},p4NetworkSlaveVersion[3]={};
const char* p4NetworkPhaseName(){return p4NetworkApStarted?"READY":"NOT_STARTED";}
static int ipCalls=0,clientCalls=0;
struct IP{String toString(){return "192.168.4.1";}};
struct {int getMode(){return 2;}IP softAPIP(){++ipCalls;return {};}int softAPgetStationNum(){++clientCalls;return 3;}}WiFi;
'''
WIRELESS_MAIN=r'''
int main(){
 String s;JsonWriterArduino empty(s);systemWirelessWriteStatus(empty);empty.finish();
 assert(s.find("hostedHostVersion")==std::string::npos&&s.find("hostedC6Version")==std::string::npos);
 assert(s.find("apIp")==std::string::npos&&s.find("apClients")==std::string::npos&&ipCalls==0&&clientCalls==0);
 p4NetworkPinsReady=p4NetworkWifiStarted=p4NetworkApStarted=true;
 p4NetworkHostVersion[0]=2;p4NetworkHostVersion[1]=6;p4NetworkHostVersion[2]=1;
 p4NetworkSlaveVersion[0]=2;p4NetworkSlaveVersion[1]=6;p4NetworkSlaveVersion[2]=0;
 s.clear();JsonWriterArduino ready(s);systemWirelessWriteStatus(ready);ready.finish();
 assert(s.find("\"hostedHostVersion\":\"2.6.1\"")!=std::string::npos);
 assert(s.find("\"hostedC6Version\":\"2.6.0\"")!=std::string::npos);
 assert(s.find("\"apClients\":3")!=std::string::npos&&s.find("192.168.4.1")!=std::string::npos&&ipCalls==1&&clientCalls==1);
 assert(s.find("c6Free")==std::string::npos&&s.find("c6Cpu")==std::string::npos);
 puts("PASS: actual wireless versions/AP metrics and unsupported omission without invented C6 RAM/CPU");
}
'''
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'wireless.cpp';out=Path(td)/'wireless';src.write_text(DIAG[:DIAG.index('static int heapCalls=')]+WIRELESS+function(web,'static void systemWirelessWriteStatus(')+WIRELESS_MAIN)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)

# A 64-row BUS-OFF export must be assembled before the HTTP response starts.
# Exercise the actual A/B handlers and their shared helpers: substituting a
# standalone CSV builder would miss per-row sendContent calls in these routes.
core=(ROOT/'can_core.h').read_text()
gate=(ROOT/'runtime_gate_pure.h').read_text()
trace_types='\n'.join((
 core[core.index('enum CanTxTraceSource :'):core.index('static portMUX_TYPE canBTxTraceMux')],
 core[core.index('static constexpr uint8_t CAN_A_TX_TRACE_CAPACITY'):core.index('static portMUX_TYPE canATxTraceMux')],
 gate[gate.index('enum NativeATxResultReason :'):gate.index('static inline NativeATxResultReason nativeATxResultReasonPure(')],
 function(core,'static inline const char* nagTxBlockReasonName('),
))
trace_source=web[web.index('static const char *canTxTraceSourceName('):
                 web.index('// ─── Wi-Fi access-point configuration')]
TRACE=r'''
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <map>
#include <string>
#include <vector>
#include "text_format_pure.h"
static bool stringReserveFails=false;
static int stringConcatCalls=0,stringConcatFailureAt=0;
class String {
 std::string value;
public:
 String()=default;
 String(const char*s):value(s?s:""){}
 bool reserve(size_t n){if(stringReserveFails)return false;value.reserve(n);return true;}
 bool concat(const char*s,size_t n){
  ++stringConcatCalls;
  if(stringConcatFailureAt==stringConcatCalls)return false;
  value.append(s,n);return true;
 }
 bool concat(const char*s){return concat(s,strlen(s));}
 size_t length()const{return value.length();}
 const char*c_str()const{return value.c_str();}
};
static int formatCalls=0,formatFailureAt=0,formatTruncationAt=0;
int traceSnprintf(char*out,size_t capacity,const char*format,...){
 ++formatCalls;
 if(formatCalls==formatFailureAt){if(capacity)out[0]='\0';return -1;}
 if(formatCalls==formatTruncationAt){if(capacity)out[0]='\0';return (int)capacity;}
 va_list args;va_start(args,format);const int n=vsnprintf(out,capacity,format,args);va_end(args);return n;
}
static int criticalDepth=0;
#define portENTER_CRITICAL(mux) do{(void)(mux);++criticalDepth;}while(0)
#define portEXIT_CRITICAL(mux) do{(void)(mux);--criticalDepth;}while(0)
#define CONTENT_LENGTH_UNKNOWN ((size_t)-1)
using esp_err_t=int;
constexpr esp_err_t ESP_OK=0;
const char*esp_err_to_name(esp_err_t e){return e==0?"ESP_OK":e==263?"ESP_ERR_TIMEOUT":"ESP_FAIL";}
constexpr uint8_t CAN_BUS_OFF_BUS_A_PURE=0,CAN_BUS_OFF_BUS_B_PURE=1;
const char*canBusOffRecordBootName(uint8_t){return "PREVIOUS_BOOT";}
const char*canBusOffPersistStateName(uint8_t){return "LOADED";}
const char*canBusOffPersistErrorName(uint8_t){return "NONE";}
static struct {uint16_t targetId=0x3C0;} nagCfg;
struct Client {bool connected(){return true;}};
struct Server {
 int status=0,sendCalls=0,sendContentCalls=0,wireWrites=0,writesAfterFailure=0,failWireWriteAt=0;
 bool wireFailed=false;
 size_t contentLength=(size_t)-2;
 std::string body,type;
 std::vector<int>statuses;
 std::map<std::string,std::string>headers;
 Client peer;
 bool write(){
  assert(criticalDepth==0);
  ++wireWrites;
  if(wireFailed){++writesAfterFailure;return false;}
  if(wireWrites==failWireWriteAt){wireFailed=true;return false;}
  return true;
 }
 void send(int code,const char*t,const String&b){
  assert(criticalDepth==0);++sendCalls;statuses.push_back(code);status=code;type=t;body=b.c_str();
  if(!write())return;
  if(b.length())write();
 }
 void sendContent(const char*b){
  ++sendContentCalls;body+=b;
  // Unknown-length WebServer chunks use prefix/data/trailer writes. Once a
  // simulated write fails, every subsequent handler chunk remains blocked.
  if(contentLength==CONTENT_LENGTH_UNKNOWN){write();write();write();}
  else write();
 }
 void sendHeader(const char*k,const char*v){assert(criticalDepth==0);headers[k]=v;}
 void setContentLength(size_t n){assert(criticalDepth==0);contentLength=n;}
 Client&client(){return peer;}
}server;
'''
TRACE_STATE=r'''
static int canATxTraceMux=0,canBTxTraceMux=0;
static CanATxTraceEntry canATxTraceFrozen[CAN_A_TX_TRACE_CAPACITY]={};
static CanBTxTraceEntry canBTxTraceFrozen[CAN_B_TX_TRACE_CAPACITY]={};
static uint8_t canATxTraceFrozenCount=0,canBTxTraceFrozenCount=0;
static uint32_t canATxTraceFrozenMs=0,canBTxTraceFrozenMs=0;
static uint32_t canATxTraceFrozenBusOffOrdinal=0,canBTxTraceFrozenBusOffOrdinal=0;
static CanABusOffSnapshot canALastBusOffSnapshot={};
'''
TRACE_MAIN=r'''
static const char*headerA="seq,relative_ms,uptime_ms,id,source,dlc,nativeA_result,result_name,gate_reason,raw\n";
static const char*headerB="seq,relative_ms,uptime_ms,id,source,dlc,result,result_name,raw\n";
static void resetResponse(){
 server=Server{};stringReserveFails=false;stringConcatCalls=stringConcatFailureAt=0;
 formatCalls=formatFailureAt=formatTruncationAt=0;
}
static void fillTrace(){
 const uint8_t bytes[]={0x00,0x11,0x22,0x33,0x44,0x55,0x66,0xFF};
 for(size_t i=0;i<64;++i){
  CanATxTraceEntry&a=canATxTraceFrozen[i];a={};
  a.seq=UINT32_MAX;a.capturedMs=900;a.id=0x3FD;a.dlc=255;
  a.source=CAN_TX_TRACE_SOURCE_AUTO_BLINKER;a.reason=NATIVE_A_TX_SEND_ERROR;
  a.result=INT32_MIN;memcpy(a.data,bytes,sizeof(bytes));
  CanBTxTraceEntry&b=canBTxTraceFrozen[i];b={};
  b.seq=UINT32_MAX;b.capturedMs=900;b.id=0x3FD;b.dlc=255;
  b.source=CAN_TX_TRACE_SOURCE_DEFAULT;b.result=263;memcpy(b.data,bytes,sizeof(bytes));
 }
 canATxTraceFrozenCount=canBTxTraceFrozenCount=64;
 canATxTraceFrozenMs=canBTxTraceFrozenMs=1000;
 canATxTraceFrozenBusOffOrdinal=canBTxTraceFrozenBusOffOrdinal=UINT32_MAX;
 canALastBusOffSnapshot={true,1000,0xFF,255,UINT32_MAX,1,2,3};
}
static void assertSuccessfulResponse(bool busA,const std::string&expected){
 assert(server.status==200&&server.type=="text/csv");
 assert(server.body==expected);
 assert(server.sendCalls==1&&server.statuses==std::vector<int>{200});
 assert(server.sendContentCalls==0&&"bounded TX CSV must not emit per-row HTTP chunks");
 assert(server.contentLength==expected.size());
 assert(server.headers["Content-Disposition"]==(busA?
  "attachment; filename=P4-CAN_CANA_TX_TRACE.csv":"attachment; filename=P4-CAN_CANB_TX_TRACE.csv"));
 assert(criticalDepth==0);
}
template<class T>static void addEvidence(std::string&out,const T&v){
 out.append(reinterpret_cast<const char*>(&v),sizeof(v));
}
static std::string frozenEvidence(){
 std::string out;
 addEvidence(out,canATxTraceFrozen);addEvidence(out,canBTxTraceFrozen);
 addEvidence(out,canATxTraceFrozenCount);addEvidence(out,canBTxTraceFrozenCount);
 addEvidence(out,canATxTraceFrozenMs);addEvidence(out,canBTxTraceFrozenMs);
 addEvidence(out,canATxTraceFrozenBusOffOrdinal);addEvidence(out,canBTxTraceFrozenBusOffOrdinal);
 addEvidence(out,canALastBusOffSnapshot);
 return out;
}
static void invokeTrace(bool busA){
 const std::string before=frozenEvidence();
 if(busA)httpCanATxTraceCsv();else httpCanBTxTraceCsv();
 assert(frozenEvidence()==before&&"CSV export must preserve all frozen evidence on success and failure");
 assert(criticalDepth==0);
}
static void assertPreparationFailure(){
 assert(server.status==503&&server.type=="application/json");
 assert(server.statuses==std::vector<int>{503}&&server.sendCalls==1);
 assert(server.sendContentCalls==0);
 assert(server.headers.count("Content-Disposition")==0);
 assert(server.contentLength==(size_t)-2);
 assert(server.body.find("seq,relative_ms")==std::string::npos);
}
int main(){
 fillTrace();
 const std::string metadata="#record_boot,PREVIOUS_BOOT\n#persist_state,LOADED\n#persist_error,NONE\n#bus_off_ordinal,4294967295\n#event_uptime_ms,1000\n#entry_count,64\n";
 std::string expectedA=metadata+"#snapshot_controllerState,0xFF\n#snapshot_tx_fail_seq,255\n#snapshot_rx_age_ms,4294967295\n"+headerA;
 std::string expectedB=metadata+headerB;
 for(size_t i=0;i<64;++i){
  expectedA+="4294967295,-100,900,0x3FD,AUTO_BLINKER,255,-2147483648,ERROR,SEND_ERROR,00 11 22 33 44 55 66 FF\n";
  expectedB+="4294967295,-100,900,0x3FD,R79_SUMMON_TLSSC,255,263,ESP_ERR_TIMEOUT,00 11 22 33 44 55 66 FF\n";
 }
 for(bool busA:{true,false}){
  resetResponse();invokeTrace(busA);assertSuccessfulResponse(busA,busA?expectedA:expectedB);
 }
 // Corrupt/out-of-range count metadata cannot read beyond the frozen arrays
 // or alter the captured count. The exported schema still reports 64 rows.
 canATxTraceFrozenCount=canBTxTraceFrozenCount=255;
 for(bool busA:{true,false}){
  resetResponse();invokeTrace(busA);assertSuccessfulResponse(busA,busA?expectedA:expectedB);
 }
 fillTrace();
 for(bool busA:{true,false}){
  resetResponse();stringReserveFails=true;invokeTrace(busA);assertPreparationFailure();
  assert(stringConcatCalls==0&&formatCalls==0);
  // Metadata, column header, first row and last row failures all remain 503.
  for(int at:{1,2,3,66}){
   resetResponse();stringConcatFailureAt=at;invokeTrace(busA);assertPreparationFailure();
   assert(stringConcatCalls==at);
  }
  // snprintf reports a negative result or the required capacity on truncation.
  // Cover metadata and early/late rows after already successful preparation.
  for(int at:{1,2,65}){
   resetResponse();formatFailureAt=at;invokeTrace(busA);assertPreparationFailure();
   assert(formatCalls==at);
   resetResponse();formatTruncationAt=at;invokeTrace(busA);assertPreparationFailure();
   assert(formatCalls==at);
  }
  for(int at:{1,2}){
   resetResponse();server.failWireWriteAt=at;invokeTrace(busA);
   assertSuccessfulResponse(busA,busA?expectedA:expectedB);
   assert(server.wireFailed&&server.writesAfterFailure==0);
  }
 }
 // Empty records retain their metadata and column header without inventing
 // rows, a capture time or an event ordinal.
 canATxTraceFrozenCount=canBTxTraceFrozenCount=0;
 canATxTraceFrozenMs=canBTxTraceFrozenMs=0;
 canATxTraceFrozenBusOffOrdinal=canBTxTraceFrozenBusOffOrdinal=0;
 canALastBusOffSnapshot={};
 const std::string emptyMetadata="#record_boot,PREVIOUS_BOOT\n#persist_state,LOADED\n#persist_error,NONE\n#bus_off_ordinal,0\n#event_uptime_ms,0\n#entry_count,0\n";
 resetResponse();invokeTrace(true);assertSuccessfulResponse(true,emptyMetadata+
  "#snapshot_controllerState,0x00\n#snapshot_tx_fail_seq,0\n#snapshot_rx_age_ms,0\n"+headerA);
 resetResponse();invokeTrace(false);assertSuccessfulResponse(false,emptyMetadata+headerB);
 // Distinct ordered rows cover the timestamp rollover and both signed
 // relative-time limits, zero/short raw data, source fallbacks and result limits.
 fillTrace();canATxTraceFrozenCount=canBTxTraceFrozenCount=4;
 canATxTraceFrozenMs=canBTxTraceFrozenMs=UINT32_MAX;
 const uint32_t times[]={UINT32_MAX,0,2147483647u,2147483646u};
 const uint16_t idsA[]={0x3C0,0x293,0x334,0x3C2},idsB[]={0x293,0x249,0x334,0x3F8};
 const uint8_t lengths[]={0,1,2,8},reasons[]={NATIVE_A_TX_OK,NATIVE_A_TX_OK,NATIVE_A_TX_SEND_ERROR,NATIVE_A_TX_FRESH_MASK};
 const int32_t results[]={0,INT32_MAX,INT32_MIN,-1};
 for(size_t i=0;i<4;++i){
  auto&a=canATxTraceFrozen[i];auto&b=canBTxTraceFrozen[i];
  a.seq=b.seq=(uint32_t)i;a.capturedMs=b.capturedMs=times[i];
  a.id=idsA[i];b.id=idsB[i];a.dlc=b.dlc=lengths[i];
  a.source=b.source=CAN_TX_TRACE_SOURCE_DEFAULT;a.reason=reasons[i];a.result=b.result=results[i];
 }
 const std::string maxMetadata="#record_boot,PREVIOUS_BOOT\n#persist_state,LOADED\n#persist_error,NONE\n#bus_off_ordinal,4294967295\n#event_uptime_ms,4294967295\n#entry_count,4\n";
 const std::string orderedA=maxMetadata+
  "#snapshot_controllerState,0xFF\n#snapshot_tx_fail_seq,255\n#snapshot_rx_age_ms,4294967295\n"+headerA+
  "0,0,4294967295,0x3C0,NAG,0,0,OK,OK,\n"
  "1,1,0,0x293,AUTO_LANE_CHANGE_ENABLE,1,2147483647,ERROR,OK,00\n"
  "2,-2147483648,2147483647,0x334,PEDAL_MAP,2,-2147483648,ERROR,SEND_ERROR,00 11\n"
  "3,2147483647,2147483646,0x3C2,AUTO_BLINKER_STALKLESS,8,-1,ERROR,FRESH_MASK,00 11 22 33 44 55 66 FF\n";
 const std::string orderedB=maxMetadata+headerB+
  "0,0,4294967295,0x293,AUTO_LANE_CHANGE_ENABLE,0,0,ESP_OK,\n"
  "1,1,0,0x249,AUTO_BLINKER,1,2147483647,ESP_FAIL,00\n"
  "2,-2147483648,2147483647,0x334,PEDAL_MAP,2,-2147483648,ESP_FAIL,00 11\n"
  "3,2147483647,2147483646,0x3F8,DRIVER_ASSIST_OVERLAY,8,-1,ESP_FAIL,00 11 22 33 44 55 66 FF\n";
 resetResponse();invokeTrace(true);assertSuccessfulResponse(true,orderedA);
 resetResponse();invokeTrace(false);assertSuccessfulResponse(false,orderedB);
 // A missing freeze timestamp keeps relative_ms at zero even for a real row.
 canATxTraceFrozenCount=canBTxTraceFrozenCount=1;
 canATxTraceFrozenMs=canBTxTraceFrozenMs=0;
 canATxTraceFrozenBusOffOrdinal=canBTxTraceFrozenBusOffOrdinal=0;
 canALastBusOffSnapshot={};
 const std::string noTimeMetadata="#record_boot,PREVIOUS_BOOT\n#persist_state,LOADED\n#persist_error,NONE\n#bus_off_ordinal,0\n#event_uptime_ms,0\n#entry_count,1\n";
 resetResponse();invokeTrace(true);assertSuccessfulResponse(true,noTimeMetadata+
  "#snapshot_controllerState,0x00\n#snapshot_tx_fail_seq,0\n#snapshot_rx_age_ms,0\n"+headerA+
  "0,0,4294967295,0x3C0,NAG,0,0,OK,OK,\n");
 resetResponse();invokeTrace(false);assertSuccessfulResponse(false,noTimeMetadata+headerB+
  "0,0,4294967295,0x293,AUTO_LANE_CHANGE_ENABLE,0,0,ESP_OK,\n");
 // The actual append helper accepts the exact budget and rejects the next
 // byte without growing or corrupting the already prepared response.
 resetResponse();String bounded;
 const std::string prefix(CAN_TX_TRACE_CSV_MAX_BYTES-1u,'x');
 assert(bounded.concat(prefix.c_str(),prefix.size()));
 assert(canTxTraceCsvAppend(bounded,"y",1,2));
 const std::string atLimit=bounded.c_str();
 assert(atLimit==prefix+"y");
 assert(!canTxTraceCsvAppend(bounded,"z",1,2));
 assert(std::string(bounded.c_str())==atLimit);
 puts("PASS: actual frozen A/B CSV bytes, empty/full/count clamp, signed rollover, bounded single send, preparation failures and immutable evidence");
}
'''
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'trace.cpp';out=Path(td)/'trace'
 src.write_text(TRACE+trace_types+TRACE_STATE+'\n#define snprintf traceSnprintf\n'+trace_source+'\n#undef snprintf\n'+TRACE_MAIN)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
