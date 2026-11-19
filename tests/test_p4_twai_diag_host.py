"""Compile the production ISR recorder as C and exercise its C ABI from C++."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


PACKAGE = Path(__file__).resolve().parents[1]


class TwaiDiagnosticHostTest(unittest.TestCase):
    def test_actual_c_isr_error_history(self):
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        self.assertIsNotNone(shutil.which(compiler[0]), "host compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="p4-twai-diag-") as tmp:
            work = Path(tmp)
            (work / "freertos").mkdir()
            (work / "esp_attr.h").write_text("#define IRAM_ATTR\n#define DRAM_ATTR\n")
            (work / "esp_timer.h").write_text(
                '#include <stdint.h>\n#ifdef __cplusplus\nextern "C" {\n#endif\n'
                'int64_t esp_timer_get_time(void);\n#ifdef __cplusplus\n}\n#endif\n'
            )
            (work / "freertos" / "FreeRTOS.h").write_text(
                '#ifndef DIAG_FAKE_PORT\n#define DIAG_FAKE_PORT\n'
                'typedef struct { int unused; } portMUX_TYPE;\n'
                '#define portMUX_INITIALIZER_UNLOCKED {0}\n'
                '#ifdef __cplusplus\nextern "C" {\n#endif\n'
                'void diagFakeEnter(int isr);\nvoid diagFakeExit(int isr);\n'
                '#ifdef __cplusplus\n}\n#endif\n'
                '#define portENTER_CRITICAL(p) ((void)(p), diagFakeEnter(0))\n'
                '#define portEXIT_CRITICAL(p) ((void)(p), diagFakeExit(0))\n'
                '#define portENTER_CRITICAL_ISR(p) ((void)(p), diagFakeEnter(1))\n'
                '#define portEXIT_CRITICAL_ISR(p) ((void)(p), diagFakeExit(1))\n'
                '#endif\n'
            )
            (work / "freertos" / "portmacro.h").write_text('#include "FreeRTOS.h"\n')
            harness = work / "test.cpp"
            harness.write_text(HARNESS)
            obj = work / "diag.o"
            build_c = subprocess.run(
                compiler + ["-x", "c", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(work), "-I", str(PACKAGE), "-c",
                            str(PACKAGE / "p4_twai_diag.c"), "-o", str(obj)],
                text=True, capture_output=True,
            )
            self.assertEqual(build_c.returncode, 0, build_c.stdout + build_c.stderr)
            binary = work / "test"
            build_cpp = subprocess.run(
                compiler + ["-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                            "-I", str(work), "-I", str(PACKAGE), str(harness),
                            str(obj), "-o", str(binary)], text=True, capture_output=True,
            )
            self.assertEqual(build_cpp.returncode, 0, build_cpp.stdout + build_cpp.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
            # A separate C translation unit includes the real source solely to
            # seed otherwise impractical UINT32_MAX counter boundaries. The
            # shipped API has no test-only setter or widened public surface.
            boundary = work / "boundary.c"
            boundary.write_text(BOUNDARY)
            boundary_binary = work / "boundary"
            build_boundary = subprocess.run(
                compiler + ["-x", "c", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(work), "-I", str(PACKAGE), str(boundary),
                            "-o", str(boundary_binary)], text=True, capture_output=True,
            )
            self.assertEqual(build_boundary.returncode, 0,
                             build_boundary.stdout + build_boundary.stderr)
            boundary_result = subprocess.run([str(boundary_binary)], text=True,
                                             capture_output=True, timeout=10)
            self.assertEqual(boundary_result.returncode, 0,
                             boundary_result.stdout + boundary_result.stderr)
            print(boundary_result.stdout.strip())


HARNESS = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include "p4_twai_diag.h"
#include "p4_twai_error_decode_pure.h"

static std::mutex mux;
static std::atomic<uint64_t> clockUs{UINT64_C(1) << 40};
static std::atomic<unsigned> isrLocks{0}, taskLocks{0};
static std::atomic<int> taskHook{0};
static thread_local bool inHook = false;

extern "C" int64_t esp_timer_get_time(void) { return (int64_t)clockUs.fetch_add(1); }
extern "C" void diagFakeEnter(int isr) {
    mux.lock();
    (isr ? isrLocks : taskLocks).fetch_add(1);
}
extern "C" void diagFakeExit(int isr) {
    mux.unlock();
    if (isr || inHook) return;
    inHook = true;
    const int mode = taskHook.load();
    if (mode == 1) p4TwaiDiagRecordFromIsr(0, 123, 456, 789, 987, 654);
    if (mode == 3) {
        P4TwaiTxIdentity tx{}; tx.identifier=123;
        p4TwaiDiagTxLoaded(0, &tx);
        P4TwaiVehicleContext vehicle{}; vehicle.gear=4;
        p4TwaiDiagPublishVehicleContext(&vehicle);
    }
    if (mode == 4) { uint8_t data[8]={0}; p4TwaiDiagRxFromIsr(1,123,8,0,data); }
    if (mode == 5) p4TwaiDiagRecordFromIsr(1,1,2,3,4,5);
    if (mode == 2 && taskHook.exchange(0) == 2) p4TwaiDiagInit(999);
    inHook = false;
}

static void record(uint8_t bus, uint32_t n) {
    p4TwaiDiagRecordFromIsr(bus, n, n ^ 0x12345678u, n + 10, n + 20, n + 30);
}

static void checkBus(const P4TwaiErrorBusSnapshot &b) {
    assert(b.count <= P4_TWAI_DIAG_CAPACITY);
    assert(b.hasFirst == (b.observed != 0));
    assert(b.hasLast == (b.observed != 0));
    for (uint32_t i = 0; i < b.count; ++i) {
        const auto &e = b.events[i];
        assert(e.status == (e.ecc ^ 0x12345678u));
        assert(e.tec == e.ecc + 10 && e.rec == e.ecc + 20 && e.halFlags == e.ecc + 30);
        assert(e.observedUs > (UINT64_C(1) << 32));
        if (i) assert(b.events[i - 1].seq + 1 == e.seq);
    }
    if (b.count) {
        assert(b.events[b.count - 1].seq == b.last.seq);
        assert(b.first.seq == 1);
    }
}

static void receiveRx(uint32_t id, uint8_t flags=0, uint8_t dlc=8) {
    uint8_t data[8]; for(unsigned i=0;i<8;++i)data[i]=(uint8_t)(id+i);
    p4TwaiDiagRxFromIsr(1,id,dlc,flags,data);
}
static void checkRxCapture() {
    P4TwaiErrorSnapshot out{};
    p4TwaiDiagInit(400);
    p4TwaiDiagConfigureRxCapture(0,true); p4TwaiDiagConfigureRxCapture(2,true);
    receiveRx(1); record(1,1);
    assert(p4TwaiDiagSnapshot(&out));
    assert(!out.rxCapture.enabled && out.rxCapture.controllerSession==0 && out.rxCapture.count==0);
    p4TwaiDiagConfigureRxCapture(1,true);
    assert(p4TwaiDiagRxCaptureEnabledFromIsr(1));
    assert(!p4TwaiDiagRxCaptureEnabledFromIsr(0)&&!p4TwaiDiagRxCaptureEnabledFromIsr(2));
    // No preframes; empty payload for RTR and invalid DLC excluded from history.
    record(1,2);receiveRx(5,3,8);receiveRx(6,0,9);
    assert(p4TwaiDiagSnapshot(&out));
    auto w=out.rxCapture.windows[0];
    assert(w.preCount==0 && w.postCount==1 && w.status==P4_TWAI_RX_COLLECTING);
    assert(w.post[0].flags==3 && w.post[0].dlc==8);
    for(auto byte:w.post[0].data)assert(byte==0);
    assert(out.rxCapture.invalidDlc==1 && out.rxCapture.rxObserved==1);
    assert(w.firstErrorSeq==2 && w.firstErrorOrder<w.post[0].observationOrder);
    clockUs.store(w.deadlineUs); assert(p4TwaiDiagSnapshot(&out));
    assert(out.rxCapture.windows[0].status==P4_TWAI_RX_EXPIRED);
    assert(out.rxCapture.windows[0].postCount==1 && out.rxCapture.windows[0].closedUs>=w.deadlineUs);
    // Chronological ring wrap, mixed RX/error hook order, deadline never extends.
    p4TwaiDiagInit(401);p4TwaiDiagConfigureRxCapture(1,true);
    for(unsigned i=0;i<40;++i)receiveRx(100+i);
    record(1,1);receiveRx(200);record(1,2);
    assert(p4TwaiDiagSnapshot(&out));w=out.rxCapture.windows[0];
    assert(w.preCount==16&&w.postCount==1&&w.errorCount==2);
    assert(w.firstErrorSeq==1&&w.lastErrorSeq==2&&w.firstErrorUs<w.lastErrorUs);
    assert(w.deadlineUs==w.firstErrorUs+100000);
    for(unsigned i=0;i<16;++i){
        assert(w.pre[i].identifier==124+i&&w.pre[i].seq==25+i);
        assert(w.pre[i].observationOrder==25+i);
        for(unsigned d=0;d<8;++d)assert(w.pre[i].data[d]==(uint8_t)(124+i+d));
    }
    assert(w.pre[15].observationOrder<w.firstErrorOrder);
    assert(w.firstErrorOrder<w.post[0].observationOrder&&w.post[0].observationOrder<w.lastErrorOrder);
    for(unsigned i=1;i<16;++i)receiveRx(200+i);
    assert(p4TwaiDiagSnapshot(&out));w=out.rxCapture.windows[0];
    assert(w.status==P4_TWAI_RX_COMPLETE&&w.postCount==16&&w.closedUs==w.post[15].observedUs);
    auto frozen=w;
    // Ordinary traffic during every export lock exit cannot starve the export.
    taskHook.store(4);assert(p4TwaiDiagSnapshot(&out));taskHook.store(0);
    assert(std::memcmp(&frozen,&out.rxCapture.windows[0],sizeof(frozen))==0);
    // Reconfiguration closes partial window and starts a separate empty prehistory.
    record(1,3);receiveRx(300);p4TwaiDiagConfigureRxCapture(1,true);record(1,4);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.rxCapture.controllerSession==2&&out.rxCapture.count==3);
    assert(out.rxCapture.windows[1].status==P4_TWAI_RX_RECONFIGURED);
    assert(out.rxCapture.windows[1].postCount==1&&out.rxCapture.windows[1].controllerSession==1);
    assert(out.rxCapture.windows[2].preCount==0&&out.rxCapture.windows[2].controllerSession==2);
    assert(std::memcmp(&frozen,&out.rxCapture.windows[0],sizeof(frozen))==0);
    p4TwaiDiagConfigureRxCapture(1,false);receiveRx(999);record(1,5);
    assert(p4TwaiDiagSnapshot(&out));
    assert(!out.rxCapture.enabled&&out.rxCapture.count==3);
    assert(out.rxCapture.windows[2].status==P4_TWAI_RX_RECONFIGURED);
    // Error after timeout opens a new window; late RX never becomes old post data.
    p4TwaiDiagInit(402);p4TwaiDiagConfigureRxCapture(1,true);record(1,1);
    assert(p4TwaiDiagSnapshot(&out));clockUs.store(out.rxCapture.windows[0].deadlineUs);
    receiveRx(400);record(1,2);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.rxCapture.windows[0].status==P4_TWAI_RX_EXPIRED&&out.rxCapture.windows[0].postCount==0);
    assert(out.rxCapture.windows[1].preCount==1&&out.rxCapture.windows[1].pre[0].identifier==400);
    clockUs.store(out.rxCapture.windows[1].deadlineUs);record(1,3);
    assert(p4TwaiDiagSnapshot(&out));assert(out.rxCapture.windows[1].status==P4_TWAI_RX_EXPIRED);
    // Retention is latest four windows, count and overwrite accounting explicit.
    for(unsigned n=3;n<10;++n){
        clockUs.fetch_add(100001);record(1,n+1);
    }
    assert(p4TwaiDiagSnapshot(&out));assert(out.rxCapture.count==4&&out.rxCapture.observed==10&&out.rxCapture.overwritten==6);
    for(unsigned n=0;n<4;++n)assert(out.rxCapture.windows[n].seq==7+n);
    // Every export attempt seeing an actual frozen-window mutation must fail boundedly.
    taskHook.store(5);assert(!p4TwaiDiagSnapshot(&out));taskHook.store(0);
    assert(!out.consistent&&out.rxCapture.count==0);
    p4TwaiDiagInit(403);assert(p4TwaiDiagSnapshot(&out));
    assert(out.rxCapture.count==0&&out.rxCapture.controllerSession==0&&!out.rxCapture.enabled);
}

int main() {
#ifndef P4_TWAI_TX_CONTEXT_VERSION
    assert(false && "ECC must retain actual loaded TX and vehicle context");
#endif
    static_assert(sizeof(P4TwaiErrorEvent) == 120, "fixed ISR record size");
    static_assert(sizeof(P4TwaiErrorSnapshot) < 40 * 1024, "bounded export memory");
    P4TwaiErrorSnapshot out{};
    record(0, 99);
    assert(!p4TwaiDiagSnapshot(&out));
    assert(!p4TwaiDiagSnapshot(nullptr));
    checkRxCapture();
    p4TwaiDiagInit(17);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.consistent && out.bootId == 17 && out.invalidBus == 0);
    for (const auto &b : out.buses) assert(b.count == 0 && !b.hasFirst && !b.hasLast);

    for (uint8_t bus = 0; bus < 3; ++bus)
        for (uint32_t n = 0; n < 201 + bus; ++n) record(bus, n + bus * 1000);
    record(3, 1); record(255, 1);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.invalidBus == 2);
    for (uint8_t bus = 0; bus < 3; ++bus) {
        const auto &b = out.buses[bus];
        assert(b.count == 64 && b.observed == 201u + bus && b.overwritten == 137u + bus);
        assert(b.first.ecc == bus * 1000u && b.last.ecc == bus * 1000u + 200u + bus);
        assert(b.events[0].ecc == bus * 1000u + 137u + bus);
        assert(b.copiedAtUs >= b.last.observedUs && b.copiedAtUs <= out.capturedUs);
        checkBus(b);
    }
    const auto before = out;
    assert(p4TwaiDiagSnapshot(&out));
    for (unsigned bus = 0; bus < 3; ++bus) {
        assert(out.buses[bus].observed == before.buses[bus].observed);
        assert(std::memcmp(out.buses[bus].events, before.buses[bus].events,
                           sizeof(out.buses[bus].events)) == 0);
    }
    assert(isrLocks.load() != 0 && taskLocks.load() != 0);

    // Exact capture-time identity/context; mutation after ECC is irrelevant.
    p4TwaiDiagInit(171);
    P4TwaiVehicleContext vehicle{};
    vehicle.publishedMs=100; vehicle.gearObservedMs=90; vehicle.apObservedMs=80;
    vehicle.summonObservedMs=70; vehicle.gear=4; vehicle.gearSource=2;
    vehicle.gearValid=1; vehicle.apState=3; vehicle.apValid=1;
    vehicle.summonActive=1; vehicle.summonValid=1;
    p4TwaiDiagPublishVehicleContext(&vehicle);
    P4TwaiTxIdentity tx{}; tx.identifier=0x3FD; tx.dlc=8; tx.data[0]=1;
    tx.source=P4_TWAI_TX_SOURCE_R79_PERIODIC; tx.requestId=17; tx.queuedUs=42;
    tx.rxObservedUs=10; tx.rxDequeuedUs=20; tx.rxSequence=9;
    p4TwaiDiagTxQueued(0,&tx); p4TwaiDiagTxLoaded(0,&tx); record(0,3);
    p4TwaiDiagTxRetire(0,P4_TWAI_TX_REASON_SUCCESS); record(0,4);
    tx.rxObservedUs=tx.rxDequeuedUs=tx.rxSequence=0; // Caller mutation cannot rewrite retained evidence.
    vehicle.gear=2; p4TwaiDiagPublishVehicleContext(&vehicle);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.buses[0].events[0].tx.active && out.buses[0].events[0].tx.valid);
    assert(out.buses[0].events[0].tx.identifier==0x3FD);
    assert(out.buses[0].events[0].tx.rxObservedUs==10 && out.buses[0].events[0].tx.rxDequeuedUs==20 && out.buses[0].events[0].tx.rxSequence==9);
    assert(out.buses[0].last.tx.rxObservedUs==10 && out.buses[0].last.tx.rxDequeuedUs==20 && out.buses[0].last.tx.rxSequence==9);
    assert(out.buses[0].events[0].vehicle.gear==4);
    assert(out.buses[0].events[0].vehicle.apObservedMs==80);
    assert(!out.buses[0].last.tx.active && out.buses[0].last.tx.valid);
    assert(out.buses[0].lifecycle.count==3);
    for(const auto &e : out.buses[0].lifecycle.events) if(e.seq) {
        assert(e.tx.requestId==17 && e.tx.queuedUs==42 && e.vehicle.gear==4);
        assert(e.tx.rxObservedUs==10 && e.tx.rxDequeuedUs==20 && e.tx.rxSequence==9);
    }
    tx.rxObservedUs=10; tx.rxDequeuedUs=20; tx.rxSequence=9;
    for(unsigned i=0;i<100;++i) p4TwaiDiagTxCancelled(0,&tx,P4_TWAI_TX_REASON_HOLD);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.buses[0].lifecycle.count==32 && out.buses[0].lifecycle.observed==103);
    assert(out.buses[0].lifecycle.overwritten==71);
    assert(out.buses[0].lifecycle.events[0].seq==72);
    for(const auto &e:out.buses[0].lifecycle.events) {
        assert(e.kind==P4_TWAI_TX_CANCELLED && e.tx.rxObservedUs==10 && e.tx.rxDequeuedUs==20 && e.tx.rxSequence==9);
        assert(!e.tx.valid && e.tx.loadedUs==0);
    }
    taskHook.store(3); assert(p4TwaiDiagSnapshot(&out)); taskHook.store(0);
    // Ordinary shadow updates/publication cannot starve a journal export.
    assert(out.buses[0].last.tx.identifier==0x3FD && out.buses[0].last.vehicle.gear==4);
    p4TwaiDiagInit(172); record(0,1); assert(p4TwaiDiagSnapshot(&out));
    assert(!out.buses[0].last.tx.valid && !out.buses[0].last.tx.active);
    assert(out.buses[0].last.vehicle.publishedMs==0 && !out.buses[0].last.vehicle.gearValid);
    assert(out.buses[0].lifecycle.count==0);

    // Every retirement reason preserves RX origin in both terminal lifecycle
    // evidence and subsequent ECC historical identity; ordinary load resets it.
    for(uint8_t reason=P4_TWAI_TX_REASON_SUCCESS;reason<=P4_TWAI_TX_REASON_RX_PENDING;++reason) {
        p4TwaiDiagInit(173);p4TwaiDiagTxQueued(0,&tx);p4TwaiDiagTxLoaded(0,&tx);
        p4TwaiDiagTxRetire(0,reason);record(0,5);assert(p4TwaiDiagSnapshot(&out));
        assert(out.buses[0].lifecycle.count==3);
        const auto &terminal=out.buses[0].lifecycle.events[2];
        assert(terminal.reason==reason && terminal.tx.valid && !terminal.tx.active);
        assert(terminal.tx.rxObservedUs==10 && terminal.tx.rxDequeuedUs==20 && terminal.tx.rxSequence==9);
        assert(out.buses[0].last.tx.rxObservedUs==10 && out.buses[0].last.tx.rxDequeuedUs==20 && out.buses[0].last.tx.rxSequence==9);
        P4TwaiTxIdentity ordinary{};ordinary.identifier=0x3FD;
        p4TwaiDiagTxLoaded(0,&ordinary);record(0,6);assert(p4TwaiDiagSnapshot(&out));
        assert(out.buses[0].lifecycle.count==3 && out.buses[0].last.tx.rxSequence==0);
        assert(out.buses[0].last.tx.rxObservedUs==0 && out.buses[0].last.tx.rxDequeuedUs==0);
    }

    p4TwaiDiagInit(18);
    taskHook.store(1);
    const auto locksBefore = taskLocks.load();
    assert(!p4TwaiDiagSnapshot(&out));
    assert(!out.consistent && taskLocks.load() - locksBefore <= 700);
    taskHook.store(0);
    p4TwaiDiagInit(19);
    record(0, 99);
    taskHook.store(2);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.bootId == 999 && out.buses[0].observed == 0);
    for (const auto &b : out.buses) {
        assert(!b.hasFirst && !b.hasLast && b.first.seq == 0 && b.last.seq == 0);
        for (const auto &e : b.events) assert(e.seq == 0 && e.ecc == 0 && e.observedUs == 0);
    }

    p4TwaiDiagInit(20);
    std::atomic<bool> finished{false};
    std::thread writer([&] {
        for (uint32_t n = 0; n < 30000; ++n)
            for (uint8_t bus = 0; bus < 3; ++bus) record(bus, n + bus * 100000u);
        finished.store(true);
    });
    unsigned attempts = 0;
    while (!finished.load()) {
        if (p4TwaiDiagSnapshot(&out)) {
            assert(out.consistent && out.bootId == 20);
            for (const auto &b : out.buses) checkBus(b);
        } else assert(!out.consistent);
        ++attempts;
    }
    writer.join();
    assert(p4TwaiDiagSnapshot(&out));
    for (const auto &b : out.buses) {
        checkBus(b);
        assert(b.observed == 30000 && b.overwritten == 29936 && b.count == 64);
    }

    for (unsigned raw = 0; raw < 256; ++raw) {
        auto d = p4TwaiDecodeError(0xBEEF0000u | raw);
        assert(d.type == ((raw >> 6) & 3));
        assert(d.direction == ((raw >> 5) & 1));
        assert(d.segment == (raw & 31));
        assert(d.ackError == ((((raw >> 6) & 3) == 3) && ((raw & 31) == 25)));
    }
    assert(!std::strcmp(p4TwaiErrorTypeLabel(0), "BIT"));
    assert(!std::strcmp(p4TwaiErrorTypeLabel(1), "FORM"));
    assert(!std::strcmp(p4TwaiErrorTypeLabel(2), "STUFF"));
    assert(!std::strcmp(p4TwaiErrorTypeLabel(3), "OTHER"));
    assert(!std::strcmp(p4TwaiErrorTypeLabel(255), "UNKNOWN"));
    assert(!std::strcmp(p4TwaiErrorDirectionLabel(0), "TX"));
    assert(!std::strcmp(p4TwaiErrorDirectionLabel(1), "RX"));
    assert(!std::strcmp(p4TwaiErrorSegmentLabel(25), "ACK_SLOT"));
    assert(!std::strcmp(p4TwaiErrorSegmentLabel(8), "CRC_SEQUENCE"));
    assert(!std::strcmp(p4TwaiErrorSegmentLabel(24), "CRC_DELIMITER"));
    assert(!std::strcmp(p4TwaiErrorSegmentLabel(0), "UNKNOWN"));
    assert(!std::strcmp(p4TwaiErrorSegmentLabel(255), "UNKNOWN"));
    assert(!p4TwaiDecodeError((3u << 6) | 8).ackError);
    std::printf("ISR ring C ABI, 3x30000 burst, snapshot race and 256 raw ECC cases pass (%u exports)\n", attempts);
}
'''


BOUNDARY = r'''
#include <assert.h>
#include <stdio.h>
#include "p4_twai_diag.c"
#include "p4_twai_error_decode_pure.h"

static int64_t clockUs = INT64_C(1) << 40;
int64_t esp_timer_get_time(void) { return clockUs++; }
void diagFakeEnter(int isr) { (void)isr; }
void diagFakeExit(int isr) { (void)isr; }

int main(void) {
    P4TwaiErrorSnapshot out;
    p4TwaiDiagInit(1234);
    for (unsigned n = 0; n < 64; ++n) p4TwaiDiagRecordFromIsr(0, n, 0, 0, 0, 0);
    sBuses[0].observed = UINT32_MAX - 1;
    sBuses[0].overwritten = UINT32_MAX - 1;
    sInvalidBus = UINT32_MAX - 1;
    p4TwaiDiagRecordFromIsr(0, 1000, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX);
    p4TwaiDiagRecordFromIsr(0, 1001, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX);
    p4TwaiDiagRecordFromIsr(3, 0, 0, 0, 0, 0);
    p4TwaiDiagRecordFromIsr(255, 0, 0, 0, 0, 0);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.invalidBus == UINT32_MAX);
    assert(out.buses[0].observed == UINT32_MAX);
    assert(out.buses[0].overwritten == UINT32_MAX);
    assert(out.buses[0].count == 64 && out.buses[0].first.seq == 1);
    assert(out.buses[0].last.seq == UINT32_MAX && out.buses[0].last.ecc == 1001);
    assert(out.buses[0].events[62].seq == UINT32_MAX);
    assert(out.buses[0].events[63].seq == UINT32_MAX);
    assert(p4TwaiDecodeError(0xD9).ackError);
    P4TwaiTxIdentity tx = {0}; tx.source = P4_TWAI_TX_SOURCE_R79_IMMEDIATE;
    for(unsigned n=0;n<32;++n)p4TwaiDiagTxQueued(0,&tx);
    sLifecycle[0].observed=UINT32_MAX-1; sLifecycle[0].overwritten=UINT32_MAX-1;
    p4TwaiDiagTxQueued(0,&tx); p4TwaiDiagTxQueued(0,&tx);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.buses[0].lifecycle.observed==UINT32_MAX);
    assert(out.buses[0].lifecycle.overwritten==UINT32_MAX);
    assert(out.buses[0].lifecycle.events[31].seq==UINT32_MAX);
    p4TwaiDiagConfigureRxCapture(1,true);
    sRx.capture.controllerSession=UINT32_MAX-1;
    p4TwaiDiagConfigureRxCapture(1,true);p4TwaiDiagConfigureRxCapture(1,true);
    sRx.capture.rxObserved=UINT32_MAX-1;sRx.capture.invalidDlc=UINT32_MAX-1;
    sRx.observationOrder=UINT64_MAX-1;
    uint8_t bytes[8]={1,2,3,4,5,6,7,8};
    p4TwaiDiagRxFromIsr(1,1,8,0,bytes);p4TwaiDiagRxFromIsr(1,2,8,0,bytes);
    p4TwaiDiagRxFromIsr(1,0,9,0,NULL);p4TwaiDiagRxFromIsr(1,0,9,0,NULL);
    p4TwaiDiagRecordFromIsr(1,1,0,0,0,0);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.rxCapture.controllerSession==UINT32_MAX&&out.rxCapture.rxObserved==UINT32_MAX);
    assert(out.rxCapture.invalidDlc==UINT32_MAX);
    assert(out.rxCapture.windows[0].pre[0].seq==UINT32_MAX);
    assert(out.rxCapture.windows[0].pre[1].observationOrder==UINT64_MAX);
    assert(out.rxCapture.windows[0].firstErrorOrder==UINT64_MAX);
    for(unsigned n=0;n<5;++n){clockUs+=100001;p4TwaiDiagRecordFromIsr(1,n,0,0,0,0);}
    sRx.capture.observed=UINT32_MAX-1;sRx.capture.overwritten=UINT32_MAX-1;
    for(unsigned n=0;n<2;++n){clockUs+=100001;p4TwaiDiagRecordFromIsr(1,n,0,0,0,0);}
    sRx.capture.windows[sRx.active].errorCount=UINT32_MAX-1;
    p4TwaiDiagRecordFromIsr(1,1,0,0,0,0);p4TwaiDiagRecordFromIsr(1,1,0,0,0,0);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.rxCapture.observed==UINT32_MAX&&out.rxCapture.overwritten==UINT32_MAX);
    assert(out.rxCapture.windows[3].seq==UINT32_MAX&&out.rxCapture.windows[3].errorCount==UINT32_MAX);
    printf("RX capture state %zu; frame %zu; window %zu; snapshot addition %zu bytes\n",
           sizeof(sRx),sizeof(P4TwaiRxFrame),sizeof(P4TwaiRxWindow),sizeof(P4TwaiRxCaptureSnapshot));
    p4TwaiDiagInit(4321);
    assert(p4TwaiDiagSnapshot(&out));
    assert(out.invalidBus == 0 && out.buses[0].observed == 0);
    printf("Saturating counters and reset pass; runtime %zu + snapshot %zu bytes\n",
           sizeof(sBuses) + sizeof(sLifecycle) + sizeof(sLoaded) + sizeof(sVehicle) + sizeof(sMux) + sizeof(sReady) + sizeof(sBootId)
           + sizeof(sInvalidBus) + sizeof(sEpoch) + sizeof(sRevision) + sizeof(sRx), sizeof(out));
    return 0;
}
'''


if __name__ == "__main__":
    unittest.main()
