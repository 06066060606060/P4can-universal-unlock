#pragma once
#include "p4_twai_diag.h"

// Only the existing web task calls this adapter. ISR capture is unchanged;
// its coherent snapshot is allocated in PSRAM before starting a session.
namespace p4_r79_driver {
struct State {
  uint32_t session, bootId, lastSeq, lost, failures, imported;
  uint64_t lastPollUs;
  bool saturated, pending, finished, allocationFailed;
};
static State state = {};
static P4TwaiErrorSnapshot *buffer = nullptr;
static uint32_t baseline = 0, bootId = 0;
static inline void add(uint32_t &value, uint32_t count = 1) {
  value = count > UINT32_MAX - value ? UINT32_MAX : value + count;
}
}

static bool p4R79TimingDriverPrepare() {
  using namespace p4_r79_driver;
  if (!buffer) buffer = static_cast<P4TwaiErrorSnapshot *>(heap_caps_malloc(
      sizeof(P4TwaiErrorSnapshot), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  state.allocationFailed = buffer == nullptr;
  if (!buffer || !p4TwaiDiagSnapshot(buffer)) return false;
  baseline = buffer->buses[1].observed;
  bootId = buffer->bootId;
  return true;
}

static void p4R79TimingDriverStarted() {
  using namespace p4_r79_driver;
  state = {};
  state.session = p4R79TimingSnapshot().session;
  state.bootId = bootId;
  state.lastSeq = baseline;
  state.saturated = baseline == UINT32_MAX;
  state.pending = true;
}

static void p4R79TimingDriverPoll(bool force = false) {
  using namespace p4_r79_driver;
  if (!buffer || !state.session || (!force && state.finished)) return;
  const auto session = p4R79TimingSnapshot();
  if (session.session != state.session ||
      p4R79TimingExportBusy() || (!force && state.finished)) return;
  const uint64_t pollUs = (uint64_t)esp_timer_get_time();
  if (!force && pollUs >= state.lastPollUs &&
      pollUs - state.lastPollUs < 100000u) return;
  state.lastPollUs = pollUs;
  if (!p4TwaiDiagSnapshot(buffer) || buffer->bootId != state.bootId) {
    add(state.failures); state.pending = true; return;
  }
  const uint64_t importedUs = (uint64_t)esp_timer_get_time();
  const auto &bus = buffer->buses[1];
  state.saturated = state.saturated || bus.observed == UINT32_MAX;
  const auto appendError = [&](const P4TwaiErrorEvent &raw) {
    if (raw.seq <= state.lastSeq) return;
    const uint32_t gap = raw.seq - state.lastSeq - 1u;
    // Source sequence gaps are an upper bound: boundary records lost before
    // import cannot be assigned an exact session time after ring overwrite.
    if (gap) add(state.lost, gap);
    p4_r79_timing::Event event = {};
    event.timeUs = raw.observedUs; event.importedUs = importedUs;
    event.bus = 1; event.errorSeq = raw.seq;
    event.ecc = raw.ecc; event.tec = raw.tec; event.rec = raw.rec;
    event.status = raw.status; event.kind = p4_r79_timing::CAN_ERROR;
    using namespace p4_r79_timing_runtime;
    portENTER_CRITICAL(&mux);
    if (!exporting && recorder.snapshot().session == state.session) {
      if (gap) {
        auto missing = event;
        missing.kind = p4_r79_timing::CAN_ERROR_GAP;
        missing.ecc = gap; missing.errorSeq = state.lastSeq + 1u;
        recorder.appendExternal(missing, state.session);
      }
      if (recorder.appendExternal(event, state.session)) add(state.imported);
    }
    portEXIT_CRITICAL(&mux);
    state.lastSeq = raw.seq;
  };
  if (bus.hasFirst) appendError(bus.first);
  for (uint32_t index = 0; index < bus.count && index < P4_TWAI_DIAG_CAPACITY; ++index)
    appendError(bus.events[index]);
  state.pending = false;
  (void)p4R79TimingSnapshot();
  // If this poll crossed expiry, a subsequent post-expiry snapshot must still
  // collect errors that arrived after this snapshot's per-bus copy.
  state.finished = !session.active;
}
