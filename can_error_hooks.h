#pragma once
#include "can_error_journal.h"
#include "driver/twai.h"

static void canDiagTwaiStatus(uint8_t bus, const twai_status_info_t &st,
                              uint32_t alerts) {
  CanDiag::Status s = {};
  s.state = (uint32_t)st.state;
  s.tec = st.tx_error_counter; s.rec = st.rx_error_counter;
  s.txPending = st.msgs_to_tx; s.rxPending = st.msgs_to_rx;
  s.txFailed = st.tx_failed_count; s.missed = st.rx_missed_count;
  s.overrun = st.rx_overrun_count; s.busErrors = st.bus_error_count;
  s.arbLost = st.arb_lost_count;
  canDiagObserveStatus(bus, s, alerts);
}
static void canDiagTwaiTx(uint8_t bus, const twai_message_t *frame,
                          int32_t result, bool called, uint8_t source) {
  if (!frame) return;
  const uint32_t id = frame->identifier | (frame->extd ? 0x80000000UL : 0u) |
      (frame->rtr ? 0x40000000UL : 0u);
  canDiagObserveTx(bus, id, frame->data_length_code,
                   frame->rtr ? nullptr : frame->data, result, source, called);
}
static uint32_t canDiagTwaiTxBegin(uint8_t bus, const twai_message_t *frame,
                                   uint8_t source) {
  if (!frame) return 0u;
  return canDiagTxBegin(bus, frame->identifier |
      (frame->extd ? 0x80000000UL : 0u) | (frame->rtr ? 0x40000000UL : 0u),
      frame->data_length_code, frame->rtr ? nullptr : frame->data, source);
}
#define P4_CAN_DIAG_TX_BEGIN(bus, frame, source) canDiagTwaiTxBegin(bus, frame, source)
#define P4_CAN_DIAG_TX_END(bus, token, frame, result, source) canDiagTxEnd(bus, token, result)
#define P4_CAN_DIAG_STATUS(bus, status, alerts) canDiagTwaiStatus(bus, status, alerts)
#define P4_CAN_DIAG_ALERTS(bus, alerts) canDiagObserveAlerts(bus, alerts)
#define P4_CAN_DIAG_RX(bus) canDiagObserveRx(bus)
#define P4_CAN_DIAG_TX(bus, frame, result, called, source) canDiagTwaiTx(bus, frame, result, called, source)
#define P4_CAN_DIAG_EPOCH(bus) canDiagControllerEpoch(bus)
#define P4_CAN_DIAG_SERVICE(bus) canDiagObserveService(bus)
#define P4_CAN_DIAG_RECOVERY(bus, start, success) canDiagObserveRecovery(bus, start, success)
// Sources: 1=settings, 2=app BLE registry, 3=preheat, 4=BUS OFF persistence,
// 5=web/reset/network settings, 6=USB mode, 7=continuous AP, 8=checked blob.
// These are application call windows, not exact physical flash/cache events.
#define P4_CAN_DIAG_NVS_WRITE(source, expression) ([&]() { CanDiagFlashScope scope(source); return (expression); }())

#define P4_CAN_DIAG_REINIT(id, reason, diag, phase) canDiagObserveReinit(id, reason, diag, phase)

#define P4_CAN_DIAG_RX_CONFIG(bus, enabled) p4TwaiDiagConfigureRxCapture(bus, enabled)
