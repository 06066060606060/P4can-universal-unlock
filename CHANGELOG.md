# P4-CAN Universal v3.35.2 — 2026-11-19

- Organized settings for a better overview
- Added experimental SmartShift feature from https://github.com/kl79613/P4Can-automatic-shifting
- Add the S3XY action FSD Visualisation. 
- Add service mode entry & restore TLSSC
- Restore Settings > Auto Lane Change Enable. 
- Add S3XY button support for lane change on standard AP configuration: LEFT emits DOWN_2 (0x8), RIGHT emits UP_2 (0x4).

# P4-CAN Universal v3.35.0 — 2026-11-17

- Replace the Settings Firmware row with a clickable About page showing the current firmware version, the project source repository and Discord invitation. 
- Add Service mode. Enter Service Mode sends one frame per click, without automatic retry or replay.
- Add TLSSC Restore feature. 
- Add FSD visualisation settings.
- Generate dashboard_demo.html from the current source with standalone Model Y preview and local LAB navigation.

# P4-CAN Universal v3.34.9 — 2026-11-07

- Restore the shared final ULC snooze composer used by driver-door and S3XY Auto Blinker cancellation. It now reads the current epoch under the caller-owned TX barrier instead of trying to reacquire that nonrecursive mutex and validating the resulting failure sentinel epoch0. The defective nested snapshot was introduced with ULC final composition in v3.33.9.
- Preserve one-shot bit36 composition in R79 immediate/periodic and existing DMS/vision owners, the idle-only standalone clone, protected pending ULC, R79 priority and MUX fencing. Keep NOA/0x24A input gates, request expiry, both required bus freshness bits, non-Summon admission, payload policies, GPIOs, NVS, routing and dashboard unchanged.
- Strengthen native composition tests with the production epoch snapshot, the actual pure epoch/freshness predicate and a faithful nonrecursive mutex. Cover both application button entries, edge/resume behavior, 16 input/owner/congestion combinations, non-default epochs, each required freshness mask, stale/invalid NOA context, disabled/short door inputs and rejection/request retention. Update the dependent recovery harness to reuse the shared mutex hook.
- Host/native tests and local target compilation do not establish BLE delivery, door hardware input, ECU acceptance, controller behavior or road performance.

# P4-CAN Universal v3.34.8 — 2026-11-04

- Stop waiting on an initial R79 echo when a newer standard DATA MUX1 becomes queued during contention. Preserve one nonblocking authorized fallback and let the RX owner compose the newer input; immediate retry due/index and authority rules remain intact.
- Permit a final nonblocking admission attempt exactly at the selected wait budget in both guards. Do not extend the budget after an overslept tick; retain per-attempt permission, generation, cancellation and quiet hard-deadline checks, including rollover.
- Keep an independent IMMEDIATE recovery reservation when periodic quiet work is accepted. Periodic acceptance is not wire completion and cannot erase the longer-lived recovery if the pending periodic descriptor later loses its MUX window. Preserve retry due/index/budget and AP authority ownership.
- Load authorized tagged IMMEDIATE work before unrelated HAL RX parse/capture/queue work on direct idle and pending dispatch paths; retain bounded RX progress afterward. Keep pre-admission RX fencing for incoming or existing pending PERIODIC work, including protected ULC, and retain final periodic MUX/residual-RX checks and combined IRQ RX-first order.
- Preserve R79 native priority, PARTY gear/AP validity, VEHICLE CPU priority, active hardware nonpreemption, FIFO/counts, protected ULC, BUS_OFF/hold guards, payload transforms, GPIOs, bit timing, NVS and dashboard assets. Host ordering evidence is not proof of physical delivery or reduced Summon Range flicker.

# P4-CAN Universal v3.34.7 — 2026-11-04

- Defer an application IMMEDIATE recovery while a newer standard DATA MUX1 is successfully queued for processing. Preserve its due time, index and retry budget. Recheck input freshness at each bounded admission attempt and before yielding; if a new MUX1 arrives during contention, stop waiting and retain the reservation. Unrelated RX backlog does not defer recovery, and periodic MUX/deadline rules remain unchanged.
- Remove the native intentional latest-input handoff idle window and its reset-on-replacement state. An authorized R79 request loads immediately into free hardware instead of waiting for unprocessed input or a later expiry checkpoint. Busy hardware still retains the newest authorized unprotected pending request; protected ULC, active TX and ordinary FIFO are preserved.
- Preserve P/Summon and strict AP authority/generation/expiry validation through admission and native dispatch. No GPIO, bit timing, NVS, dashboard, transform or task-priority changes.
- Extend the actual scheduler plus guarded-transport regression across P/AP, queue positions0/8/63, barrier/native backpressure, arrivals during admission wait, retained reservation accounting and unrelated backlog. Native tests cover 300us queued bursts, immediate idle/completion loading, pending replacement, protected one-shots and cancellation.
- Availability tradeoff: an older already-authorized transformed R79 response can occupy a hardware frame before a newer unprocessed input. Only pending, untransmitted work is replaceable. No wire-atomic, hard latency, physical delivery or Summon Range improvement guarantee is claimed.

# P4-CAN Universal v3.34.6 — 2026-11-04

- Fix a v3.34.5 regression where due application retry work could spend its two-ms bounded admission wait before an already-queued latest MUX1 was dequeued. Probe RX without blocking first; process an available frame immediately. Only an empty timeout permits due service followed by the existing one-tick queue wait.
- Refresh the captured RX authority epoch after pre-wait service and before a blocking receive. Retain first-receive error handling, cumulative runnable fairness, eight-frame/one-ms checkpoints, native MUX fencing and retry budgets.
- Keep AP retry/authority protection, YL PARTY-first/BODY budgeting, R79 native and VEHICLE CPU priority, payload transforms, GPIOs, bit timing, NVS and dashboard unchanged.
- Add a production scheduler plus guarded-transport regression for queued latest input with an older due P retry, under barrier contention and native admission backpressure. Host-controlled comparison isolates the task order: v3.34.4 first newest admission at1005 versus v3.34.5 at1007; corrected queued-input cases have zero added pre-dequeue wait. This is software scheduling evidence, not a measured vehicle latency or Summon Range fix.

# P4-CAN Universal v3.34.5 — 2026-11-04

- Extend bounded R79 admission-failure recovery to fresh real DRIVE with fresh active AP and an allowed AP gate. Keep Summon traffic priority separate; manual/unknown/stale AP does not gain recovery. Preserve the existing relative 5/15/30ms cadence, three-attempt budget, final permission checks, native R79 priority and periodic MUX/hard-deadline rules.
- Bind AP-dependent reservations to a strict authority generation from creation through service, bounded admission waits and native pending dispatch. Publish a live minimum gear/DAS expiry in internal RAM; invalidate old work across AP/gear loss and unobserved freshness gaps, including when optional AP control is bypassed. A later valid observation does not revive an old reservation or native descriptor. Existing P/Summon recovery remains independent of this AP-only authority.
- Service due R79 retry/quiet work before the first bounded receive wait through the existing native-MUX and fresh-state checkpoint. Retain the one-tick queue wait on unresolved work, cumulative runnable fairness, 64-frame/four-ms VEHICLE batches and VEHICLE priority6 above PARTY/BODY5.
- On Model Y L, process required PARTY traffic before additional BODY diagnostic/drain work. Limit BODY drain to eight frames or one cooperative millisecond per loop while preserving progress. Non-YL retains its previous 32-frame extra-bus budget and ordering; callbacks are not preempted.
- Preserve ordinary FIFO, protected ULC one-shots, active hardware TX, BODY recovery isolation, GPIOs, bit timing, NVS, payload transforms and dashboard assets. Physical latency, CAN errors and Summon Range effects still require field validation.

# P4-CAN Universal v3.34.4 — 2026-11-04

- Replace CAN-B idle polling/sleep with a first receive wait of at most one RTOS tick, waking on queued RX. Keep subsequent draining nonblocking and carry the runnable epoch across short nonempty batches. Force a one-tick scheduler handoff after 64 frames, four milliseconds of cumulative runnable work, or a receive error; preserve YL VEHICLE priority 6, PARTY/BODY priority 5 and 8-frame/1ms R79 checkpoints.
- Attach native MUX1 sequence and FIFO observation time to RX queue items; capture dequeue time and carry the latest processed MUX1 origin through authorized R79 admission and lifecycle records. No physical wire timestamp or ECU acceptance is inferred.
- If a newer valid MUX1 was successfully queued, use zero admission wait for the older echo so it cannot spend two milliseconds blocking newer input processing. Retain an accepted older unprotected immediate response as fallback; defer its hardware load for up to a 1ms eligibility window while the application composes the newer response. Replace only through the existing authorized immediate admission. Processing completion without replacement, or the first native progress checkpoint after expiry, releases the still-authorized fallback. No autonomous microsecond timer or hard wire-latency bound is claimed.
- Preserve ULC-protected pending messages, active hardware TX, ordinary FIFO and native guard/deadline/cancellation checks. Dropped newer input and receive resets do not permanently suppress the older response; MUX0/2 alone do not cancel immediate recovery. Latest periodic-MUX readiness and BODY isolation remain intact.
- Service already-admitted native work independently of the application state-refresh lock at bounded checkpoints. New application retry/periodic admission still requires a successful refresh and existing PARTY/AP validity.
- Export optional tx.rxOrigin with decimal-string sequence, observedUs and dequeuedUs for tagged R79 requests. Maximum synthetic full-ring JSON is 412,493 bytes; raise the bounded export cap from 384 to 416 KiB. Fixed native diagnostic runtime plus snapshot is 79,549 bytes under the existing 96 KiB cap.
- Preserve GPIOs, bit timing, NVS, payload bit policies and dashboard design. Parallel vehicle original frames remain present; actual latency, bus errors and Summon Range effects require field validation.

# P4-CAN Universal v3.34.3 — 2026-11-04

- Service authorized R79 periodic additions and retries during unrelated RX backlog, at the existing bounded RX slice and batch checkpoints. Replace whole software queue-empty gating with a native relevant-MUX readiness check; preserve retry due/index while readiness or state refresh is unavailable.
- Track standard DATA 0x3FD/DLC8 MUX0/1/2 boundaries at native hardware receive, before queue admission. Carry a boundary token with each RX queue item. A periodic window is eligible only when the latest observed boundary has been delivered and is MUX2.
- Recheck native MUX readiness at periodic admission and capture the boundary in the priority slot. Recheck the captured boundary before actual hardware load, including HAL RX that arrived after the interrupt event snapshot. Record RX_BOUNDARY cancellation for obsolete queued periodic requests. Ordinary software RX backlog does not invalidate a boundary.
- If RX arrives during the bounded HAL snapshot drain, defer unclassified work without cancelling the accepted periodic slot. RX-only interrupts and task-side service resume priority dispatch (or the preserved ordinary FIFO after genuine cancellation). Admission returns timeout for unclassified residual RX; direct-load diagnostic cancellation uses RX_PENDING. No double retirement on combined RX/TX events.
- Invalidate boundary readiness on unknown hardware loss and RX queue lifecycle resets. A dropped boundary cannot be acknowledged by an older queued frame; a new latest delivered MUX2 permits resynchronization. RX queue elements add one 32-bit token, with fixed per-controller state and no new ISR allocation.
- Preserve immediate recovery, periodic hard deadlines, AP/PARTY validity, YL VEHICLE CPU priority 6 versus PARTY/BODY 5, native R79 priority, protected ULC one-shots, ordinary FIFO, BODY isolation, bit timing, GPIOs, NVS and dashboard. Already active hardware TX remains nonpreemptable. Hardware reception and TX-register writes are not wire-atomic; field delivery and Summon Range effects require vehicle testing.

# P4-CAN Universal v3.34.2 — 2026-11-04

- Give YL VEHICLE (logical B / physical CAN1) CPU task priority 6, above PARTY/BODY task priority 5 on core 1. Other profiles retain priority 4/5. Keep the task sleep and bounded RX work so PARTY can update vehicle state.
- Service immediate R79 recovery after eight RX frames or one elapsed millisecond, with a cooperative 64-frame/four-millisecond drain cap. Use nonblocking authorization refresh and preserve pending due/index on contention. Service R79 before lower-priority periodic features. Allow periodic R79 only after actual empty RX or fresh empty-queue status, so unread MUX boundaries cannot be bypassed.
- Replace an untransmitted native IMMEDIATE/PERIODIC R79 slot with a newer valid IMMEDIATE, recording REPLACED and a new request identity. Preserve active hardware TX, ordinary FIFO and message counts. A pending request carrying an accepted ULC one-shot is protected from replacement; subsequent requests retain ordinary bounded retry behavior.
- Separate live AP permission expiry from the fixed periodic hard deadline. Valid allowed observations atomically renew the internal-RAM permission deadline; stale/invalid permission revokes generation even in inactive NON_AP. Keep native hold/generation/expiry rechecks and never revive an already-cancelled request across invalid state.
- Preserve PARTY gear/AP rules, BODY isolation, Mode 1, R79 highest native priority, bit timing, GPIO, payload transforms and dashboard. Continuous RX saturation can defer periodic work; per-call latency and hardware-active transmission are not preempted. No physical bus-error, delivery or Summon Range improvement is claimed without vehicle evidence.

# P4-CAN Universal v3.34.1 — 2026-11-03

- Isolate additional BODY (physical CAN2) faults on Model Y L from authorized R79 on VEHICLE (physical CAN1). Only the explicit guarded R79 priority route requires VEHICLE and PARTY readiness without BODY; ordinary feature TX retains its existing all-controller gate.
- Keep BODY BUS OFF/recovery/start failures local. Preserve BODY error/recovery diagnostics and retry installed-controller recovery through the existing status service; do not invalidate VEHICLE/PARTY observations or request a whole-subsystem restart solely for BODY failure.
- Base YL supervisor acquisition/sleep/stale decisions on the required VEHICLE/PARTY pair. Permit startup and controlled recovery with that pair healthy if additional BODY initialization fails. Non-YL behavior remains unchanged.
- Preserve PARTY gear/AP validity policies, final permission/generation/deadline checks, native R79 highest priority, ordinary FIFO, Mode 1 settings, GPIOs, bit timing, payloads and dashboard. Global maintenance, explicit reinitialize and genuine required-bus/task faults retain their existing behavior.
- No live BODY handle teardown is introduced. Missing/unrecoverable BODY may remain degraded until controlled reinitialization. This contains software fault propagation; physical bus errors, wire delivery, ECU reception and Summon Range effects remain unverified.

# P4-CAN Universal v3.34.0 — 2026-11-03

- Remove R79 Mode 2 runtime, mode selector, delayed state and configurable API. Stock reception and service now always use Mode 1. Preserve Mode 1 bit18/wait/reinjection settings. Legacy stored mode/Mode2 bytes are ignored; the existing schema-1 blob layout is preserved and retired bytes are normalized on save. Retired API parameters are rejected before any write, including mixed requests.
- Classify transient R79 TX barrier contention as timeout backpressure; retain invalid-state rejection for a missing lock and all actual policy/generation/hold failures. The selected admission budget yields without holding the TX barrier.
- Reserve and account bounded recovery under the short R79 state lock, without reacquiring the contested transport barrier. Fresh PARK_STANDBY/READY/ACTIVE retain recovery; stale/unknown gear without Summon evidence does not. Keep relative 5/15/30 ms delays and at most three recovery attempts. Contention now advances failure/index/exhaustion bookkeeping.
- Preserve an existing immediate recovery due time and attempt index when fresh stock admission fails again. Periodic work cannot replace immediate recovery; promotion from periodic to immediate retains the earlier due time and remaining budget. Final admission and dispatch still enforce permission, cancellation generation and periodic deadlines.
- Move Continuous AP NVS begin/write/end outside the shared TX barrier. Publish configuration/generation and cancel pending gestures only after successful persistence, under the short barrier.
- Preserve the native R79 priority slot, ordinary FIFO contents, nonpreemptable active hardware TX, YL CAN1 VEHICLE route, GPIOs, bit timing and payload policies. No actual CAN/vehicle test is implied; bus-error elimination and Summon Range effects remain unverified.

# P4-CAN Universal v3.33.12 — 2026-11-03

- Extend existing Mode1 bounded R79 retry eligibility to fresh real PARK_STANDBY, alongside Summon READY/ACTIVE. Immediate echo admission failure and eligible MUX2 periodic failure can now schedule recovery while parked.
- Preserve relative retry intervals of 5, 15 and 30 ms, at most three recovery attempts, latest-stock recomposition, final R79 permission checks, generation/cycle cancellation and periodic hard deadlines. NORMAL, stale/unknown gear without Summon evidence and unsupported priority values remain ineligible. The legacy helper name does not authorize FIFO clearing.
- Preserve Mode2 zero-wait behavior, bit transforms, native priority/FIFO, profile/GPIO/bus timing and dashboard. This improves software recovery coverage; actual CAN delivery, ECU acceptance and Summon Range flicker effects remain unverified.

# P4-CAN Universal v3.33.11 — 2026-11-03

- Move synchronous NVS work for country/map, LAB, Visual Speed Control, DMS/ISA and R79 AP settings outside the shared CAN TX barrier. Existing serialized web ownership (startup migrations before CAN tasks) remains; only final publication and cancellation generations use the brief barrier. Failed saves leave live settings unchanged. Do not widen R79 permissions or retry policies.
- Bound SNAPSHOT capture critical sections to 16 rows at a time. Freeze a fixed RX census and TX state; preserve each first overwritten latest RX value in fixed PSRAM so a multi-chunk snapshot remains coherent. Add reset/owner, config/mode, export and LAB off/on cancellation checks; do not publish partial history or archive data. Add 110,592 bytes of fixed PSRAM shadow storage and include it in reported capture memory. Whole snapshot work remains synchronous and proportional to captured IDs/slots.
- Keep preheating auto-off persistence pending after write/open failure and retry no more often than once per second. Explicit ON supersedes pending OFF; maintenance immediately attempts to flush outstanding OFF even during backoff and reports failure. CAN task performs no flash I/O for this work.
- Preserve YL CAN1 VEHICLE/R79 route, GPIOs, bus timing, native TX priority/FIFO, all R79 bit and permission policies, and dashboard assets. P-state audit found no additional authorized R79 producer emitting stock bits19/47; ordinary PARK_STANDBY still does not reserve a Summon-only retry after a failed echo. Native vehicle stock traffic remains present on the parallel CAN attachment.
- Physical flash latency, field bus-error rates and Summon Range effects remain unverified.

# P4-CAN Universal v3.33.10 — 2026-11-03

- Prevent shared CAN-B ULC/DMS/Visual Speed Control stock clones from entering the ordinary FIFO and later following a newer R79 message with old R79 bits. Use a dedicated standard 0x3FD/DLC8/MUX1 native immediate-only API, atomically checked against hardware occupancy, message backlog and R79 pending state.
- Return ESP_ERR_TIMEOUT when busy, without waiting, queueing, deleting unrelated traffic or promoting an ordinary frame to R79 priority. ULC requests remain pending until accepted or their existing expiration; DMS/vision are recomposed from the next fresh stock frame. A pending ULC request can also merge into the next authorized R79 message.
- Preserve generic ordinary FIFO behavior, BODY vision, R79 priority/cancellation/authorization, active hardware TX, CAN profiles/GPIO/timing and the dashboard. No additional ISR loop, queue metadata or heap allocation.
- Busy ordinary clone attempts can increase TX rejected/timeout counters. This is software backpressure, not a CAN bus error. Sustained congestion can delay an overlay or allow a one-shot to expire under its existing policy.
- Require the new package-owned admission symbol in final link validation. Actual vehicle flicker/bus-error effects remain unverified.

# P4-CAN Universal v3.33.9 — 2026-11-03

- Compose one-shot ULC cancellation into the authorized R79 MUX1 final message, including Mode 1/2 and periodic admission, and into an existing DMS/vision clone. Prevent a second stock-based ULC clone for an already claimed frame. Preserve ULC NOA, both-bus freshness and non-Summon checks; retain the request on failed admission.
- Replace RAW Research Capture's up-to-512 KiB interrupt-disabled PRE copy with archive reservation and bounded web-task service: at most 32 frames/512 bytes per lock, 16 chunks/8 KiB per call. Producers preserve one pending row before overwrite. Add 16 bytes of metadata with no extra PSRAM allocation; use bounded binary search for chronological history windows. Block export/retrigger/mode changes until reserved PRE rows are valid.
- Add a 15-second idle-progress timeout to diagnostic/research downloads. Abort stalled requests and readers, release polling, and show an English retry message. Positive chunks renew the deadline even without a percent change; progressing downloads have no fixed total-duration limit.
- Preserve CAN timing, GPIOs, routing, BODY listen-only, native priority and ordinary FIFO policy. Preheat changes are excluded. No field bus-error or flicker improvement is claimed.
- Known limits: already-admitted ordinary MUX1 clones can still dispatch after a later R79 request; existing SNAPSHOT capture and Reset metadata critical sections are unchanged. These require separate design work.

# P4-CAN Universal v3.33.8 — 2026-11-03

- Record YL physical CAN2 BODY successful native RX observations around ECC errors: four bounded windows, 16 preceding/16 subsequent observations, fixed 100 ms post deadline, explicit error sequences, observation ordering, controller session and overwrite/partial status. This does not recover the failed RX identifier or prove a physical cause.
- Keep completed windows through controller reconfiguration; reset live prehistory and close partial windows at a new configuration session. Capture is fixed internal RAM with no ISR allocation or flash writes.
- Add eight hard-reinitialize lifecycle events with begin/result times, reasons, request ordinal and timestamped cached counter/epoch context. Preserve them across controller installation and Reset Stats; reboot clears them.
- Fix traffic and controller status age snapshots so a concurrent RX/status update cannot underflow the unsigned age and falsely report Offline. Preserve rollover handling and existing UI design.
- Preserve BODY 500 kbit/s, 87.5% and LISTEN_ONLY, other bus timing/modes, saved GPIOs, routes, payloads and R79 priority. No field error reduction or timing-overhead claim is made.

# P4-CAN Universal v3.33.7 — 2026-11-02

- Add a Model Y L physical CAN2 BODY-only 87.5% sample-point comparison at unchanged 500 kbit/s and LISTEN_ONLY.
- Use legal XTAL40/BRP10, 4 MHz quanta, TSEG1 6, TSEG2 1, SJW1. Other buses/profiles retain SDK 80% timing.
- Export the selected installation timing in System Stats and CAN Error JSON; distinguish configured timing from hardware readback.
- Preserve R79 priority/authorization, routing, saved GPIOs, payloads, queue/recovery policy and dashboard design. No vehicle improvement is claimed.

# P4-CAN Universal v3.33.6 — 2026-11-02

- Capture actual controller-loaded TX ID, payload, flags, explicit R79 source, request token and software load time alongside each native ECC error. Retain identity but clear active on completion/lifecycle termination.
- Add bounded R79 queue/load/completion/cancellation history with reasons, and decoded gear/AP/Summon evidence with observation timestamps. Extend CAN Error JSON additively; record overwrites and interpretation limits.
- Invalidate previous-cycle periodic R79 on valid stock MUX0/1/2 before immediate admission, including after the periodic policy consumed its pending flag. Apply the same native cancellation guard to Mode 2 delayed work.
- Preserve ordinary TX FIFO, explicit R79 priority, payload transforms, authorization, physical bus/GPIO mappings, bit timing, YL CAN2 LISTEN_ONLY and dashboard appearance.
- This diagnostic patch does not establish the physical cause or guarantee removal of field bus errors. No hardware access is performed.

# P4-CAN Universal v3.33.5.1 — 2026-11-02

Build-only correction: validate Arduino-copied priority headers with the same exact optional original-path #line directive check used for C sources. Reject changed bytes, incorrect path/line, duplicate prefixes and shadow dependencies. All runtime headers/C sources are byte-identical to reviewed v3.33.5. The v3.33.5 target compiled/linked but publication was blocked by the header-copy checker.

# P4-CAN Universal v3.33.5 — 2026-11-02

- Give explicitly authorized R79 frames the next native TX opportunity before ordinary FIFO traffic without deleting queued frames. Reject ordinary admission while a valid R79 is pending; do not replace a pending priority frame.
- Recheck copied generation/cancellation/hold/deadline guards (including AP-enabled DAS freshness expiry) at dispatch, cancel pending R79 when manual authorization closes, and reset priority accounting on controller lifecycle changes.
- Make ordinary queue insertion and message accounting atomic with native dispatch; positive wait budgets yield outside the driver lock.
- Preserve YL CAN1 VEHICLE/R79 routing, all profile/GPIO/mode/payload policies, existing zero/2 ms R79 admission budgets, RX guards and deferred automatic persistence.
- Current hardware TX and CAN identifier arbitration remain unchanged. Field latency and bus-error effects require device validation.

# P4-CAN Universal v3.33.4.1 — 2026-11-02

Build-only correction: accept only Arduino's exact leading #line 1 directive for the selected package source in compiled-source verification. All four runtime corrections remain byte-identical to v3.33.4. The v3.33.4 target compiled and linked but publication was blocked by this overly strict checker; fresh v3.33.4.1 validation and paired build evidence are required.

# P4-CAN Universal v3.33.4 — 2026-11-02

- Reject DLC > 8 in a minimally patched, pinned package-owned native TWAI receive function; verify actual linked driver ownership and unchanged upstream source outside the guard.
- Remove R79 destructive shared TX queue flushes; preserve bounded recovery scheduling, authorization and payloads.
- Keep zero/2 ms admission budgets with zero-wait submissions under the barrier and unlocked yields between authorized attempts.
- Defer automatic BUS OFF NVS writes until confirmed maintenance stop; retain RAM export, dirty/error tracking and reset semantics. Unexpected power loss can discard deferred records.
- Preserve dashboard, physical CAN routes, GPIO, bit timing and profile mode policy. Field error reduction remains unverified.

# P4-CAN Universal v3.33.3 — 2026-11-02

- Fix undefined RX-to-TX flag propagation: clear destination flags before native receive, normalize successful RX to EXT/RTR only, and value-initialize the CAN-B task message.
- Preserve received ID/DLC/data and explicit direct-TX flags while preventing stale SS/SELF/DLC_NON_COMP/reserved bits from selecting unintended transmission behavior.
- Model the installed SDK's partial flag writes in transport regressions; cover dirty/reused destinations, three controllers, four EXT/RTR combinations, RX-to-TX copies, error/timeout counters and intentional direct-TX flag preservation.
- Preserve GPIO/NVS, profiles, timing, mode policy, HAL/ISR, queue sizes and feature payload logic. The software defect is verified; field bus-error/BUS-OFF elimination is not yet verified.

# P4-CAN Universal v3.33.2 — 2026-10-30

- Add a controlled YL-only passive isolation policy: physical CAN2 BODY uses LISTEN_ONLY during boot and reinstall. Keep CAN1 VEHICLE/R79 and CAN3 PARTY NORMAL; retain USB passive-all behavior and standard-profile modes.
- Report the effective mode in boot logs/API and mark TEC/REC frozen in listen-only. Reuse the Diagnostics soft note to prevent zero counters being mistaken for corrected signaling.
- Preserve500kbit/s/80% timing, GPIO/controller identities, queues, saved settings, R79 routes/waits/payloads and existing HAL/ISR/error capture. This is a diagnostic experiment, not a proven root-cause repair.

# P4-CAN Universal v3.33.1 — 2026-10-29

- Correct Model Y L labels across Home, setup, CAN GPIO, Diagnostics, API, exports and documentation: CAN 1 VEHICLE (original VH), CAN 2 BODY (additional bus), CAN 3 PARTY. Preserve physical identities, saved/default GPIO maps and standard-profile names.
- Extend opt-in R79 Timing Capture schema2 with same-bus/mux RX references, driver-call duration, actual gate-branch reasons and adjacent controller readiness. Retain original CAN decisions, calls, waits, payload/retry/recovery policies.
- Import existing CAN 2 ISR error evidence in the web task into the same CSV, retaining ISR time, import time, error sequence/ECC/TEC/REC/status, boot identity and explicit source-loss/snapshot/saturation/pending-tail metadata. Preserve HAL/ISR and existing64-error source rings; handle late stop/expiry tails without ISR PSRAM work.
- Preserve original dashboard style/controls. Diagnostic overhead, wire completion and actual flicker causality remain unverified on hardware.

# P4-CAN Universal v3.33.0 — 2026-10-29

- Remove the eight-pin CAN GPIO whitelist. Offer the P4 GPIO0–54 range while preventing concurrent use of the actual C6 transport pins6/14–19/54 and required hardware USB CDC/JTAG pins24/25. Preserve six-way duplicate blocking and reject out-of-range/invalid input.
- Derive API allowed pins from the shared boot/POST/record validator; expand editable source, embedded suggestions and validation without redesigning Settings. Document board wiring/I/O voltage considerations for other shared pins.
- Preserve the16-byte CRC record/version and existing saved mappings, defaults, Save & Reboot flow, reset behavior and all CAN timing, routes and HAL capture.

# P4-CAN Universal v3.32.0 — 2026-10-29

- Add Settings > CAN GPIO with existing menu/detail/field controls, active mapping display, complete six-pin validation and explicit Save & Reboot. Keep English labels and original Settings design; no new configuration polling when closed.
- Store one versioned checked physical mapping, load it once at boot, and use the same effective pins for native TWAI install, recovery, boot logs and diagnostics. Defaults remain BODY20/21, VEHICLE50/49 and PARTY26/27. Keep controller identities, routes, bit timing and frame policies.
- Reject partial, reserved, duplicate and corrupt maps. A present invalid record blocks CAN startup while retaining dashboard correction. Preserve wiring configuration during feature/setup resets; Factory Reset clears it. Maintenance/save failures are visible and never hot-apply pins.

# P4-CAN Universal v3.31.8 — 2026-10-29

- Move physical CAN 2 CHASSIS (YL: VEHICLE) from TX22/RX23 to TX50/RX49 for user-requested GPIO-path comparison. CAN 1 stays TX20/RX21 and CAN 3 stays TX26/RX27.
- Preserve the v3.31.7 ECC capture, controller identities, all feature routes, CAN timing/waits/policies, dashboard and saved settings. GPIO selection remains driver initialization work, with no added per-frame processing.
- Reconnect the CAN 2 transceiver TXD input to P4 GPIO50 and RXD output to P4 GPIO49 with power off. GPIO labels are not connector pin numbers. Hardware results and latency changes remain unverified.

# P4-CAN Universal v3.31.7 — 2026-10-28

- Capture raw ECC/type/direction/segment and adjacent TEC/REC/status at the existing P4 HAL error consumer, preserving its single read, IRQ registration and original decoding/flags.
- Add fixed-DRAM per-physical-bus 64-record error-only history with first/latest retention, boot scope, saturation and overwrite metadata. Extend the existing CAN Error JSON without changing dashboard design or polling.
- Pin the package-local HAL to upstream v5.5.5 and the actual SDK ABI. Gate OTA artifacts on final ELF/map owners, capture IRAM and state DRAM while preserving the native driver and TinyCrypt verification.
- Preserve CAN policies, timing, waits/retries/routes, stored settings and the installed SDK. No physical cause or failed RX frame identity is inferred from an error code alone.

# P4-CAN Universal v3.31.6 — 2026-10-28

- Add bounded boot-only physical CAN error journals, preserved first/latest error and fresh BUS OFF evidence, counter epochs, and TX submission/result, RX/service and recovery context.
- Correlate application-owned NVS mutation windows without adding error-triggered persistence. Preserve NVS contents, CAN decisions, bit timing, driver waits/retries/routes and SDK.
- Add a bounded coherent CAN Error JSON download to the existing Logs & Recovery controls; preserve Settings and Diagnostics navigation and the v3.31.5 TX CSV correction.

# P4-CAN Universal v3.31.5 — 2026-10-28

- Correct small BUS OFF TX CSV downloads to serialize a complete bounded response before sending, retaining all existing CSV fields and frozen evidence.
- Add managed physical-bus TX trace downloads to Diagnostics using existing controls. Preserve restored Settings, inline Diagnostics and all CAN/runtime/storage policies.

# P4-CAN Universal v3.31.4 — 2026-10-28

- Replace Diagnostics category/bus/detail navigation with eight inline accordion sections in one Diagnostics screen. Each CAN section directly exposes status, traffic, errors and recovery metrics.
- Open one section at a time, query only its existing section endpoint, and fence obsolete responses when selection/visibility changes. Keep direct reset/reinitialize confirmations and explicit downloads.
- Add smooth 200ms accordion expansion/collapse with keyboard, ARIA and closed-content focus handling. Preserve restored Settings, all existing diagnostic fields and all runtime/backend/CAN behavior.

# P4-CAN Universal v3.31.3 — 2026-10-28

- Restore Settings from the hash-verified v3.29.1 original: inline toggles and theme/refresh choices, Firmware row, descriptions, original colors and detailed page title/hero structure. Preserve current feature additions and approved removals.
- Keep Actions Menu as an original-style inline visibility toggle, independently of preheat engine state. Preserve current Bluetooth master API synchronization and visible-page status reads.
- Compare actual root controls and existing detail headers against the portable original reference at 320/390/430 px in light/dark. Keep CAN, persistence, transport and backend implementation unchanged.

# P4-CAN Universal v3.31.2 — 2026-10-28

- Restore shared warning-red text on Reboot, Reset Feature Settings, Reset Setup · Keep S3XY and Factory Reset using the existing nvsDanger class. Preserve ordinary menu colors and all confirmation behavior.
- Add actual Chromium computed-color regression checks for these actions at 320/390/430 px in both themes. Runtime/backend source and CAN behavior are unchanged.

# P4-CAN Universal v3.31.1 — 2026-10-28

- Restore the original Settings Features/System headings and always-visible menu rows; remove the major-category accordion layer. Keep existing detail pages, direct reset confirmations and English labels.
- Restore ordinary Diagnostics navigation rows without category expansion. Keep selected physical CAN/detail polling and all current diagnostic fields.
- Preserve preheat/Actions/Thermal, S3XY, R79 capture, profile-card simplification, YL VEHICLE/VH naming and all CAN/runtime/backend behavior.

# P4-CAN Universal v3.31.0 — 2026-10-28

- Add the supplied 3dfx Battery Preheat engine as a formal feature, retaining learned trip-ID selection, fixed source payloads, startup/transport guards, cadence/reply limits, target/no-heat shutdown, persistence and S3XY action semantics. Integrate only the feature into the current P4 framework rather than replacing the older whole firmware.
- Retain the Actions page and Thermal schematic from the supplied feature with current dashboard styling and visibility-scoped polling. Menu visibility remains independent of engine enable.
- Restrict accordion behavior to major Settings/Diagnostics categories; restore feature detail pages and direct confirmation for single actions/resets. Add approximately 200ms category expand/collapse/fade/chevron animation, including when the device requests reduced motion.
- Split Diagnostics into category navigation and selected detail views. CAN Status/Traffic/Errors/Recovery fetch only the selected physical bus/view while complete stats downloads remain available.
- Display Model Y L CAN 2 as VEHICLE (VH when abbreviated), without changing physical pins, enums or routes. Remove P4 profile-card bus/STALK/capability chips and their divider; retain internal feature support checks.
- Preserve current BLE ECC/security fixes, R79 Timing Capture, normal TLSSC, short TX OK labels and corrected CAN/paragraph alignment. No hardware behavior is established by host/browser checks.

# P4-CAN Universal v3.30.1 — 2026-10-28

- Fix centered physical CAN status text: remove the obsolete 56px/7px badge constraint and use the full column width with readable text. Keep controller-state and traffic-state decisions unchanged.
- Align direct card notes with the telemetry body inset, including expanded Home Details. Reuse the same readable paragraph size.
- Replace overlapping flex/Diagnostics-only row fixes with one shared telemetry grid. At 320/390px labels and values stack with the same left edge; at 430px values share a right edge. Explanatory rows retain their full-width paragraph behavior.
- Add actual Chromium text-range, baseline, inset and row-geometry regressions at all three widths in both themes. These checks catch alignment errors that overflow-only assertions missed.
- Keep backend production headers, CAN policies, API payloads, settings, polling and interactions byte-identical to v3.30.0.

# P4-CAN Universal v3.30.0 — 2026-10-28

- Combine physical BODY/CHASSIS/PARTY CAN indicators into one equal-width Home card, with optional RX-age/terminology details and unchanged state logic. Retain the short TX OK label.
- Expand full Settings controls inline with one item open at a time, including nested Mode H tuning. Poll only the open item. Preserve auto-save/Apply semantics, capture persistence and reset behavior, with common save-result feedback and short English labels.
- Move AP Control into R79 Mode and retain Timing Capture. Remove the menu visibility flag requirement from AP Control configuration only; runtime AP/transport safety remains. Consolidate Bluetooth Master into Wireless and retain the Devices shortcut.
- Leave only CAN Research Capture in LAB. Remove the five retired LAB screens and its live status board while retaining their existing firmware implementations.
- Fully remove Banned Car/TLSSC Restore state, profile capabilities, APIs and dedicated 0x331 path; preserve ordinary TLSSC. Keep cfg3282 at 14 bytes, ignore retired offsets 2/4 and write zero without shifting active settings.
- Rework Diagnostics for P4, measured internal RAM/PSRAM, Hosted C6/Wi-Fi, BLE and three physical TWAI controllers. Add validated section-specific stats, actual configured bitrate and counter lifetime metadata. Mark unavailable/stale telemetry; distinguish queue acceptance from wire completion.
- Reuse shared detail components in inline cards, wrap narrow selectors, improve 320px diagnostic readability and supply dark tokens for an unknown AP state. Preserve pin map, active CAN policies/waits/routes, recorder and BLE ECC/security fixes.

# P4-CAN Universal v3.29.4 — 2026-10-27

- Add opt-in ten-minute R79 timing capture in PSRAM, with physical-bus raw MUX0/1/2 task RX observations, driver submission calls and exact acceptance/error returns.
- Distinguish guard rejection before a driver call from failed enqueue. Preserve CAN waits, routing, payload transformations, gates, retries, bit timing, pins, NVS and v3.29.3 BLE fixes.
- Reuse the existing R79 panel controls for Start, Stop, CSV and status JSON. Freeze recordings for export, fence Stop/restart races and expose overflow/allocation failure without blocking CAN work.
- All timestamps are CPU software observations. No wire completion, ECU acceptance, vehicle compatibility or Summon flicker resolution is claimed.

# P4-CAN Universal v3.29.3 — 2026-10-27

- Backport Espressif's complete P4 TinyCrypt ECC fix (`9fd7cb7e606a06111e1b14be7f4e00d77d9cf3dd`) as package-owned C objects. Correct native/peripheral conversion and regularized 257-bit ECDH handling associated with peer DHKey Check Failed (`1291`). Keep Secure Connections, native randomness and bonding enabled.
- Check the actual linked NimBLE DHKey path with the Bluetooth Core known-answer vector before allowing BLE operations. A failure stops the host and blocks pairing for the boot; API statistics retain the check result.
- Verify final ELF/map ownership and reject the old SDK ECC archive members before OTA artifact publication. Add actual-C arithmetic regressions, original-code failure evidence and failure-path lifecycle checks.
- Retain the v3.29.2 discovery speed improvements and bounded security behavior. Preserve the user-confirmed net2 wiring, CAN policies, NVS schema and dashboard bytes. The installed SDK and completed packages are unchanged.

# P4-CAN Universal v3.29.2 — 2026-10-27

- Repair the P4 NimBLE security flow with one native owner, actual-encryption verification, a bounded and cancellable ten-second security wait, one confirmed missing-key repair, and detailed failure codes. Preserve native SC bonding while preventing Arduino GATT errors from reentering its unbounded security helper.
- Stop manual discovery promptly after Pair selection, reuse recent typed discovery addresses and retain the fresh-scan fallback for missing or expired observations. Keep multi-candidate selection and existing dashboard interactions.
- Drain host callbacks before clearing scan results or reusing BLE state. Retain operational and probe diagnostics independently of heavy logging.
- Preserve the user-selected net2 CAN pin map, YL/other vehicle routes, CAN/NVS implementation and editable dashboard bytes. Create fresh paired artifacts rather than reusing the original archive's older BIN.

# Changements du portage P4 — 25 octobre 2026

## Correctif réseau et diagnostics — net2

- Séquence réseau reprise du sketch fonctionnel fourni : GPIO6 en entrée, initialisation SDIO avant Wi-Fi, contrôle des erreurs, IP 192.168.4.1, aucune désactivation Hosted au démarrage et Bluetooth autorisé après le premier point d'accès réussi.
- Messages de démarrage avant le journal USB ; conservation des identifiants NVS lors d'un échec temporaire.
- Démarrage TWAI dans l'ordre physique 0/1/2 ; réception native non bloquante commune aux trois bus et comptage avant les traitements véhicule.
- Échantillonnage des états à 100 ms ; Diagnostics / Recovery présente BODY, CHASSIS et PARTY avec erreurs, appels RX et files indépendantes.
- Aucun flash ni essai matériel ; la cause unique de l'absence de RX rapportée reste à confirmer sur la carte.

## Portage initial

- Trois contrôleurs TWAI natifs, bus physiques BODY 20/21, CHASSIS 22/23, PARTY 26/27.
- Tous les profils utilisent les trois bus ; ancien VH Y L raccordé à BODY.
- ESP-Hosted C6 par SDIO, configuré avant Wi-Fi et Bluetooth.
- Réception, récupération, maintenance et écoute seule couvrent les trois contrôleurs.
- Accueil web à trois bus, télémétrie physique, captures de recherche et USB protocole 2.
- Suppression du pilote CAN externe et de son ancien transport matériel.
- Les anciennes notes de validation et l'historique du projet initial sont préservés dans l'archive de sauvegarde externe créée avant modification. Leurs résultats ne constituent pas une validation du P4.

- Nom P4-CAN dans le projet, le dashboard, le SSID par défaut, le BLE, les exports et les identifiants internes.
- Retrait de 19 en-têtes inaccessibles depuis le sketch et les tests, ainsi que de la prévisualisation ancienne et des binaires préliminaires. Les deux en-têtes de structure toujours utilisés sont renommés.
