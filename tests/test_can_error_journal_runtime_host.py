"""Exercise actual bounded journal hooks, short locks and concurrent export."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARDUINO = r'''
#pragma once
#include <cstdint>
#include <cassert>
#include <mutex>
struct portMUX_TYPE { std::mutex mutex; };
#define portMUX_INITIALIZER_UNLOCKED {}
extern thread_local unsigned lockDepth;
void beforeDiagLock();
static inline void portENTER_CRITICAL(portMUX_TYPE* mux) {
  beforeDiagLock();
  assert(lockDepth == 0);
  mux->mutex.lock();
  ++lockDepth;
}
static inline void portEXIT_CRITICAL(portMUX_TYPE* mux) {
  assert(lockDepth == 1);
  --lockDepth;
  mux->mutex.unlock();
}
'''
TWAI = r'''
#pragma once
#include <cstdint>
constexpr int TWAI_STATE_STOPPED=0,TWAI_STATE_RUNNING=1,TWAI_STATE_BUS_OFF=2,TWAI_STATE_RECOVERING=3;
constexpr uint32_t TWAI_ALERT_TX_SUCCESS=1u<<1,TWAI_ALERT_ARB_LOST=1u<<7,
  TWAI_ALERT_ABOVE_ERR_WARN=1u<<8,TWAI_ALERT_BUS_ERROR=1u<<9,
  TWAI_ALERT_TX_FAILED=1u<<10,TWAI_ALERT_RX_QUEUE_FULL=1u<<11,
  TWAI_ALERT_ERR_PASS=1u<<12,TWAI_ALERT_BUS_OFF=1u<<13;
'''
SOURCE = r'''
#include <atomic>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <new>
#include <thread>
#include "can_error_journal.h"
thread_local unsigned lockDepth = 0;
static thread_local bool exporting = false;
static thread_local unsigned exportLocks = 0;
static bool forceChange = false;
static std::atomic<bool> pauseCopy(false), copyPaused(false), resumeCopy(false);
static std::atomic<uint64_t> nowUs(100);
static std::atomic<unsigned> allocations(0);
void* operator new(std::size_t size) {
  ++allocations;
  if (void* p = std::malloc(size)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
int64_t esp_timer_get_time() {
  assert(lockDepth == 1); // Observation time is sampled after lock admission.
  return static_cast<int64_t>(nowUs.fetch_add(1));
}
void beforeDiagLock() {
  if (!exporting) return;
  ++exportLocks;
  if (forceChange) {
    exporting = false;
    canDiagObserveAlerts(0, TWAI_ALERT_TX_SUCCESS);
    exporting = true;
  }
  if (pauseCopy && exportLocks == 3) {
    copyPaused = true;
    while (!resumeCopy.load()) std::this_thread::yield();
  }
}
static CanDiag::Snapshot out;
static bool snapshot() {
  exporting = true;
  exportLocks = 0;
  const bool ok = canDiagSnapshot(out);
  exporting = false;
  assert(lockDepth == 0 && out.consistent == ok);
  return ok;
}
static void coherent(const CanDiag::Snapshot& s) {
  assert(s.consistent);
#ifdef CAN_DIAG_CAPTURE_INTERVAL
  assert(s.captureBeginUs <= s.capturedUs);
#endif
  for (unsigned bus = 0; bus < 3; ++bus) {
    const auto& b = s.buses[bus];
    assert(b.count <= 32 && b.observed >= b.count);
#ifdef CAN_DIAG_CAPTURE_INTERVAL
    assert(b.copiedAtUs >= s.captureBeginUs && b.copiedAtUs <= s.capturedUs);
    if (b.latestTx.valid) assert(b.latestTx.observedUs <= b.copiedAtUs);
    if (b.rxSeen) assert(b.lastRxUs <= b.copiedAtUs);
    if (b.serviceSeen) assert(b.lastServiceUs <= b.copiedAtUs);
#endif
    for (unsigned i = 0; i < b.count; ++i) {
      const auto& e = b.events[i];
      assert(e.bus == bus && e.statusObservedUs <= e.observedUs);
      assert(e.observedUs <= s.capturedUs);
      if (i) {
        assert(e.seq > b.events[i-1].seq);
        assert(e.observedUs >= b.events[i-1].observedUs);
      }
    }
  }
}
int main(int argc, char** argv) {
  using namespace CanDiag;
  if (argc > 1 && std::strcmp(argv[1], "copy-race") == 0) {
    canDiagInit(44);
    Status st = {}; st.state = STATE_RUNNING;
    for (unsigned i = 0; i < 40; ++i) { st.busErrors = i; canDiagObserveStatus(0, st, 0); }
    pauseCopy = true;
    bool success = false;
    std::thread reader([&] { success = snapshot(); });
    while (!copyPaused.load()) std::this_thread::yield();
    canDiagInit(55);
    canDiagObserveAlerts(2, TWAI_ALERT_BUS_ERROR);
    resumeCopy = true;
    reader.join();
    assert(success && out.bootId == 55 && out.buses[0].count == 0);
    assert(!out.buses[0].hasFirstError && out.buses[2].count == 1);
    coherent(out);
    return 0;
  }
  if (argc > 1 && std::strcmp(argv[1], "concurrent") == 0) {
    canDiagInit(66);
    std::atomic<bool> finished(false);
    std::thread writer([&] {
      Status st = {}; st.state = STATE_RUNNING;
      for (unsigned i = 0; i < 5000; ++i) {
        st.busErrors = i;
        const uint8_t bus = i % 3;
        canDiagObserveRx(bus);
        canDiagObserveService(bus);
        canDiagObserveTx(bus, 0x100 + bus, 0, nullptr, 0, 1, true);
        canDiagObserveStatus(bus, st, 0);
      }
      finished = true;
    });
    unsigned successes = 0, failures = 0;
    do {
      if (snapshot()) { coherent(out); ++successes; }
      else ++failures;
    } while (!finished.load());
    writer.join();
    assert(snapshot()); coherent(out);
    assert(out.buses[0].count == 32 && out.buses[1].count == 32 && out.buses[2].count == 32);
    assert(out.buses[0].hasFirstError && out.buses[0].firstError.seq < out.buses[0].events[0].seq);
    (void)successes; (void)failures;
    return 0;
  }
  if (argc > 1 && std::strcmp(argv[1], "busy-context") == 0) {
#ifdef CAN_DIAG_CAPTURE_INTERVAL
    canDiagInit(67);
    Status initial = {}; initial.state = STATE_RUNNING;
    for (unsigned bus = 0; bus < 3; ++bus) canDiagObserveStatus(bus, initial, 0);
    std::atomic<bool> finished(false), started(false);
    std::thread writer([&] {
      const uint8_t bytes[8] = {1,2,3,4,5,6,7,8};
      do {
        for (uint8_t bus = 0; bus < 3; ++bus) {
          canDiagObserveRx(bus);
          canDiagObserveService(bus);
          const uint32_t token = canDiagTxBegin(bus, 0x120 + bus, 8, bytes, 1);
          canDiagTxEnd(bus, token, 0);
        }
        started = true;
      } while (!finished.load());
    });
    while (!started.load()) std::this_thread::yield();
    for (unsigned i = 0; i < 250; ++i) { assert(snapshot()); coherent(out); }
    finished = true;
    writer.join();
    assert(snapshot()); coherent(out);
#else
    assert(false && "hot context observations must not starve bounded snapshot export");
#endif
    return 0;
  }
  Status st = {}; st.state = STATE_RUNNING;
  canDiagObserveStatus(0, st, 1);
  canDiagObserveAlerts(0, TWAI_ALERT_BUS_ERROR);
  canDiagObserveRx(0); canDiagObserveService(0); canDiagControllerEpoch(0);
  canDiagObserveTx(0, 123, 8, nullptr, -1, 2, true);
  { CanDiagFlashScope scope(3); }
  assert(!snapshot());
  canDiagInit(77);
  assert(snapshot() && out.bootId == 77 && !out.buses[0].hasStatus);
  const unsigned initialAllocations = allocations.load();
  uint8_t bytes[8] = {1,2,3,4,5,6,7,8};
  canDiagObserveTx(0, 0x3fd, 8, bytes, -7, 9, true);
  canDiagObserveService(0); canDiagObserveRx(0);
  canDiagObserveStatus(0, st, 0);
  st.txFailed = 2; st.tec = 128;
  canDiagObserveStatus(0, st, TWAI_ALERT_ERR_PASS);
  canDiagObserveAlerts(1, TWAI_ALERT_ARB_LOST | TWAI_ALERT_TX_SUCCESS);
  canDiagObserveAlerts(2, TWAI_ALERT_BUS_OFF);
  assert(snapshot()); coherent(out);
  assert(out.buses[0].firstError.status.tec == 128);
  assert(out.buses[0].firstError.tx.result == -7 && out.buses[0].firstError.tx.called);
  assert(out.buses[0].firstError.delta.txFailed == 2);
  assert(!out.buses[1].hasFirstError && out.buses[2].hasFirstError);
  // Alert arrives before fresh status: retain it, but do not freeze stale BO state.
  assert(!out.buses[2].hasFirstBusOff);
  assert(!out.buses[2].firstError.statusValid && out.buses[2].firstError.statusObservedUs == 0);
  st.state = STATE_BUS_OFF; st.tec = 256;
  canDiagObserveStatus(2, st, 0);
  assert(snapshot() && out.buses[2].hasFirstBusOff);
  assert(out.buses[2].firstBusOff.status.tec == 256);
  assert(out.buses[2].firstBusOff.statusObservedUs == out.buses[2].firstBusOff.observedUs);
  const uint32_t firstSeq = out.buses[0].firstError.seq;
  {
    CanDiagFlashScope first(1);
    { CanDiagFlashScope second(2);
      assert(snapshot() && out.flashCurrent.activeCount == 2);
      assert(out.flashCurrent.flags & FLASH_OVERLAPPED);
      canDiagObserveAlerts(0, TWAI_ALERT_BUS_ERROR);
    }
    assert(snapshot() && out.flashCurrent.activeCount == 1);
  }
  assert(snapshot() && !out.flashCurrent.activeCount && (out.flashLast.flags & FLASH_VALID));
  assert(out.flashLast.flags & FLASH_OVERLAPPED);
  assert(out.buses[0].latestError.flashCurrent.activeCount == 2);
  const uint64_t lastStatusTime = out.buses[0].latestStatusUs;
  nowUs = 1000000;
  canDiagObserveAlerts(0, TWAI_ALERT_TX_FAILED);
  assert(snapshot() && out.buses[0].latestError.statusObservedUs == lastStatusTime);
  assert(out.buses[0].latestError.observedUs >= 1000000);
  // Force every export lock boundary to observe a concurrent writer. Export is
  // bounded, reports inconsistency and preserves all first/latest evidence.
  forceChange = true;
  assert(!snapshot() && exportLocks <= 12);
  forceChange = false;
  assert(snapshot() && out.buses[0].firstError.seq == firstSeq);
  assert(allocations.load() == initialAllocations);
  canDiagControllerEpoch(0);
  st.state = STATE_RUNNING; st.txFailed = 900;
  canDiagObserveStatus(0, st, 0);
  assert(snapshot() && out.buses[0].events[out.buses[0].count - 1].delta.txFailed == 0);
  canDiagObserveStatus(3, st, 0); canDiagObserveAlerts(255, 1);
  canDiagObserveRx(3); canDiagObserveService(255);
  canDiagObserveRecovery(3, true, true); canDiagControllerEpoch(3);
  canDiagObserveTx(3, 1, 255, bytes, 0, 0, true);
  assert(snapshot() && out.buses[0].firstError.seq == firstSeq);
  for (uint32_t request = 1; request <= 6; ++request) {
    canDiagObserveReinit(request, 3, 9, 1);
    canDiagControllerEpoch(1);
    canDiagObserveReinit(request, 3, 9, request == 6 ? 3 : 2);
  }
  assert(snapshot()&&out.reinitCount==8&&out.reinitObserved==12&&out.reinitOverwritten==4);
  for(uint32_t i=0;i<out.reinitCount;++i) {
    assert(out.reinitEvents[i].seq==i+5);
    assert(out.reinitEvents[i].requestId==3+i/2);
    assert(out.reinitEvents[i].observedUs<=out.capturedUs);
  }
  forceChange=true;assert(!snapshot());forceChange=false;assert(snapshot());
  assert(out.reinitEvents[7].phase==3);
  canDiagInit(88);assert(snapshot()&&out.reinitCount==0&&out.reinitObserved==0);
  assert(sizeof(Journal) + sizeof(Snapshot) + sizeof(portMUX_TYPE) <= 51200);
  return 0;
}
'''


class CanErrorJournalRuntimeHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        (work / "driver").mkdir()
        (work / "Arduino.h").write_text(ARDUINO)
        (work / "driver/twai.h").write_text(TWAI)
        (work / "esp_timer.h").write_text("#pragma once\n#include <cstdint>\nint64_t esp_timer_get_time();\n")
        (work / "main.cpp").write_text(SOURCE)
        cls.binary = work / "test_can_error_journal_runtime"
        command = shlex.split(os.environ.get("CXX", "/usr/bin/g++"))
        command += ["-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread", "-I", str(work), "-I", str(ROOT), str(work / "main.cpp"), "-o", str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError("Journal host compile failed:\n" + result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_bounded_runtime_preserves_evidence_and_reports_export_contention(self):
        subprocess.run([str(self.binary)], check=True, timeout=10)

    def test_init_during_export_cannot_mix_boot_evidence(self):
        subprocess.run([str(self.binary), "copy-race"], check=True, timeout=10)

    def test_continuous_hot_context_updates_do_not_starve_snapshot_export(self):
        subprocess.run([str(self.binary), "busy-context"], check=True, timeout=20)

    def test_concurrent_hooks_produce_only_coherent_successful_snapshots(self):
        subprocess.run([str(self.binary), "concurrent"], check=True, timeout=20)


if __name__ == "__main__":
    unittest.main()
