"""Production MUX1 composition through actual native priority admission and dispatch."""
import ast, pathlib, subprocess, tempfile, os
from test_s3xy_pairing_host import source_block
root=pathlib.Path(__file__).resolve().parents[1]
p=root/'tests/test_p4_twai_native_priority_host.py'
nodes=[]
for n in ast.parse(p.read_text()).body:
 if isinstance(n,ast.With):break
 nodes.append(n)
ns={'__file__':str(p)}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
native='#include <initializer_list>\n'+ns['fixture'].split('int main(void) {')[0]
native=native.replace('bool extd,rtr,ss,self,dlc_non_comp;','bool extd,rtr,ss,self,dlc_non_comp; uint32_t flags;')
for dec in ('void diagFakeEnter(void)','void diagFakeExit(void)','int64_t esp_timer_get_time(void)'):
 native=native.replace(dec,'extern "C" '+dec)
# Keep pre-implementation RED executable; this fallback deliberately retains
# the old FIFO behavior and is unused once the native API exists.
if 'p4_twai_transmit_mux1_now_v2(' not in native:
 native+='\nstatic esp_err_t p4_twai_transmit_mux1_now_v2(twai_handle_t h,const twai_message_t*m){return twai_transmit_v2(h,m,0); }\n'
src=(root/'vehicle_logic.h').read_text()
def fn(s):
 start=src.rindex(s)
 return src[start:src.index('\n}',start)+2]
barrier_source=(root/'p4can_core_state.h').read_text()
barrier_pure=barrier_source[barrier_source.index('struct CanTxBarrierState {'):barrier_source.index('// BEGIN HOST-TESTABLE LOGIC')]
barrier_pure+=source_block(barrier_source,'static inline bool canTxBarrierAllowsMaskedPure(').replace('canTxBarrierAllowsMaskedPure(', 'allowsMasked(')
app=r'''
#include "r79_fixed_policy_pure.h"
#include "r79_timing_capture_pure.h"
#include "runtime_gate_pure.h"
#include "summon_state_pure.h"
'''+'\nnamespace epoch_policy {\n'+barrier_pure+'\n}\nusing epoch_policy::CanTxBarrierState;\n'+r'''
static twai_handle_t testDriver;
static twai_handle_t p4CanHandles[3];
static unsigned p4CanTxAccepted[3],p4CanTxRejected[3],diagBegins,diagEnds,timingBegins,timingEnds,diagRejected,timingRejected;
static bool allRunning=true;
static bool yl=false;
static bool activeProfileIsYl(){return yl;}
static bool p4CanOnline[3]={true,true,true};
static uint8_t p4CanBusA(){return 2;}
static bool p4CanAllRunning(){return allRunning;}
#define P4_CAN_DIAG_TX_BEGIN(bus,f,source) (++diagBegins)
#define P4_CAN_DIAG_TX_END(bus,token,f,err,source) ((void)(token),++diagEnds)
#define P4_CAN_DIAG_TX(bus,f,err,called,source) (++diagRejected)
#define P4_R79_TIMING_TX_BEGIN(bus,f,wait) (++timingBegins)
#define P4_R79_TIMING_TX_END(token,f,err,called) ((void)(token),++timingEnds)
#define P4_R79_TIMING_GATE_REASON(bus,f,wait,err,reason) (++timingRejected)
static int barrier=1,*canTxBarrierMutex=&barrier,stateMux=0,ulcSnoozeMux=0;
static bool canTxAdministrativeHold=false,twaiReady=true,barrierLocked=false,barrierAvailable=true;
static unsigned reentrantTakes=0;
static volatile uint32_t r79ApGateGeneration=1;
static bool dasAutopilotStateValid=true;static uint8_t dasAutopilotState4=5;
static uint32_t lastDASStatusMillis=10;
static bool ulcSnoozePending=true;static uint32_t ulcSnoozeExpireMs=1000;
static unsigned ulcSnoozeTxFail=0,ulcSnoozeTxOk=0,sumTxFail=0,sumTxOk=0;
static int activeVehicleProfile=1,activeVehicleTopology=1;
static CanTxBarrierState canTxBarrierState={1,3};
static constexpr uint8_t CAN_TX_FRESH_BOTH=3,VISION_CONTROL_CHASSIS_PURE=0;
static constexpr uint32_t VISION_CONTROL_FRESH_MS_PURE=250;
static uint32_t millis(){return nowMs;}
static bool getBit(const uint8_t*d,int b){return(d[b/8]>>(b%8))&1;}
static void setBit(uint8_t*d,int b,bool v){if(v)d[b/8]|=1<<(b%8);else d[b/8]&=~(1<<(b%8));}
static uint8_t readMuxID(const uint8_t*d){return d[0]&7;}
static int xSemaphoreTake(int*,int){if(barrierLocked){++reentrantTakes;return pdFALSE;}if(!barrierAvailable)return pdFALSE;barrierLocked=true;return pdTRUE;}
static void xSemaphoreGive(int*){assert(barrierLocked);barrierLocked=false;}
static bool vehicleProfileTopologyValid(int,int){return true;}
static bool canTxBarrierAllowsMaskedPure(const CanTxBarrierState&,uint32_t,uint8_t);
static bool nonSummon=true, fresh=true, gate=true, workPending=false;
static bool twaiNonSummonAdmissionOpen(){return nonSummon;} // Drive/NOA -> SUMMON_PRIORITY_NORMAL
static uint32_t canTxEpochSnapshot(){return 1;}
static uint8_t p4CanBusB(){return 0;}
static p4_twai_rx_metadata_t p4CanMux1Origin[3]={};
static uint32_t p4CanReadinessMask(){return 15;}
static bool canTxBarrierAllowsMaskedPure(const CanTxBarrierState&s,uint32_t epoch,uint8_t mask){return fresh&&epoch_policy::allowsMasked(s,epoch,mask);}
static bool visionControlApplyFinal(uint8_t*d,int){setBit(d,40,true);return true;}
static bool r79DmsApplyFinal(uint8_t*d){setBit(d,43,false);return true;}
static void visionControlRecordTx(bool,int,bool){}
static void canBTraceRecordTx(const twai_message_t*,esp_err_t){}
static void p4R79TimingGateRejected(uint8_t,const twai_message_t*,uint32_t,int32_t,uint8_t,uint32_t){}

'''
app=app.replace('static uint32_t canTxEpochSnapshot(){return 1;}',source_block((root/'can_core.h').read_text(),'static uint32_t canTxEpochSnapshot('))
adapter=(root/'p4_can.h').read_text()
for name in ('static esp_err_t p4CanSendB(', 'static esp_err_t p4CanSendR79B(', 'static esp_err_t p4CanSendMux1B('):
 if name in adapter:
  start=adapter.index(name)
  app+=adapter[start:adapter.index('\n}',start)+2]+'\n'
app+=r'''
static volatile uint32_t r79Mode1PostMux2Generation=2;
static uint32_t r79ApGateGenerationSnapshot(){return r79ApGateGeneration;}
static bool r79RetryEligible(uint32_t){return gate;}
static bool r79RetryGuardCapture(p4_twai_priority_guard_t&,uint32_t,const uint32_t* = nullptr){return true;}
static bool r79FastReactiveGateOpen(uint8_t*){return gate && !canTxAdministrativeHold && twaiReady;}
static void r79PriorityLimitDeadline(p4_twai_priority_guard_t&){}
static uint32_t canTxCancellationGenerationSnapshot(const volatile uint32_t*g){return *g;}

static bool r79DmsWorkPendingSnapshot(){return workPending;}
'''
app+='\n'.join(fn(s) for s in ('static bool autoBlinkerNOAGateOpen(', 'static bool ulcSnoozeRequestActive(', 'static void ulcSnoozeFinishRequest(', 'static bool ulcSnoozeApplyFinal(', 'static void ulcSnoozeRecordFinal(', 'static esp_err_t mux1DisplayTransmit(', 'static bool injectUlcSnooze3fdMux1(', 'static esp_err_t r79ApGateTransmitOnce(', 'static esp_err_t r79LabDirectTwaiTransmitOnce(') if s in src)
# Exercise both real application input entries through the final native owner.
# BLE delivery and non-cancellation turn-signal scheduling remain platform seams.
app+=r'''
#include "auto_blinker_pure.h"
static int blinkAMux=0;
static uint32_t visualDebugLastMs=0,autoRequestLastSeenMs=0,oneShotUntil=0,oneShotReleaseAt=0;
static uint8_t blinkACancelPauseSeconds=30,lastReqDir=0,oneShotSource=0;
static int oneShotTurn=0,activeTurn=0;
static bool oneShotDirect=false,doorButtonPressed=false,doorOpenCancelEnabled=true;
static AutoBlinkerCancelPauseStatePure autoBlinkerCancelPauseState{};
static constexpr int STALK_IDLE=0,S3XY_LOG_INFO=1;
static uint32_t ulcSnoozeLastActionMs=0,ulcSnoozeAccepted=0,ulcSnoozeBlocked=0;
static uint8_t ulcSnoozeLastDir=0;static char ulcSnoozeLastResult[64]={};
static void autoBlinkerClearPendingLocked(){}
static void blinkerTxClearPendingSourceLocked(int){}
static void s3xyLogPush(int,const char*){}
static bool activeProfileBodyControlsSupported(){return false;}
'''
for name in ('AUTO_BLINKER_CANCEL_SOURCE_S3XY','AUTO_BLINKER_CANCEL_SOURCE_DOOR'):
 app+=next(line for line in src.splitlines() if line.startswith('static constexpr uint8_t '+name))+'\n'
app+=next(line for line in src.splitlines() if line.startswith('static constexpr uint32_t ULC_REQUEST_FRESH_MS'))+'\n'
app+=next(line for line in (root/'s3xy_ble.h').read_text().splitlines() if line.startswith('static constexpr uint32_t ULC_SNOOZE_REQUEST_TIMEOUT_MS'))+'\n'
app+='\n'.join(fn(sig) for sig in ('static void ulcSnoozeSetResult(', 'static AutoBlinkerCancelActionPure handleAutoBlinkerCancelToggle(', 'static void handleS3xySingleAction(', 'static void handle102LaneChangeCancel('))
app+=r'''
static void cancelControl(bool door,bool pressed=true){
 if(door){uint8_t input[4]={};input[3]=pressed?0x80:0;handle102LaneChangeCancel(input,4);}
 else if(pressed)handleS3xySingleAction();
}
'''
runtime=(root/'can_runtime.h').read_text()
line=next(x.strip() for x in runtime.splitlines() if 'const bool ulcCloneClaimed =' in x)
app+='\nstatic bool lateStock(const twai_message_t&f,bool mux1StockClaimed){'+line+'return ulcCloneClaimed;}\n'
app+=r'''
static void request(){ulcSnoozePending=true;ulcSnoozeExpireMs=nowMs+1000;}
static void composed(const twai_hal_frame_t&f){
 assert(f.header.id==0x3FD);assert(!getBit(f.data,18)&&!getBit(f.data,19)&&getBit(f.data,47));
 assert(getBit(f.data,36)&&getBit(f.data,40)&&!getBit(f.data,43));
}
int main(){
 twai_obj_t d;twai_hal_context_t h;Queue q,r;
 twai_message_t stock={};stock.identifier=0x3FD;stock.data_length_code=8;stock.data[0]=1;stock.data[2]=0x0c;setBit(stock.data,43,true);
 twai_message_t r79=stock;r79FixedApplyBitsPure(r79.data,R79_BIT18_FORCE_0_PURE,false);
 // Real final guard -> adapter -> native slot -> ISR dispatch with BODY down.
 // R79 overtakes an ordinary queued frame; the already active frame is retained.
 init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;request();
 normal.identifier=0x111;assert(p4CanSendB(&normal,0)==ESP_OK);
 normal.identifier=0x222;assert(p4CanSendB(&normal,0)==ESP_OK);
 yl=true;p4CanOnline[1]=false;allRunning=false;
 assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK&&q.n==1&&h.n==1);
 assert(p4CanSendB(&normal,0)==ESP_ERR_INVALID_STATE);
 finish(&d);composed(h.sent[1]);assert(q.n==1);
 finish(&d);assert(h.sent[2].header.id==0x222);finish(&d);
 assert(q.n==0&&d.tx_msg_count==0);
 const unsigned isolatedLoads=h.n;
 p4CanOnline[2]=false;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_ERR_INVALID_STATE);p4CanOnline[2]=true;
 gate=false;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_ERR_INVALID_STATE);gate=true;
 canTxAdministrativeHold=true;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_ERR_INVALID_STATE);canTxAdministrativeHold=false;
 d.state=TWAI_STATE_BUS_OFF;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_ERR_INVALID_STATE);
 assert(h.n==isolatedLoads);
 yl=false;p4CanOnline[1]=true;allRunning=true;
 for(bool busy:{false,true}){
  init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;request();
  if(busy){assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);}
  assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);
  assert(!lateStock(stock,true));assert(!ulcSnoozePending);
  if(busy){assert(q.n==1);finish(&d);}
  composed(h.sent[busy?1:0]);assert(q.n==(busy?1u:0u));
  finish(&d);if(busy)finish(&d);
 }
 // Busy ordinary MUX1 never becomes a stale FIFO tail, even before R79 admission.
 init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;request();
 normal.identifier=0x111;assert(p4CanSendB(&normal,0)==ESP_OK);
 normal.identifier=0x222;assert(p4CanSendB(&normal,0)==ESP_OK);
 const auto queued=q.f[0];const unsigned failedBefore=ulcSnoozeTxFail,rejectedBefore=p4CanTxRejected[0];
 assert(lateStock(stock,false));
 assert(ulcSnoozePending && "busy standalone ULC must retain its request");
 assert(ulcSnoozeTxFail==failedBefore+1 && p4CanTxRejected[0]==rejectedBefore+1);
 assert(q.n==1 && memcmp(&q.f[0],&queued,sizeof(queued))==0 && h.n==1);
 assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);assert(!ulcSnoozePending && q.n==1);
 finish(&d);composed(h.sent[1]);finish(&d);assert(h.sent[2].header.id==0x222);finish(&d);
 assert(h.n==3 && d.tx_msg_count==0 && q.n==0);
 // Without R79, retry only a new stock payload after TX becomes idle.
 init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;request();
 assert(p4CanSendB(&normal,0)==ESP_OK);
 assert(lateStock(stock,false));assert(ulcSnoozePending && q.n==0);
 finish(&d);assert(h.n==1 && d.tx_msg_count==0 && ulcSnoozePending);
 twai_message_t latest=stock;latest.data[1]=0xA6;latest.data[6]=0x5C;
 assert(lateStock(latest,false));assert(!ulcSnoozePending);
 assert(h.n==2 && h.sent[1].data[1]==0xA6 && h.sent[1].data[6]==0x5C);
 assert(getBit(h.sent[1].data,18)&&getBit(h.sent[1].data,36)&&getBit(h.sent[1].data,40)&&!getBit(h.sent[1].data,43));finish(&d);
 // DMS/vision-only clones also drop when busy and recompose on the next stock.
 assert(p4CanSendB(&normal,0)==ESP_OK);const unsigned overlayBefore=h.n;
 assert(mux1DisplayTransmit(&stock,1,3,true)==ESP_ERR_TIMEOUT);
 assert(q.n==0 && !ulcSnoozePending);finish(&d);assert(h.n==overlayBefore);
 latest.data[1]=0xB7;
 assert(mux1DisplayTransmit(&latest,1,3,true)==ESP_OK);
 assert(h.sent[h.n-1].data[1]==0xB7 && getBit(h.sent[h.n-1].data,40) && !getBit(h.sent[h.n-1].data,43));
 assert(!getBit(h.sent[h.n-1].data,36));finish(&d);
 const unsigned beforeReadiness=h.n;
 // Readiness rejection shares adapter diagnostics and cannot consume ULC or load HAL.
 request();allRunning=false;
 const unsigned beforeBegin=diagBegins,beforeRejected=diagRejected,beforeTimingRejected=timingRejected;
 assert(mux1DisplayTransmit(&latest,1,3,false)==ESP_ERR_INVALID_STATE);
 assert(ulcSnoozePending && h.n==beforeReadiness && diagBegins==beforeBegin);
 assert(diagRejected==beforeRejected+1 && timingRejected==beforeTimingRejected+1);
 allRunning=true;assert(lateStock(latest,false));assert(!ulcSnoozePending);finish(&d);
 assert(diagBegins==diagEnds && timingBegins==timingEnds);
 // Busy rejection does not extend the existing one-shot lifetime.
 init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;request();
 assert(p4CanSendB(&normal,0)==ESP_OK);assert(lateStock(stock,false));
 assert(ulcSnoozePending && q.n==0);nowMs=ulcSnoozeExpireMs;
 finish(&d);assert(!lateStock(latest,false));
 assert(!ulcSnoozePending && h.n==1 && q.n==0 && d.tx_msg_count==0);
 // A new ULC may replace plain pending R79, then protects the accepted one-shot.
 // A further one-shot remains pending until the protected frame dispatches.
 init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 ulcSnoozePending=false;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);request();
 assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);assert(!ulcSnoozePending);request();
 assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_ERR_TIMEOUT);assert(ulcSnoozePending);
 const unsigned beforePending=h.n;
 assert(mux1DisplayTransmit(&stock,1,3,false)==ESP_ERR_TIMEOUT);
 assert(ulcSnoozePending && q.n==0 && h.n==beforePending);
 assert(!lateStock(stock,true));finish(&d);composed(h.sent[1]);finish(&d);
 assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);assert(!ulcSnoozePending);composed(h.sent[2]);finish(&d);
 // Inactive R79 retains ordinary standalone ULC, with vision and DMS overlays.
 request();assert(lateStock(stock,false));assert(!ulcSnoozePending);assert(getBit(h.sent[3].data,36)&&getBit(h.sent[3].data,18)&&getBit(h.sent[3].data,40)&&!getBit(h.sent[3].data,43));finish(&d);
 request();workPending=true;assert(!lateStock(stock,false));assert(ulcSnoozePending);workPending=false;
 // Rejected authorization and periodic cancellation never consume the request.
 gate=false;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_ERR_INVALID_STATE);assert(ulcSnoozePending);gate=true;
 assert(r79LabDirectTwaiTransmitOnce(&r79,0,&r79Mode1PostMux2Generation,1,1)==ESP_ERR_INVALID_STATE);assert(ulcSnoozePending);
 assert(r79LabDirectTwaiTransmitOnce(&r79,0,&r79Mode1PostMux2Generation,2,1)==ESP_OK);composed(h.sent[4]);assert(!ulcSnoozePending);finish(&d);
 // ULC requires its own NOA, both-bus freshness and non-Summon admission.
 for(int blocked=0;blocked<3;++blocked){request();if(blocked==0)dasAutopilotState4=3;if(blocked==1)fresh=false;if(blocked==2)nonSummon=false;
  assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);assert(ulcSnoozePending&&!getBit(h.sent[h.n-1].data,36));finish(&d);
  dasAutopilotState4=5;fresh=nonSummon=true;}
 // Mode1 STOCK bit18 policy uses the same final owner.
 request();twai_message_t stockPolicy=stock;r79FixedApplyBitsPure(stockPolicy.data,R79_BIT18_STOCK_PURE,false);
 assert(r79ApGateTransmitOnce(&stockPolicy,0,1)==ESP_OK);assert(getBit(h.sent[h.n-1].data,18)&&!getBit(h.sent[h.n-1].data,19)&&getBit(h.sent[h.n-1].data,36)&&getBit(h.sent[h.n-1].data,47));finish(&d);
 // Failed ordinary admission retains ULC for a later allowed stock frame.
 request();fresh=false;assert(lateStock(stock,false));assert(ulcSnoozePending);fresh=true;
 assert(lateStock(stock,false));assert(!ulcSnoozePending);finish(&d);
 // Existing display/DMS owner also composes ULC; no second stock clone.
 request();assert(mux1DisplayTransmit(&stock,1,3,false)==ESP_OK);assert(!lateStock(stock,true));assert(!ulcSnoozePending);assert(getBit(h.sent[h.n-1].data,36));finish(&d);
 // One-shot ULC does not latch bit36 into a later periodic owner. Stock truth remains intact.
 for(bool stockBit18:{false,true}){
  const twai_message_t &packet=stockBit18?stockPolicy:r79;
  request();assert(r79ApGateTransmitOnce(&packet,0,1)==ESP_OK);assert(getBit(h.sent[h.n-1].data,36));finish(&d);
  assert(r79LabDirectTwaiTransmitOnce(&packet,0,&r79Mode1PostMux2Generation,2,1)==ESP_OK);
  assert(!getBit(h.sent[h.n-1].data,36));finish(&d);
 }
 twai_message_t alreadySnoozed=r79;setBit(alreadySnoozed.data,36,true);
 assert(r79ApGateTransmitOnce(&alreadySnoozed,0,1)==ESP_OK);assert(getBit(h.sent[h.n-1].data,36));finish(&d);
 nowMs=UINT32_MAX-5;request();assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);composed(h.sent[h.n-1]);finish(&d);
 request();nowMs=ulcSnoozeExpireMs;assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);assert(!getBit(h.sent[h.n-1].data,36));finish(&d);
 // Door and S3XY application entries arm the same one-shot; each final owner
 // transmits bit36 once, including contention/native pending. Repeat button
 // use resumes Auto Blinker without sending another snooze.
 for(bool door:{false,true})for(unsigned owner=0;owner<4;++owner)for(bool busy:{false,true}){
  init(&d,&h,&q,&r,0);testDriver=&d;p4CanHandles[0]=&d;yl=true;
  nowMs=lastDASStatusMillis=visualDebugLastMs=1000;dasAutopilotStateValid=true;dasAutopilotState4=5;
  autoBlinkerCancelPauseState={};doorButtonPressed=false;doorOpenCancelEnabled=true;
  ulcSnoozePending=false;gate=nonSummon=fresh=true;workPending=false;
  canTxBarrierState={1,CAN_TX_FRESH_BOTH};barrierAvailable=true;
  const auto accepted=ulcSnoozeAccepted;cancelControl(door);
  assert(ulcSnoozePending&&autoBlinkerCancelPauseState.active&&ulcSnoozeAccepted==accepted+1);
  if(door){cancelControl(true);assert(ulcSnoozeAccepted==accepted+1&&autoBlinkerCancelPauseState.active);}
  if(busy)assert(p4CanSendB(&normal,0)==ESP_OK);
  auto sendOwner=[&]()->esp_err_t{
   if(owner==0){assert(lateStock(stock,false));return ulcSnoozePending?ESP_ERR_TIMEOUT:ESP_OK;}
   if(owner==1)return r79ApGateTransmitOnce(&r79,0,1);
   if(owner==2)return r79LabDirectTwaiTransmitOnce(&r79,0,&r79Mode1PostMux2Generation,2,1);
   return mux1DisplayTransmit(&stock,1,CAN_TX_FRESH_BOTH,true);
  };
  auto err=sendOwner();
  if(err!=ESP_OK){assert(busy&&owner!=1&&owner!=2&&ulcSnoozePending);finish(&d);err=sendOwner();}
  else if(busy)finish(&d);
  assert(err==ESP_OK&&!ulcSnoozePending&&getBit(h.sent[h.n-1].data,36));finish(&d);
  if(owner==0){const auto before=h.n;assert(!lateStock(stock,false)&&h.n==before);}
  else {assert(sendOwner()==ESP_OK&&!getBit(h.sent[h.n-1].data,36));finish(&d);}
  if(door)cancelControl(true,false);
  cancelControl(door);assert(!autoBlinkerCancelPauseState.active&&!ulcSnoozePending);
 }
 // Epoch numbers are not fixed at one, and both PARTY/VEHICLE freshness bits
 // remain mandatory. A missing required bus never consumes the cancel request.
 for(uint8_t mask:{0u,1u,2u,3u}){
  init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=lastDASStatusMillis=1000;
  dasAutopilotStateValid=true;dasAutopilotState4=5;canTxBarrierState={77,mask};request();
  assert(r79ApGateTransmitOnce(&r79,0,1)==ESP_OK);
  assert(getBit(h.sent[h.n-1].data,36)==(mask==CAN_TX_FRESH_BOTH));
  assert(ulcSnoozePending==(mask!=CAN_TX_FRESH_BOTH));finish(&d);
 }
 canTxBarrierState={1,CAN_TX_FRESH_BOTH};
 for(bool door:{false,true})for(unsigned why=0;why<3;++why){
  nowMs=1000;visualDebugLastMs=1000;dasAutopilotStateValid=true;dasAutopilotState4=5;
  doorButtonPressed=false;autoBlinkerCancelPauseState={};ulcSnoozePending=false;
  if(why==0)dasAutopilotStateValid=false;
  if(why==1)dasAutopilotState4=3;
  if(why==2)visualDebugLastMs=0;
  cancelControl(door);assert(!ulcSnoozePending&&!autoBlinkerCancelPauseState.active);
 }
 nowMs=visualDebugLastMs=1000;dasAutopilotStateValid=true;dasAutopilotState4=5;
 doorButtonPressed=false;doorOpenCancelEnabled=false;cancelControl(true);
 assert(!ulcSnoozePending&&!autoBlinkerCancelPauseState.active);
 doorOpenCancelEnabled=true;doorButtonPressed=false;uint8_t shortDoor[4]={0,0,0,0x80};
 handle102LaneChangeCancel(shortDoor,3);assert(!ulcSnoozePending);
 // A recovery between ordinary epoch capture and final admission still
 // rejects the stale clone and retains ULC for a newly authorized stock.
 for(bool display:{false,true}){
  init(&d,&h,&q,&r,0);p4CanHandles[0]=&d;nowMs=1000;canTxBarrierState={77,CAN_TX_FRESH_BOTH};
  const auto epoch=canTxEpochSnapshot();assert(epoch==77);
  assert(xSemaphoreTake(canTxBarrierMutex,0)==pdTRUE);++canTxBarrierState.epoch;xSemaphoreGive(canTxBarrierMutex);
  request();assert(mux1DisplayTransmit(&stock,epoch,CAN_TX_FRESH_BOTH,display)==ESP_ERR_INVALID_STATE);
  assert(ulcSnoozePending&&h.n==0&&!barrierLocked);
  assert(mux1DisplayTransmit(&stock,canTxEpochSnapshot(),CAN_TX_FRESH_BOTH,display)==ESP_OK);
  assert(!ulcSnoozePending&&getBit(h.sent[0].data,36));finish(&d);
 }
 puts("PASS: actual R79/ULC/DMS/vision final composition, empty/busy native dispatch, failed admission, cancellation, pending ownership and rollover");
 assert(reentrantTakes==0&&"final composer must not reacquire the caller-owned TX mutex");
}
'''
temp=tempfile.TemporaryDirectory();w=pathlib.Path(temp.name)
(w/'freertos').mkdir(exist_ok=True)
(w/'esp_attr.h').write_text('#define IRAM_ATTR\n#define DRAM_ATTR\n')
(w/'esp_timer.h').write_text('#include <stdint.h>\nint64_t esp_timer_get_time(void);\n')
(w/'freertos/FreeRTOS.h').write_text('#pragma once\ntypedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\nvoid diagFakeEnter(void);void diagFakeExit(void);\n#define portENTER_CRITICAL(p) ((void)(p),diagFakeEnter())\n#define portEXIT_CRITICAL(p) ((void)(p),diagFakeExit())\n#define portENTER_CRITICAL_ISR portENTER_CRITICAL\n#define portEXIT_CRITICAL_ISR portEXIT_CRITICAL\n')
(w/'freertos/portmacro.h').write_text('#include "FreeRTOS.h"\n')
(w/'audit.cpp').write_text(native+app)
inc=['-I',str(w),'-I',str(root)]
subprocess.run(['/usr/bin/cc','-std=c11',*inc,'-c',str(root/'p4_twai_diag.c'),'-o',str(w/'diag.o')],check=True)
subprocess.run([os.environ.get('CXX', '/usr/bin/c++'),'-std=c++17','-Wno-c99-designator','-Wno-reorder-init-list',*inc,str(w/'audit.cpp'),str(w/'diag.o'),'-o',str(w/'audit')],check=True)
subprocess.run([str(w/'audit')],check=True)
