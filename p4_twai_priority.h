#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "driver/twai.h"

#ifdef __cplusplus
extern "C" {
#endif

// Single RX owner metadata. Native FIFO observation is not wire arrival time.
typedef struct {
    uint64_t observed_us, dequeued_us;
    uint32_t sequence; // zero: no standard DATA/DLC8/MUX1 origin
} p4_twai_rx_metadata_t;

// All referenced values must have static lifetime in internal RAM and be
// updated with atomic stores. The descriptor itself is copied on admission.
typedef struct p4_twai_priority_guard {
    const volatile uint32_t *generation;
    uint32_t expected_generation;
    const volatile uint32_t *cancel_generation;
    uint32_t expected_cancel_generation;
    const volatile bool *administrative_hold;
    bool has_deadline;
    uint32_t deadline_ms;
    uint8_t source; // 2 immediate, 3 periodic; other values become R79_UNKNOWN.
    // Optional live AP permission expiry, independent of the request deadline.
    // Null disables it; zero is a valid wrapping deadline, never a sentinel.
    const volatile uint32_t *permission_deadline_ms
#ifdef __cplusplus
        = nullptr
#endif
        ;
    // An accepted one-shot must reach dispatch/cancellation before replacement.
    bool preserve_pending
#ifdef __cplusplus
        = false
#endif
        ;
    uint32_t rx_sequence
#ifdef __cplusplus
        = 0
#endif
        ;
    uint64_t rx_observed_us
#ifdef __cplusplus
        = 0
#endif
        ;
    uint64_t rx_dequeued_us
#ifdef __cplusplus
        = 0
#endif
        ;
    // Optional AP-only retry authority, independent of general bypass policy.
    // Invalidation advances this generation; later AP validity never revives
    // a descriptor captured before that invalidation.
    const volatile uint32_t *retry_generation
#ifdef __cplusplus
        = nullptr
#endif
        ;
    uint32_t expected_retry_generation
#ifdef __cplusplus
        = 0
#endif
        ;
} p4_twai_priority_guard_t;

// Ordinary current-state clone: standard 0x3FD/DLC8/MUX1 only. Load directly
// only when the native hardware and backlog are idle; otherwise return TIMEOUT.
// Never queues, waits, clears other traffic, or grants R79 authority. Callers
// retain one-shot requests on failure and recompose from fresh input.
esp_err_t p4_twai_transmit_mux1_now_v2(twai_handle_t handle,
                                    const twai_message_t *message);

// Single CAN-B RX owner calls this only between fully processed frames.
// Drains one hardware RX snapshot and services an idle native TX backlog.
// True means the latest observed MUX boundary was delivered and is MUX2,
// with no remaining unclassified hardware RX at this checkpoint.
// Native admission and dispatch independently recheck this fence.
bool p4_twai_r79_periodic_ready_v2(twai_handle_t handle);

// Call after successful receive from the single per-controller RX owner.
bool p4_twai_rx_metadata_v2(twai_handle_t handle, p4_twai_rx_metadata_t *out);
// Only a newer successfully queued MUX1 supersedes an application echo.
bool p4_twai_r79_input_current_v2(twai_handle_t handle, uint32_t sequence);
// Called after processing or deliberately suppressing that input. If replacement
// was unavailable, resume the older still-authorized native pending response.
void p4_twai_r79_input_done_v2(twai_handle_t handle, uint32_t sequence);

// Zero-wait admission for standard 0x3FD/DLC8/MUX1 only. A pending request
// can be replaced only by a valid explicit IMMEDIATE when the old source is
// IMMEDIATE/PERIODIC and preserve_pending is false. Hardware-active TX and
// ordinary FIFO are never displaced.
// ESP_OK means admitted, not transmitted on the wire.
esp_err_t p4_twai_transmit_r79_v2(twai_handle_t handle,
                               const twai_message_t *message,
                               const p4_twai_priority_guard_t *guard);
#ifdef __cplusplus
}
#endif
