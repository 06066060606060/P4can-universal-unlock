"""Actual Mode1 scheduling/service with real priority policy and preserved FIFO."""
from pathlib import Path
import os,subprocess,tempfile
from test_s3xy_pairing_host import source_block
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'vehicle_logic.h').read_text()
names=('static void r79RetryCancel(', 'static void r79RetrySchedule(', 'static bool r79LabTransmitOnce(', 'static bool r79LabTransmitShadow(', 'static void r79LabRetryTick(', 'static bool r79FixedFastEcho(')
functions='\n'.join(source_block(s[s.rfind(n):],n) for n in names)
retry_sig='static bool r79RetryEligible('
if retry_sig in s: functions=source_block(s[s.rfind(retry_sig):],retry_sig)+'\n'+functions
ap_sig='static bool r79RetryApAllowedLocked('
if ap_sig in s: functions=source_block(s[s.rfind(ap_sig):],ap_sig)+'\n'+functions
prelude=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#include "driver/twai.h"
#include "p4_twai_priority.h"
#include "summon_state_pure.h"
#include "runtime_gate_pure.h"
#include "r79_fixed_policy_pure.h"
#include "r79_timing_capture_pure.h"
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
constexpr int pdTRUE=1,R79LAB_TX_NONE=0,R79LAB_TX_IMMEDIATE=1,R79LAB_TX_RETRY=2,R79LAB_TX_PERIODIC=3,R79_TX_STATE_ACTIVE=1;
static int lock=1,*canTxBarrierMutex=&lock,r79LabMux=0,stateMux=0;
static bool current=true,gate=true,fresh=true,remote=false,confirmed=false,stockValid=true;
static uint8_t gear=TESLA_GEAR_P;
static bool dasValid=false,retryApAllowed=true;static uint8_t dasState=0;
static uint32_t dasMs=1000;
static uint32_t nowMs=1000,gen=8,r79Mode1PostMux2Generation=8,r79LabLastTxMs=0,r79ApGateGeneration=8;
static uint8_t r79Bit18Policy=0,r79Mode1TxWaitMode=1;
static int r79FastEchoAttempts=0,r79FastEchoTxOk=0,r79FastEchoTxFail=0;
static bool inputCurrent=true;[[maybe_unused]] static unsigned echoWait=99;
bool p4CanR79InputCurrent(){return inputCurrent;}
static int calls=0,clears=0;static esp_err_t result=ESP_ERR_TIMEOUT;
static std::vector<int> queue={0x334,0x3FD,0x3C2};
static bool r79RetryPending=false;
static uint8_t r79RetryIndex=0,r79RetryOriginKind=0;
static uint32_t r79RetryDueMs=0,r79RetryGeneration=0,r79RetryScheduled=0,r79RetryTxOk=0,r79RetryTxFail=0,r79RetryExhausted=0,r79LastRetryMs=0,r79QuietGuardSkip=0;
static volatile uint32_t r79NativeRetryGeneration=1;
static bool r79RetryApOnly=false;static uint32_t r79RetryApGeneration=0;
static R79FixedQuietStatePure r79FixedQuietState{};
static uint8_t latest[8]={1,0,12,0,0,0,0,42},sent[8]={};
uint32_t millis(){return nowMs;}
int xSemaphoreTake(int*,int){return pdTRUE;}void xSemaphoreGive(int*){}
uint32_t r79ApGateGenerationSnapshot(){return gen;}
bool r79Mode1PostMux2GenerationCurrent(uint32_t g){return current&&g==r79Mode1PostMux2Generation;}
bool r79FastReactiveGateOpen(uint8_t*reason=nullptr){if(reason)*reason=p4_r79_timing::POLICY_GATE;return gate;}
int p4CanHandleB(){return 7;}int p4CanBusB(){return 0;}int p4CanReadinessMask(){return 15;}
esp_err_t twai_clear_transmit_queue_v2(int){++clears;queue.clear();return ESP_OK;}
uint8_t readMuxID(const uint8_t*d){return d[0]&7;}bool r79Hw3Active(){return false;}
uint8_t summonPriorityStateSnapshot(uint32_t){return summonTxPriorityStatePure(fresh,gear,remote,confirmed);}
uint8_t summonPriorityStateLocked(uint32_t now){return summonPriorityStateSnapshot(now);}
bool r79FreshGearRawLocked(uint32_t,uint8_t& out){out=gear;return fresh;}
bool r79ApDasFreshLocked(uint32_t now){return dasValid&&(uint32_t)(now-dasMs)<=3000u;}
static bool &dasAutopilotStateValid=dasValid;static uint8_t &dasAutopilotState4=dasState;
R79ApGateDecisionPure r79ApGateDecisionLocked(uint32_t){return {retryApAllowed,0,0};}
struct R79RuntimeStatus{int state;};R79RuntimeStatus r79RuntimeStatusSnapshot(uint32_t){return {gate?R79_TX_STATE_ACTIVE:0};}
// The authority producer has separate real-producer/native coverage. Here
// publish a deterministic token to exercise actual reservation ownership.
bool r79RetryGuardCapture(p4_twai_priority_guard_t&g,uint32_t now,const uint32_t*expected=nullptr){
 if(expected&&*expected!=r79NativeRetryGeneration)return false;
 if(!summonPriorityAllowsR79FlushPure(summonPriorityStateSnapshot(now))){g.retry_generation=&r79NativeRetryGeneration;g.expected_retry_generation=r79NativeRetryGeneration;}
 return true;
}
bool r79CopyLatestStock(uint8_t*d){memcpy(d,latest,8);return stockValid;}
esp_err_t send(const twai_message_t*f){++calls;memcpy(sent,f->data,8);assert(!(sent[2]&8)&&(sent[5]&128));return result;}
esp_err_t r79ApGateTransmitGuarded(const twai_message_t*f,uint16_t wait,uint32_t){echoWait=wait;return send(f);}
esp_err_t r79LabDirectTwaiTransmit(const twai_message_t*f,uint16_t,uint32_t){return send(f);}
esp_err_t r79LabDirectTwaiTransmitGuarded(const twai_message_t*f,uint16_t,const volatile uint32_t*g,uint32_t expected,uint32_t,const uint32_t*,bool=false,const uint32_t*authority=nullptr){if(authority&&*authority!=r79NativeRetryGeneration)return ESP_ERR_INVALID_STATE;if(*g!=expected)return ESP_ERR_INVALID_STATE;return send(f);}
void r79LabRecordTxResult(bool,const twai_message_t&,uint8_t){}
void r79FastReactiveRecordTxState(esp_err_t,uint32_t){}
void p4R79TimingGateRejected(int,const twai_message_t*,unsigned,int,uint8_t,int){}
'''
main=r'''
static twai_message_t stockFrame(){twai_message_t f{};f.identifier=0x3FD;f.data_length_code=8;memcpy(f.data,latest,8);return f;}
static void reset(){r79NativeRetryGeneration=1;(void)r79RetryApOnly;(void)r79RetryApGeneration;(void)dasAutopilotStateValid;(void)dasAutopilotState4;dasValid=false;dasState=0;dasMs=1000;retryApAllowed=true;inputCurrent=true;nowMs=1000;gen=r79ApGateGeneration=r79Mode1PostMux2Generation=8;current=gate=fresh=stockValid=true;gear=TESLA_GEAR_P;remote=confirmed=false;result=ESP_ERR_TIMEOUT;calls=0;r79RetryCancel();r79FixedQuietState={};latest[7]=42;}
int main(){
 (void)canTxBarrierMutex;(void)stateMux;
 const auto original=queue;
 // Periodic acceptance owns only its MUX-bounded request. It must not remove
 // the longer-lived immediate recovery, including an already spent retry.
 for(bool ap:{false,true})for(bool spent:{false,true}){
  reset();if(ap){gear=TESLA_GEAR_D;dasValid=true;dasState=3;}
  assert(r79FixedFastEcho(stockFrame())&&r79RetryPending);
  if(spent){nowMs=r79RetryDueMs;r79LabRetryTick();}
  const auto due=r79RetryDueMs;const auto index=r79RetryIndex;
  const auto authority=r79RetryApGeneration;const auto retryGeneration=r79RetryGeneration;
  result=ESP_OK;
  assert(r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,1340,r79Mode1PostMux2Generation));
  assert(r79RetryPending&&r79RetryOriginKind==R79LAB_TX_IMMEDIATE&&"periodic acceptance cannot erase immediate recovery");
  assert(r79RetryDueMs==due&&r79RetryIndex==index&&r79RetryGeneration==retryGeneration&&r79RetryApGeneration==authority);
  ++r79Mode1PostMux2Generation;nowMs=due;r79LabRetryTick();assert(!r79RetryPending);
 }
 reset();inputCurrent=false;assert(r79FixedFastEcho(stockFrame()));assert(echoWait==0 && "superseded MUX1 must not spend its 2ms wait blocking the newer input");
 // Authorized AP+D gains the same bounded recovery without changing
 // Summon priority. An open general R79 gate alone is insufficient.
 reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;
 assert(summonPriorityStateSnapshot(nowMs)==SUMMON_PRIORITY_NORMAL);
 assert(r79FixedFastEcho(stockFrame()));
 assert(r79RetryPending&&r79RetryDueMs==1005&&"fresh authorized AP+D must reserve retry");
 nowMs=1005;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 for(unsigned why=0;why<7;++why){
  reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;
  if(why==0)dasValid=false;if(why==1)dasState=0;if(why==2)dasState=15;
  if(why==3)nowMs=4001;if(why==4)fresh=false;if(why==5)gear=TESLA_GEAR_N;
  if(why==6)retryApAllowed=false;
  assert(r79FixedFastEcho(stockFrame()));assert(!r79RetryPending);
 }
 // The state can expire or change after reservation, even with AP-control
 // bypass/full-runtime permission left open at the boundary fake.
 for(unsigned why=0;why<4;++why){
  reset();gear=TESLA_GEAR_D;dasValid=true;dasState=6;
  assert(r79FixedFastEcho(stockFrame())&&r79RetryPending);
  nowMs=1005;if(why==0)dasState=0;if(why==1)nowMs=4001;
  if(why==2)fresh=false;if(why==3)retryApAllowed=false;
  result=ESP_OK;r79LabRetryTick();assert(calls==1&&!r79RetryPending);
 }
 reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;
 r79FixedQuietObserveStockPure(r79FixedQuietState,2,1000,true,150);nowMs=1150;
 assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,1340,r79Mode1PostMux2Generation));
 assert(r79RetryPending&&r79RetryDueMs==1155);
 nowMs=1155;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;nowMs=UINT32_MAX-2;dasMs=nowMs;
 assert(r79FixedFastEcho(stockFrame())&&r79RetryDueMs==2);
 nowMs=2;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 // A publication invalidates an AP-only reservation even when AP becomes
 // valid again before service and generic R79 authorization stayed open.
 reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;
 assert(r79FixedFastEcho(stockFrame())&&r79RetryPending);
 ++r79NativeRetryGeneration;nowMs=r79RetryDueMs;result=ESP_OK;
 r79LabRetryTick();assert(calls==1&&!r79RetryPending&&"old AP reservation cannot cross invalidation");
 // A new stock failure after invalidation can legitimately reserve new work.
 result=ESP_ERR_TIMEOUT;assert(r79FixedFastEcho(stockFrame()));
 assert(r79RetryPending&&r79RetryApGeneration==r79NativeRetryGeneration);
 // Existing PARK recovery does not depend on the AP-only authority.
 reset();assert(r79FixedFastEcho(stockFrame())&&r79RetryPending&&!r79RetryApOnly);
 ++r79NativeRetryGeneration;nowMs=r79RetryDueMs;result=ESP_OK;
 r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 // Actual policy: only fresh PARK, READY and ACTIVE qualify. Ordinary N/D/R,
 // unknown/stale gear must not acquire new retry privilege.
 for(uint8_t g:{TESLA_GEAR_P,TESLA_GEAR_N,TESLA_GEAR_D,TESLA_GEAR_R,TESLA_GEAR_INVALID})
 for(bool valid:{false,true}){
  auto p=summonTxPriorityStatePure(valid,g,false,false);
  assert(summonPriorityAllowsR79FlushPure(p)==(valid&&g==TESLA_GEAR_P));
 }
 assert(!summonPriorityAllowsR79FlushPure(255));
 assert(summonPriorityAllowsR79FlushPure(SUMMON_PRIORITY_READY)&&summonPriorityAllowsR79FlushPure(SUMMON_PRIORITY_ACTIVE));
 // Failed immediate PARK echo arms +5 ms; retry uses latest stock and transform.
 reset();assert(r79FixedFastEcho(stockFrame()));assert(r79RetryPending&&r79RetryDueMs==1005&&calls==1);
 nowMs=1004;r79LabRetryTick();assert(calls==1);
 latest[7]=99;result=ESP_OK;nowMs=1005;r79LabRetryTick();assert(calls==2&&!r79RetryPending&&sent[7]==99);
 // Existing bounded relative delays: +5 then +15 then +30; no fourth retry.
 reset();auto exhausted=r79RetryExhausted;assert(r79FixedFastEcho(stockFrame()));
 for(uint32_t due:{1005u,1020u,1050u}){assert(r79RetryDueMs==due);nowMs=due;r79LabRetryTick();}
 assert(calls==4&&!r79RetryPending&&r79RetryExhausted==exhausted+1);
 nowMs=2000;r79LabRetryTick();assert(calls==4);
 // Revocation before service: gear leaves P, becomes stale, permission closes,
 // policy generation changes, or the stock template disappears.
 for(unsigned scenario=0;scenario<5;scenario++){
  reset();assert(r79FixedFastEcho(stockFrame()));assert(r79RetryPending);
  if(scenario==0)gear=TESLA_GEAR_D;if(scenario==1)fresh=false;
  if(scenario==2)gate=false;if(scenario==3)++gen;if(scenario==4)stockValid=false;
  nowMs=1005;r79LabRetryTick();assert(!r79RetryPending&&calls==1);
 }
 // A newer successful stock echo cancels the older reservation.
 reset();assert(r79FixedFastEcho(stockFrame()));latest[7]=7;result=ESP_OK;
 assert(r79FixedFastEcho(stockFrame()));assert(!r79RetryPending&&sent[7]==7);nowMs=1005;r79LabRetryTick();assert(calls==2);
 // Administrative/permission errors never gain an immediate retry.
 reset();result=ESP_ERR_INVALID_STATE;assert(r79FixedFastEcho(stockFrame()));assert(!r79RetryPending);
 reset();gate=false;assert(!r79FixedFastEcho(stockFrame()));assert(calls==0&&!r79RetryPending);
 // READY/ACTIVE retain the same successful recovery behavior.
 for(unsigned state=0;state<2;state++){reset();fresh=false;remote=state==0;confirmed=state==1;assert(r79FixedFastEcho(stockFrame()));assert(r79RetryPending);nowMs=1005;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);}
 // uint32 retry due arithmetic is unchanged at rollover.
 reset();nowMs=UINT32_MAX-2;assert(r79FixedFastEcho(stockFrame()));assert(r79RetryDueMs==2);
 nowMs=1;r79LabRetryTick();assert(calls==1);nowMs=2;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 // PARK periodic retry still respects the MUX2 generation and hard deadline.
 reset();r79FixedQuietObserveStockPure(r79FixedQuietState,2,1000,true,150);
 nowMs=1150;assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,1340,r79Mode1PostMux2Generation));assert(r79RetryPending);
 nowMs=1155;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 reset();r79FixedQuietObserveStockPure(r79FixedQuietState,2,1000,true,150);nowMs=1339;
 assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,1340,r79Mode1PostMux2Generation));assert(calls==1&&!r79RetryPending);
 reset();r79FixedQuietObserveStockPure(r79FixedQuietState,2,1000,true,150);nowMs=1150;
 assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,1340,r79Mode1PostMux2Generation));++r79Mode1PostMux2Generation;
 nowMs=1155;r79LabRetryTick();assert(calls==1&&!r79RetryPending);
 // A scheduled periodic retry cannot survive a late service past its hard
 // deadline, including when both the due time and deadline wrapped uint32.
 for(uint32_t base:{1000u,UINT32_MAX-100u}){
  reset();r79FixedQuietObserveStockPure(r79FixedQuietState,2,base,true,150);
  nowMs=base+150u;const uint32_t deadline=base+340u;
  assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,deadline,r79Mode1PostMux2Generation));assert(r79RetryPending);
  nowMs=deadline+1u;r79LabRetryTick();assert(calls==1&&!r79RetryPending);
 }
 reset();const uint32_t base=UINT32_MAX-100u;
 r79FixedQuietObserveStockPure(r79FixedQuietState,2,base,true,150);nowMs=base+150u;
 assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,base+340u,r79Mode1PostMux2Generation));assert(r79RetryPending);
 nowMs=base+155u;result=ESP_OK;r79LabRetryTick();assert(calls==2&&!r79RetryPending);
 reset();current=false;assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,1200,8));assert(calls==0);
 current=true;assert(!r79LabTransmitShadow(latest,R79LAB_TX_PERIODIC,999,8));assert(calls==0);
 assert(queue==original&&clears==0);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'main.cpp').write_text(prelude+functions+main)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-I'+str(ROOT/'tests'),'-I'+str(ROOT),str(p/'main.cpp'),'-o',str(p/'run')],check=True)
 subprocess.run([str(p/'run')],check=True)
print('PASS: actual PARK retry scheduling/service, bounded cadence, cancellation/rollover/deadline and unchanged FIFO')

# Integrated production admission guards, not only injected TX results.
p=prelude.replace('#include <cassert>','#include <cassert>\n#include <cstdio>\n#include "p4_twai_priority.h"\n#include "p4_twai_diag.h"')
p=p.replace('int xSemaphoreTake(int*,int){return pdTRUE;}','static bool available=true; int xSemaphoreTake(int*,int){return available?pdTRUE:0;}')
p=p.replace('esp_err_t r79ApGateTransmitGuarded(const twai_message_t*f,uint16_t wait,uint32_t){echoWait=wait;return send(f);}', '''static bool canTxAdministrativeHold=false;
constexpr int VISION_CONTROL_CHASSIS_PURE=0;
void r79DmsApplyFinal(uint8_t*){} bool visionControlApplyFinal(uint8_t*,int){return false;}
void visionControlRecordTx(bool,int,bool){} void r79PriorityLimitDeadline(p4_twai_priority_guard_t&){}
bool ulcSnoozeApplyFinal(uint8_t*,uint32_t&){return false;} void ulcSnoozeRecordFinal(bool,uint32_t,esp_err_t){}
void canBTraceRecordTx(const twai_message_t*,esp_err_t){}
esp_err_t p4CanSendR79B(const twai_message_t*f,const p4_twai_priority_guard_t&){return send(f);}
static bool revokeRetryDuringWait=false,recoverRetryDuringWait=false;
void vTaskDelay(unsigned){++nowMs;if(recoverRetryDuringWait){recoverRetryDuringWait=false;++r79NativeRetryGeneration;dasState=3;available=true;}if(revokeRetryDuringWait){revokeRetryDuringWait=false;dasState=0;available=true;}}
''')
p=p.replace('esp_err_t r79LabDirectTwaiTransmit(const twai_message_t*f,uint16_t,uint32_t){return send(f);}', '')
p=p[:p.index('esp_err_t r79LabDirectTwaiTransmitGuarded(')]+p[p.index('\nvoid r79LabRecordTxResult',p.index('esp_err_t r79LabDirectTwaiTransmitGuarded(')):]
p += "\n#define pdMS_TO_TICKS(x) (x)\nstatic bool twaiReady=true;\nuint32_t canTxCancellationGenerationSnapshot(const volatile uint32_t*g){return *g;}\n"
p=p.replace('void p4R79TimingGateRejected(int,const twai_message_t*,unsigned,int,uint8_t,int){}', 'static int rejects=0; void p4R79TimingGateRejected(int,const twai_message_t*,unsigned,int,uint8_t,int){++rejects;}')
# Inject cancellation at real function boundaries, after a failed admission and
# between permission observation and reservation publication.
p=p.replace('static bool current=true,', 'static bool cancelAfterTx=false,revokeAtGate=false;\nstatic bool current=true,')
p=p.replace('return gate;}','if(revokeAtGate){revokeAtGate=false;++gen;++r79ApGateGeneration;}return gate;}')
p=p.replace('void r79LabRecordTxResult(bool,const twai_message_t&,uint8_t){}', 'static void r79RetryCancel(bool);\nvoid r79LabRecordTxResult(bool,const twai_message_t&,uint8_t){if(cancelAfterTx){cancelAfterTx=false;++gen;++r79ApGateGeneration;r79RetryCancel(false);}}')
s=(ROOT/'vehicle_logic.h').read_text()
names=('static esp_err_t r79ApGateTransmitOnce(', 'static esp_err_t r79ApGateTransmitGuarded(', 'static esp_err_t r79LabDirectTwaiTransmit(', 'static esp_err_t r79LabDirectTwaiTransmitOnce(', 'static esp_err_t r79LabDirectTwaiTransmitGuarded(', 'static void r79RetryCancel(', 'static void r79RetrySchedule(', 'static bool r79LabTransmitOnce(', 'static bool r79LabTransmitShadow(', 'static void r79LabRetryTick(', 'static bool r79FixedFastEcho(')
f='\n'.join(source_block(s[s.rfind(n):],n) for n in names)
if retry_sig in s: f=source_block(s[s.rfind(retry_sig):],retry_sig)+'\n'+f
if ap_sig in s: f=source_block(s[s.rfind(ap_sig):],ap_sig)+'\n'+f
setup=main.split('int main(){')[0]
contention_main=r'''
int main(){
 // Barrier contention is transient, unlike missing transport/permission.
 reset(); available=false;
 assert(r79FixedFastEcho(stockFrame()));
 assert(calls==0 && r79RetryPending && r79RetryDueMs==nowMs+5);
 available=true;nowMs=r79RetryDueMs;result=ESP_OK;r79LabRetryTick();
 assert(calls==1&&!r79RetryPending);
 // Fresh AP can change while a retry waits for the barrier. Recheck
 // retry eligibility on every final admission, even with the general gate open.
 reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;available=false;
 assert(r79FixedFastEcho(stockFrame())&&r79RetryPending);
 nowMs=r79RetryDueMs;revokeRetryDuringWait=true;result=ESP_OK;r79LabRetryTick();
 assert(calls==0&&!r79RetryPending&&"AP loss during retry wait must block admission");
 // Loss and recovery entirely within the wait must not reacquire a new token.
 reset();gear=TESLA_GEAR_D;dasValid=true;dasState=3;available=false;
 assert(r79FixedFastEcho(stockFrame())&&r79RetryPending);
 nowMs=r79RetryDueMs;recoverRetryDuringWait=true;result=ESP_OK;r79LabRetryTick();
 assert(calls==0&&!r79RetryPending&&"AP invalidation during wait cannot revive old retry");
 // Reservation never needs the contested transport lock.
 reset();available=false;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);
 assert(r79RetryPending&&r79RetryDueMs==1005);
 // Busy retry attempts still consume the bounded three-attempt budget.
 auto failures=r79RetryTxFail, exhausted=r79RetryExhausted;
 for(unsigned i=0;i<3;i++){
   nowMs=r79RetryDueMs;r79LabRetryTick();
   assert(r79RetryTxFail==failures+i+1);
   if(i<2){assert(r79RetryPending&&r79RetryIndex==i+1);assert(r79RetryDueMs==nowMs+r79RetryDelayMsPure(i+1));}
 }
 assert(!r79RetryPending&&r79RetryExhausted==exhausted+1&&calls==0);
 // Overdue/current recovery cannot be postponed/reset by failed stock echoes.
 reset();available=true;assert(r79FixedFastEcho(stockFrame()));
 assert(r79RetryDueMs==1007);nowMs=1010;
 assert(r79FixedFastEcho(stockFrame()));assert(r79RetryDueMs==1007);
 auto before=calls;r79LabRetryTick();assert(calls>before&&r79RetryIndex==1);
 auto savedDue=r79RetryDueMs;assert(r79FixedFastEcho(stockFrame()));
 assert(r79RetryDueMs==savedDue&&r79RetryIndex==1);
 // Periodic failure cannot steal immediate reservation; promotion retains due/budget.
 r79RetrySchedule(R79LAB_TX_PERIODIC,nowMs,r79Mode1PostMux2Generation);
 assert(r79RetryOriginKind==R79LAB_TX_IMMEDIATE&&r79RetryDueMs==savedDue&&r79RetryIndex==1);
 reset();r79RetrySchedule(R79LAB_TX_PERIODIC,nowMs,r79Mode1PostMux2Generation);
 nowMs+=3;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);
 assert(r79RetryOriginKind==R79LAB_TX_IMMEDIATE&&r79RetryDueMs==1005);
 // Wraparound earliest-due preservation.
 reset();nowMs=UINT32_MAX-2;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);
 nowMs=1;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);assert(r79RetryDueMs==2);
 // No retry can bypass revocation, hold or missing controller lock.
 reset();available=false;assert(r79FixedFastEcho(stockFrame()));available=true;
 ++gen;nowMs=r79RetryDueMs;r79LabRetryTick();assert(calls==0&&!r79RetryPending);
 reset();available=false;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);
 gate=false;nowMs=r79RetryDueMs;r79LabRetryTick();assert(calls==0&&!r79RetryPending);
 reset();available=true;canTxAdministrativeHold=true;
 r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);nowMs=r79RetryDueMs;
 r79LabRetryTick();assert(calls==0&&!r79RetryPending);canTxAdministrativeHold=false;
 reset();canTxBarrierMutex=nullptr;assert(r79FixedFastEcho(stockFrame()));assert(calls==0&&!r79RetryPending);canTxBarrierMutex=&lock;
 // Cancellation after failed admission but before bookkeeping stays cancelled.
 reset();available=true;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);
 nowMs=r79RetryDueMs;cancelAfterTx=true;r79LabRetryTick();
 assert(!r79RetryPending);auto afterCancelled=calls;nowMs+=100;r79LabRetryTick();assert(calls==afterCancelled);
 // Permission snapshot racing generation revocation cannot publish stale work.
 reset();revokeAtGate=true;r79RetrySchedule(R79LAB_TX_IMMEDIATE,nowMs,gen);
 assert(!r79RetryPending&&calls==0);
 assert(queue==std::vector<int>({0x334,0x3FD,0x3C2})&&clears==0);
}
'''


def recovery_native_regression():
    import os
    from pathlib import Path
    import pathlib
    import subprocess
    import tempfile
    
    root = ROOT
    fixture = root / 'tests/test_r79_ulc_composition_host.py'
    text = fixture.read_text()
    boundary = text.index('temp=tempfile.TemporaryDirectory()')
    ns = {'__file__': str(fixture)}
    exec(compile(text[:boundary], str(fixture), 'exec'), ns)
    native = ns['native']
    app = ns['app'].split('int main(){')[0]
    # The shared fixture supplies a nonrecursive mutex and availability hook.
    assert 'barrierAvailable=true' in app and 'if(barrierLocked)' in app
    old = 'static bool r79FastReactiveGateOpen(uint8_t*)'
    assert app.count(old) == 1
    app = app.replace(old, 'static bool r79FastReactiveGateOpen(uint8_t* = nullptr)')
    app += r'''
    #define pdMS_TO_TICKS(ms) (ms)
    static int r79LabMux=0;
    enum {R79LAB_TX_NONE=0,R79LAB_TX_IMMEDIATE=1,R79LAB_TX_RETRY=2,R79LAB_TX_PERIODIC=3,R79_TX_STATE_ACTIVE=1};
    static uint8_t r79Bit18Policy=0,r79Mode1TxWaitMode=1;
    static unsigned r79FastEchoAttempts,r79FastEchoTxOk,r79FastEchoTxFail;
    static uint32_t r79LabLastTxMs;
    static bool r79RetryPending=false,r79RetryApOnly=false;
    static uint8_t r79RetryIndex=0,r79RetryOriginKind=0;
    static uint32_t r79RetryDueMs,r79RetryGeneration,r79RetryScheduled,r79RetryTxOk,r79RetryTxFail,r79RetryExhausted,r79LastRetryMs,r79QuietGuardSkip,r79RetryApGeneration;
    static volatile uint32_t r79NativeRetryGeneration=1;
    static R79FixedQuietStatePure r79FixedQuietState{};
    static bool r79Mode1ReinjectEnabled=true,r79LabStockValid=true;
    static uint16_t r79Mode1DelayMs=0;
    static uint32_t r79QuietArmCount,r79QuietFireCount;
    static uint8_t r79LabLastStockRaw[8]={1,0,12,0,0,0,0,42};
    struct R79RuntimeStatus{int state;};
    static R79RuntimeStatus r79RuntimeStatusSnapshot(uint32_t){return {gate?R79_TX_STATE_ACTIVE:0};}
    static bool r79Hw3Active(){return false;}
    static bool r79CopyLatestStock(uint8_t*d){memcpy(d,r79LabLastStockRaw,8);return r79LabStockValid;}
    static bool p4CanR79InputCurrent(){return p4_twai_r79_input_current_v2(p4CanHandles[0],p4CanMux1Origin[0].sequence);}
    static void r79LabRecordTxResult(bool,const twai_message_t&,uint8_t){}
    static void r79FastReactiveRecordTxState(esp_err_t,uint32_t){}
    '''
    src = (root/'vehicle_logic.h').read_text()
    fn = ns['fn']
    app += '\n'.join(fn(sig) for sig in (
        'static esp_err_t r79ApGateTransmitGuarded(',
        'static esp_err_t r79LabDirectTwaiTransmit(',
        'static esp_err_t r79LabDirectTwaiTransmitGuarded(',
        'static bool r79Mode1PostMux2GenerationCurrent(',
        'static void r79RetryCancel(', 'static void r79RetrySchedule(',
        'static bool r79LabTransmitOnce(', 'static bool r79LabTransmitShadow(',
        'static void r79LabRetryTick(', 'static bool r79FixedFastEcho(',
        'static void r79FixedObserveStock(', 'static void r79FixedTick(',
    ))
    app += r'''
    int main(){
     for(bool quiet:{false,true}){
      twai_obj_t d;twai_hal_context_t h;Queue q,r;init(&d,&h,&q,&r,0);
      p4CanHandles[0]=&d;r79ApGateGeneration=1;r79Mode1PostMux2Generation=2;
      ulcSnoozePending=false;r79RetryCancel();r79FixedQuietState={};
      r79Mode1ReinjectEnabled=quiet;gate=true;nowMs=1000;
      twai_message_t stock{};stock.identifier=0x3FD;stock.data_length_code=8;
      memcpy(stock.data,r79LabLastStockRaw,8);
      barrierAvailable=false;assert(r79FixedFastEcho(stock));barrierAvailable=true;
      assert(nowMs==1002&&r79RetryPending&&r79RetryDueMs==1007);
      // Keep the physical transmitter busy; acceptance can only mean pending.
      assert(p4CanSendB(&normal,0)==ESP_OK);assert(h.n==1);
      nowMs=1003;irqRx(&d,rxFrame(0x3FD,2));
      twai_message_t got{};assert(twai_receive_v2(&d,&got,0)==ESP_OK);
      r79FixedObserveStock(2,nowMs);assert(r79RetryPending);
      assert(p4_twai_r79_periodic_ready_v2(&d));r79FixedTick();
      assert(r79RetryPending&&"periodic native acceptance must retain immediate recovery");
      if(quiet)assert(s_p4_priority[0].pending&&s_p4_priority[0].guard.source==P4_TWAI_TX_SOURCE_R79_PERIODIC);
      nowMs=1004;irqRx(&d,rxFrame(0x3FD,0));
      assert(twai_receive_v2(&d,&got,0)==ESP_OK);r79FixedObserveStock(0,nowMs);
      nowMs=1007;r79LabRetryTick();
      nowMs=1008;finish(&d);
      assert(h.n==2&&"a cancelled periodic slot must not erase immediate R79 recovery");
      assert(h.sent[1].header.id==0x3FD);
      assert(!r79RetryPending&&!s_p4_priority[0].pending);
      printf("actual app/native: quiet_%s -> R79 hardware loads=%u (normal frame excluded)\n",quiet?"accepted":"disabled",h.n-1);
     }
    }
    '''
    # Reuse the existing domain fixture's isolated platform-header/diagnostic build.
    scope = dict(ns)
    scope.update(native=native, app=app, root=root, pathlib=pathlib, os=os,
                 subprocess=subprocess, tempfile=tempfile)
    exec(compile(text[boundary:], str(fixture), 'exec'), scope)

with tempfile.TemporaryDirectory() as d:
 out=Path(d);src=out/'contention.cpp';src.write_text(p+f+setup+contention_main)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-I'+str(ROOT/'tests'),'-I'+str(ROOT/'tests/r79_timing_fakes'),'-I'+str(ROOT),str(src),'-o',str(out/'run')],check=True)
 subprocess.run([str(out/'run')],check=True)
 recovery_native_regression()
print('PASS: real R79 guards and Park contention recovery, reservation priority/bounds and revocation')
