#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <map>
using portMUX_TYPE=int;using esp_err_t=int;
constexpr int portMUX_INITIALIZER_UNLOCKED=0,pdTRUE=1,ESP_OK=0;
constexpr uint8_t P4_BODY=0,P4_CHASSIS=1,STALK_IDLE=0,TURN_SIGNAL_STALK=1;
#define pdMS_TO_TICKS(x) (x)
int canTxBarrierMutex=1,stateMux=0,nagCtxMux=0,blinkAMux=0;bool held=false,ready=true,passive=false,canTxAdministrativeHold=false,admission=true;
uint32_t now=100;struct{uint32_t epoch=3;}canTxBarrierState;
bool gateAPActive=true,dasAutopilotStateValid=true;uint8_t dasAutopilotState4=3,gear118Raw=4,activeTurn=0,activeTurnSignalVariant=1;
uint32_t lastDASStatusMillis=100,gear118Ms=100;
struct{bool vehicleSpeedValid=true;uint32_t lastVehicleSpeedMs=100;uint16_t vehicleSpeedRaw=1000;}nagCtx;
struct{uint8_t pendingDir=0;}blinkerTxRequestState;
void portENTER_CRITICAL(int*){}void portEXIT_CRITICAL(int*){}
int xSemaphoreTake(int,int){if(held)return 0;held=true;return 1;}void xSemaphoreGive(int){assert(held);held=false;}
uint32_t millis(){return now;}bool canUsbPassive(){return passive;}bool p4CanAllRunning(){return ready;}
uint8_t p4CanBusB(){return 1;}bool twaiNonSummonAdmissionOpen(){return admission;}
void vTaskDelay(int){}
struct CanFrame{uint32_t can_id=0;uint8_t can_dlc=0,bus=0,data[8]={};};
std::vector<CanFrame> sent;bool txSuccess=true;
int p4CanSendFrame(const CanFrame*f){assert(held);sent.push_back(*f);return txSuccess?0:-1;}
uint32_t savedConfig=0;bool writeOk=true;
struct Preferences{bool begin(const char*,bool){return true;}uint32_t getUInt(const char*,uint32_t){return savedConfig;}size_t putUInt(const char*,uint32_t v){if(!writeOk)return 0;savedConfig=v;return 4;}void end(){}};
#include "runtime_gate_pure.h"
#include "lighting/lighting_runtime.h"
struct String:std::string{using std::string::string;String(std::string s):std::string(s){}int toInt()const{return std::stoi(*this);}};
struct{std::map<std::string,String> args;int status=0;bool hasArg(const char*k){return args.count(k);}String arg(const char*k){return args[k];}void send(int code,const char*,const String&){status=code;}}server;
struct JsonWriterArduino{JsonWriterArduino(String&){}void boolean(const char*,bool){}void u32(const char*,uint32_t){}void finish(){}};
bool httpBoolArg(const char*k,bool &out){auto v=server.arg(k);if(v!="0"&&v!="1")return false;out=v=="1";return true;}
#include "lighting/lighting_web.h"
void fresh(){lastDASStatusMillis=gear118Ms=nagCtx.lastVehicleSpeedMs=now;}
void stalk(uint8_t push,uint8_t turn=0,uint8_t bus=0){uint8_t d[4]={0,0xc7,0xb0,0x31};d[1]|=push<<4;d[2]|=turn;d[0]=leftStalkChecksumPure(d,7);lightingObserve(bus,0x249,4,d,3,now);}
void dark(){uint8_t d[8]={};lightingObserve(0,0x3f5,8,d,3,now);}
void body(){uint8_t d[8]={0xf1,0x09,0x20,0xa1,0x42,0xa9,0x35,0};d[7]=teslaAdditiveChecksumPure(0x3e9,d);lightingObserve(0,0x3e9,8,d,3,now);}
void pedal(bool pressed,bool hard){uint8_t d[8]={};d[2]=pressed?2:0;d[3]=hard?81:0;lightingObserve(1,0x39d,5,d,3,now);}
void reset(){lightingState={};sent.clear();now=100;fresh();gateAPActive=true;lightingPermission=false;lightingBrakeMode=0;txSuccess=ready=true;passive=false;activeTurn=0;canTxBarrierState.epoch=3;}
int main(){
 // Permission alone never forces a beam. Body bus only; push toggles inside AP.
 reset();assert(lightingSettingsSave(true,0));body();stalk(0);lightingService();assert(sent.empty());
 stalk(2,0,1);lightingService();assert(!lightingState.run.running&&sent.empty());
 stalk(2);assert(lightingState.run.running);lightingService();assert(sent.size()==1&&sent.back().can_id==0x3e9);
 assert(sent.back().bus==0&&sent.back().data[0]==0xf1&&(sent.back().data[1]&0x18)==0x10&&(sent.back().data[3]&1)==0);
 assert(sent.back().data[7]==teslaAdditiveChecksumPure(0x3e9,sent.back().data));
 // Car returns idle: a continuous-counter four-PUSH train, 10ms apart.
 now=230;fresh();stalk(0);body();dark();lightingService();
 int pushes=0;uint8_t prev=7;
 for(int i=0;i<4;i++){
  if(i){now+=10;fresh();lightingService();}
  const auto &f=sent.back();assert(f.can_id==0x249&&f.bus==0&&f.can_dlc==4);
  assert(((f.data[1]>>4)&3)==2&&(f.data[1]&15)==((prev+1)&15));prev=f.data[1]&15;
  assert(f.data[2]==0xb0&&f.data[3]==0x31&&f.data[0]==leftStalkChecksumPure(f.data,prev));pushes++;
  auto copy=f;lightingObserve(0,0x249,4,copy.data,3,now+1);assert(lightingState.run.running);
 }
 assert(pushes==4);
 // Second driver PUSH after echo guard stops ALL high-beam writes.
 now=1100;fresh();stalk(0);stalk(2);assert(!lightingState.run.running);auto n=sent.size();lightingService();assert(sent.size()==n);
 now+=600;fresh();stalk(0);stalk(2);assert(lightingState.run.running);gateAPActive=false;lightingService();assert(!lightingState.run.running);
 // Stale AP and missing timestamps close the gate.
 gateAPActive=true;lastDASStatusMillis=0;assert(!lightingApSnapshot(now));lastDASStatusMillis=100;now=4000;assert(!lightingApSnapshot(now));
 // Dynamic brake: only D, pedal, >8km/h; modifies no hazard/headlight bits.
 reset();assert(lightingSettingsSave(false,1));body();pedal(true,false);lightingService();assert(sent.size()==1);
 assert(sent.back().data[0]==0xf1&&sent.back().data[1]==0x09&&sent.back().data[3]==0xa1&&(sent.back().data[2]&0x40));
 now+=20;pedal(false,false);lightingService();assert((sent.back().data[2]&0x40)==0);
 n=sent.size();now+=20;nagCtx.vehicleSpeedRaw=600;pedal(true,false);lightingService();assert(sent.size()==n);
 now+=20;pedal(false,false);lightingService();nagCtx.vehicleSpeedRaw=601;pedal(true,false);lightingService();assert(sent.size()==n+1);
 // Invalid/stale brake data cannot hold the dynamic request indefinitely.
 now+=301;fresh();lightingService();assert(!lightingState.dynamic.requested&&(sent.back().data[2]&0x40)==0);
 reset();lightingSettingsSave(false,2);body();pedal(true,false);lightingService();assert(sent.empty());pedal(true,true);lightingService();assert(!sent.empty());
 // No output when passive, held, not ready, or after recovery epoch change.
 n=sent.size();passive=true;now+=20;lightingService();assert(sent.size()==n);passive=false;ready=false;lightingService();assert(sent.size()==n);ready=true;
 canTxBarrierState.epoch++;lightingService();assert(sent.size()==n&&!lightingState.body.valid);
 // Failed enqueue does not consume stalk train or counter; normal blinker wins.
 reset();lightingSettingsSave(true,0);body();stalk(2);now=230;fresh();stalk(0);dark();txSuccess=false;lightingService();assert(lightingState.train.left==4&&lightingState.stalk.counter==7);
 txSuccess=true;activeTurn=6;now+=10;lightingService();assert(sent.back().can_id==0x3e9);activeTurn=0;now+=10;lightingService();assert(sent.back().can_id==0x249);
 // Reject malformed frames and never arm the saved permission on stalkless profiles.
 reset();uint8_t bad[8]={};lightingObserve(0,0x249,3,bad,3,now);lightingObserve(0,0x249,4,bad,3,now);lightingObserve(0,0x3e9,8,bad,3,now);assert(!lightingState.stalk.valid&&!lightingState.body.valid);
 lightingSettingsSave(true,0);activeTurnSignalVariant=2;stalk(2);body();lightingService();assert(!lightingState.run.running&&sent.empty());activeTurnSignalVariant=1;
 // Persistent settings, failed saves and strict API validation.
 assert(lightingSettingsSave(true,2));lightingPermission=false;lightingBrakeMode=0;lightingSettingsLoad();assert(lightingPermission&&lightingBrakeMode==2);
 writeOk=false;assert(!lightingSettingsSave(false,0)&&lightingPermission&&lightingBrakeMode==2);writeOk=true;
 server.args={{"dynamicBrakeMode","junk"}};httpLightingUpdate();assert(server.status==400);
 server.args={{"apForcedHighBeam","0"}};httpLightingUpdate();assert(server.status==200&&!lightingPermission);
 activeTurnSignalVariant=2;server.args={{"apForcedHighBeam","1"}};httpLightingUpdate();assert(server.status==409&&!lightingPermission);
 httpLightingStats();assert(server.status==200);
}
