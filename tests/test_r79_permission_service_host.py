"""Actual AP permission publication and nonblocking R79 service integration."""
from pathlib import Path
import os, subprocess, tempfile
from test_s3xy_pairing_host import source_block
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'vehicle_logic.h').read_text()
def fn(sig): return source_block(s[s.rfind(sig):],sig)
pre=r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include "r79_fixed_policy_pure.h"
#include "runtime_gate_pure.h"
#include "summon_state_pure.h"
static int stateMux=0,r79LabMux=0,mutex=1,*canTxBarrierMutex=&mutex;
static unsigned depth=0,takes=0,lastWait=0,refreshes=0,fullTicks=0,retryTicks=0;
static bool available=true,locked=false;
#define portENTER_CRITICAL(p) ((void)(p),++depth)
#define portEXIT_CRITICAL(p) ((void)(p),--depth)
constexpr unsigned portMAX_DELAY=UINT32_MAX;
constexpr int pdTRUE=1;
static uint32_t nowMs=1000,lastDASStatusMillis=1000;
static volatile uint32_t r79ApGateGeneration=1,r79NativeApDeadlineMs=0;
static bool r79NativeApAllowed=false;
static volatile uint32_t r79NativeRetryGeneration=1,r79NativeRetryDeadlineMs=0;
static bool r79NativeRetryAllowed=false;
[[maybe_unused]] constexpr uint32_t SUMMON_GEAR_FRESH_MS=1000;
static constexpr uint32_t R79_AP_DAS_FRESH_MS=3000;
static bool dasAutopilotStateValid=true;
static uint8_t dasAutopilotState4=0;
static R79ApGateConfigPure r79ApGateConfig={true,R79_AP_GATE_BLOCK_PURE,2};
static R79ApGateSessionPure r79ApGateSession{};
static bool r79RetryPending=true;static uint8_t r79RetryOriginKind=1;
constexpr uint8_t R79LAB_TX_IMMEDIATE=1,R79LAB_TX_PERIODIC=2;
struct p4_twai_priority_guard_t {bool has_deadline=false;uint32_t deadline_ms=0;const volatile uint32_t *permission_deadline_ms=nullptr,*retry_generation=nullptr;uint32_t expected_retry_generation=0;};
uint32_t millis(){return nowMs;}
int xSemaphoreTake(int*,unsigned wait){++takes;lastWait=wait;if(!available)return 0;assert(!locked);locked=true;return pdTRUE;}
void xSemaphoreGive(int*){assert(locked);locked=false;}
static uint8_t gearRaw=TESLA_GEAR_D;static uint32_t gearMs=1000;static bool gearValid=true;
bool r79FreshGearRawLocked(uint32_t now,uint8_t& out){out=gearRaw;return gearValid&&(uint32_t)(now-gearMs)<=1000;}
SummonGearDecisionPure summonFreshGearDecisionLocked(uint32_t now){return {gearValid&&(uint32_t)(now-gearMs)<=1000,false,SUMMON_GEAR_118,gearMs};}
uint8_t summonPriorityStateLocked(uint32_t now){uint8_t raw;return summonTxPriorityStatePure(r79FreshGearRawLocked(now,raw),gearRaw,false,false);}
void refreshSummonDerivedStateLocked(uint32_t,bool held){assert(held&&locked&&depth);++refreshes;}
void r79FixedTick(){++fullTicks;}
void r79LabRetryTick(){++retryTicks;}
'''
extra=('static bool r79RetryApAllowedLocked(', 'static void r79NativeRetryPermissionPublishLocked(', 'static bool r79RetryGuardCapture(')
# Behavioral RED remains executable before the new producer/capture exists.
fallback='static void r79NativeRetryPermissionPublishLocked(uint32_t){}\nstatic bool r79RetryGuardCapture(p4_twai_priority_guard_t&,uint32_t){return true;}\n' if extra[0] not in s else ''
parts=fallback+'\n'.join(fn(n) for n in ('static bool r79ApDasFreshLocked(', 'static R79ApGateDecisionPure r79ApGateDecisionLocked(', 'static bool r79RetryEligible(', 'static void r79NativeApPermissionPublishLocked(', 'static void r79ApGateObserveLocked(', 'static bool countryOverrideAuthorizationBarrierLock(', 'static void countryOverrideAuthorizationBarrierUnlock(', 'static void refreshSummonState(', 'static void r79PriorityLimitDeadline('))
if extra[0] in s:
 anchor=parts.index('static bool r79RetryEligible(')
 parts=parts[:anchor]+'\n'.join(fn(n) for n in extra)+'\n'+parts[anchor:]
if 'static bool r79ServiceStateRefreshTry(' in s:
 parts+='\n'+fn('static bool r79ServiceStateRefreshTry(')
else:
 parts+='\nstatic bool r79ServiceStateRefreshTry(){refreshSummonState();return true;}\n'
if 'static void r79TransportSliceTick(' in s:
 parts+='\n'+fn('static void r79TransportSliceTick(')
else:
 parts+='\nstatic void r79TransportSliceTick(bool){r79FixedTick();}\n'
main=r'''
int main(){
 (void)r79NativeApAllowed;(void)r79NativeApDeadlineMs;(void)r79LabMux;
 (void)r79RetryPending;(void)r79RetryOriginKind;(void)R79LAB_TX_IMMEDIATE;(void)R79LAB_TX_PERIODIC;
 available=false;assert(!r79ServiceStateRefreshTry());
 assert(takes==1&&lastWait==0&&refreshes==0&&!locked);
 canTxBarrierMutex=nullptr;assert(!r79ServiceStateRefreshTry());assert(takes==1);
 canTxBarrierMutex=&mutex;available=true;assert(r79ServiceStateRefreshTry());
 assert(takes==2&&lastWait==0&&refreshes==1&&!locked&&!depth);
 // Slice service cannot consume periodic retry before unread stock cycles.
 r79RetryPending=true;r79RetryOriginKind=R79LAB_TX_PERIODIC;r79TransportSliceTick(false);
 assert(fullTicks==0&&retryTicks==0);
 r79RetryOriginKind=R79LAB_TX_IMMEDIATE;r79TransportSliceTick(false);
 assert(fullTicks==0&&retryTicks==1);
 r79RetryPending=false;r79TransportSliceTick(false);assert(retryTicks==1);
 r79TransportSliceTick(true);assert(fullTicks==1&&!depth);
 // NON_AP refresh extends only permission; never an earlier quiet hard limit.
 nowMs=3999;lastDASStatusMillis=1000;r79ApGateObserveLocked(nowMs);
 const auto generation=r79ApGateGeneration;
 p4_twai_priority_guard_t g{};g.has_deadline=true;g.deadline_ms=4100;r79PriorityLimitDeadline(g);
 assert(g.permission_deadline_ms==&r79NativeApDeadlineMs&&g.deadline_ms==4100);
 assert(__atomic_load_n(g.permission_deadline_ms,__ATOMIC_ACQUIRE)==4000);
 lastDASStatusMillis=3999;r79ApGateObserveLocked(nowMs);
 assert(r79ApGateGeneration==generation&&*g.permission_deadline_ms==6999);
 // Invalid DAS while NON_AP must revoke, despite inactive AP session.
 dasAutopilotState4=15;r79ApGateObserveLocked(nowMs);
 assert(r79ApGateGeneration!=generation&&!r79NativeApAllowed);
 const auto invalidGeneration=r79ApGateGeneration;r79ApGateObserveLocked(nowMs);
 assert(r79ApGateGeneration==invalidGeneration);
 dasAutopilotState4=0;lastDASStatusMillis=nowMs;r79ApGateObserveLocked(nowMs);
 assert(r79NativeApAllowed);nowMs=7000;r79ApGateObserveLocked(nowMs);
 assert(!r79NativeApAllowed&&r79ApGateGeneration!=invalidGeneration);
 // AP BLOCK and DELAY still revoke/hold; permission only publishes after release.
 nowMs=8000;lastDASStatusMillis=8000;dasAutopilotState4=3;r79ApGateObserveLocked(nowMs);
 assert(!r79ApGateDecisionLocked(nowMs).allowed&&!r79NativeApAllowed);
 r79ApGateConfig.mode=R79_AP_GATE_DELAY_PURE;r79ApGateSession={};r79ApGateObserveLocked(nowMs);
 assert(!r79NativeApAllowed);nowMs=10000;lastDASStatusMillis=10000;r79ApGateObserveLocked(nowMs);
 assert(r79NativeApAllowed&&r79ApGateDecisionLocked(nowMs).allowed);
 // AP-specific native retry authority must exist even with AP control bypassed.
 nowMs=12000;lastDASStatusMillis=gearMs=nowMs;gearRaw=TESLA_GEAR_D;
 dasAutopilotStateValid=true;dasAutopilotState4=3;r79ApGateConfig.enabled=false;
 r79ApGateObserveLocked(nowMs);p4_twai_priority_guard_t retry{};
 assert(r79RetryGuardCapture(retry,nowMs));
 assert(retry.retry_generation==&r79NativeRetryGeneration && "AP-only retry needs native revocation");
 assert(retry.permission_deadline_ms==&r79NativeRetryDeadlineMs&&*retry.permission_deadline_ms==13000);
 const auto retryGen=retry.expected_retry_generation;
 nowMs=12010;dasAutopilotState4=0;r79ApGateObserveLocked(nowMs);
 dasAutopilotState4=3;lastDASStatusMillis=gearMs=nowMs;r79ApGateObserveLocked(nowMs);
 assert(r79NativeRetryGeneration!=retryGen&&r79NativeRetryAllowed);
 // Fresh renewal after an unobserved validity gap must not revive old work.
 const auto gapGen=r79NativeRetryGeneration;nowMs=14000;lastDASStatusMillis=gearMs=nowMs;
 r79ApGateObserveLocked(nowMs);assert(r79NativeRetryGeneration!=gapGen);
 // Actual AP producer gates retry independently from the opt-in bypass.
 gearMs=nowMs;assert(r79RetryEligible(nowMs));
 r79ApGateConfig.enabled=false;
 for(uint8_t state:{0u,1u,2u,8u,9u,14u,15u}){dasAutopilotState4=state;assert(!r79RetryEligible(nowMs));}
 for(uint8_t state:{3u,4u,5u,6u}){dasAutopilotState4=state;assert(r79RetryEligible(nowMs));}
 dasAutopilotStateValid=false;assert(!r79RetryEligible(nowMs));dasAutopilotStateValid=true;
 lastDASStatusMillis=nowMs-3001;assert(!r79RetryEligible(nowMs));lastDASStatusMillis=nowMs;
 gearMs=nowMs-1001;assert(!r79RetryEligible(nowMs));gearMs=nowMs;
 gearValid=false;assert(!r79RetryEligible(nowMs));gearValid=true;
 gearRaw=TESLA_GEAR_R;assert(!r79RetryEligible(nowMs));gearRaw=TESLA_GEAR_D;
 r79ApGateConfig.enabled=true;r79ApGateConfig.mode=R79_AP_GATE_BLOCK_PURE;r79ApGateObserveLocked(nowMs);
 assert(!r79RetryEligible(nowMs));
 r79ApGateConfig.mode=R79_AP_GATE_DELAY_PURE;r79ApGateSession={};r79ApGateObserveLocked(nowMs);
 assert(!r79RetryEligible(nowMs));nowMs+=2000;lastDASStatusMillis=gearMs=nowMs;r79ApGateObserveLocked(nowMs);
 assert(r79RetryEligible(nowMs));
 r79ApGateConfig.enabled=false;nowMs=UINT32_MAX-100;lastDASStatusMillis=gearMs=nowMs;
 assert(r79RetryEligible(nowMs));nowMs=10;assert(r79RetryEligible(nowMs));
 // Valid timestamp rollover and disabled opt-in gate.
 r79ApGateConfig.enabled=true;
 nowMs=UINT32_MAX-100;lastDASStatusMillis=nowMs;dasAutopilotState4=0;r79ApGateObserveLocked(nowMs);
 assert(r79NativeApDeadlineMs==2899);r79ApGateConfig.enabled=false;
 p4_twai_priority_guard_t bypass{};r79PriorityLimitDeadline(bypass);
 assert(!bypass.permission_deadline_ms&&!bypass.has_deadline);
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'main.cpp').write_text(pre+parts+main)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-I'+str(ROOT),str(p/'main.cpp'),'-o',str(p/'run')],check=True)
 subprocess.run([str(p/'run')],check=True)
print('PASS: actual nonblocking refresh/slices, live AP expiry, revocation, delay and rollover')

# Real permission producer + final guard + adapter + native IRQ. Reuse platform
# doubles only; unlike the generic composition suite the fast AP gate is real.
p=ROOT/'tests/test_r79_ulc_composition_host.py'
t=p.read_text();boundary=t.index('temp=tempfile.TemporaryDirectory()')
ns={'__file__':str(p)}
exec(compile(t[:boundary],str(p),'exec'),ns)
app=ns['app'].split('int main(){')[0]
old='static bool r79FastReactiveGateOpen(uint8_t*){return gate && !canTxAdministrativeHold && twaiReady;}\nstatic void r79PriorityLimitDeadline(p4_twai_priority_guard_t&){}'
assert old in app
permission=r'''
static bool r79PostApOffHold=false;
static R79ApGateConfigPure r79ApGateConfig={true,R79_AP_GATE_BLOCK_PURE,2};
static R79ApGateSessionPure r79ApGateSession{};
static R79ManualSuppressionPure r79ManualSuppression{};
static bool gateSummoning=false,r79NativeApAllowed=false;
static volatile uint32_t r79NativeApDeadlineMs=0;
static constexpr uint32_t R79_AP_DAS_FRESH_MS=3000;
static volatile uint32_t r79NativeRetryGeneration=1,r79NativeRetryDeadlineMs=0;
static bool r79NativeRetryAllowed=false;
[[maybe_unused]] static constexpr uint32_t SUMMON_GEAR_FRESH_MS=1000;
static uint32_t gearMs=1000;static uint8_t gearRaw=TESLA_GEAR_D;
static bool gearValid=true;
static SummonGearDecisionPure summonFreshGearDecisionLocked(uint32_t now){return {gearValid&&(uint32_t)(now-gearMs)<=1000,false,SUMMON_GEAR_118,gearMs};}
static bool r79FreshGearRawLocked(uint32_t now,uint8_t&raw){raw=gearRaw;return summonFreshGearDecisionLocked(now).valid;}
static uint8_t summonPriorityStateLocked(uint32_t now){return summonTxPriorityStatePure(summonFreshGearDecisionLocked(now).valid,gearRaw,false,false);}
'''
permission+='\n'.join(fn(sig) for sig in ('static bool r79ApDasFreshLocked(', 'static R79ApGateDecisionPure r79ApGateDecisionLocked(', 'static void r79NativeApPermissionPublishLocked(', 'static void r79ApGateObserveLocked(', 'static void r79PriorityLimitDeadline(', 'static bool r79FastReactiveGateOpen(uint8_t *diagnosticReason)'))
if extra[0] in s:
 pos=permission.index('static void r79NativeApPermissionPublishLocked(')
 permission=permission[:pos]+'\n'.join(fn(n) for n in extra)+'\n'+permission[pos:]
 # Replace composition fixture's boundary fake with actual producer/capture.
 app=app.replace('static bool r79RetryGuardCapture(p4_twai_priority_guard_t&,uint32_t,const uint32_t* = nullptr){return true;}','')
app=app.replace(old,permission)
main=r'''
int main(){
 twai_obj_t d;twai_hal_context_t h;Queue q,r;
 twai_message_t old={};old.identifier=0x3FD;old.data_length_code=8;old.data[0]=1;old.data[1]=0x11;
 r79FixedApplyBitsPure(old.data,R79_BIT18_STOCK_PURE,false);
 twai_message_t latest=old;latest.data[1]=0x22;
 init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;yl=true;ulcSnoozePending=false;
 dasAutopilotState4=0;lastDASStatusMillis=1000;nowMs=1000;r79ApGateObserveLocked(nowMs);
 normal.identifier=0x111;assert(p4CanSendB(&normal,0)==ESP_OK);
 const auto gen=r79ApGateGeneration;
 assert(r79ApGateTransmitOnce(&old,0,gen)==ESP_OK);
 nowMs=1001;assert(r79ApGateTransmitOnce(&latest,0,gen)==ESP_OK);
 assert(d.tx_msg_count==2&&h.n==1&&q.n==0);
 finish(&d);assert(h.n==2&&h.sent[1].data[1]==0x22);finish(&d);
 // Fresh NON_AP renews a previously admitted frame through the real publisher.
 init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=3999;lastDASStatusMillis=1000;
 r79ApGateObserveLocked(nowMs);assert(p4CanSendB(&normal,0)==ESP_OK);
 assert(r79ApGateTransmitOnce(&old,0,r79ApGateGeneration)==ESP_OK);
 r79ApGateObserveLocked(nowMs);lastDASStatusMillis=3999;r79ApGateObserveLocked(nowMs);
 nowMs=4001;assert(r79FastReactiveGateOpen(nullptr));finish(&d);
 assert(h.n==2&&h.sent[1].header.id==0x3FD);finish(&d);
 // No refresh: expired permission cannot load even if no task observed expiry.
 init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=6998;
 assert(p4CanSendB(&normal,0)==ESP_OK);assert(r79ApGateTransmitOnce(&old,0,r79ApGateGeneration)==ESP_OK);
 nowMs=7000;finish(&d);assert(h.n==1&&d.tx_msg_count==0);
 // Invalid NON_AP observation revokes the old slot; a later valid observation
 // cannot resurrect its older generation before native dispatch.
 init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=8000;lastDASStatusMillis=8000;
 r79ApGateObserveLocked(nowMs);assert(p4CanSendB(&normal,0)==ESP_OK);
 assert(r79ApGateTransmitOnce(&old,0,r79ApGateGeneration)==ESP_OK);
 const auto beforeInvalid=r79ApGateGeneration;
 dasAutopilotState4=15;r79ApGateObserveLocked(nowMs);assert(r79ApGateGeneration!=beforeInvalid);
 dasAutopilotState4=0;lastDASStatusMillis=8001;nowMs=8001;r79ApGateObserveLocked(nowMs);
 assert(r79FastReactiveGateOpen(nullptr));finish(&d);assert(h.n==1);
 // Live permission renewal cannot extend a separate periodic hard deadline.
 init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=9000;lastDASStatusMillis=9000;
 r79ApGateObserveLocked(nowMs);assert(p4CanSendB(&normal,0)==ESP_OK);
 const uint32_t hard=9001;
 assert(r79LabDirectTwaiTransmitOnce(&old,0,&r79Mode1PostMux2Generation,2,r79ApGateGeneration,&hard)==ESP_OK);
 nowMs=9002;lastDASStatusMillis=9002;r79ApGateObserveLocked(nowMs);
 finish(&d);assert(h.n==1);
 // AP-only retry pending in native hardware must expire/revoke even while
 // the opt-in AP gate is bypassed. All general gates intentionally stay open.
 for(unsigned scenario=0;scenario<4;++scenario){
  init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=20000+scenario*5000;
  r79ApGateConfig.enabled=false;dasAutopilotState4=3;gearRaw=TESLA_GEAR_D;
  gearMs=lastDASStatusMillis=nowMs;r79ApGateObserveLocked(nowMs);
  assert(p4CanSendB(&normal,0)==ESP_OK);
  assert(r79LabDirectTwaiTransmitOnce(&old,0,&r79ApGateGeneration,r79ApGateGeneration,r79ApGateGeneration,nullptr,true)==ESP_OK);
  assert(s_p4_priority[0].pending&&h.n==1);
  if(scenario==0){nowMs+=1001;} // no refresh: gear deadline expires
  if(scenario==1){dasAutopilotState4=0;r79ApGateObserveLocked(nowMs);dasAutopilotState4=3;r79ApGateObserveLocked(nowMs);}
  if(scenario==2){nowMs+=1001;gearMs=lastDASStatusMillis=nowMs;r79ApGateObserveLocked(nowMs);} // refresh after gap
  if(scenario==3){gearRaw=TESLA_GEAR_N;r79ApGateObserveLocked(nowMs);gearRaw=TESLA_GEAR_D;r79ApGateObserveLocked(nowMs);}
  finish(&d);assert(h.n==1&&d.tx_msg_count==0&&"invalid AP-only retry must not load");
 }
 puts("PASS: real NON_AP gate/publication -> admission -> native IRQ; latest pending, renewal, expiry, revocation and hard deadline");
}
'''
ns['app']=app+main
exec(compile(t[boundary:],str(p),'exec'),ns)
