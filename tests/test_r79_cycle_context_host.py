"""Actual stock-cycle cancellation and error-context publication boundaries."""
from pathlib import Path
import os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'vehicle_logic.h').read_text()
def function(signature):
 a=s.index(signature);return s[a:s.index('\n}',a)+2]
functions='\n'.join(function(x) for x in ('static void r79FixedObserveStock(uint8_t mux, uint32_t nowMs) {','static bool r79ProcessStockFrame(const twai_message_t &src, uint8_t mux,\n                                 uint32_t nowMs) {'))
prelude=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "driver/twai.h"
#include "r79_fixed_policy_pure.h"
#include "r79_dms_composition_pure.h"
#include "p4_twai_diag.h"
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
static int r79LabMux=0;
static R79FixedQuietStatePure r79FixedQuietState{};
static bool r79Mode1ReinjectEnabled=true,r79RetryPending=false;
static uint16_t r79Mode1DelayMs=15;
[[maybe_unused]] static bool r79RetryApOnly=false;
[[maybe_unused]] static uint32_t r79RetryApGeneration=0;
static uint32_t r79QuietArmCount=0,r79RetryDueMs=0,r79RetryGeneration=0,r79DmsOnlyBlockedByR79=0;
static uint8_t r79RetryIndex=0,r79RetryOriginKind=0;
static volatile uint32_t r79Mode1PostMux2Generation=1;
static constexpr uint8_t R79LAB_TX_PERIODIC=2,R79LAB_TX_NONE=0;
static uint32_t obsoleteGeneration=0;static unsigned echoes=0;
bool r79FixedFastEcho(const twai_message_t&){assert(r79Mode1PostMux2Generation!=obsoleteGeneration);++echoes;return true;}
bool r79DmsWorkPendingSnapshot(){return false;}
bool r79DmsControlActive(){return false;}
bool r79DmsOnlyTransmit(const twai_message_t&){return false;}
'''
main=r'''
int main(){
 twai_message_t f{};f.identifier=0x3fd;f.data_length_code=8;
 for(uint8_t next:{0,1,2}){
  r79FixedQuietState={};
  r79ProcessStockFrame(f,2,1000);
  assert(r79FixedQuietStepPure(r79FixedQuietState,1015,true)==R79_FIXED_QUIET_FIRE_PURE);
  obsoleteGeneration=r79Mode1PostMux2Generation;
  r79ProcessStockFrame(f,next,1016);
  assert(r79Mode1PostMux2Generation!=obsoleteGeneration);
 }
 const auto gen=r79Mode1PostMux2Generation;r79ProcessStockFrame(f,7,1017);assert(r79Mode1PostMux2Generation==gen);
 r79Mode1PostMux2Generation=UINT32_MAX;r79ProcessStockFrame(f,0,1018);assert(r79Mode1PostMux2Generation==0);
 puts("PASS actual Mode1 new-cycle invalidation after FIRE, before immediate echo, and rollover");
}
'''
def run(text,name):
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'fixture.cpp';out=Path(td)/'fixture';p.write_text(text)
  subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable','-I'+str(ROOT/'tests'),'-I'+str(ROOT/'tests/r79_timing_fakes'),'-I'+str(ROOT),str(p),'-o',str(out)],check=True)
  subprocess.run([str(out)],check=True)
run('#include <initializer_list>\n'+prelude+functions+main,'cycle')

