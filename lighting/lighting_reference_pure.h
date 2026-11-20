#pragma once

// Five lighting features (F1..F5) - host-testable decision logic.
//
// This header deliberately contains no Arduino / ESP-IDF dependency so the
// decision rules can be compiled and unit-tested on a host compiler. The
// runtime side (frame-template pool, TX barrier, NVS, statistics) lives in
// lighting_features.h.
//
// Verification status of every rule is stated explicitly:
//   // TODO(verify):    the CAN bit assignment still needs bench confirmation
//   // TODO(calibrate): the numeric threshold is an empirical placeholder
//
// CAN channel map (physical bus numbers from p4_can.h). Every lighting frame
// this module writes or mirrors lives on the BODY controller: the on-car capture
// shows 0x3E9 DAS_bodyControls alongside 0x3C2/0x273/0x339, so the earlier
// "0x3E9 rides the party bus" split was wrong and sending there did nothing.
//   bus 0 = P4_BODY    -> 0x3C2 VCLEFT_SWITCH    (F1 high beam strobe, F2 follow)
//                      -> 0x249 SCCM_leftStalk    (F1/F2 high beam request)
//                      -> 0x273 UI_vehicleControl (F3 rear fog), 0x339 VCSEC (F5)
//                      -> 0x3E9 DAS_bodyControls  (F4 dynamic brake light)
//   bus 1 = P4_CHASSIS -> no lighting traffic
//   bus 2 = P4_PARTY   -> no lighting traffic

#include <stdint.h>
#include <string.h>

// ---------------------------------------------------------------------------
// Target frame identifiers
// ---------------------------------------------------------------------------

static constexpr uint16_t LIGHTING_ID_VCLEFT_SWITCH = 0x3C2;  // bus 0
static constexpr uint16_t LIGHTING_ID_LEFTSTALK = 0x249;      // bus 0, F1 gesture
static constexpr uint16_t LIGHTING_ID_VEHICLE_CONTROL = 0x273;  // bus 1, F3
static constexpr uint16_t LIGHTING_ID_VCSEC_AUTH = 0x339;       // bus 1, F5
static constexpr uint16_t LIGHTING_ID_DAS_BODY = 0x3E9;         // bus 0, F4
// The two chassis frames the reference firmware reads the brake from
// (`0xd664` for 0x145, `0xd67c` for 0x39D). Both are CHASSIS frames there, so
// they are listened for on the chassis bus here too - the operator asked for the
// channel to match as well as the bits.
static constexpr uint16_t LIGHTING_ID_ESP_STATUS = 0x145;
static constexpr uint16_t LIGHTING_ID_IBST_STATUS = 0x39D;
// Rear-fog lamp state feedback. Receive-only: the car broadcasts it, the
// reference firmware only listens to it, and this firmware does the same.
static constexpr uint16_t LIGHTING_ID_REAR_FOG_LAMP = 0x3E3;      // bus 1, read-only
// (BODY, 0x3F5) VCFRONT_lighting - read-only. This is the car's own report of
// what the headlights are doing, which makes it the only feedback this module
// has: the request it writes (0x3C2 d5 bit7, 0x249 d1 bit4) is a command, and
// nothing on the bus acknowledged it before this identifier was observed.
//
// The layout below is measured, not assumed: CAN_Research_Capture(1).csv segment
// 1 (an on-car AP drive with the stalk held) shows exactly two payload shapes,
// `00 19 19 08 84 04 00 00` while nothing is requested and `00 19 19 18 94 04 00
// 00` during the hold, so byte 3 bits 5..4 carry it. The values match the DBC
// enum VCFRONT_highBeamControlState: 0 IDLE / 1 INTERMITTENT / 2 LATCHED /
// 3 DAS_AUTO. The catalog also lists VCFRONT_dynamicBrakeLightState in this
// frame, but no capture of a working dynamic-brake request exists, so that bit
// is deliberately NOT decoded here rather than guessed.
static constexpr uint16_t LIGHTING_ID_VCFRONT_LIGHTING = 0x3F5;      // bus 0, read-only
static constexpr uint8_t LIGHTING_3F5_D3 = 3u;
static constexpr uint8_t LIGHTING_3F5_HIGH_BEAM_SHIFT = 4u;
static constexpr uint8_t LIGHTING_3F5_HIGH_BEAM_MASK = 0x03u;
static constexpr uint8_t LIGHTING_3F5_HIGH_BEAM_IDLE = 0u;
static constexpr uint8_t LIGHTING_3F5_HIGH_BEAM_INTERMITTENT = 1u;
static constexpr uint8_t LIGHTING_3F5_HIGH_BEAM_LATCHED = 2u;
static constexpr uint8_t LIGHTING_3F5_HIGH_BEAM_DAS_AUTO = 3u;

static inline uint8_t lightingHighBeamControlStatePure(const uint8_t data[8]) {
  return (uint8_t)((data[LIGHTING_3F5_D3] >> LIGHTING_3F5_HIGH_BEAM_SHIFT) &
                   LIGHTING_3F5_HIGH_BEAM_MASK);
}

// Byte 4 of the same frame carries the two one-bit function states that the
// lamp actually follows. This is the predicate the re-assert loop has to read.
//
// Re-measured 2026-11-18 over five captures (CAN_Research_Capture 6, 7, (1),
// 2(6) and the AHB drive), scoring each candidate against the next 0x3F6 report
// within 120 ms and keeping only samples where d3 and d4 had both been stable
// for at least 400 ms. One shared sample set, n=58, so the numbers below are
// directly comparable - the note this replaced quoted 415 samples and a 98.8%
// figure that no longer exists in any artifact and is withdrawn:
//
//   d4 & 0x30  (intermittent OR latched)   100.0%   (58/58)
//   ctrl in {1,2}                          100.0%   (58/58)
//   composite (d4 when seen, else ctrl)    100.0%   (58/58)
//   d4 & 0x20  (latched only)               98.3%   (57/58)
//   d4 bit4    (intermittent only)          84.5%   (49/58)
//
// Two facts keep that table from being as strong as it looks, and both are why
// the mask did not change:
//   * The sample set is lopsided: 48 of the 58 samples are dark, only 10 are
//     lit. The single miss on d4 & 0x20 is the one INTERMITTENT sample
//     (d4 = 0x94), the nine misses on bit4 are the LATCHED ones (0xA4).
//   * d4 is not an independent second opinion, it is ctrl compressed. Across all
//     804 0x3F5 frames on CAN 1 d4 only ever takes 0x84 / 0x94 / 0xA4, and
//     bit4 <=> ctrl==1, bit5 <=> ctrl==2. That is why 0x30 ties with
//     ctrl in {1,2} at 100%, and why d4==0 was never observed (0 of 804 frames).
// The one real disagreement is DAS_AUTO (3): ctrl reads "not ours" while d4
// still says lit (0xA4). Reading d4 as well removes those false "dark" reports,
// which is the case this mask exists for.
static constexpr uint8_t LIGHTING_3F5_D4 = 4u;
static constexpr uint8_t LIGHTING_3F5_INT_FUNCTION_BIT = 0x10u;
static constexpr uint8_t LIGHTING_3F5_LATCHED_FUNCTION_BIT = 0x20u;
static constexpr uint8_t LIGHTING_3F5_FUNCTION_LIT_MASK = 0x30u;

static inline bool lightingHighBeamFunctionLitPure(const uint8_t data[8]) {
  return (data[LIGHTING_3F5_D4] & LIGHTING_3F5_FUNCTION_LIT_MASK) != 0u;
}

// (BODY, 0x3F6) VCFRONT_lightStatus - the second headlight report.
//
// DBC 1014 declares two 2-bit signals, VCFRONT_highBeamLeftStatus 4|2@1+ and
// VCFRONT_highBeamRightStatus 6|2@1+, i.e. d0 bits 5..4 and d0 bits 7..6, with
// VAL_ 1014 0 OFF / 1 ON / 2 FAULT / 3 SNA. On this car both 2-bit fields flip
// together and only byte 0 moves: a capture holds exactly two payload shapes,
// '05 00 00 14 B6 14 00 00' (off, both fields 0) and
// '55 00 00 14 B6 14 00 00' (on, both fields 1).
//
// TIMING - measured 2026-11-18, not assumed. Pairing every 0x3F5 key transition
// with the nearest 0x3F6 lamp transition (|dt| <= 200 ms, greedy one-to-one,
// segment and phase scoped) yields 17 pairs over four captures, and
// delta = t3F6 - t3F5 is POSITIVE in 17 of 17 (median +10 ms, mean +10.4,
// range +4..+15). This frame therefore LAGS the 0x3F5 mirror; it does not lead
// it. The earlier claim of a 5..13 ms lead had the sign backwards and is
// withdrawn. It is also far sparser - median gap 642..1010 ms against 85..100 ms
// for 0x3F5 - so at a 600 ms window roughly 40% of ticks find it already stale.
// Selection is therefore by timestamp (see lightingBeamReportPure), never by
// "this frame wins".
//
// The signal is tri-state-ish and the decoder keeps all four values, because
// FAULT and SNA must never be read as "the lamp is off" - that would turn a
// broken lamp into an endless retry stream.
static constexpr uint16_t LIGHTING_ID_VCFRONT_LIGHT_STATUS = 0x3F6;  // bus 0, read-only
static constexpr uint8_t LIGHTING_3F6_D0 = 0u;
static constexpr uint8_t LIGHTING_3F6_LEFT_BEAM_SHIFT = 4u;
static constexpr uint8_t LIGHTING_3F6_LEFT_BEAM_MASK = 0x03u;
static constexpr uint8_t LIGHTING_3F6_BEAM_OFF = 0u;
static constexpr uint8_t LIGHTING_3F6_BEAM_ON = 1u;
static constexpr uint8_t LIGHTING_3F6_BEAM_FAULT = 2u;
static constexpr uint8_t LIGHTING_3F6_BEAM_SNA = 3u;

static inline uint8_t lightingHighBeamLeftStatusPure(const uint8_t data[8]) {
  return (uint8_t)((data[LIGHTING_3F6_D0] >> LIGHTING_3F6_LEFT_BEAM_SHIFT) &
                   LIGHTING_3F6_LEFT_BEAM_MASK);
}

// 0x3F5 is meaningful as a boolean too: IDLE is the only "not lit" value, and
// INTERMITTENT (a flash in progress) plus LATCHED (steady beam) are the two
// states the car reports while it is honouring a beam demand.
//
// DAS_AUTO (3) is deliberately NOT "lit". It means the car's own beam assist
// has taken the lamp over on its own authority, not that our request landed, and
// treating it as success silently broke the top-up loop: the mirror said "on",
// the loop reset its allowance to zero every pass, and the moment the car
// dropped its decision the request was never re-sent - which is exactly the
// "forced high beam falls back to low beam after a while" report.
static inline bool lightingHighBeamMirrorLitPure(uint8_t state) {
  return state == LIGHTING_3F5_HIGH_BEAM_INTERMITTENT ||
         state == LIGHTING_3F5_HIGH_BEAM_LATCHED;
}

// The predicate the loop actually uses: d4 decides, and the mode byte only
// breaks the tie when no d4 has ever arrived.
//
// "Has a d4 been seen" is a TIMESTAMP question, not a value question. d4 was
// only ever observed as 0x84 / 0x94 / 0xA4 in 804 frames, so testing d4 != 0
// happened to work - but it conflates "the car has not spoken yet" with "the car
// said zero". The caller passes whether a d4 has ever arrived
// (lighting3F5D4SeenMs in lighting_features.h).
static inline bool lightingHighBeamLitPure(uint8_t state, uint8_t d4, bool d4Seen) {
  if ((d4 & LIGHTING_3F5_FUNCTION_LIT_MASK) != 0u) return true;
  if (d4Seen) return false;               // d4 seen and neither bit is set
  return lightingHighBeamMirrorLitPure(state);
}

// How long a feedback report stays believable. 0x3F5 is the dense one (median
// gap 85..100 ms in an AP segment) and 0x3F6 the sparse one (median gap
// 642..1010 ms), so a 600 ms window already finds 0x3F6 stale on a large share
// of ticks. Both windows are deliberately generous: a stale report is never
// allowed to trigger a resend, so the only cost of a wide window is one extra
// frame per window while the lamp is genuinely wrong.
static constexpr uint32_t LIGHTING_3F6_FRESH_MS = 600u;
static constexpr uint32_t LIGHTING_3F5_FRESH_MS = 600u;

// Floor under the feedback bypass. The bypass exists to cut the LATENCY of one
// recovery, not to raise the steady rate: without a floor a lamp that stays dark
// for a legitimate reason (daylight, a fault the car reports as ON) would put a
// frame on the wire on every main-loop tick. 20 ms is the same floor the stalk
// request uses and keeps the worst case at 50 frames a second, which is still
// only a tenth of the bus budget.
static constexpr uint32_t LIGHTING_3E9_FEEDBACK_MIN_MS = 20u;

// The AP gate: how long the last (CHASSIS, 0x399) DAS status stays believable.
//
// The gate used to be a plain latch: handle921 set `gateAPActive` on every 0x399
// and nothing ever expired it, so the moment the car stopped broadcasting (bus
// off, a stalled CAN A, Autopilot dropping off the bus) the module kept forcing a
// high beam for an Autopilot session that no longer existed. The owner saw that
// on the car -- "sometimes it is still injecting after AP dropped".
//
// 3000 ms matches R79_AP_DAS_FRESH_MS, the other place in this firmware that
// asks "is the DAS picture still current". The car broadcasts 0x399 every 100 ms
// while it is alive, so anything older than 3 s means the picture is gone.
static constexpr uint32_t LIGHTING_AP_GATE_FRESH_MS = 3000u;

// Which DAS_autopilotState counts as "Autopilot engaged".
//
// Measured, not assumed. Two on-car captures disagree on the number, and both
// are real:
//
//   2026-11-12 09:51  `ap 强制远光.csv`             (CHASSIS, 0x399) d0 = 4
//   2026-11-12 13:19  `ap 强制远光不生效.csv`        (CHASSIS, 0x399) d0 = 3
//
// Both segments have the car under Autopilot; the first one also lights the beam
// (0x3F5 reaches LATCHED), the second one reports `state 3 / 0 / 1` cycling with
// the beam never settling. A single-value gate therefore cannot work: it was
// pinned to 4 after the first capture, and the second capture is exactly the
// "现在不生效完全无效果" report that followed.
//
// So the gate uses the same set the rest of the firmware uses for "AP is
// engaged" (teslaApStateActivePure: 3/4/5/6). It is narrower than `gateAPActive`
// in one important way: it also requires the 0x399 picture to be fresh, which is
// what stops the injection after AP is cancelled - the owner's "偶尔发现AP状态
// 取消后依然在注入" complaint.
//
// TODO(verify): 5 and 6 were never observed on this car; they are accepted only
// because teslaApStateActivePure already treats them as engaged everywhere else.
static inline bool lightingApStateEngagedPure(uint8_t dasState) {
  return dasState == 3u || dasState == 4u || dasState == 5u || dasState == 6u;
}

static inline bool lightingApGateActivePure(bool gateLatched, bool dasValid,
                                            uint8_t dasState, uint32_t dasMs,
                                            uint32_t nowMs) {
  if (!gateLatched) return false;
  // dasMs == 0 means no (CHASSIS, 0x399) has ever been seen in this boot. That
  // cannot happen together with gateLatched on a real car - handle921 is what
  // latches both - so this branch only exists for the host harness, which drives
  // the latch directly. Expiring it would turn "no car attached" into "AP is
  // off", which is a different statement.
  if (dasMs == 0u) return true;
  if (!dasValid) return false;
  if ((uint32_t)(nowMs - dasMs) > LIGHTING_AP_GATE_FRESH_MS) return false;
  return lightingApStateEngagedPure(dasState);
}

// Closed loop for the forced high beam.
//
// The owner's report (2026-11-12): "the forced high beam still fails -- the car
// decides it does not need the beam right now and cancels it; add a top-up when
// that happens, and stop injecting if the driver turned the beam off by hand".
//
// The old code had the timer half of that (LIGHTING_3E9_REFRESH_MS re-assert plus
// the 20 ms feedback bypass) but no way to tell the two cancels apart, so it
// could only do one of two wrong things: keep re-asserting forever against a
// driver who wants the beam off, or give up and never recover from a single car
// cancel. Both were reported at different times.
//
// The loop below separates them by counting: a cancel we did not ask for is a
// fresh report that says dark while we still demand lit. Re-asserting once is the
// "top-up" the owner asked for. A cancel that survives LIGHTING_BEAM_TOPUP_LIMIT
// consecutive top-ups is treated as the driver's decision, the demand is dropped
// and the injection stops until the demand goes away and comes back.
static constexpr uint8_t LIGHTING_BEAM_TOPUP_LIMIT = 6u;

// How long a latched "the car cancelled us" verdict stands before the loop
// probes once more.
//
// The latch exists for a good reason: six unanswered top-ups mean our request is
// not what the car wants, and re-sending forever fights the driver. But the latch
// used to be released ONLY by the demand going away, and the AP/FSD demand is a
// latched condition - it can stay true for a whole drive. So one unlucky window
// during an engagement (a lamp that had not answered yet, a report that arrived
// before the first frame was on the wire, a tunnel) killed the feature until AP
// disengaged: `txOk3e9` stayed 0, `blocked` never moved, and the 2026-11-17
// capture shows exactly that - the switch was on, `DAS_autopilotState` was 3, the
// 0x3E9 template was present, and not one frame left the controller.
//
// The probe is deliberately ONE frame, not a fresh burst of six: a single 20 ms
// PULL is below the shape the lamp controller answers (the two working captures
// need three consecutive frames), so a driver who really turned the beam off
// never sees it, while a request the car has started accepting is picked up
// again immediately. A full burst every five seconds would flicker the beam.
static constexpr uint32_t LIGHTING_BEAM_SUPPRESS_MS = 5000u;

// "The car says the beam is not doing what we asked."
//
// This is the closure the module was missing. The demand stays on the wire
// every LIGHTING_3E9_REFRESH_MS, but the car re-broadcasts its own 0x3E9 (always
// decision = OFF, d2 bit6 = 0) on a different phase, so any window can be won by
// the car's copy and the lamp drops out - which is exactly the on-car report
// "the forced high beam goes out now and then". When a fresh report disagrees,
// the caller skips the throttle and re-asserts immediately.
//
// Only the NEWEST of the two reports may answer. 0x3F5 leads 0x3F6 by ~10 ms on
// every paired transition and refreshes about ten times more often, so ORing the
// two ("either frame says dark") let a 600 ms old 0x3F6 OFF veto a 0x3F5 that
// had just reported the lamp lit - the exact failure this closure exists to
// prevent. Ties go to 0x3F5, whose d4 is the lamp-level bit.
//
// Only the beam demand takes part: 0x3F5 also carries a dynamic-brake state, but
// that bit is not decoded here (no capture of a working request exists), so the
// brake path keeps its plain periodic re-assert.
static inline bool lightingHighBeamFeedbackLostPure(bool demandBeamLit,
                                                    uint32_t nowMs,
                                                    uint32_t status3f6Ms,
                                                    uint8_t status3f6,
                                                    uint32_t mirror3f5Ms,
                                                    uint8_t mirror3f5,
                                                    uint8_t mirror3f5d4 = 0u,
                                                    bool mirror3f5d4Seen = false) {
  if (!demandBeamLit) return false;
  const bool f6Fresh = status3f6Ms != 0u &&
                       (uint32_t)(nowMs - status3f6Ms) <= LIGHTING_3F6_FRESH_MS;
  const bool f5Fresh = mirror3f5Ms != 0u &&
                       (uint32_t)(nowMs - mirror3f5Ms) <= LIGHTING_3F5_FRESH_MS;
  // Newest wins; a tie belongs to 0x3F5. A stale 0x3F6 must never veto a fresh
  // 0x3F5, which is what the old "0x3F6 first" ordering did.
  if (f6Fresh && (!f5Fresh || (int32_t)(status3f6Ms - mirror3f5Ms) > 0)) {
    // FAULT and SNA are not "off": a broken or unavailable lamp must not turn
    // into an endless resend stream.
    return status3f6 == LIGHTING_3F6_BEAM_OFF;
  }
  if (f5Fresh) {
    return !lightingHighBeamLitPure(mirror3f5, mirror3f5d4, mirror3f5d4Seen);
  }
  return false;
}

// Pick the newest believable "is the lamp actually lit" report.
//
// Two frames say it and neither is authoritative on its own: 0x3F6
// VCFRONT_highBeamLeftStatus is the lamp's own state, 0x3F5
// highBeamControlState plus d4 is what the controller decided. They are not
// simultaneous and not the same rate - measured over four captures, 0x3F6
// follows 0x3F5 by +4..+15 ms (median +10) in 17 of 17 paired transitions, and
// 0x3F5 refreshes every ~85..100 ms against ~642..1010 ms for 0x3F6. "Newest
// wins" is therefore the only ordering that cannot resurrect a stale answer,
// and equal timestamps go to 0x3F5, whose d4 bit is the lamp level rather than
// the lamp's own self-report. A stale report is never used either: "the car has
// not spoken" must not be mistaken for "the car said no".
static inline void lightingBeamReportPure(uint32_t nowMs, uint32_t status3f6Ms,
                                          uint8_t status3f6, uint32_t mirror3f5Ms,
                                          uint8_t mirror3f5, bool &fresh,
                                          bool &lit, bool &cancel,
                                          uint8_t mirror3f5d4 = 0u,
                                          bool mirror3f5d4Seen = false) {
  fresh = false;
  lit = false;
  cancel = false;
  const bool f6Fresh = status3f6Ms != 0u &&
                       (uint32_t)(nowMs - status3f6Ms) <= LIGHTING_3F6_FRESH_MS &&
                       status3f6 != LIGHTING_3F6_BEAM_SNA;
  const bool f5Fresh = mirror3f5Ms != 0u &&
                       (uint32_t)(nowMs - mirror3f5Ms) <= LIGHTING_3F5_FRESH_MS;
  // 0x3F6 answers only when it is strictly newer; a tie belongs to 0x3F5's d4.
  if (f6Fresh && (!f5Fresh || (int32_t)(status3f6Ms - mirror3f5Ms) > 0)) {
    // Only an explicit OFF is evidence of a cancel. FAULT ("the lamp is not
    // working") and SNA are not: a broken lamp must keep the plain periodic
    // re-assert instead of turning into a top-up stream the limit has to stop.
    fresh = true;
    lit = (status3f6 != LIGHTING_3F6_BEAM_OFF);
    cancel = !lit;
    return;
  }
  if (f5Fresh) {
    fresh = true;
    lit = lightingHighBeamLitPure(mirror3f5, mirror3f5d4, mirror3f5d4Seen);
    // 0x3F5 is the CONTROLLER's decision, and DAS_AUTO (3) is a mode, not a
    // verdict: the lamp can be dark because automatic high beam decided so,
    // because our request has not been accepted yet, or because the driver
    // cancelled. Only an explicit IDLE is the driver's cancellation. Counting
    // DAS_AUTO as a cancel is what made AP/FSD forced high beam stop after a few
    // ticks: "blocked" never moved, txOk3e9 stayed 0, and every later tick took
    // the "suppressed" early-out. The 2026-11-15 capture is entirely
    // DAS_AUTO/IDLE, and the feature sent nothing.
    cancel = (mirror3f5 == LIGHTING_3F5_HIGH_BEAM_IDLE);
  }
}

// The loop state is a pure struct so the host suite can drive it without a car.
struct LightingBeamLoopPure {
  uint8_t topups;         // consecutive top-ups sent since the last "lit" report
  bool suppressed;        // the driver's cancel was accepted; stop injecting
  uint32_t suppressedMs;  // millis() when the latch was armed, 0 when it is clear
};

// Release an expired latch. Called by the service before the observe step, while
// the demand is still live, so a latch can never outlive
// LIGHTING_BEAM_SUPPRESS_MS. `demand` is required here: when the demand is gone
// the observe step clears the whole struct anyway, and touching it here would
// reset a counter the caller is still using.
static inline void lightingBeamLoopExpirePure(LightingBeamLoopPure &s, bool demand,
                                              uint32_t nowMs) {
  if (!demand) return;
  if (!s.suppressed) return;
  if (s.suppressedMs != 0u &&
      (uint32_t)(nowMs - s.suppressedMs) < LIGHTING_BEAM_SUPPRESS_MS) {
    return;
  }
  s.suppressed = false;
  s.suppressedMs = 0u;
  // One frame is allowed through before the limit trips again. Leaving the
  // counter at the limit would re-latch on the next report without ever putting
  // anything on the wire, which is the dead state this function exists to end.
  s.topups = (uint8_t)(LIGHTING_BEAM_TOPUP_LIMIT - 1u);
}

// Fold one fresh report into the loop. Returns true when a top-up should be sent
// this tick (the caller still owns the transmit and the throttle).
static inline bool lightingBeamLoopObservePure(LightingBeamLoopPure &s, bool demand,
                                               bool reportFresh, bool reportLit,
                                               bool reportCancel) {
  if (!demand) {
    // The demand itself went away: forget everything, so a later engagement
    // starts from a clean slate and is allowed its own top-ups.
    s.topups = 0u;
    s.suppressed = false;
    s.suppressedMs = 0u;
    return false;
  }
  if (s.suppressed) return false;
  if (!reportFresh) return false;
  if (reportLit) {
    // The lamp agrees with us: the beam is holding, nothing to top up.
    s.topups = 0u;
    return false;
  }
  if (!reportCancel) {
    // The report is fresh but says neither "lit" nor "the driver turned it off"
    // - typically 0x3F5 state 3 (DAS_AUTO), which is a mode and not a verdict.
    // That is not a cancel, so there is nothing to top up and, crucially,
    // nothing to charge against the limit.
    return false;
  }
  if (s.topups >= LIGHTING_BEAM_TOPUP_LIMIT) {
    // It stayed dark through every top-up we sent - that is a decision, not a
    // race we are losing.
    s.suppressed = true;
    return false;
  }
  // NOTE: the counter is NOT advanced here. It is advanced by
  // lightingBeamLoopTopupSentPure below, once the frame has actually left the
  // controller. Charging the limit on a request the bus refused (or on a stall
  // where no template exists yet) used to burn all six attempts without a single
  // frame on the wire and then latch `suppressed` for the rest of the session.
  return true;
}

// Called by the service once a top-up frame was actually transmitted. Only then
// does one attempt get charged against LIGHTING_BEAM_TOPUP_LIMIT.
static inline void lightingBeamLoopTopupSentPure(LightingBeamLoopPure &s) {
  if (s.suppressed) return;
  if (s.topups < 0xFFu) s.topups++;
}

// ---------------------------------------------------------------------------
// AP forced high beam 2 (0x249) - DISABLED REFERENCE, replaced 2026-11-18
// ---------------------------------------------------------------------------
//
// The 2026-11-18 reply-loop model that used to live here (a 3-frame pulled burst
// per car frame, 20 ms spacing, "the switch is the authorisation, the stalk is
// the control") is retired. The owner's instruction was to rebuild the feature
// on Albert V12's 0x249 transaction model instead, so the live implementation
// now lives in albert_v12_light_pure.h / albert_v12_light_runtime.h and nothing
// in this file participates in its demand, framing or transmission any more.
//
// It is kept as a comment rather than as code on purpose: requirement 3 of the
// migration is that the old constants (3 frames, 20 ms, 2000 ms) must not be
// reachable from the new path, and code that still compiles is code that can
// still be wired back in by accident.

// ---------------------------------------------------------------------------
// Route 1 (0x3E9) recovery: push the stalk the way the car itself does
// ---------------------------------------------------------------------------
//
// The 0x3E9 writer only *asks* the DAS for the high beam. On the car
// (CAN_Research_Capture 6.csv, segments "ap 强制远光" / "强制远光") the car
// answers a decision-ON stream with nothing: our frames carry
// DAS_highLowBeamDecision = ON every 20 ms for whole segments and the lamp still
// never comes on. The only thing that ever lights this car's high beam is a real
// stalk action - including one this module injected (CAN_Research_Capture 5.csv,
// the successful "远光爆闪 2" waveform, is nothing but injected 0x249 pulls).
//
// What the car itself sends when the driver pushes the stalk away, measured on
// CAN_Research_Capture 4(4).csv at t = 1437 / 1477 / 1527 / 1577 ms, is a train
// of FOUR frames, 50 ms apart, with the rolling counter advancing by one on each
// (0x04_21, 0xC6_22, 0x3F_23, 0x3F_24). One frame is not the gesture - the body
// controller ignores a single frame - which is exactly why the previous
// one-frame-per-drop writer never relit anything. So this route sends the same
// four-frame train, counter continuous. 2026-11-18: the recovery train is a
// burst INSIDE one car slot, not one frame per slot. Measured on 51 captured
// segments: the longest run of our PUSH frames that ever survived in the merged
// CAN 1 stream was 1 (11 runs, 0 of them lit the lamp), while every
// driver-generated run that reached LATCHED was 4 or 5 contiguous frames
// (24 runs of 4 -> 33% lit, 16 of 5, 6 of 3 -> 17%) and no run of 1 or 2 ever
// lit the lamp. The body controller keeps broadcasting its own IDLE on 50 ms
// boundaries, so several frames inside a single 50 ms slot is the only way to
// occupy consecutive positions - a pair sent 20 ms apart did produce a merged
// run of 2 in CAN_Research_Capture 3(4).csv, and a triple produced a run of 3.
static constexpr uint8_t LIGHTING_AP1_PUSH_FRAMES = 4u;
// The car's own train is 50 ms per frame; our burst has to fit inside one slot,
// so the spacing is an order of magnitude tighter.
static constexpr uint32_t LIGHTING_AP1_PUSH_SPACING_MS = 10u;

// ---------------------------------------------------------------------------
// Bounded top-up retry (ticket "AP forced high beam: the first push does not
// light" 2026-11-19, items T1-T4).
//
// Why one train per dark episode was wrong: the DAS needs 1.5-4.9 s to accept a
// decision change, and while DAS_ahlbOverride is still set the body controller
// reads the same physical push as "turn AHB on". A single train fired on the
// first dark report therefore lands entirely inside the window where the car
// cannot act on it, and the episode is then marked spent for the rest of the
// darkness - which is exactly the owner's report "the first push does nothing,
// after several pushes it works".
//
// So a dark episode gets at most LIGHTING_AP1_TOPUP_MAX_ATTEMPTS trains spaced
// by LIGHTING_AP1_TOPUP_RETRY_MS, and the episode ends the moment the lamp is
// reported lit. The retry is bounded on purpose: an unbounded loop on the stalk
// channel reads to the body controller as a jammed lever.
static constexpr uint32_t LIGHTING_AP1_TOPUP_RETRY_MS = 300u;
static constexpr uint8_t LIGHTING_AP1_TOPUP_MAX_ATTEMPTS = 8u;
// A car push still on the wire owns the channel. The window is measured from the
// last PUSH frame seen (not from the rising edge) because the car's own train
// keeps delivering frames for ~150 ms after the edge.
static constexpr uint32_t LIGHTING_AP1_CAR_PUSH_ACTIVE_MS = 120u;
// T2: after the car stops pushing, wait before injecting, so our frames never
// interleave with the tail of the driver's own train.
static constexpr uint32_t LIGHTING_AP1_CAR_PUSH_SETTLE_MS = 100u;
// "The lamp came up within two seconds of a train" is the only survival
// criterion (T3): everything else can look healthy while the beam stays off.
static constexpr uint32_t LIGHTING_AP1_TOPUP_LIT_WINDOW_MS = 2000u;

// Rollback profiles (ticket 7). cfg[8] bits0..1, which no previous build ever
// wrote, so a profile saved by an older build reads back as 0 - the retry
// behaviour is the default without migrating anything.
static constexpr uint8_t LIGHTING_TOPUP_PROFILE_RETRY = 0u;
static constexpr uint8_t LIGHTING_TOPUP_PROFILE_OFF = 1u;
static constexpr uint8_t LIGHTING_TOPUP_PROFILE_LEGACY_ONCE = 2u;
static constexpr uint8_t LIGHTING_CFG_TOPUP_PROFILE_MASK = 0x03u;

struct LightingAp1PushPure {
  bool spent;            // this dark episode has used up its attempts
  bool awaitingLit;      // a train went out and no lit report has arrived since
  uint8_t left;          // frames of the current train still owed
  uint8_t attempts;      // trains started in this dark episode
  uint32_t lastTrainMs;  // when the current (or last) train started
  uint32_t lastLitMs;    // when the lamp was last reported lit
};

// One-shot transitions the caller turns into counters/diagnostics.
struct LightingAp1TopupEventPure {
  bool started;     // a new train was armed on this call
  bool suppressed;  // a train was held back by the driver's own push
  bool lit;         // the lamp came up after a train (the survival criterion)
};

static inline void lightingAp1PushResetPure(LightingAp1PushPure &s) {
  s = LightingAp1PushPure{};
}

// Called once a push frame actually left the controller.
static inline void lightingAp1PushSentPure(LightingAp1PushPure &s) {
  if (s.left != 0u) s.left--;
}

// Decide whether this tick owes a stalk frame.
//
// reportFresh/reportLit carry the lamp verdict (0x3F5/0x3F6, see
// lightingBeamReportPure); carPushActive/lastCarPushMs carry the driver's own
// push seen on 0x249; profile selects retry / off / legacy-one-shot.
//
// Suppressing under a car push must NOT consume the episode - that is the whole
// point of T1: the train is being saved for after the car's semantics switch.
static inline bool lightingAp1TopupDuePure(LightingAp1PushPure &s, bool demand,
                                           bool reportFresh, bool reportLit,
                                           bool carPushActive,
                                           uint32_t lastCarPushMs,
                                           uint32_t nowMs, uint8_t profile,
                                           LightingAp1TopupEventPure *ev) {
  if (ev != nullptr) *ev = LightingAp1TopupEventPure{};
  if (!demand || profile == LIGHTING_TOPUP_PROFILE_OFF) {
    lightingAp1PushResetPure(s);
    return false;
  }
  // A lit report closes the episode. A train already in flight still finishes:
  // the car's own train does not stop at the first lit report either, and
  // cutting ours short is what makes the body controller see a single stray
  // frame instead of a push.
  if (reportFresh && reportLit) {
    if (s.awaitingLit) {
      s.awaitingLit = false;
      if (s.lastTrainMs != 0u &&
          (uint32_t)(nowMs - s.lastTrainMs) <= LIGHTING_AP1_TOPUP_LIT_WINDOW_MS &&
          ev != nullptr) {
        ev->lit = true;
      }
    }
    s.lastLitMs = nowMs != 0u ? nowMs : 1u;
    if (s.left == 0u) {
      s.spent = false;
      s.attempts = 0u;
      s.lastTrainMs = 0u;
    }
    return s.left != 0u;
  }
  // A train in flight always finishes, whatever the report says.
  if (s.left != 0u) return true;
  if (s.spent) return false;
  // The driver's own push owns the channel (T1).
  if (profile == LIGHTING_TOPUP_PROFILE_RETRY) {
    if (carPushActive) {
      if (ev != nullptr) ev->suppressed = true;
      return false;
    }
    if (lastCarPushMs != 0u &&
        (uint32_t)(nowMs - lastCarPushMs) < LIGHTING_AP1_CAR_PUSH_SETTLE_MS) {
      if (ev != nullptr) ev->suppressed = true;
      return false;
    }
  }
  if (s.attempts != 0u) {
    if (profile == LIGHTING_TOPUP_PROFILE_LEGACY_ONCE) {
      s.spent = true;
      return false;
    }
    // Later attempts only fire on evidence that the lamp is actually dark.
    if (!reportFresh) return false;
    if ((uint32_t)(nowMs - s.lastTrainMs) < LIGHTING_AP1_TOPUP_RETRY_MS) return false;
    if (s.attempts >= LIGHTING_AP1_TOPUP_MAX_ATTEMPTS) {
      s.spent = true;
      return false;
    }
  }
  // First train of the episode: it fires even without a report, otherwise a
  // demand switched on before the first 0x3F5/0x3F6 would wait forever.
  s.attempts++;
  s.lastTrainMs = nowMs != 0u ? nowMs : 1u;
  s.awaitingLit = true;
  s.left = LIGHTING_AP1_PUSH_FRAMES;
  if (ev != nullptr) ev->started = true;
  return true;
}

// UI_vehicleModes - the vehicle's answer to a maintenance-mode request.
// Receive-only, never transmitted: F5 writes 0x339 d5 bit7 (a request) and the
// car reports back through this frame's d0 bit3 (`UI_serviceMode`, DBC 644
// `3|1@1+`), which is a different direction with its own signal. Albert's
// receive filter (0x481356b8) accepts exactly this pair {0x339, 0x284} and
// compares the echoed bit rather than our own transmitted one.
static constexpr uint16_t LIGHTING_ID_UI_VEHICLE_MODES = 0x284;   // bus 1, read-only

// ---------------------------------------------------------------------------
// Bit assignments
// ---------------------------------------------------------------------------

// 0x3C2 VCLEFT_SWITCH payload bytes 5, 6 and 7.
// The high-beam request replicated by F1 and F2 lives in d5 bits 7..6 of the
// MUX1 multiplex slot. One pull of the left stalk toward the driver raises that
// request for a single body-frame round and the body controller answers with a
// single high-beam flash (flash-to-pass). Holding the stalk the other way asks
// for a steady beam; that is a different request and is not generated here.
// Evidence: the TSL8 write block at 0x41a4 and its TSL9 twin at 0x41b0 set
// d5 = (d5 & 0x3F) | 0x80 and are only reached for the MUX1 payload, while
// neither image ever writes d6 bit5 - the previous assignment is retired.
// TODO(verify): an on-car capture of this module's own request frame is still
// outstanding.
static constexpr uint8_t LIGHTING_3C2_D5 = 5u;
static constexpr uint8_t LIGHTING_3C2_HIGH_BEAM_CLEAR_MASK = 0x3Fu;  // d5 bits 7..6
static constexpr uint8_t LIGHTING_3C2_HIGH_BEAM_SET = 0x80u;         // d5[7:6] = 0b10
static constexpr uint8_t LIGHTING_3C2_HIGH_BEAM_MUX_SLOT = 1u;       // d0 bits 1..0
// Byte 7 of a module-composed 0x3C2 is opaque: it is NOT a checksum and must be
// copied through verbatim. Stock mux0 frames carry 0x45, 0x55 or 0x85 and stock
// mux1 frames 0x80, and two frames with identical d0..d6 were captured carrying
// different byte-7 values, so it moves with hidden state this module cannot see.
static constexpr uint8_t LIGHTING_3C2_D7 = 7u;
// TODO(verify): byte6 bit4 is the "heads + high beam together" companion bit
// used only when byte25 bit2 asks for both lamps to strobe. In the reference
// image that write belongs to the turnProtocol 7/8 branch, so on this car
// (turnProtocol 4) it is inert and only kept for the opt-in toggle.
static constexpr uint8_t LIGHTING_3C2_BOTH_LAMPS_MASK = 0x10u;  // d6 bit4
static constexpr uint8_t LIGHTING_3C2_D6 = 6u;
// Manual rear-fog mirror: byte0 bit3 is the lamp mode the body controller
// publishes on the MUX1 slot. In the on-car capture the car's own rear-fog
// press leaves MUX1 29 55 00 00 00 00 00 80 behind while a front-fog press
// returns the identifier to the MUX0 payload, so raising bit3 on MUX1 is the
// same request the physical button makes - no 0x273 frame is involved.
static constexpr uint8_t LIGHTING_3C2_D0 = 0u;
static constexpr uint8_t LIGHTING_3C2_REAR_FOG_BUTTON_MASK = 0x08u;  // d0 bit3

// 0x273 UI_vehicleControl payload byte 2 (d2).
// TODO(verify): the task document specifies d2 bit7 (0x80) for
// UI_rearFogSwitch, while an earlier disassembly pass reported d0 bit3 and
// d2 bit7 in the same handler block. d2 bit7 is used here because it is the
// value the specification confirms.
static constexpr uint8_t LIGHTING_273_REAR_FOG_MASK = 0x80u;  // d2 bit7
static constexpr uint8_t LIGHTING_273_D2 = 2u;
// The reference merge layer (0x4ff259c6) copies the whole template and also
// writes byte0 with "bVar6 |= 3", which was mistaken here for an owner marker.
// byte0 is not a marker: per DBC BO_ 627 UI_vehicleControl it is
//   bit 0      UI_accessoryPowerRequest
//   bits 1..2  UI_lightSwitch (0 AUTO_SNA, 1 ON, 2 PARKING, 3 OFF)
// so OR-ing 0x03 asks the body controller for accessory power and flips the
// light switch from AUTO_SNA to ON on every single pulse frame. A twenty frame
// burst therefore spoofed twenty "power on, switch the lights on" requests; on
// the car that ended with the lights being switched off and the driver profile
// recall firing (0x285 UI_driverProfileRecall moved its index from 0x61/0x02 to
// 0x71/0x12, CAN_Research_Capture 11 segment 3 at t = 1097 ms, right after the
// 0x3E3 light status collapsed to 00 00 00 00 at t = 1024 ms). Every captured
// stock 0x273 frame carries d0 = 0x81 and never asks for a light switch change,
// so the burst now edits byte2 only and passes byte0 through untouched.
static constexpr uint8_t LIGHTING_273_D0 = 0u;

// 0x339 VCSEC_authentication: byte5 bit7 is the service-mode request.
// TODO(verify): the task document described a constructed frame (d5 = 0x80 and
// every other byte 0), but the real bus carries 05 F1 FE 00 80 02 80 08 and the
// reference state machine at 0x481351cc keeps the received template and only
// raises bit7 of byte5. Mirroring the live frame is therefore the safer edit;
// the all-zero shape is kept as the fallback for when no template was seen.
static constexpr uint8_t LIGHTING_339_D5 = 5u;
static constexpr uint8_t LIGHTING_339_SERVICE_MODE_MASK = 0x80u;
static constexpr uint8_t LIGHTING_339_D5_CLEAR_MASK = 0x7Fu;

// 0x284 UI_vehicleModes d0 bit3 = UI_serviceMode (DBC 644 `3|1@1+`). Same bit
// number as UI_factoryMode's byte, so the mask is spelled out rather than
// reusing a shift.
//
// The task note claimed this frame is DLC 4; the car actually broadcasts 8
// bytes (captured 30 00 00 00 40 08 <cnt> <sum> on both BODY and CHASSIS). The
// decoder therefore requires only one byte and never assumes a length, so both
// shapes are accepted.
static constexpr uint8_t LIGHTING_284_D0_SERVICE_MODE_MASK = 0x08u;

// F4 用到的 0x3E9 DAS_bodyControls 载荷字节下标。
//
// 车自身约每 500 ms 广播一次，实测载荷形如 F1 08 20 00 00 00 <cnt> <sum>：
// d6 的 bit7..4 是每帧 +1 的滚动计数器（0xF0 之后回绕到 0x00），d7 是加和校验，
// d1 静止时为 0x08。车身控制器会丢弃「计数器没有前进」的镜像帧，所以本模块每次
// 组帧前都要先把 d6 的计数器推进一格，再重算 d7。
//
// 注意：本模块只写 d2 bit6（DAS_dynamicBrakeLightRequest）和远光决策那两个位，
// 绝不写 d0 —— d0 的低半字节是 DAS_hazardLightRequest，写它就是点亮双闪。
static constexpr uint8_t LIGHTING_3E9_D0 = 0u;
static constexpr uint8_t LIGHTING_3E9_D1 = 1u;
static constexpr uint8_t LIGHTING_3E9_D2 = 2u;
static constexpr uint8_t LIGHTING_3E9_D3 = 3u;
// DBC 1001 DAS_dynamicBrakeLightRequest = 22|1 -> d2 bit6. This is the whole
// of the reference "dynamic brake light": the module only raises the request
// bit and the body controller runs the flash pattern itself.
static constexpr uint8_t LIGHTING_3E9_DYNAMIC_BRAKE_MASK = 0x40u;
// DBC 1001 DAS_headlightRequest = 0|2 -> d0 bits 1..0, the "free-will high beam"
// request of the reference firmware's 0x3E9 composer (0x7bd4):
//   0x7c92  lbu a5,3(s0)      ; s0 is the FRAME base, so 3(s0) is data[0]
//   0x7c96  andi a3,a5,3      ; already 1 ?
//   0x7c9e  andi a5,a5,-4     ; clear bits 1..0
//   0x7ca0  ori  a5,a5,1      ; DAS_headlightRequest = 1 (ON)
// Nothing in this firmware writes that pair any more: the free-will route went
// with the AP-2 rework ("AP forced high beam 2" now holds the stalk channel), so
// the constants that described it are gone too. The warning below still stands,
// because d0 is the byte a careless edit is most likely to touch:
// d0 bits 3..2 are DAS_hazardLightRequest - writing the whole low nibble would
// switch the hazard lights on. Only bits 1..0 may ever be touched there.
// DBC 1001 DAS_highLowBeamDecision = 11|2, so the decision is d1 bits 3..4 and
// "head lamps on" is the value 2 (binary 10) sitting in bit4 with bit3 clear.
static constexpr uint8_t LIGHTING_3E9_HIGH_BEAM_CLEAR = 0x18u;
static constexpr uint8_t LIGHTING_3E9_HIGH_BEAM_SET = 0x10u;
// DBC 1001 DAS_ahlbOverride = 24|1 -> d3 bit0. The reference clears it in the
// same write as the decision, otherwise the body controller keeps its own
// automatic high-beam answer and the decision above never takes effect.
static constexpr uint8_t LIGHTING_3E9_AHLB_OVERRIDE_MASK = 0x01u;
// 2026-11-18 (owner, m36022): the three experiment switches that used to live
// in cfg[6] bits 4..6 are gone from the panel and from this struct, and the
// behaviour they used to select is now the only behaviour:
//   * DAS_ahlbOverride (0x3E9 d3 bit0) is ALWAYS cleared while this module
//     drives the beam, so automatic high beam cannot take the lamp back. The old
//     "keep the car's own bit" arm is retired - the capture showed the beam being
//     handed back within 10 ms whenever that bit survived.
//   * the 0x249 channel is ALWAYS open to this module. The old "inject 0x249"
//     switch made the whole recovery path silent, which is exactly the state a
//     firmware update could have left the operator in.
//   * the Autopilot gate is ALWAYS required. Running the forced beam outside AP
//     is what left a permanent PULL demand on the stalk with nothing to stop it.
// The bits are still cleared on encode (see lightingConfigEncodePure) so a
// profile saved by the previous build cannot resurrect any of the three.
// d6 bits 7..4: rolling frame counter, wraps 0xF0 -> 0x00 on the car.
static constexpr uint8_t LIGHTING_3E9_D6 = 6u;
// d7 carries the additive checksum (id high + id low + d0..d6). The body
// controller drops frames whose checksum does not match, so every edit has to
// refresh it - confirmed against every 0x3E9 frame of the on-car captures.
static constexpr uint8_t LIGHTING_3E9_D7 = 7u;

// Echo window for 0x3E9, same idea as LIGHTING_249_SELF_ECHO_MS below.
//
// This module rewrites d6 bits 7..4 (the rolling counter) and d7 (the additive
// checksum) before every transmit, so the generic byte-for-byte compare can
// never recognise our own frame coming back. The window is far below the car's
// own 500 ms broadcast period and the compare ignores d6/d7, so a genuine car
// frame is only ever swallowed when it matches us on d0..d5 - and in that case
// it carries exactly the bytes we just sent.
static constexpr uint32_t LIGHTING_3E9_SELF_ECHO_MS = 200u;

// 0x3E3 rear-fog lamp state, receive-only. Byte 1 bit 0 is the lamp the car
// reports after a 0x273 d2 bit7 request; the reference firmware reads it and
// never writes the frame, so this module only mirrors it for the panel.
static constexpr uint8_t LIGHTING_3E3_D1 = 1u;
static constexpr uint8_t LIGHTING_3E3_LAMP_MASK = 0x01u;

// ---------------------------------------------------------------------------
// Configuration decode (cfg[n] = App byte(24 + n))
// ---------------------------------------------------------------------------

// What a strobe beat asks its caller to do. IDLE means "write nothing at all".
// The high-beam strobe keeps reporting these through lightingHs2BeatState.
static constexpr uint8_t LIGHTING_HS_STATE_IDLE = 0u;
static constexpr uint8_t LIGHTING_HS_STATE_ON = 1u;
static constexpr uint8_t LIGHTING_HS_STATE_OFF = 2u;


struct LightingConfigPure {
  // cfg[1] bits0..1 used to carry the reference firmware's strobe speed level
  // (P+1 bits0..1) and cfg[1] bit3 used to carry the FSD forced high beam
  // switch. Both features are gone at the owner's request (2026-11-16): the
  // strobe no longer has a speed picker and FSD forcing was removed outright,
  // so decode ignores these bits and encode writes them back untouched - a
  // stored 1 in an old profile can never bring either behaviour back.
  // cfg[6] bit3: "AP forced high beam 2" - AP-only high beam over (BODY, 0x249),
  // the channel a real driver pull uses. It holds a steady PULL while the
  // driver-assistance system is engaged and re-asserts the request when the
  // lamp drops. It is a switch of its own on purpose: cfg[7] bits 4..5 carry
  // the App's `apHighBeam` dropdown, which is App-only and a display value
  // here, so gating on it would silently disable this feature for every
  // web-only user with nothing on the panel to explain why.
  bool apForcedHighBeam2;
  // cfg[6] bits 4..6 are retired, 2026-11-18 (owner, m36022). They used to carry
  // the AP-gate switch, the AHB-override A/B and the 0x249 silence switch; all
  // three are gone from the panel and the behaviour they chose is now fixed (see
  // the retirement note above LIGHTING_3E9_HIGH_BEAM_CLEAR). The bits are written
  // 0 on every save so an older profile cannot bring any of them back.
  // cfg[7] bits4..5: the operator's `apHighBeam` choice (App byte 31: 0 off,
  // 1 legacy AP, 2 free-will follow), reported for display under the App-facing
  // name so the JSON field and the App byte stay recognisable. READ-ONLY: the
  // panel dropdown that briefly wrote these bits went away with the AP high
  // beam modes (owner request 2026-11-19), and the encoder passes them back
  // verbatim, so only the App can change them.
  uint8_t newApHighBeam;  // cfg[7] bit4-5: 0 off, 1 legacy AP, 2 follow mode
  uint8_t rearFogStrobe;  // cfg[7] bit6: gate the 0x273 d2 bit7 flash burst
  // cfg[7] bit7 is retired. It used to select a separate "pilot pulse" sender for
  // the same 0x273 d2 bit7 request; the owner had it removed, and the 20-flash
  // burst above is now the single rear-fog sender. The bit is neither decoded nor
  // written any more, so saving settings clears whatever an older build left.
  uint8_t maintenance;    // cfg[4] bit3
  // cfg[7] exactly as it was read. Only bit6 is owned by this firmware (the
  // rear-fog strobe gate); everything else is the operator's App image and must
  // survive a decode/encode round trip untouched.
  uint8_t raw7;

  // cfg[5] bit0-1: the reference dynamic brake light, renamed on the panel to
  // "dynamic high-mount lamp". 0 off, 1 light press, 2 hard press. The value is
  // compared with == (never masked), exactly like the reference switch. This is
  // now the only owner of 0x3E9 d2 bit6: the old cfg[9] pulse train that used to
  // be OR-arbitrated against it is gone.
  uint8_t dynHighLamp;
  // cfg[6] bit0: impersonate the AP high-beam decision on 0x3E9 while AP is on.
  bool apForcedHighBeam;
  // cfg[2] bit0: the high-beam strobe ("远光爆闪"). It holds the stalk pulled
  // (high beam latched on) and flips one release frame every 70 ms so the beam
  // goes dark for 70 ms. The arm/disarm gesture is three quick stalk pulls to
  // start and one more pull to stop, handled in lighting_features.h. It owns the
  // whole 0x249 writer while it is on.
  bool hsStrobe2;
  // cfg[8] bits0..1: how the route-1 (0x3E9) recovery train behaves after the
  // lamp drops. 0 = bounded retry (default, the 2026-11-19 ticket), 1 = off
  // (reproduces the pre-fix behaviour of sending nothing), 2 = legacy one-shot
  // (one train per dark episode, the behaviour the ticket says does not work on
  // the first push). cfg[8] was never written by any earlier build, so an older
  // profile reads back as 0 and gets the new default without a migration.
  uint8_t topupRetryProfile;
};

// cfg holds at least 10 bytes (cfg[0] = App byte24 ... cfg[9] = App byte33).
static inline LightingConfigPure lightingConfigDecodePure(const uint8_t cfg[10]) {
  LightingConfigPure out = {};
  if (cfg == nullptr) return out;
  out.newApHighBeam = (uint8_t)((cfg[7] >> 4) & 0x03u);
  out.rearFogStrobe = (uint8_t)((cfg[7] >> 6) & 0x01u);
  out.raw7 = cfg[7];
  out.maintenance = (uint8_t)((cfg[4] >> 3) & 0x01u);
  out.dynHighLamp = (uint8_t)(cfg[5] & 0x03u);
  out.apForcedHighBeam = (cfg[6] & 0x01u) != 0u;
  out.hsStrobe2 = (cfg[2] & 0x01u) != 0u;
  out.apForcedHighBeam2 = (cfg[6] & 0x08u) != 0u;
  out.topupRetryProfile = (uint8_t)(cfg[8] & LIGHTING_CFG_TOPUP_PROFILE_MASK);
  return out;
}

// Encode back to the three bytes the decoder reads, so the web layer can keep
// a single shared representation with the App/BLE contract.
static inline void lightingConfigEncodePure(const LightingConfigPure &in, uint8_t cfg[10]) {
  if (cfg == nullptr) return;
  // cfg[1] is now App-owned. Bits0..1 used to hold the strobe speed level and
  // bit3 the FSD forced high-beam switch; both features are gone, so neither is
  // written any more. Bit2 (the retired low-beam follow gate) is the exception:
  // it is written 0, so a profile saved by a build that still had that feature
  // can never bring the behaviour back. Every other bit survives the round trip
  // exactly as it was read.
  cfg[1] = (uint8_t)(cfg[1] & (uint8_t)~0x04u);
  cfg[4] = (uint8_t)((cfg[4] & (uint8_t)~0x08u) | ((in.maintenance & 0x01u) ? 0x08u : 0x00u));
  // This function owns exactly ONE bit of cfg[7]: bit6, the rear-fog strobe
  // gate. Every other bit is written back exactly as it was read, because they
  // belong to the operator's mini-program image (App byte 31): bit3 is its
  // `onlyOpenAP`, bits4..5 are `apHighBeam`, bit7 is retired but may still hold
  // an older build's value. Rebuilding the byte field by field (what an earlier
  // revision did) cleared bits0..3 and bit7 on every save, i.e. every settings
  // round-trip from the web panel silently flipped App switches off.
  cfg[7] = (uint8_t)((in.raw7 & (uint8_t)~0x40u) |
                     ((in.rearFogStrobe & 0x01u) << 6));
  // cfg[9] is no longer interpreted at all (the old brake pulse train is gone).
  cfg[5] = (uint8_t)(in.dynHighLamp & 0x03u);
  // cfg[6] bits1 and 2 used to carry the retired stalk-gesture and body-bus
  // reply switches, and bits4..6 the three experiment switches retired on
  // 2026-11-18. All five are written 0 so a profile saved by an older build comes
  // back to a clean state. Only bits 0 and 3 are live: AP forced high beam and
  // AP forced high beam 2.
  cfg[6] = (uint8_t)((cfg[6] & (uint8_t)~0x7Fu) |
                     (in.apForcedHighBeam ? 0x01u : 0x00u) |
                     (in.apForcedHighBeam2 ? 0x08u : 0x00u));
  // This function owns exactly one bit of cfg[2]: bit0, the strobe-2 gate. The
  // rest of the byte is written back untouched, for the same reason cfg[7] is.
  cfg[2] = (uint8_t)((cfg[2] & (uint8_t)~0x01u) | (in.hsStrobe2 ? 0x01u : 0x00u));
  // cfg[8] bits0..1: the route-1 recovery profile. No earlier build touched this
  // byte, so the two bits are free; the upper bits are written back untouched in
  // case a future App byte lands there.
  cfg[8] = (uint8_t)((cfg[8] & (uint8_t)~LIGHTING_CFG_TOPUP_PROFILE_MASK) |
                     (in.topupRetryProfile & LIGHTING_CFG_TOPUP_PROFILE_MASK));
}

// ---------------------------------------------------------------------------
// Enable gates. Every feature is independently gated and a gate that is shut
// must produce no extra transmission at all.
// ---------------------------------------------------------------------------

// Rear-fog path A: cfg byte31 bit6 - mirror the physical button on 0x3C2 MUX1.
static inline bool lightingRearFogEnabledPure(uint8_t cfg7) {
  return (cfg7 & 0x40u) != 0u;
}

// F5: cfg byte28 bit3.
static inline bool lightingMaintenanceEnabledPure(uint8_t cfg4) {
  return (cfg4 & 0x08u) != 0u;
}

// ---------------------------------------------------------------------------
// F1 high-beam strobe gesture: three quick stalk pulls start a flash train; a
// single further pull cancels it
// ---------------------------------------------------------------------------

// Three pulls within three seconds start the train. The window comes from the
// reference firmware, which uses a 3000 ms second-action timer for the same
// gesture (see the decompiled high-beam handler); 1500 ms was a
// guess made before that timer was found and is now too short on a real car.
static constexpr uint32_t LIGHTING_HS_WINDOW_MS = 3000u;
static constexpr uint8_t LIGHTING_HS_PULLS_REQUIRED = 3u;
// A pull is a rising edge; the stalk rests in the idle position between pulls.
// Three is the operator's own count (the app binds btn 72, "拉3次");
// two was our earlier reading of the reference firmware and fires far too
// easily when a single push bounces.
static constexpr uint32_t LIGHTING_HS_EDGE_GUARD_MS = 40u;
// A single pull cancels a running train, but only once the gesture that started
// it has settled: the next pull of the triple-pull arrives ~200 ms after the
// previous one and must not cancel the train it just armed.
static constexpr uint32_t LIGHTING_HS_CANCEL_GUARD_MS = 600u;

// Where the pull is read from on 0x249 SCCM_leftStalk.
//
// Payload byte 1 bits 7..4, not byte 2 bits 3..0. Three independent sources
// agree on this:
//   * The reference firmware decodes the direction as `(d1 >> 4) & 3` and maps
//     it onto event codes 67..70 (TSL8 at 0x48004938, TSL9 at the twin site).
//     A two-bit mask only fits a four-valued field.
//   * The official Tesla CAN database lists TWO separate signals in this frame:
//     `SCCM_highBeamStalkStatus` = IDLE/PULL/PUSH/SNA (four values, two bits)
//     and `SCCM_turnIndicatorStalkStatus` = ten values (four bits). The field
//     read here is the former, so the semantic is PULL, not "turn stalk up".
//   * The project's own on-car-validated 0x229 builder already puts its
//     position nibble in byte 1 bits 7..4 (continuous_ap_fsm_pure.h), and its
//     parser reads it back the same way.
//
// The old code read `data[2] & 0x0F`, which is a nibble that is 0x00 in all
// 738 captured frames of this car and in every captured frame of the four
// fresh captures. The gesture could therefore never arm, which is exactly the
// symptom reported on the car.
static constexpr uint8_t LIGHTING_249_DIR_BYTE = 1u;
static constexpr uint8_t LIGHTING_249_DIR_SHIFT = 4u;
static constexpr uint8_t LIGHTING_249_DIR_MASK = 0x03u;
// 0x249 is the SCCM frame; byte 2 bits 3..0 is not the stalk direction.
static constexpr uint8_t LIGHTING_249_HIGH_BEAM_IDLE = 0u;  // resting position
static constexpr uint8_t LIGHTING_249_HIGH_BEAM_PULL = 1u;  // toward the driver
// Pushing the stalk away from the driver is the latching high-beam position, the
// one the owner asked for ("external push starts the forced high beam"). DBC
// `VAL_ 585 SCCM_highBeamStalkStatus 0 IDLE 1 PULL 2 PUSH 3 SNA`, so it is the
// remaining value 2. Our own injected request only ever raises PULL (bit 4), so
// the car can never echo a PUSH back at us.
//
// TODO(verify): PUSH was never observed in any capture of this car. Every one of
// the four 2026-11 captures carries only IDLE (0) and PULL (1) on
// SCCM_highBeamStalkStatus, because the owner was flashing, not latching. The
// value comes from the DBC enum alone, so it is wired but unproven on hardware.
static constexpr uint8_t LIGHTING_249_HIGH_BEAM_PUSH = 2u;
// The request this module injects is byte 1 bit 4. The reference firmware decodes
// the action as `(d1 >> 4) & 3` with 1 = PULL, and the frame checksum only covers
// the HIGH nibble of d1 (plus d2, d3), so raising bit 4 and recomputing byte 0 is
// exactly what the car's own SCCM frame carries on a physical pull. The low
// nibble of d1 is the rolling counter and must keep its sampled value.
static constexpr uint8_t LIGHTING_249_PULL_BIT = 0x10u;

// How long after transmitting a 0x249 request a received stalk frame may still
// be recognised as our own echo. One body-bus round is ~50 ms, and our own
// request is emitted at most twice per round, so 120 ms covers the loopback with
// room to spare without swallowing the driver's next pull.
static constexpr uint32_t LIGHTING_249_SELF_ECHO_MS = 120u;

// The reference firmware's forced-high-beam gate chain ends with "the 0x118
// timestamp is younger than 1001 ms" - i.e. the car itself is alive and talking,
// not "Autopilot is engaged". This module had substituted gateAPActive for it,
// which is a stricter condition the reference does not have; the operator asked
// for the reference behaviour, so this is that freshness test expressed on the
// same 0x118 sample the gear decision already uses.
static constexpr uint32_t LIGHTING_VEHICLE_FRESH_MS = 1001u;

static inline bool lightingVehicleFreshPure(uint32_t lastFrameMs, uint32_t nowMs) {
  return lastFrameMs != 0u && (uint32_t)(nowMs - lastFrameMs) < LIGHTING_VEHICLE_FRESH_MS;
}

// ---------------------------------------------------------------------------
// Who owns (BODY, 0x249) right now
// ---------------------------------------------------------------------------
// Four writers share this identifier, and every one of them rewrites data1 in
// place on a frame the body controller broadcasts every ~50 ms. Two of them
// running at once interleave two independent counter/CRC streams on one id, which
// the SCCM reads as the driver flipping the stalk - that is the mechanism behind
// every "it strobes" report this project has had. Ownership is therefore a single
// decision, computed from the four writers' own demand flags, with a fixed
// priority:
//
//   STROBE  the high-beam strobe's running train and the release frame it owes.
//           It is the only writer that flips the beam by design, and only while
//           the operator has armed it.
//   ALBERT  the Albert V12 transaction: a bounded, hand-armed request.
//   AP1     route 1's recovery train, alive only inside a latched AP run.
//
// A writer that holds a demand but does not get ownership is a CONFLICT, and the
// caller counts it: that counter is the only way to tell "the feature did nothing"
// from "another writer was on the wire".
static constexpr uint8_t LIGHTING_249_OWNER_NONE = 0u;
static constexpr uint8_t LIGHTING_249_OWNER_STROBE = 1u;
static constexpr uint8_t LIGHTING_249_OWNER_ALBERT = 2u;
static constexpr uint8_t LIGHTING_249_OWNER_AP1 = 3u;

static inline uint8_t lighting249OwnerPure(bool strobeOwns, bool albertWants,
                                           bool ap1Wants) {
  if (strobeOwns) return LIGHTING_249_OWNER_STROBE;
  if (albertWants) return LIGHTING_249_OWNER_ALBERT;
  if (ap1Wants) return LIGHTING_249_OWNER_AP1;
  return LIGHTING_249_OWNER_NONE;
}

static inline const char *lighting249OwnerNamePure(uint8_t owner) {
  switch (owner) {
    case LIGHTING_249_OWNER_STROBE: return "STROBE";
    case LIGHTING_249_OWNER_ALBERT: return "ALBERT";
    case LIGHTING_249_OWNER_AP1: return "AP1";
    default: return "NONE";
  }
}

static inline uint8_t lightingStalkDirPure(const uint8_t data[8]) {
  return (uint8_t)((data[LIGHTING_249_DIR_BYTE] >> LIGHTING_249_DIR_SHIFT) &
                   LIGHTING_249_DIR_MASK);
}

// ---------------------------------------------------------------------------
// AP forced high beam: the stalk is the switch, the panel is the permission
// ---------------------------------------------------------------------------
//
// Owner request (2026-11-18, third revision of this feature). The panel switch
// is an AUTHORISATION only. Turning it on must not put a single frame on the
// bus and must not touch the car's adaptive high beam: an AP-mode driver keeps
// normal AHB until they ask for the forced beam with the stalk. Inside
// Autopilot, one outward PUSH starts the run - from then on this module holds
// the 0x3E9 decision, clears the AHB override bit and re-pushes the stalk
// whenever the lamp reports dark - and one more outward PUSH stops it and hands
// the lamp back to AHB. With the run stopped, or with the switch off, this
// module writes nothing and AHB behaves exactly as it does without the module.
//
// Two quiet requirements keep the car's own traffic from toggling the latch:
//   * LIGHTING_AP_BEAM_PUSH_GUARD_MS (500 ms) between accepted edges. A real
//     push holds the contact for 100..200 ms and the car repeats the same
//     direction every ~50 ms, so a naive rising-edge test would count one push
//     three or four times and toggle the feature straight back off.
//   * LIGHTING_AP1_TX_QUIET_MS (700 ms) after OUR OWN 0x249 transmission. The
//     recovery train is itself a PUSH burst and the car mirrors it back a few
//     tens of milliseconds later (CAN_Research_Capture 2(6).csv: our
//     826/836/846/856 came back as RX PUSH at 852/901/952/1001). Those are real
//     RX frames carrying the car's own counter, so the byte-level echo test in
//     lightingIsSelfEcho249 cannot reliably recognise them; they have to be
//     excluded by timing instead.
static constexpr uint32_t LIGHTING_AP_BEAM_PUSH_GUARD_MS = 500u;
static constexpr uint32_t LIGHTING_AP1_TX_QUIET_MS = 700u;

struct LightingAp1RunPure {
  bool running;        // the driver pushed while the switch and the AP were ready
  uint32_t lastEdgeMs; // millis() of the last accepted push, 0 = none yet
};

static inline void lightingAp1RunResetPure(LightingAp1RunPure &s) {
  s = LightingAp1RunPure{};
}

// One observed 0x249 sample. `authorized` is the panel switch AND the AP gate;
// `pushEdge` is the rising edge into PUSH computed by the caller; `ownTxQuiet`
// false means this firmware put a 0x249 frame on the wire too recently for the
// edge to be the driver's own gesture. Returns the running state after the
// sample, so the caller can publish it without a second query.
static inline bool lightingAp1RunStepPure(LightingAp1RunPure &s, bool authorized,
                                          bool pushEdge, bool ownTxQuiet,
                                          uint32_t nowMs) {
  if (!authorized) {
    lightingAp1RunResetPure(s);
    return false;
  }
  if (!pushEdge) return s.running;
  if (!ownTxQuiet) return s.running;
  if (s.lastEdgeMs != 0u &&
      (uint32_t)(nowMs - s.lastEdgeMs) < LIGHTING_AP_BEAM_PUSH_GUARD_MS) {
    return s.running;
  }
  s.lastEdgeMs = nowMs != 0u ? nowMs : 1u;
  s.running = !s.running;
  return s.running;
}

static inline bool lightingAp1RunActivePure(const LightingAp1RunPure &s) {
  return s.running;
}

// ---------------------------------------------------------------------------
// Strobe 2: hold the stalk pulled and flip to a release every 70 ms
// ---------------------------------------------------------------------------
//
// The first strobe replays the reference firmware's burst: three PULL frames
// 20 ms apart, then idle, and it depends on the lamp controller latching the
// burst. This second feature is the operator's own idea and works the other way
// round: keep the stalk pulled so the high beam is commanded ON continuously,
// then keep flipping the level so the beam goes dark for one half of the cycle
// and stays lit for the other. The beam therefore sees a square wave that never
// leaves the stalk idling long enough to be read as "off" by the body.
//
// One half of the cycle. The owner set both halves to 70 ms (2026-11-16, "every
// 70 ms dark, dark lasting 70 ms"), i.e. a 140 ms cycle at ~7.1 Hz, up from the
// 200 ms / 5 Hz square wave this shipped with. 70 is deliberately not a multiple
// of the 20 ms assertion grid, so the service sends a frame the instant the level
// flips instead of waiting for the next grid slot; otherwise one half would come
// out 80 ms and the other 60 ms. See lightingServiceHs2 in lighting_features.h.
static constexpr uint32_t LIGHTING_HS2_HOLD_MS = 70u;

struct LightingHs2Pure {
  uint32_t lastEdgeMs;  // when the current half cycle started
  uint32_t armedAtMs;   // when a stalk gesture raised the switch; 0 = panel
  bool pull;            // true: the half cycle holds PULL, false: holds IDLE
  bool armed;           // RAM-only master switch
};

static inline void lightingHs2ResetPure(LightingHs2Pure &s) {
  s = LightingHs2Pure{};
}

// Arm from "the first half is the lit one", so the very first frame the writer
// emits after the switch is thrown is a PULL. `armedAtMs` records when a stalk
// gesture did it, so a single pull cannot cancel the train it just started; a
// panel arm passes 0 and is therefore cancellable at once.
static inline void lightingHs2ArmAtPure(LightingHs2Pure &s, uint32_t nowMs) {
  s.armed = true;
  s.pull = true;
  s.lastEdgeMs = (nowMs != 0u) ? nowMs : 1u;
  s.armedAtMs = nowMs;
}

static inline void lightingHs2ArmPure(LightingHs2Pure &s, uint32_t nowMs) {
  lightingHs2ArmAtPure(s, nowMs);
  s.armedAtMs = 0u;
}

static inline void lightingHs2DisarmPure(LightingHs2Pure &s) {
  s.armed = false;
  s.pull = false;
  s.lastEdgeMs = 0u;
  s.armedAtMs = 0u;
}

static inline bool lightingHs2RunningPure(const LightingHs2Pure &s) {
  return s.armed;
}

// true = assert PULL on this tick, false = assert the released (dark) level.
// The flip happens on the wall clock, not on how often the service happens to be
// called, so a slow tick can never stretch one half of the cycle.
static inline bool lightingHs2LevelPure(LightingHs2Pure &s, uint32_t nowMs) {
  if (!s.armed) return false;
  if (s.lastEdgeMs == 0u) {
    s.lastEdgeMs = (nowMs != 0u) ? nowMs : 1u;
    s.pull = true;
    return true;
  }
  if ((uint32_t)(nowMs - s.lastEdgeMs) >= LIGHTING_HS2_HOLD_MS) {
    s.lastEdgeMs = nowMs;
    s.pull = !s.pull;
  }
  return s.pull;
}

// ---------------------------------------------------------------------------
// High-beam strobe gesture: three quick stalk pulls arm it, one more stops it
// ---------------------------------------------------------------------------

// A pull is a rising edge of the high-beam stalk (0x249 d1 bits7..4 == PULL).
// Three of them inside LIGHTING_HS_WINDOW_MS arm the strobe; a single pull while
// it runs stops it again. The owner asked for exactly this on 2026-11-16: the
// strobe is the only high-beam strobe left, so the gesture belongs to it and is
// always live - there is no separate enable bit any more. The reference
// firmware arms on the second pull (`481019b0`: first PULL stores a timestamp
// and sets state 2, second within 3000 ms sets state 5 open, release sets 4);
// the third pull is the operator's own count, because two fires far too easily
// when a single push bounces.
struct LightingHsTriplePullPure {
  uint8_t pulls;
  uint32_t windowStartMs;
  uint32_t lastEdgeMs;
};

// What one gesture edge asks the caller to do.
static constexpr int8_t LIGHTING_HS_ACTION_NONE = -1;
static constexpr int8_t LIGHTING_HS_ACTION_DISARM = 0;
static constexpr int8_t LIGHTING_HS_ACTION_ARM = 1;

static inline void lightingHsTriplePullResetPure(LightingHsTriplePullPure &s) {
  s = LightingHsTriplePullPure{};
}

// Feed one stalk rising edge. `master` is the current strobe switch state and
// `armedAtMs` when it was raised, so a pull that arrives only ~200 ms after the
// one that armed the train cannot immediately be read as the closing pull.
static inline int8_t lightingHsGestureFeedPure(LightingHsTriplePullPure &s, uint32_t nowMs,
                                               bool upPullEdge, bool master,
                                               uint32_t armedAtMs) {
  if (!upPullEdge) return LIGHTING_HS_ACTION_NONE;
  if (s.pulls != 0u && (uint32_t)(nowMs - s.lastEdgeMs) < LIGHTING_HS_EDGE_GUARD_MS) {
    return LIGHTING_HS_ACTION_NONE;
  }
  s.lastEdgeMs = nowMs;
  // Running train: one pull closes it, but only once the opening gesture has
  // settled (`LIGHTING_HS_CANCEL_GUARD_MS` after the switch went up).
  if (master) {
    if (armedAtMs != 0u && (uint32_t)(nowMs - armedAtMs) < LIGHTING_HS_CANCEL_GUARD_MS) {
      s.pulls = 0u;
      return LIGHTING_HS_ACTION_NONE;
    }
    s.pulls = 0u;
    return LIGHTING_HS_ACTION_DISARM;
  }
  if (s.pulls == 0u || (uint32_t)(nowMs - s.windowStartMs) > LIGHTING_HS_WINDOW_MS) {
    s.pulls = 0u;
    s.windowStartMs = nowMs;
  }
  s.pulls++;
  if (s.pulls < LIGHTING_HS_PULLS_REQUIRED) return LIGHTING_HS_ACTION_NONE;
  s.pulls = 0u;
  return LIGHTING_HS_ACTION_ARM;
}

// ---------------------------------------------------------------------------
// F3 后雾灯手势：按住右滚轮的同时，把左滚轮向下滚。
// 判据是瞬时电平——松手立刻停止，不做任何锁存。
// ---------------------------------------------------------------------------

static constexpr uint8_t LIGHTING_3C2_RIGHT_BUTTON_BYTE = 1u;   // d1 bit4-5
static constexpr uint8_t LIGHTING_3C2_RIGHT_BUTTON_SHIFT = 4u;  // d1 bit4-5
static constexpr uint8_t LIGHTING_3C2_RIGHT_BUTTON_ON = 2u;     // VCLEFT_SWITCH_ON
static constexpr uint8_t LIGHTING_3C2_LEFT_WHEEL_BYTE = 2u;     // d2 six-bit signed
static constexpr uint8_t LIGHTING_3C2_MUX_BYTE = 0u;
static constexpr uint8_t LIGHTING_3C2_MUX1 = 1u;

static inline int8_t lightingDecodeSignedSixBitPure(uint8_t raw) {
  const uint8_t v = (uint8_t)(raw & 0x3Fu);
  return (v & 0x20u) != 0u ? (int8_t)(v | 0xC0u) : (int8_t)v;
}

// 「右滚轮被按住」判的是 d1 的 bit5..4：本工程自己的 Continuous-AP 点击构帧
// （continuousApBuildClickPure）写的正是这个字段，它的解析侧
// （continuousApDecodeFramePure 的 `(d1 >> 4) & 3`）读的也是同一段，且已在
// 实车上验证过。「左滚轮向下滚」判的是 d2 的六位有符号刻度，tsl9InputApplyCommandPure
// 往里写 LEFT_VOLUME 刻度。
// 上一版把右滚轮判在 d5 的 bit5..4 —— 而实车 394 帧 MUX1 里那半个字节恒为
// 0x00，所以这个手势在这台车上永远触发不了。
static inline bool lightingRearFogGesturePure(const uint8_t data[8], bool mux1Only) {
  if (data == nullptr) return false;
  if (mux1Only && (uint8_t)(data[LIGHTING_3C2_MUX_BYTE] & 0x03u) != LIGHTING_3C2_MUX1) return false;
  const uint8_t rightButton =
      (uint8_t)((data[LIGHTING_3C2_RIGHT_BUTTON_BYTE] >>
                 LIGHTING_3C2_RIGHT_BUTTON_SHIFT) &
                0x03u);
  if (rightButton != LIGHTING_3C2_RIGHT_BUTTON_ON) return false;
  return lightingDecodeSignedSixBitPure(data[LIGHTING_3C2_LEFT_WHEEL_BYTE]) < 0;
}

// 后雾灯频闪的半周期（每个电平边沿之间的间隔）。
//
// 变更历史：最初用 250 ms/半周期（约 2 Hz，第一个凭经验取的值），车主反馈
// 「太慢」；改成 50 ms 后车主反馈「太快」；当前取 100 ms。
//
// 取值依据：车身总线两帧 0x249 / 0x3C2 都是约 50 ms 一轮，100 ms 相当于两个
// 车身总线往返，节奏比车自身的 20 Hz 调度慢一半，不会和它抢拍。车自身广播
// 0x273 的周期是 500 ms，所以整段频闪完全落在我们自己发的帧里，不会被车的
// 原生更新覆盖掉。
//
// TODO(calibrate)：100 ms 来自车主实车观感，不是对灯实际响应时间的测量值。
// 换车型或换灯具后需要用实车重新确认。
static constexpr uint32_t LIGHTING_REAR_FOG_HALF_PERIOD_MS = 100u;

// 每次触发闪几下（车主指令：从原来的 5 下改为 20 下）。
// 现在后雾灯只有「频闪」这一条发送路径，所以全工程只有这一个计数。
static constexpr uint8_t LIGHTING_REAR_FOG_FLASHES = 20u;

// 拿不到帧模板时的放弃时限：车没接、总线上没有真帧时帧池永远是空的，如果不
// 设上限就会无限重试；而「正在闪」这个标志一旦卡住，下一次按键会被 409 挡掉。
// 计时从「第一个被拒绝的边沿」开始算，与本次要闪多少下无关。
static constexpr uint32_t LIGHTING_REAR_FOG_STALL_MS = 5000u;

// 20 下 = 40 个半周期，按 100 ms 算约 4 秒发完。边沿计数用的是 uint8_t，
// 这里静态保证不会溢出。
static_assert(LIGHTING_REAR_FOG_FLASHES * 2u <= 255u,
              "burst edge counter is a uint8_t");

// ---------------------------------------------------------------------------
// Dynamic high-mount lamp - the reference firmware's "dynamic brake light"
// (0x3E9 d2 bit6 / DBC DAS_dynamicBrakeLightRequest), renamed on the panel.
//
// This is a port of the reference machine, not an invention, and the two have
// very little in common with what used to live here. The reference:
//
//   * takes brake state from TWO chassis frames, not from a deceleration
//     estimate:  0x145 ESP_status -> data[6] bit6   (brake pressed)
//                                   data[8] >= 38   (hard press, 9th byte)
//              0x39D IBST_status -> data[5] bit1   (brake pressed)
//                                   data[6] >= 81   (hard press)
//     (`0xd664` / `0xd67c`: `lhu a0,6(a0) ; srli 6 ; andi 1` and
//      `lhu a0,4(a0) ; srli 9 ; andi 1`, i.e. byte 6 bit 6 and byte 5 bit 1.)
//     Both are CHASSIS frames - the operator asked for the bus to match too.
//   * gates the LAMP, never the release, on "vehicle state == 4" and
//     "speed > 8 km/h" (`0xfdd8`: `jal 0xd084` must return 4, `jal 0x10434`
//     must exceed 8).
//   * drives the LIGHT level off brake-state CHANGES only
//     (`0xd5b6: beq a4,a0 -> skip`, then `0xd5d4: jal 0xfdd8`), which is why a
//     car that is already braking at power-up does NOT light the lamp until the
//     pedal is released and pressed again. That looks like a bug and is not one;
//     it is the reference behaviour.
//   * drives the HARD level off "not lit + brake pressed + hard flag"
//     (`0xd5e2`-`0xd604`), evaluated on every received brake frame.
//   * releases when the brake state falls and the level is hard (`0xd63a`), and
//     separately lets go when the lamp is lit, the state is still "lit", and the
//     car is down to <= 8 km/h (`0xd622`-`0xd634`).
//   * keeps a lamp level word (gp+317: 0 off / 1 lit / 2 fading) and writes the
//     single output bit from it: `fd0c: ori 0x40` for lit, `fd4c: andi ~0x40`
//     for the fade, which is data[2] bit6 once the frame header offset is taken
//     into account (`0xfd0c: lbu a5,5(s0)` - s0 is the frame header, so 5(s0) is
//     data[2]).
//
// The previous implementation substituted a deceleration estimate for the brake
// signal and a timeout for the release; that is deleted. It never had an input
// the car produces.
// ---------------------------------------------------------------------------

// How a brake frame is read - straight out of the reference's two decoders.
//
// The byte indices below are DATA indices, i.e. already rebased past the
// reference's three-byte frame header (`id` at +0/+1, `dlc` at +2, `data` at +3
// - proved by 0xb628 reading its own DLC with `lbu a5,6(sp)` while its buffer
// starts at sp+4). The disassembly reads:
//
//   0xd664 (ID 325 = 0x145): lbu a1,8(a0)   -> data[5]              = "hard"
//                            lhu a0,6(a0)   -> data[3] | data[4]<<8, srli 6, andi 1
//                                           -> bit 6 of that word = data[3] bit6
//   0xd67c (ID 925 = 0x39D): lbu a1,6(a0)   -> data[3]              = "hard"
//                            lhu a0,4(a0)   -> data[1] | data[2]<<8, srli 9, andi 1
//                                           -> bit 9 of that word = data[2] bit1
// (the `lhu` pairs are little-endian, so the low byte of each is the first one
// named - that is why 0x145's brake bit lands in data[3] and not in data[4])
//
// Both pairs sit inside the DLCs this car actually sends (8 bytes for 0x145,
// 5 bytes for 0x39D), so nothing has to be invented for absent bytes. An
// earlier revision of this block added three to every index by treating the
// pointer as if it were the payload start; that read bytes the frames do not
// carry and could never have fired.
//
// TODO(verify): the DBC's own brake bit for 0x145 is ESP_brakeLamp at byte2 bit5,
// which is not either of the bits above. The reference is followed here because
// the operator asked for byte-for-byte fidelity; a bench capture with the pedal
// pressed would settle which reading the body controller actually reacts to.
static constexpr uint8_t LIGHTING_145_BRAKE_BYTE = 3u;    // data[3] bit6
static constexpr uint8_t LIGHTING_145_BRAKE_SHIFT = 6u;
static constexpr uint8_t LIGHTING_145_HARD_BYTE = 5u;     // data[5] >= 38
static constexpr uint8_t LIGHTING_145_HARD_MIN = 38u;
static constexpr uint8_t LIGHTING_39D_BRAKE_BYTE = 2u;    // data[2] bit1
static constexpr uint8_t LIGHTING_39D_BRAKE_SHIFT = 1u;
static constexpr uint8_t LIGHTING_39D_HARD_BYTE = 3u;     // data[3] >= 81
static constexpr uint8_t LIGHTING_39D_HARD_MIN = 81u;
static constexpr uint8_t LIGHTING_BRAKE_STATE_MASK = 0x01u;

// The three positions of the operator's picker stored in cfg[5] bits0..1.
// These are the reference firmware's own numbering (0 = 关闭, 1 = 轻踩刹车,
// 2 = 深踩刹车) and are also what the dynamic-brake state machine compares
// against, so they must exist before it.
static constexpr uint8_t LIGHTING_DYN_MODE_OFF = 0u;
static constexpr uint8_t LIGHTING_DYN_MODE_LIGHT = 1u;
static constexpr uint8_t LIGHTING_DYN_MODE_HARD = 2u;

struct LightingBrakeSignalPure {
  bool brake;  // the brake is pressed
  bool hard;   // the press counts as "hard"
};

static inline LightingBrakeSignalPure lightingDecodeBrake145Pure(const uint8_t data[8],
                                                                 uint8_t dlc) {
  uint8_t padded[8] = {};
  const uint8_t n = dlc > 8u ? 8u : dlc;
  if (data != nullptr && n != 0u) memcpy(padded, data, n);
  LightingBrakeSignalPure out = {};
  out.brake = (uint8_t)((padded[LIGHTING_145_BRAKE_BYTE] >> LIGHTING_145_BRAKE_SHIFT) &
                        LIGHTING_BRAKE_STATE_MASK) != 0u;
  out.hard = padded[LIGHTING_145_HARD_BYTE] >= LIGHTING_145_HARD_MIN;
  return out;
}

static inline LightingBrakeSignalPure lightingDecodeBrake39DPure(const uint8_t data[8],
                                                                 uint8_t dlc) {
  uint8_t padded[8] = {};
  const uint8_t n = dlc > 8u ? 8u : dlc;
  if (data != nullptr && n != 0u) memcpy(padded, data, n);
  LightingBrakeSignalPure out = {};
  out.brake = (uint8_t)((padded[LIGHTING_39D_BRAKE_BYTE] >> LIGHTING_39D_BRAKE_SHIFT) &
                        LIGHTING_BRAKE_STATE_MASK) != 0u;
  out.hard = padded[LIGHTING_39D_HARD_BYTE] >= LIGHTING_39D_HARD_MIN;
  return out;
}

// The two chassis brake frames are latched separately and merged here. They used
// to be written into one struct, so whichever frame arrived last replaced the
// other one wholesale: 0x145 never sets its "hard" byte on this car (measured:
// d5 is 0x00 in every captured brake frame), so every 0x145 frame erased the
// hard flag that 0x39D had just raised, and the hard-press level could never
// fire.
static inline LightingBrakeSignalPure lightingMergeBrakePure(
    const LightingBrakeSignalPure &a, const LightingBrakeSignalPure &b) {
  LightingBrakeSignalPure out = {};
  out.brake = a.brake || b.brake;
  out.hard = a.hard || b.hard;
  return out;
}

static constexpr uint8_t LIGHTING_DYN_GEAR_DRIVE = 4u;   // vehicle state 4
static constexpr int32_t LIGHTING_DYN_SPEED_GATE_KPH_X100 = 800;  // > 8.00 kph

static constexpr int8_t LIGHTING_DYN_ACT_NONE = -1;
static constexpr int8_t LIGHTING_DYN_ACT_RELEASE = 0;
static constexpr int8_t LIGHTING_DYN_ACT_RAISE = 1;

// gp+268 / gp+265 / gp+317 of the reference, in the same order.
struct LightingDynHighPure {
  uint8_t prevBrakeState;  // 0/1: last brake state seen, so only changes act
  bool lit;                // gp+265: a brake press has been latched
  uint8_t lampLevel;       // gp+317: 0 off / 1 lit / 2 fading (release in flight)
  bool requested;          // what our last write put into d2 bit6
};

static inline void lightingDynHighResetPure(LightingDynHighPure &s) {
  s = LightingDynHighPure{};
}

static inline bool lightingDynHighEnabledPure(uint8_t mode) {
  return mode == LIGHTING_DYN_MODE_LIGHT || mode == LIGHTING_DYN_MODE_HARD;
}

// The two lamp gates. They apply to lighting the lamp only - `0xfdd8` is the
// only place that checks them, and its release path checks nothing.
static inline bool lightingDynHighGatePure(uint8_t vehicleStateRaw, int32_t speedKphX100) {
  return vehicleStateRaw == LIGHTING_DYN_GEAR_DRIVE &&
         speedKphX100 > LIGHTING_DYN_SPEED_GATE_KPH_X100;
}

// `0xfdd8(level)`: level != 0 lights the lamp (if the gates allow), level == 0
// hands it over to the fade. Returns the action this tick owes.
static inline int8_t lightingDynHighSetLampPure(LightingDynHighPure &s, bool on,
                                                uint8_t vehicleStateRaw,
                                                int32_t speedKphX100) {
  if (on) {
    if (!lightingDynHighGatePure(vehicleStateRaw, speedKphX100)) {
      return LIGHTING_DYN_ACT_NONE;  // 0xfdd8 returns before touching gp+317
    }
    if (s.lampLevel == 1u) return LIGHTING_DYN_ACT_NONE;
    s.lampLevel = 1u;
    s.requested = true;
    return LIGHTING_DYN_ACT_RAISE;
  }
  // 0xfdd8(0): gp+317 goes 1 -> 2 and the very next composer pass sees the 2,
  // clears the bit and drops gp+317 back to 0. One release frame carries the
  // whole transition, so the ledger has to close here - leaving `requested`
  // true would keep d2 bit6 asserted and the lamp stays lit forever.
  const bool owed = s.requested || s.lampLevel != 0u;
  s.lampLevel = 0u;
  s.requested = false;
  return owed ? LIGHTING_DYN_ACT_RELEASE : LIGHTING_DYN_ACT_NONE;
}

// One received brake frame (or one tick). `brake` / `hard` come straight out of
// lightingDecodeBrake145Pure / ...39DPure. Returns RAISE / RELEASE when d2 bit6
// has to be written this tick, NONE otherwise.
//
static inline int8_t lightingDynHighStepPure(LightingDynHighPure &s, uint8_t mode,
                                             bool brake, bool hard,
                                             uint8_t vehicleStateRaw,
                                             int32_t speedKphX100) {
  if (!lightingDynHighEnabledPure(mode)) {
    const bool release = s.requested || s.lampLevel != 0u;
    s.prevBrakeState = brake ? 1u : 0u;
    s.lit = false;
    s.lampLevel = 0u;
    s.requested = false;
    return release ? LIGHTING_DYN_ACT_RELEASE : LIGHTING_DYN_ACT_NONE;
  }

  int8_t action = LIGHTING_DYN_ACT_NONE;
  const uint8_t brakeState = brake ? 1u : 0u;

  // 0xd5b6: only a CHANGE of the brake state runs the light-level path, and only
  // when the operator picked the light level. A car that is already braking at
  // power-up therefore stays dark until the pedal is worked again - that is the
  // reference's own behaviour, reproduced on purpose.
  if (brakeState != s.prevBrakeState) {
    s.prevBrakeState = brakeState;
    if (mode == LIGHTING_DYN_MODE_LIGHT) {
      const int8_t a = lightingDynHighSetLampPure(s, brake, vehicleStateRaw,
                                                  speedKphX100);
      if (a != LIGHTING_DYN_ACT_NONE) action = a;
    }
  }

  // 0xd5e2: "not lit + brake pressed + hard flag" latches the press, and the hard
  // level lights the lamp from there. Evaluated on every frame, not only on edges.
  if (!s.lit) {
    if (brake && hard) {
      s.lit = true;
      if (mode == LIGHTING_DYN_MODE_HARD) {
        const int8_t a = lightingDynHighSetLampPure(s, true, vehicleStateRaw,
                                                    speedKphX100);
        if (a != LIGHTING_DYN_ACT_NONE) action = a;
      }
    }
  } else if (!brake) {
    // 0xd63a: the pedal came back up.
    s.lit = false;
    if (mode == LIGHTING_DYN_MODE_HARD) {
      const int8_t a = lightingDynHighSetLampPure(s, false, vehicleStateRaw,
                                                  speedKphX100);
      if (a != LIGHTING_DYN_ACT_NONE) action = a;
    }
  }

  // 0xd618-0xd634: while the lamp is lit and the car has come down to <= 8 km/h,
  // let go. Only level 1 is touched - a fade in flight must not be restarted.
  if (s.lampLevel == 1u && speedKphX100 <= LIGHTING_DYN_SPEED_GATE_KPH_X100) {
    const int8_t a = lightingDynHighSetLampPure(s, false, vehicleStateRaw,
                                                speedKphX100);
    if (a != LIGHTING_DYN_ACT_NONE) action = a;
  }

  return action;
}

// ---------------------------------------------------------------------------
// AP forced high beam - the reference firmware's "manual high beam", renamed.
//
// Two bits of the same 0x3E9 mirror, written together and never apart:
//   d1 bits 3..4 = DAS_highLowBeamDecision, value 2 (bit4 set, bit3 clear) = on
//   d3 bit0      = DAS_ahlbOverride, forced to 0 so the car cannot overwrite the
//                  decision above with its own automatic answer.
//
// Turning the feature off only ever CLEARS d3 bit0; it never sets it. The
// reference firmware does the same - its whole 0x3E9 composer contains a single
// `andi a5,-2` on that byte (0x07C34) and no matching `ori` - and setting the
// bit is actively harmful: it tells the body controller that DAS demands to
// override the automatic high beam, so the car stays locked out of AHLB after
// the operator releases the forced decision. An earlier revision of this module
// set it on the way out; that was wrong.
//
// d1 is cleared with ~0x18, i.e. bits 3..4 only. The reference clears ~0x19 at
// 0x07C26, which also wipes bit0. We deliberately keep bit0: per the DBC,
// d1 bit0 (absolute bit 8) is the low bit of DAS_turnIndicatorRequest, not part
// of the high-beam decision, so the reference is clobbering an unrelated signal
// there and this port should not copy that.
//
// 2026-11-18: clearing this bit unconditionally is what let AHB take the
// beam back (captures show LATCHED -> DAS_AUTO -> IDLE within 10 ms). The
// reference firmware's `andi a5,-2` was only ever exercised at night with
// no ambient light, so its behaviour cannot be trusted in lit roads.
static inline bool lightingApForcedHighBeamEnabledPure(uint8_t cfg6) {
  return (cfg6 & 0x01u) != 0u;
}

static inline void lightingApplyApForcedHighBeamPure(uint8_t data[8], bool on,
                                                    bool clearAhlb) {
  if (data == nullptr) return;
  uint8_t d1 = (uint8_t)(data[LIGHTING_3E9_D1] & (uint8_t)~LIGHTING_3E9_HIGH_BEAM_CLEAR);
  if (on) d1 = (uint8_t)(d1 | LIGHTING_3E9_HIGH_BEAM_SET);
  data[LIGHTING_3E9_D1] = d1;
  // Only ever clear the override bit, never raise it - see the block comment
  // above. Whether to clear it at all is the caller's A/B decision (cfg[6] bit5).
  if (clearAhlb) {
    data[LIGHTING_3E9_D3] =
        (uint8_t)(data[LIGHTING_3E9_D3] & (uint8_t)~LIGHTING_3E9_AHLB_OVERRIDE_MASK);
  }
}

static inline void lightingApplyDynamicBrakePure(uint8_t data[8], bool on) {
  if (data == nullptr) return;
  if (on) {
    data[LIGHTING_3E9_D2] =
        (uint8_t)(data[LIGHTING_3E9_D2] | LIGHTING_3E9_DYNAMIC_BRAKE_MASK);
  } else {
    data[LIGHTING_3E9_D2] =
        (uint8_t)(data[LIGHTING_3E9_D2] & (uint8_t)~LIGHTING_3E9_DYNAMIC_BRAKE_MASK);
  }
}

// ---------------------------------------------------------------------------
// F5 maintenance mode request state machine
//
// REQUESTED -> APPLIED only on a vehicle confirmation ((BODY, 0x284) d0 bit3).
// REQUESTED -> BLOCKED after LIGHTING_MAINT_MAX_ATTEMPTS transmits with no
// confirmation. A successful transmit is not success: it only means the
// request left the controller.
// ---------------------------------------------------------------------------

enum LightingMaintStatePure : uint8_t {
  LIGHTING_MAINT_IDLE = 0,
  LIGHTING_MAINT_REQUESTED,
  LIGHTING_MAINT_APPLIED,
  LIGHTING_MAINT_BLOCKED,
};

// The confirmation is (BODY, 0x284) d0 bit3 - see LIGHTING_ID_UI_VEHICLE_MODES.
// 2000 ms is the retry window: at most LIGHTING_MAINT_MAX_ATTEMPTS transmits,
// then the state machine reports BLOCKED instead of claiming success.
static constexpr uint32_t LIGHTING_MAINT_CONFIRM_TIMEOUT_MS = 2000u;
static constexpr uint8_t LIGHTING_MAINT_MAX_ATTEMPTS = 2u;

struct LightingMaintPure {
  uint8_t state;
  uint8_t attempts;
  uint32_t sentMs;
  bool pending;  // the App request is latched until it is applied or blocked
};

static inline void lightingMaintResetPure(LightingMaintPure &s) { s = LightingMaintPure{}; }

// Mirror the live 0x339 template and raise d5 bit7 - every other byte, including
// the low bits of d5, is passed through untouched. A null template falls back to
// the documented all-zero shape so a bench run without a car still produces a
// well-formed frame.
static inline void lightingMaintCompose339Pure(const uint8_t stock[8], uint8_t out[8]) {
  if (out == nullptr) return;
  if (stock != nullptr) memcpy(out, stock, 8);
  else memset(out, 0, 8);
  out[LIGHTING_339_D5] =
      (uint8_t)((out[LIGHTING_339_D5] & LIGHTING_339_D5_CLEAR_MASK) |
                LIGHTING_339_SERVICE_MODE_MASK);
}

static inline void lightingMaintBuild339Pure(uint8_t out[8]) {
  lightingMaintCompose339Pure(nullptr, out);
}

// Precondition: maintenance enabled, P gear (not driving), request latched.
// TODO(verify): the "vehicle not running" precondition is mapped to the parked
// gate plus the absence of a running vehicle state, pending bench confirmation.
static inline bool lightingMaintGatePure(bool cfgEnabled, bool parked, bool requestPending) {
  return cfgEnabled && parked && requestPending;
}

static inline void lightingMaintArmPure(LightingMaintPure &s, uint32_t nowMs) {
  s.pending = true;
  s.state = LIGHTING_MAINT_REQUESTED;
  s.attempts = 0u;
  s.sentMs = nowMs;
}

static inline void lightingMaintMarkSentPure(LightingMaintPure &s, uint32_t nowMs) {
  s.attempts++;
  s.sentMs = nowMs;
}

// Returns true when the frame must be (re)sent on this tick.
//
// The attempts cap matters: without it this predicate stays true forever once
// the first retry is due, the caller re-sends instead of ticking, and the state
// machine can never reach BLOCKED. It was harmless only while a successful
// transmit jumped straight to APPLIED; now that APPLIED requires a vehicle
// confirmation, an uncapped retry loop would spin at the timeout rate and the
// panel would sit on "requested" with no way to report the failure.
static inline bool lightingMaintShouldSendPure(const LightingMaintPure &s, uint32_t nowMs) {
  if (s.state != LIGHTING_MAINT_REQUESTED) return false;
  if (s.attempts >= LIGHTING_MAINT_MAX_ATTEMPTS) return false;
  if (s.attempts == 0u) return true;
  return (uint32_t)(nowMs - s.sentMs) >= LIGHTING_MAINT_CONFIRM_TIMEOUT_MS;
}

static inline void lightingMaintTickPure(LightingMaintPure &s, uint32_t nowMs) {
  if (s.state != LIGHTING_MAINT_REQUESTED) return;
  if (s.attempts >= LIGHTING_MAINT_MAX_ATTEMPTS &&
      (uint32_t)(nowMs - s.sentMs) >= LIGHTING_MAINT_CONFIRM_TIMEOUT_MS) {
    s.state = LIGHTING_MAINT_BLOCKED;
    s.pending = false;
  }
}

static inline void lightingMaintClearPure(LightingMaintPure &s) {
  s = LightingMaintPure{};
  s.state = LIGHTING_MAINT_IDLE;
}
