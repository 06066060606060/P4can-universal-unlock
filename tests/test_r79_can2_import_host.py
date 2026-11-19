"""Actual web-owned importer: bounded late ISR rows, loss and session isolation."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CODE = r'''
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include "r79_timing_capture.h"
#include "r79_timing_driver.h"
thread_local unsigned timingLockDepth=0;
void timingBeforeLock(){}
static int64_t nowUs=1000;
static bool failAlloc=true, failSnapshot=false;
static unsigned allocations=0, snapshots=0;
static bool advanceDuringSnapshot=false;
static bool expireDuringSnapshot=false;
static uint64_t targetExpiry=0;
static P4TwaiErrorSnapshot source{};
int64_t esp_timer_get_time(){return nowUs;}
void* heap_caps_malloc(size_t bytes,uint32_t caps){
 assert(timingLockDepth==0&&caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
 assert(bytes==sizeof(P4TwaiErrorSnapshot)||bytes==32768*sizeof(p4_r79_timing::Event));
 ++allocations;return failAlloc?nullptr:std::malloc(bytes);
}
bool p4TwaiDiagSnapshot(P4TwaiErrorSnapshot*out){
 assert(timingLockDepth==0);++snapshots;if(failSnapshot)return false;
 if(advanceDuringSnapshot){
  source.buses[1].first.observedUs=uint64_t(nowUs+5);
  source.buses[1].events[0].observedUs=uint64_t(nowUs+5);
  nowUs+=10;advanceDuringSnapshot=false;
 }
 *out=source;
 if(expireDuringSnapshot){
  expireDuringSnapshot=false;
  source.buses[1].observed=8;source.buses[1].count=1;
  source.buses[1].events[0].seq=8;source.buses[1].events[0].observedUs=targetExpiry-1;
  source.buses[1].events[0].ecc=170;source.buses[1].events[0].rec=4;source.buses[1].events[0].status=44;
  source.buses[1].first=source.buses[1].events[0];source.buses[1].hasFirst=true;
  nowUs=(int64_t)targetExpiry+1;
 }
 return true;
}
static P4TwaiErrorEvent error(uint32_t seq,uint64_t us){
 P4TwaiErrorEvent e{};e.seq=seq;e.observedUs=us;e.ecc=170;e.tec=0;e.rec=4;e.status=44;return e;
}
static void setErrors(std::initializer_list<P4TwaiErrorEvent> errors,uint32_t observed){
 auto &bus=source.buses[1];bus={};bus.observed=observed;
 for(const auto&e:errors)bus.events[bus.count++]=e;
 if(bus.count){bus.first=bus.events[0];bus.last=bus.events[bus.count-1];bus.hasFirst=bus.hasLast=true;}
}
static unsigned countError(uint32_t seq){
 const auto snapshot=p4R79TimingSnapshot();unsigned count=0;
 for(uint32_t i=0;i<snapshot.count;++i){p4_r79_timing::Event e{};assert(p4R79TimingRead(i,e));
  if(e.kind==p4_r79_timing::CAN_ERROR&&e.errorSeq==seq){++count;assert(e.bus==1&&e.ecc==170&&e.rec==4&&e.status==44&&e.importedUs>=e.timeUs);}}
 return count;
}
int main(){
 source.bootId=1234;
 p4R79TimingDriverPoll();assert(!allocations&&!snapshots);
 assert(!p4R79TimingDriverPrepare()&&p4_r79_driver::state.allocationFailed);
 failAlloc=false;failSnapshot=true;assert(!p4R79TimingDriverPrepare());
 failSnapshot=false;assert(p4R79TimingDriverPrepare());
 assert(p4R79TimingStart());p4R79TimingDriverStarted();
 assert(p4_r79_driver::state.bootId==1234);
 twai_message_t frame{};frame.identifier=0x3FD;frame.data_length_code=8;frame.data[0]=1;
 nowUs=1050;p4R79TimingRx(0,frame);
 nowUs=1100;auto token=p4R79TimingTxBegin(0,&frame,2,15);assert(token.valid);
 nowUs=1123;p4R79TimingTxEnd(token,&frame,0,true);
 p4_r79_timing::Event call{},done{};assert(p4R79TimingRead(1,call)&&p4R79TimingRead(2,done));
 assert(call.rxSequence==1&&call.rxUs==1050&&call.timeUs-call.rxUs==50&&call.readyMask==15);
 assert(done.callId==call.callId&&done.rxSequence==1&&done.timeUs-done.callUs==23);
 setErrors({error(1,1060)},1);nowUs=120000;advanceDuringSnapshot=true;p4R79TimingDriverPoll(true);
 assert(countError(1)==1&&p4_r79_driver::state.imported==1);
 p4R79TimingDriverPoll(true);assert(countError(1)==1);
 setErrors({error(4,120020),error(5,120030)},5);source.buses[1].first=error(1,120005);nowUs=120100;
 p4R79TimingDriverPoll(true);assert(countError(4)==1&&countError(5)==1&&p4_r79_driver::state.lost==2);
 failSnapshot=true;p4R79TimingDriverPoll(true);
 assert(p4_r79_driver::state.pending&&p4_r79_driver::state.failures==1);
 failSnapshot=false;
 nowUs=130000;p4R79TimingStop();
 setErrors({error(6,129999),error(7,130001)},7);p4R79TimingDriverPoll(true);
 assert(countError(6)==1&&countError(7)==0&&p4_r79_driver::state.finished&&!p4_r79_driver::state.pending);
 p4_r79_timing::Snapshot exported{};assert(p4R79TimingBeginExport(exported));
 const auto before=snapshots;p4R79TimingDriverPoll(true);assert(snapshots==before);p4R79TimingEndExport();
 // A new session must neither import previous errors nor retain old RX context.
 nowUs=200000;assert(p4R79TimingDriverPrepare());assert(p4R79TimingStart());p4R79TimingDriverStarted();
 nowUs=200001;token=p4R79TimingTxBegin(0,&frame,0,13);assert(token.event.rxSequence==0&&token.event.rxUs==0);
 const uint64_t expiry=200000+UINT64_C(600000000);
 targetExpiry=expiry;nowUs=expiry-10;expireDuringSnapshot=true;
 p4R79TimingDriverPoll(true);
 assert(!p4R79TimingSnapshot().active&&!p4_r79_driver::state.finished);
 setErrors({error(8,expiry-1),error(9,expiry)},9);nowUs=expiry+200000;
 p4R79TimingDriverPoll();assert(countError(8)==1&&countError(9)==0&&p4_r79_driver::state.finished);
 // Counter saturation is explicit, never a false claim of complete capture.
 nowUs=expiry+200100;assert(p4R79TimingDriverPrepare());assert(p4R79TimingStart());p4R79TimingDriverStarted();
 setErrors({error(UINT32_MAX,nowUs+1)},UINT32_MAX);nowUs+=2;p4R79TimingDriverPoll(true);
 assert(p4_r79_driver::state.saturated&&p4_r79_driver::state.lost>0);
 source.bootId=4321;p4R79TimingDriverPoll(true);assert(p4_r79_driver::state.pending);
 assert(timingLockDepth==0);
 puts("PASS: actual importer disabled fast path, PSRAM/snapshot failures, late ordered ISR evidence, dedup/gaps, stop/expiry tail, session/RX fence, saturation, boot and export fences");
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'import.cpp'
    executable = Path(directory) / 'import'
    source.write_text(CODE.replace('#include <cstdio>', '#include <cstdio>\n#include <initializer_list>'))
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-I' + str(ROOT / 'tests/r79_timing_fakes'), '-I' + str(ROOT),
                    str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
