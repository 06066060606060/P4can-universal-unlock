#pragma once

// Standalone legacy host fixtures can omit the observational adapter.
#ifndef P4_CAN_DIAG_STATUS
#define P4_CAN_DIAG_STATUS(bus, status, alerts) ((void)0)
#endif
#ifndef P4_CAN_DIAG_ALERTS
#define P4_CAN_DIAG_ALERTS(bus, alerts) ((void)0)
#endif
#ifndef P4_CAN_DIAG_RX
#define P4_CAN_DIAG_RX(bus) ((void)0)
#endif
#ifndef P4_CAN_DIAG_TX
#define P4_CAN_DIAG_TX(bus, frame, result, called, source) ((void)0)
#endif
#ifndef P4_CAN_DIAG_EPOCH
#define P4_CAN_DIAG_EPOCH(bus) ((void)0)
#endif
#ifndef P4_CAN_DIAG_SERVICE
#define P4_CAN_DIAG_SERVICE(bus) ((void)0)
#endif
#ifndef P4_CAN_DIAG_RECOVERY
#define P4_CAN_DIAG_RECOVERY(bus, start, success) ((void)0)
#endif
#ifndef P4_CAN_DIAG_NVS_WRITE
#define P4_CAN_DIAG_NVS_WRITE(source, expression) (expression)
#endif

#ifndef P4_CAN_DIAG_TX_BEGIN
#define P4_CAN_DIAG_TX_BEGIN(bus, frame, source) (0u)
#endif
#ifndef P4_CAN_DIAG_TX_END
#define P4_CAN_DIAG_TX_END(bus, token, frame, result, source) do { (void)(token); P4_CAN_DIAG_TX(bus, frame, result, true, source); } while (0)
#endif

#ifndef P4_CAN_DIAG_REINIT
#define P4_CAN_DIAG_REINIT(id, reason, diag, phase) ((void)0)
#endif

#ifndef P4_CAN_DIAG_RX_CONFIG
#define P4_CAN_DIAG_RX_CONFIG(bus, enabled) ((void)0)
#endif
