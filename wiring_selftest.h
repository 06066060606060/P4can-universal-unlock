#pragma once
// Bench wiring self-test for the 3 x SN65HVD230 transceivers.
//
// Requested from Settings -> System -> Wiring Self-Test. The request is kept in
// RTC no-init memory across a software reboot and the test runs in setup()
// BEFORE any TWAI controller is installed, so live CAN drivers are never torn
// down. It is meant for the bench, without a car:
//   1. Activity guard   - if any CAN pin toggles (live bus), nothing is driven.
//   2. Static check     - transceiver powered? TX/RX on the expected GPIOs?
//   3. Echo check       - driving each TX GPIO must move the matching RX GPIO.
//   4. TWAI loopback    - one single-shot self-reception frame per bus.
// Results live in RAM and are served by GET /api/system/wiring-test.
#include "driver/gpio.h"
#include "driver/twai.h"
#include "esp_attr.h"

enum WiringTestCode : uint8_t {
  WT_NOT_RUN = 0,
  WT_PASS = 1,
  WT_NO_POWER = 2,
  WT_SWAPPED = 3,
  WT_TX_NOT_CONNECTED = 4,
  WT_CROSSED = 5,
  WT_LOOPBACK_FAIL = 6,
  WT_ABORTED = 7,
};

struct WiringBusResult {
  uint8_t code = WT_NOT_RUN;
  bool rxDriven = false;      // RX GPIO held HIGH against pull-down (CRX output present)
  bool txPulledLow = false;   // TX GPIO held LOW against pull-up (CRX output on TX pin)
  bool swapConfirmed = false;
  uint8_t echoMask = 0;       // RX GPIOs (bit per bus) that follow this bus's TX GPIO
  bool loopbackRun = false;
  bool loopbackSelf = false;
  uint8_t loopbackMask = 0;   // other controllers that received this bus's frame
};

struct WiringTestResult {
  bool ran = false;
  bool aborted = false;
  uint32_t ranAtMs = 0;
  uint32_t durationMs = 0;
  uint16_t edges[2 * P4_CAN_COUNT] = {};  // activity guard edges: TX0,RX0,TX1,RX1,TX2,RX2
  WiringBusResult bus[P4_CAN_COUNT];
};

static WiringTestResult wiringTest;
static constexpr uint32_t WIRING_TEST_MAGIC = 0x57495245UL;  // "WIRE"
RTC_NOINIT_ATTR static uint32_t wiringTestRequestMagic;

static inline void wiringTestRequest() { wiringTestRequestMagic = WIRING_TEST_MAGIC; }
static inline bool wiringTestRequested() { return wiringTestRequestMagic == WIRING_TEST_MAGIC; }

static inline gpio_num_t wtTx(uint8_t b) { return (gpio_num_t)p4CanTxPins[b]; }
static inline gpio_num_t wtRx(uint8_t b) { return (gpio_num_t)p4CanRxPins[b]; }

static void wtInput(gpio_num_t pin, bool pullUp) {
  gpio_reset_pin(pin);
  gpio_set_direction(pin, GPIO_MODE_INPUT);
  gpio_set_pull_mode(pin, pullUp ? GPIO_PULLUP_ONLY : GPIO_PULLDOWN_ONLY);
}

// Idle bias for a bus: keep the transceiver's D input recessive (HIGH) and
// listen to its R output with a pull-down, so "HIGH" can only mean "driven".
// For a board already found swapped, bias the other way round.
static void wtBiasIdle(uint8_t b) {
  if (wiringTest.bus[b].code == WT_SWAPPED) {
    wtInput(wtRx(b), true);
    wtInput(wtTx(b), false);
  } else {
    wtInput(wtTx(b), true);
    wtInput(wtRx(b), false);
  }
}

static void wtReleaseAll() {
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) {
    gpio_reset_pin(wtTx(b));
    gpio_reset_pin(wtRx(b));
    pinMode(p4CanTxPins[b], INPUT);
    pinMode(p4CanRxPins[b], INPUT);
  }
}

// 1. A live bus toggles the R outputs. If anything toggles, abort before
//    driving a single pin.
static bool wtBusActivityDetected() {
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) wtBiasIdle(b);
  delay(5);
  int last[2 * P4_CAN_COUNT];
  for (uint8_t i = 0; i < 2 * P4_CAN_COUNT; ++i)
    last[i] = gpio_get_level((i & 1) ? wtRx(i / 2) : wtTx(i / 2));
  const uint32_t start = millis();
  while ((uint32_t)(millis() - start) < 300) {
    for (uint8_t i = 0; i < 2 * P4_CAN_COUNT; ++i) {
      const int v = gpio_get_level((i & 1) ? wtRx(i / 2) : wtTx(i / 2));
      if (v != last[i] && wiringTest.edges[i] < 0xffff) ++wiringTest.edges[i];
      last[i] = v;
    }
  }
  for (uint8_t i = 0; i < 2 * P4_CAN_COUNT; ++i)
    if (wiringTest.edges[i] >= 6) return true;
  return false;
}

// 2. Static check. Inputs only, so a wrong wiring can never cause contention.
static void wtStatic(uint8_t b) {
  WiringBusResult &r = wiringTest.bus[b];
  wtInput(wtTx(b), true);
  wtInput(wtRx(b), false);
  delayMicroseconds(300);
  r.rxDriven = gpio_get_level(wtRx(b)) == 1;
  r.txPulledLow = gpio_get_level(wtTx(b)) == 0;
  if (r.rxDriven) return;
  if (r.txPulledLow) {
    // Looks swapped: our RX GPIO (pull-down) sits on D -> dominant -> R LOW on
    // our TX GPIO. Confirm by reversing the bias: R must then drive TX HIGH.
    wtInput(wtRx(b), true);
    wtInput(wtTx(b), false);
    delayMicroseconds(300);
    r.swapConfirmed = gpio_get_level(wtTx(b)) == 1;
    r.code = r.swapConfirmed ? WT_SWAPPED : WT_NO_POWER;
  } else {
    r.code = WT_NO_POWER;
  }
  wtBiasIdle(b);
}

// 3. Echo check: toggle TX GPIO b, see which RX GPIOs follow every time.
static void wtEcho(uint8_t b) {
  WiringBusResult &r = wiringTest.bus[b];
  uint8_t follows = 0;
  for (uint8_t j = 0; j < P4_CAN_COUNT; ++j)
    if (wiringTest.bus[j].rxDriven) follows |= (uint8_t)(1u << j);
  gpio_set_pull_mode(wtTx(b), GPIO_FLOATING);
  gpio_set_level(wtTx(b), 1);
  gpio_set_direction(wtTx(b), GPIO_MODE_INPUT_OUTPUT);
  delayMicroseconds(50);
  for (uint8_t k = 0; k < 8; ++k) {
    gpio_set_level(wtTx(b), 0);
    delayMicroseconds(20);
    for (uint8_t j = 0; j < P4_CAN_COUNT; ++j)
      if (gpio_get_level(wtRx(j)) != 0) follows &= (uint8_t)~(1u << j);
    gpio_set_level(wtTx(b), 1);
    delayMicroseconds(20);
    for (uint8_t j = 0; j < P4_CAN_COUNT; ++j)
      if (gpio_get_level(wtRx(j)) != 1) follows &= (uint8_t)~(1u << j);
  }
  r.echoMask = follows;
  wtBiasIdle(b);
  delayMicroseconds(100);
  if (follows & (1u << b)) r.code = WT_PASS;              // may be confirmed by loopback
  else if (follows) r.code = WT_CROSSED;
  else r.code = WT_TX_NOT_CONNECTED;
}

// 4. TWAI loopback: NO_ACK mode, single-shot frame with self-reception.
static void wtLoopback() {
  twai_handle_t h[P4_CAN_COUNT] = {};
  bool use[P4_CAN_COUNT] = {};
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) {
    if (wiringTest.bus[b].code != WT_PASS) continue;
    gpio_reset_pin(wtTx(b));
    gpio_reset_pin(wtRx(b));
    twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT_V2(
        b, wtTx(b), wtRx(b), TWAI_MODE_NO_ACK);
    g.rx_queue_len = 8;
    g.tx_queue_len = 2;
    g.alerts_enabled = TWAI_ALERT_NONE;
    twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    if (twai_driver_install_v2(&g, &t, &f, &h[b]) != ESP_OK) { h[b] = nullptr; continue; }
    if (twai_start_v2(h[b]) != ESP_OK) {
      twai_driver_uninstall_v2(h[b]);
      h[b] = nullptr;
      continue;
    }
    use[b] = true;
  }
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) {
    if (!use[b]) continue;
    WiringBusResult &r = wiringTest.bus[b];
    r.loopbackRun = true;
    for (uint8_t j = 0; j < P4_CAN_COUNT; ++j) {  // drain
      twai_message_t junk;
      while (use[j] && twai_receive_v2(h[j], &junk, 0) == ESP_OK) {}
    }
    twai_message_t m = {};
    m.identifier = 0x7F0 + b;  // bench-only marker frame
    m.data_length_code = 8;
    m.self = 1;
    m.ss = 1;
    const uint8_t payload[8] = {'W', 'I', 'R', 'E', 'T', 'S', 'T', (uint8_t)('1' + b)};
    memcpy(m.data, payload, 8);
    if (twai_transmit_v2(h[b], &m, pdMS_TO_TICKS(20)) == ESP_OK) {
      const uint32_t start = millis();
      while ((uint32_t)(millis() - start) < 60) {
        for (uint8_t j = 0; j < P4_CAN_COUNT; ++j) {
          if (!use[j]) continue;
          twai_message_t rx;
          if (twai_receive_v2(h[j], &rx, 0) == ESP_OK && rx.identifier == m.identifier &&
              rx.data_length_code == 8 && memcmp(rx.data, payload, 8) == 0) {
            if (j == b) r.loopbackSelf = true;
            else r.loopbackMask |= (uint8_t)(1u << j);
          }
        }
        delay(1);
      }
    }
  }
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) {
    if (!h[b]) continue;
    twai_status_info_t st = {};
    if (twai_get_status_info_v2(h[b], &st) == ESP_OK && st.state == TWAI_STATE_RUNNING)
      twai_stop_v2(h[b]);
    twai_driver_uninstall_v2(h[b]);
  }
}

static void wiringTestPrint() {
  static const char *const names[] = {"NOT_RUN", "PASS", "NO_POWER", "SWAPPED",
      "TX_NOT_CONNECTED", "CROSSED", "LOOPBACK_FAIL", "ABORTED"};
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) {
    const WiringBusResult &r = wiringTest.bus[b];
    Serial.printf("[WIRING] CAN%u %s TX%d RX%d: %s rx=%d txLow=%d echo=0x%X loop=%d/0x%X\n",
        b + 1, p4CanNames[b], p4CanTxPins[b], p4CanRxPins[b], names[r.code],
        r.rxDriven, r.txPulledLow, r.echoMask, r.loopbackSelf, r.loopbackMask);
  }
}

// Called from setup() before any TWAI controller is installed.
static void wiringTestRunIfRequested() {
  if (!wiringTestRequested()) return;
  wiringTestRequestMagic = 0;  // one shot, even if the test crashes
  wiringTest = WiringTestResult();
  wiringTest.ran = true;
  const uint32_t start = millis();
  wiringTest.ranAtMs = start;
  if (wtBusActivityDetected()) {
    wiringTest.aborted = true;
    for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) wiringTest.bus[b].code = WT_ABORTED;
  } else {
    for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) wtStatic(b);
    for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) wtBiasIdle(b);
    delayMicroseconds(300);
    for (uint8_t b = 0; b < P4_CAN_COUNT; ++b)
      if (wiringTest.bus[b].code == WT_NOT_RUN) wtEcho(b);
    wtLoopback();
  }
  wtReleaseAll();
  wiringTest.durationMs = millis() - start;
  wiringTestPrint();
}

static String wtGpioList(uint8_t mask, bool rx) {
  String s;
  for (uint8_t j = 0; j < P4_CAN_COUNT; ++j) {
    if (!(mask & (1u << j))) continue;
    if (s.length()) s += ", ";
    s += "GPIO" + String(rx ? p4CanRxPins[j] : p4CanTxPins[j]) + " (CAN " + String(j + 1) + ")";
  }
  return s;
}

static String wiringTestMessage(uint8_t b) {
  const WiringBusResult &r = wiringTest.bus[b];
  const String tx = "GPIO" + String(p4CanTxPins[b]);
  const String rx = "GPIO" + String(p4CanRxPins[b]);
  String note;
  const uint8_t shared = (uint8_t)((r.echoMask | r.loopbackMask) & ~(1u << b));
  if (shared && r.code == WT_PASS)
    note = " CANH/CANL appear linked to " + wtGpioList(shared, true) +
           " on the breadboard (fine for bench, keep buses separate in the car).";
  switch (r.code) {
    case WT_PASS:
      return "Powered. CTX on " + tx + ", CRX on " + rx + "." +
             (r.loopbackSelf ? String(" 500 kbit/s loopback frame OK.")
                             : String(" (500 kbit/s loopback frame did not return: normal on a bare breadboard "
                                      "with the 120 ohm removed; add a temporary 120 ohm across CANH-CANL to test it.)")) +
             note;
    case WT_NO_POWER:
      return rx + " stays LOW: transceiver has no 3V3/GND, or its CRX is not wired to " + rx + ".";
    case WT_SWAPPED:
      return "TX/RX swapped: CTX is on " + rx + " and CRX is on " + tx +
             ". Swap the two signal wires.";
    case WT_TX_NOT_CONNECTED:
      return "Powered and CRX is on " + rx + ", but toggling " + tx +
             " does not reach the transceiver: CTX is not wired to " + tx + ".";
    case WT_CROSSED:
      return "Wires crossed between boards: " + tx + " drives the transceiver whose CRX is on " +
             wtGpioList(r.echoMask, true) + ".";
    case WT_ABORTED:
      return "Aborted: CAN activity detected. Disconnect from the car and run again.";
    default:
      return "Not run.";
  }
}

static String wiringTestJson() {
  static const char *const codes[] = {"not_run", "pass", "no_power", "swapped",
      "tx_not_connected", "crossed", "loopback_fail", "aborted"};
  String j = "{\"ok\":true,\"ran\":";
  j += wiringTest.ran ? "true" : "false";
  j += ",\"aborted\":";
  j += wiringTest.aborted ? "true" : "false";
  j += ",\"durationMs\":" + String(wiringTest.durationMs);
  j += ",\"pending\":";
  j += wiringTestRequested() ? "true" : "false";
  j += ",\"buses\":[";
  for (uint8_t b = 0; b < P4_CAN_COUNT; ++b) {
    const WiringBusResult &r = wiringTest.bus[b];
    if (b) j += ",";
    j += "{\"bus\":" + String(b + 1) + ",\"name\":\"" + p4CanNames[b] + "\"";
    j += ",\"tx\":" + String(p4CanTxPins[b]) + ",\"rx\":" + String(p4CanRxPins[b]);
    j += ",\"code\":\"" + String(codes[r.code]) + "\"";
    j += ",\"pass\":";
    j += r.code == WT_PASS ? "true" : "false";
    j += ",\"loopback\":";
    j += r.loopbackSelf ? "true" : "false";
    j += ",\"edges\":[" + String(wiringTest.edges[2 * b]) + "," + String(wiringTest.edges[2 * b + 1]) + "]";
    j += ",\"message\":\"" + wiringTestMessage(b) + "\"}";
  }
  j += "]}";
  return j;
}
