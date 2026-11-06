#pragma once
#include "driver/twai.h"
#include "soc/soc_caps.h"
#include "pin_config.h"
#if !defined(CONFIG_IDF_TARGET_ESP32P4) || SOC_TWAI_CONTROLLER_NUM < 3
#error "This firmware requires ESP32-P4 with three TWAI controllers"
#endif

// These identities are physical and never change with the vehicle profile.
enum P4CanBus : uint8_t { P4_BODY = 0, P4_CHASSIS = 1, P4_PARTY = 2, P4_CAN_COUNT = 3 };
static constexpr int p4CanTxPins[] = {CAN_BODY_TX, CAN_CHASSIS_TX, CAN_PARTY_TX};
static constexpr int p4CanRxPins[] = {CAN_BODY_RX, CAN_CHASSIS_RX, CAN_PARTY_RX};
static const char *const p4CanNames[] = {"BODY", "CHASSIS", "PARTY"};
static twai_handle_t p4CanHandles[P4_CAN_COUNT] = {};
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

// A/B identify existing feature routes, not connectors. YL: A=Party, B=Body
// (formerly VH), extra=Chassis. Other models: A=Body, B=Chassis, extra=Party.
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

static bool p4CanInstall(uint8_t bus, bool passive, uint32_t txQueueLength = 32) {
  if (bus >= P4_CAN_COUNT || p4CanHandles[bus]) return false;
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT_V2(
      bus, (gpio_num_t)p4CanTxPins[bus], (gpio_num_t)p4CanRxPins[bus],
      passive ? TWAI_MODE_LISTEN_ONLY : TWAI_MODE_NORMAL);
  g.rx_queue_len = 256;
  g.tx_queue_len = txQueueLength;
  g.alerts_enabled = TWAI_ALERT_TX_FAILED | TWAI_ALERT_ERR_PASS |
      TWAI_ALERT_BUS_ERROR | TWAI_ALERT_BUS_OFF | TWAI_ALERT_RX_QUEUE_FULL;
  twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  p4CanPassive[bus] = passive;
  p4CanInitError[bus] = twai_driver_install_v2(&g, &t, &f, &p4CanHandles[bus]);
  if (p4CanInitError[bus] != ESP_OK) return false;
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
  const esp_err_t err = twai_receive_v2(p4CanHandles[bus], out, wait);
  p4CanLastRxResult[bus] = err;
  if (err == ESP_OK) p4CanObserveRx(bus);
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
static esp_err_t p4CanSendFrame(const CanFrame *in) {
  if (!in || in->can_dlc > 8 || (in->can_id & 0x20000000UL)) return ESP_ERR_INVALID_ARG;
  const uint8_t bus = in->bus == 0xff ? p4CanBusA() : in->bus;
  if (bus >= P4_CAN_COUNT || !p4CanHandles[bus] || !p4CanAllRunning()) return ESP_ERR_INVALID_STATE;
  twai_message_t f = {};
  f.extd = (in->can_id & 0x80000000UL) != 0;
  f.rtr = (in->can_id & 0x40000000UL) != 0;
  f.identifier = in->can_id & 0x1fffffffUL;
  if (f.identifier > (f.extd ? 0x1fffffffUL : 0x7ffUL)) return ESP_ERR_INVALID_ARG;
  f.data_length_code = in->can_dlc;
  if (!f.rtr) memcpy(f.data, in->data, in->can_dlc);
  const esp_err_t err = twai_transmit_v2(p4CanHandles[bus], &f, 0);
  if (err == ESP_OK) __atomic_add_fetch(&p4CanTxAccepted[bus], 1U, __ATOMIC_RELAXED);
  else __atomic_add_fetch(&p4CanTxRejected[bus], 1U, __ATOMIC_RELAXED);
  return err;
}
static esp_err_t p4CanSendB(const twai_message_t *f, TickType_t wait = 0) {
  const uint8_t bus = p4CanBusB();
  if (!f || f->data_length_code > 8 || f->identifier > (f->extd ? 0x1fffffffUL : 0x7ffUL)) return ESP_ERR_INVALID_ARG;
  if (!p4CanAllRunning()) return ESP_ERR_INVALID_STATE;
  const esp_err_t err = twai_transmit_v2(p4CanHandles[bus], f, wait);
  if (err == ESP_OK) __atomic_add_fetch(&p4CanTxAccepted[bus], 1U, __ATOMIC_RELAXED);
  else __atomic_add_fetch(&p4CanTxRejected[bus], 1U, __ATOMIC_RELAXED);
  return err;
}
