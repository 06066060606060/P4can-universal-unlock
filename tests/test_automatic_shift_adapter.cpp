#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <strings.h>
#include <string>
#include <vector>
#include <map>
#include <algorithm>
#include <initializer_list>
using esp_err_t=int;
constexpr int ESP_OK=0,pdTRUE=1,TWAI_STATE_RUNNING=1,P4_CAN_COUNT=3,P4_BODY=0,VEHICLE_MODEL_Y_JUNIPER=2,VEHICLE_MODEL_Y_LEGACY=3;
#define pdMS_TO_TICKS(x) (x)
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
std::map<int*,bool> locks;
void portENTER_CRITICAL(int *p){assert(!locks[p]);locks[p]=true;}void portEXIT_CRITICAL(int*p){assert(locks[p]);locks[p]=false;}
int canTxBarrierMutex=1;bool barrierHeld=false;
int xSemaphoreTake(int,uint32_t){if(barrierHeld)return 0;barrierHeld=true;return 1;}void xSemaphoreGive(int){assert(barrierHeld);barrierHeld=false;}
uint32_t clockMs=0;uint32_t millis(){return clockMs;}void vTaskDelay(int){}
bool vehicleProfileSetupMode=false,vehicleProfileNvsError=false,canSubsystemBusy=false,canTxAdministrativeHold=false,passive=false,routeSupported=true;
int activeVehicleProfile=3;bool p4CanOnline[3]={true,true,true};uint8_t p4CanState[3]={1,1,1};
bool canUsbTxHeld(){return passive;}bool canUsbPassive(){return passive;}bool activeCanAIsBody(){return routeSupported;}bool activeCanBIsChassis(){return routeSupported;}
struct CanFrame{uint8_t bus=255,can_dlc=0,data[8]={};uint32_t can_id=0;};CanFrame last;int sent=0,sendResult=0;
int p4CanSendFrame(const CanFrame *f){assert(barrierHeld);assert(f->bus==0);last=*f;sent++;return sendResult;}
std::vector<uint8_t> blob;bool writeOk=true;
struct Preferences{bool begin(const char*,bool){return true;}bool isKey(const char*){return !blob.empty();}size_t getBytesLength(const char*){return blob.size();}size_t getBytes(const char*,void *out,size_t n){n=std::min(n,blob.size());memcpy(out,blob.data(),n);return n;}size_t putBytes(const char*,const void *in,size_t n){if(!writeOk)return 0;blob.assign((const uint8_t*)in,(const uint8_t*)in+n);return n;}void end(){}};
class String:public std::string{public:using std::string::string;using std::string::operator+=;String(const std::string&s):std::string(s){}String &operator+=(unsigned long n){append(std::to_string(n));return *this;}String &operator+=(long n){append(std::to_string(n));return *this;}void toUpperCase(){for(char &c:*this)c=::toupper((unsigned char)c);}};
struct Server{std::map<std::string,String> args;int code=0;String body;bool hasArg(const char*k){return args.count(k);}String arg(const char*k){return args[k];}void sendHeader(const char*,const char*){}void send(int c,const char*,const String &b){code=c;body=b;}}server;
#include "automatic_shift/gear_shift_runtime.h"
#include "automatic_shift/gear_shift_web.h"
using namespace gearhintv12live;
struct AutoFixture {
  Observer o;
  uint32_t now=0,tick=0;
  int gear=1,brake=0xCF,buckle=2,occupancy=2,accel=0,speed=500,wheel=0,angleValidity=1,angleStatus=0;
  int left=0x22,right=0x22,trunk=2,aux=0,skip=-1;
  uint16_t front[6]={200,500,500,500,500,500},rear[6]={50,500,500,500,500,500};
  void emit(uint8_t bus,uint16_t id,uint8_t *d,uint8_t dlc=8,bool ext=false,bool remote=false) {
    const int s=signalIndex(id),cp=checksumPosition(s);
    if(cp>=0&&dlc==8) d[cp]=checksum(id,d,cp);
    o.observe(bus,id,dlc,ext,remote,d,now);clockMs=now;gearHintDisplayObserveRaw(bus,id,dlc,ext,remote,d);
  }
  void frame(int s) {
    if(s==skip) return;
    uint8_t d[8]={};const uint8_t bus=s<=Rear?1:(s==Speed||s==Steering?aux:0);
    if(s==Gear){const uint8_t bytes[]={0,0x32,0x55,0x72,0x95};d[2]=gear>=0&&gear<=4?bytes[gear]:uint8_t(gear<<5);d[4]=accel;}
    if(s==Brake)d[3]=brake;
    if(s==Speed){d[1]=(speed&15)<<4;d[2]=speed>>4;}
    if(s==Steering){const unsigned raw=wheel+8192;d[2]=raw;d[3]=((raw>>8)&63)|(angleValidity<<6);d[1]=angleStatus<<6;}
    if(s==LeftDoors)d[0]=left;
    if(s==RightDoors){d[0]=right;d[7]=trunk;}
    if(s==Buckle)d[6]=buckle|(occupancy<<2);
    if(s==Front||s==Rear){
      uint64_t word=uint64_t(tick&3)<<54;const auto *v=s==Front?front:rear;
      for(int i=0;i<6;++i)word|=uint64_t(v[i])<<(9*i);
      for(int i=0;i<7;++i)d[i]=word>>(8*i);
    } else if(counterValue(s,d)>=0)d[1]=(d[1]&0xf0)|(tick&15);
    emit(bus,kSignalIds[s],d);
  }
  void step(){for(int s=0;s<SignalCount;++s)frame(s);++tick;now+=40;}
  void run(unsigned count=50){for(unsigned i=0;i<count;++i)step();}
  Result result(bool confirm=false,uint8_t source=0){Config c;c.requireSteering=confirm;return o.result(source,now,true,c);}
};

void tick(AutoFixture &f){f.step();clockMs=f.now;uint8_t t[3]={gearshift::v12Checksum(0,f.tick&15),uint8_t(f.tick&15),1};gearHintDisplayObserveRaw(0,0x229,3,false,false,t);gearShiftServiceTick();}
int main(){
 gearShiftConfigLoad();assert(!gearShiftConfig.enabled);gearshift::Config cfg;cfg.enabled=true;cfg.protocol=gearshift::Protocol::V12;cfg.speedBus=0;assert(gearShiftConfigSave(cfg));
 gearShiftConfig={};gearShiftConfigLoad();assert(gearShiftConfig.enabled&&gearShiftConfig.speedBus==0);
 AutoFixture f;f.brake=0x2f;for(int i=0;i<35;i++)tick(f);
 assert(sent==0);f.brake=0xcf;tick(f);assert(sent==1&&last.can_id==0x229&&last.can_dlc==3);assert((last.data[1]>>4)==4);
 for(int i=0;i<10;i++)tick(f);assert(sent==1);
 cfg.enabled=false;assert(gearShiftConfigSave(cfg));cfg.enabled=true;assert(gearShiftConfigSave(cfg));for(int i=0;i<10;i++)tick(f);assert(sent==1);
 barrierHeld=true;gearShiftInvalidateInputs();barrierHeld=false;for(int i=0;i<10;i++)tick(f);assert(sent==1);
 passive=true;f.brake=0x2f;for(int i=0;i<10;i++)tick(f);f.brake=0xcf;tick(f);assert(sent==1);passive=false;
 writeOk=false;cfg.enabled=false;assert(!gearShiftConfigSave(cfg)&&gearShiftConfig.enabled);writeOk=true;
 server.args={{"enabled","0"}};httpGearShiftConfig();assert(server.code==200&&!gearShiftConfig.enabled);
 server.args={{"maxKph","9"}};httpGearShiftConfig();assert(server.code==400);
 server.args.clear();httpGearShiftStatus();assert(server.code==200&&server.body.find("executionEnabled")!=std::string::npos);
 routeSupported=false;server.args={{"enabled","1"}};httpGearShiftConfig();assert(server.code==409);
 assert(!barrierHeld);puts("PASS: adapted runtime/web compile, actual V12 request, brake hold/disable/recovery interlocks, passive mode, NVS and HTTP validation");
}
