"""Real stock observers + consumed FIRE + native priority/IRQ dispatch integration.

Only the immediate transport boundary is bound to the real native admission API;
queue, HAL and platform primitives come from the existing native driver fixture.
P4_R79_CYCLE_BASELINE=1 selects the immutable predecessor observers for RED.
"""
import ast
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def fixture_module(path):
    """Reuse fixture construction without executing its standalone scenarios."""
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.With):
            break
        nodes.append(node)
    namespace = {'__file__': str(path), '__name__': 'native_cycle_fixture'}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


native = fixture_module(ROOT / 'tests/test_p4_twai_native_priority_host.py')['fixture']
native = native[:native.index('int main(void) {')]
# The real recorder remains compiled as C. Match its platform-stub C linkage.
for declaration in ('void diagFakeEnter(void)', 'void diagFakeExit(void)',
                    'int64_t esp_timer_get_time(void)'):
    native = native.replace(declaration, 'extern "C" ' + declaration)

vehicle_root = (ROOT.parent / 'P4-CAN-Universal-v3.33.5.1'
                if os.environ.get('P4_R79_CYCLE_BASELINE') == '1' else ROOT)
source = (vehicle_root / 'vehicle_logic.h').read_text()


def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


application = r'''
#include "r79_fixed_policy_pure.h"
#include "r79_dms_composition_pure.h"
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
static twai_handle_t cycleDriver;
static unsigned immediateAttempts;
static esp_err_t immediateResult;
static bool r79FixedFastEcho(const twai_message_t &stock) {
    ++immediateAttempts;
    twai_message_t immediate=stock;
    immediate.data[0]=1; immediate.data[7]=0xEE;
    p4_twai_priority_guard_t immediateGuard=guard;
    immediateGuard.cancel_generation=NULL;
    immediateGuard.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE;
    immediateResult=p4_twai_transmit_r79_v2(cycleDriver,&immediate,&immediateGuard);
    return immediateResult==ESP_OK;
}
static bool r79DmsWorkPendingSnapshot() { return false; }
static bool r79DmsControlActive() { return false; }
static bool r79DmsOnlyTransmit(const twai_message_t&) { return false; }
'''
application += '\n'.join(function(signature) for signature in (
    'static void r79FixedObserveStock(uint8_t mux, uint32_t nowMs) {',
    'static bool r79ProcessStockFrame(const twai_message_t &src, uint8_t mux,\n                                 uint32_t nowMs) {'))

scenarios = r'''
int main() {
    unsigned cases=0;
    for(uint8_t next=0;next<=2;++next)
    for(unsigned rollover=0;rollover<2;++rollover) {
        twai_obj_t driver;twai_hal_context_t hal;Queue queue,rx;
        init(&driver,&hal,&queue,&rx,0);cycleDriver=&driver;
        r79FixedQuietState={};
        r79RetryPending=false;immediateAttempts=0;immediateResult=ESP_FAIL;
        r79Mode1PostMux2Generation=rollover?UINT32_MAX-1:100;
        twai_message_t stock={};stock.identifier=0x3FD;stock.data_length_code=8;
        stock.data[0]=2;nowMs=1000;
        r79ProcessStockFrame(stock,2,nowMs);
        nowMs=1015;
        // Production pure step consumes pending before native admission occurs.
        assert(r79FixedQuietStepPure(r79FixedQuietState,nowMs,true)==R79_FIXED_QUIET_FIRE_PURE);
        normal.identifier=0x111;assert(twai_transmit_v2(&driver,&normal,0)==ESP_OK);
        normal.identifier=0x222;assert(twai_transmit_v2(&driver,&normal,0)==ESP_OK);
        normal.identifier=0x333;assert(twai_transmit_v2(&driver,&normal,0)==ESP_OK);
        twai_message_t oldPeriodic=stock;oldPeriodic.data[0]=1;oldPeriodic.data[7]=0xDD;
        guard.cancel_generation=&r79Mode1PostMux2Generation;
        guard.expected_cancel_generation=r79Mode1PostMux2Generation;
        guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
        const uint32_t obsolete=guard.expected_cancel_generation;
        assert(p4_twai_transmit_r79_v2(&driver,&oldPeriodic,&guard)==ESP_OK);
        assert(queue.n==2 && hal.n==1 && driver.tx_msg_count==4);
        P4TwaiErrorSnapshot snapshot;
        assert(p4TwaiDiagSnapshot(&snapshot));
        const uint32_t oldRequest=snapshot.buses[0].lifecycle.events[0].tx.requestId;
        stock.data[0]=next;nowMs=1016;
        r79ProcessStockFrame(stock,next,nowMs);
        finish(&driver); // Actual IRQ selects next controller frame.
        assert(!(hal.sent[1].header.id==0x3FD && hal.sent[1].data[7]==0xDD)
               && "new stock cycle must invalidate already-admitted periodic R79 after FIRE");
        assert(r79Mode1PostMux2Generation!=obsolete);
        if(next==1) {
            assert(immediateAttempts==1 && immediateResult==ESP_OK);
            assert(hal.sent[1].header.id==0x3FD && hal.sent[1].data[7]==0xEE);
            assert(queue.n==2);finish(&driver);
            assert(hal.sent[2].header.id==0x222);finish(&driver);
            assert(hal.sent[3].header.id==0x333);finish(&driver);
        } else {
            assert(immediateAttempts==0 && hal.sent[1].header.id==0x222);
            assert(queue.n==1);finish(&driver);
            assert(hal.sent[2].header.id==0x333);finish(&driver);
        }
        assert(driver.tx_msg_count==0 && queue.n==0 && !lockDepth && !diagDepth);
        assert(p4TwaiDiagSnapshot(&snapshot));
        unsigned cancelled=0,oldLoaded=0;
        const auto &life=snapshot.buses[0].lifecycle;
        for(uint32_t index=0;index<life.count;++index) {
            const auto &event=life.events[index];
            if(event.tx.requestId!=oldRequest)continue;
            if(event.kind==P4_TWAI_TX_CANCELLED) {
                ++cancelled;assert(event.reason==P4_TWAI_TX_REASON_CANCEL_GENERATION);
            }
            if(event.kind==P4_TWAI_TX_LOADED)++oldLoaded;
        }
        assert(cancelled==1 && oldLoaded==0);
        ++cases;
    }
    printf("PASS %u actual Mode1 consumed FIRE -> native pending -> MUX0/1/2 -> IRQ cases; cancellation, immediate precedence, ordinary FIFO and generation rollover\n",cases);
}
'''

with tempfile.TemporaryDirectory(prefix='p4-native-cycle-') as directory:
    work = Path(directory)
    (work / 'esp_attr.h').write_text('#define IRAM_ATTR\n#define DRAM_ATTR\n')
    (work / 'esp_timer.h').write_text('#include <stdint.h>\nint64_t esp_timer_get_time(void);\n')
    (work / 'freertos').mkdir()
    (work / 'freertos/FreeRTOS.h').write_text(
        '#pragma once\ntypedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\n'
        'void diagFakeEnter(void); void diagFakeExit(void);\n'
        '#define portENTER_CRITICAL(p) ((void)(p),diagFakeEnter())\n'
        '#define portEXIT_CRITICAL(p) ((void)(p),diagFakeExit())\n'
        '#define portENTER_CRITICAL_ISR portENTER_CRITICAL\n'
        '#define portEXIT_CRITICAL_ISR portEXIT_CRITICAL\n')
    (work / 'freertos/portmacro.h').write_text('#include "FreeRTOS.h"\n')
    (work / 'cycle.cpp').write_text(native + application + scenarios)
    includes = ['-I', str(work), '-I', str(ROOT)]
    subprocess.run([os.environ.get('CC', '/usr/bin/cc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', *includes, '-c', str(ROOT / 'p4_twai_diag.c'),
                    '-o', str(work / 'diag.o')], check=True)
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra',
                    '-Wno-unused-function', '-Wno-unused-variable', '-Wno-c99-designator',
                    '-Wno-missing-field-initializers', '-Wno-reorder-init-list',
                    *includes, str(work / 'cycle.cpp'), str(work / 'diag.o'),
                    '-o', str(work / 'cycle')], check=True)
    subprocess.run([str(work / 'cycle')], check=True)
