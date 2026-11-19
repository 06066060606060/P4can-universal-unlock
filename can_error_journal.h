#pragma once
#include <Arduino.h>
#include <driver/twai.h>
#include <esp_timer.h>
#include "can_error_journal_pure.h"

namespace CanDiagRuntime {
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
// Deliberately ordinary static RAM: no PSRAM, heap or persistence in hooks.
static CanDiag::Journal journal;
static_assert(sizeof(CanDiag::Journal) + sizeof(CanDiag::Snapshot) + sizeof(mux) <= 50u * 1024u,
              "CAN diagnostic runtime plus export snapshot exceeds 50 KiB");
static_assert(TWAI_STATE_BUS_OFF == CanDiag::STATE_BUS_OFF &&
              TWAI_STATE_RECOVERING == CanDiag::STATE_RECOVERING,
              "legacy TWAI controller state mapping changed");
static inline uint64_t now() { return static_cast<uint64_t>(esp_timer_get_time()); }
static inline uint32_t errorAlerts(uint32_t alerts) {
  // Preserve raw alerts in each record. Contention and success notifications
  // alone cannot prove a protocol fault, exact failed frame or wire result.
  return alerts & (TWAI_ALERT_TX_FAILED | TWAI_ALERT_ERR_PASS | TWAI_ALERT_BUS_ERROR |
                   TWAI_ALERT_BUS_OFF | TWAI_ALERT_RX_QUEUE_FULL | TWAI_ALERT_ABOVE_ERR_WARN);
}
} // namespace CanDiagRuntime

static inline void canDiagInit(uint32_t bootId) {
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.init(bootId, now());
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagObserveStatus(uint8_t bus, const CanDiag::Status& status, uint32_t alerts) {
  if (bus >= CanDiag::BUS_COUNT) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeStatus(bus, status, alerts, now(), errorAlerts(alerts), (alerts & TWAI_ALERT_BUS_OFF) != 0);
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagObserveAlerts(uint8_t bus, uint32_t alerts) {
  if (bus >= CanDiag::BUS_COUNT || !alerts) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeAlerts(bus, alerts, now(), errorAlerts(alerts), (alerts & TWAI_ALERT_BUS_OFF) != 0);
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagObserveTx(uint8_t bus, uint32_t id, uint8_t dlc,
                                   const uint8_t* data, int32_t result,
                                   uint8_t source, bool called) {
  if (bus >= CanDiag::BUS_COUNT) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeTx(bus, id, dlc, data, result, source, called, now());
  portEXIT_CRITICAL(&mux);
}
static inline uint32_t canDiagTxBegin(uint8_t bus, uint32_t id, uint8_t dlc,
                                      const uint8_t* data, uint8_t source) {
  if (bus >= CanDiag::BUS_COUNT) return 0;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  const uint32_t token = journal.txBegin(bus, id, dlc, data, source, now());
  portEXIT_CRITICAL(&mux);
  return token;
}
static inline void canDiagTxEnd(uint8_t bus, uint32_t token, int32_t result) {
  if (bus >= CanDiag::BUS_COUNT || !token) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.txEnd(bus, token, result, now());
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagObserveService(uint8_t bus) {
  if (bus >= CanDiag::BUS_COUNT) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeService(bus, now());
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagObserveRx(uint8_t bus) {
  if (bus >= CanDiag::BUS_COUNT) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeRx(bus, now());
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagControllerEpoch(uint8_t bus) {
  if (bus >= CanDiag::BUS_COUNT) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.controllerEpoch(bus, now());
  portEXIT_CRITICAL(&mux);
}
// start=true describes initiate_recovery return; start=false/success=true
// describes a later observed RUNNING state, not queue acceptance.
static inline void canDiagObserveRecovery(uint8_t bus, bool start, bool success) {
  if (bus >= CanDiag::BUS_COUNT) return;
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeRecovery(bus, start, success, now());
  portEXIT_CRITICAL(&mux);
}
static inline void canDiagObserveReinit(uint32_t requestId, uint8_t reason,
                                        uint8_t diagnosticReason, uint8_t phase) {
  using namespace CanDiagRuntime;
  portENTER_CRITICAL(&mux);
  journal.observeReinit(requestId, reason, diagnosticReason, phase, now());
  portEXIT_CRITICAL(&mux);
}
class CanDiagFlashScope {
 public:
  explicit CanDiagFlashScope(uint8_t source) : generation_(0) {
    using namespace CanDiagRuntime;
    portENTER_CRITICAL(&mux);
    generation_ = journal.flashBegin(source, now());
    portEXIT_CRITICAL(&mux);
  }
  ~CanDiagFlashScope() {
    using namespace CanDiagRuntime;
    portENTER_CRITICAL(&mux);
    journal.flashEnd(generation_, now());
    portEXIT_CRITICAL(&mux);
  }
  CanDiagFlashScope(const CanDiagFlashScope&) = delete;
  CanDiagFlashScope& operator=(const CanDiagFlashScope&) = delete;
 private:
  uint32_t generation_;
};

static inline bool canDiagSnapshot(CanDiag::Snapshot& out) {
  using namespace CanDiagRuntime;
  // Each critical copy is at most flash history or bus metadata (<1 KiB), never the
  // entire journal. Immutable events/flash history share a structural generation;
  // hot RX/TX/service context is copied per bus at copiedAtUs within the bounded
  // [captureBeginUs,capturedUs] interval, not an atomic instant across buses.
  // Concurrent hooks continue; a changed structural version retries up to
  // three times, then explicitly rejects the capture without changing history.
  for (unsigned attempt = 0; attempt < 3; ++attempt) {
    portENTER_CRITICAL(&mux);
    const uint32_t version = journal.version();
    journal.copyHeader(out, now());
    const uint64_t beginUs = out.captureBeginUs;
    const bool initialized = journal.initialized();
    portEXIT_CRITICAL(&mux);
    if (!initialized) { out.consistent = false; return false; }
    bool coherent = true;
    for (uint32_t index = 0; index < out.reinitCount && coherent; ++index) {
      portENTER_CRITICAL(&mux);
      coherent = journal.version() == version && journal.readReinit(index, out.reinitEvents[index]);
      portEXIT_CRITICAL(&mux);
    }
    for (uint8_t bus = 0; bus < CanDiag::BUS_COUNT && coherent; ++bus) {
      portENTER_CRITICAL(&mux);
      coherent = journal.version() == version;
      if (coherent) {
        journal.copyBusMeta(bus, out.buses[bus]);
        out.buses[bus].copiedAtUs = now();
      }
      portEXIT_CRITICAL(&mux);
      if (!coherent) break;
      for (uint32_t i = 0; i < out.buses[bus].count; ++i) {
        portENTER_CRITICAL(&mux);
        coherent = journal.version() == version && journal.readEvent(bus, i, out.buses[bus].events[i]);
        portEXIT_CRITICAL(&mux);
        if (!coherent) break;
      }
    }
    portENTER_CRITICAL(&mux);
    coherent = coherent && journal.version() == version;
    if (coherent) {
      journal.copyHeader(out, now());
      out.captureBeginUs = beginUs;
    }
    portEXIT_CRITICAL(&mux);
    if (coherent) { out.consistent = true; return true; }
  }
  out.consistent = false;
  return false;
}
