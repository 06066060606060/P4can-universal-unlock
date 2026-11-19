"""Exercise real persistence and maintenance teardown with fault-injected HAL/NVS.

Catches flash writes before all three controllers are uninstalled, lost dirty
records, stale save-after-clear, and unbounded/falsely successful failed saves.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'

runtime = (ROOT / 'can_runtime.h').read_text()
backend = (ROOT / 'p4_can.h').read_text()
CODE = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#include <cstdio>
#include "can_busoff_persistence_pure.h"
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)0)
#define portEXIT_CRITICAL(x) ((void)0)
#define pdMS_TO_TICKS(x) (x)
constexpr int pdTRUE=1,ESP_OK=0,ESP_FAIL=1,INPUT=0;
constexpr unsigned P4_CAN_COUNT=3;
constexpr int TWAI_STATE_RUNNING=1,TWAI_STATE_STOPPED=0,TWAI_STATE_BUS_OFF=2,TWAI_STATE_RECOVERING=3;
struct twai_status_info_t {int state;};
static uint32_t clockMs=100;
static uint32_t millis(){return clockMs;}
static void vTaskDelay(unsigned n){clockMs+=n;}
static void* p4CanHandles[3]={(void*)1,(void*)2,(void*)3};
static bool p4CanOnline[3]={true,true,true};
static int p4CanState[3]={1,1,1},actualState[3]={1,1,1};
static int p4CanTxPins[3]={20,50,26},p4CanRxPins[3]={21,49,27};
static bool statusFails[3]={},stopFails[3]={},uninstallFails[3]={};
static int stopCalls=0,uninstallCalls=0;
static unsigned busOf(void*h){return (uintptr_t)h-1;}
static int twai_get_status_info_v2(void*h,twai_status_info_t*s){auto b=busOf(h);s->state=actualState[b];return statusFails[b]?ESP_FAIL:ESP_OK;}
static int twai_stop_v2(void*h){++stopCalls;auto b=busOf(h);if(stopFails[b])return ESP_FAIL;actualState[b]=TWAI_STATE_STOPPED;return ESP_OK;}
static int twai_driver_uninstall_v2(void*h){++uninstallCalls;return uninstallFails[busOf(h)]?ESP_FAIL:ESP_OK;}
static void pinMode(int,int){}
static unsigned p4CanBusB(){return 2;}
static bool canMaintenanceRequested=false,canMaintenancePreparing=false,canMaintenanceStopped=false;
static bool canMaintenanceSupervisorParked=false,canMaintenanceObservedCanRuntime=false;
static bool nativeAReady=true,twaiReady=true,p4CanExtraFresh=true,canTxAdministrativeHold=false;
static void *canSupervisorHandle=(void*)4,*canTaskNativeAHandle=(void*)5,*canTaskTwaiHandle=(void*)6;
static bool canTaskNativeAQuiesced=true,canTaskTwaiQuiesced=true,preheatQuiet=true,barrierAvailable=true;
static void*canTxBarrierMutex=(void*)7;
static bool preheatSettingsQuiesceForMaintenance(){return preheatQuiet;}
static void*xTaskGetCurrentTaskHandle(){return nullptr;}
static int xSemaphoreTake(void*,unsigned){return barrierAvailable?pdTRUE:0;}
static void xSemaphoreGive(void*){}
static void invalidateCanTxStateForFullRecovery(){}
static int restarts=0;
struct {void restart(){++restarts;}} ESP;
using CanATxTraceEntry=CanBusOffTraceEntryPure;
using CanBTxTraceEntry=CanBusOffTraceEntryPure;
constexpr unsigned CAN_A_TX_TRACE_CAPACITY=64,CAN_B_TX_TRACE_CAPACITY=64;
static int canATxTraceMux=0,canBTxTraceMux=0,canRecoveryMux=0;
static uint32_t canANativeABusOffCount=2,canTwaiBusOffCount=3;
static uint8_t canATxTraceFrozenCount=1,canBTxTraceFrozenCount=1;
static uint32_t canATxTraceFrozenMs=42,canBTxTraceFrozenMs=43;
static uint32_t canATxTraceFrozenBusOffOrdinal=2,canBTxTraceFrozenBusOffOrdinal=3;
static uint32_t canATxTraceSeq=0,canBTxTraceSeq=0;
static CanATxTraceEntry canATxTraceFrozen[64]={};
static CanBTxTraceEntry canBTxTraceFrozen[64]={};
struct ASnapshot:CanBusOffSnapshotPure {uint32_t capturedMs=42,rxAgeMs=4;} canALastBusOffSnapshot;
struct BSnapshot:CanBusOffSnapshotPure {uint32_t capturedMs=43,rxGapMs=5;uint8_t state=2;} canTwaiLastBusOffSnapshot;
static std::map<std::string,std::vector<uint8_t>> store;
static int writeOpens=0,putCalls=0,removes=0;
static bool openFails=false,putFails=false,verifyFails=false;
static void(*duringPut)()=nullptr;
struct Preferences {
 bool begin(const char*ns,bool ro){assert(std::string(ns)=="p4CanDiag");if(!ro)++writeOpens;return !openFails;}
 void end(){}
 size_t getBytesLength(const char*k){return store[k].size();}
 size_t getBytes(const char*k,void*out,size_t n){auto&v=store[k];if(v.size()!=n)return 0;memcpy(out,v.data(),n);if(verifyFails&&n)((uint8_t*)out)[0]^=1;return n;}
 size_t putBytes(const char*k,const void*buf,size_t n){++putCalls;if(putFails)return 0;auto p=(const uint8_t*)buf;store[k]={p,p+n};if(duringPut){auto f=duringPut;duringPut=nullptr;f();}return n;}
 bool remove(const char*k){++removes;store.erase(k);return true;}
};
#include "can_busoff_persistence.h"
'''
CODE += function(backend, 'static bool p4CanUninstall(uint8_t bus)')
CODE += function(backend, 'static bool p4CanStopAll()')
CODE += function(runtime, 'static bool prepareCanForMaintenance()')
CODE += function(runtime, 'static void restartP4CanSafely()')
CODE += r'''
static void liveReset(){
 canMaintenanceRequested=canMaintenancePreparing=canMaintenanceStopped=false;
 canMaintenanceSupervisorParked=true;canTaskNativeAQuiesced=canTaskTwaiQuiesced=true;
 preheatQuiet=barrierAvailable=true;nativeAReady=twaiReady=p4CanExtraFresh=true;
 canBusOffPersistenceDirtyMask=0;canBusOffPersistenceBusy=false;
 for(int b=0;b<3;++b){p4CanHandles[b]=(void*)(uintptr_t)(b+1);actualState[b]=TWAI_STATE_RUNNING;p4CanState[b]=TWAI_STATE_STOPPED;statusFails[b]=stopFails[b]=uninstallFails[b]=false;}
 for(int i=0;i<2;++i){canBusOffPersistenceState[i]=CAN_BUS_OFF_PERSIST_EMPTY;canBusOffPersistenceRetryAtMs[i]=0;canBusOffPersistenceError[i]=0;canBusOffPersistenceDirtyEpoch[i]=0;canBusOffPersistenceActiveSlot[i]=0xff;canBusOffPersistenceSlots[i][0]={};canBusOffPersistenceSlots[i][1]={};}
 writeOpens=putCalls=removes=stopCalls=uninstallCalls=restarts=0;clockMs=100;store.clear();
 openFails=putFails=verifyFails=false;duringPut=nullptr;
 canALastBusOffSnapshot.valid=canTwaiLastBusOffSnapshot.valid=true;
 canATxTraceFrozen[0].id=0x118;canATxTraceFrozen[0].dlc=8;canATxTraceFrozen[0].data[0]=0x45;
}
static void dirty(){canBusOffPersistenceMarkDirty(1);canBusOffPersistenceMarkDirty(2);}
static void newerEvent(){canBusOffPersistenceMarkDirty(1);}
static void checkedRecord(){
 CanBusOffRecordPure r{};assert(decodeCanBusOffRecordPure(store["a0"].data(),store["a0"].size(),1,r));
 assert(r.count==2&&r.eventUptimeMs==42&&r.traceCount==1&&r.trace[0].id==0x118&&r.trace[0].data[0]==0x45);
}
int main(){
 // A cached stopped/BUS_OFF state never authorizes NVS while live handles remain.
 liveReset();dirty();
 for(int state:{TWAI_STATE_RUNNING,TWAI_STATE_BUS_OFF,TWAI_STATE_STOPPED}){
  for(auto&s:p4CanState)s=state;
  canBusOffPersistenceService(clockMs);
  assert(writeOpens==0&&putCalls==0&&stopCalls==0&&uninstallCalls==0);
  assert(canBusOffPersistenceDirtyMask==3&&std::string(canBusOffPersistStateName(1))=="DIRTY");
 }
 // Even inconsistent sticky state cannot authorize a still-installed controller.
 for(int physical=0;physical<3;++physical){
  liveReset();dirty();canMaintenanceStopped=true;
  for(int b=0;b<3;++b)if(b!=physical)p4CanHandles[b]=nullptr;
  canBusOffPersistenceService(clockMs);assert(writeOpens==0&&putCalls==0);
 }
 // Park failures and all HAL teardown failure variants must leave NVS untouched.
 for(int physical=0;physical<3;++physical)for(int scenario=0;scenario<9;++scenario){
  liveReset();dirty();
  if(scenario==0)canMaintenanceSupervisorParked=false;
  if(scenario==1)canTaskNativeAQuiesced=false;
  if(scenario==2)canTaskTwaiQuiesced=false;
  if(scenario==3)statusFails[physical]=true;
  if(scenario==4)stopFails[physical]=true;
  if(scenario==5)uninstallFails[physical]=true;
  if(scenario==6)actualState[physical]=TWAI_STATE_RECOVERING;
  if(scenario==7)preheatQuiet=false;
  if(scenario==8)barrierAvailable=false;
  assert(!prepareCanForMaintenance());canBusOffPersistenceService(clockMs);
  assert(!canMaintenanceStopped&&writeOpens==0&&putCalls==0&&canBusOffPersistenceDirtyMask==3);
 }
 // Successful maintenance saves both records exactly once before reboot/OTA.
 liveReset();dirty();assert(prepareCanForMaintenance());
 assert(canMaintenanceStopped&&putCalls==2&&canBusOffPersistenceDirtyMask==0);
 for(auto h:p4CanHandles)assert(!h);
 checkedRecord();assert(prepareCanForMaintenance());restartP4CanSafely();assert(putCalls==2&&restarts==1);
 // Explicit clear cancels pending traces; it retains its existing durable-delete semantics.
 liveReset();dirty();assert(canBusOffPersistenceClear());assert(removes==4);
 assert(prepareCanForMaintenance());assert(putCalls==0&&canBusOffPersistenceDirtyMask==0);
 // Factory reset occurs AFTER prepare; repeated safe restart must not save after erase,
 // including a dirty record left behind by a failed first maintenance flush.
 liveReset();dirty();putFails=true;assert(prepareCanForMaintenance());assert(putCalls==2);
 store.clear();putFails=false;clockMs+=10000;restartP4CanSafely();assert(putCalls==2&&store.empty()&&restarts==1);
 // Flash failure leaves error/dirty and bounded retry, without rejecting shutdown.
 for(int fail=0;fail<3;++fail){
  liveReset();dirty();openFails=fail==0;putFails=fail==1;verifyFails=fail==2;
  assert(prepareCanForMaintenance());assert(canBusOffPersistenceDirtyMask==3);
  assert(canBusOffPersistenceState[0]==CAN_BUS_OFF_PERSIST_ERROR);
  assert(canBusOffPersistenceError[0]==(fail==0?CAN_BUS_OFF_PERSIST_ERROR_OPEN:fail==1?CAN_BUS_OFF_PERSIST_ERROR_WRITE:CAN_BUS_OFF_PERSIST_ERROR_VERIFY));
  int attempted=writeOpens;openFails=putFails=verifyFails=false;
  canBusOffPersistenceService(clockMs+4999);assert(writeOpens==attempted);
  canBusOffPersistenceService(clockMs+5000);assert(writeOpens==attempted+2&&canBusOffPersistenceDirtyMask==0);
 }
 // A failed partial teardown can be retried safely; flash remains deferred until then.
 liveReset();dirty();uninstallFails[2]=true;assert(!prepareCanForMaintenance());assert(putCalls==0);
 uninstallFails[2]=false;assert(prepareCanForMaintenance());assert(putCalls==2);
 // Retry delay handles uptime rollover without writing early.
 liveReset();dirty();clockMs=0xfffffff0u;putFails=true;assert(prepareCanForMaintenance());
 putFails=false;canBusOffPersistenceService(clockMs+4999u);assert(putCalls==2);
 canBusOffPersistenceService(clockMs+5000u);assert(putCalls==4&&canBusOffPersistenceDirtyMask==0);
 // An owned writer is not entered recursively, and the pending record survives.
 liveReset();dirty();canBusOffPersistenceBusy=true;assert(prepareCanForMaintenance());assert(putCalls==0&&canBusOffPersistenceDirtyMask==3);
 canBusOffPersistenceBusy=false;canBusOffPersistenceService(clockMs);assert(putCalls==2);
 // A newer event during a save must remain DIRTY and exportable for a later save.
 liveReset();dirty();duringPut=newerEvent;assert(prepareCanForMaintenance());
 assert(canBusOffPersistenceDirtyMask==1&&std::string(canBusOffPersistStateName(1))=="DIRTY");
 canBusOffPersistenceService(clockMs);assert(canBusOffPersistenceDirtyMask==0&&putCalls==3);
 putCalls=0;assert(canBusOffPersistenceClear());canBusOffPersistenceService(clockMs);assert(putCalls==0);
 std::puts("PASS: real persistence/maintenance live gate, 27 park/partial-stop failures, flush, reset, 3 flash failures/retry and dirty epochs");
}
'''
with tempfile.TemporaryDirectory(prefix='p4-busoff-') as tmp:
    source = Path(tmp) / 'test.cpp'
    binary = Path(tmp) / 'test'
    source.write_text(CODE)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-Wall', '-Wextra', '-Wno-unused-function', '-I', str(ROOT), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
