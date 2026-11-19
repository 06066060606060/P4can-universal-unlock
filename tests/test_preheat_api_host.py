"""Production preheat HTTP handlers/serializer and reset namespace behavior."""
import ast,os,re,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def function(source,marker):
 start=source.index(marker);pos=source.index('{',start);depth=1;end=pos+1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
fixture=ast.parse((ROOT/'tests/test_preheat_p4_host.py').read_text())
code=next(ast.literal_eval(n.value) for n in fixture.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CODE' for t in n.targets))
code=code[:code.index('int main(){\n assert(preheatSettingsQuiesceForMaintenance());')].replace('//ACTUAL_CAN_SERVICE_ORDER','')
code+=r'''
class String:public std::string {
public:
 using std::string::string;using std::string::operator+=;
 String(const std::string&s):std::string(s){}
 String& operator+=(unsigned long n){append(std::to_string(n));return *this;}
 String& operator+=(long n){append(std::to_string(n));return *this;}
 char charAt(size_t i)const{return at(i);}
};
#include "json_writer_arduino.h"
#include "text_format_pure.h"
struct Server{
 std::map<std::string,String>args;int status=0;String body;
 bool hasArg(const char*k){return args.count(k);}
 String arg(const char*k){return args[k];}
 void send(int c,const char*,const String&s){status=c;body=s;}
}server;
static String v3FeaturePolicyJson(){return "{}";}
static String lab3f8RawHex(const uint8_t*d,uint8_t dlc){String s;for(unsigned i=0;i<dlc;++i){char b[4];snprintf(b,sizeof(b),"%02X",d[i]);if(i)s+=' ';s+=b;}return s;}
'''
web=(ROOT/'web_api.h').read_text()
for marker in ['static bool httpBoolArg(', 'static bool httpDecimalTenthsInRange(', 'static String preheatStatsToJson()', 'static void httpPreheatStats()', 'static void httpPreheatSet()', 'static void httpFeaturePreheat()']:
 code+='\n'+function(web,marker)+'\n'
code+=r'''
int main(){
 preheatMenuLoad();
 server.args={{"targetC","35.5"},{"enabled","1"}};httpPreheatSet();assert(server.status==200&&preheatEnabled&&preheatTargetCx10==355);
 assert(server.body.find("\"targetC\":35.5")!=std::string::npos);
 for(const char*v:{"19.9","50.1","35.55","35.","garbage","1e2",""," 35"}){
  server.args={{"targetC",v},{"enabled","0"}};httpPreheatSet();assert(server.status==400&&preheatEnabled&&preheatTargetCx10==355);
 }
 server.args.clear();httpPreheatSet();assert(server.status==400);
 server.args={{"enabled","garbage"}};httpPreheatSet();assert(server.status==400&&preheatEnabled);
 for(const char*v:{"20","20.0","20.1","49.9","50.0"}){server.args={{"targetC",v}};httpPreheatSet();assert(server.status==200);}
 nvsWrite=false;server.args={{"enabled","0"}};httpPreheatSet();assert(server.status==500&&preheatEnabled);nvsWrite=true;
 server.args={{"enabled","1"}};httpFeaturePreheat();assert(server.status==200&&preheatMenuEnabled&&preheatEnabled);
 server.args={{"enabled","0"}};httpFeaturePreheat();assert(server.status==200&&!preheatMenuEnabled&&preheatEnabled);
 activeVehicleProfile=0;server.args={{"enabled","1"}};httpPreheatSet();assert(server.status==409);
 server.args={{"targetC","35.5"}};httpPreheatSet();assert(server.status==409);
 server.args={{"enabled","0"}};httpPreheatSet();assert(server.status==200&&!preheatEnabled);
 activeVehicleProfile=1;activeVehicleTopology=1;
 preheatRuntimeIngestPhysical(0,0x082,8,PREHEAT_REFERENCE_FRAME);
 httpPreheatStats();assert(server.status==200);
 for(const char*k:{"tripId","srcRaw","lastTxRaw","ptPackAvgC","ptAmbientC","statorHeatKw","thPumpBatRpm","thValveMode","thInletsAgeMs","thInvFrontC","thApC","thInfoC","replyBreaker","blockedReason"})assert(server.body.find(std::string("\"")+k+"\":")!=std::string::npos);
 assert(server.body.find("\"tripId\":\"0x082\"")!=std::string::npos);
 puts("PASS: actual preheat APIs validate before mutation, decimal targets, independent menu, NVS failures, unsupported fail-closed, full Thermal/source JSON");
}
#endif
'''
def run(code):
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'api.cpp';out=Path(td)/'api';p.write_text(code)
  subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-include',str(ROOT/'can_error_diag_macros.h'),'-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-I'+str(ROOT),str(p),'-o',str(out)],check=True)
  subprocess.run([str(out)],check=True)
run(code)
reset=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#include "nvs_keep_ble_reset_pure.h"
static std::vector<std::string>cleared;
static bool succeed=true;
struct Preferences{std::string ns;bool begin(const char*n,bool){ns=n;return true;}bool clear(){cleared.push_back(ns);return succeed;}void end(){}};
'''
reset+=function(web,'static bool resetFirmwareSettingsPreserveProfileAndBle()')+'\n'+function(web,'static bool resetNvsKeepBleClearApplicationNamespaces()')
reset+=r'''
int main(){
 assert(resetFirmwareSettingsPreserveProfileAndBle());bool preheat=false;
 for(const auto&n:cleared){assert(n!="v3profile"&&n!="wifiap"&&n!="s3xy"&&n!="s3xyreg"&&n!="p4gpio");if(n=="preheat")preheat=true;}assert(preheat);
 cleared.clear();assert(resetNvsKeepBleClearApplicationNamespaces());assert(cleared.size()==NVS_KEEP_BLE_APPLICATION_NAMESPACE_COUNT_PURE);
 preheat=false;for(const auto&n:cleared){assert(n!="s3xy"&&n!="s3xyreg"&&n!="p4gpio");if(n=="preheat")preheat=true;}assert(preheat);
 succeed=false;assert(!resetNvsKeepBleClearApplicationNamespaces());
 auto state=nvsKeepBleResetStartPure(true);for(unsigned i=0;i<NVS_KEEP_BLE_APPLICATION_NAMESPACE_COUNT_PURE-1;++i)nvsKeepBleResetClearOnePure(state,true);
 nvsKeepBleResetWriteBootstrapPure(state,true);assert(!state.bootstrapWritten);nvsKeepBleResetClearOnePure(state,true);nvsKeepBleResetWriteBootstrapPure(state,true);nvsKeepBleResetClearGuardPure(state,true);assert(nvsKeepBleResetCompletePure(state));
 puts("PASS: actual reset allowlists clear preheat independently, preserve BLE, enforce 17-namespace failure model");
}
'''
run(reset)
# Exercise the original S3XY enum/parser/profile gate, callback queue and owner
# dispatch block, while reusing the real preheat runtime/persistence fixture.
ble=(ROOT/'s3xy_ble.h').read_text()
s3xy=code[:code.index('int main(){\n preheatMenuLoad();')]
s3xy+=r'''
#define S3XY_DIAGNOSTICS_ENABLED 0
static uint8_t activeTurnSignalVariant=1;
bool activeProfilePedalMapSupported(){return true;}
bool activeProfileAdvancedEapSupported(){return true;}
void s3xyLogPush(int,const char*,const void*,int,int,int){}
void handleS3xySingleAction(){}void requestPedalMapToggleFromButton(){}void requestPedalMapPerformanceFromButton(){}
void toggleTlsscEnabledFromButton(){}void toggleAutoBlinkerEnabledFromButton(){}
bool requestTurnSignalPulseFromButton(int){return true;}
constexpr uint8_t RESEARCH_CAPTURE_LABEL_NONE=0,RESEARCH_CAPTURE_LABEL_A=1,RESEARCH_CAPTURE_LABEL_B=2,RESEARCH_CAPTURE_LABEL_C=3,RESEARCH_CAPTURE_LABEL_D=4;
void researchCaptureReset(){}bool researchCaptureRequest(int){return true;}
'''
s3xy+=function(ble,'enum S3xyAction :')+';\n'
s3xy+=ble[ble.index('static volatile uint32_t s3xyActionPending ='):ble.index('static volatile bool s3xyAutoEnabled =')]
for marker in ['static const char *s3xyActionCode(', 'static const char *s3xyActionLabel(', 'static bool s3xyActionSupportedForCurrentProfile(', 'static bool s3xyActionParseKnown(', 'static void s3xyRunMappedAction(']:
 s3xy+='\n'+function(ble,marker)+'\n'
begin=ble.index('    bool runAction = false, runAccel = false,');end=ble.index('    static uint32_t lastRssiMs =',begin)
s3xy+='\nvoid ownerDispatch(){\n'+ble[begin:end]+'}\n'
s3xy+=r'''
int main(){
 preheatMenuLoad();
 static_assert(S3XY_ACTION_BATTERY_PREHEAT==13,"stored action ID remains original");
 uint8_t action=0;assert(s3xyActionParseKnown("battery_preheat",action)&&action==13);
 assert(s3xyActionParseKnown("Battery Preheating",action)&&action==13);
 assert(std::string(s3xyActionCode(13))=="battery_preheat"&&std::string(s3xyActionLabel(13))=="Battery Preheating");
 preheatEnabled=false;preheatMenuEnabled=false;activeVehicleProfile=1;activeVehicleTopology=1;
 s3xyRunMappedAction(0,13,"single");assert(s3xyPreheatActionPending==1&&!preheatEnabled);
 ownerDispatch();assert(s3xyPreheatActionPending==0&&preheatEnabled&&!preheatMenuEnabled&&nvs["enabled"]==1);
 ownerDispatch();assert(preheatEnabled);
 s3xyRunMappedAction(0,13,"single");ownerDispatch();assert(!preheatEnabled&&nvs["enabled"]==0);
 s3xyRunMappedAction(0,13,"single");s3xyClearPendingActionsLocked(S3XY_PENDING_CAN_RECOVERY);ownerDispatch();assert(!preheatEnabled);
 maintenance=true;s3xyRunMappedAction(0,13,"single");assert(s3xyPreheatActionPending==0);
 s3xyPreheatActionPending=1;nvs.clear();ownerDispatch();assert(!preheatEnabled&&nvs.empty());maintenance=false;
 activeVehicleProfile=0;s3xyRunMappedAction(0,13,"single");assert(s3xyPreheatActionPending==0);
 puts("PASS: actual S3XY action 13 parser/profile gate, deferred owner toggle, durable independent engine state and cancellation reset");
}
#endif
'''
run(s3xy)

# Integration call sites complement executable runtime/API checks: a complete
# helper without a startup, RX, owner or HTTP binding must not silently ship.
ino=(ROOT/(ROOT.name+'.ino')).read_text()
runtime=(ROOT/'can_runtime.h').read_text()
assert ino.index('#include "preheat_runtime.h"')<ino.index('#include "web_api.h"')<ino.index('#include "can_runtime.h"')
assert '  preheatMenuLoad();' in ino
for route,method,handler in [('features/preheat','HTTP_POST','httpFeaturePreheat'),('preheat/stats','HTTP_GET','httpPreheatStats'),('preheat/set','HTTP_POST','httpPreheatSet')]:
 assert f'server.on("/api/{route}", {method}, {handler});' in web
assert runtime.count('preheatRuntimeIngestPhysical(')==3
assert '    preheatRuntimeTick();' in runtime
assert '  preheatRuntimeResetUnderTxBarrier();' in runtime
maintenance=function(runtime,'static bool prepareCanForMaintenance()')
assert maintenance.index('__atomic_store_n(&canMaintenanceRequested')<maintenance.index('preheatSettingsQuiesceForMaintenance()')<maintenance.index('canMaintenanceStopped')
assert '    preheatSettingsService();' in web
print('PASS: production startup/include order, three physical RX stages, CAN owner/reset and complete HTTP route binding')
