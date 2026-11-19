#ifndef P4_R79_TIMING_CAPTURE_PURE_H
#define P4_R79_TIMING_CAPTURE_PURE_H

#include <stdint.h>

namespace p4_r79_timing {

enum Kind { RX = 1, TX_CALL = 2, TX_ACCEPTED = 3, TX_REJECTED = 4, GATE_REJECTED = 5,
            CAN_ERROR = 6, CAN_ERROR_GAP = 7 };
enum Reason : uint8_t {
  NONE, UNSPECIFIED, BARRIER_BUSY, GENERATION_CHANGED, ADMIN_HOLD,
  TRANSPORT_NOT_READY, CANCELLED, INVALID_PROFILE, REQUIRED_FRESHNESS,
  NON_SUMMON_ADMISSION, ALL_CONTROLLERS_NOT_READY, INVALID_FRAME,
  DRIVER_ERROR, STOCK_TOO_OLD, NO_OVERLAY_CHANGE, MANUAL_D, MANUAL_R,
  AP_BLOCKED, AP_WAITING, AP_UNKNOWN, POLICY_GATE
};
// Observe the same short-circuit conditions once; diagnostics never authorize TX.
static inline bool check(bool allowed, uint8_t why, uint8_t &reason) {
  if (!allowed) reason = why;
  return allowed;
}
static inline const char *reasonName(uint8_t reason) {
  switch (reason) {
    case NONE: return "NONE";
    case BARRIER_BUSY: return "BARRIER_BUSY";
    case GENERATION_CHANGED: return "GENERATION_CHANGED";
    case ADMIN_HOLD: return "ADMIN_HOLD";
    case TRANSPORT_NOT_READY: return "TRANSPORT_NOT_READY";
    case CANCELLED: return "CANCELLED";
    case INVALID_PROFILE: return "INVALID_PROFILE";
    case REQUIRED_FRESHNESS: return "REQUIRED_FRESHNESS";
    case NON_SUMMON_ADMISSION: return "NON_SUMMON_ADMISSION";
    case ALL_CONTROLLERS_NOT_READY: return "ALL_CONTROLLERS_NOT_READY";
    case INVALID_FRAME: return "INVALID_FRAME";
    case DRIVER_ERROR: return "DRIVER_ERROR";
    case STOCK_TOO_OLD: return "STOCK_TOO_OLD";
    case NO_OVERLAY_CHANGE: return "NO_OVERLAY_CHANGE";
    case MANUAL_D: return "MANUAL_D";
    case MANUAL_R: return "MANUAL_R";
    case AP_BLOCKED: return "AP_BLOCKED";
    case AP_WAITING: return "AP_WAITING";
    case AP_UNKNOWN: return "AP_UNKNOWN";
    case POLICY_GATE: return "POLICY_GATE";
    default: return "UNSPECIFIED";
  }
}

struct Event {
  uint64_t timeUs, callUs;
  uint32_t sequence, callId, waitTicks;
  int32_t result;
  uint8_t kind, bus, mux, dlc;
  uint8_t data[8];
  uint64_t rxUs, importedUs;
  uint32_t rxSequence, readyMask, errorSeq, ecc, tec, rec, status;
  uint8_t reason;
};

struct Snapshot {
  uint32_t session, count, capacity, dropped, ignoredOldSession;
  uint64_t startUs, stopUs;
  bool active, expired;
};

// The caller owns storage and externally synchronizes all operations.
class Recorder {
 public:
  Recorder(Event* storage, uint32_t capacity) : storage_(storage), state_{} {
    state_.capacity = capacity;
  }

  bool start(uint64_t now) {
    if (!storage_ || state_.capacity == 0) return false;
    // Session zero denotes a recorder that has never started.
    ++state_.session;
    if (state_.session == 0) ++state_.session;
    state_.count = 0;
    state_.dropped = 0;
    state_.ignoredOldSession = 0;
    state_.startUs = now;
    state_.stopUs = 0;
    state_.active = true;
    state_.expired = false;
    return true;
  }

  void stop(uint64_t now) {
    tick(now);
    if (!state_.active) return;
    state_.active = false;
    state_.stopUs = now;
  }

  void tick(uint64_t now) {
    if (!state_.active || now < state_.startUs) return;
    if (now - state_.startUs < durationUs()) return;
    state_.active = false;
    state_.expired = true;
    state_.stopUs = state_.startUs + durationUs();
  }

  bool append(Event event, uint32_t expectedSession) {
    // Check the token before time: an old in-flight return must not expire or
    // otherwise change the current session.
    if (expectedSession != state_.session) {
      incrementSaturating(state_.ignoredOldSession);
      return false;
    }
    if (!state_.active || event.timeUs < state_.startUs) return false;
    tick(event.timeUs);
    if (!state_.active) return false;
    if (state_.count == state_.capacity) {
      incrementSaturating(state_.dropped);
      return false;
    }
    event.sequence = state_.count + 1;
    storage_[state_.count++] = event;
    return true;
  }

  bool read(uint32_t index, Event& out) const {
    if (index >= state_.count) return false;
    out = storage_[index];
    return true;
  }

  // Late web-task imports retain ISR time, including the stopped/expired tail.
  // Only external error rows may enter a closed session; ordinary TX cannot.
  bool appendExternal(Event event, uint32_t expectedSession) {
    if (expectedSession != state_.session) {
      incrementSaturating(state_.ignoredOldSession);
      return false;
    }
    if (!state_.session || (event.kind != CAN_ERROR && event.kind != CAN_ERROR_GAP) ||
        event.timeUs < state_.startUs ||
        event.timeUs >= state_.startUs + durationUs() ||
        (!state_.active && event.timeUs > state_.stopUs)) return false;
    if (state_.count == state_.capacity) {
      incrementSaturating(state_.dropped);
      return false;
    }
    event.sequence = state_.count + 1;
    storage_[state_.count++] = event;
    return true;
  }

  Snapshot snapshot() const { return state_; }

 private:
  static uint64_t durationUs() { return UINT64_C(600000000); }
  static void incrementSaturating(uint32_t& value) {
    if (value != UINT32_MAX) ++value;
  }

  Event* storage_;
  Snapshot state_;
};

}  // namespace p4_r79_timing

#endif
