/*
 * SPDX-FileCopyrightText: 2015-2025 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/idf_additions.h"
#include "esp_types.h"
#include "esp_log.h"
#include "esp_intr_alloc.h"
#include "esp_pm.h"
#include "esp_attr.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_clk_tree.h"
#include "clk_ctrl_os.h"
#include "esp_private/periph_ctrl.h"
#include "esp_private/esp_clk.h"
#include "esp_private/gpio.h"
#include "esp_private/esp_gpio_reserve.h"
#include "driver/twai.h"
#include "p4_twai_priority.h"
#include "p4_twai_diag.h"
#include "esp_timer.h"
#include "soc/soc_caps.h"
#include "soc/soc.h"
#include "soc/io_mux_reg.h"
#include "soc/twai_periph.h"
#include "hal/twai_hal.h"
#include "hal/twai_ll.h"
#include "esp_rom_gpio.h"
#if SOC_TWAI_SUPPORT_SLEEP_RETENTION
#include "esp_private/sleep_retention.h"
#endif

/* ---------------------------- Definitions --------------------------------- */
//Internal Macros
#define TWAI_TAG "TWAI"
#define TWAI_CHECK(cond, ret_val) ({                                        \
            if (!(cond)) {                                                  \
                return (ret_val);                                           \
            }                                                               \
})

#define TWAI_SET_FLAG(var, mask)    ((var) |= (mask))
#define TWAI_RESET_FLAG(var, mask)  ((var) &= ~(mask))

#ifdef CONFIG_TWAI_ISR_IN_IRAM
#define TWAI_MALLOC_CAPS    (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
#else
#define TWAI_MALLOC_CAPS    MALLOC_CAP_DEFAULT
#endif  //CONFIG_TWAI_ISR_IN_IRAM

#define DRIVER_DEFAULT_INTERRUPTS   0xE7        //Exclude data overrun (bit[3]) and brp_div (bit[4])

#define ALERT_LOG_LEVEL_WARNING     TWAI_ALERT_ARB_LOST  //Alerts above and including this level use ESP_LOGW
#define ALERT_LOG_LEVEL_ERROR       TWAI_ALERT_TX_FAILED //Alerts above and including this level use ESP_LOGE

#if !SOC_RCC_IS_INDEPENDENT
#define TWAI_RCC_ATOMIC() PERIPH_RCC_ATOMIC()
#else
#define TWAI_RCC_ATOMIC()
#endif

#if SOC_PERIPH_CLK_CTRL_SHARED
#define TWAI_PERI_ATOMIC() PERIPH_RCC_ATOMIC()
#else
#define TWAI_PERI_ATOMIC()
#endif

#define TWAI_USE_RETENTION_LINK  (SOC_TWAI_SUPPORT_SLEEP_RETENTION && CONFIG_PM_POWER_DOWN_PERIPHERAL_IN_LIGHT_SLEEP)

/* ------------------ Typedefs, structures, and variables ------------------- */

//Control structure for TWAI driver
typedef struct twai_obj_t {
    int controller_id;
    gpio_num_t tx_io;
    gpio_num_t rx_io;
    gpio_num_t clkout_io;
    gpio_num_t bus_off_io;
    twai_hal_context_t *hal;  // hal context
    //Control and status members
    twai_state_t state;
    twai_mode_t mode;
    uint32_t rx_missed_count;
    uint32_t rx_overrun_count;
    uint32_t tx_failed_count;
    uint32_t arb_lost_count;
    uint32_t bus_error_count;
    intr_handle_t isr_handle;
    //TX and RX
    QueueHandle_t tx_queue;
    QueueHandle_t rx_queue;
    int tx_msg_count;
    int rx_msg_count;
    //Alerts
    SemaphoreHandle_t alert_semphr;
    uint32_t alerts_enabled;
    uint32_t alerts_triggered;
    //Power Management Lock
    esp_pm_lock_handle_t pm_lock;
    portMUX_TYPE spinlock;
} twai_obj_t;

static twai_handle_t g_twai_objs[SOC_TWAI_CONTROLLER_NUM];
static portMUX_TYPE g_spinlock = portMUX_INITIALIZER_UNLOCKED;

// Native RX epochs belong to the controller lock. Tokens travel with queue
// items; a dropped boundary advances observed but can never advance delivered.
// Only a subsequent latest, successfully dequeued MUX2 resynchronizes periodic
// work. Ordinary queued frames do not affect this state.
typedef struct {
    twai_hal_frame_t frame;
    uint32_t boundary;
    uint32_t mux1Sequence;
    uint64_t observedUs;
} p4_twai_rx_item_t;
typedef struct {
    uint32_t observed;
    uint32_t delivered;
    uint8_t mux;
    uint32_t latestQueuedMux1, completedMux1;
    p4_twai_rx_metadata_t deliveredMeta;
} p4_twai_rx_boundary_t;
static DRAM_ATTR p4_twai_rx_boundary_t s_p4_rx_boundary[SOC_TWAI_CONTROLLER_NUM];

static uint32_t p4_twai_boundary_advance(twai_obj_t *obj, uint8_t mux)
{
    p4_twai_rx_boundary_t *rx = &s_p4_rx_boundary[obj->controller_id];
    if (++rx->observed == 0) ++rx->observed;
    rx->mux = mux;
    if (mux == 0xff) { rx->latestQueuedMux1 = 0; rx->completedMux1 = 0; }
    return rx->observed;
}

static void p4_twai_boundary_reset(twai_obj_t *obj)
{
    (void)p4_twai_boundary_advance(obj, 0xff);
    s_p4_rx_boundary[obj->controller_id].delivered = 0;
    memset(&s_p4_rx_boundary[obj->controller_id].deliveredMeta, 0,
           sizeof(p4_twai_rx_metadata_t));
}

static uint32_t p4_twai_boundary_observe(twai_obj_t *obj, twai_hal_frame_t *frame)
{
    if (frame->dlc != 8) return 0;
    twai_frame_header_t header = {0};
    uint8_t data[8] = {0};
    twai_hal_parse_frame(obj->hal, frame, &header, data, sizeof(data));
    if (header.id != 0x3FD || header.ide || header.rtr || header.dlc != 8 ||
        (data[0] & 7) > 2) return 0;
    return p4_twai_boundary_advance(obj, data[0] & 7);
}

static bool p4_twai_periodic_ready_locked(twai_obj_t *obj)
{
    const p4_twai_rx_boundary_t *rx = &s_p4_rx_boundary[obj->controller_id];
    return rx->observed != 0 && rx->observed == rx->delivered && rx->mux == 2;
}

static void p4_twai_rx_drain(twai_obj_t *obj, BaseType_t *task_woken,
                             int *alert_req, bool from_isr);

// P4 R79 priority state: fixed internal-RAM storage, protected by each driver's
// spinlock. No application locks, callbacks, allocation, or FIFO reset in ISR.
typedef struct {
    bool pending;
    twai_hal_frame_t frame;
    p4_twai_priority_guard_t guard;
    P4TwaiTxIdentity request;
    uint32_t requestSequence;
    uint32_t rxBoundary; // Captured at periodic admission, never refreshed in-place.
} p4_twai_priority_slot_t;
static DRAM_ATTR p4_twai_priority_slot_t s_p4_priority[SOC_TWAI_CONTROLLER_NUM];

static P4TwaiTxIdentity p4_twai_tx_identity(twai_obj_t *obj, twai_hal_frame_t *frame, uint8_t source)
{
    P4TwaiTxIdentity tx = {0};
    twai_frame_header_t header = {0};
    twai_hal_parse_frame(obj->hal, frame, &header, tx.data, sizeof(tx.data));
    tx.identifier = header.id;
    tx.dlc = header.dlc;
    tx.flags = (header.ide ? 1 : 0) | (header.rtr ? 2 : 0);
    tx.source = source;
    return tx;
}

static uint8_t p4_twai_r79_source(const p4_twai_priority_guard_t *guard)
{
    return (guard->source == P4_TWAI_TX_SOURCE_R79_IMMEDIATE ||
            guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC)
            ? guard->source : P4_TWAI_TX_SOURCE_R79_UNKNOWN;
}

static void p4_twai_load(twai_obj_t *obj, twai_hal_frame_t *frame, uint8_t source, const P4TwaiTxIdentity *request)
{
    P4TwaiTxIdentity tx = request ? *request : p4_twai_tx_identity(obj, frame, source);
    twai_hal_set_tx_buffer_and_transmit(obj->hal, frame, 0);
    // The native lock prevents ECC/complete observation between load and shadow.
    p4TwaiDiagTxLoaded(obj->controller_id, &tx);
}

static P4TwaiTxIdentity p4_twai_new_request(twai_obj_t *obj, twai_hal_frame_t *frame,
                                         const p4_twai_priority_guard_t *guard)
{
    p4_twai_priority_slot_t *slot = &s_p4_priority[obj->controller_id];
    P4TwaiTxIdentity tx = p4_twai_tx_identity(obj, frame, p4_twai_r79_source(guard));
    if (++slot->requestSequence == 0) ++slot->requestSequence;
    tx.requestId = slot->requestSequence;
    tx.rxSequence = guard->rx_sequence;
    tx.rxObservedUs = guard->rx_observed_us;
    tx.rxDequeuedUs = guard->rx_dequeued_us;
    tx.queuedUs = (uint64_t)esp_timer_get_time();
    p4TwaiDiagTxQueued(obj->controller_id, &tx);
    return tx;
}

static uint8_t p4_twai_priority_guard_reason(const p4_twai_priority_guard_t *guard)
{
    if (__atomic_load_n(guard->administrative_hold, __ATOMIC_ACQUIRE))
        return P4_TWAI_TX_REASON_HOLD;
    if (__atomic_load_n(guard->generation, __ATOMIC_ACQUIRE) != guard->expected_generation)
        return P4_TWAI_TX_REASON_GENERATION;
    if (guard->cancel_generation &&
        __atomic_load_n(guard->cancel_generation, __ATOMIC_ACQUIRE) != guard->expected_cancel_generation)
        return P4_TWAI_TX_REASON_CANCEL_GENERATION;
    if (guard->retry_generation &&
        __atomic_load_n(guard->retry_generation, __ATOMIC_ACQUIRE) != guard->expected_retry_generation)
        return P4_TWAI_TX_REASON_CANCEL_GENERATION;
    const uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
    if (guard->has_deadline && (int32_t)(now_ms - guard->deadline_ms) > 0)
        return P4_TWAI_TX_REASON_DEADLINE;
    if (guard->permission_deadline_ms) {
        const uint32_t permission_deadline = __atomic_load_n(guard->permission_deadline_ms, __ATOMIC_ACQUIRE);
        if ((int32_t)(now_ms - permission_deadline) > 0)
            return P4_TWAI_TX_REASON_DEADLINE;
        // Renewal is a live publication. Never let it mask revocation that
        // occurred after the first authority reads above.
        if (__atomic_load_n(guard->administrative_hold, __ATOMIC_ACQUIRE))
            return P4_TWAI_TX_REASON_HOLD;
        if (__atomic_load_n(guard->generation, __ATOMIC_ACQUIRE) != guard->expected_generation)
            return P4_TWAI_TX_REASON_GENERATION;
        if (guard->cancel_generation &&
            __atomic_load_n(guard->cancel_generation, __ATOMIC_ACQUIRE) != guard->expected_cancel_generation)
            return P4_TWAI_TX_REASON_CANCEL_GENERATION;
        if (guard->retry_generation &&
            __atomic_load_n(guard->retry_generation, __ATOMIC_ACQUIRE) != guard->expected_retry_generation)
            return P4_TWAI_TX_REASON_CANCEL_GENERATION;
    }
    return P4_TWAI_TX_REASON_NONE;
}

static bool p4_twai_priority_guard_valid(const p4_twai_priority_guard_t *guard)
{
    return p4_twai_priority_guard_reason(guard) == P4_TWAI_TX_REASON_NONE;
}

static void p4_twai_priority_clear(twai_obj_t *obj, uint8_t reason)
{
    p4_twai_priority_slot_t *slot = &s_p4_priority[obj->controller_id];
    if (slot->pending) {
        if (reason != P4_TWAI_TX_REASON_NONE) {
            p4TwaiDiagTxCancelled(obj->controller_id, &slot->request, reason);
        }
        obj->tx_msg_count--;
    }
    const uint32_t sequence = slot->requestSequence;
    memset(slot, 0, sizeof(*slot));
    slot->requestSequence = sequence;
}

static bool p4_twai_priority_pending(twai_obj_t *obj)
{
    p4_twai_priority_slot_t *slot = &s_p4_priority[obj->controller_id];
    if (slot->pending) {
        uint8_t reason = p4_twai_priority_guard_reason(&slot->guard);
        if (reason == P4_TWAI_TX_REASON_NONE &&
            slot->guard.source == P4_TWAI_TX_SOURCE_R79_PERIODIC &&
            (!p4_twai_periodic_ready_locked(obj) ||
             slot->rxBoundary != s_p4_rx_boundary[obj->controller_id].observed))
            reason = P4_TWAI_TX_REASON_RX_BOUNDARY;
        if (reason != P4_TWAI_TX_REASON_NONE) p4_twai_priority_clear(obj, reason);
    }
    return slot->pending;
}

/* -------------------- Sleep Retention ------------------------ */
#if TWAI_USE_RETENTION_LINK
static esp_err_t s_twai_create_sleep_retention_link_cb(void *obj);
#endif

/* -------------------- Interrupt and Alert Handlers ------------------------ */

static void twai_alert_handler(twai_obj_t *p_twai_obj, uint32_t alert_code, int *alert_req)
{
    if (p_twai_obj->alerts_enabled & alert_code) {
        //Signify alert has occurred
        TWAI_SET_FLAG(p_twai_obj->alerts_triggered, alert_code);
        *alert_req = 1;
#ifndef CONFIG_TWAI_ISR_IN_IRAM     //Only log if ISR is not in IRAM
        if (p_twai_obj->alerts_enabled & TWAI_ALERT_AND_LOG) {
            if (alert_code >= ALERT_LOG_LEVEL_ERROR) {
                ESP_EARLY_LOGE(TWAI_TAG, "Alert %" PRIu32, alert_code);
            } else if (alert_code >= ALERT_LOG_LEVEL_WARNING) {
                ESP_EARLY_LOGW(TWAI_TAG, "Alert %" PRIu32, alert_code);
            } else {
                ESP_EARLY_LOGI(TWAI_TAG, "Alert %" PRIu32, alert_code);
            }
        }
#endif  //CONFIG_TWAI_ISR_IN_IRAM
    }
}

/* Observe successful native FIFO reads before queue admission. This is hook
 * order, not physical wire order relative to the earlier HAL ECC callback. */
static inline void p4_twai_capture_rx(twai_obj_t *obj, twai_hal_frame_t *frame)
{
    if (!p4TwaiDiagRxCaptureEnabledFromIsr(obj->controller_id)) return;
    if (frame->dlc > 8) {
        p4TwaiDiagRxFromIsr(obj->controller_id, 0, frame->dlc, 0, NULL);
        return;
    }
    twai_frame_header_t header = {0};
    uint8_t data[8] = {0};
    twai_hal_parse_frame(obj->hal, frame, &header, data, sizeof(data));
    p4TwaiDiagRxFromIsr(obj->controller_id, header.id, header.dlc,
                      (header.ide ? 1 : 0) | (header.rtr ? 2 : 0), data);
}

static void p4_twai_rx_drain(twai_obj_t *p_twai_obj, BaseType_t *task_woken,
                             int *alert_req, bool from_isr)
{
#ifdef SOC_TWAI_SUPPORTS_RX_STATUS
    uint32_t msg_count = twai_hal_get_rx_msg_count(p_twai_obj->hal);

    for (uint32_t i = 0; i < msg_count; i++) {
        twai_hal_frame_t frame;
        if (twai_hal_read_rx_fifo(p_twai_obj->hal, &frame)) {
            //Valid frame copied from RX buffer
            p4_twai_capture_rx(p_twai_obj, &frame);
            p4_twai_rx_item_t item = { .frame = frame,
                .boundary = p4_twai_boundary_observe(p_twai_obj, &frame) };
            if (item.boundary && s_p4_rx_boundary[p_twai_obj->controller_id].mux == 1) {
                item.mux1Sequence = item.boundary;
                item.observedUs = (uint64_t)esp_timer_get_time();
            }
            const BaseType_t queued = from_isr
                ? xQueueSendFromISR(p_twai_obj->rx_queue, &item, task_woken)
                : xQueueSend(p_twai_obj->rx_queue, &item, 0);
            if (queued == pdTRUE) {
                if (item.mux1Sequence)
                    s_p4_rx_boundary[p_twai_obj->controller_id].latestQueuedMux1 = item.mux1Sequence;
                p_twai_obj->rx_msg_count++;
                twai_alert_handler(p_twai_obj, TWAI_ALERT_RX_DATA, alert_req);
            } else {    //Failed to send to queue
                p_twai_obj->rx_missed_count++;
                twai_alert_handler(p_twai_obj, TWAI_ALERT_RX_QUEUE_FULL, alert_req);
            }
        } else {    //Failed to read from RX buffer because message is overrun
            p_twai_obj->rx_overrun_count++;
            (void)p4_twai_boundary_advance(p_twai_obj, 0xff);
            twai_alert_handler(p_twai_obj, TWAI_ALERT_RX_FIFO_OVERRUN, alert_req);
        }
    }
#else   //SOC_TWAI_SUPPORTS_RX_STATUS
    uint32_t msg_count = twai_hal_get_rx_msg_count(p_twai_obj->hal);
    bool overrun = false;
    //Clear all valid RX frames
    for (int i = 0; i < msg_count; i++) {
        twai_hal_frame_t frame;
        if (twai_hal_read_rx_fifo(p_twai_obj->hal, &frame)) {
            //Valid frame copied from RX buffer
            p4_twai_capture_rx(p_twai_obj, &frame);
            p4_twai_rx_item_t item = { .frame = frame,
                .boundary = p4_twai_boundary_observe(p_twai_obj, &frame) };
            if (item.boundary && s_p4_rx_boundary[p_twai_obj->controller_id].mux == 1) {
                item.mux1Sequence = item.boundary;
                item.observedUs = (uint64_t)esp_timer_get_time();
            }
            const BaseType_t queued = from_isr
                ? xQueueSendFromISR(p_twai_obj->rx_queue, &item, task_woken)
                : xQueueSend(p_twai_obj->rx_queue, &item, 0);
            if (queued == pdTRUE) {
                if (item.mux1Sequence)
                    s_p4_rx_boundary[p_twai_obj->controller_id].latestQueuedMux1 = item.mux1Sequence;
                p_twai_obj->rx_msg_count++;
                twai_alert_handler(p_twai_obj, TWAI_ALERT_RX_DATA, alert_req);
            } else {
                p_twai_obj->rx_missed_count++;
                twai_alert_handler(p_twai_obj, TWAI_ALERT_RX_QUEUE_FULL, alert_req);
            }
        } else {
            overrun = true;
            break;
        }
    }
    //All remaining frames are treated as overrun. Clear them all
    if (overrun) {
        (void)p4_twai_boundary_advance(p_twai_obj, 0xff);
        p_twai_obj->rx_overrun_count += twai_hal_clear_rx_fifo_overrun(p_twai_obj->hal);
        twai_alert_handler(p_twai_obj, TWAI_ALERT_RX_FIFO_OVERRUN, alert_req);
    }
#endif  //SOC_TWAI_SUPPORTS_RX_STATUS
}

static inline void twai_handle_rx_buffer_frames(twai_obj_t *obj, BaseType_t *task_woken, int *alert_req)
{
    p4_twai_rx_drain(obj, task_woken, alert_req, true);
}

// Load the next slot only. Callers must have retired any actual TX completion
// once; RX/task kicks never decrement an active frame or preempt hardware.
static void p4_twai_dispatch_idle(twai_obj_t *p_twai_obj, BaseType_t *task_woken,
                                  int *alert_req, bool from_isr)
{
    if (p_twai_obj->state != TWAI_STATE_RUNNING ||
        twai_hal_check_state_flags(p_twai_obj->hal,
            TWAI_HAL_STATE_FLAG_BUS_OFF | TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED)) return;
    // Priority owns the next hardware slot; an already active frame is never
    // aborted. Invalid entries are retired before consulting the ordinary FIFO.
    const bool service_immediate_rx = s_p4_priority[p_twai_obj->controller_id].pending &&
        s_p4_priority[p_twai_obj->controller_id].guard.source == P4_TWAI_TX_SOURCE_R79_IMMEDIATE &&
        s_p4_priority[p_twai_obj->controller_id].guard.rx_sequence != 0;
    const bool priority_pending = p4_twai_priority_pending(p_twai_obj);
    if (!twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_BUS_OFF)
            && p_twai_obj->state == TWAI_STATE_RUNNING) {
        if (priority_pending) {
            p4_twai_priority_slot_t *slot = &s_p4_priority[p_twai_obj->controller_id];
            // Frames arriving during drain/guard work are still unclassified.
            // Retain the request and FIFO until RX or the task-side kick retries.
            if (slot->guard.source == P4_TWAI_TX_SOURCE_R79_PERIODIC &&
                twai_hal_get_rx_msg_count(p_twai_obj->hal) != 0) return;
            twai_hal_frame_t frame = slot->frame;
            const uint8_t source = p4_twai_r79_source(&slot->guard);
            const P4TwaiTxIdentity request = slot->request;
            p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_NONE);
            p4_twai_load(p_twai_obj, &frame, source, &request);
            p_twai_obj->tx_msg_count++;
            goto rx_progress;
        }
        if (p_twai_obj->tx_msg_count > 0 && p_twai_obj->tx_queue != NULL) {
            twai_hal_frame_t frame;
            int res = from_isr
                ? xQueueReceiveFromISR(p_twai_obj->tx_queue, &frame, task_woken)
                : xQueueReceive(p_twai_obj->tx_queue, &frame, 0);
            assert(res == pdTRUE);
            (void)res;
            p4_twai_load(p_twai_obj, &frame, P4_TWAI_TX_SOURCE_UNKNOWN, NULL);
            goto rx_progress;
        }
    }
    twai_alert_handler(p_twai_obj, TWAI_ALERT_TX_IDLE, alert_req);
rx_progress:
    // The origin tag is metadata, not an IMMEDIATE validity fence. Preserve
    // bounded RX service and wakeups after loading (or retiring) the request.
    if (service_immediate_rx)
        p4_twai_rx_drain(p_twai_obj, task_woken, alert_req, from_isr);
}

// Inspect hardware RX too: software queue state is not a MUX boundary fence.
// Work is bounded to the HAL count snapshot, never an unbounded drain-to-empty.
bool p4_twai_r79_periodic_ready_v2(twai_handle_t handle)
{
    if (!handle) return false;
    int alert_req = 0;
    portENTER_CRITICAL(&handle->spinlock);
    bool ready = false;
    if (handle->state == TWAI_STATE_RUNNING) {
        p4_twai_rx_drain(handle, NULL, &alert_req, false);
        p4_twai_dispatch_idle(handle, NULL, &alert_req, false);
        ready = p4_twai_periodic_ready_locked(handle) &&
                twai_hal_get_rx_msg_count(handle->hal) == 0;
    }
    portEXIT_CRITICAL(&handle->spinlock);
    if (alert_req) xSemaphoreGive(handle->alert_semphr);
    return ready;
}

bool p4_twai_rx_metadata_v2(twai_handle_t handle, p4_twai_rx_metadata_t *out)
{
    if (!handle || !out) return false;
    portENTER_CRITICAL(&handle->spinlock);
    *out = s_p4_rx_boundary[handle->controller_id].deliveredMeta;
    portEXIT_CRITICAL(&handle->spinlock);
    return out->sequence != 0;
}

bool p4_twai_r79_input_current_v2(twai_handle_t handle, uint32_t sequence)
{
    if (!handle || !sequence) return true;
    int alert_req = 0;
    portENTER_CRITICAL(&handle->spinlock);
    if (handle->state == TWAI_STATE_RUNNING)
        p4_twai_rx_drain(handle, NULL, &alert_req, false);
    const uint32_t latest = s_p4_rx_boundary[handle->controller_id].latestQueuedMux1;
    const bool current = latest == 0 || latest == sequence;
    portEXIT_CRITICAL(&handle->spinlock);
    if (alert_req) xSemaphoreGive(handle->alert_semphr);
    return current;
}

void p4_twai_r79_input_done_v2(twai_handle_t handle, uint32_t sequence)
{
    if (!handle || !sequence) return;
    int alert_req = 0;
    portENTER_CRITICAL(&handle->spinlock);
    p4_twai_rx_boundary_t *rx = &s_p4_rx_boundary[handle->controller_id];
    if (rx->latestQueuedMux1 == sequence) rx->completedMux1 = sequence;
    p4_twai_dispatch_idle(handle, NULL, &alert_req, false);
    portEXIT_CRITICAL(&handle->spinlock);
    if (alert_req) xSemaphoreGive(handle->alert_semphr);
}

static inline void twai_handle_tx_buffer_frame(twai_obj_t *p_twai_obj, bool tx_success, BaseType_t *task_woken, int *alert_req)
{
    p4TwaiDiagTxRetire(p_twai_obj->controller_id,
        tx_success ? P4_TWAI_TX_REASON_SUCCESS : P4_TWAI_TX_REASON_FAILED);
    //Handle previously transmitted frame
    if (tx_success) {
        twai_alert_handler(p_twai_obj, TWAI_ALERT_TX_SUCCESS, alert_req);
    } else {
        p_twai_obj->tx_failed_count++;
        twai_alert_handler(p_twai_obj, TWAI_ALERT_TX_FAILED, alert_req);
    }

    //Update TX message count
    p_twai_obj->tx_msg_count--;
    assert(p_twai_obj->tx_msg_count >= 0);      //Sanity check

    if (s_p4_priority[p_twai_obj->controller_id].pending &&
        s_p4_priority[p_twai_obj->controller_id].guard.source == P4_TWAI_TX_SOURCE_R79_PERIODIC)
        p4_twai_rx_drain(p_twai_obj, task_woken, alert_req, true);
    p4_twai_dispatch_idle(p_twai_obj, task_woken, alert_req, true);
}

static void twai_intr_handler_main(void *arg)
{
    twai_obj_t *p_twai_obj = (twai_obj_t *)arg;
    BaseType_t task_woken = pdFALSE;
    int alert_req = 0;
    uint32_t events;
    portENTER_CRITICAL_ISR(&p_twai_obj->spinlock);
    events = twai_hal_get_events(p_twai_obj->hal);    //Get the events that triggered the interrupt

#if defined(CONFIG_TWAI_ERRATA_FIX_RX_FRAME_INVALID) || defined(CONFIG_TWAI_ERRATA_FIX_RX_FIFO_CORRUPT)
    if (events & TWAI_HAL_EVENT_NEED_PERIPH_RESET) {
        p4_twai_boundary_reset(p_twai_obj);
        twai_hal_prepare_for_reset(p_twai_obj->hal);
        TWAI_RCC_ATOMIC() {
            twai_ll_reset_register(p_twai_obj->controller_id);
        }
        twai_hal_recover_from_reset(p_twai_obj->hal);
        p_twai_obj->rx_missed_count += twai_hal_get_reset_lost_rx_cnt(p_twai_obj->hal);
        twai_alert_handler(p_twai_obj, TWAI_ALERT_PERIPH_RESET, &alert_req);
    }
#endif
    if (events & TWAI_HAL_EVENT_RX_BUFF_FRAME) {
        //Note: This event will never occur if there is a periph reset event
        twai_handle_rx_buffer_frames(p_twai_obj, &task_woken, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_TX_BUFF_FREE) {
        twai_handle_tx_buffer_frame(p_twai_obj, (events & TWAI_HAL_EVENT_TX_SUCCESS), &task_woken, &alert_req);
    } else if (events & TWAI_HAL_EVENT_RX_BUFF_FRAME) {
        // A previous periodic dispatch may be waiting for RX classification.
        // Even if it is now invalid, resume any preserved ordinary FIFO.
        p4_twai_dispatch_idle(p_twai_obj, &task_woken, &alert_req, true);
    }

    //Handle events that only require alerting (i.e. no handler)
    if (events & TWAI_HAL_EVENT_BUS_OFF) {
        twai_ll_set_mode(p_twai_obj->hal->dev, true, false, false);  //Freeze TEC/REC by entering LOM
        p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_BUS_OFF);
        p4TwaiDiagTxRetire(p_twai_obj->controller_id, P4_TWAI_TX_REASON_BUS_OFF);
        p_twai_obj->state = TWAI_STATE_BUS_OFF;
        twai_alert_handler(p_twai_obj, TWAI_ALERT_BUS_OFF, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_BUS_RECOV_CPLT) {
        //Back to STOPPED state after recovered, for cautious engineering strategy
        twai_ll_enter_reset_mode(p_twai_obj->hal->dev);
        p_twai_obj->state = TWAI_STATE_STOPPED;
        twai_alert_handler(p_twai_obj, TWAI_ALERT_BUS_RECOVERED, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_BUS_ERR) {
        p_twai_obj->bus_error_count++;
        twai_alert_handler(p_twai_obj, TWAI_ALERT_BUS_ERROR, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_ARB_LOST) {
        p_twai_obj->arb_lost_count++;
        twai_alert_handler(p_twai_obj, TWAI_ALERT_ARB_LOST, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_BUS_RECOV_PROGRESS) {
        //Bus-recovery in progress. TEC has dropped below error warning limit
        twai_alert_handler(p_twai_obj, TWAI_ALERT_RECOVERY_IN_PROGRESS, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_ERROR_PASSIVE) {
        //Entered error passive
        twai_alert_handler(p_twai_obj, TWAI_ALERT_ERR_PASS, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_ERROR_ACTIVE) {
        //Returned to error active
        twai_alert_handler(p_twai_obj, TWAI_ALERT_ERR_ACTIVE, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_ERROR_WARNING) {
        //TEC or REC surpassed error warning limit
        twai_alert_handler(p_twai_obj, TWAI_ALERT_ABOVE_ERR_WARN, &alert_req);
    }
    if (events & TWAI_HAL_EVENT_BELOW_EWL) {
        //TEC and REC are both below error warning
        twai_alert_handler(p_twai_obj, TWAI_ALERT_BELOW_ERR_WARN, &alert_req);
    }

    portEXIT_CRITICAL_ISR(&p_twai_obj->spinlock);

    if (p_twai_obj->alert_semphr != NULL && alert_req) {
        //Give semaphore if alerts were triggered
        xSemaphoreGiveFromISR(p_twai_obj->alert_semphr, &task_woken);
    }
    if (task_woken == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

/* -------------------------- Helper functions  ----------------------------- */

static void twai_configure_gpio(twai_obj_t *p_obj)
{
    uint8_t controller_id = p_obj->controller_id;
    assert(GPIO_IS_VALID_OUTPUT_GPIO(p_obj->tx_io));    //coverity check
    uint64_t gpio_mask = BIT64(p_obj->tx_io);

    //Set RX pin
    gpio_func_sel(p_obj->rx_io, PIN_FUNC_GPIO);
    gpio_input_enable(p_obj->rx_io);
    esp_rom_gpio_connect_in_signal(p_obj->rx_io, twai_controller_periph_signals.controllers[controller_id].rx_sig, false);

    //Set TX pin
    gpio_func_sel(p_obj->tx_io, PIN_FUNC_GPIO);
    esp_rom_gpio_connect_out_signal(p_obj->tx_io, twai_controller_periph_signals.controllers[controller_id].tx_sig, false, false);

    //Configure output clock pin (Optional)
    if (GPIO_IS_VALID_OUTPUT_GPIO(p_obj->clkout_io)) {
        gpio_mask |= BIT64(p_obj->clkout_io);
        gpio_func_sel(p_obj->clkout_io, PIN_FUNC_GPIO);
        esp_rom_gpio_connect_out_signal(p_obj->clkout_io, twai_controller_periph_signals.controllers[controller_id].clk_out_sig, false, false);
    }

    //Configure bus status pin (Optional)
    if (GPIO_IS_VALID_OUTPUT_GPIO(p_obj->bus_off_io)) {
        gpio_mask |= BIT64(p_obj->bus_off_io);
        gpio_func_sel(p_obj->bus_off_io, PIN_FUNC_GPIO);
        esp_rom_gpio_connect_out_signal(p_obj->bus_off_io, twai_controller_periph_signals.controllers[controller_id].bus_off_sig, false, false);
    }

    uint64_t busy_mask = esp_gpio_reserve(gpio_mask);
    uint64_t conflict_mask = busy_mask & gpio_mask;
    for (; conflict_mask > 0;) {
        uint8_t pos = __builtin_ctzll(conflict_mask);
        conflict_mask &= ~(1ULL << pos);
        ESP_LOGW(TWAI_TAG, "GPIO %d is not usable, maybe used by others", pos);
    }
}

static void twai_release_gpio(twai_obj_t *p_obj)
{
    assert(p_obj);
    assert(GPIO_IS_VALID_OUTPUT_GPIO(p_obj->tx_io));    //coverity check
    uint64_t gpio_mask = BIT64(p_obj->tx_io);

    esp_rom_gpio_connect_in_signal(GPIO_MATRIX_CONST_ONE_INPUT, twai_controller_periph_signals.controllers[p_obj->controller_id].rx_sig, false);
    gpio_output_disable(p_obj->tx_io);
    if (GPIO_IS_VALID_OUTPUT_GPIO(p_obj->clkout_io)) {
        gpio_mask |= BIT64(p_obj->clkout_io);
        gpio_output_disable(p_obj->clkout_io);
    }
    if (GPIO_IS_VALID_OUTPUT_GPIO(p_obj->bus_off_io)) {
        gpio_mask |= BIT64(p_obj->bus_off_io);
        gpio_output_disable(p_obj->bus_off_io);
    }
    esp_gpio_revoke(gpio_mask);
}

static void twai_free_driver_obj(twai_obj_t *p_obj)
{
    //Free driver object and any dependent SW resources it uses (queues, semaphores, interrupts, PM locks etc)
#if CONFIG_PM_ENABLE
    if (p_obj->pm_lock != NULL) {
        ESP_ERROR_CHECK(esp_pm_lock_delete(p_obj->pm_lock));
    }
#endif //CONFIG_PM_ENABLE
    if (p_obj->isr_handle) {
        ESP_ERROR_CHECK(esp_intr_free(p_obj->isr_handle));
    }
    //Delete queues and semaphores
    if (p_obj->tx_queue != NULL) {
        vQueueDeleteWithCaps(p_obj->tx_queue);
    }
    if (p_obj->rx_queue != NULL) {
        vQueueDeleteWithCaps(p_obj->rx_queue);
    }
    if (p_obj->alert_semphr != NULL) {
        vSemaphoreDeleteWithCaps(p_obj->alert_semphr);
    }

#if TWAI_USE_RETENTION_LINK
    const periph_retention_module_t retention_id = twai_reg_retention_info[p_obj->controller_id].module_id;
    if (sleep_retention_is_module_created(retention_id)) {
        assert(sleep_retention_is_module_inited(retention_id));
        sleep_retention_module_free(retention_id);
    }
    if (sleep_retention_is_module_inited(retention_id)) {
        sleep_retention_module_deinit(retention_id);
    }

#endif

    heap_caps_free(p_obj);
}

static esp_err_t twai_alloc_driver_obj(const twai_general_config_t *g_config, twai_clock_source_t clk_src, int controller_id,  twai_obj_t **p_twai_obj_ret)
{
    //Allocate driver object and any dependent SW resources it uses (queues, semaphores, interrupts, PM locks etc)
    esp_err_t ret;

    //Create a TWAI driver object
    twai_obj_t *p_obj = heap_caps_calloc(1, sizeof(twai_obj_t) + twai_hal_get_mem_requirment(), TWAI_MALLOC_CAPS);
    if (p_obj == NULL) {
        return ESP_ERR_NO_MEM;
    }
    if (g_config->tx_queue_len > 0) {
        p_obj->tx_queue = xQueueCreateWithCaps(g_config->tx_queue_len, sizeof(twai_hal_frame_t), TWAI_MALLOC_CAPS);
    }
    p_obj->rx_queue = xQueueCreateWithCaps(g_config->rx_queue_len, sizeof(p4_twai_rx_item_t), TWAI_MALLOC_CAPS);
    p_obj->alert_semphr = xSemaphoreCreateBinaryWithCaps(TWAI_MALLOC_CAPS);
    if ((g_config->tx_queue_len > 0 && p_obj->tx_queue == NULL) || p_obj->rx_queue == NULL || p_obj->alert_semphr == NULL) {
        ret = ESP_ERR_NO_MEM;
        goto err;
    }
    //Allocate interrupt
    ret = esp_intr_alloc(twai_controller_periph_signals.controllers[controller_id].irq_id,
                         g_config->intr_flags | ESP_INTR_FLAG_INTRDISABLED,
                         twai_intr_handler_main,
                         p_obj,
                         &p_obj->isr_handle);
    if (ret != ESP_OK) {
        goto err;
    }

    p_obj->controller_id = controller_id;
    p_obj->hal = (twai_hal_context_t *)(p_obj + 1);   //hal context is place at end of driver context

#if CONFIG_PM_ENABLE
#if SOC_TWAI_CLK_SUPPORT_APB
    // DFS can change APB frequency. So add lock to prevent sleep and APB freq from changing
    if (clk_src == TWAI_CLK_SRC_APB) {
        // TODO: pm_lock name should also reflect the controller ID
        ret = esp_pm_lock_create(ESP_PM_APB_FREQ_MAX, 0, "twai", &(p_obj->pm_lock));
        if (ret != ESP_OK) {
            goto err;
        }
    }
#else // XTAL
    // XTAL freq can be closed in light sleep, so we need to create a lock to prevent light sleep
    ret = esp_pm_lock_create(ESP_PM_NO_LIGHT_SLEEP, 0, "twai", &(p_obj->pm_lock));
    if (ret != ESP_OK) {
        goto err;
    }
#endif //SOC_TWAI_CLK_SUPPORT_APB
#endif //CONFIG_PM_ENABLE

#if TWAI_USE_RETENTION_LINK
    sleep_retention_module_t module = twai_reg_retention_info[controller_id].module_id;
    sleep_retention_module_init_param_t init_param = {
        .cbs = {
            .create = {
                .handle = s_twai_create_sleep_retention_link_cb,
                .arg = p_obj,
            },
        },
        .depends = RETENTION_MODULE_BITMAP_INIT(CLOCK_SYSTEM)
    };
    if (sleep_retention_module_init(module, &init_param) != ESP_OK) {
        ESP_LOGW(TWAI_TAG, "init sleep retention failed for TWAI%d, power domain may be turned off during sleep", controller_id);
    }

    if (g_config->general_flags.sleep_allow_pd) {
        if (sleep_retention_module_allocate(module) != ESP_OK) {
            ESP_LOGW(TWAI_TAG, "create retention module failed, power domain can't turn off");
        }
    }
#endif

    *p_twai_obj_ret = p_obj;
    return ESP_OK;

err:
    twai_free_driver_obj(p_obj);
    return ret;
}

/* ---------------------------- Public Functions ---------------------------- */
esp_err_t twai_driver_install_v2(const twai_general_config_t *g_config, const twai_timing_config_t *t_config, const twai_filter_config_t *f_config, twai_handle_t *ret_twai)
{
    //Check arguments
    TWAI_CHECK(g_config != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(t_config != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(f_config != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(g_config->controller_id < SOC_TWAI_CONTROLLER_NUM, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(g_config->rx_queue_len > 0, ESP_ERR_INVALID_ARG);
    // assert the GPIO number is not a negative number (shift operation on a negative number is undefined)
    TWAI_CHECK(GPIO_IS_VALID_OUTPUT_GPIO(g_config->tx_io), ESP_ERR_INVALID_ARG);
    TWAI_CHECK(GPIO_IS_VALID_GPIO(g_config->rx_io), ESP_ERR_INVALID_ARG);
#ifndef CONFIG_TWAI_ISR_IN_IRAM
    TWAI_CHECK(!(g_config->intr_flags & ESP_INTR_FLAG_IRAM), ESP_ERR_INVALID_ARG);
#endif
    int controller_id = g_config->controller_id;
    TWAI_CHECK(g_twai_objs[controller_id] == NULL, ESP_ERR_INVALID_STATE);
#if !SOC_TWAI_SUPPORT_SLEEP_RETENTION
    TWAI_CHECK(!g_config->general_flags.sleep_allow_pd, ESP_ERR_INVALID_ARG);
#endif

    //Get clock source resolution
    uint32_t clock_source_hz = 0;
    twai_clock_source_t clk_src = t_config->clk_src;
    //Fall back to default clock source
    if (clk_src == 0) {
        clk_src = TWAI_CLK_SRC_DEFAULT;
    }
    esp_clk_tree_src_get_freq_hz(clk_src, ESP_CLK_TREE_SRC_FREQ_PRECISION_CACHED, &clock_source_hz);

    //Check brp validation
    uint32_t brp = t_config->brp;
    if (t_config->quanta_resolution_hz) {
        TWAI_CHECK(clock_source_hz % t_config->quanta_resolution_hz == 0, ESP_ERR_INVALID_ARG);
        brp = clock_source_hz / t_config->quanta_resolution_hz;
    }
    TWAI_CHECK(twai_ll_check_brp_validation(brp), ESP_ERR_INVALID_ARG);

    esp_err_t ret;
    twai_obj_t *p_twai_obj;

    //Create a TWAI object (including queues, semaphores, interrupts, and PM locks)
    ret = twai_alloc_driver_obj(g_config, clk_src, controller_id, &p_twai_obj);
    if (ret != ESP_OK) {
        return ret;
    }

    //Initialize flags and variables. All other members are already set to zero by twai_alloc_driver_obj()
    portMUX_INITIALIZE(&p_twai_obj->spinlock);
    p_twai_obj->state = TWAI_STATE_STOPPED;
    p_twai_obj->mode = g_config->mode;
    p_twai_obj->alerts_enabled = g_config->alerts_enabled;
    p_twai_obj->tx_io = g_config->tx_io;
    p_twai_obj->rx_io = g_config->rx_io;
    p_twai_obj->clkout_io = g_config->clkout_io;
    p_twai_obj->bus_off_io = g_config->bus_off_io;

    //Assign the TWAI object
    portENTER_CRITICAL(&g_spinlock);
    if (g_twai_objs[controller_id] == NULL) {
        g_twai_objs[controller_id] = p_twai_obj;
    } else {
        //Check if driver is already installed
        portEXIT_CRITICAL(&g_spinlock);
        ret = ESP_ERR_INVALID_STATE;
        goto err;
    }
    portEXIT_CRITICAL(&g_spinlock);

    //Enable TWAI peripheral register clock
    TWAI_RCC_ATOMIC() {
        twai_ll_enable_bus_clock(controller_id, true);
        twai_ll_reset_register(controller_id);
    }
    TWAI_PERI_ATOMIC() {
        //Enable functional clock
        twai_ll_set_clock_source(p_twai_obj->controller_id, clk_src);
        twai_ll_enable_clock(p_twai_obj->controller_id, true);
    }

    //Initialize TWAI HAL layer
    twai_hal_config_t hal_config = {
        .clock_source_hz = clock_source_hz,
        .controller_id = controller_id,
        .intr_mask = DRIVER_DEFAULT_INTERRUPTS,
        .enable_self_test = (p_twai_obj->mode == TWAI_MODE_NO_ACK),
        .enable_listen_only = (p_twai_obj->mode == TWAI_MODE_LISTEN_ONLY),
    };
    ESP_GOTO_ON_FALSE(twai_hal_init(p_twai_obj->hal, &hal_config), ESP_ERR_INVALID_STATE, err, TWAI_TAG, "hardware not in reset state");
    twai_hal_configure(p_twai_obj->hal, t_config, f_config, g_config->clkout_divider);

    //Assign GPIO and Interrupts
    twai_configure_gpio(p_twai_obj);

#if CONFIG_PM_ENABLE
    //Acquire PM lock
    if (p_twai_obj->pm_lock) {
        ESP_ERROR_CHECK(esp_pm_lock_acquire(p_twai_obj->pm_lock));     //Acquire pm_lock during the whole driver lifetime
    }
#endif //CONFIG_PM_ENABLE

    //Enable interrupt
    ESP_ERROR_CHECK(esp_intr_enable(p_twai_obj->isr_handle));

    *ret_twai = p_twai_obj;

    return ESP_OK;      //TWAI module is still in reset mode, users need to call twai_start() afterwards

err:
    twai_free_driver_obj(p_twai_obj);
    return ret;
}

esp_err_t twai_driver_install(const twai_general_config_t *g_config, const twai_timing_config_t *t_config, const twai_filter_config_t *f_config)
{
    // the handle-less driver API only supports one TWAI controller, i.e. the g_twai_objs[0]
    TWAI_CHECK(g_config->controller_id == 0, ESP_ERR_INVALID_ARG);
    return twai_driver_install_v2(g_config, t_config, f_config, &g_twai_objs[0]);
}

esp_err_t twai_driver_uninstall_v2(twai_handle_t handle)
{
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    int controller_id = handle->controller_id;
    twai_obj_t *p_twai_obj;

    portENTER_CRITICAL(&g_spinlock);
    //Check state
    if (g_twai_objs[controller_id] == NULL) {
        portEXIT_CRITICAL(&g_spinlock);
        return ESP_ERR_INVALID_STATE;
    }
    p_twai_obj = g_twai_objs[controller_id];
    if (!(p_twai_obj->state == TWAI_STATE_STOPPED || p_twai_obj->state == TWAI_STATE_BUS_OFF)) {
        portEXIT_CRITICAL(&g_spinlock);
        return ESP_ERR_INVALID_STATE;
    }
    g_twai_objs[controller_id] = NULL;
    portEXIT_CRITICAL(&g_spinlock);

    //Disable interrupt
    ESP_ERROR_CHECK(esp_intr_disable(p_twai_obj->isr_handle));

    portENTER_CRITICAL(&p_twai_obj->spinlock);
    p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_UNINSTALL);
    p4TwaiDiagTxRetire(p_twai_obj->controller_id, P4_TWAI_TX_REASON_UNINSTALL);
    portEXIT_CRITICAL(&p_twai_obj->spinlock);

    //Clear registers by reading
    twai_hal_deinit(p_twai_obj->hal);
    TWAI_PERI_ATOMIC() {
        twai_ll_enable_clock(controller_id, false);
    }
    TWAI_RCC_ATOMIC() {
        twai_ll_enable_bus_clock(controller_id, false);
    }

#if CONFIG_PM_ENABLE
    if (p_twai_obj->pm_lock) {
        //Release and delete power management lock
        ESP_ERROR_CHECK(esp_pm_lock_release(p_twai_obj->pm_lock));
    }
#endif //CONFIG_PM_ENABLE

    twai_release_gpio(p_twai_obj);
    //Free twai driver object
    twai_free_driver_obj(p_twai_obj);
    return ESP_OK;
}

esp_err_t twai_driver_uninstall(void)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_driver_uninstall_v2(g_twai_objs[0]);
}

esp_err_t twai_start_v2(twai_handle_t handle)
{
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    if (p_twai_obj->state != TWAI_STATE_STOPPED) {
        portEXIT_CRITICAL(&handle->spinlock);
        return ESP_ERR_INVALID_STATE;
    }

    //Reset RX queue, RX message count, amd TX queue
    xQueueReset(p_twai_obj->rx_queue);
    p4_twai_boundary_reset(p_twai_obj);
    if (p_twai_obj->tx_queue != NULL) {
        xQueueReset(p_twai_obj->tx_queue);
    }
    p_twai_obj->rx_msg_count = 0;
    p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_START);
    p4TwaiDiagTxRetire(p_twai_obj->controller_id, P4_TWAI_TX_REASON_START);
    p_twai_obj->tx_msg_count = 0;
    twai_hal_start(p_twai_obj->hal);

    p_twai_obj->state = TWAI_STATE_RUNNING;
    portEXIT_CRITICAL(&handle->spinlock);
    return ESP_OK;
}

esp_err_t twai_start(void)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_start_v2(g_twai_objs[0]);
}

esp_err_t twai_stop_v2(twai_handle_t handle)
{
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    //Check state
    if (p_twai_obj->state != TWAI_STATE_RUNNING) {
        portEXIT_CRITICAL(&handle->spinlock);
        return ESP_ERR_INVALID_STATE;
    }

    twai_hal_stop(p_twai_obj->hal);

    //Reset TX Queue and message count
    if (p_twai_obj->tx_queue != NULL) {
        xQueueReset(p_twai_obj->tx_queue);
    }
    p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_STOP);
    p4TwaiDiagTxRetire(p_twai_obj->controller_id, P4_TWAI_TX_REASON_STOP);
    p_twai_obj->tx_msg_count = 0;
    p_twai_obj->state = TWAI_STATE_STOPPED;

    portEXIT_CRITICAL(&handle->spinlock);
    return ESP_OK;
}

esp_err_t twai_stop(void)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_stop_v2(g_twai_objs[0]);
}

esp_err_t twai_transmit_v2(twai_handle_t handle, const twai_message_t *message, TickType_t ticks_to_wait)
{
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(message != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK((message->data_length_code <= TWAI_FRAME_MAX_DLC) || message->dlc_non_comp, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;
    twai_hal_frame_t tx_frame;
    twai_frame_header_t header = {
        .id = message->identifier,
        .dlc = message->data_length_code,
        .ide = message->extd,
        .rtr = message->rtr,
    };
    twai_hal_trans_desc_t hal_trans = {
        .frame = {
            .header = &header,
            .buffer = (uint8_t *)message->data,
            .buffer_len = message->data_length_code,
        },
        .config.retry_cnt = message->ss ? 0 : -1,
        .config.loopback = message->self,
    };
    twai_hal_format_frame(&hal_trans, &tx_frame);

    const TickType_t started = xTaskGetTickCount();
    for (;;) {
        portENTER_CRITICAL(&handle->spinlock);
        esp_err_t ret;
        if (p_twai_obj->mode == TWAI_MODE_LISTEN_ONLY) {
            ret = ESP_ERR_NOT_SUPPORTED;
        } else if (p_twai_obj->state != TWAI_STATE_RUNNING ||
                   twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_BUS_OFF)) {
            ret = ESP_ERR_INVALID_STATE;
        } else if (p4_twai_priority_pending(p_twai_obj)) {
            // Ordinary producers cannot extend the backlog ahead of R79.
            ret = ESP_ERR_TIMEOUT;
        } else if (p_twai_obj->tx_msg_count == 0) {
            p4_twai_load(p_twai_obj, &tx_frame, P4_TWAI_TX_SOURCE_UNKNOWN, NULL);
            p_twai_obj->tx_msg_count++;
            ret = ESP_OK;
        } else if (p_twai_obj->tx_queue == NULL) {
            ret = ESP_FAIL;
        } else if (xQueueSend(p_twai_obj->tx_queue, &tx_frame, 0) == pdTRUE) {
            // Queue publication and accounting are atomic with respect to both
            // ISR dispatch and priority admission (no post-enqueue handoff gap).
            p_twai_obj->tx_msg_count++;
            ret = ESP_OK;
        } else {
            portEXIT_CRITICAL(&handle->spinlock);
            if ((TickType_t)(xTaskGetTickCount() - started) >= ticks_to_wait) {
                return ESP_ERR_TIMEOUT;
            }
            // Never wait on a queue or sleep while holding the native spinlock.
            vTaskDelay(1);
            continue;
        }
        portEXIT_CRITICAL(&handle->spinlock);
        return ret;
    }
}

// State-derived ordinary MUX1 clones must never outlive their authorization in
// the FIFO and follow a newer R79. This explicit route is atomic with native
// R79 admission; generic ordinary traffic keeps the existing queue behavior.
esp_err_t p4_twai_transmit_mux1_now_v2(twai_handle_t handle, const twai_message_t *message)
{
    TWAI_CHECK(handle != NULL && message != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(message->identifier == 0x3FD && !message->extd && !message->rtr &&
               message->data_length_code == 8 && (message->data[0] & 0x07) == 1, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;
    twai_hal_frame_t tx_frame;
    twai_frame_header_t header = {
        .id = message->identifier,
        .dlc = message->data_length_code,
        .ide = message->extd,
        .rtr = message->rtr,
    };
    twai_hal_trans_desc_t hal_trans = {
        .frame = {
            .header = &header,
            .buffer = (uint8_t *)message->data,
            .buffer_len = message->data_length_code,
        },
        .config.retry_cnt = message->ss ? 0 : -1,
        .config.loopback = message->self,
    };
    twai_hal_format_frame(&hal_trans, &tx_frame);

    portENTER_CRITICAL(&handle->spinlock);
    esp_err_t ret;
    if (p_twai_obj->mode == TWAI_MODE_LISTEN_ONLY) {
        ret = ESP_ERR_NOT_SUPPORTED;
    } else if (p_twai_obj->state != TWAI_STATE_RUNNING ||
               twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_BUS_OFF)) {
        ret = ESP_ERR_INVALID_STATE;
    } else if (p4_twai_priority_pending(p_twai_obj) || p_twai_obj->tx_msg_count != 0 ||
               twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED)) {
        // Do not wait or consume the request: the producer must recompose from
        // the next fresh stock frame, not retry an old payload after R79.
        ret = ESP_ERR_TIMEOUT;
    } else {
        p4_twai_load(p_twai_obj, &tx_frame, P4_TWAI_TX_SOURCE_UNKNOWN, NULL);
        p_twai_obj->tx_msg_count++;
        ret = ESP_OK;
    }
    portEXIT_CRITICAL(&handle->spinlock);
    return ret;
}

esp_err_t p4_twai_transmit_r79_v2(twai_handle_t handle, const twai_message_t *message,
                               const p4_twai_priority_guard_t *guard)
{
    TWAI_CHECK(handle != NULL && message != NULL && guard != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(guard->generation != NULL && guard->administrative_hold != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(message->identifier == 0x3FD && !message->extd && !message->rtr &&
               message->data_length_code == 8 && (message->data[0] & 0x07) == 1, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;
    twai_hal_frame_t tx_frame;
    twai_frame_header_t header = {
        .id = message->identifier,
        .dlc = message->data_length_code,
        .ide = message->extd,
        .rtr = message->rtr,
    };
    twai_hal_trans_desc_t hal_trans = {
        .frame = {
            .header = &header,
            .buffer = (uint8_t *)message->data,
            .buffer_len = message->data_length_code,
        },
        .config.retry_cnt = message->ss ? 0 : -1,
        .config.loopback = message->self,
    };
    twai_hal_format_frame(&hal_trans, &tx_frame);

    int alert_req = 0;
    portENTER_CRITICAL(&handle->spinlock);
    // An existing PERIODIC owner, including a protected one-shot, must see
    // fresh HAL boundaries before admission decides whether it still owns TX.
    if (p_twai_obj->state == TWAI_STATE_RUNNING &&
        (guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC ||
         (s_p4_priority[p_twai_obj->controller_id].pending &&
          s_p4_priority[p_twai_obj->controller_id].guard.source == P4_TWAI_TX_SOURCE_R79_PERIODIC)))
        p4_twai_rx_drain(p_twai_obj, NULL, &alert_req, false);
    esp_err_t ret;
    if (p_twai_obj->mode == TWAI_MODE_LISTEN_ONLY) {
        ret = ESP_ERR_NOT_SUPPORTED;
    } else if (p_twai_obj->state != TWAI_STATE_RUNNING ||
               twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_BUS_OFF) ||
               !p4_twai_priority_guard_valid(guard) ||
               (guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC &&
                !p4_twai_periodic_ready_locked(p_twai_obj))) {
        ret = ESP_ERR_INVALID_STATE;
    } else if (guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC &&
               twai_hal_get_rx_msg_count(p_twai_obj->hal) != 0) {
        ret = ESP_ERR_TIMEOUT; // Unclassified residual RX, not an obsolete cycle.
    } else if (p4_twai_priority_pending(p_twai_obj)) {
        p4_twai_priority_slot_t *slot = &s_p4_priority[p_twai_obj->controller_id];
        if (!p4_twai_priority_guard_valid(guard)) {
            ret = ESP_ERR_INVALID_STATE;
        } else if (!slot->guard.preserve_pending &&
                   guard->source == P4_TWAI_TX_SOURCE_R79_IMMEDIATE &&
                   (slot->guard.source == P4_TWAI_TX_SOURCE_R79_IMMEDIATE ||
                    slot->guard.source == P4_TWAI_TX_SOURCE_R79_PERIODIC)) {
            // Replace exactly one pending request under the native lock. The
            // active controller, ordinary FIFO and message count are untouched.
            p4TwaiDiagTxCancelled(p_twai_obj->controller_id, &slot->request, P4_TWAI_TX_REASON_REPLACED);
            slot->frame = tx_frame;
            slot->guard = *guard;
            slot->request = p4_twai_new_request(p_twai_obj, &tx_frame, guard);
            ret = ESP_OK;
        } else {
            ret = ESP_ERR_TIMEOUT;
        }
    } else if (!twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED)) {
        const P4TwaiTxIdentity request = p4_twai_new_request(p_twai_obj, &tx_frame, guard);
        // Request diagnostics may take time. Recheck live guards and RX at
        // the last software boundary before handing the frame to hardware.
        if (guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC)
            p4_twai_rx_drain(p_twai_obj, NULL, &alert_req, false);
        const uint8_t reason = p4_twai_priority_guard_reason(guard);
        if (reason != P4_TWAI_TX_REASON_NONE ||
            (guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC &&
             !p4_twai_periodic_ready_locked(p_twai_obj))) {
            p4TwaiDiagTxCancelled(p_twai_obj->controller_id, &request,
                reason != P4_TWAI_TX_REASON_NONE ? reason : P4_TWAI_TX_REASON_RX_BOUNDARY);
            ret = ESP_ERR_INVALID_STATE;
        } else if (guard->source == P4_TWAI_TX_SOURCE_R79_PERIODIC &&
                   twai_hal_get_rx_msg_count(p_twai_obj->hal) != 0) {
            p4TwaiDiagTxCancelled(p_twai_obj->controller_id, &request, P4_TWAI_TX_REASON_RX_PENDING);
            ret = ESP_ERR_TIMEOUT;
        } else {
            p4_twai_load(p_twai_obj, &tx_frame, p4_twai_r79_source(guard), &request);
            p_twai_obj->tx_msg_count++;
            ret = ESP_OK;
        }
    } else {
        p4_twai_priority_slot_t *slot = &s_p4_priority[p_twai_obj->controller_id];
        slot->frame = tx_frame;
        slot->guard = *guard;
        slot->rxBoundary = s_p4_rx_boundary[p_twai_obj->controller_id].delivered;
        slot->pending = true;
        slot->request = p4_twai_new_request(p_twai_obj, &tx_frame, guard);
        p_twai_obj->tx_msg_count++;
        ret = ESP_OK;
    }
    // Task-side progress also covers a drained RX interrupt with an idle slot.
    p4_twai_dispatch_idle(p_twai_obj, NULL, &alert_req, false);
    // Keep tagged RX progress on successful or rejected admission, without
    // putting unrelated parse/capture/queue work ahead of an IMMEDIATE load.
    if (p_twai_obj->state == TWAI_STATE_RUNNING &&
        guard->source != P4_TWAI_TX_SOURCE_R79_PERIODIC && guard->rx_sequence != 0)
        p4_twai_rx_drain(p_twai_obj, NULL, &alert_req, false);
    portEXIT_CRITICAL(&handle->spinlock);
    if (alert_req) xSemaphoreGive(handle->alert_semphr);
    return ret;
}

esp_err_t twai_transmit(const twai_message_t *message, TickType_t ticks_to_wait)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_transmit_v2(g_twai_objs[0], message, ticks_to_wait);
}

esp_err_t twai_receive_v2(twai_handle_t handle, twai_message_t *message, TickType_t ticks_to_wait)
{
    //Check arguments and state
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(message != NULL, ESP_ERR_INVALID_ARG);

    twai_obj_t *p_twai_obj = handle;
    //Get frame from RX Queue or RX Buffer
    p4_twai_rx_item_t item = {0};
    if (xQueueReceive(p_twai_obj->rx_queue, &item, ticks_to_wait) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    portENTER_CRITICAL(&handle->spinlock);
    p_twai_obj->rx_msg_count--;
    s_p4_rx_boundary[p_twai_obj->controller_id].deliveredMeta = (p4_twai_rx_metadata_t){
        .observed_us = item.observedUs,
        .dequeued_us = item.mux1Sequence ? (uint64_t)esp_timer_get_time() : 0,
        .sequence = item.mux1Sequence };
    if (item.boundary)
        s_p4_rx_boundary[p_twai_obj->controller_id].delivered = item.boundary;
    portEXIT_CRITICAL(&handle->spinlock);

    //Decode frame
    twai_frame_header_t header = {0};
    twai_hal_parse_frame(p_twai_obj->hal, &item.frame, &header, message->data, TWAI_FRAME_MAX_LEN);
    message->identifier = header.id;
    message->data_length_code = header.dlc;
    message->extd = header.ide;
    message->rtr = header.rtr;
    // Reject malformed raw DLC before the remaining-byte count can underflow.
    TWAI_CHECK(message->data_length_code <= TWAI_FRAME_MAX_LEN, ESP_ERR_INVALID_SIZE);
    //Set remaining bytes of data to 0
    memset(message->data + message->data_length_code, 0, TWAI_FRAME_MAX_LEN - message->data_length_code);
    return ESP_OK;
}

esp_err_t twai_receive(twai_message_t *message, TickType_t ticks_to_wait)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_receive_v2(g_twai_objs[0], message, ticks_to_wait);
}

esp_err_t twai_read_alerts_v2(twai_handle_t handle, uint32_t *alerts, TickType_t ticks_to_wait)
{
    //Check arguments and state
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(alerts != NULL, ESP_ERR_INVALID_ARG);

    twai_obj_t *p_twai_obj = handle;

    //Wait for an alert to occur
    if (xSemaphoreTake(p_twai_obj->alert_semphr, ticks_to_wait) == pdTRUE) {
        portENTER_CRITICAL(&handle->spinlock);
        *alerts = p_twai_obj->alerts_triggered;
        p_twai_obj->alerts_triggered = 0;    //Clear triggered alerts
        portEXIT_CRITICAL(&handle->spinlock);
        return ESP_OK;
    } else {
        *alerts = 0;
        return ESP_ERR_TIMEOUT;
    }
}

esp_err_t twai_read_alerts(uint32_t *alerts, TickType_t ticks_to_wait)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_read_alerts_v2(g_twai_objs[0], alerts, ticks_to_wait);
}

esp_err_t twai_reconfigure_alerts_v2(twai_handle_t handle, uint32_t alerts_enabled, uint32_t *current_alerts)
{
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);

    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    //Clear any unhandled alerts
    if (current_alerts != NULL) {
        *current_alerts = p_twai_obj->alerts_triggered;
    }
    p_twai_obj->alerts_triggered = 0;
    p_twai_obj->alerts_enabled = alerts_enabled;         //Update enabled alerts
    portEXIT_CRITICAL(&handle->spinlock);

    return ESP_OK;
}

esp_err_t twai_reconfigure_alerts(uint32_t alerts_enabled, uint32_t *current_alerts)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_reconfigure_alerts_v2(g_twai_objs[0], alerts_enabled, current_alerts);
}

esp_err_t twai_initiate_recovery_v2(twai_handle_t handle)
{
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    //Check state
    if (p_twai_obj->state != TWAI_STATE_BUS_OFF) {
        portEXIT_CRITICAL(&handle->spinlock);
        return ESP_ERR_INVALID_STATE;
    }

    //Reset TX Queue/Counters
    if (p_twai_obj->tx_queue != NULL) {
        xQueueReset(p_twai_obj->tx_queue);
    }
    p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_RECOVERY);
    p4TwaiDiagTxRetire(p_twai_obj->controller_id, P4_TWAI_TX_REASON_RECOVERY);
    p_twai_obj->tx_msg_count = 0;

    //Trigger start of recovery process
    twai_hal_start_bus_recovery(p_twai_obj->hal);
    p_twai_obj->state = TWAI_STATE_RECOVERING;
    portEXIT_CRITICAL(&handle->spinlock);

    return ESP_OK;
}

esp_err_t twai_initiate_recovery(void)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_initiate_recovery_v2(g_twai_objs[0]);
}

esp_err_t twai_get_status_info_v2(twai_handle_t handle, twai_status_info_t *status_info)
{
    //Check parameters
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    TWAI_CHECK(status_info != NULL, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    if (p_twai_obj->mode == TWAI_MODE_LISTEN_ONLY) {
        //Error counters are frozen under listen only mode thus are meaningless. Simply return 0 in this case.
        status_info->tx_error_counter = 0;
        status_info->rx_error_counter = 0;
    } else {
        status_info->tx_error_counter = twai_hal_get_tec(p_twai_obj->hal);
        status_info->rx_error_counter = twai_hal_get_rec(p_twai_obj->hal);
    }
    status_info->msgs_to_tx = p_twai_obj->tx_msg_count;
    status_info->msgs_to_rx = p_twai_obj->rx_msg_count;
    status_info->tx_failed_count = p_twai_obj->tx_failed_count;
    status_info->rx_missed_count = p_twai_obj->rx_missed_count;
    status_info->rx_overrun_count = p_twai_obj->rx_overrun_count;
    status_info->arb_lost_count = p_twai_obj->arb_lost_count;
    status_info->bus_error_count = p_twai_obj->bus_error_count;
    status_info->state = p_twai_obj->state;
    portEXIT_CRITICAL(&handle->spinlock);

    return ESP_OK;
}

esp_err_t twai_get_status_info(twai_status_info_t *status_info)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_get_status_info_v2(g_twai_objs[0], status_info);
}

esp_err_t twai_clear_transmit_queue_v2(twai_handle_t handle)
{
    //Check parameters
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    p4_twai_priority_clear(p_twai_obj, P4_TWAI_TX_REASON_QUEUE_CLEAR);
    //If a message is currently undergoing transmission, the tx interrupt handler will decrement tx_msg_count
    p_twai_obj->tx_msg_count = twai_hal_check_state_flags(p_twai_obj->hal, TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED) ? 1 : 0;
    if (p_twai_obj->tx_queue != NULL) {
        xQueueReset(p_twai_obj->tx_queue);
    }
    portEXIT_CRITICAL(&handle->spinlock);

    return ESP_OK;
}

esp_err_t twai_clear_transmit_queue(void)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_clear_transmit_queue_v2(g_twai_objs[0]);
}

esp_err_t twai_clear_receive_queue_v2(twai_handle_t handle)
{
    //Check parameters
    TWAI_CHECK(handle != NULL, ESP_ERR_INVALID_ARG);
    twai_obj_t *p_twai_obj = handle;

    portENTER_CRITICAL(&handle->spinlock);
    p_twai_obj->rx_msg_count = 0;
    xQueueReset(p_twai_obj->rx_queue);
    p4_twai_boundary_reset(p_twai_obj);
    portEXIT_CRITICAL(&handle->spinlock);

    return ESP_OK;
}

esp_err_t twai_clear_receive_queue(void)
{
    // the handle-less driver API only support one TWAI controller, i.e. the g_twai_objs[0]
    return twai_clear_receive_queue_v2(g_twai_objs[0]);
}

#if TWAI_USE_RETENTION_LINK
static esp_err_t s_twai_create_sleep_retention_link_cb(void *obj)
{
    twai_obj_t *host = (twai_obj_t *)obj;
    return sleep_retention_entries_create(twai_reg_retention_info[host->controller_id].entry_array,
                                          twai_reg_retention_info[host->controller_id].array_size,
                                          REGDMA_LINK_PRI_TWAI,
                                          twai_reg_retention_info[host->controller_id].module_id);
}
#endif

#if CONFIG_TWAI_SKIP_LEGACY_CONFLICT_CHECK
/**
 * @brief This function will be called during start up, to check that this legacy TWAI driver is not running along with the new TWAI driver
 */
__attribute__((constructor))
static void check_twai_driver_conflict(void)
{
    // This function was declared as weak here. The new TWAI driver has the implementation.
    // So if the new TWAI driver is not linked in, then `twai_new_node_onchip()` should be NULL at runtime.
    extern __attribute__((weak)) esp_err_t twai_new_node_onchip(const void *node_config, void *node_ret);
    if ((void *)twai_new_node_onchip != NULL) {
        ESP_EARLY_LOGE(TWAI_TAG, "CONFLICT! driver_ng is not allowed to be used with this old driver");
        abort();
    }
    ESP_EARLY_LOGW(TWAI_TAG, "This driver is an old driver, please migrate your application code to adapt `esp_twai_onchip.h`");
}
#endif
