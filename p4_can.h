#pragma once
#include "driver/twai.h"
#include "p4_twai_priority.h"
#include "soc/soc_caps.h"
#include "pin_config.h"
#include "can_error_diag_macros.h"
#include "can_gpio_pure.h"
#include "r79_timing_capture_pure.h"
#include "p4_can_mode_pure.h"

#ifndef P4_R79_TIMING_RX
#define P4_R79_TIMING_RX(bus, frame) ((void)0)
#define P4_R79_TIMING_TX_BEGIN(bus, frame, wait) 0u
#define P4_R79_TIMING_TX_END(token, frame, result, called) ((void)(token))
#endif
#ifndef P4_R79_TIMING_GATE_REJECTED
#define P4_R79_TIMING_GATE_REJECTED(bus, frame, wait, result) ((void)0)
#endif
#ifndef P4_R79_TIMING_GATE_REASON
#define P4_R79_TIMING_GATE_REASON(bus, frame, wait, result, reason) P4_R79_TIMING_GATE_REJECTED(bus, frame, wait, result)
#endif
#if !defined(CONFIG_IDF_TARGET_ESP32P4) || SOC_TWAI_CONTROLLER_NUM < 3
#error "This firmware requires ESP32-P4 with three TWAI controllers"
#endif

// These identities are physical and never change with the vehicle profile.
enum P4CanBus : uint8_t { P4_BODY = 0, P4_CHASSIS = 1, P4_PARTY = 2, P4_CAN_COUNT = 3 };
static int p4CanTxPins[] = {CAN_BODY_TX, CAN_CHASSIS_TX, CAN_PARTY_TX};
static int p4CanRxPins[] = {CAN_BODY_RX, CAN_CHASSIS_RX, CAN_PARTY_RX};
static bool p4CanGpioValid = true;
static const char *const p4CanNames[] = {"BODY", "CHASSIS", "PARTY"};
static inline const char *p4CanRoleName(uint8_t bus) {
  if (bus >= P4_CAN_COUNT) return "UNKNOWN";
  if (activeProfileIsYl()) return bus == 0 ? "VEHICLE" : bus == 1 ? "BODY" : "PARTY";
  return p4CanNames[bus];
}
static twai_handle_t p4CanHandles[P4_CAN_COUNT] = {};
// Owned by each bus RX task; retain the latest dequeued MUX1 origin for retries.
static p4_twai_rx_metadata_t p4CanMux1Origin[P4_CAN_COUNT] = {};
static volatile bool p4CanOnline[P4_CAN_COUNT] = {};
static volatile uint8_t p4CanState[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanRxCount[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanLastRxMs[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanTxAccepted[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanTxRejected[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanBusOffCount[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanMissed[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanOverrun[P4_CAN_COUNT] = {};
static volatile int32_t p4CanInitError[P4_CAN_COUNT] = {ESP_ERR_INVALID_STATE, ESP_ERR_INVALID_STATE, ESP_ERR_INVALID_STATE};
static volatile int32_t p4CanLastRxResult[P4_CAN_COUNT] = {ESP_ERR_INVALID_STATE, ESP_ERR_INVALID_STATE, ESP_ERR_INVALID_STATE};
static volatile uint32_t p4CanRxPolls[P4_CAN_COUNT] = {};
static volatile bool p4CanPassive[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanTec[P4_CAN_COUNT] = {}, p4CanRec[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanTxQueued[P4_CAN_COUNT] = {}, p4CanRxQueued[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanBusErrors[P4_CAN_COUNT] = {}, p4CanArbLost[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanDriverTxFailed[P4_CAN_COUNT] = {}, p4CanStatusMs[P4_CAN_COUNT] = {};
static volatile uint32_t p4CanRecoveries[P4_CAN_COUNT] = {}, p4CanRecoveryFailures[P4_CAN_COUNT] = {};

// A/B identify existing feature routes, not connectors. YL user names:
// A=PARTY, B=VEHICLE(original VH), extra=BODY; internal enums are retained. Other models: A=Body, B=Chassis, extra=Party.
static inline uint8_t p4CanBusA() { return activeProfileIsYl() ? P4_PARTY : P4_BODY; }
static inline uint8_t p4CanBusB() { return activeProfileIsYl() ? P4_BODY : P4_CHASSIS; }
static inline uint8_t p4CanBusExtra() { return activeProfileIsYl() ? P4_CHASSIS : P4_PARTY; }
static inline uint8_t p4CanLogicalBus(uint8_t route) {
  return route == 0 ? p4CanBusA() : route == 1 ? p4CanBusB() : p4CanBusExtra();
}
static inline const char *p4CanPhysicalName(uint8_t bus) {
  return bus == P4_BODY ? "CAN 1" : bus == P4_CHASSIS ? "CAN 2" : "CAN 3";
}
static inline twai_handle_t p4CanHandleB() { return p4CanHandles[p4CanBusB()]; }
static volatile bool p4CanExtraFresh = false;
static inline uint32_t p4CanReadinessMask() {
  return (p4CanOnline[0] ? 1u : 0u) | (p4CanOnline[1] ? 2u : 0u) |
      (p4CanOnline[2] ? 4u : 0u) | (p4CanExtraFresh ? 8u : 0u);
}
static inline bool p4CanAllRunning() {
  return p4CanOnline[0] && p4CanOnline[1] && p4CanOnline[2] && p4CanExtraFresh;
}

// A copied frame retains its physical origin. New A-route frames resolve the
// default at the final enqueue boundary; no frame is mirrored to another bus.
struct CanFrame {
  uint32_t can_id = 0;
  uint8_t can_dlc = 0;
  uint8_t data[8] = {};
  uint8_t bus = 0xff;
};

struct P4CanTimingConfiguration {
  uint32_t bitrate;
  twai_timing_config_t timing;
};
static P4CanTimingConfiguration p4CanConfiguredTiming(uint8_t bus) {
  P4CanTimingConfiguration config = {500000u, TWAI_TIMING_CONFIG_500KBITS()};
  if (activeProfileIsYl() && bus == P4_CHASSIS) {
    // YL physical CAN2 is BODY. Preserve XTAL and 500 kbit/s.
    // P4 requires an even BRP: XTAL40 / 4MHz = 10, 8 TQ/bit,
    // sample at (1 + 6) / 8 = 87.5%. SJW must not exceed TSEG2.
    config.timing.quanta_resolution_hz = 4000000u;
    config.timing.brp = 0u;
    config.timing.prop_seg = 0u;
    config.timing.tseg_1 = 6u;
    config.timing.tseg_2 = 1u;
    config.timing.sjw = 1u;
  }
  return config;
}
static uint32_t p4CanConfiguredBitrate(uint8_t bus) {
  return bus < P4_CAN_COUNT ? p4CanConfiguredTiming(bus).bitrate : 0u;
}

static bool p4CanInstall(uint8_t bus, bool passive, uint32_t txQueueLength = 32) {
  if (bus >= P4_CAN_COUNT || p4CanHandles[bus]) return false;
  if (!p4CanGpioValid) { p4CanInitError[bus] = ESP_ERR_INVALID_STATE; return false; }
  const bool effectivePassive = p4CanReceiveOnlyPure(activeProfileIsYl(), bus, passive);
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT_V2(
      bus, (gpio_num_t)p4CanTxPins[bus], (gpio_num_t)p4CanRxPins[bus],
      effectivePassive ? TWAI_MODE_LISTEN_ONLY : TWAI_MODE_NORMAL);
  g.rx_queue_len = 256;
  g.tx_queue_len = txQueueLength;
  g.alerts_enabled = TWAI_ALERT_TX_FAILED | TWAI_ALERT_ERR_PASS |
      TWAI_ALERT_BUS_ERROR | TWAI_ALERT_BUS_OFF | TWAI_ALERT_RX_QUEUE_FULL;
  twai_timing_config_t t = p4CanConfiguredTiming(bus).timing;
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  p4CanPassive[bus] = effectivePassive;
  P4_CAN_DIAG_RX_CONFIG(bus, activeProfileIsYl() && bus == P4_CHASSIS);
  p4CanInitError[bus] = twai_driver_install_v2(&g, &t, &f, &p4CanHandles[bus]);
  if (p4CanInitError[bus] != ESP_OK) return false;
  P4_CAN_DIAG_EPOCH(bus);
  p4CanInitError[bus] = twai_start_v2(p4CanHandles[bus]);
  if (p4CanInitError[bus] != ESP_OK) {
    if (twai_driver_uninstall_v2(p4CanHandles[bus]) == ESP_OK) p4CanHandles[bus] = nullptr;
    return false;
  }
  if (bus == p4CanBusExtra()) p4CanExtraFresh = false;
  p4CanState[bus] = TWAI_STATE_RUNNING;
  p4CanOnline[bus] = true;
  p4CanLastRxMs[bus] = 0;
  p4CanMissed[bus] = 0;
  p4CanOverrun[bus] = 0;
  return true;
}

// Called only after the CAN tasks and senders have parked. A recovering
// controller is kept installed until it stops; a failed teardown never starts it.
static bool p4CanUninstall(uint8_t bus) {
  if (bus >= P4_CAN_COUNT) return false;
  p4CanOnline[bus] = false;
  if (!p4CanHandles[bus]) return true;
  twai_status_info_t st = {};
  if (twai_get_status_info_v2(p4CanHandles[bus], &st) != ESP_OK) return false;
  if (st.state == TWAI_STATE_RUNNING && twai_stop_v2(p4CanHandles[bus]) != ESP_OK) return false;
  if (st.state == TWAI_STATE_RECOVERING) return false;
  if (twai_driver_uninstall_v2(p4CanHandles[bus]) != ESP_OK) return false;
  p4CanHandles[bus] = nullptr;
  p4CanState[bus] = TWAI_STATE_STOPPED;
  pinMode(p4CanTxPins[bus], INPUT);
  pinMode(p4CanRxPins[bus], INPUT);
  return true;
}
static bool p4CanReinstall(uint8_t bus, bool passive, uint32_t txQueueLength = 32) {
  if (bus >= P4_CAN_COUNT) return false;
  const uint32_t start = millis();
  while (p4CanHandles[bus]) {
    twai_status_info_t st = {};
    if (twai_get_status_info_v2(p4CanHandles[bus], &st) != ESP_OK) return false;
    if (st.state != TWAI_STATE_RECOVERING) break;
    if ((uint32_t)(millis() - start) >= 1800) return false;
    delay(5);
  }
  return p4CanUninstall(bus) && p4CanInstall(bus, passive, txQueueLength);
}
static bool p4CanStopAll() {
  bool ok = true;
  for (uint8_t bus = 0; bus < P4_CAN_COUNT; ++bus) {
    const bool stopped = p4CanUninstall(bus);
    ok = stopped && ok;
  }
  return ok;
}
static void p4CanObserveRx(uint8_t bus) {
  __atomic_add_fetch(&p4CanRxCount[bus], 1U, __ATOMIC_RELAXED);
  __atomic_store_n(&p4CanLastRxMs[bus], (uint32_t)millis(), __ATOMIC_RELAXED);
}
static void p4CanPublishStatus(uint8_t bus, const twai_status_info_t &st) {
  P4_CAN_DIAG_STATUS(bus, st, 0u);
  p4CanState[bus] = (uint8_t)st.state;
  p4CanMissed[bus] = st.rx_missed_count;
  p4CanOverrun[bus] = st.rx_overrun_count;
  p4CanTec[bus] = st.tx_error_counter;
  p4CanRec[bus] = st.rx_error_counter;
  p4CanTxQueued[bus] = st.msgs_to_tx;
  p4CanRxQueued[bus] = st.msgs_to_rx;
  p4CanBusErrors[bus] = st.bus_error_count;
  p4CanArbLost[bus] = st.arb_lost_count;
  p4CanDriverTxFailed[bus] = st.tx_failed_count;
  p4CanStatusMs[bus] = millis();
}
// The same native receive call as the working reference, shared by all three
// physical controllers. Counters are updated before any vehicle decoder/gate.
static esp_err_t p4CanReceiveRaw(uint8_t bus, twai_message_t *out, TickType_t wait = 0) {
  if (!out || bus >= P4_CAN_COUNT) return ESP_ERR_INVALID_ARG;
  if (!p4CanHandles[bus]) return ESP_ERR_INVALID_STATE;
  __atomic_add_fetch(&p4CanRxPolls[bus], 1U, __ATOMIC_RELAXED);
  // Native RX writes EXT/RTR only. Copied RX templates must not inherit
  // stale TX-only SS/SELF or reserved bits from the destination object.
  out->flags = 0;
  const esp_err_t err = twai_receive_v2(p4CanHandles[bus], out, wait);
  p4CanLastRxResult[bus] = err;
  if (err == ESP_OK) {
    out->flags &= TWAI_MSG_FLAG_EXTD | TWAI_MSG_FLAG_RTR;
    if (!out->extd && !out->rtr && out->identifier == 0x3FD &&
        out->data_length_code == 8 && (out->data[0] & 7) == 1) {
      p4CanMux1Origin[bus] = {};
      (void)p4_twai_rx_metadata_v2(p4CanHandles[bus], &p4CanMux1Origin[bus]);
    }
    P4_CAN_DIAG_RX(bus);
    p4CanObserveRx(bus);
    P4_R79_TIMING_RX(bus, *out);
  }
  return err;
}
static esp_err_t p4CanReadFrame(uint8_t bus, CanFrame *out) {
  if (!out || bus >= P4_CAN_COUNT || !p4CanHandles[bus]) return ESP_ERR_INVALID_ARG;
  twai_message_t f = {};
  const esp_err_t err = p4CanReceiveRaw(bus, &f);
  if (err != ESP_OK) return err;
  if (f.data_length_code > 8 || f.identifier > (f.extd ? 0x1fffffffUL : 0x7ffUL))
    return ESP_ERR_INVALID_ARG;
  *out = {};
  out->bus = bus;
  out->can_id = f.identifier | (f.extd ? 0x80000000UL : 0) | (f.rtr ? 0x40000000UL : 0);
  out->can_dlc = f.data_length_code;
  if (!f.rtr) memcpy(out->data, f.data, f.data_length_code);
  return ESP_OK;
}
static esp_err_t p4CanReadFrameA(CanFrame *out) { return p4CanReadFrame(p4CanBusA(), out); }
static esp_err_t p4CanSendFrame(const CanFrame *in, uint8_t source = 0u) {
  (void)source;
  if (!in || in->can_dlc > 8 || (in->can_id & 0x20000000UL)) return ESP_ERR_INVALID_ARG;
  const uint8_t bus = in->bus == 0xff ? p4CanBusA() : in->bus;
  if (bus >= P4_CAN_COUNT || !p4CanHandles[bus] || !p4CanAllRunning()) {
    if (in->can_id == 0x3FDu && in->can_dlc == 8u) {
      twai_message_t rejected = {};
      rejected.identifier = in->can_id;
      rejected.data_length_code = in->can_dlc;
      memcpy(rejected.data, in->data, 8);
      P4_R79_TIMING_GATE_REASON(bus, &rejected, 0, ESP_ERR_INVALID_STATE, p4_r79_timing::ALL_CONTROLLERS_NOT_READY);
    }
    twai_message_t rejectedDiag = {};
    rejectedDiag.identifier = in->can_id & 0x1fffffffUL;
    rejectedDiag.extd = (in->can_id & 0x80000000UL) != 0;
    rejectedDiag.rtr = (in->can_id & 0x40000000UL) != 0;
    rejectedDiag.data_length_code = in->can_dlc;
    memcpy(rejectedDiag.data, in->data, in->can_dlc);
    P4_CAN_DIAG_TX(bus, &rejectedDiag, ESP_ERR_INVALID_STATE, false, source);
    return ESP_ERR_INVALID_STATE;
  }
  twai_message_t f = {};
  f.extd = (in->can_id & 0x80000000UL) != 0;
  f.rtr = (in->can_id & 0x40000000UL) != 0;
  f.identifier = in->can_id & 0x1fffffffUL;
  if (f.identifier > (f.extd ? 0x1fffffffUL : 0x7ffUL)) return ESP_ERR_INVALID_ARG;
  f.data_length_code = in->can_dlc;
  if (!f.rtr) memcpy(f.data, in->data, in->can_dlc);
  const auto timingToken = P4_R79_TIMING_TX_BEGIN(bus, &f, 0);
  const auto diagToken = P4_CAN_DIAG_TX_BEGIN(bus, &f, source);
  const esp_err_t err = twai_transmit_v2(p4CanHandles[bus], &f, 0);
  P4_R79_TIMING_TX_END(timingToken, &f, err, true);
  P4_CAN_DIAG_TX_END(bus, diagToken, &f, err, source);
  if (err == ESP_OK) __atomic_add_fetch(&p4CanTxAccepted[bus], 1U, __ATOMIC_RELAXED);
  else __atomic_add_fetch(&p4CanTxRejected[bus], 1U, __ATOMIC_RELAXED);
  return err;
}
static esp_err_t p4CanSendB(const twai_message_t *f, TickType_t wait = 0, uint8_t source = 0u,
    const p4_twai_priority_guard_t *priority = nullptr, bool mux1ImmediateOnly = false) {
  (void)source;
  const uint8_t bus = p4CanBusB();
  if (!f || f->data_length_code > 8 || f->identifier > (f->extd ? 0x1fffffffUL : 0x7ffUL)) {
    return ESP_ERR_INVALID_ARG;
  }
  // YL R79 depends on VEHICLE transport and PARTY state, not additional BODY.
  // Only the explicit guarded priority route gets this exception. Ordinary
  // features retain their existing all-controller admission requirements.
  const bool ready = priority && activeProfileIsYl()
      ? p4CanOnline[p4CanBusA()] && p4CanOnline[bus] && p4CanHandles[bus]
      : p4CanAllRunning();
  if (!ready) {
    P4_R79_TIMING_GATE_REASON(bus, f, wait, ESP_ERR_INVALID_STATE, p4_r79_timing::ALL_CONTROLLERS_NOT_READY);
    P4_CAN_DIAG_TX(bus, f, ESP_ERR_INVALID_STATE, false, source);
    return ESP_ERR_INVALID_STATE;
  }
  const auto timingToken = P4_R79_TIMING_TX_BEGIN(bus, f, wait);
  const auto diagToken = P4_CAN_DIAG_TX_BEGIN(bus, f, source);
  const esp_err_t err = priority
      ? p4_twai_transmit_r79_v2(p4CanHandles[bus], f, priority)
      : mux1ImmediateOnly ? p4_twai_transmit_mux1_now_v2(p4CanHandles[bus], f)
      : twai_transmit_v2(p4CanHandles[bus], f, wait);
  P4_R79_TIMING_TX_END(timingToken, f, err, true);
  P4_CAN_DIAG_TX_END(bus, diagToken, f, err, source);
  if (err == ESP_OK) __atomic_add_fetch(&p4CanTxAccepted[bus], 1U, __ATOMIC_RELAXED);
  else __atomic_add_fetch(&p4CanTxRejected[bus], 1U, __ATOMIC_RELAXED);
  return err;
}

static bool p4CanR79InputCurrent() {
  return p4_twai_r79_input_current_v2(p4CanHandleB(), p4CanMux1Origin[p4CanBusB()].sequence);
}
static void p4CanR79InputDone() {
  p4_twai_r79_input_done_v2(p4CanHandleB(), p4CanMux1Origin[p4CanBusB()].sequence);
}

// Only the final authorized R79 composers use this explicit priority route.
static esp_err_t p4CanSendR79B(const twai_message_t *f, const p4_twai_priority_guard_t &guard) {
  p4_twai_priority_guard_t tagged = guard;
  const p4_twai_rx_metadata_t &origin = p4CanMux1Origin[p4CanBusB()];
  tagged.rx_sequence = origin.sequence;
  tagged.rx_observed_us = origin.observed_us;
  tagged.rx_dequeued_us = origin.dequeued_us;
  return p4CanSendB(f, 0u, 0u, &tagged);
}

// Stock-derived MUX1 overlays are valid only for immediate ordinary TX.
// Busy admission leaves ULC pending for a fresh stock frame or R79 composition.
static esp_err_t p4CanSendMux1B(const twai_message_t *f) {
  return p4CanSendB(f, 0u, 0u, nullptr, true);
}
