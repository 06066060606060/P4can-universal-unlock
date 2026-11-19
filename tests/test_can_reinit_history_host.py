"""Exercise actual hard-reinitialize begin/result hooks without hardware."""
from pathlib import Path
import os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'can_runtime.h').read_text()
body=s[s.index('static bool recoveryHardReinitialize('):s.index('static void canRecoverySupervisorTick(')]
fixture=r'''
#include <cassert>
#include <cstdint>
#include <vector>
struct Event {uint32_t id;uint8_t reason,diag,phase;};
static std::vector<Event> events;
static bool canSubsystemBusy=false,apDisplayHold=false,recoveryEverBothActive=false;
static int failure=0,stateMux=0;
static uint32_t canHardReinitCount=0,canHardReinitFailCount=0,lastCanAFrameMs=0,lastCanBFrameMs=0,canInitTime=0,recoveryOneBusStaleStartMs=0,recoveryWakeAcquireStartMs=0;
static uint8_t canLastHardReinitReason=0,canLastHardDiagReason=0;
constexpr uint8_t CAN_SUP_HARD_ACQUIRE=2;
#define P4CAN_SERIAL_PRINTF(...) ((void)0)
#define P4CAN_SERIAL_PRINTLN(...) ((void)0)
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
#define P4_CAN_DIAG_REINIT(id, reason, diag, phase) events.push_back({id,reason,diag,phase})
static int8_t bootCaptureHardStart(uint8_t){return 0;}
static void bootCaptureHardFinish(int8_t,bool){}
static uint32_t millis(){return 50;}
static void apDisplayBeginHardInitPure(bool&,uint32_t){}
static bool recoveryStopCanTasks(){return failure!=1;}
static void invalidateCanTxStateForFullRecovery(){}
static bool recoveryNativeAColdInit(){return failure!=2;}
static bool recoveryTwaiFullReinit(){return failure!=3;}
static bool recoveryStartCanTasks(){return failure!=4;}
'''+body+r'''
int main(){
 for(failure=0;failure<5;++failure){
  events.clear();bool ok=recoveryHardReinitialize(3,9);
  assert(ok==(failure==0));assert(!canSubsystemBusy);
  assert(events.size()==2 && "hard reinitialize must journal begin and terminal result");
  assert(events[0].id==canHardReinitCount&&events[1].id==canHardReinitCount);
  assert(events[0].reason==3&&events[0].diag==9&&events[0].phase==1);
  assert(events[1].phase==(failure==0?2:3));
 }
 events.clear();canSubsystemBusy=true;assert(!recoveryHardReinitialize(3,9)&&events.empty());
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'main.cpp').write_text(fixture)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(p/'main.cpp'),'-o',str(p/'run')],check=True)
 subprocess.run([str(p/'run')],check=True)
