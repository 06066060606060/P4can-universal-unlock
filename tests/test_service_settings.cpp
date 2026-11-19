#include <cassert>
#include <cstdint>
#include <cstring>
#include <initializer_list>
using portMUX_TYPE=int;using esp_err_t=int;
constexpr int portMUX_INITIALIZER_UNLOCKED=0,pdTRUE=1,ESP_OK=0,ESP_ERR_INVALID_STATE=-1,CAN_TX_FRESH_BOTH=3;
constexpr uint8_t P4_CHASSIS=1,P4_BODY=0;
#define pdMS_TO_TICKS(x) (x)
int canTxBarrierMutex=1;bool held=false,canTxAdministrativeHold=false,twaiReady=true,passive=false,ready=true,admission=true,fresh=true;
uint32_t now=100;struct{uint32_t epoch=3;}canTxBarrierState;
void portENTER_CRITICAL(int*){}void portEXIT_CRITICAL(int*){}
int xSemaphoreTake(int,int){if(held)return 0;held=true;return 1;}void xSemaphoreGive(int){assert(held);held=false;}
uint32_t millis(){return now;}bool canUsbPassive(){return passive;}bool p4CanAllRunning(){return ready;}
uint8_t route=1;uint8_t p4CanBusB(){return route;}bool twaiNonSummonAdmissionOpen(){return admission;}
template<class T>bool canTxBarrierAllowsMaskedPure(T,uint32_t e,int){return e==3&&fresh;}
struct twai_message_t{uint32_t identifier=0x3fd,flags=0;uint8_t data_length_code=8,data[8]={};};
struct CanFrame{uint32_t can_id=0x3fd;uint8_t can_dlc=8,bus=1,data[8]={};};
uint8_t last[8],lastBus=255,lastDlc=0;uint32_t lastId=0;int sent=0;
int p4CanSendB(const twai_message_t*f,int){assert(held);memcpy(last,f->data,8);sent++;return 0;}
int p4CanSendFrame(const CanFrame*f){assert(held);lastBus=f->bus;lastId=f->can_id;lastDlc=f->can_dlc;memcpy(last,f->data,8);sent++;return 0;}
void canBTraceRecordTx(const twai_message_t*,int){}
uint32_t savedConfig=0;bool writeOk=true;
bool savedRestore=false;
struct Preferences{bool getBool(const char*,bool){return savedRestore;}size_t putBool(const char*,bool value){if(!writeOk)return 0;savedRestore=value;return sizeof(bool);}bool begin(const char*,bool){return true;}uint32_t getUInt(const char*,uint32_t){return savedConfig;}size_t putUInt(const char*,uint32_t value){if(!writeOk)return 0;savedConfig=value;return 4;}void end(){}};
int stateMux=0;bool apKnown=true,dasAutopilotStateValid=true;uint8_t dasAutopilotState4=0;
bool r79ApDasFreshLocked(uint32_t){return apKnown;}
bool dasStateApActivePure(bool valid,uint8_t state){return valid&&state>=3&&state<=6;}

uint32_t canTxEpochSnapshot(){return canTxBarrierState.epoch;}
#include "service_settings.h"
int main(){
 assert(serviceSettingsEnter()==0&&sent==1&&lastBus==0&&lastId==0x339&&lastDlc==8);
 for(int i=0;i<8;i++)assert(last[i]==(i==5?0x80:0));
 int n=sent;serviceSettingsLoad();assert(sent==n);
 passive=true;assert(serviceSettingsEnter()!=0&&sent==n);passive=false;
 assert(serviceSettingsSetRestore(true));chinaRestoreEnabled=false;serviceSettingsLoad();assert(chinaRestoreEnabled);
 uint8_t data[8]={};
 for(int byte=0;byte<256;byte++){
  for(int i=0;i<8;i++)data[i]=byte+i;
  chinaRestoreEcho(1,0x331,6,data,3,now);assert(lastBus==1&&lastId==0x331&&lastDlc==6);
  assert(last[0]==((data[0]&0xc0)|0x1b));for(int i=1;i<6;i++)assert(last[i]==data[i]);
 }
 n=sent;chinaRestoreEcho(0,0x331,6,data,3,now);chinaRestoreEcho(1,0x331,8,data,3,now);chinaRestoreEcho(1,0x331,6,data,2,now);assert(sent==n);
 canTxAdministrativeHold=true;chinaRestoreEcho(1,0x331,6,data,3,now);assert(sent==n);canTxAdministrativeHold=false;
 passive=true;chinaRestoreEcho(1,0x331,6,data,3,now);assert(sent==n);passive=false;
 writeOk=false;assert(!serviceSettingsSetRestore(false)&&chinaRestoreEnabled);writeOk=true;
 assert(serviceSettingsSetRestore(false));chinaRestoreEcho(1,0x331,6,data,3,now);assert(sent==n);
}
