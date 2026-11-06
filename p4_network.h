#pragma once
#include "pin_config.h"

// The board sequence follows the supplied P4_CAN_Hosted sketch. WiFi/Hosted
// are initialized by setup(), then owned by the web task for AP changes/retries.
enum P4NetworkPhase : uint8_t {
  P4_NET_NOT_STARTED, P4_NET_PINS_FAILED, P4_NET_WIFI_FAILED,
  P4_NET_ADDRESS_FAILED, P4_NET_AP_FAILED, P4_NET_READY
};
static bool p4NetworkPinsReady = false;
static bool p4NetworkWifiStarted = false;
static bool p4NetworkApStarted = false;
static P4NetworkPhase p4NetworkPhase = P4_NET_NOT_STARTED;
static uint32_t p4NetworkHostVersion[3] = {};
static uint32_t p4NetworkSlaveVersion[3] = {};

static const char *p4NetworkPhaseName() {
  switch (p4NetworkPhase) {
    case P4_NET_PINS_FAILED: return "HOSTED_PINS_FAILED";
    case P4_NET_WIFI_FAILED: return "HOSTED_WIFI_FAILED";
    case P4_NET_ADDRESS_FAILED: return "AP_ADDRESS_FAILED";
    case P4_NET_AP_FAILED: return "AP_START_FAILED";
    case P4_NET_READY: return "READY";
    default: return "NOT_STARTED";
  }
}

static bool p4NetworkPrepare() {
  // Connected to C6 IO2: leave the external pull-up in control, as in the
  // reference sketch. The Hosted driver owns C6 EN/reset on GPIO54.
  pinMode(HOSTED_C6_BOOT, INPUT);
  p4NetworkPinsReady = hostedSetPins(HOSTED_CLK, HOSTED_CMD, HOSTED_D0,
      HOSTED_D1, HOSTED_D2, HOSTED_D3, HOSTED_RESET);
  if (!p4NetworkPinsReady) p4NetworkPhase = P4_NET_PINS_FAILED;
  return p4NetworkPinsReady;
}

static bool p4NetworkBeginWifi() {
  if (!p4NetworkPinsReady) { p4NetworkPhase = P4_NET_PINS_FAILED; return false; }
  if (p4NetworkWifiStarted) return true;
  // Do not disconnect(true)/switch WiFi off: that tears down ESP-Hosted.
  if (!WiFi.mode(WIFI_AP)) { p4NetworkPhase = P4_NET_WIFI_FAILED; return false; }
  p4NetworkWifiStarted = true;
  hostedGetHostVersion(&p4NetworkHostVersion[0], &p4NetworkHostVersion[1], &p4NetworkHostVersion[2]);
  hostedGetSlaveVersion(&p4NetworkSlaveVersion[0], &p4NetworkSlaveVersion[1], &p4NetworkSlaveVersion[2]);
  return true;
}

static bool p4NetworkStartAp(const char *ssid, const char *password) {
  if (!p4NetworkBeginWifi()) return false;
  if (!WiFi.softAPConfig(IPAddress(192,168,4,1), IPAddress(192,168,4,1), IPAddress(255,255,255,0))) {
    p4NetworkPhase = P4_NET_ADDRESS_FAILED;
    return false;
  }
  if (!WiFi.softAP(ssid, password)) { p4NetworkPhase = P4_NET_AP_FAILED; return false; }
  p4NetworkPhase = P4_NET_READY;
  // This admission gate only opens after the first successful AP start. Runtime
  // SSID changes reuse the active Hosted transport, including an active BLE host.
  __atomic_store_n(&p4NetworkApStarted, true, __ATOMIC_RELEASE);
  return true;
}

static bool p4NetworkAllowsBle() {
  return __atomic_load_n(&p4NetworkApStarted, __ATOMIC_ACQUIRE);
}
