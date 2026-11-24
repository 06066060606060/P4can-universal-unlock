#pragma once
static portMUX_TYPE serviceSettingsMux=portMUX_INITIALIZER_UNLOCKED;
static bool chinaRestoreEnabled=false;
static uint32_t chinaRestoreTxOk=0,chinaRestoreTxFail=0;
static void serviceSettingsLoad(){Preferences p;if(p.begin("features",true)){chinaRestoreEnabled=p.getBool("chinaRestore",false);p.end();}}
static bool serviceSettingsSetRestore(bool enabled){
  if(!canTxBarrierMutex||xSemaphoreTake(canTxBarrierMutex,pdMS_TO_TICKS(100))!=pdTRUE)return false;
  Preferences p;bool saved=false;
  if(p.begin("features",false)){saved=p.putBool("chinaRestore",enabled)==sizeof(bool);p.end();}
  if(saved){portENTER_CRITICAL(&serviceSettingsMux);chinaRestoreEnabled=enabled;portEXIT_CRITICAL(&serviceSettingsMux);}
  xSemaphoreGive(canTxBarrierMutex);return saved;
}
// One enqueue attempt per explicit click; no saved entry request or retry.
static esp_err_t serviceSettingsEnter(){
  const uint32_t epoch=canTxEpochSnapshot();
  if(!canTxBarrierMutex||xSemaphoreTake(canTxBarrierMutex,pdMS_TO_TICKS(100))!=pdTRUE)return ESP_ERR_INVALID_STATE;
  esp_err_t err=ESP_ERR_INVALID_STATE;
  if(!canTxAdministrativeHold&&!canUsbPassive()&&p4CanAllRunning()&&epoch!=0u&&epoch==canTxBarrierState.epoch&&(p4CanBusB()!=P4_BODY||twaiNonSummonAdmissionOpen())){
    CanFrame out;out.bus=P4_BODY;out.can_id=0x339u;out.can_dlc=8;memset(out.data,0,sizeof(out.data));out.data[5]=0x80u;
    err=p4CanSendFrame(&out);
  }
  xSemaphoreGive(canTxBarrierMutex);return err;
}
// ModelY_CH: DAS_autopilot bits0..2, DAS_autopilotBase bits3..5.
static void chinaRestoreEcho(uint8_t bus,uint32_t id,uint8_t dlc,const uint8_t *data,uint32_t epoch,uint32_t ms){
  if(bus!=P4_CHASSIS||id!=0x331u||dlc!=6u||!data||!canTxBarrierMutex||xSemaphoreTake(canTxBarrierMutex,0)!=pdTRUE)return;
  portENTER_CRITICAL(&serviceSettingsMux);const bool enabled=chinaRestoreEnabled;portEXIT_CRITICAL(&serviceSettingsMux);
  if(enabled&&!canTxAdministrativeHold&&!canUsbPassive()&&p4CanAllRunning()&&epoch!=0u&&epoch==canTxBarrierState.epoch&&(uint32_t)((uint32_t)millis()-ms)<=100u&&(bus!=p4CanBusB()||twaiNonSummonAdmissionOpen())){
    CanFrame out;out.bus=bus;out.can_id=id;out.can_dlc=dlc;memcpy(out.data,data,dlc);out.data[0]=(out.data[0]&0xC0u)|0x1Bu;
    const esp_err_t err=p4CanSendFrame(&out);
    portENTER_CRITICAL(&serviceSettingsMux);if(err==ESP_OK)chinaRestoreTxOk++;else chinaRestoreTxFail++;portEXIT_CRITICAL(&serviceSettingsMux);
  }
  xSemaphoreGive(canTxBarrierMutex);
}

#include "eap_anti_restart.h"  // EAP anti-restart: cached 0x331 replay for TLSSC Restore
