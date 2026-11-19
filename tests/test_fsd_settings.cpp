#include <cassert>
#include <cstdint>
#include <cstring>
#include <initializer_list>
using portMUX_TYPE=int;using esp_err_t=int;
constexpr int portMUX_INITIALIZER_UNLOCKED=0,pdTRUE=1,ESP_OK=0,ESP_ERR_INVALID_STATE=-1,CAN_TX_FRESH_BOTH=3;
constexpr uint8_t P4_CHASSIS=1,P4_BODY=0;
int canTxBarrierMutex=1;bool held=false,canTxAdministrativeHold=false,twaiReady=true,passive=false,ready=true,admission=true,fresh=true;
uint32_t now=100;struct{uint32_t epoch=3;}canTxBarrierState;
void portENTER_CRITICAL(int*){}void portEXIT_CRITICAL(int*){}
int xSemaphoreTake(int,int){if(held)return 0;held=true;return 1;}void xSemaphoreGive(int){assert(held);held=false;}
uint32_t millis(){return now;}bool canUsbPassive(){return passive;}bool p4CanAllRunning(){return ready;}
uint8_t route=1;uint8_t p4CanBusB(){return route;}bool twaiNonSummonAdmissionOpen(){return admission;}
template<class T>bool canTxBarrierAllowsMaskedPure(T,uint32_t e,int){return e==3&&fresh;}
struct twai_message_t{uint32_t identifier=0x3fd,flags=0;uint8_t data_length_code=8,data[8]={};};
struct CanFrame{uint32_t can_id=0x3fd;uint8_t can_dlc=8,bus=1,data[8]={};};
uint8_t last[8];int sent=0;
int p4CanSendB(const twai_message_t*f,int){assert(held);memcpy(last,f->data,8);sent++;return 0;}
int p4CanSendFrame(const CanFrame*f){assert(held&&(f->bus==0||f->bus==1));memcpy(last,f->data,8);sent++;return 0;}
void canBTraceRecordTx(const twai_message_t*,int){}
uint32_t savedConfig=0;bool writeOk=true;
struct Preferences{bool begin(const char*,bool){return true;}uint32_t getUInt(const char*,uint32_t){return savedConfig;}size_t putUInt(const char*,uint32_t value){if(!writeOk)return 0;savedConfig=value;return 4;}void end(){}};
int stateMux=0;bool apKnown=true,dasAutopilotStateValid=true;uint8_t dasAutopilotState4=0;
bool r79ApDasFreshLocked(uint32_t){return apKnown;}
bool dasStateApActivePure(bool valid,uint8_t state){return valid&&state>=3&&state<=6;}
#define pdMS_TO_TICKS(x) (x)
#include "fsd_settings.h"
int main(){
 fsdSettingsEnabled=false;fsdSettingsValues=137;fsdSettingsSuspendAp=true;
 assert(toggleFsdSettingsFromButton()&&fsdSettingsEnabled);assert(toggleFsdSettingsFromButton()&&!fsdSettingsEnabled);
 assert(fsdSettingsValues==137&&fsdSettingsSuspendAp);
 writeOk=false;assert(!toggleFsdSettingsFromButton()&&!fsdSettingsEnabled);writeOk=true;

 for(int suspend=0;suspend<2;suspend++)for(unsigned value=0;value<256;value++)for(int enabled=0;enabled<2;enabled++){
  assert(fsdSettingsSave(enabled,value,suspend));fsdSettingsEnabled=false;fsdSettingsValues=0;fsdSettingsLoad();
  assert(fsdSettingsEnabled==bool(enabled)&&fsdSettingsValues==(value&2)&&fsdSettingsSuspendAp==bool(suspend));
 }
 // Legacy persistence: bit6 remains master, bit7 remains AP suspension.
 for(unsigned legacy=0;legacy<256;legacy++){
  savedConfig=0x100|legacy;fsdSettingsLoad();
  assert(fsdSettingsValues==(legacy&2));assert(fsdSettingsEnabled==bool(legacy&64));assert(fsdSettingsSuspendAp==bool(legacy&128));
 }
 writeOk=false;assert(!fsdSettingsSave(false,0));writeOk=true;
 fsdSettingsEnabled=false;fsdSettingsSuspendAp=false;

 twai_message_t stock;stock.data[7]=0x80;
 fsdSettingsTransmit(stock,stock,false,3,100);assert(!sent);
 fsdSettingsEnabled=true;
 for(int mux: {0,2})for(int values=0;values<256;values++)for(int byte=0;byte<256;byte++){
  memset(stock.data,byte,8);stock.data[0]=(byte&0xf8)|mux;stock.data[7]|=0x80;fsdSettingsValues=values;
  fsdSettingsObserve(1,0x3fd,8,stock.data,3,100);
  int before=sent;fsdSettingsTransmit(stock,stock,false,3,100);assert(sent==before+(mux==0?1:0));if(mux!=0)continue;
  for(int bit=0;bit<64;bit++){int expected=(stock.data[bit/8]>>(bit%8))&1;
   if(bit==46)expected=(values>>1)&1;
   assert(((last[bit/8]>>(bit%8))&1)==expected);
  }
 }
 stock.data[0]=0;stock.data[7]=0x80;twai_message_t proposed=stock;proposed.data[4]|=0xc0;
 fsdSettingsTransmit(stock,proposed,true,3,100);assert(last[4]==proposed.data[4]);
 fresh=false;fsdSettingsTransmit(stock,proposed,true,3,100);assert(last[4]==stock.data[4]);fresh=true;
 auto blocked=[&](){int before=sent;fsdSettingsTransmit(stock,stock,false,3,100);assert(sent==before);};
 passive=true;blocked();passive=false;canTxAdministrativeHold=true;blocked();canTxAdministrativeHold=false;
 ready=false;blocked();ready=true;admission=false;blocked();admission=true;
 now=201;blocked();now=100;canTxBarrierState.epoch=4;blocked();canTxBarrierState.epoch=3;
 fsdSettingsSuspendAp=true;
 for(uint8_t ap=3;ap<=6;ap++){dasAutopilotState4=ap;for(uint8_t mux: {0,2}){stock.data[0]=mux;blocked();}}
 dasAutopilotState4=0;apKnown=false;stock.data[0]=0;blocked();
 apKnown=true;int prior=sent;fsdSettingsTransmit(stock,stock,false,3,100);assert(sent==prior+1);
 fsdSettingsSuspendAp=false;
 stock.data[0]=1;blocked();stock.data[0]=3;blocked();stock.data[0]=0;
 route=0;blocked();CanFrame frame;frame.data[7]=0x80;int before=sent;fsdSettingsExtra(frame,3,100);assert(sent==before+1);
 // Legacy BODY/BOTH settings must never enable physical BODY injection.
 for(uint8_t legacy=1;legacy<=3;legacy++){
  savedConfig=0x100u|0x40u|((uint32_t)legacy<<11);fsdSettingsLoad();
  fsdSettingsSuspendAp=false;route=0;stock.data[0]=0;stock.data[7]=0x80;int n=sent;
  fsdSettingsTransmit(stock,stock,false,3,100);assert(sent==n);
  frame.bus=0;fsdSettingsExtra(frame,3,100);assert(sent==n);
  frame.bus=1;fsdSettingsExtra(frame,3,100);assert(sent==n+1);
 }
 fsdSettingsEnabled=false;before=sent;fsdSettingsExtra(frame,3,100);assert(sent==before);
}
