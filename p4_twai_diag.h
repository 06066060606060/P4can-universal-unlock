#ifndef P4_TWAI_DIAG_H
#define P4_TWAI_DIAG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_attr.h"

#ifdef __cplusplus
extern "C" {
#endif

#define P4_TWAI_TX_CONTEXT_VERSION 1
enum { P4_TWAI_DIAG_BUS_COUNT = 3, P4_TWAI_DIAG_CAPACITY = 64,
       P4_TWAI_TX_LIFECYCLE_CAPACITY = 32 };
enum { P4_TWAI_TX_SOURCE_UNKNOWN = 0, P4_TWAI_TX_SOURCE_R79_UNKNOWN = 1,
       P4_TWAI_TX_SOURCE_R79_IMMEDIATE = 2, P4_TWAI_TX_SOURCE_R79_PERIODIC = 3 };
enum { P4_TWAI_TX_QUEUED = 1, P4_TWAI_TX_LOADED = 2,
       P4_TWAI_TX_COMPLETED = 3, P4_TWAI_TX_CANCELLED = 4 };
enum { P4_TWAI_TX_REASON_NONE = 0, P4_TWAI_TX_REASON_SUCCESS = 1,
       P4_TWAI_TX_REASON_FAILED = 2, P4_TWAI_TX_REASON_GENERATION = 3,
       P4_TWAI_TX_REASON_CANCEL_GENERATION = 4, P4_TWAI_TX_REASON_HOLD = 5,
       P4_TWAI_TX_REASON_DEADLINE = 6, P4_TWAI_TX_REASON_BUS_OFF = 7,
       P4_TWAI_TX_REASON_STOP = 8, P4_TWAI_TX_REASON_RECOVERY = 9,
       P4_TWAI_TX_REASON_UNINSTALL = 10, P4_TWAI_TX_REASON_QUEUE_CLEAR = 11,
       P4_TWAI_TX_REASON_START = 12, P4_TWAI_TX_REASON_REPLACED = 13, P4_TWAI_TX_REASON_RX_BOUNDARY = 14, P4_TWAI_TX_REASON_RX_PENDING = 15 };

typedef struct {
    uint32_t publishedMs, gearObservedMs, apObservedMs, summonObservedMs;
    uint8_t gear, gearSource, gearValid, apState, apValid, summonActive, summonValid, reserved;
} P4TwaiVehicleContext;

/* loadedUs marks software controller loading, NEVER wire start/completion.
 * valid means a load was observed this diagnostic epoch; active means that
 * identity is still associated with an outstanding controller TX.
 * flags: bit0 EXT, bit1 RTR; source UNKNOWN is never inferred from an ID. */
typedef struct {
    uint64_t loadedUs;
    uint64_t queuedUs; // explicit R79 admission; zero for ordinary TX
    uint64_t rxObservedUs; // native FIFO observation, never physical wire time
    uint64_t rxDequeuedUs; // application receive dequeue observation
    uint32_t rxSequence; // originating RX token; zero means origin absent
    uint32_t requestId; // per-controller R79 token; wraps skipping zero
    uint32_t identifier;
    uint8_t data[8];
    uint8_t dlc, source, flags, active, valid, reserved[3];
} P4TwaiTxIdentity;

typedef struct {
    uint64_t observedUs;
    uint32_t seq;
    uint8_t kind, reason, reserved[2];
    P4TwaiTxIdentity tx;
    P4TwaiVehicleContext vehicle;
} P4TwaiTxLifecycleEvent;

typedef struct {
    uint32_t count, observed, overwritten;
    P4TwaiTxLifecycleEvent events[P4_TWAI_TX_LIFECYCLE_CAPACITY];
} P4TwaiTxLifecycleSnapshot;

typedef struct {
    uint64_t observedUs;
    uint32_t seq;
    uint32_t ecc;
    uint32_t status;
    uint32_t tec;
    uint32_t rec;
    uint32_t halFlags;
    P4TwaiTxIdentity tx;
    P4TwaiVehicleContext vehicle;
} P4TwaiErrorEvent;

typedef struct {
    uint32_t count;
    uint32_t observed;
    uint32_t overwritten;
    uint64_t copiedAtUs;
    bool hasFirst;
    bool hasLast;
    P4TwaiErrorEvent first;
    P4TwaiErrorEvent last;
    P4TwaiErrorEvent events[P4_TWAI_DIAG_CAPACITY];
    P4TwaiTxLifecycleSnapshot lifecycle;
} P4TwaiErrorBusSnapshot;

/* RX/session/window counters saturate at UINT32_MAX; observationOrder at
 * UINT64_MAX. Prehistory is rolling and exports include only error windows.
 * COLLECTING is partial; EXPIRED/RECONFIGURED preserve partial postframes.
 * Expiry is lazy at the next hook/configuration/snapshot, never extends deadline. */
#define P4_TWAI_RX_CAPTURE_VERSION 1
enum { P4_TWAI_RX_PRE_CAPACITY = 16, P4_TWAI_RX_POST_CAPACITY = 16,
       P4_TWAI_RX_WINDOW_CAPACITY = 4, P4_TWAI_RX_POST_TIMEOUT_US = 100000 };
enum { P4_TWAI_RX_COLLECTING = 1, P4_TWAI_RX_COMPLETE = 2,
       P4_TWAI_RX_EXPIRED = 3, P4_TWAI_RX_RECONFIGURED = 4 };
/* Software hook order only: FIFO frames observed after ECC may have arrived
 * physically before the error. No damaged frame payload is recoverable here. */
typedef struct {
    uint64_t observedUs, observationOrder;
    uint32_t seq, identifier;
    uint8_t data[8];
    uint8_t dlc, flags, reserved[6];
} P4TwaiRxFrame;
typedef struct {
    uint64_t firstErrorUs, lastErrorUs, firstErrorOrder, lastErrorOrder;
    uint64_t deadlineUs, closedUs;
    uint32_t seq, controllerSession, firstErrorSeq, lastErrorSeq, errorCount;
    uint8_t status, preCount, postCount, reserved;
    P4TwaiRxFrame pre[P4_TWAI_RX_PRE_CAPACITY];
    P4TwaiRxFrame post[P4_TWAI_RX_POST_CAPACITY];
} P4TwaiRxWindow;
typedef struct {
    uint32_t controllerSession, count, observed, overwritten, rxObserved, invalidDlc;
    uint8_t enabled, physicalBus, reserved[6];
    P4TwaiRxWindow windows[P4_TWAI_RX_WINDOW_CAPACITY];
} P4TwaiRxCaptureSnapshot;

typedef struct {
    uint32_t bootId;
    uint32_t invalidBus;
    uint64_t captureBeginUs;
    uint64_t capturedUs;
    bool consistent;
    P4TwaiErrorBusSnapshot buses[P4_TWAI_DIAG_BUS_COUNT];
    P4TwaiRxCaptureSnapshot rxCapture;
} P4TwaiErrorSnapshot;

/* Initialize once before driver installation. Reinitialization clears the
 * journal safely, invalidating exports already in progress. */
void p4TwaiDiagInit(uint32_t bootId);

/* Physical controller index: 0 CAN1, 1 CAN2, 2 CAN3; profile determines role.
 * Model Y L maps CAN2 to BODY. Error IRQs only.
 * ecc is the existing HAL read: this routine never reads hardware registers. */
void IRAM_ATTR p4TwaiDiagRecordFromIsr(uint8_t bus, uint32_t ecc,
                                    uint32_t status, uint32_t tec,
                                    uint32_t rec, uint32_t halFlags);

/* Task-only publication. A fixed struct copy under the diagnostic lock;
 * caller owns freshness semantics and all observed timestamps. Init clears it. */
void p4TwaiDiagPublishVehicleContext(const P4TwaiVehicleContext *context);
/* Native driver only, called while its spinlock is held, from task or ISR.
 * These APIs take only the inner diagnostic lock; no heap/app callback/lock.
 * Ordinary load updates do not invalidate an in-progress journal snapshot. */
void p4TwaiDiagTxQueued(uint8_t bus, const P4TwaiTxIdentity *tx);
void p4TwaiDiagTxLoaded(uint8_t bus, const P4TwaiTxIdentity *tx);
void p4TwaiDiagTxCancelled(uint8_t bus, const P4TwaiTxIdentity *tx, uint8_t reason);
void p4TwaiDiagTxRetire(uint8_t bus, uint8_t reason);

/* Task-only before install/reconfigure. Only physical bus 1 supports capture;
 * each call for that bus starts a new controller session, clears prehistory,
 * and closes active collection while preserving bounded frozen history. */
void p4TwaiDiagConfigureRxCapture(uint8_t bus, bool enabled);
bool IRAM_ATTR p4TwaiDiagRxCaptureEnabledFromIsr(uint8_t bus);
void IRAM_ATTR p4TwaiDiagRxFromIsr(uint8_t bus, uint32_t identifier,
                                uint8_t dlc, uint8_t flags, const uint8_t *data);

/* Task-only read. Three bounded attempts; false means no coherent export.
 * On failure the caller must discard all output, even if some fields changed.
 * Counters and event seq saturate at UINT32_MAX; entries remain chronological. */
bool p4TwaiDiagSnapshot(P4TwaiErrorSnapshot *out);

#ifdef __cplusplus
}
#endif
#endif
