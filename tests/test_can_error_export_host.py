"""Execute the bounded CAN-error JSON HTTP handler against immutable snapshots.

A distinct fixture is necessary because this route exports the three physical
journals in one snapshot, rather than the unrelated frozen logical A/B CSVs.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
web = (ROOT / 'web_api.h').read_text()
assert re.search(r'server\.on\("/api/system/can-errors\.json",\s*HTTP_GET,\s*httpCanErrorsJson\)', web), \
    'The read-only physical CAN error JSON export must be registered as GET'

import json
import os
import subprocess
import tempfile

start = web.index('// CAN error JSON export:')
end = web.index('// End CAN error JSON export.', start)
production = web[start:end]
p4_can = (ROOT / 'p4_can.h').read_text()
timing = p4_can[p4_can.index('struct P4CanTimingConfiguration {'):p4_can.index('static bool p4CanInstall(')]
status = web[web.index('static void p4CanWriteStatus('):web.index('static String canTrafficStatsToJson(')]
PREAMBLE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <new>
#include <string>
#include <map>
#include <vector>
#include <fstream>
#include "tests/fakes/driver/twai.h"
#include "can_error_journal_pure.h"
#include "p4_twai_diag.h"
#include "p4_twai_error_decode_pure.h"
#define FW_VERSION "v3.34.9"
static int lockDepth=0,allocations=0,frees=0,snapshotCalls=0,driverSnapshotCalls=0;
static int concatCalls=0,formatCalls=0,concatFailureAt=0,formatFailureAt=0,formatTruncationAt=0;
static bool allocationFails=false,psramAllocationFails=false,reserveFails=false,snapshotFails=false,driverSnapshotFails=false,yl=true;
static size_t failedAllocationSize=0;
static std::map<void *,size_t> snapshotMemory;
constexpr uint32_t MALLOC_CAP_8BIT=1,MALLOC_CAP_SPIRAM=2;
static std::vector<uint32_t> requestedCaps;
void *heap_caps_malloc(size_t bytes,uint32_t caps){
 assert(lockDepth==0);requestedCaps.push_back(caps);
 if(allocationFails||bytes==failedAllocationSize||(psramAllocationFails&&(caps&MALLOC_CAP_SPIRAM)))return nullptr;
 void *memory=malloc(bytes);assert(memory);++allocations;snapshotMemory[memory]=bytes;return memory;
}
void heap_caps_free(void *memory){assert(lockDepth==0&&snapshotMemory.erase(memory)==1);++frees;free(memory);}
class String:public std::string {
public:
 using std::string::string;
 using std::string::operator+=;
 String(const std::string &s):std::string(s){}
 String& operator+=(unsigned long n){append(std::to_string(n));return *this;}
 String& operator+=(long n){append(std::to_string(n));return *this;}
 bool reserve(size_t bytes){assert(lockDepth==0);if(reserveFails)return false;std::string::reserve(bytes);return true;}
 bool concat(const char *data,unsigned int bytes){
  assert(lockDepth==0);++concatCalls;if(concatCalls==concatFailureAt)return false;
  append(data,bytes);return true;
 }
};
#include "json_writer_arduino.h"
constexpr uint8_t P4_CAN_COUNT=3,P4_CHASSIS=1;
constexpr uint32_t CAN_TRAFFIC_UI_FRESH_MS=1500;
static uint32_t clockMs=5000;
static bool updateAtMillis=false,updateBetweenFields=false;
static uint32_t lastCanAFrameMs=4990,lastCanBFrameMs=4990;
static uint32_t millis();
static const char *esp_err_to_name(int value){return value ? "ESP_FAIL" : "ESP_OK";}
static uint32_t p4CanTxPins[]={20,22,26},p4CanRxPins[]={21,23,27};
static bool p4CanGpioValid=true;
static uint32_t p4CanState[]={1,0,1},p4CanLastRxMs[]={4990,0,2000};
static uint32_t p4CanStatusMs[]={4900,0,2900};
static uint32_t p4CanRxCount[3]={},p4CanTxAccepted[3]={},p4CanTxRejected[3]={};
static uint32_t p4CanBusOffCount[3]={},p4CanMissed[3]={},p4CanOverrun[3]={};
static uint32_t p4CanRxPolls[3]={},p4CanTec[3]={},p4CanRec[3]={},p4CanTxQueued[3]={},p4CanRxQueued[3]={};
static uint32_t p4CanBusErrors[3]={},p4CanArbLost[3]={},p4CanDriverTxFailed[3]={};
static uint32_t p4CanRecoveries[3]={},p4CanRecoveryFailures[3]={},p4CanInitError[]={0,1,0},p4CanLastRxResult[3]={};
static bool p4CanOnline[]={true,false,true},p4CanPassive[]={false,true,false};
static uint32_t millis(){const uint32_t value=clockMs;if(updateAtMillis){updateAtMillis=false;++clockMs;
 for(uint8_t bus=0;bus<3;++bus)p4CanLastRxMs[bus]=p4CanStatusMs[bus]=clockMs;
 lastCanAFrameMs=lastCanBFrameMs=clockMs;}return value;}
static CanDiag::Snapshot state{};
static P4TwaiErrorSnapshot driverState{};
static bool activeProfileIsYl(){return yl;}
static const char* p4CanRoleName(uint8_t bus){if(updateBetweenFields){updateBetweenFields=false;++clockMs;
 for(uint8_t n=0;n<3;++n)p4CanLastRxMs[n]=p4CanStatusMs[n]=clockMs;}return bus==0?(activeProfileIsYl()?"VEHICLE":"BODY"):bus==1?(activeProfileIsYl()?"BODY":"CHASSIS"):"PARTY";}
static bool canDiagSnapshot(CanDiag::Snapshot &out){
 assert(lockDepth==0&&snapshotMemory.at(&out)==sizeof(out));++snapshotCalls;
 if(snapshotFails){out=state;out.buses[1].count=UINT32_MAX;return false;}
 ++lockDepth;out=state;--lockDepth;return true;
}
bool p4TwaiDiagSnapshot(P4TwaiErrorSnapshot *out){
 assert(lockDepth==0&&out&&snapshotMemory.at(out)==sizeof(*out));++driverSnapshotCalls;
 if(driverSnapshotFails){*out=driverState;out->buses[1].lifecycle.count=UINT32_MAX;return false;}
 ++lockDepth;*out=driverState;--lockDepth;return true;
}
static int diagVsnprintf(char *target,size_t bytes,const char *format,va_list args){
 assert(lockDepth==0);++formatCalls;
 if(formatCalls==formatFailureAt)return -1;
 if(formatCalls==formatTruncationAt)return (int)bytes;
 return vsnprintf(target,bytes,format,args);
}
struct Server {
 int status=0,sendCalls=0,sendContentCalls=0;
 size_t contentLength=(size_t)-2;
 std::string body,type;
 std::map<std::string,std::string> headers;
 std::vector<int> statuses;
 void send(int code,const char *mime,const String &data){
  assert(lockDepth==0);status=code;type=mime;body=data;++sendCalls;statuses.push_back(code);
 }
 void sendHeader(const char *name,const char *value){assert(lockDepth==0);headers[name]=value;}
 void setContentLength(size_t bytes){assert(lockDepth==0);contentLength=bytes;}
 void sendContent(const char *){++sendContentCalls;}
} server;
'''
PREAMBLE += timing + '\n' + web[web.index('struct CanTrafficUiSnapshot {'):web.index('static void p4CanWriteStatus(')] + '\n' + status
MAIN = r'''
static void resetResponse(){
 server={};allocationFails=psramAllocationFails=reserveFails=snapshotFails=driverSnapshotFails=false;failedAllocationSize=0;
 concatFailureAt=formatFailureAt=formatTruncationAt=concatCalls=formatCalls=0;
 snapshotCalls=driverSnapshotCalls=allocations=frees=0;requestedCaps.clear();
}
static void invoke(){
 const CanDiag::Snapshot before=state;const P4TwaiErrorSnapshot driverBefore=driverState;httpCanErrorsJson();
 assert(memcmp(&before,&state,sizeof(state))==0&&"Export must never mutate/clear the live evidence");
 assert(memcmp(&driverBefore,&driverState,sizeof(driverState))==0&&"Export must never mutate/clear the driver error evidence");
 assert(lockDepth==0&&allocations==frees&&snapshotMemory.empty());
 assert(server.sendCalls==1&&server.sendContentCalls==0);
}
static void success(bool fallback=false){
 assert(server.status==200&&server.statuses==std::vector<int>{200});
 assert(server.type=="application/json"&&server.contentLength==server.body.size());
 assert(server.headers["Content-Disposition"]=="attachment; filename=P4-CAN_CAN_ERRORS.json");
 assert(server.body.size()<=CAN_ERROR_JSON_MAX_BYTES&&snapshotCalls==1&&driverSnapshotCalls==1);
 assert(requestedCaps==(fallback?std::vector<uint32_t>{3,1,3,1}:std::vector<uint32_t>{3,3}));
}
static void failure(){
 assert(server.status==503&&server.statuses==std::vector<int>{503});
 assert(server.type=="application/json"&&server.contentLength==(size_t)-2);
 assert(server.headers.empty());
 assert(server.body=="{\"ok\":false,\"error\":\"CAN error JSON preparation failed\"}");
}
static void save(const char *directory,const char *name){
 std::ofstream file(std::string(directory)+"/"+name);file<<server.body;assert(file.good());
}
static CanDiag::Status maximalStatus(){return {UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX};}
static CanDiag::FlashWindow maximalFlash(){return {UINT64_MAX,UINT64_MAX,UINT32_MAX,UINT16_MAX,UINT8_MAX,UINT8_MAX};}
static CanDiag::Tx maximalTx(){
 CanDiag::Tx tx{};tx.observedUs=UINT64_MAX;tx.id=UINT32_MAX;tx.result=INT32_MIN;
 tx.dlc=8;tx.source=UINT8_MAX;tx.called=tx.valid=true;tx.callId=tx.resultDelayUs=UINT32_MAX;
 for(uint8_t n=0;n<8;n++)tx.data[n]=(uint8_t)(n*17u);
 return tx;
}
static CanDiag::Event event(uint8_t bus,uint32_t index){
 CanDiag::Event e{};e.bus=bus;e.observedUs=UINT64_MAX-32u+index;e.statusObservedUs=UINT64_MAX;
 e.seq=index;e.epoch=e.reasonMask=e.alerts=UINT32_MAX;e.status=e.delta=maximalStatus();
 e.tx=maximalTx();e.flashCurrent=e.flashLast=maximalFlash();
 e.rxAgeUs=e.serviceGapUs=UINT32_MAX;e.rxSeen=e.serviceSeen=e.statusValid=true;
 return e;
}
static void setRxOrigin(P4TwaiTxIdentity &tx,uint64_t observed,uint64_t dequeued,uint32_t sequence,int) {
 tx.rxObservedUs=observed;tx.rxDequeuedUs=dequeued;tx.rxSequence=sequence;
}
static P4TwaiTxIdentity controllerTx(){
 P4TwaiTxIdentity tx{};tx.loadedUs=tx.queuedUs=UINT64_MAX;tx.requestId=UINT32_MAX;tx.identifier=UINT32_MAX;
 setRxOrigin(tx,UINT64_MAX,UINT64_MAX,UINT32_MAX,0);
 tx.dlc=8;tx.source=UINT8_MAX;tx.flags=3;tx.active=0;tx.valid=1;
 for(uint8_t n=0;n<8;n++)tx.data[n]=(uint8_t)(n*17u);
 return tx;
}
static P4TwaiVehicleContext vehicleContext(){
 P4TwaiVehicleContext v{};v.publishedMs=v.gearObservedMs=v.apObservedMs=v.summonObservedMs=UINT32_MAX;
 v.gear=v.gearSource=v.apState=UINT8_MAX;v.gearValid=v.apValid=v.summonValid=1;v.summonActive=0;return v;
}
static P4TwaiTxLifecycleEvent lifecycleEvent(uint32_t index){
 P4TwaiTxLifecycleEvent e{};e.observedUs=UINT64_MAX;e.seq=index;e.kind=e.reason=UINT8_MAX;
 e.tx=controllerTx();e.vehicle=vehicleContext();return e;
}
static P4TwaiErrorEvent driverEvent(uint32_t index){
 P4TwaiErrorEvent e{};e.observedUs=UINT64_MAX-1000u+index;e.seq=index;
 e.ecc=e.status=e.tec=e.rec=e.halFlags=UINT32_MAX;e.tx=controllerTx();e.vehicle=vehicleContext();return e;
}
static P4TwaiRxFrame rxFrame(){
 P4TwaiRxFrame f{};f.observedUs=f.observationOrder=UINT64_MAX;
 f.seq=f.identifier=UINT32_MAX;f.dlc=8;f.flags=1;memset(f.data,255,8);return f;
}
static void fullState(){
 state={};state.consistent=true;state.bootId=UINT32_MAX;state.captureBeginUs=UINT64_MAX-1000u;state.capturedUs=UINT64_MAX;
 state.flashCurrent=state.flashLast=maximalFlash();
 state.flashCount=32;state.flashObserved=state.flashOverwritten=UINT32_MAX;
 for(auto &window:state.flashWindows)window=maximalFlash();
 state.reinitCount=CanDiag::REINIT_CAPACITY;state.reinitObserved=state.reinitOverwritten=UINT32_MAX;
 for(auto &e:state.reinitEvents){e.observedUs=UINT64_MAX;e.seq=e.requestId=UINT32_MAX;
  e.reason=e.diagnosticReason=UINT8_MAX;e.phase=3;e.statusValidMask=0;
  for(uint8_t bus=0;bus<3;++bus){e.statusObservedUs[bus]=UINT64_MAX;e.controllerEpoch[bus]=e.busErrors[bus]=UINT32_MAX;}}

 driverState={};driverState.consistent=true;driverState.bootId=state.bootId;driverState.invalidBus=UINT32_MAX;
 driverState.captureBeginUs=UINT64_MAX-500u;driverState.capturedUs=UINT64_MAX-1u;
 auto &rx=driverState.rxCapture;rx.enabled=1;rx.physicalBus=1;
 rx.controllerSession=rx.observed=rx.overwritten=rx.rxObserved=rx.invalidDlc=UINT32_MAX;rx.count=P4_TWAI_RX_WINDOW_CAPACITY;
 for(auto &w:rx.windows){
  w.seq=w.controllerSession=w.firstErrorSeq=w.lastErrorSeq=w.errorCount=UINT32_MAX;
  w.firstErrorUs=w.lastErrorUs=w.firstErrorOrder=w.lastErrorOrder=w.deadlineUs=w.closedUs=UINT64_MAX;
  w.status=P4_TWAI_RX_COMPLETE;w.preCount=P4_TWAI_RX_PRE_CAPACITY;w.postCount=P4_TWAI_RX_POST_CAPACITY;
  for(auto &f:w.pre)f=rxFrame();for(auto &f:w.post)f=rxFrame();
 }

 for(uint8_t bus=0;bus<3;++bus){
  auto &s=state.buses[bus];s.count=32;s.observed=s.overwritten=s.epoch=UINT32_MAX;
  s.latestStatus=maximalStatus();s.latestTx=maximalTx();
  s.hasStatus=s.hasFirstError=s.hasLatestError=s.hasFirstBusOff=true;
  s.firstError=event(bus,1);s.latestError=event(bus,100);s.firstBusOff=event(bus,2);
  s.lastRxUs=s.lastServiceUs=s.latestStatusUs=UINT64_MAX;s.copiedAtUs=UINT64_MAX-900u+bus;
  s.maxServiceGapUs=s.unmatchedTxResults=UINT32_MAX;s.rxSeen=s.serviceSeen=true;
  for(uint32_t i=0;i<32;++i)s.events[i]=event(bus,10u+i);
  auto &d=driverState.buses[bus];d.count=64;d.observed=164;d.overwritten=100;
  d.copiedAtUs=UINT64_MAX-400u+bus;d.hasFirst=d.hasLast=true;
  d.first=driverEvent(1);d.last=driverEvent(164);
  d.lifecycle.count=32;d.lifecycle.observed=132;d.lifecycle.overwritten=100;
  for(uint32_t i=0;i<32;++i)d.lifecycle.events[i]=lifecycleEvent(101u+i);
  for(uint32_t i=0;i<64;++i)d.events[i]=driverEvent(101u+i);
 }
}
static void testTrafficAges(){
 for(uint32_t age:{0u,10u,1500u,1501u,0x80000010u}){
  clockMs=5000;const uint32_t last=clockMs-age;
  lastCanAFrameMs=lastCanBFrameMs=last;
  for(uint8_t bus=0;bus<3;++bus)p4CanLastRxMs[bus]=p4CanStatusMs[bus]=last;
  auto t=canTrafficUiSnapshot();assert(t.nativeAAgeMs==age&&t.twaiAgeMs==age);
  assert(t.nativeAOnline==(age<=1500)&&t.twaiOnline==(age<=1500));
  String json;JsonWriterArduino writer(json);p4CanWriteStatus(writer,true);writer.finish();
  for(unsigned n=1;n<=3;++n){
   const auto key="\"can"+std::to_string(n);
   assert(json.find(key+"TrafficAgeMs\":"+std::to_string(age))!=std::string::npos);
   assert(json.find(key+"StatusAgeMs\":"+std::to_string(age))!=std::string::npos);
  }
 }
 clockMs=5;lastCanAFrameMs=lastCanBFrameMs=UINT32_MAX-4;
 auto wrap=canTrafficUiSnapshot();assert(wrap.nativeAAgeMs==10&&wrap.twaiOnline);
 for(uint8_t bus=0;bus<3;++bus)p4CanLastRxMs[bus]=p4CanStatusMs[bus]=UINT32_MAX-4;
 String rolled;JsonWriterArduino rolledWriter(rolled);p4CanWriteStatus(rolledWriter,true);rolledWriter.finish();
 for(unsigned n=1;n<=3;++n){const auto key="\"can"+std::to_string(n);
  assert(rolled.find(key+"TrafficAgeMs\":10")!=std::string::npos&&rolled.find(key+"StatusAgeMs\":10")!=std::string::npos);
 }

 clockMs=5000;lastCanAFrameMs=lastCanBFrameMs=0;
 for(uint8_t bus=0;bus<3;++bus)p4CanLastRxMs[bus]=p4CanStatusMs[bus]=0;
 auto unseen=canTrafficUiSnapshot();assert(!unseen.nativeASeen&&!unseen.twaiOnline&&unseen.nativeAAgeMs==0);
 String missing;JsonWriterArduino missingWriter(missing);p4CanWriteStatus(missingWriter,true);missingWriter.finish();
 assert(missing.find("\"can1TrafficSeen\":false")!=std::string::npos&&missing.find("\"can1StatusSeen\":false")!=std::string::npos);
 clockMs=5000;lastCanAFrameMs=lastCanBFrameMs=4990;updateAtMillis=true;
 const auto race=canTrafficUiSnapshot();assert(race.nativeAAgeMs==10&&race.twaiAgeMs==10&&race.nativeAOnline&&"RX after sampled now must not underflow into Offline");
 for(bool duringWrite:{false,true}){
  clockMs=5000;for(uint8_t bus=0;bus<3;++bus)p4CanLastRxMs[bus]=p4CanStatusMs[bus]=4990;
  updateAtMillis=!duringWrite;updateBetweenFields=duringWrite;
  String json;JsonWriterArduino writer(json);p4CanWriteStatus(writer,true);writer.finish();
  for(unsigned n=1;n<=3;++n){const auto key="\"can"+std::to_string(n);
   assert(json.find(key+"TrafficAgeMs\":10")!=std::string::npos);
   assert(json.find(key+"StatusAgeMs\":10")!=std::string::npos);
   assert(json.find(key+"TrafficOnline\":true")!=std::string::npos);
  }
 }
 clockMs=5000;for(uint8_t bus=0;bus<3;++bus){p4CanLastRxMs[bus]=bus==0?4990:bus==1?0:2000;p4CanStatusMs[bus]=bus==0?4900:bus==1?0:2900;}
}
int main(int argc,char **argv){
 assert(argc==2);testTrafficAges();
 assert(p4CanConfiguredBitrate(0)==500000 && p4CanConfiguredBitrate(P4_CAN_COUNT)==0);
 for(bool profile:{true,false}){
  yl=profile;String details;JsonWriterArduino writer(details);p4CanWriteStatus(writer,true);writer.finish();
  server.body=details;save(argv[1],profile?"status-yl.json":"status-other.json");
  String selected;JsonWriterArduino selectedWriter(selected);p4CanWriteStatus(selectedWriter,true,1,"status");selectedWriter.finish();
  server.body=selected;save(argv[1],profile?"selected-yl.json":"selected-other.json");
  String brief;JsonWriterArduino briefWriter(brief);p4CanWriteStatus(briefWriter);briefWriter.finish();
  assert(brief.find("SamplePointPermille")==std::string::npos);
 }
 yl=true;state={};state.consistent=true;state.bootId=73;state.captureBeginUs=90;state.capturedUs=101;
 driverState={};driverState.rxCapture.physicalBus=1;driverState.consistent=true;driverState.bootId=73;driverState.captureBeginUs=102;driverState.capturedUs=109;
 for(uint8_t bus=0;bus<3;++bus)state.buses[bus].copiedAtUs=93u+bus;
 for(uint8_t bus=0;bus<3;++bus)driverState.buses[bus].copiedAtUs=104u+bus;
 resetResponse();invoke();success();save(argv[1],"empty.json");
 fullState();resetResponse();invoke();success();save(argv[1],"full-yl.json");
 const int fullConcats=concatCalls,fullFormats=formatCalls;
 for(uint8_t bus=0;bus<3;++bus){
  auto &b=state.buses[bus];
  b.firstError.seq=b.latestError.seq=b.firstBusOff.seq=UINT32_MAX;
  b.firstError.observedUs=b.latestError.observedUs=b.firstBusOff.observedUs=UINT64_MAX;
  for(auto &row:b.events){row.seq=UINT32_MAX;row.observedUs=UINT64_MAX;}
 }
 for(auto &b:driverState.buses){
  b.observed=b.overwritten=UINT32_MAX;
  b.first.seq=b.last.seq=UINT32_MAX;b.first.observedUs=b.last.observedUs=UINT64_MAX;
  for(auto &row:b.events){row.seq=UINT32_MAX;row.observedUs=UINT64_MAX;}
  b.lifecycle.observed=b.lifecycle.overwritten=UINT32_MAX;
  for(auto &row:b.lifecycle.events){row.seq=UINT32_MAX;}
 }
 driverState.rxCapture.enabled=0;
 resetResponse();invoke();success();save(argv[1],"maximum.json");
 yl=false;resetResponse();invoke();success();save(argv[1],"maximum-other.json");yl=true;
 resetResponse();psramAllocationFails=true;invoke();success(true);
 fullState();
 assert(server.body.size()>100000&&"The full fixture must actually exercise all three 32-row journals");
 yl=false;resetResponse();invoke();success();save(argv[1],"full-other.json");yl=true;
 // Different physical rings, preserved first evidence, partial DLC and signed
 // results must survive one snapshot without borrowing another bus's rows.
 fullState();state.buses[0].count=1;state.buses[1].count=3;state.buses[2].count=0;
 state.buses[0].events[0].tx.dlc=0;state.buses[0].events[0].tx.resultPending=true;state.buses[1].events[0].tx.dlc=1;
 state.buses[1].events[1].tx.result=INT32_MAX;
 driverState.buses[0].count=1;driverState.buses[1].count=3;driverState.buses[2]={};
 driverState.buses[2].copiedAtUs=UINT64_MAX-398u;
 driverState.buses[0].events[0].ecc=0xD9u; // SDK OTHER plus ACK_SLOT.
 driverState.buses[1].events[0].ecc=0x19u; // BIT at ACK_SLOT is not ACK_ERROR.
 driverState.buses[1].events[1].ecc=0xC8u; // CRC sequence is a segment, not CRC-error proof.
 driverState.buses[1].events[2].ecc=0x20u; // Unknown segment keeps its raw code.
 // Four lifecycle stages explicitly share loaded identity only after load;
 // retain invalid raw context and wrap-safe ages without claiming freshness.
 auto &dl=driverState.buses[0].lifecycle;dl.count=4;
 for(uint8_t i=0;i<4;++i){auto &e=dl.events[i];e.kind=i+1;e.reason=i==2?1:(i==3?6:0);
  e.observedUs=5000;e.tx=controllerTx();e.tx.source=2;e.tx.loadedUs=3000;e.tx.queuedUs=2000;e.tx.requestId=73;setRxOrigin(e.tx,1000,1500,91,0);
  e.tx.active=i==1;e.tx.valid=(i==1||i==2);if(!e.tx.valid)e.tx.loadedUs=0;
  e.vehicle={};e.vehicle.publishedMs=UINT32_MAX;e.vehicle.gearObservedMs=UINT32_MAX-2;
  e.vehicle.gear=4;e.vehicle.gearSource=1;e.vehicle.gearValid=1;e.vehicle.apState=7;
 }
 driverState.buses[0].events[0].tx=dl.events[1].tx;
 driverState.buses[0].events[0].vehicle=dl.events[1].vehicle;
 driverState.buses[0].events[0].observedUs=5000;
 setRxOrigin(driverState.buses[1].events[0].tx,UINT64_MAX,UINT64_MAX,0,0); // Sequence alone indicates absence.
 driverState.buses[1].events[0].tx.source=0; // Ordinary source is never inferred from ID.
 driverState.buses[1].events[0].tx.identifier=0x3FD;driverState.buses[1].events[0].tx.active=0;
 auto &rx=driverState.rxCapture;rx.enabled=0;rx.controllerSession=9;
 for(uint8_t i=0;i<4;++i){auto &w=rx.windows[i];w.status=i+1;w.controllerSession=i+1;
  w.firstErrorSeq=10+i;w.lastErrorSeq=20+i;w.firstErrorOrder=30+i;w.lastErrorOrder=40+i;
  w.preCount=i;w.postCount=i==1?16:i;w.pre[0].dlc=0;w.post[0].flags=2;w.post[0].dlc=8;
  if(i==2){w.pre[1].dlc=1;w.pre[1].flags=0;w.pre[1].identifier=0x123;}
 }
 for(uint8_t i=0;i<8;++i){state.reinitEvents[i].phase=i%3+1;state.reinitEvents[i].statusValidMask=i;state.reinitEvents[i].requestId=42;}
 resetResponse();invoke();success();save(argv[1],"mixed.json");
 fullState();resetResponse();allocationFails=true;invoke();failure();assert(snapshotCalls==0&&driverSnapshotCalls==0&&concatCalls==0);
 for(size_t bytes:{sizeof(CanDiag::Snapshot),sizeof(P4TwaiErrorSnapshot)}){
  resetResponse();failedAllocationSize=bytes;invoke();failure();assert(concatCalls==0);
 }
 resetResponse();snapshotFails=true;invoke();failure();assert(snapshotCalls==1&&concatCalls==0);
 resetResponse();driverSnapshotFails=true;invoke();failure();assert(driverSnapshotCalls==1&&concatCalls==0);
 resetResponse();reserveFails=true;invoke();failure();assert(concatCalls==0&&formatCalls==0);
 state.consistent=false;resetResponse();invoke();failure();state.consistent=true;
 driverState.consistent=false;resetResponse();invoke();failure();driverState.consistent=true;
 driverState.bootId--;resetResponse();invoke();failure();driverState.bootId++;
 state.flashCount=33;resetResponse();invoke();failure();state.flashCount=32;
 for(int at:{1,2,10,fullConcats/2,fullConcats}){
  resetResponse();concatFailureAt=at;invoke();failure();assert(concatCalls==at);
 }
 for(int at:{1,10,fullFormats/2,fullFormats}){
  resetResponse();formatFailureAt=at;invoke();failure();assert(formatCalls==at);
  resetResponse();formatTruncationAt=at;invoke();failure();assert(formatCalls==at);
 }
 // Corrupt lengths or wrong physical identities fail closed before HTTP 200.
 for(uint8_t bus=0;bus<3;++bus){
  fullState();state.buses[bus].count=33;resetResponse();invoke();failure();
  fullState();state.buses[bus].latestTx.dlc=9;resetResponse();invoke();failure();
  fullState();state.buses[bus].events[0].bus=(uint8_t)((bus+1)%3);resetResponse();invoke();failure();
  fullState();state.buses[bus].firstError.tx.dlc=255;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].count=65;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].lifecycle.count=33;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].events[0].tx.dlc=9;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].first.tx.flags=4;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].last.tx.valid=2;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].events[0].tx.active=2;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].events[0].tx.active=1;driverState.buses[bus].events[0].tx.valid=0;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].lifecycle.events[0].tx.dlc=255;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].lifecycle.events[0].vehicle.gearValid=2;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].events[0].vehicle.apValid=255;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].events[0].vehicle.summonValid=2;resetResponse();invoke();failure();
  fullState();driverState.buses[bus].events[0].vehicle.summonActive=2;resetResponse();invoke();failure();
 }
 // Invalid new-ring lengths/flags/status cannot leak partial HTTP success.
 fullState();driverState.rxCapture.count=5;resetResponse();invoke();failure();
 fullState();driverState.rxCapture.enabled=2;resetResponse();invoke();failure();
 fullState();driverState.rxCapture.physicalBus=0;resetResponse();invoke();failure();
 fullState();driverState.rxCapture.windows[0].preCount=17;resetResponse();invoke();failure();
 fullState();driverState.rxCapture.windows[0].postCount=17;resetResponse();invoke();failure();
 for(uint8_t status:{0,5}){fullState();driverState.rxCapture.windows[0].status=status;resetResponse();invoke();failure();}
 fullState();driverState.rxCapture.windows[0].pre[0].dlc=9;resetResponse();invoke();failure();
 fullState();driverState.rxCapture.windows[0].post[15].flags=4;resetResponse();invoke();failure();
 fullState();state.reinitCount=9;resetResponse();invoke();failure();
 fullState();state.reinitEvents[7].statusValidMask=8;resetResponse();invoke();failure();
 for(uint8_t phase:{0,4}){fullState();state.reinitEvents[7].phase=phase;resetResponse();invoke();failure();}
 // The real bounded append stops at the exact ceiling without touching the
 // prepared prefix. This exercises a budget failure independently of malloc.
 resetResponse();String limited;std::string prefix(CAN_ERROR_JSON_MAX_BYTES-1u,'x');
 assert(limited.concat(prefix.c_str(),(unsigned int)prefix.size()));
 assert(canDiagJsonAppend(limited,"y",1));const std::string before=limited;
 assert(!canDiagJsonAppend(limited,"z",1)&&limited==before);
 printf("Snapshot heap bytes: general=%zu driver=%zu combined=%zu\n",sizeof(CanDiag::Snapshot),sizeof(P4TwaiErrorSnapshot),sizeof(CanDiag::Snapshot)+sizeof(P4TwaiErrorSnapshot));
 puts("PASS: actual bounded CAN error handler, immutable coherent snapshot, max/mixed physical journals, single response and preparation failures");
}
'''
with tempfile.TemporaryDirectory() as td:
    (Path(td) / 'esp_attr.h').write_text('#pragma once\n#define IRAM_ATTR\n')
    source = Path(td) / 'export.cpp'
    binary = Path(td) / 'export'
    source.write_text(PREAMBLE + '\n#define vsnprintf diagVsnprintf\n' + production + '\n#undef vsnprintf\n' + MAIN)
    compiled = subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I'+td, '-I'+str(ROOT), str(source), '-o', str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, 'INVALID-RED: '+compiled.stdout+compiled.stderr
    result = subprocess.run([str(binary), td], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout+result.stderr
    exports = {name: json.loads((Path(td) / name).read_text()) for name in ('empty.json', 'full-yl.json', 'full-other.json', 'mixed.json', 'maximum.json')}
    empty, full, other, mixed = [exports[name] for name in ('empty.json', 'full-yl.json', 'full-other.json', 'mixed.json')]
    assert empty['schemaVersion'] == 1 and empty['firmware'] == 'v3.34.9' and empty['bootId'] == 73
    assert empty['captureBeginUs'] == '90'
    assert [bus['copiedAtUs'] for bus in empty['buses']] == ['93', '94', '95']
    assert empty['capturedUs'] == '101' and empty['consistent'] is True
    assert [bus['name'] for bus in full['buses']] == ['VEHICLE', 'BODY', 'PARTY']
    assert [bus['name'] for bus in other['buses']] == ['BODY', 'CHASSIS', 'PARTY']
    assert full['captureBeginUs'] == str(2**64-1001)
    assert full['capturedUs'] == str(2**64-1) and full['bootId'] == 2**32-1
    assert empty['flashHistory'] == {'capacity': 32, 'count': 0, 'observed': 0, 'overwritten': 0, 'windows': []}
    history = full['flashHistory']
    assert history['count'] == history['capacity'] == len(history['windows']) == 32
    assert history['observed'] == history['overwritten'] == 2**32-1
    assert all(window == full['flashLast'] for window in history['windows'])
    assert [bus['canNumber'] for bus in full['buses']] == [1, 2, 3]
    assert [bus['physicalBus'] for bus in full['buses']] == [0, 1, 2]
    for bus in empty['buses']:
        assert bus['events'] == [] and bus['count'] == 0 and bus['overwritten'] == 0
        assert bus['firstError'] is None and bus['latestError'] is None and bus['firstBusOff'] is None
        assert bus['hasStatus'] is False
    for index, bus in enumerate(full['buses']):
        assert bus['copiedAtUs'] == str(2**64-901+index)
        assert int(full['captureBeginUs']) <= int(bus['copiedAtUs']) <= int(full['capturedUs'])
        assert bus['count'] == bus['capacity'] == 32 and len(bus['events']) == 32
        assert bus['observed'] == bus['overwritten'] == bus['epoch'] == 2**32-1
        assert [row['seq'] for row in bus['events']] == list(range(10, 42))
        assert all(row['physicalBus'] == index for row in bus['events'])
        assert bus['firstError']['seq'] == 1 and bus['latestError']['seq'] == 100 and bus['firstBusOff']['seq'] == 2
        row = bus['events'][0]
        assert row['status'] == bus['latestStatus'] == row['delta']
        assert row['status']['txPending'] == row['status']['missed'] == row['status']['busErrors'] == 2**32-1
        assert row['tx']['result'] == -(2**31) and row['tx']['dataHex'] == '0011223344556677'
        assert row['tx']['callId'] == row['tx']['resultDelayUs'] == bus['unmatchedTxResults'] == 2**32-1
        assert row['tx']['resultPending'] is False
        assert row['tx']['observedUs'] == str(2**64-1) and row['tx']['called'] is True
        assert row['flashCurrent'] == row['flashLast'] == full['flashCurrent']
        assert row['flashCurrent']['activeCount'] == 65535 and row['flashCurrent']['source'] == 255
        assert row['rxSeen'] and row['serviceSeen'] and row['rxAgeUs'] == row['serviceGapUs'] == 2**32-1
        assert bus['lastRxUs'] == bus['lastServiceUs'] == bus['latestStatusUs'] == str(2**64-1)
    assert [len(bus['events']) for bus in mixed['buses']] == [1, 3, 0]
    assert mixed['buses'][0]['events'][0]['tx']['dataHex'] == ''
    assert mixed['buses'][0]['events'][0]['tx']['resultPending'] is True and mixed['buses'][0]['events'][0]['tx']['result'] is None
    assert mixed['buses'][1]['events'][0]['tx']['dataHex'] == '00'
    assert mixed['buses'][1]['events'][1]['tx']['result'] == 2**31-1
    driver = full['driverErrorCapture']
    assert 'rxCapture' in driver, 'BODY pre/post RX evidence must survive JSON export'
    assert 'reinitializations' in full, 'Hard-reinit history must survive JSON export'
    assert 'configuredTiming' in driver['buses'][0], 'Driver export must disclose supplied timing configuration'
    for profile, expected_points in [('yl', [800, 875, 800]), ('other', [800, 800, 800])]:
        document = full if profile == 'yl' else other
        status_values = json.loads((Path(td) / f'status-{profile}.json').read_text())
        selected = json.loads((Path(td) / f'selected-{profile}.json').read_text())
        for index, bus in enumerate(document['driverErrorCapture']['buses']):
            config = bus['configuredTiming']
            special = profile == 'yl' and index == 1
            assert config == {'bitrate': 500000, 'samplePointPermille': expected_points[index],
                              'timingQuantaHz': 4000000 if special else 10000000,
                              'timingTseg1': 6 if special else 15, 'timingTseg2': 1 if special else 4,
                              'timingSjw': 1 if special else 3, 'timingTripleSampling': False}
            total_tq = 1 + config['timingTseg1'] + config['timingTseg2']
            assert config['timingQuantaHz'] // total_tq == config['bitrate']
            assert 1000 * (1 + config['timingTseg1']) // total_tq == config['samplePointPermille']
            assert config['timingSjw'] <= config['timingTseg2']
            for key, value in config.items():
                status_key = f'can{index+1}' + key[0].upper() + key[1:]
                assert status_values[status_key] == value
                if index == 1:
                    assert selected[status_key] == value
            assert 'supplied to driver' in status_values[f'can{index+1}TimingSemantics']
        assert status_values['can2Ready'] is False and status_values['can2InitResult'] == 'ESP_FAIL'
        assert status_values['can2Mode'] == 'LISTEN_ONLY'
        assert 'can1SamplePointPermille' not in selected and 'can3SamplePointPermille' not in selected
    for phrase in ['supplied to driver', 'not register readback', 'measured waveform', 'mode/init status', '(1+TSEG1)/(1+TSEG1+TSEG2)']:
        assert phrase in driver['semantics']['configuredTiming']
    assert driver['capabilities'].get('controllerLoadedTx') is True, 'ECC exports need actual controller-loaded TX context'
    assert 'r79Lifecycle' in driver['buses'][0], 'R79 lifecycle evidence must survive JSON export'
    assert driver['bootId'] == full['bootId'] and driver['consistent'] is True
    assert driver['captureBeginUs'] == str(2**64-501) and driver['capturedUs'] == str(2**64-2)
    assert driver['captureBeginUs'] != full['captureBeginUs']
    assert driver['invalidBus'] == 2**32-1
    assert driver['capabilities'] == {'rawEcc': True, 'type': True, 'direction': True, 'segment': True,
                                      'failedRxIdentifier': False, 'physicalCause': False, 'wireTimestamps': False,
                                      'controllerLoadedTx': True, 'vehicleContext': True, 'r79Lifecycle': True, 'bodyRxPrePost': True}
    for key, phrase in [('snapshotConsistency', 'independently timed'), ('interrupts', 'coalesced'),
                        ('journalLifetime', 'RAM only'), ('storedEvents', 'routine RX/TX/status'),
                        ('classification', 'CRC segment')]:
        assert phrase in driver['semantics'][key]
    assert 'not an atomic instant across sources' in driver['semantics']['snapshotConsistency']
    assert 'Reset Stats' in driver['semantics']['journalLifetime']
    assert driver['codebook']['types'] == {'0': 'BIT', '1': 'FORM', '2': 'STUFF', '3': 'OTHER'}
    assert driver['codebook']['directions'] == {'0': 'TX', '1': 'RX'}
    assert driver['codebook']['segments']['25'] == 'ACK_SLOT'
    assert driver['codebook']['segments']['8'] == 'CRC_SEQUENCE'
    assert driver['codebook']['segments']['24'] == 'CRC_DELIMITER'
    assert driver['codebook']['segments']['0'] == 'UNKNOWN'
    for bus in empty['driverErrorCapture']['buses']:
        assert bus['events'] == [] and bus['count'] == bus['observed'] == bus['overwritten'] == 0
        assert bus['first'] is None and bus['last'] is None
    assert empty['driverErrorCapture']['captureBeginUs'] == '102'
    assert empty['driverErrorCapture']['capturedUs'] == '109'
    assert [bus['copiedAtUs'] for bus in empty['driverErrorCapture']['buses']] == ['104', '105', '106']
    for index, bus in enumerate(driver['buses']):
        assert bus['physicalBus'] == index and bus['canNumber'] == index+1
        assert bus['name'] == ['VEHICLE', 'BODY', 'PARTY'][index]
        assert bus['count'] == bus['capacity'] == len(bus['events']) == 64
        assert bus['observed'] == 164 and bus['overwritten'] == 100
        assert bus['first']['seq'] == 1 and bus['last']['seq'] == 164
        assert [row['seq'] for row in bus['events']] == list(range(101, 165))
        assert bus['copiedAtUs'] == str(2**64-401+index)
        assert int(driver['captureBeginUs']) <= int(bus['copiedAtUs']) <= int(driver['capturedUs'])
        row = bus['events'][0]
        assert {k:v for k,v in row.items() if k not in ('tx', 'vehicle')} == {'observedUs': str(2**64-900), 'seq': 101, 'ecc': 2**32-1,
                       'status': 2**32-1, 'tec': 2**32-1, 'rec': 2**32-1, 'halFlags': 2**32-1,
                       'type': 3, 'direction': 1, 'segment': 31, 'ackError': False}
        tx = row['tx']
        assert tx == {'valid': True, 'active': False, 'loadedUs': str(2**64-1),
                      'queuedUs': str(2**64-1), 'requestId': 2**32-1, 'identifier': 2**32-1, 'dlc': 8, 'source': 255, 'flags': 3,
                      'dataHex': '0011223344556677',
                      'rxOrigin': {'sequence': str(2**32-1), 'observedUs': str(2**64-1), 'dequeuedUs': str(2**64-1)}}
        vehicle = row['vehicle']
        assert vehicle['publishedMs'] == vehicle['gearObservedMs'] == vehicle['apObservedMs'] == vehicle['summonObservedMs'] == 2**32-1
        assert vehicle['gear'] == vehicle['gearSource'] == vehicle['apState'] == 255
        assert vehicle['gearValid'] is True and vehicle['apValid'] is True and vehicle['summonValid'] is True
        age = ((int(row['observedUs'])//1000) - (2**32-1)) % 2**32
        assert vehicle['publicationAgeMs'] == vehicle['gearAgeMs'] == vehicle['apAgeMs'] == vehicle['summonAgeMs'] == age
        lifecycle = bus['r79Lifecycle']
        assert lifecycle['capacity'] == lifecycle['count'] == len(lifecycle['events']) == 32
        assert lifecycle['observed'] == 132 and lifecycle['overwritten'] == 100
        assert [event['seq'] for event in lifecycle['events']] == list(range(101,133))
        assert all(event['tx'] == tx for event in lifecycle['events'])
    assert [bus['name'] for bus in other['driverErrorCapture']['buses']] == ['BODY', 'CHASSIS', 'PARTY']
    mixed_driver = mixed['driverErrorCapture']['buses']
    assert [len(bus['events']) for bus in mixed_driver] == [1, 3, 0]
    assert mixed_driver[0]['events'][0]['ecc'] == 0xD9 and mixed_driver[0]['events'][0]['ackError'] is True
    assert mixed_driver[1]['events'][0]['ecc'] == 0x19 and mixed_driver[1]['events'][0]['ackError'] is False
    assert mixed_driver[1]['events'][1]['segment'] == 8 and mixed_driver[1]['events'][1]['ackError'] is False
    assert mixed_driver[1]['events'][2]['segment'] == 0 and mixed_driver[1]['events'][2]['direction'] == 1
    assert mixed_driver[2]['first'] is None and mixed_driver[2]['last'] is None
    mixed_events = mixed_driver[0]['r79Lifecycle']['events']
    assert [event['kind'] for event in mixed_events] == [1,2,3,4]
    assert [event['reason'] for event in mixed_events] == [0,0,1,6]
    assert [event['tx']['valid'] for event in mixed_events] == [False,True,True,False]
    assert [event['tx']['active'] for event in mixed_events] == [False,True,False,False]
    assert [event['tx']['loadedUs'] for event in mixed_events] == ['0','3000','3000','0']
    assert all(e['tx']['requestId'] == 73 and e['tx']['queuedUs'] == '2000' for e in mixed_events)
    assert all(e['tx']['rxOrigin'] == {'sequence':'91','observedUs':'1000','dequeuedUs':'1500'} for e in mixed_events)
    completed = mixed_events[2]
    assert [int(completed['tx']['rxOrigin']['observedUs']), int(completed['tx']['rxOrigin']['dequeuedUs']),
            int(completed['tx']['queuedUs']), int(completed['tx']['loadedUs']), int(completed['observedUs'])] == [1000,1500,2000,3000,5000]
    assert mixed_driver[0]['events'][0]['tx'] == mixed_events[1]['tx']
    context = mixed_driver[0]['events'][0]['vehicle']
    assert context['publicationAgeMs'] == 6 and context['gearAgeMs'] == 8
    assert context['apState'] == 7 and context['apValid'] is False and context['apAgeMs'] is None
    assert context['summonValid'] is False and context['summonAgeMs'] is None
    assert mixed_driver[1]['events'][0]['tx']['source'] == 0
    assert mixed_driver[1]['events'][0]['tx']['identifier'] == 0x3FD
    assert mixed_driver[1]['events'][0]['tx']['active'] is False
    assert 'rxOrigin' not in mixed_driver[1]['events'][0]['tx']
    assert driver['codebook']['gearSources'] == {'NONE':0,'CAN_0x118':1,'CAN_0x186':2}
    assert driver['contextVersion'] == 1
    assert driver['codebook']['txSources'] == {'UNKNOWN':0,'R79_UNKNOWN':1,'R79_IMMEDIATE':2,'R79_PERIODIC':3}
    assert driver['codebook']['lifecycleReasons']['DEADLINE'] == 6
    for key,phrase in [('controllerTx','not wire start'),('controllerTx','RX error identifier remains unknown'),
                       ('vehicleContext','not simultaneous physical measurement'),('vehicleContext','modulo-2^32'),
                       ('rxOrigin','exact decimal strings'),('rxOrigin','neither is a physical wire timestamp'),
                       ('rxOrigin','nonzero wrapping RX token'),('r79Lifecycle','not ECU acceptance'),('r79Lifecycle','overwritten')]:
        assert phrase in driver['semantics'][key]
    for bus in empty['driverErrorCapture']['buses']:
        assert bus['r79Lifecycle'] == {'capacity':32,'count':0,'observed':0,'overwritten':0,'events':[]}
    for bus in exports['maximum.json']['driverErrorCapture']['buses']:
        assert bus['r79Lifecycle']['observed'] == bus['r79Lifecycle']['overwritten'] == 2**32-1
        assert all(e['seq'] == 2**32-1 for e in bus['r79Lifecycle']['events'])
    capture = driver['rxCapture']
    assert capture['version'] == 1 and capture['enabled'] is True and capture['physicalBus'] == 1
    assert capture['capacity'] == capture['count'] == len(capture['windows']) == 4
    assert capture['preCapacity'] == capture['postCapacity'] == 16 and capture['postTimeoutUs'] == 100000
    assert capture['controllerSession'] == capture['observed'] == capture['overwritten'] == capture['rxObserved'] == capture['invalidDlc'] == 2**32-1
    for window in capture['windows']:
        assert window['status'] == 2 and window['postPartial'] is False
        assert window['preCount'] == window['postCount'] == len(window['pre']) == len(window['post']) == 16
        for key in ('seq','controllerSession','firstErrorSeq','lastErrorSeq','errorCount'):
            assert window[key] == 2**32-1
        for key in ('firstErrorUs','lastErrorUs','firstErrorOrder','lastErrorOrder','deadlineUs','closedUs'):
            assert window[key] == str(2**64-1)
        for frame in window['pre'] + window['post']:
            assert frame == {'observedUs':str(2**64-1),'observationOrder':str(2**64-1),
                             'seq':2**32-1,'identifier':2**32-1,'dlc':8,'flags':1,'dataHex':'FFFFFFFFFFFFFFFF'}
    assert empty['driverErrorCapture']['rxCapture']['windows'] == []
    assert empty['driverErrorCapture']['rxCapture']['enabled'] is False
    mixed_capture = mixed['driverErrorCapture']['rxCapture']
    assert mixed_capture['enabled'] is False and mixed_capture['controllerSession'] == 9
    assert [w['status'] for w in mixed_capture['windows']] == [1,2,3,4]
    assert [w['postPartial'] for w in mixed_capture['windows']] == [True,False,True,True]
    for i, window in enumerate(mixed_capture['windows']):
        assert window['controllerSession'] == i+1 and window['firstErrorSeq'] == 10+i and window['lastErrorSeq'] == 20+i
        assert window['firstErrorOrder'] == str(30+i) and window['lastErrorOrder'] == str(40+i)
        if i:
            assert window['pre'][0]['dataHex'] == '' and window['pre'][0]['dlc'] == 0
            assert window['post'][0]['dataHex'] == '' and window['post'][0]['dlc'] == 8 and window['post'][0]['flags'] == 2
    assert mixed_capture['windows'][2]['pre'][1]['dataHex'] == 'FF'
    assert mixed_capture['windows'][2]['pre'][1]['identifier'] == 0x123
    assert driver['codebook']['rxWindowStatuses'] == {'COLLECTING':1,'COMPLETE':2,'EXPIRED':3,'RECONFIGURED':4}
    for phrase in ('successful RX', 'ISR software observation order', 'not wire order', 'failed RX identifier', 'FIFO backlog'):
        assert phrase in driver['semantics']['rxCapture']
    for phrase in ('Reset Stats', 'controllerSession', 'postPartial', 'overwritten', 'RECONFIGURED'):
        assert phrase in driver['semantics']['rxWindowLifetime']
    history = full['reinitializations']
    assert history['count'] == history['capacity'] == len(history['events']) == 8
    assert history['observed'] == history['overwritten'] == 2**32-1
    for event in history['events']:
        assert event['observedUs'] == str(2**64-1) and event['seq'] == event['requestId'] == 2**32-1
        assert event['reason'] == event['diagnosticReason'] == 255 and event['phase'] == 3
        assert event['statusValidMask'] == 0
        for bus, row in enumerate(event['buses']):
            assert row == {'physicalBus':bus,'controllerEpoch':2**32-1,'busErrors':2**32-1,
                           'statusObservedUs':str(2**64-1),'statusValid':False}
    assert empty['reinitializations'] == {'capacity':8,'count':0,'observed':0,'overwritten':0,'events':[]}
    for i, event in enumerate(mixed['reinitializations']['events']):
        assert event['phase'] == i%3+1 and event['statusValidMask'] == i and event['requestId'] == 42
        assert [b['statusValid'] for b in event['buses']] == [bool(i&(1<<b)) for b in range(3)]
    assert full['reinitializationCodebook']['phases'] == {'BEGIN':1,'SUCCESS':2,'FAILED':3}
    assert full['reinitializationCodebook']['reasons'] == {'NONE':0,'ACQUIRE':1,'STALE':2,'MANUAL':3}
    for phrase in ('cached diagnostics','not simultaneous hardware readback','requestId','overwritten','Reset Stats'):
        assert phrase in full['reinitializationSemantics']
    semantics = full['semantics']
    assert semantics['uint64Encoding'] == 'decimal strings'
    assert 'retained events structurally coherent' in semantics['snapshotConsistency']
    assert 'bounded capture interval' in semantics['snapshotConsistency']
    assert 'copiedAtUs' in semantics['snapshotConsistency'] and 'not an atomic instant' in semantics['snapshotConsistency']
    assert '50000' in semantics['serviceTiming']
    assert full['reasonBits']['SERVICE_GAP'] == 4096
    for key, phrase in [('timeSource', 'software observation'), ('txResult', 'not wire completion'), ('alerts', 'coalesced'), ('journalLifetime', 'RAM only'), ('counterLifetime', 'epoch'), ('serviceTiming', 'does not prove cause'), ('flashScope', 'SDK-internal')]:
        assert phrase in semantics[key]
    assert full['reasonBits']['COUNTER_RESET'] == 32 and full['reasonBits']['RECOVERY_ACCEPTED'] == 256 and full['reasonBits']['BUS_OFF_ALERT'] == 2048
    assert semantics['autoPersistence'] is False and 'Reset Stats' in semantics['journalLifetime']
    assert full['appNvsSources'] == {'SETTINGS': 1, 'BLE_REGISTRY': 2, 'PREHEAT': 3, 'BUS_OFF_EVIDENCE': 4, 'WEB_RESET_NETWORK': 5, 'USB': 6, 'CONTINUOUS_AP': 7, 'CHECKED_BLOB': 8}
    assert full['txSources']['R79_REINJECT'] == 7 and full['txSources']['DISPLAY'] == 9
    # Recompile the same handler with a constrained preparation budget. This
    # exercises its HTTP failure path on a valid snapshot that exceeds the
    # allowed response size; production retains the measured 416 KiB ceiling.
    assert production.count('416u * 1024u') == 1
    budget_main = MAIN[:MAIN.index('int main(')] + r'''
int main(int argc,char **argv){assert(argc==2);testTrafficAges();assert(p4CanConfiguredBitrate(0)==500000);String details;JsonWriterArduino writer(details);p4CanWriteStatus(writer,true);writer.finish();fullState();resetResponse();invoke();if(server.status==200){success();save(argv[1],"unexpected.json");}failure();assert(concatCalls>0&&formatCalls>0);}
'''
    budget_source = Path(td) / 'budget.cpp'
    budget_binary = Path(td) / 'budget'
    budget_source.write_text(PREAMBLE + '\n#define vsnprintf diagVsnprintf\n' + production.replace('416u * 1024u', '64u * 1024u') + '\n#undef vsnprintf\n' + budget_main)
    budget_compile = subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I'+td, '-I'+str(ROOT), str(budget_source), '-o', str(budget_binary)], capture_output=True, text=True)
    assert budget_compile.returncode == 0, 'INVALID-RED: '+budget_compile.stdout+budget_compile.stderr
    budget_run = subprocess.run([str(budget_binary), td], capture_output=True, text=True, timeout=15)
    assert budget_run.returncode == 0, budget_run.stdout+budget_run.stderr
    full_bytes = max((Path(td) / name).stat().st_size for name in ('maximum.json', 'maximum-other.json'))
    maximum_other = json.loads((Path(td) / 'maximum-other.json').read_text())
    assert [bus['configuredTiming']['samplePointPermille'] for bus in maximum_other['driverErrorCapture']['buses']] == [800, 800, 800]
    assert full_bytes <= 416*1024
    print(result.stdout.strip())
    print(f'PASS: parsed independent JSON schema/value assertions; maximum fixture {full_bytes} bytes / 425984-byte budget')
