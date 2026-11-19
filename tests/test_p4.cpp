#include <cassert>
#include <cstdio>
#include <vector>
#include "driver/twai.h"
#define CONFIG_IDF_TARGET_ESP32P4 1
constexpr int INPUT=0;
static uint32_t fakeTime=100;
static uint8_t profile=0;
uint32_t millis(){return fakeTime;}
void delay(uint32_t ms){fakeTime+=ms;}
void pinMode(int,int){}
static bool activeProfileIsYl(){return profile==1;}
#include "vehicle_profile.h"
struct TraceToken { unsigned id; };
struct TraceEvent { int kind; uint8_t bus; twai_message_t frame; TickType_t wait; esp_err_t result; bool driverCalled; };
static std::vector<TraceEvent> traceEvents;
void traceRx(uint8_t bus, const twai_message_t& f) { traceEvents.push_back({1,bus,f,0,ESP_OK,false}); }
TraceToken traceBegin(uint8_t bus,const twai_message_t* f,TickType_t wait) {
 if (!f) return {0};
 traceEvents.push_back({2,bus,*f,wait,ESP_OK,false}); return {(unsigned)traceEvents.size()};
}
void traceEnd(TraceToken token,const twai_message_t* f,esp_err_t result,bool called) {
 if (!token.id || !f) return;
 const TraceEvent original=traceEvents[token.id-1];
 traceEvents.push_back({3,original.bus,*f,original.wait,result,called});
}
void traceGate(uint8_t bus,const twai_message_t* f,TickType_t wait,esp_err_t result) {
 if(f) traceEvents.push_back({4,bus,*f,wait,result,false});
}
#define P4_R79_TIMING_GATE_REJECTED(bus, frame, wait, result) traceGate(bus,frame,wait,result)
#define P4_R79_TIMING_RX(bus, frame) traceRx(bus,frame)
#define P4_R79_TIMING_TX_BEGIN(bus, frame, wait) traceBegin(bus,frame,wait)
#define P4_R79_TIMING_TX_END(token, frame, result, called) traceEnd(token,frame,result,called)
static unsigned diagStatusCalls=0,diagRxCalls=0,diagTxCalls=0,diagEpochCalls=0;
static uint8_t diagBus=255; static bool diagDriverCalled=false; static esp_err_t diagResult=ESP_FAIL;
#define P4_CAN_DIAG_STATUS(bus, st, alerts) do { ++diagStatusCalls; diagBus=(bus); } while(0)
#define P4_CAN_DIAG_RX(bus) do { ++diagRxCalls; diagBus=(bus); } while(0)
#define P4_CAN_DIAG_TX(bus, frame, result, called, source) do { ++diagTxCalls; diagBus=(bus); diagResult=(result); diagDriverCalled=(called); } while(0)
#define P4_CAN_DIAG_EPOCH(bus) do { ++diagEpochCalls; diagBus=(bus); } while(0)
static bool rxCaptureConfigured[3]={},rxCaptureEnabled[3]={};
#define P4_CAN_DIAG_RX_CONFIG(bus, enabled) do { rxCaptureConfigured[bus]=true;rxCaptureEnabled[bus]=(enabled); } while(0)
#include "p4_can.h"
#include "can_usb_logger_pure.h"
#include "driver_monitor_capture_pure.h"

static FakeController hw[3];
static twai_general_config_t configs[3];
static int installFail=-1,startFail=-1,uninstallFail=-1,sendBus=-1,sends=0;
static twai_message_t sent;
static esp_err_t sendResult=ESP_OK;
static TickType_t lastWait=0;
static esp_err_t receiveResult=ESP_OK;
static TickType_t lastRxWait=0;
static int lastRxBus=-1;
esp_err_t twai_driver_install_v2(const twai_general_config_t*g,const twai_timing_config_t*t,const twai_filter_config_t*f,twai_handle_t*out){
 assert(g->controller_id>=0&&g->controller_id<3); assert(t->bitrate==500000&&f->acceptAll);
 assert(p4CanConfiguredBitrate(g->controller_id)==(uint32_t)t->bitrate);
 const bool bodyTrial=profile==1 && g->controller_id==1;
 assert(rxCaptureConfigured[g->controller_id] && "configure capture before native installation");
 assert(rxCaptureEnabled[g->controller_id]==bodyTrial);
 rxCaptureConfigured[g->controller_id]=false;
 const uint32_t tq=1+t->prop_seg+t->tseg_1+t->tseg_2;
 const uint32_t brp=40000000u/t->quanta_resolution_hz;
 assert(t->quanta_resolution_hz/tq==500000u && (brp%2)==0);
 assert((1+t->prop_seg+t->tseg_1)*1000/tq==(bodyTrial?875u:800u));
 assert(t->clk_src==1 && !t->triple_sampling && t->prop_seg==0);
 assert(t->tseg_1==(bodyTrial?6u:15u) && t->tseg_2==(bodyTrial?1u:4u));
 assert(t->sjw==(bodyTrial?1u:3u));
 if(g->controller_id==installFail)return ESP_FAIL;
 configs[g->controller_id]=*g;hw[g->controller_id]={g->controller_id,TWAI_STATE_STOPPED,g->mode,false,{}};*out=&hw[g->controller_id];return ESP_OK;
}
esp_err_t twai_start_v2(twai_handle_t h){if(h->id==startFail)return ESP_FAIL;h->state=TWAI_STATE_RUNNING;return ESP_OK;}
esp_err_t twai_stop_v2(twai_handle_t h){h->state=TWAI_STATE_STOPPED;return ESP_OK;}
esp_err_t twai_driver_uninstall_v2(twai_handle_t h){return h->id==uninstallFail?ESP_FAIL:ESP_OK;}
esp_err_t twai_get_status_info_v2(twai_handle_t h,twai_status_info_t*out){if(!h)return ESP_ERR_INVALID_ARG;out->state=h->state;return ESP_OK;}
esp_err_t twai_receive_v2(twai_handle_t h,twai_message_t*out,TickType_t wait){
 lastRxWait=wait;lastRxBus=h->id;
 if(receiveResult!=ESP_OK)return receiveResult;
 if(!h->pending)return ESP_ERR_TIMEOUT;
 h->pending=false;
 // Model IDF's partial flag writes. RTR payload is unused; this fixture does
 // not simulate the SDK's separate malformed-DLC zero-fill overflow.
 out->extd=h->rx.extd;out->rtr=h->rx.rtr;
 out->identifier=h->rx.identifier;out->data_length_code=h->rx.data_length_code;
 const size_t dataLength=out->data_length_code<8?out->data_length_code:8;
 if(!out->rtr)memcpy(out->data,h->rx.data,dataLength);
 if(dataLength<8)memset(out->data+dataLength,0,8-dataLength);
 return ESP_OK;
}
esp_err_t twai_transmit_v2(twai_handle_t h,const twai_message_t*f,TickType_t wait){
 lastWait=wait; if(sendResult!=ESP_OK)return sendResult;
 if(h->mode==TWAI_MODE_LISTEN_ONLY||h->state!=TWAI_STATE_RUNNING)return ESP_ERR_INVALID_STATE;
 sendBus=h->id;sent=*f;sends++;return ESP_OK;
}
static unsigned priorityCalls=0;
static p4_twai_priority_guard_t priorityGuard{};
extern "C" esp_err_t p4_twai_transmit_r79_v2(twai_handle_t h,const twai_message_t*f,const p4_twai_priority_guard_t*g){
 ++priorityCalls;priorityGuard=*g;return twai_transmit_v2(h,f,0);
}
static unsigned mux1NowCalls=0;
static p4_twai_rx_metadata_t nativeOrigin{1000,1100,7};
static uint32_t completedInput=0;
extern "C" bool p4_twai_rx_metadata_v2(twai_handle_t h,p4_twai_rx_metadata_t*out){
 assert(h==p4CanHandleB());*out=nativeOrigin;return true;
}
extern "C" bool p4_twai_r79_input_current_v2(twai_handle_t h,uint32_t sequence){
 assert(h==p4CanHandleB());return sequence==nativeOrigin.sequence;
}
extern "C" void p4_twai_r79_input_done_v2(twai_handle_t h,uint32_t sequence){
 assert(h==p4CanHandleB());completedInput=sequence;
}
extern "C" esp_err_t p4_twai_transmit_mux1_now_v2(twai_handle_t h,const twai_message_t*f){
 ++mux1NowCalls;return twai_transmit_v2(h,f,0);
}
int main(){
 p4CanGpioValid=false;
 assert(!p4CanInstall(P4_BODY,false)&&!p4CanHandles[P4_BODY]);
 p4CanGpioValid=true;
 assert(p4CanConfiguredBitrate(3)==0);
 for(profile=1;profile<=5;profile++){
  const auto topology=vehicleProfileDefaultTopology(profile);
  assert(vehicleProfileTopologyValid(profile,topology));
  if(profile==1)assert(strcmp(vehicleProfileCanBName(profile,topology),"VEHICLE")==0);
  assert(!vehicleProfileTopologyValid(profile,VEHICLE_TOPOLOGY_RETIRED_PARTY_CHASSIS));
  assert(vehicleProfileNagTorqueSupported(profile,topology));
  assert(vehicleProfileAdvancedEapSupported(profile,topology));
  assert(vehicleProfilePedalMapSupported(profile,topology));
  assert(p4CanBusA()==(profile==1?P4_PARTY:P4_BODY));
  assert(p4CanBusB()==(profile==1?P4_BODY:P4_CHASSIS));
  assert(p4CanBusExtra()==(profile==1?P4_CHASSIS:P4_PARTY));
  for(uint8_t bus=0;bus<3;bus++)assert(p4CanInstall(bus,false));
  for(unsigned bus=0;bus<3;bus++){
   const bool listening=profile==1&&bus==1;
   assert(configs[bus].mode==(listening?TWAI_MODE_LISTEN_ONLY:TWAI_MODE_NORMAL));
   assert(p4CanPassive[bus]==listening);
  }
  const int tx[]={20,50,26},rx[]={21,49,27};
  for(int bus=0;bus<3;bus++){assert(configs[bus].tx_io==tx[bus]&&configs[bus].rx_io==rx[bus]);assert(configs[bus].rx_queue_len==256);}
  CanFrame frame{};frame.can_id=0x123;frame.can_dlc=8;frame.data[7]=0x5a;
  p4CanExtraFresh=false;assert(p4CanSendFrame(&frame)!=ESP_OK);
  p4CanExtraFresh=true;assert(p4CanSendFrame(&frame)==ESP_OK&&sendBus==p4CanBusA());
  // Origin survives copy/modification and never follows the default A route.
  for(int bus=0;bus<3;bus++){
   hw[bus].rx={};hw[bus].rx.identifier=0x456;hw[bus].rx.data_length_code=8;hw[bus].rx.data[7]=0x7b;hw[bus].pending=true;
   const uint32_t beforeRx=p4CanRxCount[bus],beforePoll=p4CanRxPolls[bus];
   assert(p4CanReadFrame(bus,&frame)==ESP_OK);
   assert(p4CanRxCount[bus]==beforeRx+1&&p4CanRxPolls[bus]==beforePoll+1&&p4CanLastRxResult[bus]==ESP_OK);
   CanFrame copy=frame;copy.data[0]=9;
   const int before=sends;
   if(profile==1&&bus==1){assert(p4CanSendFrame(&copy)!=ESP_OK&&sends==before);}
   else {assert(p4CanSendFrame(&copy)==ESP_OK);assert(sendBus==bus&&sends==before+1&&sent.data[7]==0x7b);}
  }
  assert(p4CanReadFrameA(&frame)==ESP_ERR_TIMEOUT);
  assert(p4CanLastRxResult[p4CanBusA()]==ESP_ERR_TIMEOUT);
  twai_status_info_t stats{};stats.state=TWAI_STATE_RUNNING;stats.rx_error_counter=7;
  stats.tx_error_counter=9;stats.msgs_to_rx=4;stats.rx_missed_count=2;stats.bus_error_count=17;
  p4CanPublishStatus(p4CanBusExtra(),stats);
  assert(p4CanRec[p4CanBusExtra()]==7&&p4CanTec[p4CanBusExtra()]==9);
  assert(p4CanBusErrors[p4CanBusExtra()]==17);
  assert(diagStatusCalls>0 && diagBus==p4CanBusExtra());
  assert(diagRxCalls>=3 && diagTxCalls>=4 && diagEpochCalls>=3);
  assert(p4CanRxQueued[p4CanBusExtra()]==4&&p4CanMissed[p4CanBusExtra()]==2);
  assert(p4CanReadFrame(3,&frame)==ESP_ERR_INVALID_ARG);
  hw[2].rx={};hw[2].rx.identifier=0x123;hw[2].rx.data_length_code=9;hw[2].pending=true;
  assert(p4CanReadFrame(2,&frame)==ESP_ERR_INVALID_ARG);
  hw[2].rx.data_length_code=8;hw[2].rx.identifier=0x800;hw[2].pending=true;
  assert(p4CanReadFrame(2,&frame)==ESP_ERR_INVALID_ARG);
  hw[2].rx.identifier=0x123;hw[2].rx.rtr=true;hw[2].rx.data[0]=0xaa;hw[2].pending=true;
  assert(p4CanReadFrame(2,&frame)==ESP_OK&&frame.can_id==0x40000123&&frame.data[0]==0);
  assert(!p4CanReinstall(3,false));
  twai_message_t b{};b.identifier=0x399;b.data_length_code=8;assert(p4CanSendB(&b)==ESP_OK&&sendBus==p4CanBusB());
  assert(diagBus==p4CanBusB() && diagDriverCalled && diagResult==ESP_OK);
  volatile uint32_t generation=7; volatile bool hold=false;
  p4_twai_priority_guard_t guard{&generation,7,nullptr,0,&hold,true,1000,0};
  b.identifier=0x3FD;b.data[0]=1;
  const unsigned mux1Before=mux1NowCalls,priorityBeforeMux1=priorityCalls;
  const uint32_t mux1Accepted=p4CanTxAccepted[p4CanBusB()];
  assert(p4CanSendMux1B(&b)==ESP_OK&&mux1NowCalls==mux1Before+1&&priorityCalls==priorityBeforeMux1);
  assert(sendBus==p4CanBusB()&&lastWait==0&&p4CanTxAccepted[p4CanBusB()]==mux1Accepted+1);
  assert(diagBus==p4CanBusB()&&diagDriverCalled&&diagResult==ESP_OK);
  // Every controller and the extra-bus freshness gate must be ready.
  for(unsigned blocked=0;blocked<4;++blocked){
   if(blocked<3)p4CanOnline[blocked]=false;else p4CanExtraFresh=false;
   const int beforeSends=sends;const unsigned beforeCalls=mux1NowCalls;
   assert(p4CanSendMux1B(&b)==ESP_ERR_INVALID_STATE&&sends==beforeSends&&mux1NowCalls==beforeCalls);
   assert(!diagDriverCalled&&diagResult==ESP_ERR_INVALID_STATE);
   if(blocked<3)p4CanOnline[blocked]=true;else p4CanExtraFresh=true;
  }
  sendResult=ESP_ERR_TIMEOUT;const auto mux1Rejected=p4CanTxRejected[p4CanBusB()];
  assert(p4CanSendMux1B(&b)==ESP_ERR_TIMEOUT&&p4CanTxRejected[p4CanBusB()]==mux1Rejected+1);
  assert(diagDriverCalled&&diagResult==ESP_ERR_TIMEOUT);sendResult=ESP_OK;
  const unsigned priorityBefore=priorityCalls;
  const unsigned ordinaryMux1Calls=mux1NowCalls;
  assert(p4CanSendB(&b)==ESP_OK&&priorityCalls==priorityBefore&&mux1NowCalls==ordinaryMux1Calls);
  const uint32_t accepted=p4CanTxAccepted[p4CanBusB()];
  hw[p4CanBusB()].rx=b;hw[p4CanBusB()].pending=true;
  twai_message_t originFrame{};
  assert(p4CanReceiveRaw(p4CanBusB(),&originFrame)==ESP_OK);
  assert(p4CanR79InputCurrent());
  ++nativeOrigin.sequence;assert(!p4CanR79InputCurrent());--nativeOrigin.sequence;
  p4CanR79InputDone();assert(completedInput==nativeOrigin.sequence);
  assert(p4CanSendR79B(&b,guard)==ESP_OK&&priorityCalls==priorityBefore+1);
  assert(priorityGuard.rx_sequence==nativeOrigin.sequence);
  assert(priorityGuard.rx_observed_us==1000&&priorityGuard.rx_dequeued_us==1100);
  assert(sendBus==p4CanBusB()&&lastWait==0&&p4CanTxAccepted[p4CanBusB()]==accepted+1);
  assert(priorityGuard.generation==&generation&&priorityGuard.expected_generation==7&&priorityGuard.has_deadline&&priorityGuard.deadline_ms==1000);
  assert(diagBus==p4CanBusB()&&diagDriverCalled&&diagResult==ESP_OK);
  // YL authorized R79 ignores only additional BODY availability/acquisition.
  // Ordinary overlays keep the existing all-bus gate; PARTY/VEHICLE stay required.
  for(unsigned blocked=0;blocked<4;++blocked){
   if(blocked<3)p4CanOnline[blocked]=false;else p4CanExtraFresh=false;
   const bool isolated=profile==1&&(blocked==p4CanBusExtra()||blocked==3);
   const unsigned beforeCalls=priorityCalls;
   assert(p4CanSendR79B(&b,guard)==(isolated?ESP_OK:ESP_ERR_INVALID_STATE));
   assert(priorityCalls==beforeCalls+(isolated?1:0));
   assert(p4CanSendB(&b)==ESP_ERR_INVALID_STATE);
   if(blocked<3)p4CanOnline[blocked]=true;else p4CanExtraFresh=true;
  }
  sendResult=ESP_ERR_TIMEOUT;
  const uint32_t rejected=p4CanTxRejected[p4CanBusB()];
  assert(p4CanSendR79B(&b,guard)==ESP_ERR_TIMEOUT&&p4CanTxRejected[p4CanBusB()]==rejected+1);
  assert(diagResult==ESP_ERR_TIMEOUT);sendResult=ESP_OK;
  p4CanExtraFresh=false;const unsigned beforeGate=priorityCalls;
  assert(p4CanSendR79B(&b,guard)==(profile==1?ESP_OK:ESP_ERR_INVALID_STATE));
  assert(priorityCalls==beforeGate+(profile==1?1:0));
  p4CanExtraFresh=true;
  if(profile==1){
   assert(sendBus==0&&p4CanAllRunning());
   assert(p4CanReinstall(1,false)&&configs[1].mode==TWAI_MODE_LISTEN_ONLY&&p4CanPassive[1]);
   p4CanExtraFresh=true;assert(p4CanSendB(&b)==ESP_OK&&sendBus==0);
  }
  sendResult=ESP_ERR_TIMEOUT;assert(p4CanSendB(&b)==ESP_ERR_TIMEOUT);
  assert(diagDriverCalled && diagResult==ESP_ERR_TIMEOUT);sendResult=ESP_OK;
  frame.bus=P4_PARTY;frame.can_id=0x80000123;assert(p4CanSendFrame(&frame)==ESP_OK&&sent.extd);
  frame.can_id=0x40000123;assert(p4CanSendFrame(&frame)==ESP_OK&&sent.rtr);
  frame.can_id=0x123;frame.can_dlc=9;assert(p4CanSendFrame(&frame)==ESP_ERR_INVALID_ARG);
  frame.can_dlc=8;frame.can_id=0x800;assert(p4CanSendFrame(&frame)==ESP_ERR_INVALID_ARG);
  frame.can_id=0x20000123;assert(p4CanSendFrame(&frame)==ESP_ERR_INVALID_ARG);
  frame.can_id=0x123;frame.bus=3;assert(p4CanSendFrame(&frame)==ESP_ERR_INVALID_STATE);
  frame.bus=2;p4CanOnline[1]=false;assert(p4CanSendFrame(&frame)!=ESP_OK);assert(!diagDriverCalled && diagResult==ESP_ERR_INVALID_STATE);p4CanOnline[1]=true;
  assert(p4CanStopAll());for(auto h:p4CanHandles)assert(!h);
  for(uint8_t bus=0;bus<3;bus++)assert(p4CanInstall(bus,true));
  for(unsigned bus=0;bus<3;bus++)assert(configs[bus].mode==TWAI_MODE_LISTEN_ONLY&&p4CanPassive[bus]);
  const int before=sends;p4CanExtraFresh=true;assert(p4CanSendFrame(&frame)!=ESP_OK&&p4CanSendB(&b)!=ESP_OK&&sends==before);
  assert(p4CanStopAll());
 }
 assert(!vehicleProfileValid(0)&&!vehicleProfileValid(6));
 assert(!vehicleProfileTurnValid(4,2,0)&&vehicleProfileTurnValid(4,2,1)&&vehicleProfileTurnValid(4,2,2));
 installFail=1;assert(!p4CanInstall(1,false)&&!p4CanHandles[1]);installFail=-1;
 startFail=2;assert(!p4CanInstall(2,false)&&!p4CanHandles[2]&&!p4CanOnline[2]);startFail=-1;
 assert(p4CanInstall(2,false));hw[2].state=TWAI_STATE_RECOVERING;assert(!p4CanUninstall(2)&&p4CanHandles[2]);
 const uint32_t before=fakeTime;assert(!p4CanReinstall(2,false)&&fakeTime-before>=1800&&p4CanHandles[2]);
 hw[2].state=TWAI_STATE_BUS_OFF;assert(p4CanReinstall(2,false));
 uninstallFail=2;assert(!p4CanStopAll()&&p4CanHandles[2]&&!p4CanOnline[2]);uninstallFail=-1;assert(p4CanStopAll());
 char line[160];CanUsbFrame f{};f.id=0x123;f.dlc=8;f.data[7]=0xaa;
 for(uint8_t bus=0;bus<3;bus++){f.bus=bus;assert(canUsbFormatFrame(line,sizeof(line),f)>0);char token[12];snprintf(token,sizeof(token),",%u,0,123,8,",bus+1);assert(strstr(line,token));}
 f.bus=3;assert(!canUsbFormatFrame(line,sizeof(line),f));f.bus=2;f.dlc=9;assert(!canUsbFormatFrame(line,sizeof(line),f));
 for(uint8_t bus=0;bus<3;bus++)assert(driver_monitor_capture_pure::targetFrame(bus,0x399));
 assert(!driver_monitor_capture_pure::targetFrame(3,0x399));
 // A reused native RX buffer must never turn old SS/SELF/reserved bits into TX policy.
 profile=2;for(uint8_t bus=0;bus<3;bus++)assert(p4CanInstall(bus,false));p4CanExtraFresh=true;
 twai_message_t reused{};
 const uint32_t formats[]={0u,TWAI_MSG_FLAG_EXTD,TWAI_MSG_FLAG_RTR,TWAI_MSG_FLAG_EXTD|TWAI_MSG_FLAG_RTR};
 for(uint8_t bus=0;bus<3;bus++){
  for(const uint32_t format:formats){
   auto& rx=hw[bus].rx;rx={};rx.flags=format;
   rx.identifier=(format&TWAI_MSG_FLAG_EXTD)?0x1abcdeu:0x456u;rx.data_length_code=8;
   for(unsigned i=0;i<8;i++)rx.data[i]=(uint8_t)(0x30u+bus*8u+i+format);
   hw[bus].pending=true;reused.flags=0xffffffffu;
   const uint32_t polls=p4CanRxPolls[bus],count=p4CanRxCount[bus];
   const unsigned diagnostics=diagRxCalls;traceEvents.clear();
   assert(p4CanReceiveRaw(bus,&reused,13)==ESP_OK);
   assert(reused.flags==format);
   assert(reused.identifier==rx.identifier&&reused.data_length_code==8&&(reused.rtr||memcmp(reused.data,rx.data,8)==0));
   assert(lastRxWait==13&&lastRxBus==bus&&p4CanLastRxResult[bus]==ESP_OK);
   assert(p4CanRxPolls[bus]==polls+1&&p4CanRxCount[bus]==count+1&&diagRxCalls==diagnostics+1&&diagBus==bus);
   assert(traceEvents.size()==1&&traceEvents[0].kind==1&&traceEvents[0].bus==bus&&traceEvents[0].frame.flags==format);
   twai_message_t copy=reused;const int beforeSends=sends;
   assert(p4CanSendB(&copy,17)==ESP_OK&&sends==beforeSends+1&&sendBus==P4_CHASSIS&&lastWait==17);
   assert(sent.flags==format&&!sent.ss&&!sent.self&&sent.identifier==rx.identifier&&sent.data_length_code==8&&(sent.rtr||memcmp(sent.data,rx.data,8)==0));
  }
  for(const esp_err_t result:{ESP_ERR_TIMEOUT,ESP_FAIL}){
   receiveResult=result==ESP_ERR_TIMEOUT?ESP_OK:result;
   const uint32_t polls=p4CanRxPolls[bus],count=p4CanRxCount[bus];
   const unsigned diagnostics=diagRxCalls;traceEvents.clear();
   assert(p4CanReceiveRaw(bus,&reused,19)==result);
   assert(lastRxWait==19&&lastRxBus==bus&&p4CanLastRxResult[bus]==result);
   assert(p4CanRxPolls[bus]==polls+1&&p4CanRxCount[bus]==count&&diagRxCalls==diagnostics&&traceEvents.empty());
  }
  receiveResult=ESP_OK;
 }
 // RX isolation must not strip explicitly selected native TX single-shot/self-reception.
 twai_message_t direct{};direct.flags=TWAI_MSG_FLAG_SS|TWAI_MSG_FLAG_SELF;direct.identifier=0x399;direct.data_length_code=8;direct.data[7]=0xa5;
 assert(p4CanSendB(&direct,23)==ESP_OK&&lastWait==23&&sendBus==P4_CHASSIS);
 assert(sent.flags==(TWAI_MSG_FLAG_SS|TWAI_MSG_FLAG_SELF)&&sent.ss&&sent.self&&sent.identifier==0x399&&sent.data_length_code==8&&sent.data[7]==0xa5);
 assert(p4CanStopAll());
 // The production transport must observe driver dequeue and preserve submission outcomes.
 profile=1; for(uint8_t bus=0;bus<3;bus++)assert(p4CanInstall(bus,false)); p4CanExtraFresh=true;
 traceEvents.clear();
 hw[0].rx={};hw[0].rx.identifier=0x3fd;hw[0].rx.data_length_code=8;hw[0].rx.data[7]=0x72;hw[0].pending=true;
 twai_message_t received{};assert(p4CanReceiveRaw(0,&received)==ESP_OK);
 assert(traceEvents.size()==1 && traceEvents[0].kind==1 && traceEvents[0].bus==0 && traceEvents[0].frame.data[7]==0x72);
 assert(p4CanReceiveRaw(0,&received)==ESP_ERR_TIMEOUT && traceEvents.size()==1);
 traceEvents.clear();
 twai_message_t traced{};traced.identifier=0x3fd;traced.data_length_code=8;traced.data[3]=0x5a;
 const auto accepted=p4CanTxAccepted[0];
 assert(p4CanSendB(&traced,7)==ESP_OK && lastWait==7 && p4CanTxAccepted[0]==accepted+1);
 assert(traceEvents.size()==2 && traceEvents[0].kind==2 && traceEvents[1].kind==3 && traceEvents[1].driverCalled && traceEvents[1].wait==7 && traceEvents[1].result==ESP_OK && traceEvents[1].frame.data[3]==0x5a);
 traceEvents.clear();sendResult=ESP_ERR_TIMEOUT;const auto rejected=p4CanTxRejected[0];
 assert(p4CanSendB(&traced,0)==ESP_ERR_TIMEOUT && p4CanTxRejected[0]==rejected+1);
 assert(traceEvents.size()==2 && traceEvents[1].driverCalled && traceEvents[1].result==ESP_ERR_TIMEOUT);
 traceEvents.clear();sendResult=ESP_OK;p4CanExtraFresh=false;
 assert(p4CanSendB(&traced,0)==ESP_ERR_INVALID_STATE);
 assert(traceEvents.size()==1 && traceEvents[0].kind==4 && !traceEvents[0].driverCalled && traceEvents[0].result==ESP_ERR_INVALID_STATE);
 traceEvents.clear();CanFrame blocked{};blocked.bus=0;blocked.can_id=0x3fd;blocked.can_dlc=8;blocked.data[0]=1;
 assert(p4CanSendFrame(&blocked)==ESP_ERR_INVALID_STATE);
 assert(traceEvents.size()==1 && traceEvents[0].kind==4 && traceEvents[0].frame.data[0]==1);
 p4CanExtraFresh=true;assert(p4CanStopAll());
 // Installation, recovery and physical teardown share the boot-effective map.
 p4CanTxPins[0]=22;p4CanRxPins[0]=23;
 for(uint8_t bus=0;bus<3;bus++)assert(p4CanInstall(bus,false));
 assert(configs[0].controller_id==0&&configs[0].tx_io==22&&configs[0].rx_io==23);
 assert(configs[1].controller_id==1&&configs[1].tx_io==50&&configs[1].rx_io==49&&configs[1].mode==TWAI_MODE_LISTEN_ONLY);
 assert(configs[2].controller_id==2&&configs[2].tx_io==26&&configs[2].rx_io==27);
 assert(p4CanReinstall(0,true)&&configs[0].tx_io==22&&configs[0].rx_io==23&&configs[0].mode==TWAI_MODE_LISTEN_ONLY);
 assert(p4CanStopAll());
 puts("PASS: five profiles, pin maps, origin-preserving TX, three listen-only controllers, invalid frames, partial init/teardown, recovery timeout, USB v2 and third-bus capture");
}
