#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "../r79_timing_capture_pure.h"

using namespace p4_r79_timing;
static const uint64_t durationUs = UINT64_C(600000000);

static Event eventAt(uint64_t now, Kind kind = RX) {
  Event event = {};
  event.timeUs = now;
  event.kind = kind;
  event.dlc = 8;
  for (uint8_t i = 0; i < 8; ++i) event.data[i] = uint8_t(i * 17 + 1);
  return event;
}

static void testInitialAndStart() {
  Event storage[3] = {};
  Recorder recorder(storage, 3);
  Snapshot initial = recorder.snapshot();
  assert(initial.session == 0 && initial.count == 0 && initial.capacity == 3);
  assert(!initial.active && !initial.expired && initial.startUs == 0 && initial.stopUs == 0);
  assert(initial.dropped == 0 && initial.ignoredOldSession == 0);
  assert(recorder.start(123));
  Snapshot started = recorder.snapshot();
  assert(started.session != 0 && started.active && !started.expired);
  assert(started.startUs == 123 && started.stopUs == 0 && started.count == 0);
}

static void testCopiesAllStagesAndValues() {
  Event storage[5] = {};
  Recorder recorder(storage, 5);
  assert(recorder.start(100));
  const uint32_t session = recorder.snapshot().session;
  const Kind kinds[] = {RX, TX_CALL, TX_ACCEPTED, TX_REJECTED, GATE_REJECTED};
  for (uint32_t i = 0; i < 5; ++i) {
    Event event = eventAt(101 + i, kinds[i]);
    event.callUs = UINT64_C(0x100000010) + i;
    event.sequence = 999;
    event.callId = 81 + i;
    event.waitTicks = 37 + i;
    event.result = -int32_t(101 + i);
    event.bus = uint8_t(i % 3);
    event.mux = uint8_t(i % 3);
    Event expected = event;
    assert(recorder.append(event, session));
    event.data[0] = 0;
    event.callId = 0;
    Event actual = {};
    assert(recorder.read(i, actual));
    assert(actual.sequence == i + 1);
    assert(actual.timeUs == expected.timeUs && actual.callUs == expected.callUs);
    assert(actual.callId == expected.callId && actual.waitTicks == expected.waitTicks);
    assert(actual.result == expected.result && actual.kind == expected.kind);
    assert(actual.bus == expected.bus && actual.mux == expected.mux && actual.dlc == expected.dlc);
    assert(std::memcmp(actual.data, expected.data, sizeof(actual.data)) == 0);
    actual.data[0] = 0;
    Event reread = {};
    assert(recorder.read(i, reread) && reread.data[0] == expected.data[0]);
  }
  assert(recorder.snapshot().count == 5);
}

static void testRetainsFirstRowsWhenFull() {
  Event storage[2] = {};
  Recorder recorder(storage, 2);
  assert(recorder.start(100));
  const uint32_t session = recorder.snapshot().session;
  assert(recorder.append(eventAt(101), session));
  assert(recorder.append(eventAt(102), session));
  assert(!recorder.append(eventAt(103), session));
  assert(!recorder.append(eventAt(104), session));
  Snapshot full = recorder.snapshot();
  assert(full.count == 2 && full.capacity == 2 && full.dropped == 2 && full.active);
  Event event = {};
  assert(recorder.read(0, event) && event.timeUs == 101 && event.sequence == 1);
  assert(recorder.read(1, event) && event.timeUs == 102 && event.sequence == 2);
  event.callId = 123;
  assert(!recorder.read(2, event) && event.callId == 123);
  assert(!recorder.read(UINT32_MAX, event));
}

static void testAppendExpiryBoundary() {
  Event storage[3] = {};
  Recorder recorder(storage, 3);
  const uint64_t start = 1000;
  assert(recorder.start(start));
  const uint32_t session = recorder.snapshot().session;
  assert(recorder.append(eventAt(start + durationUs - 1), session));
  assert(!recorder.append(eventAt(start + durationUs), session));
  Snapshot ended = recorder.snapshot();
  assert(!ended.active && ended.expired && ended.count == 1 && ended.dropped == 0);
  assert(ended.stopUs == start + durationUs);
  assert(!recorder.append(eventAt(start + durationUs + 1), session));
  recorder.stop(start + durationUs + 10);
  assert(recorder.snapshot().stopUs == ended.stopUs);
}

static void testTickExpiryAndLargeTimes() {
  Event storage[2] = {};
  Recorder recorder(storage, 2);
  const uint64_t start = UINT64_C(0xfffffff0);
  assert(recorder.start(start));
  const uint32_t session = recorder.snapshot().session;
  recorder.tick(start + durationUs - 1);
  assert(recorder.snapshot().active);
  assert(recorder.append(eventAt(start + 32), session));
  Event event = {};
  assert(recorder.read(0, event) && event.timeUs == UINT64_C(0x100000010));
  recorder.tick(start + durationUs + 1234);
  Snapshot ended = recorder.snapshot();
  assert(ended.expired && !ended.active && ended.stopUs == start + durationUs);
  assert(ended.startUs == start && ended.count == 1);
  recorder.tick(start + durationUs + 9999);
  assert(recorder.snapshot().stopUs == ended.stopUs);
}

static void testStopAndRestartFence() {
  Event storage[3] = {};
  Recorder recorder(storage, 3);
  assert(recorder.start(100));
  const uint32_t oldSession = recorder.snapshot().session;
  assert(recorder.append(eventAt(101), oldSession));
  recorder.stop(200);
  Snapshot stopped = recorder.snapshot();
  assert(!stopped.active && !stopped.expired && stopped.stopUs == 200 && stopped.count == 1);
  assert(!recorder.append(eventAt(201, TX_ACCEPTED), oldSession));
  assert(recorder.snapshot().dropped == 0 && recorder.snapshot().ignoredOldSession == 0);
  recorder.stop(250);
  assert(recorder.snapshot().stopUs == 200);
  assert(recorder.start(300));
  const uint32_t newSession = recorder.snapshot().session;
  assert(newSession != 0 && newSession != oldSession);
  assert(!recorder.read(0, storage[2]));
  // A late old call cannot expire the new session using its own timestamp.
  assert(!recorder.append(eventAt(300 + durationUs, TX_ACCEPTED), oldSession));
  Snapshot fenced = recorder.snapshot();
  assert(fenced.active && !fenced.expired && fenced.count == 0);
  assert(fenced.ignoredOldSession == 1 && fenced.dropped == 0);
  assert(recorder.append(eventAt(302), newSession));
  Event event = {};
  assert(recorder.read(0, event) && event.sequence == 1 && event.timeUs == 302);
  // Starting a new session resets evidence counters and invalidates an active session too.
  assert(recorder.start(400));
  Snapshot restarted = recorder.snapshot();
  assert(restarted.session != newSession && restarted.count == 0 && restarted.startUs == 400);
  assert(restarted.ignoredOldSession == 0 && restarted.dropped == 0 && restarted.stopUs == 0);
  assert(!recorder.append(eventAt(401), newSession));
}

static void testRestartResetsOverflowAndExpiry() {
  Event storage[1] = {};
  Recorder recorder(storage, 1);
  assert(recorder.start(0));
  const uint32_t oldSession = recorder.snapshot().session;
  assert(recorder.append(eventAt(1), oldSession));
  assert(!recorder.append(eventAt(2), oldSession));
  assert(!recorder.append(eventAt(3), oldSession + 1));
  recorder.stop(durationUs);
  Snapshot expired = recorder.snapshot();
  assert(expired.expired && !expired.active && expired.stopUs == durationUs);
  assert(expired.dropped == 1 && expired.ignoredOldSession == 1);
  assert(recorder.start(durationUs + 1));
  Snapshot restarted = recorder.snapshot();
  assert(restarted.active && !restarted.expired && restarted.count == 0);
  assert(restarted.dropped == 0 && restarted.ignoredOldSession == 0 && restarted.stopUs == 0);
  assert(restarted.session != 0 && restarted.session != oldSession);
}

static void testMissingStorage() {
  Event storage[1] = {};
  Recorder missing(nullptr, 4);
  Recorder empty(storage, 0);
  Recorder neither(nullptr, 0);
  Recorder* recorders[] = {&missing, &empty, &neither};
  for (Recorder* recorder : recorders) {
    assert(!recorder->start(10));
    Snapshot state = recorder->snapshot();
    assert(!state.active && state.session == 0 && state.count == 0);
    assert(!recorder->append(eventAt(11), 0));
    Event out = {};
    assert(!recorder->read(0, out));
    recorder->stop(12);
    recorder->tick(13);
    assert(!recorder->snapshot().active);
  }
}

static void testLateExternalAndReason() {
  Event storage[4] = {};
  Recorder r(storage, 4); assert(r.start(100));
  const uint32_t session=r.snapshot().session;
  auto external=eventAt(150,CAN_ERROR);external.errorSeq=9;external.ecc=170;
  r.stop(200);
  assert(!r.append(external,session));
  assert(r.appendExternal(external,session));
  auto future=external;future.timeUs=201;assert(!r.appendExternal(future,session));
  auto before=external;before.timeUs=99;assert(!r.appendExternal(before,session));
  auto ordinary=eventAt(150,TX_CALL);assert(!r.appendExternal(ordinary,session));
  auto gap=eventAt(160,CAN_ERROR_GAP);assert(r.appendExternal(gap,session));
  Event read{};assert(r.read(0,read)&&read.errorSeq==9&&read.ecc==170);
  assert(r.start(300));assert(!r.appendExternal(external,session));
  assert(r.snapshot().ignoredOldSession==1&&r.snapshot().count==0);
  r.tick(300+durationUs);external.timeUs=300+durationUs-1;
  assert(r.appendExternal(external,r.snapshot().session));
  external.timeUs++;assert(!r.appendExternal(external,r.snapshot().session));
  uint8_t reason=NONE;assert(!check(false,BARRIER_BUSY,reason)&&reason==BARRIER_BUSY);
  assert(check(true,MANUAL_D,reason)&&reason==BARRIER_BUSY);
  assert(strcmp(reasonName(ALL_CONTROLLERS_NOT_READY),"ALL_CONTROLLERS_NOT_READY")==0);
}

int main() {
  testLateExternalAndReason();
  testInitialAndStart();
  testCopiesAllStagesAndValues();
  testRetainsFirstRowsWhenFull();
  testAppendExpiryBoundary();
  testTickExpiryAndLargeTimes();
  testStopAndRestartFence();
  testRestartResetsOverflowAndExpiry();
  testMissingStorage();
  std::puts("8 R79 timing journal cases passed");
}
