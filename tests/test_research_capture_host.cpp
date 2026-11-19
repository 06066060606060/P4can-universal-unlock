// Real recorder regression: reject a trigger that copies the whole PRE ring
// while interrupts are disabled; preserve chronological bytes across overwrite.
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <string>
#include <algorithm>
struct String : std::string { using std::string::string; void trim() {} };
struct Preferences {
 bool begin(const char*, bool){return true;} void end(){}
 String getString(const char*,const char*v){return String(v);}
 uint32_t getUInt(const char*,uint32_t v){return v;} uint8_t getUChar(const char*,uint8_t v){return v;}
 size_t putString(const char*,const char*v){return std::strlen(v);}
 size_t putUInt(const char*,uint32_t){return 4;} size_t putUChar(const char*,uint8_t){return 1;}
};
static uint32_t nowMs=6000; static uint32_t millis(){return nowMs;}
static bool labMenuEnabled=true;
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
static bool held=false; static size_t lockBytes=0,maxLockBytes=0;
static void (*interleave)() = nullptr; static bool injecting=false;
static void enter(portMUX_TYPE*){assert(!held);held=true;lockBytes=0;}
static void leave(portMUX_TYPE*){assert(held);held=false;maxLockBytes=std::max(maxLockBytes,lockBytes);if(interleave && !injecting){injecting=true;interleave();injecting=false;}}
#define portENTER_CRITICAL enter
#define portEXIT_CRITICAL leave
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
static size_t failAllocationBytes=0;
static void* heap_caps_malloc(size_t n,int caps){assert(!held && caps==3);return n==failAllocationBytes?nullptr:std::malloc(n);}
static void heap_caps_free(void*p){assert(!held);std::free(p);}
#define P4CAN_SERIAL_PRINTF(...) std::printf(__VA_ARGS__)
static void* checkedMemset(void*d,int c,size_t n){if(held)lockBytes+=n;return std::memset(d,c,n);}
static void* checkedMemcpy(void*d,const void*s,size_t n){if(held)lockBytes+=n;return std::memcpy(d,s,n);}
struct RoadContext238Pure {bool valid;uint8_t roadClass;bool gpsRoadMatch,navRouteActive,controlledAccess,nextBranchLeftOffRamp,nextBranchRightOffRamp;};
static RoadContext238Pure decodeRoadContext238Pure(const uint8_t*,uint8_t){return {};}
static uint8_t readDASState4(const uint8_t*){return 0;}
#include "../can_research_capture_pure.h"
#define memcpy checkedMemcpy
#define memset checkedMemset
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
// Preserve the public declaration supplied by p4can_forward.h in the firmware TU.
static void researchCaptureReset();
#include "../can_research_capture.h"
#pragma GCC diagnostic pop
#undef memcpy
#undef memset
static void seed(uint32_t start=0){
 researchCaptureMode=RESEARCH_CAPTURE_MODE_RAW_TRANSITION;researchCaptureReset();
 researchCaptureRawPreStartIndex=start;researchCaptureRawPreFrameCount=32768;
 for(uint32_t i=0;i<32768;i++){
  auto&e=researchCaptureRawPreBase()[(start+i)%32768];e={};e.timestampMs=1000+i/8;e.id=i%2048;e.dlc=8;std::memcpy(e.data,&i,4);
 }
 maxLockBytes=0;
}
static void validatePre(){
 for(uint32_t i=0;i<32768;i++){const auto&e=researchCaptureRawArchiveBase()[i];uint32_t seq;std::memcpy(&seq,e.data,4);assert(seq==i);assert(e.timestampMs==1000+i/8);}
}

static void drain(){for(unsigned i=0;i<2048 && researchCaptureRawCopyPendingLocked();i++)researchCaptureService();assert(!researchCaptureRawCopyPendingLocked());}
static void frame(){uint8_t data[8]={0xEE};researchCaptureObserve(1,0x321,8,data);}
static void testDeferredAndOverwrite(){
 for(uint32_t start: {0U,31763U}) {
  nowMs=6000;seed(start);assert(researchCaptureRequest(0));
  assert(maxLockBytes<=512 && "trigger must not copy 512 KiB under one critical section");
  assert(researchCaptureRawCopyPendingLocked());
  assert(!researchCaptureRequest(1));assert(!researchCaptureSetMode(0));
  assert(!researchCaptureSetConfig(5000,2000));
  auto* archive=researchCaptureEntries;auto* pre=researchCapturePreStates;
  researchCaptureReleaseModeBuffers();assert(researchCaptureEntries==archive && researchCapturePreStates==pre);
  assert(researchCaptureEnsureBuffer());assert(researchCaptureEntries==archive && researchCapturePreStates==pre);
  // Overwrite the entire frozen ring without allowing the service to run.
  // Each producer must rescue exactly its next original row before reuse.
  for(unsigned i=0;i<32768;i++)frame();
  assert(!researchCaptureRawCopyPendingLocked());validatePre();
  assert(researchCaptureRawArchiveCount==65536);
  assert(researchCaptureSegments[0].rawFrameCount==65536);
  assert(maxLockBytes<=512);
 }
 // Service and producer interleave on every lock release, including wrap.
 nowMs=6000;seed(32755);assert(researchCaptureRequest(0));
 interleave=frame;drain();interleave=nullptr;validatePre();assert(maxLockBytes<=512);
}
static void testExpiryAndCompletion(){
 nowMs=6000;seed(31763);assert(researchCaptureRequest(0));
 // All PRE timestamps expire at once. Eviction must not lose frozen bytes.
 nowMs=12000;frame();assert(researchCaptureRawPreFrameCount==1);
 researchCaptureTick(nowMs);assert(!researchCaptureRawTriggered);
 uint32_t count=researchCaptureRawArchiveCount;frame();assert(researchCaptureRawArchiveCount==count);
 assert(researchCaptureState==RESEARCH_CAPTURE_CAPTURING);
 drain();validatePre();researchCaptureTick(nowMs);
 assert(researchCaptureCompletedSegments==1 && researchCaptureState==RESEARCH_CAPTURE_READY);
 assert(researchCaptureRequest(1));drain();
 assert(researchCaptureSegments[1].rawStartIndex==count);
 assert(researchCaptureSegments[1].rawFrameCount==2);
 validatePre();
}
static void testClearExportAndFull(){
 nowMs=6000;seed();assert(researchCaptureRequest(0));researchCaptureService();
 assert(researchCaptureRawCopyPendingLocked());researchCaptureReset();
 assert(!researchCaptureRawCopyPendingLocked());researchCaptureService();assert(researchCaptureCount==0);
 assert(researchCaptureRequest(0));drain();assert(researchCaptureRawArchiveCount==0);
 seed();researchCaptureExporting=true;
 assert(!researchCaptureRequest(0));researchCaptureReset();assert(researchCaptureRawPreFrameCount==32768);
 assert(!researchCaptureSetMode(0));frame();assert(researchCaptureRawArchiveCount==0);
 researchCaptureExporting=false;
 seed();researchCaptureRawArchiveCount=RESEARCH_CAPTURE_RAW_ARCHIVE_CAPACITY-17;
 researchCaptureCount=researchCaptureRawArchiveCount;
 assert(!researchCaptureRequest(0));assert(researchCaptureState==RESEARCH_CAPTURE_FULL);
 assert(researchCaptureRawCopyPendingLocked());assert(!researchCaptureSetMode(0));
 drain();assert(researchCaptureRawArchiveCount==RESEARCH_CAPTURE_RAW_ARCHIVE_CAPACITY);
 for(uint32_t i=0;i<17;i++){uint32_t seq;std::memcpy(&seq,researchCaptureRawArchiveBase()[RESEARCH_CAPTURE_RAW_ARCHIVE_CAPACITY-17+i].data,4);assert(seq==i);}
 assert(researchCaptureDropped==1);
}
static void resetBetweenChunks(){researchCaptureReset();interleave=nullptr;}
static void testClearAtServiceBoundary(){
 nowMs=6000;seed();assert(researchCaptureRequest(0));interleave=resetBetweenChunks;
 researchCaptureService();assert(!researchCaptureRawCopyPendingLocked());assert(researchCaptureCount==0);
 assert(researchCaptureRequest(2));drain();assert(researchCaptureRawArchiveCount==0);
}
static void testAutoDelayedAndRollover(){
 seed(32765);researchCaptureMode=RESEARCH_CAPTURE_MODE_RAW_AUTO_ALC;
 // Real AUTO transition: OPEN baseline -> BLOCKED persists for 300 ms.
 auto alc=[](uint8_t value){uint8_t data[8]={};data[5]=(value&3)<<6;data[6]=value>>2;researchCaptureObserve(0,0x399,8,data);};
 nowMs=6000;alc(8);nowMs=6100;alc(1);nowMs=6400;alc(1);
 assert(researchCaptureAutoTriggerCount==1);assert(researchCaptureSegments[0].triggerMs==6100);
 assert(researchCaptureRawCopyPendingLocked());assert(maxLockBytes<=512);drain();
 const auto&m=researchCaptureSegments[0];const auto*base=researchCaptureRawArchiveBase();
 assert(base[m.rawStartIndex].timestampMs==4100);
 assert(base[m.rawStartIndex+m.rawFrameCount-1].timestampMs==6400);
 assert(base[m.rawStartIndex+m.rawFrameCount-2].timestampMs==6100);
 // Equal timestamps and uint32 wrap, inclusive lower window edge.
 ResearchCaptureRawEntry entries[6]={};
 const uint32_t stamps[]={0xFFFFFFF0U,0xFFFFFFF0U,0xFFFFFFFAU,0U,5U,5U};
 for(unsigned i=0;i<6;i++)entries[(4+i)%6].timestampMs=stamps[i];
 auto plan=researchRawCopyPlanPure(entries,6,4,6,5,15,6);
 assert(plan.ringStart==0 && plan.count==4 && !plan.truncated);
 plan=researchRawCopyPlanPure(entries,6,4,6,5,15,2);assert(plan.count==2 && plan.truncated);
 plan=researchRawCopyPlanPure(entries,6,4,6,6,0,6);assert(plan.count==0);
 plan=researchRawCopyPlanPure(entries,6,4,6,5,0,6);assert(plan.count==2 && plan.ringStart==2);
}
static uint32_t timestampReads;
struct CountedTimestamp {uint32_t value;operator uint32_t() const {++timestampReads;return value;}};
static void testSnapshotUnchanged(){
 researchCaptureReset();assert(researchCaptureSetMode(RESEARCH_CAPTURE_MODE_SNAPSHOT));
 nowMs=500;frame();researchCaptureTick(nowMs);nowMs=1000;researchCaptureTick(nowMs);
 nowMs=1100;assert(researchCaptureRequest(0));assert(researchCaptureLastPreSnapshotsCopied==2);
 assert(researchCaptureLastTriggerRows>0);nowMs=6100;researchCaptureTick(nowMs);
 assert(researchCaptureState==RESEARCH_CAPTURE_PAUSED && researchCaptureCompletedSegments==1);
 assert(researchCaptureLastPostSnapshotsCopied==4);
}
static void testSnapshotLockBoundAndHiddenLab(){
 researchCaptureReset();assert(researchCaptureSetMode(RESEARCH_CAPTURE_MODE_SNAPSHOT));
 researchCaptureKnownIds=0;std::memset(researchCaptureLatest,0,RESEARCH_CAPTURE_LATEST_BYTES);
 nowMs=1000;
 for(unsigned i=0;i<RESEARCH_CAPTURE_STATE_COUNT;i++){
  uint8_t data[8]={};std::memcpy(data,&i,4);
  researchCaptureObserve(i/2048,i%2048,8,data);
 }
 maxLockBytes=0;researchCaptureTick(nowMs);
 assert(maxLockBytes<=512 && "SNAPSHOT tick must release capture lock between bounded row chunks");
 nowMs=1100;maxLockBytes=0;assert(researchCaptureRequest(0));
 assert(maxLockBytes<=512 && "SNAPSHOT trigger must release capture lock between bounded row chunks");
 labMenuEnabled=false;nowMs=6100;researchCaptureTick(nowMs);
 assert(researchCaptureState!=RESEARCH_CAPTURE_CAPTURING);
 assert(researchCaptureRequest(1));labMenuEnabled=true;

 researchCaptureReset();assert(researchCaptureRequest(1));
}
static void seedSnapshot(unsigned ids=64){
 labMenuEnabled=true;researchCaptureReset();
 assert(researchCaptureSetMode(RESEARCH_CAPTURE_MODE_SNAPSHOT));
 researchCaptureKnownIds=0;std::memset(researchCaptureLatest,0,RESEARCH_CAPTURE_LATEST_BYTES);
 researchCaptureTx3f8Valid=0;nowMs=1000;
 for(unsigned i=0;i<ids;i++){
  uint8_t data[8]={};std::memcpy(data,&i,4);
  researchCaptureObserve(i/2048,i%2048,8,data);
 }
}
static unsigned snapshotInterleaves;
static void mutateDuringSnapshot(){
 if(!researchCaptureSnapshotBusy)return;
 ++snapshotInterleaves;
 uint8_t changed[8]={0xEF};
 researchCaptureObserve(0,63,8,changed);researchCaptureObserve(0,0,8,changed);
 researchCaptureObserve(1,123,8,changed); // new ID is absent from the frozen census
 researchCaptureObserveTxVh(0x3F8,8,changed,false);
 assert(!researchCaptureRequest(1));assert(!researchCaptureSetMode(1));
 assert(!researchCaptureSetConfig(5000,2000));
 auto* archive=researchCaptureEntries;auto* pre=researchCapturePreStates;
 researchCaptureReleaseModeBuffers();assert(archive==researchCaptureEntries && pre==researchCapturePreStates);
 const uint32_t epoch=researchCaptureSnapshotEpoch;
 researchCaptureTick(nowMs);assert(researchCaptureSnapshotEpoch==epoch);
}
static void testSnapshotCoherentRxAndTx(){
 seedSnapshot();uint8_t tx[8]={0x42};researchCaptureObserveTxVh(0x3F8,8,tx,true);
 snapshotInterleaves=0;interleave=mutateDuringSnapshot;maxLockBytes=0;
 researchCaptureTick(nowMs);interleave=nullptr;
 assert(snapshotInterleaves>1 && !researchCaptureSnapshotBusy && maxLockBytes<=512);
 const auto&meta=researchCapturePreSlots[0];assert(meta.count==64 && meta.txData[0]==0x42 && meta.txOk);
 for(unsigned i=0;i<64;i++){uint32_t id;std::memcpy(&id,researchCapturePreSlotBase(0)[i].data,4);assert(id==i);}
 // Reestablish known trigger state, leaving the older PRE slot unchanged.
 uint8_t zero[8]={};researchCaptureObserve(0,0,8,zero);uint8_t last[8]={63};researchCaptureObserve(0,63,8,last);
 researchCaptureObserveTxVh(0x3F8,8,tx,true);nowMs=1100;
 interleave=mutateDuringSnapshot;assert(researchCaptureRequest(0));interleave=nullptr;
 assert(researchCaptureLastPreSnapshotsCopied==1 && researchCaptureLastTriggerRows==66);
 assert(researchCaptureCount==131);
 for(unsigned i=0;i<64;i++){
  uint32_t id;std::memcpy(&id,researchCaptureEntries[i].data,4);assert(id==i);
  std::memcpy(&id,researchCaptureEntries[65+i].data,4);assert(id==i);
 }
 assert(researchCaptureEntries[64].data[0]==0x42 && researchCaptureEntries[130].data[0]==0x42);
 nowMs=6100;researchCaptureTick(nowMs);assert(researchCaptureState==RESEARCH_CAPTURE_PAUSED);
}
static unsigned cancelAfter;
static void hideSnapshot(){
 if(researchCaptureSnapshotBusy && ++snapshotInterleaves>=cancelAfter){researchCaptureSnapshotCancelled=true;interleave=nullptr;}
}
static void resetReplaceSnapshot(){
 if(researchCaptureSnapshotBusy && ++snapshotInterleaves>=cancelAfter){
  interleave=nullptr;researchCaptureReset();researchCaptureReleaseModeBuffers();
  assert(researchCaptureEntries==nullptr);assert(researchCaptureEnsureBuffer());
  assert(researchCaptureRequest(2));
 }
}
static void toggleLabDuringSnapshot(){
 if(researchCaptureSnapshotBusy && ++snapshotInterleaves>=cancelAfter){
  interleave=nullptr;labMenuEnabled=false;researchCaptureSnapshotCancelled=true;labMenuEnabled=true;
 }
}
static void testSnapshotCancellationAndNewOwner(){
 seedSnapshot();researchCaptureTick(nowMs);nowMs=1100;
 snapshotInterleaves=0;cancelAfter=3;interleave=hideSnapshot;
 assert(!researchCaptureRequest(0));assert(!researchCaptureSnapshotBusy && researchCaptureCount==0 && researchCaptureSegment==0);
 assert(researchCaptureCurrentLabelSlot==RESEARCH_CAPTURE_LABEL_NONE && researchCaptureStartMs==0);
 labMenuEnabled=true;assert(researchCaptureRequest(0));
 const uint32_t initialCount=researchCaptureCount;
 nowMs=6100;snapshotInterleaves=0;cancelAfter=8;interleave=hideSnapshot;
 researchCaptureTick(nowMs);assert(!researchCaptureSnapshotBusy && researchCaptureCount==initialCount);
 assert(researchCaptureState==RESEARCH_CAPTURE_PAUSED);
 labMenuEnabled=true;assert(researchCaptureRequest(1));
 // The real LAB handler latches cancellation across an immediate off/on.
 seedSnapshot();researchCaptureTick(nowMs);nowMs=1100;
 snapshotInterleaves=0;cancelAfter=3;interleave=toggleLabDuringSnapshot;
 assert(!researchCaptureRequest(0));assert(!researchCaptureSnapshotBusy && researchCaptureCount==0);
 assert(researchCaptureRequest(0));
 // Reset and replace mode blocks while the old trigger holds a local pointer.
 seedSnapshot();researchCaptureTick(nowMs);nowMs=1100;
 snapshotInterleaves=0;cancelAfter=3;interleave=resetReplaceSnapshot;
 assert(!researchCaptureRequest(0));assert(!researchCaptureSnapshotBusy);
 assert(researchCaptureSegment==1 && researchCaptureCurrentLabelSlot==2 && researchCaptureState==RESEARCH_CAPTURE_CAPTURING);
 assert(researchCaptureCount==64); // replacement owner's trigger only
 researchCaptureReset();researchCaptureConfigUpdating=true;researchCaptureCount=7;
 researchCaptureReset();assert(researchCaptureCount==7 && researchCaptureConfigUpdating);
 researchCaptureConfigUpdating=false;researchCaptureReset();
}
static void testLogarithmicSearch(){
 struct Entry {CountedTimestamp timestampMs;};static Entry entries[32768];
 for(unsigned i=0;i<32768;i++)entries[i].timestampMs.value=1000+i/8;
 for(uint32_t window: {0U,1000U,5000U}){timestampReads=0;auto p=researchRawCopyPlanPure(entries,32768,0,32768,6000,window,32768);assert(timestampReads<=16);if(window==5000)assert(p.count==32768);}
}
int main(){
 failAllocationBytes=RESEARCH_CAPTURE_LATEST_BYTES+RESEARCH_CAPTURE_FROZEN_BYTES;
 assert(!researchCaptureEnsureBuffer());assert(researchCaptureState==RESEARCH_CAPTURE_ERROR);
 assert(!researchCaptureEntries && !researchCapturePreStates && !researchCaptureLatest);
 researchCaptureTick(nowMs);frame();assert(researchCaptureCount==0);
 failAllocationBytes=0;
 assert(researchCaptureEnsureBuffer());
 testDeferredAndOverwrite();testExpiryAndCompletion();testClearExportAndFull();
 testClearAtServiceBoundary();testAutoDelayedAndRollover();testLogarithmicSearch();testSnapshotUnchanged();testSnapshotLockBoundAndHiddenLab();testSnapshotCoherentRxAndTx();testSnapshotCancellationAndNewOwner();
 std::puts("research capture production lock and lifecycle tests passed (11 groups)");
}
