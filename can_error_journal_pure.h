#pragma once
#include <stdint.h>
#include <string.h>
#define CAN_DIAG_FLASH_HISTORY 1
#define CAN_DIAG_TX_PENDING 1
#define CAN_DIAG_CAPTURE_INTERVAL 1

// Physical bus indices only: 0 BODY, 1 VEHICLE/CHASSIS, 2 PARTY.
// All times describe software observations; submission is not wire completion.
namespace CanDiag {
static constexpr uint8_t BUS_COUNT = 3;
static constexpr uint8_t EVENT_CAPACITY = 32;
static constexpr uint8_t FLASH_CAPACITY = 32;
static constexpr uint8_t REINIT_CAPACITY = 8;
static constexpr uint32_t PERIOD_US = 1000000;
static constexpr uint32_t STATE_STOPPED = 0, STATE_RUNNING = 1,
                          STATE_BUS_OFF = 2, STATE_RECOVERING = 3;
enum Reason : uint32_t {
  BASELINE = 1u << 0, PERIODIC = 1u << 1, STATUS_CHANGE = 1u << 2,
  COUNTER_CHANGE = 1u << 3, ALERT = 1u << 4, COUNTER_RESET = 1u << 5,
  CONTROLLER_EPOCH = 1u << 6, RECOVERY_START = 1u << 7,
  RECOVERY_ACCEPTED = 1u << 8, RECOVERY_FAILURE = 1u << 9,
  RECOVERY_RUNNING = 1u << 10, BUS_OFF_ALERT = 1u << 11, SERVICE_GAP = 1u << 12
};
enum FlashFlag : uint8_t { FLASH_VALID = 1u, FLASH_OVERLAPPED = 2u };
struct Status {
  uint32_t state, tec, rec, txPending, rxPending;
  uint32_t txFailed, missed, overrun, busErrors, arbLost;
};
struct Tx {
  uint64_t observedUs;
  uint32_t id;
  int32_t result;
  uint32_t callId, resultDelayUs; // Delay saturates at UINT32_MAX; result invalid while pending.
  uint8_t data[8], dlc, source;
  bool called, valid, resultPending;
};
struct FlashWindow {
  uint64_t beginUs, endUs;
  uint32_t seq;
  uint16_t activeCount;
  uint8_t source, flags;
};
struct Event {
  uint64_t observedUs, statusObservedUs;
  uint32_t seq, epoch, reasonMask, alerts;
  Status status, delta;
  Tx tx;
  FlashWindow flashCurrent, flashLast;
  uint32_t rxAgeUs, serviceGapUs;
  uint8_t bus;
  bool rxSeen, serviceSeen, statusValid;
};
struct BusSnapshot {
  Event events[EVENT_CAPACITY]; // Exported [0,count) is chronological.
  uint32_t count, observed, overwritten, epoch, unmatchedTxResults;
  Status latestStatus;
  Tx latestTx;
  Event firstError, latestError, firstBusOff;
  bool hasStatus, hasFirstError, hasLatestError, hasFirstBusOff;
  uint64_t lastRxUs, lastServiceUs, latestStatusUs, copiedAtUs;
  uint32_t maxServiceGapUs;
  bool rxSeen, serviceSeen;
};
// Cached per-controller context, not an atomic hardware counter read.
struct ReinitEvent {
  uint64_t observedUs, statusObservedUs[BUS_COUNT];
  uint32_t seq, requestId, controllerEpoch[BUS_COUNT], busErrors[BUS_COUNT];
  uint8_t reason, diagnosticReason, phase, statusValidMask;
};
struct Snapshot {
  uint32_t bootId;
  uint64_t captureBeginUs, capturedUs;
  bool consistent;
  FlashWindow flashCurrent, flashLast;
  FlashWindow flashWindows[FLASH_CAPACITY];
  uint32_t flashCount, flashObserved, flashOverwritten;
  BusSnapshot buses[BUS_COUNT];
  uint32_t reinitCount, reinitObserved, reinitOverwritten;
  ReinitEvent reinitEvents[REINIT_CAPACITY];
};

class Journal {
 public:
  void init(uint32_t bootId, uint64_t nowUs);
  void observeStatus(uint8_t bus, const Status& status, uint32_t alerts,
                     uint64_t nowUs, uint32_t errorAlerts = 0, bool busOffAlert = false);
  void observeAlerts(uint8_t bus, uint32_t alerts, uint64_t nowUs,
                     uint32_t errorAlerts = 0, bool busOffAlert = false);
  void observeTx(uint8_t bus, uint32_t id, uint8_t dlc, const uint8_t* data,
                 int32_t result, uint8_t source, bool called, uint64_t nowUs);
  uint32_t txBegin(uint8_t bus, uint32_t id, uint8_t dlc, const uint8_t* data,
                   uint8_t source, uint64_t nowUs);
  void txEnd(uint8_t bus, uint32_t callId, int32_t result, uint64_t nowUs);
  void observeService(uint8_t bus, uint64_t nowUs);
  void observeRx(uint8_t bus, uint64_t nowUs);
  void controllerEpoch(uint8_t bus, uint64_t nowUs);
  void observeRecovery(uint8_t bus, bool start, bool success, uint64_t nowUs);
  uint32_t flashBegin(uint8_t source, uint64_t nowUs);
  void flashEnd(uint32_t generation, uint64_t nowUs);
  bool readEvent(uint8_t bus, uint32_t index, Event& out) const;
  void copyBusMeta(uint8_t bus, BusSnapshot& out) const;
  void copyHeader(Snapshot& out, uint64_t nowUs) const;
  void observeReinit(uint32_t requestId, uint8_t reason, uint8_t diagnosticReason,
                     uint8_t phase, uint64_t nowUs);
  bool readReinit(uint32_t index, ReinitEvent& out) const;
  uint32_t version() const { return version_; }
  bool initialized() const { return initialized_; }
  const BusSnapshot& bus(uint8_t index) const { return buses_[index]; }
 private:
  BusSnapshot buses_[BUS_COUNT] = {};
  ReinitEvent reinitEvents_[REINIT_CAPACITY] = {};
  uint32_t reinitCount_ = 0, reinitObserved_ = 0, reinitOverwritten_ = 0;
  uint8_t reinitNext_ = 0;
  FlashWindow flashCurrent_ = {}, flashLast_ = {};
  FlashWindow flashWindows_[FLASH_CAPACITY] = {};
  uint32_t flashCount_ = 0, flashObserved_ = 0, flashOverwritten_ = 0;
  uint8_t flashNext_ = 0;
  uint64_t observedUs_ = 0, lastRecordUs_[BUS_COUNT] = {};
  uint32_t bootId_ = 0, seq_ = 0, version_ = 0, flashGeneration_ = 0, txCallId_ = 0;
  uint8_t next_[BUS_COUNT] = {};
  bool initialized_ = false;
  uint64_t time(uint64_t nowUs);
  void append(uint8_t bus, uint32_t reason, uint32_t alerts,
              const Status& delta, bool error, uint64_t nowUs);
};
} // namespace CanDiag

namespace CanDiag {
static inline uint32_t saturatedAge(uint64_t nowUs, uint64_t thenUs) {
  const uint64_t age = nowUs >= thenUs ? nowUs - thenUs : 0;
  return age > UINT32_MAX ? UINT32_MAX : static_cast<uint32_t>(age);
}
static inline uint32_t increment(uint32_t value) {
  return value == UINT32_MAX ? value : value + 1;
}
inline uint64_t Journal::time(uint64_t nowUs) {
  if (nowUs > observedUs_) observedUs_ = nowUs;
  return observedUs_;
}
inline void Journal::init(uint32_t bootId, uint64_t nowUs) {
  bootId_ = bootId;
  observedUs_ = nowUs;
  seq_ = 0;
  ++version_;
  if (++flashGeneration_ == 0) ++flashGeneration_;
  flashCurrent_ = {};
  flashLast_ = {};
  flashCount_ = flashObserved_ = flashOverwritten_ = 0;
  flashNext_ = 0;
  reinitCount_ = reinitObserved_ = reinitOverwritten_ = 0;
  reinitNext_ = 0;
  for (uint8_t i = 0; i < BUS_COUNT; ++i) {
    BusSnapshot& b = buses_[i];
    // Old event bytes are unreachable after resetting the ring metadata. Avoid
    // clearing the large storage while a caller holds the task-side mutex.
    b.count = b.observed = b.overwritten = b.unmatchedTxResults = 0;
    b.epoch = 1;
    b.hasStatus = b.hasFirstError = b.hasLatestError = b.hasFirstBusOff = false;
    b.latestStatus = {};
    b.latestTx = {};
    b.lastRxUs = b.lastServiceUs = b.latestStatusUs = b.copiedAtUs = 0;
    b.maxServiceGapUs = 0;
    b.rxSeen = b.serviceSeen = false;
    next_[i] = 0;
    lastRecordUs_[i] = 0;
  }
  initialized_ = true;
}
inline void Journal::append(uint8_t busIndex, uint32_t reason, uint32_t alerts,
                            const Status& delta, bool error, uint64_t nowUs) {
  ++version_; // Immutable event generation; hot live context has its own capture time.
  BusSnapshot& b = buses_[busIndex];
  Event e = {};
  e.observedUs = nowUs;
  e.statusObservedUs = b.latestStatusUs;
  if (++seq_ == 0) ++seq_;
  e.seq = seq_;
  e.epoch = b.epoch;
  e.reasonMask = reason;
  e.alerts = alerts;
  e.status = b.latestStatus;
  e.statusValid = b.hasStatus;
  e.delta = delta;
  e.tx = b.latestTx;
  e.flashCurrent = flashCurrent_;
  e.flashLast = flashLast_;
  e.rxSeen = b.rxSeen;
  e.serviceSeen = b.serviceSeen;
  e.rxAgeUs = b.rxSeen ? saturatedAge(nowUs, b.lastRxUs) : 0;
  e.serviceGapUs = b.serviceSeen ? saturatedAge(nowUs, b.lastServiceUs) : 0;
  e.bus = busIndex;
  b.events[next_[busIndex]] = e;
  next_[busIndex] = uint8_t((next_[busIndex] + 1) % EVENT_CAPACITY);
  if (b.count < EVENT_CAPACITY) ++b.count;
  else b.overwritten = increment(b.overwritten);
  b.observed = increment(b.observed);
  lastRecordUs_[busIndex] = nowUs;
  if (error) {
    if (!b.hasFirstError) { b.firstError = e; b.hasFirstError = true; }
    b.latestError = e;
    b.hasLatestError = true;
  }
  if (e.statusValid && e.status.state == STATE_BUS_OFF && !b.hasFirstBusOff) {
    b.firstBusOff = e;
    b.hasFirstBusOff = true;
  }
}
inline void Journal::observeStatus(uint8_t busIndex, const Status& status,
                                  uint32_t alerts, uint64_t nowUs, uint32_t errorAlerts, bool busOffAlert) {
  if (!initialized_ || busIndex >= BUS_COUNT) return;
  nowUs = time(nowUs);
  BusSnapshot& b = buses_[busIndex];
  Status delta = {};
  uint32_t reason = 0;
  bool error = false;
  if (!b.hasStatus) reason |= BASELINE;
  else {
    const Status& old = b.latestStatus;
    const bool reset = status.txFailed < old.txFailed || status.missed < old.missed ||
        status.overrun < old.overrun || status.busErrors < old.busErrors || status.arbLost < old.arbLost;
    if (reset) {
      b.epoch = increment(b.epoch);
      reason |= COUNTER_RESET;
    } else {
      delta.txFailed = status.txFailed - old.txFailed;
      delta.missed = status.missed - old.missed;
      delta.overrun = status.overrun - old.overrun;
      delta.busErrors = status.busErrors - old.busErrors;
      delta.arbLost = status.arbLost - old.arbLost;
      if (delta.txFailed || delta.missed || delta.overrun || delta.busErrors || delta.arbLost)
        reason |= COUNTER_CHANGE;
      error = delta.txFailed || delta.missed || delta.overrun || delta.busErrors;
    }
    if (status.state == STATE_RUNNING && old.state != STATE_RUNNING)
      reason |= RECOVERY_RUNNING;
    if (memcmp(&old, &status, sizeof(Status)) != 0) reason |= STATUS_CHANGE;
    if (nowUs - lastRecordUs_[busIndex] >= PERIOD_US) reason |= PERIODIC;
  }
  b.latestStatus = status;
  b.latestStatusUs = nowUs;
  b.hasStatus = true;
  if (alerts) reason |= ALERT;
  if (busOffAlert) reason |= BUS_OFF_ALERT;
  error = error || errorAlerts || status.tec || status.rec || status.state == STATE_BUS_OFF;
  if (reason) append(busIndex, reason, alerts, delta, error, nowUs);
}
inline void Journal::observeAlerts(uint8_t busIndex, uint32_t alerts, uint64_t nowUs,
                                  uint32_t errorAlerts, bool busOffAlert) {
  if (!initialized_ || busIndex >= BUS_COUNT || !alerts) return;
  nowUs = time(nowUs);
  append(busIndex, uint32_t(ALERT) | (busOffAlert ? uint32_t(BUS_OFF_ALERT) : 0u),
         alerts, Status{}, errorAlerts != 0 || busOffAlert, nowUs);
}
inline void Journal::observeTx(uint8_t busIndex, uint32_t id, uint8_t dlc,
                              const uint8_t* data, int32_t result, uint8_t source,
                              bool called, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT) return;
  Tx tx = {};
  tx.observedUs = time(nowUs);
  tx.id = id;
  tx.result = result;
  tx.dlc = dlc > 8 ? 8 : dlc;
  if (data) memcpy(tx.data, data, tx.dlc);
  tx.source = source;
  tx.called = called;
  tx.valid = true;
  buses_[busIndex].latestTx = tx;
}
inline uint32_t Journal::txBegin(uint8_t busIndex, uint32_t id, uint8_t dlc,
                                 const uint8_t* data, uint8_t source, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT) return 0;
  observeTx(busIndex, id, dlc, data, 0, source, true, nowUs);
  if (++txCallId_ == 0) ++txCallId_;
  Tx& tx = buses_[busIndex].latestTx;
  tx.callId = txCallId_;
  tx.resultPending = true;
  return tx.callId;
}
inline void Journal::txEnd(uint8_t busIndex, uint32_t callId, int32_t result, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT || !callId) return;
  nowUs = time(nowUs);
  BusSnapshot& b = buses_[busIndex];
  if (b.latestTx.callId == callId && b.latestTx.resultPending) {
    b.latestTx.result = result;
    b.latestTx.resultDelayUs = saturatedAge(nowUs, b.latestTx.observedUs);
    b.latestTx.resultPending = false;
  } else b.unmatchedTxResults = increment(b.unmatchedTxResults);
}
inline void Journal::observeService(uint8_t busIndex, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT) return;
  nowUs = time(nowUs);
  BusSnapshot& b = buses_[busIndex];
  if (b.serviceSeen) {
    const uint32_t gap = saturatedAge(nowUs, b.lastServiceUs);
    if (gap > b.maxServiceGapUs) b.maxServiceGapUs = gap;
    if (gap >= 50000u) append(busIndex, SERVICE_GAP, 0, Status{}, false, nowUs);
  }
  b.lastServiceUs = nowUs;
  b.serviceSeen = true;
}
inline void Journal::observeRx(uint8_t busIndex, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT) return;
  buses_[busIndex].lastRxUs = time(nowUs);
  buses_[busIndex].rxSeen = true;
}
inline void Journal::controllerEpoch(uint8_t busIndex, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT) return;
  nowUs = time(nowUs);
  BusSnapshot& b = buses_[busIndex];
  b.epoch = increment(b.epoch);
  b.hasStatus = false;
  b.latestStatus = {};
  b.latestStatusUs = 0;
  b.latestTx = {};
  append(busIndex, CONTROLLER_EPOCH, 0, Status{}, false, nowUs);
}
inline void Journal::observeRecovery(uint8_t busIndex, bool start, bool success, uint64_t nowUs) {
  if (!initialized_ || busIndex >= BUS_COUNT) return;
  nowUs = time(nowUs);
  const uint32_t reason = start
      ? uint32_t(RECOVERY_START | (success ? RECOVERY_ACCEPTED : RECOVERY_FAILURE))
      : uint32_t(success ? RECOVERY_RUNNING : RECOVERY_FAILURE);
  // Recovery/service gaps are context; they do not establish the initiating error.
  append(busIndex, reason, 0, Status{}, false, nowUs);
}
inline uint32_t Journal::flashBegin(uint8_t source, uint64_t nowUs) {
  if (!initialized_) return 0;
  nowUs = time(nowUs);
  if (!flashCurrent_.activeCount) {
    if (++flashGeneration_ == 0) ++flashGeneration_;
    flashCurrent_ = {};
    flashCurrent_.beginUs = nowUs;
    flashCurrent_.seq = flashGeneration_;
    flashCurrent_.source = source;
    flashCurrent_.flags = FLASH_VALID;
  } else flashCurrent_.flags |= FLASH_OVERLAPPED;
  if (flashCurrent_.activeCount == UINT16_MAX) return 0;
  ++flashCurrent_.activeCount;
  ++version_;
  return flashCurrent_.seq;
}
inline void Journal::flashEnd(uint32_t generation, uint64_t nowUs) {
  if (!initialized_ || !generation || generation != flashCurrent_.seq || !flashCurrent_.activeCount) return;
  nowUs = time(nowUs);
  ++version_;
  if (--flashCurrent_.activeCount == 0) {
    flashCurrent_.endUs = nowUs;
    flashLast_ = flashCurrent_;
    flashWindows_[flashNext_] = flashLast_;
    flashNext_ = uint8_t((flashNext_ + 1) % FLASH_CAPACITY);
    if (flashCount_ < FLASH_CAPACITY) ++flashCount_;
    else flashOverwritten_ = increment(flashOverwritten_);
    flashObserved_ = increment(flashObserved_);
    flashCurrent_ = {};
  }
}
inline bool Journal::readEvent(uint8_t busIndex, uint32_t index, Event& out) const {
  if (!initialized_ || busIndex >= BUS_COUNT || index >= buses_[busIndex].count) return false;
  const uint32_t first = buses_[busIndex].count == EVENT_CAPACITY ? next_[busIndex] : 0;
  out = buses_[busIndex].events[(first + index) % EVENT_CAPACITY];
  return true;
}
inline void Journal::copyBusMeta(uint8_t busIndex, BusSnapshot& out) const {
  const BusSnapshot& b = buses_[busIndex];
  out.count = b.count;
  out.observed = b.observed;
  out.overwritten = b.overwritten;
  out.epoch = b.epoch;
  out.unmatchedTxResults = b.unmatchedTxResults;
  out.latestStatus = b.latestStatus;
  out.latestTx = b.latestTx;
  out.hasStatus = b.hasStatus;
  out.hasFirstError = b.hasFirstError;
  out.hasLatestError = b.hasLatestError;
  out.hasFirstBusOff = b.hasFirstBusOff;
  out.firstError = b.hasFirstError ? b.firstError : Event{};
  out.latestError = b.hasLatestError ? b.latestError : Event{};
  out.firstBusOff = b.hasFirstBusOff ? b.firstBusOff : Event{};
  out.lastRxUs = b.lastRxUs;
  out.lastServiceUs = b.lastServiceUs;
  out.latestStatusUs = b.latestStatusUs;
  out.copiedAtUs = observedUs_;
  out.maxServiceGapUs = b.maxServiceGapUs;
  out.rxSeen = b.rxSeen;
  out.serviceSeen = b.serviceSeen;
}
inline void Journal::observeReinit(uint32_t requestId, uint8_t reason,
                                  uint8_t diagnosticReason, uint8_t phase, uint64_t nowUs) {
  if (!initialized_ || phase < 1 || phase > 3) return;
  ReinitEvent event = {};
  event.observedUs = time(nowUs);
  event.seq = reinitObserved_ = increment(reinitObserved_);
  event.requestId = requestId;
  event.reason = reason; event.diagnosticReason = diagnosticReason; event.phase = phase;
  for (uint8_t bus = 0; bus < BUS_COUNT; ++bus) {
    event.controllerEpoch[bus] = buses_[bus].epoch;
    event.statusObservedUs[bus] = buses_[bus].latestStatusUs;
    event.busErrors[bus] = buses_[bus].latestStatus.busErrors;
    if (buses_[bus].hasStatus) event.statusValidMask |= (1u << bus);
  }
  reinitEvents_[reinitNext_] = event;
  reinitNext_ = (reinitNext_ + 1) % REINIT_CAPACITY;
  if (reinitCount_ < REINIT_CAPACITY) ++reinitCount_;
  else reinitOverwritten_ = increment(reinitOverwritten_);
  ++version_;
}
inline bool Journal::readReinit(uint32_t index, ReinitEvent& out) const {
  if (!initialized_ || index >= reinitCount_) return false;
  const uint32_t first = reinitCount_ == REINIT_CAPACITY ? reinitNext_ : 0;
  out = reinitEvents_[(first + index) % REINIT_CAPACITY];
  return true;
}
inline void Journal::copyHeader(Snapshot& out, uint64_t nowUs) const {
  out.bootId = bootId_;
  out.capturedUs = nowUs > observedUs_ ? nowUs : observedUs_;
  out.captureBeginUs = out.capturedUs;
  out.consistent = initialized_;
  out.reinitCount = reinitCount_;
  out.reinitObserved = reinitObserved_;
  out.reinitOverwritten = reinitOverwritten_;
  out.flashCurrent = flashCurrent_;
  out.flashLast = flashLast_;
  out.flashCount = flashCount_;
  out.flashObserved = flashObserved_;
  out.flashOverwritten = flashOverwritten_;
  const uint32_t first = flashCount_ == FLASH_CAPACITY ? flashNext_ : 0;
  for (uint32_t i = 0; i < flashCount_; ++i)
    out.flashWindows[i] = flashWindows_[(first + i) % FLASH_CAPACITY];
}
} // namespace CanDiag
