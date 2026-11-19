"""Production Continuous AP settings apply with real policy/FSM and NVS hooks.

Isolated fixture probes CAN barrier availability throughout synchronous flash I/O,
then verifies atomic publication, failed-save state, and pending-gesture cleanup.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


CODE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "continuous_ap_fsm_pure.h"
constexpr int pdTRUE=1;
constexpr uint32_t portMAX_DELAY=0xffffffffu;
static int mutexToken,continuousApMux;
static void *canTxBarrierMutex=&mutexToken;
static bool barrierHeld=false,criticalHeld=false,openFails=false,takeFails=false;
static unsigned beginCalls=0,putCalls=0,endCalls=0,publishTakes=0,probes=0;
static size_t writeSize=sizeof(uint32_t);
static uint32_t stored=0,clockMs=2000;
static struct {uint32_t epoch=41;} canTxBarrierState;
static uint8_t activeVehicleProfile=VEHICLE_MODEL_Y_JUNIPER;
static uint8_t activeVehicleTopology=VEHICLE_TOPOLOGY_TRIPLE_STANDARD;
static ContApConfig continuousApConfig;
static uint32_t continuousApGeneration=7;
static ContinuousApFsmPure continuousApFsm;
static ContApConfig oldConfig;
static ContApStatus oldStatus;
static uint32_t oldGeneration;
static bool changeEpochDuringEnd=false;
static uint32_t millis(){return clockMs;}
static int xSemaphoreTake(void *mutex,uint32_t wait){
 assert(mutex==canTxBarrierMutex);
 if(wait==portMAX_DELAY){
  ++publishTakes;
  if(takeFails)return 0;
 }
 if(barrierHeld)return 0;
 barrierHeld=true;return pdTRUE;
}
static void xSemaphoreGive(void *mutex){assert(mutex==canTxBarrierMutex&&barrierHeld&&!criticalHeld);barrierHeld=false;}
static void enterCritical(int *mux){assert(mux==&continuousApMux&&barrierHeld&&!criticalHeld);assert(endCalls==1 && "publication must wait for all NVS I/O to finish");criticalHeld=true;}
static void exitCritical(int *mux){assert(mux==&continuousApMux&&criticalHeld);criticalHeld=false;}
#define portENTER_CRITICAL(x) enterCritical(x)
#define portEXIT_CRITICAL(x) exitCritical(x)
#define P4_CAN_DIAG_NVS_WRITE(source, expression) (expression)
static void unchanged(){
 assert(continuousApConfig.enabled==oldConfig.enabled&&continuousApConfig.method==oldConfig.method);
 assert(continuousApGeneration==oldGeneration);
 const auto s=continuousApFsm.status();
 assert(s.state==oldStatus.state&&s.reason==oldStatus.reason&&s.lastCancelReason==oldStatus.lastCancelReason);
 assert(s.releaseOwed==oldStatus.releaseOwed&&s.cleanupUnconfirmed==oldStatus.cleanupUnconfirmed);
 assert(s.txOk==oldStatus.txOk&&s.txFail==oldStatus.txFail&&s.attempts==oldStatus.attempts);
}
static void nvsProbe(){
 assert(!criticalHeld);
 unchanged();
 assert(xSemaphoreTake(canTxBarrierMutex,0)==pdTRUE && "CAN TX barrier must remain available during NVS");
 xSemaphoreGive(canTxBarrierMutex);++probes;
}
struct Preferences {
 bool begin(const char *ns,bool readOnly){assert(std::strcmp(ns,"features")==0&&!readOnly);++beginCalls;nvsProbe();return !openFails;}
 size_t putUInt(const char *key,uint32_t value){assert(std::strcmp(key,"contApCfg")==0);++putCalls;nvsProbe();if(writeSize==sizeof(uint32_t))stored=value;return writeSize;}
 void end(){++endCalls;nvsProbe();if(changeEpochDuringEnd){++canTxBarrierState.epoch;++continuousApGeneration;oldGeneration=continuousApGeneration;}}
};
'''
CODE += function((ROOT / 'continuous_ap_runtime.h').read_text(),
                 'static inline bool continuousApControlApply(ContApConfig next)')
CODE += r'''
static void remember(){oldConfig=continuousApConfig;oldGeneration=continuousApGeneration;oldStatus=continuousApFsm.status();}
static void reset(){
 canTxBarrierMutex=&mutexToken;barrierHeld=criticalHeld=openFails=takeFails=changeEpochDuringEnd=false;
 beginCalls=putCalls=endCalls=publishTakes=probes=0;writeSize=sizeof(uint32_t);stored=0;clockMs=2000;
 activeVehicleProfile=VEHICLE_MODEL_Y_JUNIPER;activeVehicleTopology=VEHICLE_TOPOLOGY_TRIPLE_STANDARD;
 continuousApConfig={true,ContApMethod::ScrollSingle};continuousApGeneration=7;canTxBarrierState.epoch=41;
 continuousApFsm=ContinuousApFsmPure();continuousApFsm.reset(41);remember();
}
static ContApInputs inputs(uint32_t now,int ap,int turn){
 ContApInputs i;i.nowMs=now;i.epoch=canTxBarrierState.epoch;i.generation=continuousApGeneration;
 i.profile=activeVehicleProfile;i.topology=activeVehicleTopology;i.config=continuousApConfig;
 i.ap={true,true,ap,now,i.epoch};i.turn={true,true,turn,now,i.epoch};
 i.brake={true,true,1,now,i.epoch};i.gear={true,true,4,now,i.epoch};
 i.torque={true,true,0,now,i.epoch};i.control={true,true,0,now,i.epoch};
 i.templateFresh=i.transportAllowed=i.ownershipAllowed=true;return i;
}
static ContApCommand seedPress(bool accepted){
 continuousApFsm.service(inputs(100,3,1));
 continuousApFsm.service(inputs(200,2,0));
 const auto i=inputs(1200,2,0);
 const auto command=continuousApFsm.service(i);
 assert(command.kind==ContApCommandKind::Press&&continuousApFsm.allowsCommand(command,i));
 if(accepted)continuousApFsm.onTxResult(command,true,1200);
 remember();return command;
}
static void published(ContApConfig next){
 assert(continuousApConfig.enabled==next.enabled&&continuousApConfig.method==next.method);
 assert(continuousApGeneration==oldGeneration+1u);
 assert(stored==continuousApConfigEncodePure(next));
 assert(beginCalls==1&&putCalls==1&&endCalls==1&&probes==3&&publishTakes==1);
 assert(!barrierHeld&&!criticalHeld);
 assert(continuousApFsm.status().lastCancelReason==ContApReason::Changed);
}
int main(){
 const ContApConfig next{false,ContApMethod::ScrollDouble};
 // The real pending command remains authoritative during each flash operation,
 // and becomes invalid only after a successful, short atomic publication.
 reset();auto command=seedPress(false);assert(continuousApControlApply(next));published(next);
 assert(!continuousApFsm.allowsCommand(command,inputs(2000,2,0)));
 assert(continuousApFsm.status().state==ContApState::Idle);
 // Flash-open and short-write failures preserve the live config/generation/FSM.
 for(int failure=0;failure<3;++failure){
  reset();command=seedPress(false);openFails=failure==0;writeSize=failure==1?0:2;
  assert(!continuousApControlApply(next));unchanged();
  assert(continuousApFsm.allowsCommand(command,inputs(2000,2,0)));
  assert(beginCalls==1&&putCalls==(failure?1u:0u)&&endCalls==(failure?1u:0u));
  assert(publishTakes==0&&!barrierHeld&&!criticalHeld);
 }
 // An accepted press retains the existing bounded release cleanup on settings change.
 reset();seedPress(true);assert(continuousApControlApply(next));published(next);
 assert(continuousApFsm.status().state==ContApState::CleanupPending&&continuousApFsm.status().releaseOwed);
 auto release=continuousApFsm.service(inputs(2000,2,0));
 assert(release.kind==ContApCommandKind::Release&&release.generation==continuousApGeneration);
 assert(continuousApFsm.allowsCommand(release,inputs(2000,2,0)));
 // Invalid encoding, enabled unsupported method/profile/topology, and absent
 // barrier all reject before persistence. Disabling an unsupported route is valid.
 for(int invalid=0;invalid<6;++invalid){
  reset();ContApConfig bad{true,ContApMethod::ScrollDouble};
  if(invalid==0)bad.method=ContApMethod::Unset;
  if(invalid==1)bad.method=(ContApMethod)255;
  if(invalid==2)bad.method=ContApMethod::StalkDouble;
  if(invalid==3)activeVehicleProfile=VEHICLE_MODEL_YL;
  if(invalid==4)activeVehicleTopology=VEHICLE_TOPOLOGY_NONE;
  if(invalid==5)canTxBarrierMutex=nullptr;
  assert(!continuousApControlApply(bad));unchanged();assert(beginCalls==0&&publishTakes==0);
 }
 reset();activeVehicleProfile=VEHICLE_MODEL_YL;assert(continuousApControlApply(next));published(next);
 // Successful reconfiguration advances even if unchanged, matching the existing contract.
 reset();assert(continuousApControlApply(oldConfig));published(oldConfig);
 // Publish against current epoch/generation, including wrap, rather than values
 // captured before flash while a CAN epoch reset can happen.
 reset();changeEpochDuringEnd=true;assert(continuousApControlApply(next));published(next);
 reset();continuousApGeneration=0xffffffffu;remember();assert(continuousApControlApply(next));published(next);
 assert(continuousApGeneration==0);
 // A failed final barrier acquisition never mutates live state after persistence.
 reset();takeFails=true;assert(!continuousApControlApply(next));unchanged();
 assert(stored==continuousApConfigEncodePure(next)&&publishTakes==1&&!barrierHeld);
 std::puts("PASS: Continuous AP real apply/FSM NVS lock probes, save faults, validation, publication, pending cancellation, cleanup, epoch and generation wrap");
}
'''
with tempfile.TemporaryDirectory(prefix='p4-contap-persistence-') as tmp:
    source = Path(tmp) / 'test.cpp'
    binary = Path(tmp) / 'test'
    source.write_text(CODE)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-function', '-I', str(ROOT), str(source),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
