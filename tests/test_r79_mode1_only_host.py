"""Fixed Mode1 dispatch ignores a retired mode selection, including stored value 2."""
from pathlib import Path
import os, subprocess, tempfile
ROOT = Path(__file__).resolve().parents[1]
s = (ROOT / 'vehicle_logic.h').read_text()
a = s.index('static bool r79ProcessStockFrame(const twai_message_t &src, uint8_t mux,\n                                 uint32_t nowMs) {')
function = s[a:s.index('\n}', a)+2]
prelude = r'''
#include <cassert>
#include <cstdint>
#include "driver/twai.h"
#include "r79_fixed_policy_pure.h"
#include "r79_dms_composition_pure.h"
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
static int r79LabMux=0;
static uint8_t r79TransportMode=2;
static unsigned fixedObservations=0,fixedEchoes=0,retiredCalls=0;
static uint32_t r79DmsOnlyBlockedByR79=0;
void r79FixedObserveStock(uint8_t,uint32_t){++fixedObservations;}
bool r79FixedFastEcho(const twai_message_t&){++fixedEchoes;return true;}
void r79Mode2ObserveStock(uint8_t,uint32_t){++retiredCalls;}
bool r79Mode2FastEcho(const twai_message_t&){++retiredCalls;return true;}
bool r79DmsWorkPendingSnapshot(){return false;}
bool r79DmsControlActive(){return false;}
bool r79DmsOnlyTransmit(const twai_message_t&){return false;}
'''
main = r'''
int main(){
 twai_message_t f{};
 for(unsigned stored=0;stored<256;++stored){
  r79TransportMode=stored;
  const auto before=fixedEchoes;
  assert(r79ProcessStockFrame(f,1,1000));
  assert(fixedEchoes==before+1 && "retired mode selection must always use Mode1");
  r79ProcessStockFrame(f,2,1001);
 }
 assert(retiredCalls==0 && fixedObservations==512);
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'fixture.cpp'; out=Path(td)/'fixture'; p.write_text(prelude+function+main)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I'+str(ROOT/'tests/r79_timing_fakes'),'-I'+str(ROOT),str(p),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
print('PASS actual Mode1 dispatch for all retired mode byte values')

# Compile the actual load/save and HTTP update functions against deterministic NVS.
def block(text, signature):
 a=text.index(signature);return text[a:text.index('\n}',a)+2]
web=(ROOT/'web_api.h').read_text()
config=s[s.index('struct R79CfgSnapshot {'):s.index('static bool r79CfgSave()')]
fixture=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <map>
#include "r79_fixed_policy_pure.h"
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
static int stateMux=0,r79LabMux=0,r79ApGateSession=0;
static R79ApGateConfigPure r79ApGateConfig{};
static uint8_t r79Bit18Policy=0,r79Mode1TxWaitMode=1,r79RetryIndex=0,r79RetryOriginKind=0;
static uint16_t r79Mode1DelayMs=150;
[[maybe_unused]] static bool r79RetryApOnly=false;
[[maybe_unused]] static uint32_t r79RetryApGeneration=0;
static bool r79Hw3Enabled=false,r79Mode1ReinjectEnabled=true,r79RetryPending=false;
static bool r79CfgReadOk=true,featureConfigNvsReadOk=true;
static uint32_t r79RetryDueMs=0,r79RetryGeneration=0,r79Mode1PostMux2Generation=1;
static constexpr uint8_t R79LAB_TX_NONE=0,R79LAB_TX_PERIODIC=2;
static R79FixedQuietStatePure r79FixedQuietState{};
static bool blobFound=true,readOk=true,saveOk=true;
static unsigned writes=0,holds=0,hw3Calls=0;
static uint8_t blob[10]={1,1,2,0,0,44,1,1,255,255},written[10]{};
static std::map<std::string,unsigned> legacy;
struct CheckedPreferences {
 bool begin(const char*,bool){return readOk;}
 unsigned getUInt(const char*k,unsigned d){return get(k,d);}
 bool getBool(const char*k,bool d){return get(k,d)!=0;}
 uint8_t getUChar(const char*k,uint8_t d){return get(k,d);}
 uint16_t getUShort(const char*k,uint16_t d){return get(k,d);}
 unsigned get(const char*k,unsigned d){assert(std::string(k)!="mode"&&std::string(k)!="m2re"&&std::string(k)!="m2delay");return legacy.count(k)?legacy[k]:d;}
 bool ok(){return readOk;}void end(){}
};
bool nvsCheckedReadBlob(const char*,const char*,uint8_t*out,size_t n,bool&found){assert(n==10);found=blobFound;std::memcpy(out,blob,n);return readOk;}
bool nvsCheckedWriteBlob(const char*,const char*,const uint8_t*in,size_t n){assert(n==10);++writes;if(saveOk)std::memcpy(written,in,n);return saveOk;}
uint16_t featureNvsU16(const uint8_t*d){return d[0]|(uint16_t(d[1])<<8);}
class String:public std::string {public:using std::string::string;String(const std::string&s):std::string(s){} long toInt()const{return std::stol(*this);}};
struct Server {std::map<std::string,String> args;int status=0;String response;
 bool hasArg(const char*k){return args.count(k)!=0;}String arg(const char*k){return args[k];}
 void send(int s,const char*,const String&v){status=s;response=v;}
}server;
enum class HttpBoolPolicy{LegacyOneTrue};
bool httpBoolValue(const String&s,HttpBoolPolicy){return s=="1"||s=="true";}
bool activeProfileR79Hw3Supported(){return true;}
bool r79Hw3Apply(bool){++hw3Calls;return true;}
String r79StatsToJson(){return "fixed-mode1";}
void setCanTxAdministrativeHold(bool on){holds+=on?1:0;}
void canTxCancellationGenerationAdvance(uint32_t*g){++*g;}
'''
scenarios=r'''
int main(){
 // Existing schema-1 Mode2 installs preserve only Mode1 settings and AP/HW3.
 legacy={{"apctl",(3u<<8)|1u},{"hw3",1}};
 for(unsigned retired=0;retired<256;++retired){
  blob[2]=retired;r79CfgLoad();assert(r79CfgReadOk);
  assert(r79Bit18Policy==1&&r79Mode1TxWaitMode==0&&!r79Mode1ReinjectEnabled&&r79Mode1DelayMs==300);
  assert(r79Hw3Enabled&&r79ApGateConfig.enabled&&r79ApGateConfig.delaySeconds==3);
 }
 // Legacy scalar mode keys are ignored without losing existing Mode1 fields.
 blobFound=false;legacy={{"mode",2},{"m2re",1},{"m2delay",900},{"bit18",1},{"m1wait",0},{"m1re",1},{"m1delay",123}};
 r79CfgLoad();assert(r79Mode1TxWaitMode==0&&r79Mode1ReinjectEnabled&&r79Mode1DelayMs==123&&r79Bit18Policy==1);
 auto snapshot=r79CfgRuntimeSnapshot();assert(r79CfgPersistCandidate(snapshot));
 assert(written[2]==1&&written[7]==0&&written[8]==0&&written[9]==0&&written[5]==123);
 r79CfgRuntimeRestore(snapshot);
 // Every retired selector fails before saving or mutating even on a mixed request.
 for(const char* key:{"mode","mode2Reinject","mode2DelayMs"}){
  for(const char* value:{"1","2","0","garbage"}){
   const auto before=writes;server.args={{key,value},{"mode1DelayMs","250"},{"hw3Enabled","1"}};
   httpR79Update();assert(server.status==400&&writes==before&&r79Mode1DelayMs==123&&hw3Calls==0);
  }
 }
 server.args={{"mode1TxWaitMode","1"},{"mode1Reinject","1"},{"mode1DelayMs","340"},{"bit18Mode","0"}};
 httpR79Update();assert(server.status==200&&r79Mode1TxWaitMode==1&&r79Mode1DelayMs==340&&r79Bit18Policy==0);
 assert(written[2]==1&&written[5]==84&&written[6]==1);
 for(const char* delay:{"-1","341","1.5","","x"}){
  auto before=writes;server.args={{"mode1DelayMs",delay}};httpR79Update();assert(server.status==400&&writes==before&&r79Mode1DelayMs==340);
 }
 saveOk=false;server.args={{"mode1DelayMs","50"}};httpR79Update();assert(server.status==500&&r79Mode1DelayMs==340);saveOk=true;
 // Disabling periodic reinjection cancels its retry and generation, preserving immediate retry.
 r79RetryPending=true;r79RetryOriginKind=R79LAB_TX_PERIODIC;auto gen=r79Mode1PostMux2Generation;
 server.args={{"mode1Reinject","0"}};httpR79Update();assert(server.status==200&&!r79RetryPending&&r79Mode1PostMux2Generation==gen+1);
 server.args={{"mode1Reinject","1"}};httpR79Update();r79RetryPending=true;r79RetryOriginKind=1;
 server.args={{"mode1Reinject","0"}};httpR79Update();assert(r79RetryPending);
 // Invalid persisted Mode1 input still uses original sanitizers/defaults.
 blobFound=true;blob[1]=255;blob[3]=255;blob[5]=255;blob[6]=255;r79CfgLoad();
 assert(r79Bit18Policy==R79_BIT18_DEFAULT_PURE&&r79Mode1TxWaitMode==R79_MODE1_WAIT_DEFAULT_PURE&&r79Mode1DelayMs==R79_FIXED_QUIET_DELAY_MS_PURE);
 readOk=false;r79CfgLoad();assert(!r79CfgReadOk&&!r79CfgPersistCandidate(snapshot));
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'config.cpp';out=Path(td)/'config'
 p.write_text(fixture+block(s,'static void r79CfgLoad() {')+config+block(web,'static void httpR79Update() {')+scenarios)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I'+str(ROOT),str(p),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
# Runtime and editable UI must not retain an executable Mode2 transport.
for file in ('vehicle_logic.h','r79_fixed_policy_pure.h','can_runtime.h','dashboard_source.html'):
 text=(ROOT/file).read_text()
 for retired in ('r79Mode2','R79_MODE_2_PURE','r79TransportMode'):
  assert retired not in text,(file,retired)
assert 'id="r79Mode"' not in (ROOT/'dashboard_source.html').read_text()
assert 'jw.u32("mode", 1u)' in web
print('PASS actual NVS legacy/blob migration, retired API rejection, preserved Mode1 settings/retry cancellation and save-failure isolation')
