"""Real quiet/retry state and runtime slices under unrelated RX backlog.

Combines the existing scheduling and queue-preservation fixtures, preserving
production quiet observation, due/deadline handling, retry budget, and TX
transform. Only hardware I/O, state publication, and native boundary readiness
are fakes; native admission/dispatch races have separate driver coverage.
"""
import ast
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def fixture_prefix(name):
    path = ROOT / 'tests' / name
    nodes = []
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.With):
            break
        nodes.append(node)
    scope = {'__file__': str(path)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return scope


def replace_once(text, old, new):
    # A changed scheduling fixture must not silently retain its boundary fake
    # while this integration test appears to exercise transport production.
    assert text.count(old) == 1, f'fixture extraction expected exactly one {old[:70]!r}'
    return text.replace(old, new, 1)


scheduling = fixture_prefix('test_r79_service_scheduling_host.py')
transport = fixture_prefix('test_r79_queue_preservation_host.py')
rx = scheduling['code'].split('void reset(')[0]
# Keep headers at global scope; isolate the scheduling fakes from the existing
# transport fixture's ordinary FIFO and complete TWAI frame type.
headers = '\n'.join(re.findall(r'^#include .*$', rx, re.M))
rx = re.sub(r'^#include .*$', '', rx, flags=re.M)
rx = replace_once(rx, 'bool r79ProcessStockFrame(const twai_message_t&,uint8_t,uint32_t){return stockClaimed;}',
                  'bool r79ProcessStockFrame(const twai_message_t&,uint8_t,uint32_t);')
rx = replace_once(rx, 'void r79TransportSliceTick(bool allowPeriodic){if(checkInputDone)assert(inputDone==1);services.push_back({processed,nowMs,unsigned(queue.size()),allowPeriodic});nowMs+=serviceStepMs;if(advanceEpochOnService)++epoch;}',
                  'void r79TransportSliceTick(bool);')
prelude = replace_once(transport['prelude'], 'uint32_t millis(){return nowMs;}',
                       'uint32_t millis(){return runtime::nowMs;}')
source = (ROOT / 'vehicle_logic.h').read_text()
runtime_source = (ROOT / 'can_runtime.h').read_text()
due_helper = transport['source_block'](runtime_source, 'static bool r79ServiceWorkDueSnapshot(')
# Bind the actual scheduler's due snapshot to the actual transport state;
# duplicate scheduling-only fixture globals must not hide pending work.
rx = replace_once(rx, due_helper, 'static bool r79ServiceWorkDueSnapshot(uint32_t);')


def production(sig):
    return transport['source_block'](source[source.rfind(sig):], sig)


helpers = r'''
#include "r79_dms_composition_pure.h"
static bool r79Mode1ReinjectEnabled=true;
static uint16_t r79Mode1DelayMs=150;
static uint32_t r79QuietArmCount=0,r79QuietFireCount=0,r79DmsOnlyBlockedByR79=0;
static bool& r79LabStockValid=stockValid;
static uint8_t* r79LabLastStockRaw=latest;
uint32_t canTxCancellationGenerationSnapshot(const volatile uint32_t*g){return *g;}
bool r79DmsControlActive(){return false;}
bool r79DmsOnlyTransmit(const twai_message_t&){return false;}
'''
helpers += due_helper + '\n'
helpers += '\n'.join(production(sig) for sig in (
    'static void r79FixedObserveStock(', 'static bool r79DmsWorkPendingSnapshot(',
    'static bool r79ProcessStockFrame(', 'static void r79FixedTick(',
    'static void r79TransportSliceTick('))
bridge = r'''
namespace runtime {
static bool r79ServiceWorkDueSnapshot(uint32_t now){return ::r79ServiceWorkDueSnapshot(now);}
bool r79ProcessStockFrame(const twai_message_t& f,uint8_t mux,uint32_t now){
 ::twai_message_t copy{};copy.identifier=f.identifier;copy.data_length_code=f.data_length_code;
 copy.extd=f.extd;copy.rtr=f.rtr;memcpy(copy.data,f.data,8);
 return ::r79ProcessStockFrame(copy,mux,now);
}
void r79TransportSliceTick(bool ready){::r79TransportSliceTick(ready);}
}
'''
main = transport['main'].split('int main(){')[0] + r'''
void push(unsigned id,uint8_t mux=0){runtime::twai_message_t f;f.identifier=id;f.data[0]=mux;runtime::queue.push_back(f);}
void runAt(uint32_t at){nowMs=runtime::nowMs=at;runtime::productionRxAndService();}
void resetCase(uint32_t base=1000){
 reset();runtime::scheduler=runtime::RuntimeScheduler{};runtime::queue.clear();runtime::stepMs=0;runtime::processed=0;
 runtime::inputDone=runtime::stockObserved=runtime::yields=0;runtime::receiveWaits.clear();
 runtime::nativeReady=runtime::refreshAvailable=true;r79QuietGuardSkip=0;
 runtime::beforeReceive=nullptr;runtime::receiveError=false;
 nowMs=runtime::nowMs=base;result=ESP_OK;
 push(0x3FD,1);push(0x3FD,2);runAt(base);
 assert(calls==1&&!r79RetryPending&&r79FixedQuietState.pending);
}
void floodAt(uint32_t at){while(runtime::queue.size()<130)push(0x123);runAt(at);assert(!runtime::queue.empty());}
int main(){
 const auto ordinary=queue;
 // The real quiet reservation and retry are submitted before the first RX
 // wait, rather than merely at a bounded point after it. No input is needed.
 for(uint32_t base:{1000u,UINT32_MAX-100u}){
  resetCase(base);
  runtime::beforeReceive=[](unsigned wait){if(wait)assert(calls==2&&!r79FixedQuietState.pending);};
  runAt(base+150);assert(calls==2&&runtime::queue.empty());
  resetCase(base);result=ESP_ERR_TIMEOUT;runAt(base+150);
  assert(calls==2&&r79RetryPending&&r79RetryDueMs==base+155);
  result=ESP_OK;
  runtime::beforeReceive=[](unsigned wait){if(wait)assert(calls==3&&!r79RetryPending);};
  runAt(base+155);assert(calls==3&&runtime::queue.empty());
  resetCase(base);result=ESP_ERR_TIMEOUT;assert(r79FixedFastEcho(stockFrame()));
  result=ESP_OK;
  runtime::beforeReceive=[](unsigned wait){if(wait)assert(calls==3&&!r79RetryPending);};
  runAt(base+5);assert(calls==3);
 }
 // Unseen MUX0/1/2 fences quiet admission before the wait; dequeue then
 // invalidates/rearms through the real stock observer without consuming it early.
 for(uint8_t mux:{0u,1u,2u}){
  resetCase();push(0x3FD,mux);
  runtime::beforeReceive=[](unsigned wait){if(wait)assert(calls==1&&r79FixedQuietState.pending&&r79FixedQuietState.dueMs==1150);};
  runAt(1150);assert(calls==(mux==1?2u:1u));
 }
 // The same unread-boundary fence applies to an already reserved periodic
 // retry: the pre-wait checkpoint must not spend its attempt or due time.
 resetCase();result=ESP_ERR_TIMEOUT;runAt(1150);assert(r79RetryPending);
 push(0x3FD,0);result=ESP_OK;
 runtime::beforeReceive=[](unsigned wait){if(wait)assert(calls==2&&r79RetryPending&&r79RetryDueMs==1155&&r79RetryIndex==0);};
 runAt(1155);assert(calls==2&&!r79RetryPending);
 // Native periodic readiness cannot withhold an immediate retry before RX.
 resetCase();result=ESP_ERR_TIMEOUT;assert(r79FixedFastEcho(stockFrame()));
 runtime::nativeReady=false;push(0x3FD,0);result=ESP_OK;
 runtime::beforeReceive=[](unsigned wait){if(wait)assert(calls==3&&!r79RetryPending);};
 runAt(1005);assert(calls==3&&runtime::queue.empty());
 // A busy application refresh leaves both quiet and retry reservations intact
 // across the wait, while native boundary checks continue to run.
 resetCase();runtime::refreshAvailable=false;const auto busyQuiet=r79FixedQuietState;
 runAt(1150);assert(calls==1&&memcmp(&busyQuiet,&r79FixedQuietState,sizeof(busyQuiet))==0);
 resetCase();result=ESP_ERR_TIMEOUT;runAt(1150);runtime::refreshAvailable=false;
 const auto busyDue=r79RetryDueMs,busyGeneration=r79RetryGeneration;
 runAt(1155);assert(calls==2&&r79RetryPending&&r79RetryDueMs==busyDue&&r79RetryIndex==0&&r79RetryGeneration==busyGeneration);
 // MUX2+150 initial work fires during the first bounded unrelated slice.
 resetCase();floodAt(1150);
 assert(calls==2&&!r79FixedQuietState.pending&&!r79RetryPending&&r79QuietGuardSkip==0);
 // Retry is real: failed admission arms +5, then +15 and +30, without
 // clearing or changing ordinary TX FIFO, even with sustained RX backlog.
 resetCase();result=ESP_ERR_TIMEOUT;floodAt(1150);
 assert(calls==2&&r79RetryPending&&r79RetryDueMs==1155&&r79RetryIndex==0);
 for(uint32_t due:{1155u,1170u,1200u})floodAt(due);
 assert(calls==5&&!r79RetryPending);
 // Native not-ready must retain initial due time and retry due/index/generation.
 resetCase();runtime::nativeReady=false;const auto quiet=r79FixedQuietState;
 floodAt(1150);floodAt(1180);
 assert(calls==1&&r79FixedQuietState.pending&&memcmp(&quiet,&r79FixedQuietState,sizeof(quiet))==0);
 runtime::nativeReady=true;floodAt(1200);assert(calls==2&&!r79FixedQuietState.pending);
 resetCase();result=ESP_ERR_TIMEOUT;floodAt(1150);
 const auto due=r79RetryDueMs, generation=r79RetryGeneration;
 runtime::nativeReady=false;floodAt(1155);floodAt(1200);
 assert(calls==2&&r79RetryPending&&r79RetryDueMs==due&&r79RetryIndex==0&&r79RetryGeneration==generation);
 runtime::nativeReady=true;result=ESP_OK;floodAt(1201);assert(calls==3&&!r79RetryPending);
 // Deferred initial and retry work still expire at the original hard window,
 // including uint32 rollover. Readiness cannot revive expired work.
 for(uint32_t base:{1000u,UINT32_MAX-100u}){
  resetCase(base);runtime::nativeReady=false;floodAt(base+150u);
  runtime::nativeReady=true;floodAt(base+341u);
  assert(calls==1&&!r79FixedQuietState.pending&&r79QuietGuardSkip==1);
  resetCase(base);result=ESP_ERR_TIMEOUT;floodAt(base+150u);
  runtime::nativeReady=false;floodAt(base+155u);assert(calls==2&&r79RetryIndex==0);
  runtime::nativeReady=true;result=ESP_OK;floodAt(base+341u);
  assert(calls==2&&!r79RetryPending);
 }
 // Immediate retry service stays available when periodic native readiness is false.
 resetCase();result=ESP_ERR_TIMEOUT;assert(r79FixedFastEcho(stockFrame()));
 assert(r79RetryPending&&r79RetryOriginKind==R79LAB_TX_IMMEDIATE);
 runtime::nativeReady=false;result=ESP_OK;floodAt(1005);assert(calls==3&&!r79RetryPending);
 // A new MUX1 within a backlog still takes the immediate path and invalidates
 // both the previous quiet slot and a pending periodic retry.
 resetCase();result=ESP_ERR_TIMEOUT;floodAt(1150);assert(r79RetryPending);
 runtime::twai_message_t newer;newer.identifier=0x3FD;newer.data[0]=1;
 runtime::queue.push_front(newer);result=ESP_OK;floodAt(1155);
 assert(calls==3&&!r79RetryPending&&!r79FixedQuietState.pending);
 assert(queue==ordinary&&clears==0);
}
'''
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'backlog.cpp'
    binary = Path(td) / 'backlog'
    path.write_text(headers + '\nnamespace runtime {\n' + rx + '\n}\n' +
                    prelude + transport['functions'] + helpers + bridge + main)
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-function', '-Wno-unused-variable',
                    '-I' + str(ROOT / 'tests'), '-I' + str(ROOT), str(path),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('PASS: actual quiet initial/retry under unrelated backlog, native deferral budget, deadlines, rollover, immediate service and FIFO')
