"""Exercise production R79 guards: rejected work is observed without driver side effects."""
import os
from pathlib import Path
import subprocess
import tempfile
from test_s3xy_pairing_host import source_block
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'vehicle_logic.h').read_text()
functions='\n'.join(source_block(source,s) for s in ('static void r79PriorityLimitDeadline(', 'static esp_err_t r79ApGateTransmitOnce(', 'static esp_err_t r79ApGateTransmitGuarded(', 'static esp_err_t r79LabDirectTwaiTransmit(', 'static esp_err_t r79LabDirectTwaiTransmitOnce(', 'static esp_err_t r79LabDirectTwaiTransmitGuarded(', 'static esp_err_t mux1DisplayTransmit(', 'static esp_err_t tlsscTransmitGuarded(') if s in source)
prelude=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include "driver/twai.h"
#include "p4_twai_priority.h"
#include "p4_twai_diag.h"
#include "r79_timing_capture_pure.h"
#include "r79_fixed_policy_pure.h"
static int stateMux=0;
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
struct ApConfig { bool enabled; };static ApConfig r79ApGateConfig{};
static uint32_t lastDASStatusMillis=1000;static constexpr uint32_t R79_AP_DAS_FRESH_MS=3000;
static volatile uint32_t r79NativeApDeadlineMs=0;
void r79NativeApPermissionPublishLocked(uint32_t){if(r79ApGateConfig.enabled)r79NativeApDeadlineMs=lastDASStatusMillis+R79_AP_DAS_FRESH_MS;}
static int barrier=1;static int* canTxBarrierMutex=&barrier;
static bool available=true,gate=true,canTxAdministrativeHold=false,twaiReady=true;
static volatile uint32_t r79ApGateGeneration=8;
static volatile uint32_t r79Mode1PostMux2Generation=12;
static int activeVehicleProfile=1,activeVehicleTopology=1,canTxBarrierState=0;
constexpr uint8_t CAN_TX_FRESH_BOTH=3;
constexpr uint32_t VISION_CONTROL_FRESH_MS_PURE=250;
static bool fresh=true,nonSummon=true;
static uint32_t nowMs=1000;
uint32_t millis(){return nowMs;}
uint8_t readMuxID(const uint8_t*d){return d[0]&7;}
bool vehicleProfileTopologyValid(int,int){return true;}
bool canTxBarrierAllowsMaskedPure(int,uint32_t,uint8_t){return fresh;}
bool twaiNonSummonAdmissionOpen(){return nonSummon;}
static uint8_t lastReason=0;
uint32_t p4CanReadinessMask(){return 15;}
static uint32_t generationValue=8;static int driverCalls=0,rejections=0;
static int priorityCalls=0; static p4_twai_priority_guard_t lastGuard{};
static int lastError=0,lastWait=0;static uint8_t lastPayload=0;
constexpr int pdTRUE=1,VISION_CONTROL_CHASSIS_PURE=0;
#define pdMS_TO_TICKS(ms) (ms)
static bool locked=false;static unsigned yields=0;static int timeouts=0;static bool cancelOnYield=false,releaseOnYield=false;
static unsigned releaseYield=1,yieldAdvance=1;
int xSemaphoreTake(int*,int){if(!available||locked)return 0;locked=true;return pdTRUE;}
void xSemaphoreGive(int*){assert(locked);locked=false;}
void vTaskDelay(unsigned ticks){assert(!locked&&ticks==1);++yields;nowMs+=yieldAdvance;
 if(releaseOnYield&&yields>=releaseYield)available=true;
 if(available){assert(xSemaphoreTake(canTxBarrierMutex,0)==pdTRUE);xSemaphoreGive(canTxBarrierMutex);}
 if(cancelOnYield)++generationValue;
}
uint32_t r79ApGateGenerationSnapshot(){return generationValue;}
bool r79FastReactiveGateOpen(uint8_t*reason=nullptr){if(reason)*reason=gate?p4_r79_timing::NONE:p4_r79_timing::POLICY_GATE;return gate;}
static bool retryEligible=true;static uint32_t retryUntil=UINT32_MAX;
bool p4CanR79InputCurrent(){return true;}
bool r79RetryEligible(uint32_t now){return retryEligible&&now<=retryUntil;}
bool r79RetryGuardCapture(p4_twai_priority_guard_t&,uint32_t now,const uint32_t*){return r79RetryEligible(now);}
static bool ulcSnoozeApplyFinal(uint8_t*, uint32_t&){return false;}
static void ulcSnoozeRecordFinal(bool,uint32_t,esp_err_t){}
static unsigned composeAdvance=0;
bool r79DmsApplyFinal(uint8_t*d){nowMs+=composeAdvance;d[7]=0x99;return true;}
bool visionControlApplyFinal(uint8_t*,int){return false;}
void visionControlRecordTx(bool,int,bool){}
uint32_t canTxCancellationGenerationSnapshot(const volatile uint32_t*g){return *g;}
esp_err_t p4CanSendB(const twai_message_t*f,TickType_t wait,uint8_t=0){driverCalls++;lastWait=wait;lastPayload=f->data[7];assert(locked);if(timeouts>0){--timeouts;return ESP_ERR_TIMEOUT;}return ESP_OK;}
esp_err_t p4CanSendMux1B(const twai_message_t*f){return p4CanSendB(f,0);}
esp_err_t p4CanSendR79B(const twai_message_t*f,const p4_twai_priority_guard_t& guard){
 ++priorityCalls;lastGuard=guard;return p4CanSendB(f,0);
}
uint8_t p4CanBusB(){return 0;}
void p4R79TimingGateRejected(uint8_t bus,const twai_message_t*f,uint32_t wait,int32_t result,uint8_t reason=p4_r79_timing::UNSPECIFIED,uint32_t ready=0){(void)ready;lastReason=reason;assert(bus==0&&f);rejections++;lastError=result;lastWait=wait;}
void canBTraceRecordTx(const twai_message_t*,esp_err_t){}
'''
deadline_arg=', &deadline' if 'const uint32_t *hardDeadline' in functions else ''
functions += '''\nstatic esp_err_t withDeadline(const twai_message_t*f,uint16_t wait,const volatile uint32_t*g,uint32_t expected,uint32_t ap,uint32_t deadline){(void)deadline;return r79LabDirectTwaiTransmitGuarded(f,wait,g,expected,ap''' + deadline_arg + ''');}\n'''
scenarios=r'''
int main(){
 (void)stateMux;(void)R79_AP_DAS_FRESH_MS;
 twai_message_t f{};f.identifier=0x3fd;f.data_length_code=8;f.data[0]=1;
 volatile uint32_t retryGen=9;
 // Availability at exactly the selected budget still permits one final
 // zero-wait attempt. Oversleep must not extend that budget.
 for(bool direct:{false,true})for(uint32_t start:{1000u,UINT32_MAX-1u}){
  auto attempt=[&](){return direct?r79LabDirectTwaiTransmitGuarded(&f,2,&retryGen,9,8):r79ApGateTransmitGuarded(&f,2,8);};
  nowMs=start;available=false;releaseOnYield=true;releaseYield=2;yields=0;driverCalls=0;
  assert(attempt()==ESP_OK&&"final wait tick must attempt the newly available transport");
  assert(nowMs==start+2u&&yields==2&&driverCalls==1&&!locked);
  nowMs=start;available=false;releaseYield=1;yieldAdvance=3;yields=0;driverCalls=0;
  assert(attempt()==ESP_ERR_TIMEOUT&&nowMs==start+3u&&driverCalls==0&&!locked);
  yieldAdvance=1;releaseYield=1;releaseOnYield=false;
 }
 nowMs=1000;available=true;driverCalls=0;rejections=0;priorityCalls=0;
 retryEligible=false;
 assert(r79LabDirectTwaiTransmitGuarded(&f,0,&retryGen,9,8,nullptr,true)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==0&&lastReason==p4_r79_timing::POLICY_GATE);
 retryEligible=true;retryUntil=1001;composeAdvance=2;
 assert(r79LabDirectTwaiTransmitGuarded(&f,0,&retryGen,9,8,nullptr,true)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==0&&lastReason==p4_r79_timing::POLICY_GATE);
 retryUntil=UINT32_MAX;composeAdvance=0;nowMs=1000;rejections=0;

 available=false;assert(r79ApGateTransmitGuarded(&f,0,8)==ESP_ERR_TIMEOUT);assert(rejections==1&&driverCalls==0&&lastWait==0&&lastReason==p4_r79_timing::BARRIER_BUSY);
 available=true;assert(r79ApGateTransmitGuarded(&f,2,7)==ESP_ERR_INVALID_STATE);assert(rejections==2&&driverCalls==0&&lastReason==p4_r79_timing::GENERATION_CHANGED);
 gate=false;assert(r79ApGateTransmitGuarded(&f,0,8)==ESP_ERR_INVALID_STATE);assert(rejections==3&&driverCalls==0&&lastReason==p4_r79_timing::POLICY_GATE);
 gate=true;assert(r79ApGateTransmitGuarded(&f,2,8)==ESP_OK);assert(rejections==3&&driverCalls==1&&lastPayload==0x99&&lastWait==0&&f.data[7]==0);
 assert(lastGuard.source==P4_TWAI_TX_SOURCE_R79_IMMEDIATE);
 assert(priorityCalls==1&&lastGuard.generation==&r79ApGateGeneration&&lastGuard.expected_generation==8);
 assert(lastGuard.administrative_hold==&canTxAdministrativeHold&&!lastGuard.cancel_generation&&!lastGuard.has_deadline);
 canTxAdministrativeHold=true;assert(r79LabDirectTwaiTransmit(&f,0,8)==ESP_ERR_INVALID_STATE);assert(rejections==4&&lastReason==p4_r79_timing::ADMIN_HOLD);
 volatile uint32_t g=9;assert(r79LabDirectTwaiTransmitGuarded(&f,0,&g,9,8)==ESP_ERR_INVALID_STATE);assert(rejections==5);
 canTxAdministrativeHold=false;assert(r79LabDirectTwaiTransmitGuarded(&f,0,&g,8,8)==ESP_ERR_INVALID_STATE);assert(rejections==6&&lastReason==p4_r79_timing::CANCELLED);
 assert(r79LabDirectTwaiTransmitGuarded(&f,0,&g,9,8)==ESP_OK);assert(rejections==6&&driverCalls==2&&lastWait==0);
 assert(priorityCalls==2&&lastGuard.cancel_generation==&g&&lastGuard.expected_cancel_generation==9);
 assert(lastGuard.generation==&r79ApGateGeneration&&lastGuard.expected_generation==8&&!lastGuard.has_deadline);
 assert(withDeadline(&f,0,&g,9,8,1000)==ESP_OK);
 assert(lastGuard.has_deadline&&lastGuard.deadline_ms==1000);
 nowMs=UINT32_MAX;assert(withDeadline(&f,0,&g,9,8,0)==ESP_OK);
 assert(lastGuard.has_deadline&&lastGuard.deadline_ms==0);nowMs=1000;
 // Congestion retries yield without owning the cross-bus barrier.
 yields=0;timeouts=1;int before=driverCalls;
 assert(r79ApGateTransmitGuarded(&f,2,8)==ESP_OK);
 assert(driverCalls==before+2&&yields==1&&lastWait==0&&!locked);
 timeouts=10;yields=0;before=driverCalls;
 assert(r79ApGateTransmitGuarded(&f,2,8)==ESP_ERR_TIMEOUT);
 assert(driverCalls==before+3&&yields==2&&lastWait==0&&!locked);
 timeouts=10;yields=0;before=driverCalls;
 assert(r79ApGateTransmitGuarded(&f,0,8)==ESP_ERR_TIMEOUT);
 assert(driverCalls==before+1&&yields==0&&!locked);
 timeouts=1;cancelOnYield=true;yields=0;before=driverCalls;
 assert(r79LabDirectTwaiTransmitGuarded(&f,2,&g,9,8)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==before+1&&yields==1&&!locked);
 cancelOnYield=false;generationValue=8;timeouts=0;
 nowMs=1000;
 // Caller-computed budgets may be stale before guard entry.
 timeouts=0;before=driverCalls;
 assert(withDeadline(&f,2,&g,9,8,999)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==before&&!locked);
 timeouts=1;yields=0;before=driverCalls;
 assert(withDeadline(&f,2,&g,9,8,1000)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==before+1&&yields==1&&!locked);
 nowMs=1000;timeouts=0;composeAdvance=1;before=driverCalls;
 assert(withDeadline(&f,2,&g,9,8,1000)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==before&&!locked);composeAdvance=0;nowMs=1000;
 // Unsigned elapsed budget also works through millis wraparound.
 nowMs=UINT32_MAX;timeouts=1;yields=0;
 assert(r79LabDirectTwaiTransmitGuarded(&f,2,&g,9,8)==ESP_OK);
 assert(yields==1&&nowMs==0&&lastWait==0&&!locked);nowMs=1000;
 rejections=0;driverCalls=0;available=false;
 assert(mux1DisplayTransmit(&f,8,3,false)==ESP_ERR_INVALID_STATE);assert(rejections==1&&driverCalls==0);
 available=true;fresh=false;rejections=0;
 assert(mux1DisplayTransmit(&f,8,3,false)==ESP_ERR_INVALID_STATE);assert(rejections==1&&driverCalls==0);
 fresh=true;rejections=0;
 assert(mux1DisplayTransmit(&f,8,3,true,0)==ESP_ERR_INVALID_STATE);assert(rejections==1&&driverCalls==0);
 f.data[0]=0;canTxAdministrativeHold=true;rejections=0;
 assert(tlsscTransmitGuarded(&f,8)==ESP_ERR_INVALID_STATE);assert(rejections==1&&driverCalls==0);
 canTxAdministrativeHold=false;available=false;rejections=0;
 assert(tlsscTransmitGuarded(&f,8)==ESP_ERR_INVALID_STATE);assert(rejections==1&&driverCalls==0);
 available=true;fresh=false;rejections=0;
 assert(tlsscTransmitGuarded(&f,8)==ESP_ERR_INVALID_STATE);assert(rejections==1&&driverCalls==0);
 const int priorityBefore=priorityCalls;
 fresh=true;rejections=0;assert(tlsscTransmitGuarded(&f,8)==ESP_OK);assert(rejections==0&&driverCalls==1);
 assert(priorityCalls==priorityBefore);
 // AP Control permission must expire even when the observed NON_AP session
 // remains inactive and no generation transition occurs.
 f.data[0]=1;r79ApGateConfig.enabled=true;nowMs=1000;lastDASStatusMillis=1000;
 assert(r79ApGateTransmitGuarded(&f,0,8)==ESP_OK);
 assert(!lastGuard.has_deadline&&lastGuard.permission_deadline_ms==&r79NativeApDeadlineMs&&r79NativeApDeadlineMs==4000);
 assert(withDeadline(&f,0,&g,9,8,2000)==ESP_OK&&lastGuard.deadline_ms==2000);
 assert(withDeadline(&f,0,&g,9,8,5000)==ESP_OK&&lastGuard.deadline_ms==5000&&*lastGuard.permission_deadline_ms==4000);
 lastDASStatusMillis=UINT32_MAX-2999;nowMs=UINT32_MAX;
 assert(r79ApGateTransmitGuarded(&f,0,8)==ESP_OK);
 assert(!lastGuard.has_deadline&&lastGuard.permission_deadline_ms&&*lastGuard.permission_deadline_ms==0);
 assert(withDeadline(&f,0,&g,9,8,UINT32_MAX)==ESP_OK&&lastGuard.deadline_ms==UINT32_MAX);
 r79ApGateConfig.enabled=false;nowMs=1000;

 assert(r79LabDirectTwaiTransmitGuarded(&f,0,&r79Mode1PostMux2Generation,12,8)==ESP_OK);
 assert(lastGuard.source==P4_TWAI_TX_SOURCE_R79_PERIODIC);
 assert(lastGuard.cancel_generation==&r79Mode1PostMux2Generation);
 // Temporary contention yields within the budget without owning the lock.
 available=false;yields=0;before=driverCalls;nowMs=1000;
 assert(r79ApGateTransmitGuarded(&f,2,8)==ESP_ERR_TIMEOUT);
 assert(yields==2&&driverCalls==before&&!locked);
 releaseOnYield=true;yields=0;
 assert(r79ApGateTransmitGuarded(&f,2,8)==ESP_OK);
 assert(yields==1&&driverCalls==before+1&&!locked);
 available=false;yields=0;before=driverCalls;
 assert(r79LabDirectTwaiTransmitGuarded(&f,2,&g,9,8)==ESP_OK);
 assert(yields==1&&driverCalls==before+1&&!locked);
 releaseOnYield=false;available=false;canTxBarrierMutex=nullptr;yields=0;
 assert(r79ApGateTransmitGuarded(&f,2,8)==ESP_ERR_INVALID_STATE&&yields==0);
 canTxBarrierMutex=&barrier;
 // Last-tick attempts retain permission/generation and quiet hard deadlines.
 for(bool direct:{false,true}){
  nowMs=1000;available=false;releaseOnYield=true;releaseYield=2;yields=0;
  generationValue=8;cancelOnYield=true;before=driverCalls;
  const auto err=direct?r79LabDirectTwaiTransmitGuarded(&f,2,&g,9,8):r79ApGateTransmitGuarded(&f,2,8);
  assert(err==ESP_ERR_INVALID_STATE&&driverCalls==before&&yields==2&&!locked);
  cancelOnYield=false;generationValue=8;
 }
 nowMs=1000;available=false;yields=0;before=driverCalls;
 assert(withDeadline(&f,2,&g,9,8,1001)==ESP_ERR_INVALID_STATE);
 assert(driverCalls==before&&yields==2&&!locked);
 releaseOnYield=false;releaseYield=1;
 puts("PASS: actual R79 guard rejection, no-send gates, payload and driver waits preserved");
}
'''
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'guard.cpp';out=Path(td)/'guard';src.write_text(prelude+functions+scenarios)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I'+str(ROOT/'tests'),'-I'+str(ROOT/'tests/r79_timing_fakes'),'-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)

# Classify the actual policy gate using the unchanged pure authorization rules.
policy=source_block(source,'static bool r79FastReactiveGateOpen(uint8_t *diagnosticReason) {')
POLICY=r'''
#include <cassert>
#include <cstdint>
#include "r79_timing_capture_pure.h"
#include "summon_state_pure.h"
#include "r79_fixed_policy_pure.h"
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
static int stateMux=0;
static bool canTxAdministrativeHold=false,twaiReady=true,gateSummoning=false;
static bool r79PostApOffHold=false;
static bool dasAutopilotStateValid=false;
static uint8_t dasAutopilotState4=0;
static R79ManualSuppressionPure r79ManualSuppression{};
static R79ApGateConfigPure r79ApGateConfig{};
static R79ApGateDecisionPure apDecision={true,R79_AP_GATE_BYPASS_PURE,0};
static uint32_t nowMs=1000;
uint32_t millis(){return nowMs;}
bool dasStateApActivePure(bool valid,uint8_t state){return valid&&state>=3&&state<=6;}
R79ApGateDecisionPure r79ApGateDecisionLocked(uint32_t){return apDecision;}
'''
POLICY_MAIN=r'''
int main(){
 uint8_t why=255;
 assert(r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::NONE);
 canTxAdministrativeHold=true;assert(!r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::ADMIN_HOLD);
 canTxAdministrativeHold=false;twaiReady=false;assert(!r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::TRANSPORT_NOT_READY);twaiReady=true;
 r79ManualSuppression.active=true;r79ManualSuppression.gearRaw=TESLA_GEAR_D;
 assert(!r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::MANUAL_D);
 r79ManualSuppression.gearRaw=TESLA_GEAR_R;assert(!r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::MANUAL_R);
 gateSummoning=true;assert(r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::NONE);gateSummoning=false;
 r79ApGateConfig.allowManualDriving=true;assert(r79FastReactiveGateOpen(&why));
 r79PostApOffHold=true;assert(!r79FastReactiveGateOpen(&why)&&why==p4_r79_timing::POLICY_GATE);
 r79PostApOffHold=false;assert(r79FastReactiveGateOpen(&why));
 r79ManualSuppression.active=false;
 for(uint8_t reason:{R79_AP_GATE_BLOCKED_PURE,R79_AP_GATE_WAITING_PURE,R79_AP_GATE_UNKNOWN_PURE}){
  apDecision={false,reason,100};assert(!r79FastReactiveGateOpen(&why));
  assert(why==(reason==R79_AP_GATE_BLOCKED_PURE?p4_r79_timing::AP_BLOCKED:reason==R79_AP_GATE_WAITING_PURE?p4_r79_timing::AP_WAITING:p4_r79_timing::AP_UNKNOWN));
 }
}
'''
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'policy.cpp';out=Path(td)/'policy'
 src.write_text('#include <initializer_list>\n'+POLICY+policy+POLICY_MAIN)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
print('PASS: actual policy classifies administrative/transport, manual D/R and AP block/wait/unknown without changing authorization')

# A manual-authorization revoke must invalidate an already-admitted priority slot.
manual=source_block(source,'static void updateR79ManualSuppressionLocked(')
MANUAL=r'''
#include <cassert>
#include <cstdint>
static volatile uint32_t r79ApGateGeneration=1;
static volatile bool countryOverrideR79AuthorizationOpen=true;
static bool dasAutopilotStateValid=true,gateSummoning=false,permit=false;
static uint8_t dasAutopilotState4=0;
constexpr uint8_t TESLA_GEAR_INVALID=0;
struct Manual{};static Manual r79ManualSuppression;
struct Config{bool allowManualDriving;};static Config r79ApGateConfig{};
struct Decision{bool txEnabled;};
bool r79FreshGearRawLocked(uint32_t,uint8_t&){return true;}
bool dasStateApActivePure(bool,uint8_t){return false;}
bool dasStateManualPure(bool,uint8_t){return true;}
bool r79RemoteStartupEvidenceLocked(uint32_t){return false;}
void r79ApGateObserveLocked(uint32_t){}
void r79ManualSuppressionUpdatePure(Manual&,bool,uint8_t,bool,bool,bool,bool,bool){}
Decision r79TxDecisionPure(bool,bool,Manual&,bool){return {permit};}
void countryOverrideUpdateR79AuthorizationLocked(bool open,bool){countryOverrideR79AuthorizationOpen=open;}
'''
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'manual.cpp';out=Path(td)/'manual'
 src.write_text(MANUAL+manual+'''\nint main(){
 updateR79ManualSuppressionLocked(1,true);assert(r79ApGateGeneration==2);
 updateR79ManualSuppressionLocked(2,true);assert(r79ApGateGeneration==2);
 permit=true;updateR79ManualSuppressionLocked(3,true);assert(r79ApGateGeneration==2);
 permit=false;updateR79ManualSuppressionLocked(4,true);assert(r79ApGateGeneration==3);
 }''')
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
print('PASS: manual authorization revocation invalidates admitted R79 generation')

# Real settings writers must allow the real R79 admission path throughout NVS
# I/O. A short final publication barrier still serializes policy changes.
settings_functions='\n'.join(source_block(source,s) for s in (
 'static bool countryOverrideApplySelection(',
 'static bool countryOverrideSetLabEnabledWithBarrier(',
 'static bool visionControlApplySettings(',
 'static bool featureBoolPersist(',
 'static bool driverMonitoringControlApply(',
 'static bool isaSuppressionControlApply(',
 'static bool r79ApControlApply('))
settings_prelude=prelude.replace('struct ApConfig { bool enabled; };',
 'using ApConfig=R79ApGateConfigPure;')
settings_stubs=r"""
#include <functional>
constexpr int portMAX_DELAY=-1,VEHICLE_MODEL_YL=1;
static bool maintenance=false;
bool canMaintenanceActive(){return maintenance;}
static bool nvsOk=true;static unsigned nvsCalls=0;static std::function<void()> onNvs;
static void io(){++nvsCalls;if(onNvs)onNvs();}
#define P4_CAN_DIAG_NVS_WRITE(tag,expr) (expr)
struct Preferences {
 bool begin(const char*,bool){io();return nvsOk;}void end(){io();}
 size_t putUShort(const char*,uint16_t){io();return nvsOk?2u:0u;}
 size_t putBool(const char*,bool){io();return nvsOk?1u:0u;}
 size_t putUInt(const char*,uint32_t){io();return nvsOk?4u:0u;}
};
static int countryOverrideMux,lab3f8Mux,r79LabMux,driverMonitoringControlMux,isaSuppressionControlMux;
static uint8_t countryOverrideMode=0,countryOverrideMapMode=0,visionControlBus=0;
static unsigned countryOverrideCancelGeneration=1,lab3f8Generation=1,visionControlGeneration=1,isaSuppressionGeneration=1;
static bool labMenuEnabled=false,summonHeartbeatOverrideEnabled=false;
static bool visionControlRequestDisabledState=false,driverMonitoringDisableEnabled=false,isaSuppressionEnabled=false;
bool countryOverrideModeValidPure(uint8_t x){return x<10;}bool mapRegionModeValidPure(uint8_t x){return x<10;}
bool featureCfgPersistLab(bool){io();return nvsOk;}
static unsigned cancellations=0;
void mux1CancelPendingLocked(){assert(locked);++cancellations;}
bool visionControlSupported(){return true;}bool visionControlBusSupported(uint8_t b){return b<2;}
static int r79ApGateSession,r79FixedQuietState;
[[maybe_unused]] static bool r79RetryApOnly=false;
[[maybe_unused]] static uint32_t r79RetryApGeneration=0;
static bool r79RetryPending=false;static unsigned r79RetryIndex,r79RetryOriginKind,r79RetryDueMs,r79RetryGeneration;
constexpr unsigned R79LAB_TX_NONE=0;
void updateR79ManualSuppressionLocked(uint32_t,bool){assert(locked);}
"""
settings_main=r"""
int main(){
 twai_message_t msg={};msg.identifier=0x3FD;msg.data_length_code=8;msg.data[0]=1;
 unsigned oldCalls=driverCalls;
 onNvs=[&](){assert(!locked && "settings NVS must not hold CAN TX barrier");
   assert(r79ApGateTransmitOnce(&msg,0,generationValue)==ESP_OK);};
 assert(countryOverrideApplySelection(1,2));assert(countryOverrideMode==1&&countryOverrideMapMode==2);
 assert(countryOverrideSetLabEnabledWithBarrier(true,true));assert(labMenuEnabled);
 assert(visionControlApplySettings(true,0));assert(visionControlRequestDisabledState);
 assert(driverMonitoringControlApply(true));assert(driverMonitoringDisableEnabled);
 assert(isaSuppressionControlApply(true));assert(isaSuppressionEnabled);
 ApConfig ap={true,1,5,true};assert(r79ApControlApply(ap));assert(r79ApGateConfig.enabled&&r79ApGateConfig.delaySeconds==5);
 assert(driverCalls>int(oldCalls)&&!locked&&rejections==0);
 // A failed durable save leaves current published settings and generations.
 nvsOk=false;unsigned gen=r79ApGateGeneration;
 assert(!countryOverrideApplySelection(2,3));assert(countryOverrideMode==1);
 assert(!countryOverrideSetLabEnabledWithBarrier(false,true));assert(labMenuEnabled);
 assert(!visionControlApplySettings(false,0));assert(visionControlRequestDisabledState);
 assert(!driverMonitoringControlApply(false));assert(driverMonitoringDisableEnabled);
 assert(!isaSuppressionControlApply(false));assert(isaSuppressionEnabled);
 ap.enabled=false;assert(!r79ApControlApply(ap));assert(r79ApGateConfig.enabled&&r79ApGateGeneration==gen&&!locked);
 puts("PASS: seven production settings writers keep R79 admission available during NVS; failure leaves live state");
}
"""
with tempfile.TemporaryDirectory() as td:
 src=Path(td)/'settings.cpp';out=Path(td)/'settings'
 src.write_text(settings_prelude+functions+settings_stubs+settings_functions+settings_main)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-I'+str(ROOT/'tests'),'-I'+str(ROOT/'tests/r79_timing_fakes'),'-I'+str(ROOT),str(src),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
