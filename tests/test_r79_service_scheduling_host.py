"""Execute production CAN-B RX/service ordering and task creation with fake RTOS/I/O.

Detects draining an entire burst before retries, periodic service ahead of unread
MUX frames, blocking refresh, starvation of PARTY, and inverted YL priorities.
Decoders/transport are boundary fakes; their payload/permission tests are separate.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'can_runtime.h').read_text()
start = source.index('    twai_message_t f = {};', source.index('static void canTaskTwai('))
end = source.index('    // R79 immediate', start)
rx_service = source[start:end]
task_start = source.index('static void canTaskTwai(')
init_start = source.index('  unsigned long lastTwaiStatusMs', task_start)
initialization = source[init_start:source.index('  canTaskDiagnosticsResetPure', init_start)]
tail_end = source.index('\n  }\n}', end)
tail_start = source.rfind('    canTaskDiagnosticsEnterStagePure(', end, tail_end)
scheduler_tail = source[tail_start:tail_end]
start = source.index('static bool recoveryStartCanTasks() {')
startup = source[start:source.index('\n}', start) + 2]
# Any scheduling constants/helpers immediately ahead of CAN-B are production,
# not reimplemented in this harness.
start = source.index('static void canTaskTwai(')
helper_start = source.index('static void r79ServiceCheckpoint(') if 'static void r79ServiceCheckpoint(' in source else source.rfind('\n}', 0, start) + 2
prefix = source[helper_start:start]

code = r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include <deque>
#include <string>
#include <algorithm>
using esp_err_t=int;using BaseType_t=int;using UBaseType_t=unsigned;using TaskHandle_t=void*;
constexpr int ESP_OK=0,ESP_ERR_TIMEOUT=-1,ESP_FAIL=-2,pdPASS=1;
constexpr unsigned TWAI_RX_DRAIN_BUDGET=64;
constexpr int CAN_TASK_STAGE_RECEIVE=1,CAN_TASK_STAGE_PROCESS=2,CAN_TASK_STAGE_SERVICE=3,CAN_TASK_STAGE_DELAY=4;
constexpr int CAN_RX_BUS_VH=0,CAN_TX_FRESH_VH=0,DRIVER_MONITOR_BUS_B=0,VISION_CONTROL_CHASSIS_PURE=0;
constexpr int UI_CHASSIS_CONTROL_ID=0x293,UI_POWERTRAIN_ID=0x334,LEFTSTALK_ID=0x249,
 VCLEFT_SWITCH_ID=0x3C2,DOOR_SWITCH_ID=0x102,VISUAL_DEBUG_ID=0x3F9,DRIVER_ASSIST_ID=0x3F8,TURN_SIGNAL_STALK=1;
struct twai_message_t{uint32_t identifier=0;bool extd=false,rtr=false;uint8_t data_length_code=8,data[8]={};};
struct twai_status_info_t{unsigned msgs_to_rx=0;};
static uint32_t nowMs=1000,lastCanBFrameMs=0,canBLastRxGapMs=0,canBMaxRxGapMs=0,
 canTaskTwaiHeartbeatMs=0,visualDebugRxCount=0,visualDebugLastMs=0,lab3f8FrameRxMs=0,lab3f8FrameRxEpoch=0;
static int canTaskTwaiDiagnostics=0,activeTurnSignalVariant=0,visualBehaviorType=0;
static TaskHandle_t canTaskNativeAHandle=nullptr,canTaskTwaiHandle=nullptr;
static bool canTasksStopping=false,yl=true,refreshAvailable=true,statusAvailable=true,nativeReady=true;
static unsigned processed=0,stepMs=0,serviceStepMs=0,blockingRefreshes=0,refreshes=0,ordinaryServices=0;
static unsigned retryDue=1000,retryIndex=1,inputDone=0,stockObserved=0,yields=0;
static bool r79RetryPending=false;
static uint32_t r79RetryDueMs=0;
struct QuietState{bool pending=false;uint32_t dueMs=0;};
static QuietState r79FixedQuietState;
static int r79LabMux=0;
static unsigned lockDepth=0,nativeChecks=0;
void portENTER_CRITICAL(int*){assert(lockDepth++==0);}
void portEXIT_CRITICAL(int*){assert(--lockDepth==0);}
static void (*beforeReceive)(unsigned)=nullptr;
static bool arriveOnWait=false,receiveError=false,passive=false,stockClaimed=true,checkInputDone=false;
static std::vector<unsigned> receiveWaits;
static std::deque<twai_message_t> queue;
struct Service{unsigned processed,ms,queued;bool periodic;};
static std::vector<Service> services;
struct Task{std::string name;unsigned priority,core;};static std::vector<Task> tasks;
uint32_t millis(){return nowMs;}
uint32_t micros(){return nowMs*1000;}
void vTaskDelay(unsigned ticks){assert(ticks==1);++yields;++nowMs;}
bool activeProfileIsYl(){return yl;}
int p4CanBusB(){return 1;}int p4CanHandleB(){return 1;}
static uint32_t epoch=1,seenEpoch=0;static bool advanceEpochOnService=false;
uint32_t canTxEpochSnapshot(){return epoch;}
void continuousApObserveStock(int,uint16_t,const uint8_t*,uint8_t,uint32_t observedEpoch,uint32_t){seenEpoch=observedEpoch;}
int p4CanReceiveRaw(int,twai_message_t*f,unsigned wait=0){
 if(beforeReceive)beforeReceive(wait);receiveWaits.push_back(wait);if(receiveError)return ESP_FAIL;
 if(queue.empty()&&wait&&arriveOnWait){twai_message_t next;next.identifier=0x123;queue.push_back(next);arriveOnWait=false;}
 if(queue.empty()){nowMs+=wait;return ESP_ERR_TIMEOUT;}*f=queue.front();queue.pop_front();return ESP_OK;
}
int twai_get_status_info_v2(int,twai_status_info_t*s){s->msgs_to_rx=queue.size();return statusAvailable?ESP_OK:ESP_FAIL;}
// Native readiness is a boundary fake; native token/HAL semantics have their
// own driver harness. Unread relevant frames must still defer the runtime.
bool p4_twai_r79_periodic_ready_v2(int){
 ++nativeChecks;assert(lockDepth==0);
 return nativeReady&&std::none_of(queue.begin(),queue.end(),[](const twai_message_t& f){
  return !f.extd&&!f.rtr&&f.identifier==0x3FD&&f.data_length_code==8&&(f.data[0]&7)<=2;
 });
}
void canUsbObserve(int,uint32_t,int,uint8_t,const uint8_t*){++processed;nowMs+=stepMs;}
bool canUsbPassive(){return passive;}
uint8_t readMuxID(const uint8_t*d){return d[0];}
unsigned readBitsLE(const uint8_t*,unsigned,unsigned){return 0;}
bool r79ProcessStockFrame(const twai_message_t&,uint8_t,uint32_t){return stockClaimed;}
void visionControlObserveStock(const twai_message_t&,uint32_t,bool,uint32_t){++stockObserved;}
void p4CanR79InputDone(){++inputDone;if(!passive)assert(stockObserved>=inputDone);}
void refreshSummonState(){++blockingRefreshes;}
bool r79ServiceStateRefreshTry(){++refreshes;return refreshAvailable;}
void r79TransportSliceTick(bool allowPeriodic){if(checkInputDone)assert(inputDone==1);services.push_back({processed,nowMs,unsigned(queue.size()),allowPeriodic});nowMs+=serviceStepMs;if(advanceEpochOnService)++epoch;}
void r79TransportTick(){r79TransportSliceTick(true);}
void driverWindowLabServiceTick(){++ordinaryServices;}
void preheatRuntimeTick(){++ordinaryServices;}
void canTaskNativeA(void*){}void canTaskTwai(void*){}
int xTaskCreatePinnedToCore(void(*)(void*),const char*n,unsigned,void*,unsigned p,TaskHandle_t*h,unsigned c){tasks.push_back({n,p,c});*h=(void*)1;return pdPASS;}
'''
noops = '''canTaskDiagnosticsEnterStagePure visionControlCacheStock
canTaskDiagnosticsPulsePure canTaskDiagnosticsFinishLoopPure canRxObserve preheatRuntimeIngestPhysical canTxMarkFresh
bootCaptureObserveVhFrame researchCaptureObserveVh driverMonitorCaptureObserve
uiAutoLaneChangeObserveAndInjectCanB handlePedalMap334OnCanB handle249OnCanB
handleDriverWindowLab3C2CanB tsl9InputObserveCanB handle102LaneChangeCancel evaluateAutoBlinker
handle280 handle390 nagProcessTsl9Twai399 handle921 handleRoadContext238 countryOverrideObserve238CanB
countryOverrideObserve7ffCanB handle1016 injectDriverAssistControl r79LabObserve3fdMux1
injectTLSSC p4PublishVehicleDiagnosticContext'''.split()
for name in noops:
    code += f'template<typename... T> void {name}(T...){{}}\n'
for name in ('activeProfilePedalMapSupported', 'activeProfileTsl9InputSupported',
             'activeProfileTsl9InputOnBodyCanA', 'activeCanBIsChassis',
             'activeProfileAdvancedEapSupported', 'injectUlcSnooze3fdMux1'):
    code += f'template<typename... T> bool {name}(T...){{return false;}}\n'
code += (prefix + '\nstruct RuntimeScheduler{\n' + initialization +
         '\nvoid run(){\n' + rx_service + scheduler_tail + '\n}};\n' +
         'RuntimeScheduler scheduler;\nvoid productionRxAndService(){scheduler.run();}\n' + startup)
code += r'''
void reset(unsigned n,unsigned ms=0){epoch=1;seenEpoch=0;advanceEpochOnService=false;queue.clear();services.clear();processed=blockingRefreshes=refreshes=ordinaryServices=0;
 scheduler=RuntimeScheduler{};receiveWaits.clear();inputDone=stockObserved=yields=0;
 r79RetryPending=false;r79RetryDueMs=0;r79FixedQuietState={};lockDepth=nativeChecks=serviceStepMs=0;beforeReceive=nullptr;
 arriveOnWait=receiveError=passive=checkInputDone=false;stockClaimed=true;nowMs=1000;stepMs=ms;refreshAvailable=statusAvailable=nativeReady=true;retryDue=1000;retryIndex=1;
 for(unsigned i=0;i<n;++i){twai_message_t f;f.identifier=i%4?0x123:0x3FD;f.data[0]=i%3;queue.push_back(f);}}
int main(){
 // Latest already-queued input must be observed before older due service.
 // Model a contended bounded admission costing2ms, as the real guarded
 // transport regression demonstrates; no wire/RTOS timing is inferred.
 reset(1);r79RetryPending=true;r79RetryDueMs=1000;serviceStepMs=2;
 beforeReceive=[](unsigned){if(!queue.empty())assert(nowMs==1000&&services.empty()&&"queued RX must precede old due retry wait");};
 productionRxAndService();assert(processed==1);
 // Due service can change the authority epoch before a blocking receive.
 // A newly arrived frame must carry that refreshed epoch, not the probe epoch.
 reset(0);r79RetryPending=true;r79RetryDueMs=1000;advanceEpochOnService=true;
 beforeReceive=[](unsigned wait){if(wait){assert(epoch==2);advanceEpochOnService=false;twai_message_t f;f.identifier=0x123;queue.push_back(f);}};
 productionRxAndService();assert(processed==1&&seenEpoch==2);
 // Due retry/quiet work must reach native readiness and refresh before the
 // first one-tick receive, even without incoming frames and across rollover.
 for(bool retry:{false,true})for(uint32_t base:{1000u,UINT32_MAX}){
  reset(0);nowMs=base;r79RetryPending=retry;r79RetryDueMs=base;
  r79FixedQuietState={ !retry,base };
  beforeReceive=[](unsigned wait){if(wait)assert(!services.empty()&&services.front().ms==nowMs&&nativeChecks==1&&"due work must run before blocking RX");};
  productionRxAndService();assert(receiveWaits==std::vector<unsigned>({0,1})&&yields==0);
 }

 // Future reservations do not add an eager checkpoint; snapshots do not
 // change due time/index, and wraparound uses the same signed due comparison.
 for(uint32_t base:{1000u,UINT32_MAX})for(bool pending:{false,true}){
  reset(0);nowMs=base;r79RetryPending=pending;r79RetryDueMs=pending?base+2:base;
  r79FixedQuietState={pending,pending?base+2:base};
  beforeReceive=[](unsigned wait){if(wait)assert(services.empty()&&nativeChecks==0);};
  const auto retryDueBefore=r79RetryDueMs,quietDueBefore=r79FixedQuietState.dueMs;
  productionRxAndService();assert(r79RetryPending==pending&&r79RetryDueMs==retryDueBefore&&r79FixedQuietState.pending==pending&&r79FixedQuietState.dueMs==quietDueBefore);
 }
 // A contended refresh still makes native progress and then blocks exactly
 // once. No immediate retry loop is introduced when due work stays pending.
 reset(0);r79RetryPending=true;r79RetryDueMs=1000;refreshAvailable=false;
 beforeReceive=[](unsigned wait){if(wait)assert(nativeChecks==1&&refreshes==1&&services.empty());};
 productionRxAndService();assert(nativeChecks==2&&refreshes==2&&receiveWaits==std::vector<unsigned>({0,1})&&yields==0);
 reset(0);r79FixedQuietState={true,1000};nativeReady=false;
 beforeReceive=[](unsigned wait){if(wait)assert(services.size()==1&&!services.front().periodic);};
 productionRxAndService();assert(r79FixedQuietState.pending&&r79FixedQuietState.dueMs==1000&&yields==0);
 reset(0);r79RetryPending=true;r79RetryDueMs=1000;receiveError=true;
 productionRxAndService();assert(services.front().ms==1000&&yields==1);
 // Expensive pre-wait work belongs to the 4ms fairness epoch, including wrap.
 for(uint32_t base:{1000u,UINT32_MAX-1u}){
  reset(0);nowMs=base;r79RetryPending=true;r79RetryDueMs=base;serviceStepMs=4;
  beforeReceive=[](unsigned wait){if(wait)for(unsigned i=0;i<20;++i){twai_message_t f;f.identifier=0x123;queue.push_back(f);}};
  productionRxAndService();assert(processed==1&&queue.size()==19&&yields==1);
 }
 // Empty RX waits one bounded tick; no second unconditional sleep follows.
 reset(0);productionRxAndService();
 assert(receiveWaits==std::vector<unsigned>({0,1})&&"idle receive must wait for queue wake");
 assert(yields==0&&nowMs==1001&&services.size()==1);
 // A frame delivered during the first wait is processed in the same batch.
 reset(0);arriveOnWait=true;productionRxAndService();
 assert(processed==1&&queue.empty()&&!arriveOnWait&&yields==0);
 assert(receiveWaits==std::vector<unsigned>({0,1,0}));
 // A failed driver cannot become a higher-priority busy spin.
 reset(0);receiveError=true;productionRxAndService();assert(yields==1);
 // Repeated short batches ending in a zero-wait timeout are still one
 // runnable epoch: PARTY must get an actual yield after four elapsed ms.
 for(uint32_t base:{1000u,UINT32_MAX-1u}){
  reset(0,1);nowMs=base;
  for(unsigned i=0;i<4;++i){twai_message_t f;f.identifier=0x123;queue.push_back(f);productionRxAndService();
   assert(yields==(i==3?1u:0u));}
 }
 // A fourth millisecond reached in a new batch stops that batch too;
 // resetting only the per-batch timer would continue decoding its backlog.
 reset(0,1);
 for(unsigned i=0;i<3;++i){twai_message_t f;queue.push_back(f);productionRxAndService();}
 for(unsigned i=0;i<10;++i){twai_message_t f;queue.push_back(f);}
 productionRxAndService();assert(processed==4&&queue.size()==9&&yields==1);
 // The forced handoff starts a new epoch rather than immediately yielding again.
 queue.clear();queue.push_back(twai_message_t{});productionRxAndService();assert(yields==1);
 // A full first receive timeout resets that epoch because it gave PARTY
 // a blocking opportunity. A subsequent short batch starts a fresh epoch.
 reset(0,1);
 for(unsigned i=0;i<3;++i){twai_message_t f;queue.push_back(f);productionRxAndService();}
 productionRxAndService();
 twai_message_t next;queue.push_back(next);productionRxAndService();assert(yields==0);
 // Native replacement fallback is released only after MUX1 stock processing,
 // including rejected/passive input, and never for malformed or other MUXes.
 reset(0);checkInputDone=true;stockClaimed=false;
 for(unsigned i=0;i<7;++i){twai_message_t f;f.identifier=0x3FD;f.data[0]=1;
  if(i==1)f.extd=true;if(i==2)f.rtr=true;if(i==3)f.data_length_code=7;
  if(i==4)f.data[0]=2;if(i==5)f.identifier=0x123;if(i==6)f.data_length_code=9;
  queue.push_back(f);}
 productionRxAndService();assert(inputDone==1&&stockObserved==1);
 reset(0);passive=checkInputDone=true;next.identifier=0x3FD;next.data[0]=1;queue.push_back(next);
 productionRxAndService();assert(inputDone==1&&stockObserved==0);
 reset(40);productionRxAndService();
 assert(!services.empty()&&services.front().processed<=8&&"due immediate retries must run within eight processed RX frames");
 assert(processed==40&&queue.empty());
 assert(services.back().periodic&&services.back().queued==0);
 assert(blockingRefreshes==0&&refreshes>0&&ordinaryServices==2);
 reset(65);productionRxAndService();
 assert(processed<=64&&processed+queue.size()==65);
 for(auto s:services)assert(!s.periodic&&"unread new-cycle MUX frames must precede old periodic service");
 productionRxAndService();assert(processed==65&&queue.empty()&&services.back().periodic);
 reset(64);productionRxAndService();assert(processed==64&&services.back().periodic&&yields==1);
 reset(40,1);productionRxAndService();
 assert(!services.empty()&&services.front().processed==1&&"slow decoding must service retry after 1ms");
 assert(processed<=4&&processed+queue.size()==40&&yields==1&&"bound higher-priority VEHICLE RX work so PARTY runs");
 reset(40);refreshAvailable=false;productionRxAndService();
 assert(services.empty()&&blockingRefreshes==0&&retryDue==1000&&retryIndex==1&&ordinaryServices==2);
 reset(65);nativeReady=false;productionRxAndService();
 for(auto s:services)assert(!s.periodic);
 // Unrelated RX backlog must not suppress the due periodic service.
 reset(130);for(auto& f:queue)f.identifier=0x123;productionRxAndService();
 assert(processed==64&&queue.size()==66&&services.front().periodic);
 assert(services.front().processed<=8&&services.back().periodic);
 // Missing/unseen native boundary blocks even if software RX is empty.
 reset(0);nativeReady=false;productionRxAndService();assert(!services.back().periodic);
 reset(0);productionRxAndService();assert(services.size()==1&&services[0].periodic);
 reset(40,1);nowMs=UINT32_MAX-1;productionRxAndService();assert(processed<=4&&services.front().processed==1);
 for(bool profile:{false,true}){yl=profile;tasks.clear();assert(recoveryStartCanTasks());
 assert(tasks.size()==2&&tasks[0].name=="canA"&&tasks[1].name=="canB");
 assert(tasks[0].priority==5&&tasks[1].priority==(profile?6u:4u));
 assert(tasks[0].core==1&&tasks[1].core==1);}
}
'''
# Execute the actual native-A iteration through PARTY decoding and service,
# together with the production extra-controller drain. Hardware/decoders are
# deterministic fakes; no generated replacement of task ordering is used.
party_start = source.index('    P4_CAN_DIAG_SERVICE(p4CanBusA());', source.index('static void canTaskNativeA('))
party_end = source.index('    // ── STATUS CHECK / RECOVERY', party_start)
party_iteration = source[party_start:party_end]
extra_start = source.index('static void p4CanDrainExtra()')
extra_end = source.index('static void p4CanServiceNativeStatus(', extra_start)
party_code = r'''
#include <cassert>
#include <cstdint>
#include <deque>
#include <vector>
#include <algorithm>
using esp_err_t=int;
constexpr int ESP_OK=0,ESP_ERR_TIMEOUT=-1,ESP_FAIL=-2;
constexpr unsigned NATIVE_A_RX_BUDGET=32;
constexpr int CAN_TASK_STAGE_RECEIVE=1,CAN_TASK_STAGE_PROCESS=2,CAN_TASK_STAGE_SERVICE=3;
constexpr int CAN_RX_BUS_PARTY=1,CAN_TX_FRESH_PARTY=1,DRIVER_MONITOR_BUS_A=1,RESEARCH_CAPTURE_BUS_EXTRA=2;
constexpr int UI_CHASSIS_CONTROL_ID=0x293,UI_POWERTRAIN_ID=0x334,LEFTSTALK_ID=0x249,
 VCLEFT_SWITCH_ID=0x3C2,DOOR_SWITCH_ID=0x102,VISUAL_DEBUG_ID=0x3F9,TURN_SIGNAL_STALK=1,TURN_SIGNAL_STALKLESS=2;
struct CanFrame{uint32_t can_id=0x123;uint8_t can_dlc=8,data[8]={},bus=0;};
static uint32_t nowMs=1000,extraStepMs=0,partyStepMs=0;
static unsigned long lastCanFrameMs=0,lastCanAFrameMs=0;
static unsigned nativeARxCount=0,visualDebugRxCount=0,visualDebugLastMs=0,extraReads=0,partyReads=0;
static int canTaskNativeADiagnostics=0,canARxDiagnostics=0,activeTurnSignalVariant=0,visualBehaviorType=0;
static bool yl=true,passive=false,extraError=false,partyError=false,p4CanExtraFresh=false,p4CanOnline[3]={true,true,true};
static std::deque<CanFrame> partyQueue,extraQueue;
// 10/20 diagnostics, 11 PARTY RX, 21 extra RX, 12 PARTY service.
static std::vector<int> events;
uint32_t millis(){return nowMs;}
bool activeProfileIsYl(){return yl;}bool canUsbPassive(){return passive;}
int p4CanBusA(){return 0;}int p4CanBusExtra(){return 2;}
void P4_CAN_DIAG_SERVICE(int bus){events.push_back(bus==0?10:20);}
int p4CanReadFrame(int,CanFrame*f){++extraReads;if(extraError)return ESP_FAIL;
 if(extraQueue.empty())return ESP_ERR_TIMEOUT;*f=extraQueue.front();extraQueue.pop_front();return ESP_OK;}
int p4CanReadFrameA(CanFrame*f){++partyReads;if(partyError)return ESP_FAIL;
 if(partyQueue.empty())return ESP_ERR_TIMEOUT;*f=partyQueue.front();partyQueue.pop_front();return ESP_OK;}
void canUsbObserve(int bus,uint32_t,int,uint8_t,const uint8_t*){events.push_back(bus==0?11:21);nowMs+=bus==0?partyStepMs:extraStepMs;}
static uint32_t epoch=1,seenEpoch=0;static bool advanceEpochOnService=false;
uint32_t canTxEpochSnapshot(){return epoch;}
void continuousApObserveStock(int,uint16_t,const uint8_t*,uint8_t,uint32_t observedEpoch,uint32_t){seenEpoch=observedEpoch;}
constexpr uint8_t canARxReadBatchBudgetPure(){return 1;}
unsigned readBitsLE(const uint8_t*,unsigned,unsigned){return 0;}
bool activeCanAIsParty(){return true;}
bool activeCanAIsBody(){return false;}
namespace ContApRoute {constexpr int BodyA=0;}
void continuousApService(int){events.push_back(12);}
'''
for name in '''canTaskDiagnosticsEnterStagePure canARxDiagnosticsCompleteLoopPure
canRxObserve preheatRuntimeIngestPhysical canTxMarkFresh continuousApObserveStock
bootCaptureObservePartyFrame researchCaptureObserveParty researchCaptureObserve driverMonitorCaptureObserve
uiAutoLaneChangeObserveAndInjectCanA countryOverrideObserve7ffCanA countryOverrideObserve238CanA
visionControlObserveBody nagProcessNativeAFrame evaluateAutoBlinker nagProcessTsl9NativeA
handlePedalMap334OnCanA handle249OnCanA handle3C2OnCanA tsl9InputObserveCanA handle102LaneChangeCancel
tsl9InputServiceCanA'''.split():
    party_code += f'template<typename... T> void {name}(T...){{}}\n'
for name in ('nagTsl9Body39BSelected','activeProfilePedalMapSupported','activeProfileTsl9InputOnBodyCanA'):
    party_code += f'bool {name}(){{return false;}}\n'
party_code += source[extra_start:extra_end] + '\nvoid iteration(){\n' + party_iteration + '\n}\n'
party_code += r'''
void reset(bool profile,unsigned n=100,unsigned step=0){yl=profile;nowMs=1000;extraStepMs=step;partyStepMs=0;
 passive=extraError=partyError=p4CanExtraFresh=false;extraReads=partyReads=nativeARxCount=0;
 p4CanOnline[2]=true;events.clear();partyQueue.clear();extraQueue.clear();
 for(unsigned i=0;i<n;++i){CanFrame f;f.bus=0;partyQueue.push_back(f);f.bus=2;extraQueue.push_back(f);}}
int first(int e){auto it=std::find(events.begin(),events.end(),e);assert(it!=events.end());return it-events.begin();}
int main(){
 for(bool profile:{false,true}){
  reset(profile);iteration();
  assert(nativeARxCount==32&&partyQueue.size()==68);
  assert(extraQueue.size()==(profile?92u:68u));
  assert(profile?(first(11)<first(20)&&first(12)<first(20)):(first(20)<first(11)));
  assert(profile?(first(11)<first(21)):(first(21)<first(11)));
  assert(p4CanExtraFresh);
  iteration();assert(nativeARxCount==64&&extraQueue.size()==(profile?84u:36u));
  // Each loop gives both inputs progress under saturation; no repeated drain.
  assert(extraReads==(profile?16u:64u));
 }
 // Cooperative 1ms BODY limit covers callbacks, flagged frames and rollover.
 for(uint32_t base:{1000u,UINT32_MAX})for(uint32_t flags:{0u,0x80000000u,0x40000000u,0xc0000000u}){
  reset(true,100,1);nowMs=base;for(auto& f:extraQueue)f.can_id|=flags;
  iteration();assert(extraReads==1&&extraQueue.size()==99&&nativeARxCount==32);
  reset(true);for(auto& f:extraQueue)f.can_id|=flags;
  iteration();assert(extraReads==8&&extraQueue.size()==92&&nativeARxCount==32);
 }
 // Non-YL retains the original 32-frame limit, even for slow callbacks.
 reset(false,100,1);iteration();assert(extraReads==32&&extraQueue.size()==68);
 reset(true,0);iteration();assert(extraReads==1&&partyReads==1&&!p4CanExtraFresh);
 reset(true);extraError=true;iteration();assert(nativeARxCount==32&&extraReads==1&&!p4CanExtraFresh);
 reset(true);partyError=true;iteration();assert(nativeARxCount==0&&extraReads==8&&p4CanExtraFresh);
 reset(true);p4CanOnline[2]=false;iteration();assert(nativeARxCount==32&&!p4CanExtraFresh);
 reset(true);passive=true;iteration();assert(nativeARxCount==32&&extraReads==8);
}
'''

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'scheduling.cpp'
    binary = Path(td) / 'scheduling'
    path.write_text(code)
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-function', '-Wno-unused-variable',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    path.write_text(party_code)
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-function', '-Wno-unused-variable',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
# The actual scheduler tail is executed above; retain early fast-path ordering.
task = source[source.index('static void canTaskTwai('):source.index('static inline bool recoveryFresh(')]
assert task.index('r79ProcessStockFrame(') < task.index('researchCaptureObserveVh(')
print('PASS: production pre-wait due/refresh/MUX/fairness, RX wake/error, YL PARTY-before-BODY 8-frame/1ms progress, non-YL 32-frame ordering, rollover and RTOS priorities')
