"""Run the actual capture adapter with clock, PSRAM and short-lock doubles."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKES = ROOT / "tests/r79_timing_fakes"
SOURCE = r'''
#include <atomic>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <thread>
#include "r79_timing_capture.h"
thread_local unsigned timingLockDepth = 0;
static thread_local bool pauseNextLock = false;
static std::atomic<bool> hookPaused(false), releaseHook(false);
void timingBeforeLock() {
  if (!pauseNextLock) return;
  pauseNextLock = false;
  hookPaused = true;
  while (!releaseHook.load()) std::this_thread::yield();
}
static std::atomic<int64_t> nowUs(100);
static unsigned allocations = 0;
static bool failAllocation = true;
static std::atomic<bool> pauseAllocation(false), allocationEntered(false), releaseAllocation(false);
int64_t esp_timer_get_time() { return nowUs.load(); }
void* heap_caps_malloc(size_t bytes, uint32_t caps) {
  assert(timingLockDepth == 0);
  assert(caps == (MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  assert(bytes == 32768 * sizeof(p4_r79_timing::Event));
  ++allocations;
  if (pauseAllocation.load()) {
    allocationEntered = true;
    while (!releaseAllocation.load()) std::this_thread::yield();
  }
  return failAllocation ? nullptr : std::malloc(bytes);
}
static twai_message_t frame(uint8_t mux = 1) {
  twai_message_t message = {};
  message.identifier = 0x3fd;
  message.data_length_code = 8;
  for (unsigned i = 0; i < 8; ++i) message.data[i] = uint8_t(0x80 + i);
  message.data[0] = uint8_t(0xa0 | mux);
  return message;
}
static p4_r79_timing::Event row(uint32_t index) {
  p4_r79_timing::Event event = {};
  assert(p4R79TimingRead(index, event));
  assert(timingLockDepth == 0);
  return event;
}
int main(int argc, char** argv) {
  using namespace p4_r79_timing;
  if (argc > 1 && std::strcmp(argv[1], "session-entry-race") == 0) {
    failAllocation = false;
    assert(p4R79TimingStart());
    twai_message_t message = frame();
    // Freeze software time: rejecting an earlier timestamp cannot hide a race.
    for (unsigned kind = 0; kind < 3; ++kind) {
      hookPaused = false;
      releaseHook = false;
      P4R79TimingToken token = {};
      std::thread producer([&] {
        pauseNextLock = true;
        if (kind == 0) p4R79TimingRx(0, message);
        if (kind == 1) p4R79TimingGateRejected(0, &message, 3, -5);
        if (kind == 2) token = p4R79TimingTxBegin(0, &message, 3);
      });
      while (!hookPaused.load()) std::this_thread::yield();
      const uint32_t oldSession = p4R79TimingSnapshot().session;
      p4R79TimingStop();
      assert(p4R79TimingStart());
      assert(p4R79TimingSnapshot().session != oldSession);
      releaseHook = true;
      producer.join();
      assert(p4R79TimingSnapshot().count == 0);
      assert(!token.valid);
    }
    return 0;
  }
  if (argc > 1) {
    // Stop while allocation runs must cancel pending Start, without a long lock.
    failAllocation = false;
    pauseAllocation = true;
    bool started = true;
    std::thread starter([&] { started = p4R79TimingStart(); });
    while (!allocationEntered.load()) std::this_thread::yield();
    p4R79TimingStop();
    assert(!p4R79TimingStart());
    releaseAllocation = true;
    starter.join();
    assert(!started && !p4R79TimingSnapshot().active);
    assert(p4R79TimingStart() && allocations == 1);
    return 0;
  }
  twai_message_t message = frame();
  p4R79TimingRx(0, message);
  assert(!p4R79TimingTxBegin(0, &message, 7).valid && allocations == 0);
  assert(!p4R79TimingStart());
  assert(p4R79TimingAllocationFailed() && !p4R79TimingSnapshot().active);
  failAllocation = false;
  assert(p4R79TimingStart());
  assert(!p4R79TimingAllocationFailed() && allocations == 2);
  Snapshot initial = p4R79TimingSnapshot();
  assert(initial.active && initial.capacity == 32768 && initial.session != 0);
  assert(!p4R79TimingStart() && p4R79TimingSnapshot().session == initial.session);
  Snapshot exporting = {};
  assert(!p4R79TimingBeginExport(exporting));
  for (uint8_t bus = 0; bus < 3; ++bus) {
    nowUs = 101 + bus;
    twai_message_t rx = frame(bus);
    p4R79TimingRx(bus, rx);
    Event event = row(bus);
    assert(event.kind == RX && event.bus == bus && event.mux == bus && event.dlc == 8);
    assert(event.timeUs == uint64_t(101 + bus) && std::memcmp(event.data, rx.data, 8) == 0);
  }
  const uint32_t beforeInvalid = p4R79TimingSnapshot().count;
  for (unsigned variant = 0; variant < 7; ++variant) {
    twai_message_t invalid = message;
    if (variant == 0) invalid.extd = true;
    if (variant == 1) invalid.rtr = true;
    if (variant == 2) invalid.identifier = 0x3fc;
    if (variant == 3) invalid.data_length_code = 7;
    if (variant == 4) invalid.data_length_code = 9;
    if (variant == 5) invalid.data[0] = 3;
    const uint8_t bus = variant == 6 ? 3 : 0;
    p4R79TimingRx(bus, invalid);
    assert(!p4R79TimingTxBegin(bus, &invalid, 9).valid);
    p4R79TimingGateRejected(bus, &invalid, 9, -3);
  }
  assert(!p4R79TimingTxBegin(0, nullptr, 0).valid);
  p4R79TimingGateRejected(0, nullptr, 0, -3);
  assert(p4R79TimingSnapshot().count == beforeInvalid && allocations == 2);
  for (unsigned variant = 0; variant < 3; ++variant) {
    nowUs = 200 + variant * 10;
    const uint32_t first = p4R79TimingSnapshot().count;
    P4R79TimingToken token = p4R79TimingTxBegin(2, &message, 55 + variant);
    assert(token.valid && token.session == initial.session);
    Event call = row(first);
    assert(call.kind == TX_CALL && call.callId != 0 && call.callUs == uint64_t(nowUs.load()));
    assert(call.waitTicks == 55 + variant && call.bus == 2);
    twai_message_t actual = message;
    actual.data[7] = uint8_t(variant);
    nowUs = 205 + variant * 10;
    p4R79TimingTxEnd(token, &actual, variant == 0 ? 0 : -23, variant != 2);
    Event result = row(first + 1);
    assert(result.kind == (variant == 0 ? TX_ACCEPTED : variant == 1 ? TX_REJECTED : GATE_REJECTED));
    assert(result.result == (variant == 0 ? 0 : -23));
    assert(result.callId == call.callId && result.callUs == call.callUs);
    assert(result.waitTicks == call.waitTicks && result.data[7] == variant);
    assert(result.timeUs == uint64_t(nowUs.load()));
  }
  uint32_t gateIndex = p4R79TimingSnapshot().count;
  p4R79TimingGateRejected(1, &message, 92, -5);
  assert(row(gateIndex).kind == GATE_REJECTED && row(gateIndex).callId == 0);
  assert(row(gateIndex).waitTicks == 92 && row(gateIndex).result == -5);
  P4R79TimingToken old = p4R79TimingTxBegin(0, &message, 0);
  p4R79TimingStop();
  uint32_t stoppedCount = p4R79TimingSnapshot().count;
  p4R79TimingTxEnd(old, &message, 0, true);
  assert(p4R79TimingSnapshot().count == stoppedCount);
  assert(p4R79TimingBeginExport(exporting) && p4R79TimingExportBusy());
  assert(!exporting.active && exporting.count == stoppedCount);
  assert(!p4R79TimingBeginExport(exporting) && !p4R79TimingStart());
  Event first = row(0);
  p4R79TimingRx(0, message);
  p4R79TimingTxEnd(old, &message, -3, true);
  assert(p4R79TimingSnapshot().count == stoppedCount && row(0).timeUs == first.timeUs);
  p4R79TimingEndExport();
  assert(!p4R79TimingExportBusy());
  nowUs = UINT64_C(0xfffffff0);
  assert(p4R79TimingStart() && allocations == 2);
  const uint32_t freshSession = p4R79TimingSnapshot().session;
  assert(freshSession != old.session);
  p4R79TimingTxEnd(old, &message, 0, true);
  assert(p4R79TimingSnapshot().ignoredOldSession == 1 && p4R79TimingSnapshot().count == 0);
  nowUs = UINT64_C(0x100000010);
  P4R79TimingToken fresh = p4R79TimingTxBegin(0, &message, 1);
  assert(row(0).timeUs == UINT64_C(0x100000010) && fresh.event.callId == 1);
  for (uint32_t i = 1; i < 32768; ++i) p4R79TimingRx(0, message);
  p4R79TimingRx(0, message);
  P4R79TimingToken full = p4R79TimingTxBegin(0, &message, 1);
  assert(full.valid);
  p4R79TimingTxEnd(full, &message, -1, true);
  Snapshot overflow = p4R79TimingSnapshot();
  assert(overflow.count == 32768 && overflow.dropped == 3 && row(0).kind == TX_CALL);
  nowUs = UINT64_C(0xfffffff0) + 600000000;
  Snapshot expired = p4R79TimingSnapshot();
  assert(!expired.active && expired.expired && expired.stopUs == uint64_t(nowUs.load()));
  assert(!p4R79TimingTxBegin(0, &message, 1).valid);
  assert(allocations == 2);
  assert(std::strcmp(p4R79TimingStageName(RX), "RX") == 0);
  assert(std::strcmp(p4R79TimingStageName(TX_CALL), "TX_CALL") == 0);
  assert(std::strcmp(p4R79TimingStageName(TX_ACCEPTED), "TX_ACCEPTED") == 0);
  assert(std::strcmp(p4R79TimingStageName(TX_REJECTED), "TX_REJECTED") == 0);
  assert(std::strcmp(p4R79TimingStageName(GATE_REJECTED), "GATE_REJECTED") == 0);
}
'''


class R79TimingRuntimeHost(unittest.TestCase):
    def test_actual_adapter_lifecycle_and_capture(self):
        with tempfile.TemporaryDirectory(prefix="p4-r79-timing-") as temporary:
            source = Path(temporary) / "runtime.cpp"
            binary = Path(temporary) / "runtime"
            source.write_text(SOURCE)
            command = shlex.split(os.environ.get("CXX", "c++")) + [
                "-std=c++11", "-pthread", "-Wall", "-Wextra", "-Werror", "-I", str(FAKES),
                "-I", str(ROOT), str(source), "-o", str(binary)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, "INVALID-RED compilation:\n" + compiled.stdout + compiled.stderr)
            for arguments in ([], ["allocation-stop-race"], ["session-entry-race"]):
                result = subprocess.run([str(binary)] + arguments, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
