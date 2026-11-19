#pragma once
// ModelY_CH JSON: UI_enableFullSelfDriving only; multiplexor is never rewritten.
static portMUX_TYPE fsdSettingsMux = portMUX_INITIALIZER_UNLOCKED;
static bool fsdSettingsEnabled = false;
static bool fsdSettingsSuspendAp = false;
static uint8_t fsdSettingsValues = 0;
static bool fsdSettingsSeen[2] = {};
static uint8_t fsdSettingsStock[8] = {};
static uint32_t fsdSettingsMs[2] = {}, fsdSettingsEpoch[2] = {};
static uint32_t fsdSettingsTxOk = 0, fsdSettingsTxFail = 0;
// Reuse the application settings namespace so existing reset operations clear it.
static void fsdSettingsLoad() {
  Preferences prefs;
  uint32_t saved=0;
  if(prefs.begin("features",true)){saved=prefs.getUInt("fsd",0);prefs.end();}
  if((saved&~0x1FFFu)==0u && (saved&0x100u)) {
    fsdSettingsEnabled=(saved&0x40u)!=0u;
    fsdSettingsValues=saved&2u;
    fsdSettingsSuspendAp=(saved&0x80u)!=0u;
  }
}
static bool fsdSettingsSave(bool enabled,uint8_t values,bool suspendAp=false) {
  Preferences prefs;
  if(!prefs.begin("features",false)) return false;
  const bool ok=prefs.putUInt("fsd",0x100u|(enabled?0x40u:0u)|(suspendAp?0x80u:0u)|(values&2u))==sizeof(uint32_t);
  prefs.end();return ok;
}
// Explicit S3XY action toggles only the persistent master under the final barrier.
static bool toggleFsdSettingsFromButton(){
  if(!canTxBarrierMutex||xSemaphoreTake(canTxBarrierMutex,pdMS_TO_TICKS(100))!=pdTRUE)return false;
  portENTER_CRITICAL(&fsdSettingsMux);
  const bool enabled=!fsdSettingsEnabled,suspend=fsdSettingsSuspendAp;
  const uint8_t values=fsdSettingsValues;
  portEXIT_CRITICAL(&fsdSettingsMux);
  const bool saved=fsdSettingsSave(enabled,values,suspend);
  if(saved){portENTER_CRITICAL(&fsdSettingsMux);fsdSettingsEnabled=enabled;portEXIT_CRITICAL(&fsdSettingsMux);}
  xSemaphoreGive(canTxBarrierMutex);return saved;
}
static void fsdSettingsObserve(uint8_t bus,uint32_t id,uint8_t dlc,const uint8_t *data,uint32_t epoch,uint32_t ms){
  if(bus!=P4_CHASSIS||id!=0x3FDu||dlc!=8u||!data)return;
  const uint8_t mux=data[0]&7u;if(mux!=0)return;
  portENTER_CRITICAL(&fsdSettingsMux);const uint8_t slot=mux==0?0:1;
  fsdSettingsSeen[slot]=(data[7]&0x80u)!=0;fsdSettingsMs[slot]=ms;fsdSettingsEpoch[slot]=epoch;
  fsdSettingsStock[1]=(data[5]>>6)&1u;
  portEXIT_CRITICAL(&fsdSettingsMux);
}
// Unknown/stale AP status blocks FSD until a fresh manual state is confirmed.
static bool fsdSettingsApBlocked() {
  portENTER_CRITICAL(&stateMux);
  const bool blocked=!r79ApDasFreshLocked((uint32_t)millis()) ||
      dasStateApActivePure(dasAutopilotStateValid,dasAutopilotState4);
  portEXIT_CRITICAL(&stateMux);
  return blocked;
}
// Caller holds the final TX barrier. Only selected fields are patched.
static bool fsdSettingsPatch(uint8_t bus, uint8_t *data) {
  if(bus!=P4_CHASSIS || !(data[7]&0x80u)) return false;
  const uint8_t mux=data[0]&7u;
  if(mux!=0u) return false;
  portENTER_CRITICAL(&fsdSettingsMux);
  const bool enabled=fsdSettingsEnabled, suspendAp=fsdSettingsSuspendAp; const uint8_t values=fsdSettingsValues;
  portEXIT_CRITICAL(&fsdSettingsMux);
  if(!enabled || (suspendAp && fsdSettingsApBlocked())) return false;
  data[5]=(data[5]&0xBFu)|((values&2u)?0x40u:0u);
  return true;
}
static void fsdSettingsRecord(esp_err_t err) {
  portENTER_CRITICAL(&fsdSettingsMux);
  if(err==ESP_OK) fsdSettingsTxOk++; else fsdSettingsTxFail++;
  portEXIT_CRITICAL(&fsdSettingsMux);
}
// Shared with TLSSC: one composed MUX0 copy, no competing FSD clone.
static esp_err_t fsdSettingsTransmit(const twai_message_t &stock, const twai_message_t &proposed, bool tlssc, uint32_t epoch, uint32_t receivedMs) {
  if(!canTxBarrierMutex || xSemaphoreTake(canTxBarrierMutex,0)!=pdTRUE) return ESP_ERR_INVALID_STATE;
  const bool transport=!canTxAdministrativeHold && !canUsbPassive() && p4CanAllRunning() && epoch!=0u && epoch==canTxBarrierState.epoch && (uint32_t)((uint32_t)millis()-receivedMs)<=100u && twaiNonSummonAdmissionOpen();
  const bool tlsscAllowed=transport && tlssc && twaiReady && canTxBarrierAllowsMaskedPure(canTxBarrierState,epoch,CAN_TX_FRESH_BOTH);
  twai_message_t out=tlsscAllowed?proposed:stock;
  const bool fsd=transport && fsdSettingsPatch(p4CanBusB(),out.data);
  esp_err_t err=ESP_ERR_INVALID_STATE;
  if(tlsscAllowed || fsd) { err=p4CanSendB(&out,0);canBTraceRecordTx(&out,err);if(fsd) fsdSettingsRecord(err); }
  xSemaphoreGive(canTxBarrierMutex);
  return tlssc && !tlsscAllowed ? ESP_ERR_INVALID_STATE : err;
}
static void fsdSettingsExtra(const CanFrame &stock, uint32_t epoch, uint32_t ms) {
  if(stock.bus!=P4_CHASSIS || stock.can_id!=0x3FDu || stock.can_dlc!=8u || !canTxBarrierMutex || xSemaphoreTake(canTxBarrierMutex,0)!=pdTRUE) return;
  CanFrame out=stock;
  if(!canTxAdministrativeHold && !canUsbPassive() && p4CanAllRunning() && epoch!=0u && epoch==canTxBarrierState.epoch && (uint32_t)((uint32_t)millis()-ms)<=100u && (stock.bus!=p4CanBusB()||twaiNonSummonAdmissionOpen()) && fsdSettingsPatch(stock.bus,out.data)) fsdSettingsRecord(p4CanSendFrame(&out));
  xSemaphoreGive(canTxBarrierMutex);
}
