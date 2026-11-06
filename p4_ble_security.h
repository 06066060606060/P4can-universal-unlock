#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

#if !defined(CONFIG_NIMBLE_ENABLED)
#error "P4 BLE security requires the Arduino NimBLE host"
#endif

// The mapper serializes links. Observe only its current connection attempt;
// never depend on Arduino's global securityStarted flag or a second GAP event.
struct P4BleSecurityResult {
  int startRc = -1;
  int encryptionRc = -1;
  int pairingRc = -1;
  int disconnectRc = -1;
  bool repairAttempted = false;
  uint32_t elapsedMs = 0;
};

static constexpr uint32_t P4_BLE_SECURITY_TIMEOUT_MS = 10000;
static portMUX_TYPE p4BleSecurityMux = portMUX_INITIALIZER_UNLOCKED;
static ble_gap_event_listener p4BleSecurityListener = {};
static bool p4BleSecurityListenerReady = false;
static bool p4BleSecurityActive = false;
static uint16_t p4BleSecurityHandle = BLE_HS_CONN_HANDLE_NONE;
static P4BleSecurityResult p4BleSecurityResult;
static ble_npl_event p4BleHostDrainEvent = {};
static bool p4BleHostDrainPending = false;

static void p4BleHostDrainDone(ble_npl_event *event) {
  (void)event;
  __atomic_store_n(&p4BleHostDrainPending, false, __ATOMIC_RELEASE);
}

static bool p4BleHostDrainIsPending() {
  return __atomic_load_n(&p4BleHostDrainPending, __ATOMIC_ACQUIRE);
}

static bool p4BleAwaitHostIdle(uint32_t timeoutMs) {
  bool expected = false;
  if (__atomic_compare_exchange_n(&p4BleHostDrainPending, &expected, true, false,
                                  __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
    ble_npl_eventq_put(nimble_port_get_dflt_eventq(), &p4BleHostDrainEvent);
  }
  const uint32_t started = millis();
  while (p4BleHostDrainIsPending()) {
    if (uint32_t(millis() - started) >= timeoutMs) return false;
    vTaskDelay(pdMS_TO_TICKS(10));
  }
  return true;
}

static void p4BleSecurityConfigure() {
  // Disable Arduino's implicit ATT-error retry into secureConnection().
  // Native SMP retains the same bonded Secure Connections / Just Works policy.
  BLESecurity::setAuthenticationMode(false, false, false);
  BLESecurity::setForceAuthentication(false);
  ble_hs_cfg.sm_bonding = 1;
  ble_hs_cfg.sm_mitm = 0;
  ble_hs_cfg.sm_sc = 1;
}

static int p4BleSecurityObserve(ble_gap_event *event, void *arg) {
  (void)arg;
  portENTER_CRITICAL(&p4BleSecurityMux);
  if (p4BleSecurityActive) {
    if (event->type == BLE_GAP_EVENT_CONNECT && event->connect.status == 0 &&
        p4BleSecurityHandle == BLE_HS_CONN_HANDLE_NONE) {
      p4BleSecurityHandle = event->connect.conn_handle;
    } else if (event->type == BLE_GAP_EVENT_ENC_CHANGE &&
               event->enc_change.conn_handle == p4BleSecurityHandle) {
      if (p4BleSecurityResult.encryptionRc <= 0)
        p4BleSecurityResult.encryptionRc = event->enc_change.status;
    } else if (event->type == BLE_GAP_EVENT_PARING_COMPLETE &&
               event->pairing_complete.conn_handle == p4BleSecurityHandle) {
      if (p4BleSecurityResult.pairingRc <= 0)
        p4BleSecurityResult.pairingRc = event->pairing_complete.status;
    } else if (event->type == BLE_GAP_EVENT_DISCONNECT &&
               event->disconnect.conn.conn_handle == p4BleSecurityHandle) {
      p4BleSecurityResult.disconnectRc = event->disconnect.reason;
    }
  }
  portEXIT_CRITICAL(&p4BleSecurityMux);
  return 0;
}

static bool p4BleSecurityInit() {
  if (p4BleSecurityListenerReady) return true;
  if (p4BleHostDrainIsPending()) return false;
  ble_npl_event_init(&p4BleHostDrainEvent, p4BleHostDrainDone, nullptr);
  const int rc = ble_gap_event_listener_register(&p4BleSecurityListener,
                                                p4BleSecurityObserve, nullptr);
  p4BleSecurityListenerReady = (rc == 0);
  return p4BleSecurityListenerReady;
}

static void p4BleSecurityBeginAttempt() {
  portENTER_CRITICAL(&p4BleSecurityMux);
  p4BleSecurityResult = P4BleSecurityResult{};
  p4BleSecurityHandle = BLE_HS_CONN_HANDLE_NONE;
  p4BleSecurityActive = true;
  portEXIT_CRITICAL(&p4BleSecurityMux);
}

static void p4BleSecurityShutdown() {
  portENTER_CRITICAL(&p4BleSecurityMux);
  p4BleSecurityActive = false;
  portEXIT_CRITICAL(&p4BleSecurityMux);
  if (p4BleSecurityListenerReady) {
    ble_gap_event_listener_unregister(&p4BleSecurityListener);
    p4BleSecurityListenerReady = false;
  }
}

static bool p4BleSecurityComplete(bool ok, const char *phase, char *error,
                                  size_t errorSize, P4BleSecurityResult *out,
                                  uint32_t started) {
  P4BleSecurityResult result;
  portENTER_CRITICAL(&p4BleSecurityMux);
  p4BleSecurityResult.elapsedMs = uint32_t(millis() - started);
  result = p4BleSecurityResult;
  if (ok && (result.disconnectRc >= 0 || result.encryptionRc > 0 || result.pairingRc > 0)) {
    ok = false;
    phase = "failed";
  }
  p4BleSecurityActive = false;
  portEXIT_CRITICAL(&p4BleSecurityMux);
  if (out) *out = result;
  if (error && errorSize) {
    if (ok) error[0] = '\0';
    else snprintf(error, errorSize, "security %s: i=%d e=%d sm=%d d=%d",
                  phase, result.startRc, result.encryptionRc,
                  result.pairingRc, result.disconnectRc);
  }
  return ok;
}

static bool p4BleSecureClient(BLEClient *client, char *error, size_t errorSize,
                              P4BleSecurityResult *out, bool (*keepRunning)()) {
  const uint32_t started = millis();
  if (!p4BleSecurityListenerReady || !client || !client->isConnected())
    return p4BleSecurityComplete(false, "disconnected", error, errorSize, out, started);
  const uint16_t handle = client->getConnId();
  portENTER_CRITICAL(&p4BleSecurityMux);
  p4BleSecurityHandle = handle;
  p4BleSecurityActive = true;
  portEXIT_CRITICAL(&p4BleSecurityMux);
  bool initiated = false;
  bool repaired = false;
  for (;;) {
    if (keepRunning && !keepRunning())
      return p4BleSecurityComplete(false, "cancelled", error, errorSize, out, started);
    P4BleSecurityResult state;
    portENTER_CRITICAL(&p4BleSecurityMux);
    state = p4BleSecurityResult;
    portEXIT_CRITICAL(&p4BleSecurityMux);
    if (state.disconnectRc >= 0 || !client->isConnected() || client->getConnId() != handle)
      return p4BleSecurityComplete(false, "disconnected", error, errorSize, out, started);
    const uint32_t elapsed = uint32_t(millis() - started);
    if (elapsed > P4_BLE_SECURITY_TIMEOUT_MS)
      return p4BleSecurityComplete(false, "timeout", error, errorSize, out, started);
    ble_gap_conn_desc desc = {};
    if (ble_gap_conn_find(handle, &desc) != 0)
      return p4BleSecurityComplete(false, "disconnected", error, errorSize, out, started);
    const bool missingKey = state.encryptionRc == BLE_HS_ERR_HCI_BASE + BLE_ERR_PINKEY_MISSING;
    if (missingKey && !repaired) {
      // Repair only this confirmed missing key, never all bonds or an
      // unrelated timeout/rejection. The same overall deadline still applies.
      const int rc = ble_store_util_delete_peer(&desc.peer_id_addr);
      if (rc != 0 && rc != BLE_HS_ENOENT)
        return p4BleSecurityComplete(false, "key removal failed", error, errorSize, out, started);
      repaired = true;
      initiated = false;
      portENTER_CRITICAL(&p4BleSecurityMux);
      p4BleSecurityResult.repairAttempted = true;
      p4BleSecurityResult.encryptionRc = -1;
      p4BleSecurityResult.pairingRc = -1;
      portEXIT_CRITICAL(&p4BleSecurityMux);
    } else if (state.encryptionRc > 0 || state.pairingRc > 0) {
      return p4BleSecurityComplete(false, "failed", error, errorSize, out, started);
    } else if (desc.sec_state.encrypted) {
      return p4BleSecurityComplete(true, "ready", error, errorSize, out, started);
    }
    if (elapsed >= P4_BLE_SECURITY_TIMEOUT_MS)
      return p4BleSecurityComplete(false, "timeout", error, errorSize, out, started);
    if (!initiated) {
      const int rc = ble_gap_security_initiate(handle);
      portENTER_CRITICAL(&p4BleSecurityMux);
      p4BleSecurityResult.startRc = rc;
      portEXIT_CRITICAL(&p4BleSecurityMux);
      if (rc != 0 && rc != BLE_HS_EALREADY)
        return p4BleSecurityComplete(false, "start failed", error, errorSize, out, started);
      initiated = true;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}
