#pragma once
#include <Arduino.h>
#include <driver/twai.h>
#include <esp_timer.h>
#include <esp_heap_caps.h>
#include <atomic>
#include <string.h>
#include "r79_timing_capture_pure.h"
struct P4R79TimingToken { uint32_t session; p4_r79_timing::Event event; bool valid; };

namespace p4_r79_timing_runtime {
static const uint32_t capacity = 32768;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static p4_r79_timing::Event* storage = nullptr;
static p4_r79_timing::Recorder recorder(nullptr, capacity);
static std::atomic<uint32_t> activeSession(0);
static bool exporting = false, starting = false, cancelStart = false, allocationFailed = false;
static uint32_t callId = 0;
struct RxReference { uint64_t us; uint32_t sequence; };
static RxReference lastRx[3][3] = {};
static inline void referenceLocked(p4_r79_timing::Event &event) {
  const auto &rx = lastRx[event.bus][event.mux];
  if (rx.us <= event.timeUs) { event.rxUs = rx.us; event.rxSequence = rx.sequence; }
}

static inline uint64_t now() { return static_cast<uint64_t>(esp_timer_get_time()); }
static inline void syncActive() {
  const p4_r79_timing::Snapshot state = recorder.snapshot();
  activeSession.store(state.active ? state.session : 0, std::memory_order_relaxed);
}
static inline bool relevant(uint8_t bus, const twai_message_t* message) {
  return bus < 3 && message && !message->extd && !message->rtr &&
         message->identifier == 0x3FDu && message->data_length_code == 8 &&
         (message->data[0] & 0x07u) <= 2;
}
static inline void payload(p4_r79_timing::Event& event, const twai_message_t& message) {
  event.mux = message.data[0] & 0x07u;
  event.dlc = message.data_length_code;
  memcpy(event.data, message.data, sizeof(event.data));
}
}  // namespace p4_r79_timing_runtime

static inline bool p4R79TimingStart() {
  using namespace p4_r79_timing_runtime;
  const uint64_t timestamp = now();
  portENTER_CRITICAL(&mux);
  recorder.tick(timestamp);
  syncActive();
  if (exporting || starting || recorder.snapshot().active) {
    portEXIT_CRITICAL(&mux);
    return false;
  }
  starting = true;
  cancelStart = false;
  p4_r79_timing::Event* buffer = storage;
  portEXIT_CRITICAL(&mux);

  // The web task owns allocation; hooks never allocate or wait for allocation.
  if (!buffer) buffer = static_cast<p4_r79_timing::Event*>(heap_caps_malloc(
      sizeof(p4_r79_timing::Event) * capacity, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));

  portENTER_CRITICAL(&mux);
  allocationFailed = buffer == nullptr;
  if (buffer && !storage) {
    storage = buffer;
    recorder = p4_r79_timing::Recorder(storage, capacity);
  }
  const bool success = buffer && !cancelStart && recorder.start(now());
  if (success) { callId = 0; memset(lastRx, 0, sizeof(lastRx)); }
  starting = false;
  syncActive();
  portEXIT_CRITICAL(&mux);
  return success;
}

static inline void p4R79TimingStop() {
  using namespace p4_r79_timing_runtime;
  const uint64_t timestamp = now();
  portENTER_CRITICAL(&mux);
  if (starting) cancelStart = true;
  recorder.stop(timestamp);
  syncActive();
  portEXIT_CRITICAL(&mux);
}

static inline p4_r79_timing::Snapshot p4R79TimingSnapshot() {
  using namespace p4_r79_timing_runtime;
  const uint64_t timestamp = now();
  portENTER_CRITICAL(&mux);
  recorder.tick(timestamp);
  syncActive();
  p4_r79_timing::Snapshot result = recorder.snapshot();
  portEXIT_CRITICAL(&mux);
  return result;
}

static inline bool p4R79TimingBeginExport(p4_r79_timing::Snapshot& out) {
  using namespace p4_r79_timing_runtime;
  const uint64_t timestamp = now();
  portENTER_CRITICAL(&mux);
  recorder.tick(timestamp);
  syncActive();
  const p4_r79_timing::Snapshot state = recorder.snapshot();
  const bool success = !starting && !exporting && !state.active && state.session != 0;
  if (success) { exporting = true; out = state; }
  portEXIT_CRITICAL(&mux);
  return success;
}

static inline void p4R79TimingEndExport() {
  using namespace p4_r79_timing_runtime;
  portENTER_CRITICAL(&mux);
  exporting = false;
  portEXIT_CRITICAL(&mux);
}

static inline bool p4R79TimingRead(uint32_t index, p4_r79_timing::Event& out) {
  using namespace p4_r79_timing_runtime;
  portENTER_CRITICAL(&mux);
  const bool success = recorder.read(index, out);
  portEXIT_CRITICAL(&mux);
  return success;
}

static inline bool p4R79TimingExportBusy() {
  using namespace p4_r79_timing_runtime;
  portENTER_CRITICAL(&mux);
  const bool result = exporting;
  portEXIT_CRITICAL(&mux);
  return result;
}

static inline bool p4R79TimingAllocationFailed() {
  using namespace p4_r79_timing_runtime;
  portENTER_CRITICAL(&mux);
  const bool result = allocationFailed;
  portEXIT_CRITICAL(&mux);
  return result;
}

static inline void p4R79TimingRx(uint8_t bus, const twai_message_t& message) {
  using namespace p4_r79_timing_runtime;
  const uint32_t expectedSession = activeSession.load(std::memory_order_relaxed);
  if (!expectedSession || !relevant(bus, &message)) return;
  p4_r79_timing::Event event = {};
  event.timeUs = now();
  event.kind = p4_r79_timing::RX;
  event.bus = bus;
  payload(event, message);
  portENTER_CRITICAL(&mux);
  if (!exporting) {
    const bool same = recorder.snapshot().session == expectedSession;
    const uint32_t sequence = recorder.snapshot().count + 1;
    const bool appended = recorder.append(event, expectedSession);
    if (same && appended) lastRx[bus][event.mux] = {event.timeUs, sequence};
  }
  syncActive();
  portEXIT_CRITICAL(&mux);
}

static inline P4R79TimingToken p4R79TimingTxBegin(uint8_t bus, const twai_message_t* message,
                                               uint32_t waitTicks, uint32_t readyMask = 0u) {
  using namespace p4_r79_timing_runtime;
  P4R79TimingToken token = {};
  const uint32_t expectedSession = activeSession.load(std::memory_order_relaxed);
  if (!expectedSession || !relevant(bus, message)) return token;
  token.event.timeUs = now();
  token.event.callUs = token.event.timeUs;
  token.event.kind = p4_r79_timing::TX_CALL;
  token.event.bus = bus;
  token.event.waitTicks = waitTicks;
  token.event.readyMask = readyMask;
  payload(token.event, *message);
  portENTER_CRITICAL(&mux);
  // An old observation cannot expire a replacement session or acquire its ID.
  if (recorder.snapshot().session == expectedSession) recorder.tick(token.event.timeUs);
  const p4_r79_timing::Snapshot state = recorder.snapshot();
  if (!exporting && state.active && state.session == expectedSession) {
    token.valid = true;
    token.session = state.session;
    if (++callId == 0) ++callId;
    token.event.callId = callId;
    referenceLocked(token.event);
    recorder.append(token.event, token.session);
  }
  syncActive();
  portEXIT_CRITICAL(&mux);
  return token;
}

static inline void p4R79TimingTxEnd(P4R79TimingToken token, const twai_message_t* message,
                                   int32_t result, bool driverCalled) {
  using namespace p4_r79_timing_runtime;
  if (!token.valid || !relevant(token.event.bus, message)) return;
  token.event.timeUs = now();
  token.event.kind = !driverCalled ? p4_r79_timing::GATE_REJECTED :
      result == 0 ? p4_r79_timing::TX_ACCEPTED : p4_r79_timing::TX_REJECTED;
  token.event.result = result;
  token.event.reason = !driverCalled ? p4_r79_timing::UNSPECIFIED :
      result == 0 ? p4_r79_timing::NONE : p4_r79_timing::DRIVER_ERROR;
  payload(token.event, *message);
  portENTER_CRITICAL(&mux);
  if (!exporting) recorder.append(token.event, token.session);
  syncActive();
  portEXIT_CRITICAL(&mux);
}

static inline void p4R79TimingGateRejected(uint8_t bus, const twai_message_t* message,
                                          uint32_t waitTicks, int32_t result,
                                          uint8_t reason = p4_r79_timing::UNSPECIFIED,
                                          uint32_t readyMask = 0u) {
  using namespace p4_r79_timing_runtime;
  const uint32_t expectedSession = activeSession.load(std::memory_order_relaxed);
  if (!expectedSession || !relevant(bus, message)) return;
  p4_r79_timing::Event event = {};
  event.timeUs = now();
  event.kind = p4_r79_timing::GATE_REJECTED;
  event.bus = bus;
  event.waitTicks = waitTicks;
  event.result = result;
  event.reason = reason;
  event.readyMask = readyMask;
  payload(event, *message);
  portENTER_CRITICAL(&mux);
  if (!exporting) { referenceLocked(event); recorder.append(event, expectedSession); }
  syncActive();
  portEXIT_CRITICAL(&mux);
}

static inline const char* p4R79TimingStageName(uint8_t kind) {
  switch (kind) {
    case p4_r79_timing::RX: return "RX";
    case p4_r79_timing::TX_CALL: return "TX_CALL";
    case p4_r79_timing::TX_ACCEPTED: return "TX_ACCEPTED";
    case p4_r79_timing::TX_REJECTED: return "TX_REJECTED";
    case p4_r79_timing::GATE_REJECTED: return "GATE_REJECTED";
    case p4_r79_timing::CAN_ERROR: return "CAN_ERROR";
    case p4_r79_timing::CAN_ERROR_GAP: return "CAN_ERROR_GAP";
    default: return "UNKNOWN";
  }
}
