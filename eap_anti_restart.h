#pragma once
// ─────────────────────────────────────────────────────────────
// EAP anti-restart — cached 0x331 replay for "TLSSC Restore"
//
// Problem
// -------
// chinaRestoreEcho() rewrites a stock 0x331 DAS_autopilotConfig only when the
// vehicle emits one (read-modify-write). The MCU latches its DAS configuration
// once, at its own boot: if no patched 0x331 is on the bus at that instant it
// latches the banned state and someone has to reboot the MCU manually. That is
// the "reboot the screen every power cycle" symptom. The upstream Flipper
// project labels TLSSC Restore "Triggers MCU reboot" for the same reason.
//
// Fix
// ---
//   1) Cache the last patched 0x331 payload in NVS (at most one write per
//      power cycle; the stock 0x331 counter changes every frame).
//   2) After CAN B becomes ready, replay that cached frame at 10 Hz for a
//      60 s window — before the vehicle sends anything — so the MCU reads
//      SELF_DRIVING whenever it samples the bus at boot.
//   3) Stop as soon as the vehicle sends its own fresh 0x331 (2 s rule) and
//      fall back to the existing reactive chinaRestoreEcho() path.
//   4) Hard-stop at window expiry or after 600 frames. Never synthesise a
//      frame without a cached, previously observed payload.
//
// Safety / boundaries
// -------------------
//   · Active only while "TLSSC Restore" (chinaRestoreEnabled) is on. No
//     separate switch: this is a fix for that feature, not a new feature.
//   · CAN CHASSIS only, matching the 0x331 route, via the same TX barrier /
//     epoch / administrative-hold / USB-passive gates as the reactive path.
//   · TX-barrier contention (ESP_ERR_TIMEOUT) is counted as "yield", not as
//     failure, and does not advance the burst — the next 100 ms tick retries.
//   · All counters are diagnostics only; transmit errors never block CAN.

#include <Arduino.h>

#define EAP_NR_NS        "features"
#define EAP_NR_KEY_FRAME "eapFrame"   // cached 0x331 payload, 8-byte hex string
#define EAP_NR_WINDOW_MS 60000u
#define EAP_NR_PERIOD_MS 100u
#define EAP_NR_MAX_FRAME 600u
#define EAP_NR_STOCK_FRESH_MS 2000u

static uint8_t       eapNrFrame[8] = {};
static volatile uint8_t  eapNrFrameLen = 0;
static volatile bool     eapNrFrameValid = false;
static volatile bool     eapNrPersisted = false;
static volatile uint32_t eapNrStockMs = 0;
static volatile uint32_t eapNrReplayOk = 0;
static volatile uint32_t eapNrReplayFail = 0;
static volatile uint32_t eapNrReplayBusy = 0;
static volatile uint32_t eapNrReplaySkip = 0;
static volatile uint32_t eapNrLastReplayMs = 0;
static volatile int16_t  eapNrLastErr = 0;
static volatile uint32_t eapNrArmedMs = 0;
static volatile uint16_t eapNrBurst = 0;

static void eapNrLoad() {
  Preferences p;
  if (!p.begin(EAP_NR_NS, true)) return;
  const String hex = p.getString(EAP_NR_KEY_FRAME, "");
  p.end();
  if (hex.length() != 16) return;
  auto nib = [](char c) -> int8_t {
    if (c >= '0' && c <= '9') return (int8_t)(c - '0');
    if (c >= 'a' && c <= 'f') return (int8_t)(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return (int8_t)(c - 'A' + 10);
    return -1;
  };
  for (uint8_t i = 0; i < 8; i++) {
    const int8_t a = nib(hex[i * 2]), b = nib(hex[i * 2 + 1]);
    if (a < 0 || b < 0) return;
    eapNrFrame[i] = (uint8_t)((a << 4) | b);
  }
  eapNrFrameLen = 8;
  eapNrFrameValid = true;
  eapNrPersisted = true;  // already on disk: do not rewrite this power cycle
}

static void eapNrPersistFrame() {
  if (eapNrPersisted || !eapNrFrameValid) return;
  char hex[17];
  for (uint8_t i = 0; i < eapNrFrameLen; i++)
    snprintf(hex + i * 2, 3, "%02X", eapNrFrame[i]);
  hex[eapNrFrameLen * 2] = '\0';
  Preferences p;
  if (!p.begin(EAP_NR_NS, false)) return;
  const size_t n = p.putString(EAP_NR_KEY_FRAME, hex);
  p.end();
  if (n > 0) eapNrPersisted = true;
}

// Called next to chinaRestoreEcho() for every stock 0x331, on both CAN paths.
static void eapNrObserve331(uint8_t bus, uint32_t id, uint8_t dlc,
                            const uint8_t *data, uint32_t ms) {
  if (bus != P4_CHASSIS || id != 0x331u || dlc < 1 || dlc > 8 || !data) return;
  eapNrStockMs = ms ? ms : 1u;
  uint8_t patched[8] = {};
  for (uint8_t i = 0; i < dlc; i++) patched[i] = data[i];
  patched[0] = (uint8_t)((patched[0] & 0xC0u) | 0x1Bu);
  bool changed = (eapNrFrameLen != dlc) || !eapNrFrameValid;
  for (uint8_t i = 0; i < dlc && !changed; i++)
    if (eapNrFrame[i] != patched[i]) changed = true;
  if (!changed) return;
  for (uint8_t i = 0; i < dlc; i++) eapNrFrame[i] = patched[i];
  eapNrFrameLen = dlc;
  eapNrFrameValid = true;
  portENTER_CRITICAL(&serviceSettingsMux);
  const bool enabled = chinaRestoreEnabled;
  portEXIT_CRITICAL(&serviceSettingsMux);
  if (enabled) eapNrPersistFrame();
}

// Called from both CAN task service loops (same cadence as chinaRestoreEcho).
static void eapNrTick() {
  portENTER_CRITICAL(&serviceSettingsMux);
  const bool enabled = chinaRestoreEnabled;
  portEXIT_CRITICAL(&serviceSettingsMux);
  if (!enabled) return;
  if (!canTxBarrierMutex || xSemaphoreTake(canTxBarrierMutex, 0) != pdTRUE) {
    eapNrReplayBusy++;   // another injector holds the barrier; yield, retry later
    return;
  }
  const uint32_t now = (uint32_t)millis();
  const uint32_t epoch = canTxEpochSnapshot();
  do {
    if (canTxAdministrativeHold || canUsbPassive() || !p4CanAllRunning() ||
        epoch == 0u || epoch != canTxBarrierState.epoch) break;
    if (p4CanBusB() == P4_BODY && !twaiNonSummonAdmissionOpen()) break;
    if (eapNrArmedMs == 0) eapNrArmedMs = now ? now : 1u;
    if ((uint32_t)(now - eapNrArmedMs) > EAP_NR_WINDOW_MS) break;
    if (eapNrBurst >= EAP_NR_MAX_FRAME) break;
    if (!eapNrFrameValid) { eapNrReplaySkip++; break; }
    if (eapNrStockMs && (uint32_t)(now - eapNrStockMs) < EAP_NR_STOCK_FRESH_MS) break;
    if (eapNrLastReplayMs && (uint32_t)(now - eapNrLastReplayMs) < EAP_NR_PERIOD_MS) break;

    CanFrame out;
    out.bus = P4_CHASSIS;
    out.can_id = 0x331u;
    out.can_dlc = eapNrFrameLen;
    memset(out.data, 0, sizeof(out.data));
    for (uint8_t i = 0; i < eapNrFrameLen; i++) out.data[i] = eapNrFrame[i];
    const esp_err_t err = p4CanSendFrame(&out);
    eapNrLastErr = (int16_t)err;
    if (err == ESP_ERR_TIMEOUT) { eapNrReplayBusy++; break; }
    eapNrLastReplayMs = now ? now : 1u;
    eapNrBurst++;
    if (err == ESP_OK) eapNrReplayOk++; else eapNrReplayFail++;
  } while (0);
  xSemaphoreGive(canTxBarrierMutex);
}

static void eapNrStatsAppend(String &json) {
  json += ",\"eap\":{\"cacheValid\":";
  json += eapNrFrameValid ? "true" : "false";
  json += ",\"cacheLen\":"; json += String((unsigned)eapNrFrameLen);
  json += ",\"cacheHex\":\"";
  if (eapNrFrameValid) {
    for (uint8_t i = 0; i < eapNrFrameLen; i++) {
      char b[3]; snprintf(b, sizeof(b), "%02X", eapNrFrame[i]); json += b;
    }
  }
  json += "\",\"replayOk\":"; json += String((unsigned long)eapNrReplayOk);
  json += ",\"replayFail\":"; json += String((unsigned long)eapNrReplayFail);
  json += ",\"replayBusy\":"; json += String((unsigned long)eapNrReplayBusy);
  json += ",\"replaySkip\":"; json += String((unsigned long)eapNrReplaySkip);
  json += ",\"burst\":"; json += String((unsigned)eapNrBurst);
  json += ",\"lastErr\":"; json += String((int)eapNrLastErr);
  json += ",\"lastErrName\":\"";
  switch ((uint16_t)eapNrLastErr) {
    case 0: json += "OK"; break;
    case 0x107: json += "TX-busy"; break;
    case 0x103: json += "gate-closed"; break;
    case 0x10B: json += "send-failed"; break;
    default: json += "other"; break;
  }
  json += "\",\"epoch\":\""; json += canTxEpochSnapshot() ? "live" : "boot";
  json += "\"}";
}
