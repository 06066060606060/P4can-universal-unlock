#include "p4_twai_diag.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include <string.h>

typedef struct {
    uint32_t count;
    uint32_t head;
    uint32_t observed;
    uint32_t overwritten;
    P4TwaiErrorEvent first;
    P4TwaiErrorEvent last;
    P4TwaiErrorEvent events[P4_TWAI_DIAG_CAPACITY];
} P4TwaiErrorBus;

static DRAM_ATTR P4TwaiErrorBus sBuses[P4_TWAI_DIAG_BUS_COUNT];
typedef struct {
    uint32_t count, head, observed, overwritten;
    P4TwaiTxLifecycleEvent events[P4_TWAI_TX_LIFECYCLE_CAPACITY];
} P4TwaiTxLifecycleBus;
static DRAM_ATTR P4TwaiTxLifecycleBus sLifecycle[P4_TWAI_DIAG_BUS_COUNT];
static DRAM_ATTR P4TwaiTxIdentity sLoaded[P4_TWAI_DIAG_BUS_COUNT];
static DRAM_ATTR P4TwaiVehicleContext sVehicle;
static DRAM_ATTR portMUX_TYPE sMux = portMUX_INITIALIZER_UNLOCKED;
static DRAM_ATTR bool sReady;
static DRAM_ATTR uint32_t sBootId;
static DRAM_ATTR uint32_t sInvalidBus;
static DRAM_ATTR uint64_t sEpoch;
static DRAM_ATTR uint64_t sRevision;

/* All RX state is internal RAM. Prehistory is mutable and deliberately excluded
 * from export revision accounting; only error windows invalidate exports. */
typedef struct {
    P4TwaiRxCaptureSnapshot capture;
    uint64_t observationOrder;
    uint32_t head, preHead, preCount;
    int active;
    P4TwaiRxFrame pre[P4_TWAI_RX_PRE_CAPACITY];
} P4TwaiRxState;
static DRAM_ATTR P4TwaiRxState sRx;

static void IRAM_ATTR p4TwaiRxIncrement(uint32_t *value) {
    if (*value != UINT32_MAX) ++*value;
}
static uint64_t IRAM_ATTR p4TwaiRxNextOrder(void) {
    if (sRx.observationOrder != UINT64_MAX) ++sRx.observationOrder;
    return sRx.observationOrder;
}
static void IRAM_ATTR p4TwaiRxCloseLocked(uint8_t status, uint64_t now) {
    if (sRx.active < 0) return;
    P4TwaiRxWindow *w = &sRx.capture.windows[sRx.active];
    w->status = status;
    w->closedUs = now;
    sRx.active = -1;
    ++sRevision;
}
static void IRAM_ATTR p4TwaiRxExpireLocked(uint64_t now) {
    if (sRx.active >= 0 && now >= sRx.capture.windows[sRx.active].deadlineUs)
        p4TwaiRxCloseLocked(P4_TWAI_RX_EXPIRED, now);
}
void p4TwaiDiagConfigureRxCapture(uint8_t bus, bool enabled) {
    if (bus != 1) return;
    portENTER_CRITICAL(&sMux);
    if (sReady) {
        const uint64_t now = (uint64_t)esp_timer_get_time();
        p4TwaiRxExpireLocked(now);
        p4TwaiRxCloseLocked(P4_TWAI_RX_RECONFIGURED, now);
        p4TwaiRxIncrement(&sRx.capture.controllerSession);
        sRx.capture.enabled = enabled;
        sRx.preHead = sRx.preCount = 0;
        ++sRevision;
    }
    portEXIT_CRITICAL(&sMux);
}
bool IRAM_ATTR p4TwaiDiagRxCaptureEnabledFromIsr(uint8_t bus) {
    if (bus != 1) return false;
    portENTER_CRITICAL_ISR(&sMux);
    bool enabled = sReady && sRx.capture.enabled;
    portEXIT_CRITICAL_ISR(&sMux);
    return enabled;
}
void IRAM_ATTR p4TwaiDiagRxFromIsr(uint8_t bus, uint32_t identifier,
                                uint8_t dlc, uint8_t flags, const uint8_t *data) {
    if (bus != 1) return;
    portENTER_CRITICAL_ISR(&sMux);
    if (sReady && sRx.capture.enabled) {
        const uint64_t now = (uint64_t)esp_timer_get_time();
        p4TwaiRxExpireLocked(now);
        if (dlc > 8 || (!(flags & 2) && dlc && !data)) {
            p4TwaiRxIncrement(&sRx.capture.invalidDlc);
        } else {
            p4TwaiRxIncrement(&sRx.capture.rxObserved);
            P4TwaiRxFrame frame = {0};
            frame.observedUs = now;
            frame.observationOrder = p4TwaiRxNextOrder();
            frame.seq = sRx.capture.rxObserved;
            frame.identifier = identifier;
            frame.dlc = dlc;
            frame.flags = flags & 3;
            if (!(flags & 2) && dlc) memcpy(frame.data, data, dlc);
            sRx.pre[sRx.preHead] = frame;
            sRx.preHead = (sRx.preHead + 1) % P4_TWAI_RX_PRE_CAPACITY;
            if (sRx.preCount < P4_TWAI_RX_PRE_CAPACITY) ++sRx.preCount;
            if (sRx.active >= 0) {
                P4TwaiRxWindow *w = &sRx.capture.windows[sRx.active];
                w->post[w->postCount++] = frame;
                ++sRevision;
                if (w->postCount == P4_TWAI_RX_POST_CAPACITY)
                    p4TwaiRxCloseLocked(P4_TWAI_RX_COMPLETE, now);
            }
        }
    }
    portEXIT_CRITICAL_ISR(&sMux);
}
/* The largest ISR copy is 16 fixed 40-byte preframes; no heap or giant local. */
static void IRAM_ATTR p4TwaiRxErrorLocked(uint8_t bus, const P4TwaiErrorEvent *error) {
    p4TwaiRxExpireLocked(error->observedUs);
    if (bus != 1 || !sRx.capture.enabled) return;
    const uint64_t order = p4TwaiRxNextOrder();
    if (sRx.active < 0) {
        sRx.active = (int)sRx.head;
        P4TwaiRxWindow *w = &sRx.capture.windows[sRx.head];
        /* Unused payload remains unreachable; snapshot clears unused entries. */
        memset(w, 0, offsetof(P4TwaiRxWindow, pre));
        p4TwaiRxIncrement(&sRx.capture.observed);
        w->seq = sRx.capture.observed;
        w->controllerSession = sRx.capture.controllerSession;
        w->firstErrorSeq = error->seq;
        w->firstErrorUs = error->observedUs;
        w->firstErrorOrder = order;
        w->deadlineUs = error->observedUs + P4_TWAI_RX_POST_TIMEOUT_US;
        w->status = P4_TWAI_RX_COLLECTING;
        w->preCount = sRx.preCount;
        const unsigned start = (sRx.preHead + P4_TWAI_RX_PRE_CAPACITY - sRx.preCount)
                               % P4_TWAI_RX_PRE_CAPACITY;
        for (unsigned n = 0; n < sRx.preCount; ++n)
            w->pre[n] = sRx.pre[(start + n) % P4_TWAI_RX_PRE_CAPACITY];
        sRx.head = (sRx.head + 1) % P4_TWAI_RX_WINDOW_CAPACITY;
        if (sRx.capture.count < P4_TWAI_RX_WINDOW_CAPACITY) ++sRx.capture.count;
        else p4TwaiRxIncrement(&sRx.capture.overwritten);
    }
    P4TwaiRxWindow *w = &sRx.capture.windows[sRx.active];
    p4TwaiRxIncrement(&w->errorCount);
    w->lastErrorSeq = error->seq;
    w->lastErrorUs = error->observedUs;
    w->lastErrorOrder = order;
}

_Static_assert(sizeof(P4TwaiErrorEvent) == 120, "fixed ISR record size");
_Static_assert(sizeof(sBuses) + sizeof(sLifecycle) + sizeof(sLoaded) + sizeof(sVehicle) + sizeof(sMux) + sizeof(sReady) + sizeof(sBootId)
               + sizeof(sInvalidBus) + sizeof(sEpoch) + sizeof(sRevision) + sizeof(sRx)
               + sizeof(P4TwaiErrorSnapshot) <= 96 * 1024,
               "ISR journal and one export must fit the 96KiB budget");
_Static_assert(P4_TWAI_DIAG_BUS_COUNT * offsetof(P4TwaiErrorBus, events) < 1024,
               "initialization clears metadata only in a short critical section");

void p4TwaiDiagInit(uint32_t bootId) {
    portENTER_CRITICAL(&sMux);
    /* Ring payload is deliberately not cleared under the lock: count/head make
     * all old slots unreachable, and successful exports zero unused slots. */
    for (unsigned bus = 0; bus < P4_TWAI_DIAG_BUS_COUNT; ++bus) {
        memset(&sBuses[bus], 0, offsetof(P4TwaiErrorBus, events));
        memset(&sLifecycle[bus], 0, offsetof(P4TwaiTxLifecycleBus, events));
        memset(&sLoaded[bus], 0, sizeof(sLoaded[bus]));
    }
    memset(&sVehicle, 0, sizeof(sVehicle));
    memset(&sRx.capture, 0, offsetof(P4TwaiRxCaptureSnapshot, windows));
    sRx.capture.physicalBus = 1;
    sRx.observationOrder = 0;
    sRx.head = sRx.preHead = sRx.preCount = 0;
    sRx.active = -1;
    sBootId = bootId;
    sInvalidBus = 0;
    ++sEpoch;
    ++sRevision;
    sReady = true;
    portEXIT_CRITICAL(&sMux);
}

void p4TwaiDiagPublishVehicleContext(const P4TwaiVehicleContext *context) {
    if (!context) return;
    portENTER_CRITICAL(&sMux);
    if (sReady) sVehicle = *context;
    portEXIT_CRITICAL(&sMux);
}

/* Caller holds sMux. Events capture immutable identities/context; mutable
 * shadows themselves are intentionally outside snapshot revision accounting. */
static void p4TwaiDiagLifecycleLocked(uint8_t bus, const P4TwaiTxIdentity *tx,
                                    uint8_t kind, uint8_t reason) {
    if (tx->source == P4_TWAI_TX_SOURCE_UNKNOWN) return;
    P4TwaiTxLifecycleBus *b = &sLifecycle[bus];
    if (b->observed != UINT32_MAX) ++b->observed;
    P4TwaiTxLifecycleEvent event = {0};
    event.observedUs = (uint64_t)esp_timer_get_time();
    event.seq = b->observed;
    event.kind = kind;
    event.reason = reason;
    event.tx = *tx;
    event.vehicle = sVehicle;
    b->events[b->head] = event;
    b->head = (b->head + 1) % P4_TWAI_TX_LIFECYCLE_CAPACITY;
    if (b->count < P4_TWAI_TX_LIFECYCLE_CAPACITY) ++b->count;
    else if (b->overwritten != UINT32_MAX) ++b->overwritten;
    ++sRevision;
}

void p4TwaiDiagTxQueued(uint8_t bus, const P4TwaiTxIdentity *tx) {
    portENTER_CRITICAL_ISR(&sMux);
    if (sReady && bus < P4_TWAI_DIAG_BUS_COUNT && tx)
        p4TwaiDiagLifecycleLocked(bus, tx, P4_TWAI_TX_QUEUED, P4_TWAI_TX_REASON_NONE);
    portEXIT_CRITICAL_ISR(&sMux);
}

void p4TwaiDiagTxLoaded(uint8_t bus, const P4TwaiTxIdentity *tx) {
    portENTER_CRITICAL_ISR(&sMux);
    if (sReady && bus < P4_TWAI_DIAG_BUS_COUNT && tx) {
        sLoaded[bus] = *tx;
        sLoaded[bus].loadedUs = (uint64_t)esp_timer_get_time();
        sLoaded[bus].active = 1;
        sLoaded[bus].valid = 1;
        p4TwaiDiagLifecycleLocked(bus, &sLoaded[bus], P4_TWAI_TX_LOADED, P4_TWAI_TX_REASON_NONE);
    }
    portEXIT_CRITICAL_ISR(&sMux);
}

void p4TwaiDiagTxCancelled(uint8_t bus, const P4TwaiTxIdentity *tx, uint8_t reason) {
    portENTER_CRITICAL_ISR(&sMux);
    if (sReady && bus < P4_TWAI_DIAG_BUS_COUNT && tx)
        p4TwaiDiagLifecycleLocked(bus, tx, P4_TWAI_TX_CANCELLED, reason);
    portEXIT_CRITICAL_ISR(&sMux);
}

void p4TwaiDiagTxRetire(uint8_t bus, uint8_t reason) {
    portENTER_CRITICAL_ISR(&sMux);
    if (sReady && bus < P4_TWAI_DIAG_BUS_COUNT && sLoaded[bus].active) {
        sLoaded[bus].active = 0;
        p4TwaiDiagLifecycleLocked(bus, &sLoaded[bus],
            (reason == P4_TWAI_TX_REASON_SUCCESS || reason == P4_TWAI_TX_REASON_FAILED)
                ? P4_TWAI_TX_COMPLETED : P4_TWAI_TX_CANCELLED, reason);
    }
    portEXIT_CRITICAL_ISR(&sMux);
}

void IRAM_ATTR p4TwaiDiagRecordFromIsr(uint8_t bus, uint32_t ecc,
                                    uint32_t status, uint32_t tec,
                                    uint32_t rec, uint32_t halFlags) {
    portENTER_CRITICAL_ISR(&sMux);
    if (!sReady) {
        portEXIT_CRITICAL_ISR(&sMux);
        return;
    }
    if (bus >= P4_TWAI_DIAG_BUS_COUNT) {
        if (sInvalidBus != UINT32_MAX) ++sInvalidBus;
        ++sRevision;
        portEXIT_CRITICAL_ISR(&sMux);
        return;
    }
    P4TwaiErrorBus *b = &sBuses[bus];
    if (b->observed != UINT32_MAX) ++b->observed;
    P4TwaiErrorEvent event = {0};
    event.observedUs = (uint64_t)esp_timer_get_time();
    event.seq = b->observed;
    event.ecc = ecc;
    event.status = status;
    event.tec = tec;
    event.rec = rec;
    event.halFlags = halFlags;
    event.tx = sLoaded[bus];
    event.vehicle = sVehicle;
    p4TwaiRxErrorLocked(bus, &event);
    if (b->count == 0) b->first = event;
    b->last = event;
    b->events[b->head] = event;
    b->head = (b->head + 1) % P4_TWAI_DIAG_CAPACITY;
    if (b->count < P4_TWAI_DIAG_CAPACITY) {
        ++b->count;
    } else if (b->overwritten != UINT32_MAX) {
        ++b->overwritten;
    }
    ++sRevision;
    portEXIT_CRITICAL_ISR(&sMux);
}

bool p4TwaiDiagSnapshot(P4TwaiErrorSnapshot *out) {
    if (!out) return false;
    for (unsigned attempt = 0; attempt < 3; ++attempt) {
        uint64_t epoch, revision;
        uint32_t rxStart = 0;
        bool valid = true;
        /* No large copy or clearing takes place while interrupts are masked. */
        memset(out, 0, sizeof(*out));
        portENTER_CRITICAL(&sMux);
        if (!sReady) {
            portEXIT_CRITICAL(&sMux);
            return false;
        }
        p4TwaiRxExpireLocked((uint64_t)esp_timer_get_time());
        epoch = sEpoch;
        revision = sRevision;
        memcpy(&out->rxCapture, &sRx.capture, offsetof(P4TwaiRxCaptureSnapshot, windows));
        rxStart = (sRx.head + P4_TWAI_RX_WINDOW_CAPACITY - sRx.capture.count)
                  % P4_TWAI_RX_WINDOW_CAPACITY;
        out->bootId = sBootId;
        out->invalidBus = sInvalidBus;
        out->captureBeginUs = (uint64_t)esp_timer_get_time();
        portEXIT_CRITICAL(&sMux);

        for (unsigned bus = 0; valid && bus < P4_TWAI_DIAG_BUS_COUNT; ++bus) {
            uint32_t start = 0, lifecycleStart = 0;
            P4TwaiErrorBusSnapshot *dest = &out->buses[bus];
            portENTER_CRITICAL(&sMux);
            valid = sReady && sEpoch == epoch && sRevision == revision;
            if (valid) {
                const P4TwaiTxLifecycleBus *life = &sLifecycle[bus];
                dest->lifecycle.count = life->count;
                dest->lifecycle.observed = life->observed;
                dest->lifecycle.overwritten = life->overwritten;
                lifecycleStart = (life->head + P4_TWAI_TX_LIFECYCLE_CAPACITY - life->count)
                                 % P4_TWAI_TX_LIFECYCLE_CAPACITY;
                const P4TwaiErrorBus *b = &sBuses[bus];
                dest->count = b->count;
                dest->observed = b->observed;
                dest->overwritten = b->overwritten;
                dest->hasFirst = b->count != 0;
                dest->hasLast = b->count != 0;
                dest->first = b->first;
                dest->last = b->last;
                start = (b->head + P4_TWAI_DIAG_CAPACITY - b->count)
                        % P4_TWAI_DIAG_CAPACITY;
            }
            portEXIT_CRITICAL(&sMux);
            for (uint32_t index = 0; valid && index < dest->count; ++index) {
                portENTER_CRITICAL(&sMux);
                valid = sReady && sEpoch == epoch && sRevision == revision;
                if (valid) {
                    dest->events[index] = sBuses[bus].events[
                        (start + index) % P4_TWAI_DIAG_CAPACITY];
                }
                portEXIT_CRITICAL(&sMux);
            }
            for (uint32_t index = 0; valid && index < dest->lifecycle.count; ++index) {
                portENTER_CRITICAL(&sMux);
                valid = sReady && sEpoch == epoch && sRevision == revision;
                if (valid) dest->lifecycle.events[index] = sLifecycle[bus].events[
                    (lifecycleStart + index) % P4_TWAI_TX_LIFECYCLE_CAPACITY];
                portEXIT_CRITICAL(&sMux);
            }
            /* Copy time describes the completed per-bus copy interval. */
            if (valid) dest->copiedAtUs = (uint64_t)esp_timer_get_time();
        }
        for (uint32_t n = 0; valid && n < out->rxCapture.count; ++n) {
            P4TwaiRxWindow *dest = &out->rxCapture.windows[n];
            const uint32_t slot = (rxStart + n) % P4_TWAI_RX_WINDOW_CAPACITY;
            portENTER_CRITICAL(&sMux);
            valid = sReady && sEpoch == epoch && sRevision == revision;
            if (valid) memcpy(dest, &sRx.capture.windows[slot], offsetof(P4TwaiRxWindow, pre));
            portEXIT_CRITICAL(&sMux);
            for (unsigned i = 0; valid && i < dest->preCount + dest->postCount; ++i) {
                portENTER_CRITICAL(&sMux);
                valid = sReady && sEpoch == epoch && sRevision == revision;
                if (valid) {
                    if (i < dest->preCount) dest->pre[i] = sRx.capture.windows[slot].pre[i];
                    else dest->post[i - dest->preCount] = sRx.capture.windows[slot].post[i - dest->preCount];
                }
                portEXIT_CRITICAL(&sMux);
            }
        }
        portENTER_CRITICAL(&sMux);
        valid = valid && sReady && sEpoch == epoch && sRevision == revision;
        if (valid) {
            out->capturedUs = (uint64_t)esp_timer_get_time();
            out->consistent = true;
        }
        portEXIT_CRITICAL(&sMux);
        if (valid) return true;
    }
    memset(out, 0, sizeof(*out));
    return false;
}
