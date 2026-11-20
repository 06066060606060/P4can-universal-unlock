#pragma once
#include "lighting_reference_pure.h"
#include "../auto_blinker_pure.h"
#include "../tesla_can_fields_pure.h"

// Only the two dashboard features are instantiated. All output uses physical BODY.
struct LightingTemplate {
  bool valid=false, sent=false;
  uint32_t ms=0, sentMs=0;
  uint8_t data[8]={}, last[8]={}, counter=0;
};
struct LightingRuntime {
  uint32_t epoch=0;
  LightingTemplate stalk, body;
  LightingAp1RunPure run={};
  LightingAp1PushPure train={};
  LightingDynHighPure dynamic={};
  LightingBrakeSignalPure brake[2]={};
  bool brakeSeen[2]={}; uint32_t brakeMs[2]={};
  uint8_t prevPush=0, beam5=0, beamD4=0, beam6=3;
  uint32_t carPushMs=0, beam5Ms=0, beam6Ms=0;
  bool dynSent=false;
  uint32_t lastBodyAttempt=0, lastStalkAttempt=0;
};
static portMUX_TYPE lightingSettingsMux=portMUX_INITIALIZER_UNLOCKED;
static LightingRuntime lightingState;
static bool lightingPermission=false;
static uint8_t lightingBrakeMode=0;
static uint32_t lightingTxOk=0,lightingTxFail=0;
static bool lightingApSnapshot(uint32_t now) {
  portENTER_CRITICAL(&stateMux);
  const bool ap=gateAPActive, valid=dasAutopilotStateValid;
  const uint8_t state=dasAutopilotState4;
  const uint32_t ms=lastDASStatusMillis;
  portEXIT_CRITICAL(&stateMux);
  // No reference harness exception: missing DAS data always closes the gate.
  return valid && ms!=0u && lightingApGateActivePure(ap,valid,state,ms,now);
}
static void lightingSettingsLoad(){
  Preferences p;uint32_t raw=0;
  if(p.begin("features",true)){raw=p.getUInt("lighting",0);p.end();}
  if((raw&~0x107u)==0u&&(raw&0x100u)&&((raw>>1)&3u)<=2u){lightingPermission=(raw&1u)!=0;lightingBrakeMode=(raw>>1)&3u;}
}
static bool lightingSettingsSave(bool permission,uint8_t brakeMode){
  if(brakeMode>2u||!canTxBarrierMutex||xSemaphoreTake(canTxBarrierMutex,pdMS_TO_TICKS(100))!=pdTRUE)return false;
  Preferences p;bool saved=false;
  if(p.begin("features",false)){const uint32_t value=0x100u|(permission?1u:0u)|(uint32_t(brakeMode)<<1);saved=p.putUInt("lighting",value)==sizeof(uint32_t)&&p.getUInt("lighting",0)==value;p.end();}
  if(saved){portENTER_CRITICAL(&lightingSettingsMux);if(permission!=lightingPermission||!permission){lightingState.run={};lightingState.train={};}if(brakeMode!=lightingBrakeMode)lightingDynHighResetPure(lightingState.dynamic);lightingPermission=permission;lightingBrakeMode=brakeMode;portEXIT_CRITICAL(&lightingSettingsMux);}
  xSemaphoreGive(canTxBarrierMutex);return saved;
}
static void lightingObserve(uint8_t bus,uint32_t id,uint8_t dlc,const uint8_t *data,uint32_t epoch,uint32_t ms){
  if(!data||dlc>8u||id>0x7ffu||epoch==0u)return;
  const bool ap=lightingApSnapshot(ms);
  portENTER_CRITICAL(&lightingSettingsMux);
  if(lightingState.epoch!=epoch){lightingState=LightingRuntime{};lightingState.epoch=epoch;}
  auto &s=lightingState;
  if(bus==P4_CHASSIS&&((id==0x145u&&dlc==8u)||(id==0x39du&&dlc==5u))){
    const uint8_t i=id==0x145u?0u:1u;
    s.brake[i]=i==0?lightingDecodeBrake145Pure(data,dlc):lightingDecodeBrake39DPure(data,dlc);s.brakeMs[i]=ms;s.brakeSeen[i]=true;
  }
  if(bus==P4_BODY){
    if(id==0x3f5u&&dlc>=5u){s.beam5=lightingHighBeamControlStatePure(data);s.beamD4=data[4];s.beam5Ms=ms;}
    if(id==0x3f6u&&dlc>=1u){s.beam6=lightingHighBeamLeftStatusPure(data);s.beam6Ms=ms;}
    if((id==0x249u&&dlc==4u)||(id==0x3e9u&&dlc==8u)){
      auto &t=id==0x249u?s.stalk:s.body;
      const bool stalk=id==0x249u;
      const bool echo=t.sent&&uint32_t(ms-t.sentMs)<(stalk?700u:200u)&&
        (stalk?((data[1]&0xf0u)==(t.last[1]&0xf0u)&&memcmp(data+2,t.last+2,2)==0):memcmp(data,t.last,6)==0);
      const bool checksum=stalk?data[0]==leftStalkChecksumPure(data,data[1]&15u):data[7]==teslaAdditiveChecksumPure(0x3e9u,data);
      if(!echo&&checksum){
        t.valid=true;t.ms=ms;memcpy(t.data,data,dlc);
        if(!stalk||s.train.left==0)t.counter=stalk?(data[1]&15u):(data[6]>>4);
        if(stalk){
          const uint8_t push=(data[1]>>4)&3u;
          const bool quiet=!t.sent||uint32_t(ms-t.sentMs)>=LIGHTING_AP1_TX_QUIET_MS;
          lightingAp1RunStepPure(s.run,lightingPermission&&ap&&activeTurnSignalVariant==TURN_SIGNAL_STALK,push==2u&&s.prevPush!=2u,quiet,ms);
          s.prevPush=push;if(push==2u)s.carPushMs=ms;
        }
      }
    }
  }
  portEXIT_CRITICAL(&lightingSettingsMux);
}
static void lightingService(){
  const uint32_t now=millis();
  if(!canTxBarrierMutex||xSemaphoreTake(canTxBarrierMutex,0)!=pdTRUE)return;
  const uint32_t epoch=canTxBarrierState.epoch;
  const bool transport=!canTxAdministrativeHold&&!canUsbPassive()&&p4CanAllRunning()&&epoch!=0u&&(P4_BODY!=p4CanBusB()||twaiNonSummonAdmissionOpen());
  const bool ap=lightingApSnapshot(now);
  portENTER_CRITICAL(&stateMux);
  const uint8_t gear=gear118Raw;const uint32_t gearMs=gear118Ms;
  portEXIT_CRITICAL(&stateMux);
  portENTER_CRITICAL(&nagCtxMux);
  const bool speedValid=nagCtx.vehicleSpeedValid&&uint32_t(now-nagCtx.lastVehicleSpeedMs)<=500u;
  const int32_t speed=nagPartySpeedKphX100Pure(nagCtx.vehicleSpeedRaw);
  portEXIT_CRITICAL(&nagCtxMux);
  portENTER_CRITICAL(&blinkAMux);
  const bool blinkerBusy=activeTurn!=STALK_IDLE||blinkerTxRequestState.pendingDir!=0u;
  portEXIT_CRITICAL(&blinkAMux);
  CanFrame out={};out.bus=P4_BODY;bool send=false,stalkSend=false;uint8_t counter=0;bool requested=false;
  portENTER_CRITICAL(&lightingSettingsMux);
  auto &s=lightingState;
  if(s.epoch!=epoch){s=LightingRuntime{};s.epoch=epoch;}
  if(!transport){s.run={};s.train={};s.dynamic={};s.dynSent=false;}
  else {
    lightingAp1RunStepPure(s.run,lightingPermission&&ap&&activeTurnSignalVariant==TURN_SIGNAL_STALK,false,true,now);
    const bool beam=lightingPermission&&ap&&s.run.running;
    LightingBrakeSignalPure a={},b={};
    if(s.brakeSeen[0]&&uint32_t(now-s.brakeMs[0])<=300u)a=s.brake[0];
    if(s.brakeSeen[1]&&uint32_t(now-s.brakeMs[1])<=300u)b=s.brake[1];
    const auto brake=lightingMergeBrakePure(a,b);
    const bool driveFresh=gearMs!=0u&&uint32_t(now-gearMs)<=500u&&speedValid;
    lightingDynHighStepPure(s.dynamic,driveFresh?lightingBrakeMode:0u,brake.brake,brake.hard,gear,driveFresh?speed:0);
    requested=s.dynamic.requested;
    bool fresh=false,lit=false,cancel=false;
    lightingBeamReportPure(now,s.beam6Ms,s.beam6,s.beam5Ms,s.beam5,fresh,lit,cancel,s.beamD4,s.beam5Ms!=0u);
    LightingAp1TopupEventPure event={};
    bool train=false;
    if(!beam)lightingAp1PushResetPure(s.train);
    else if(fresh||s.train.left!=0u)train=lightingAp1TopupDuePure(s.train,beam,fresh,lit,s.carPushMs!=0u&&uint32_t(now-s.carPushMs)<120u,s.carPushMs,now,LIGHTING_TOPUP_PROFILE_RETRY,&event);
    // Own four-frame train yields to normal blinker work; never replace a real stalk action.
    if(train&&!blinkerBusy&&s.stalk.valid&&uint32_t(now-s.stalk.ms)<=200u&&uint32_t(now-s.lastStalkAttempt)>=10u&&((s.stalk.data[1]>>4)&3u)==0u&&(s.stalk.data[2]&15u)==0u){
      stalkSend=send=true;out.can_id=0x249u;out.can_dlc=4;memcpy(out.data,s.stalk.data,4);
      counter=(s.stalk.counter+1u)&15u;out.data[1]=(out.data[1]&0xc0u)|0x20u|counter;
      out.data[0]=leftStalkChecksumPure(out.data,counter);s.lastStalkAttempt=now;
    }else if(s.body.valid&&uint32_t(now-s.body.ms)<=1500u&&uint32_t(now-s.lastBodyAttempt)>=20u&&(beam||requested||s.dynSent)){
      send=true;out.can_id=0x3e9u;out.can_dlc=8;memcpy(out.data,s.body.data,8);
      // Preserve the car's brake request and all unrelated bits. No beam write on stop.
      if(requested)lightingApplyDynamicBrakePure(out.data,true);
      if(beam)lightingApplyApForcedHighBeamPure(out.data,true,true);
      counter=(s.body.counter+1u)&15u;out.data[6]=(out.data[6]&15u)|(counter<<4);
      out.data[7]=teslaAdditiveChecksumPure(0x3e9u,out.data);s.lastBodyAttempt=now;
    }
  }
  portEXIT_CRITICAL(&lightingSettingsMux);
  if(send){
    const esp_err_t result=p4CanSendFrame(&out);
    portENTER_CRITICAL(&lightingSettingsMux);
    if(result==ESP_OK){
      lightingTxOk++;auto &t=stalkSend?s.stalk:s.body;t.counter=counter;t.sent=true;t.sentMs=now;memcpy(t.last,out.data,out.can_dlc);
      if(stalkSend)lightingAp1PushSentPure(s.train);else s.dynSent=requested;
    }else lightingTxFail++;
    portEXIT_CRITICAL(&lightingSettingsMux);
  }
  xSemaphoreGive(canTxBarrierMutex);
}
static void lightingTask(void*){for(;;){lightingService();vTaskDelay(pdMS_TO_TICKS(5));}}
