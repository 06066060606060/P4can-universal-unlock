#pragma once
#include <stdint.h>
#include <string.h>

// An experimental interpretation of received signals for DISPLAY ONLY.
// There is no shift request, output payload, control permission or actuator API.
namespace gearhint {
enum class DisplayHint : uint8_t { None, Forward, Reverse };
enum class HintReason : uint8_t {
  GearMissing, GearStale, UnsupportedGear, SourcesMissing, SourcesStale,
  SourcesDisagree, Matched, MatchedOutsidePark, ReceiverUnavailable,
  BrakeMissing, BrakeStale, BrakeInvalid, BrakeReleased
};
struct HintResult {
  DisplayHint hint = DisplayHint::None;
  HintReason reason = HintReason::GearMissing;
  uint32_t remainingMs = 0;
};
inline const char *hintName(DisplayHint h) {
  return h == DisplayHint::Forward ? "FORWARD" :
      h == DisplayHint::Reverse ? "REVERSE" : "NONE";
}
inline const char *reasonName(HintReason r) {
  switch (r) {
    case HintReason::GearMissing: return "GEAR_MISSING";
    case HintReason::GearStale: return "GEAR_STALE";
    case HintReason::UnsupportedGear: return "GEAR_UNSUPPORTED";
    case HintReason::SourcesMissing: return "SOURCES_MISSING";
    case HintReason::SourcesStale: return "SOURCES_STALE";
    case HintReason::SourcesDisagree: return "SOURCES_DISAGREE";
    case HintReason::Matched: return "MATCHED_UNVERIFIED";
    case HintReason::MatchedOutsidePark: return "MATCHED_OUTSIDE_P_UNVERIFIED";
    case HintReason::BrakeMissing: return "BRAKE_MISSING";
    case HintReason::BrakeStale: return "BRAKE_STALE";
    case HintReason::BrakeInvalid: return "BRAKE_INVALID";
    case HintReason::BrakeReleased: return "BRAKE_RELEASED";
    default: return "RECEIVER_UNAVAILABLE";
  }
}
struct Sample {
  uint32_t count = 0, observedMs = 0;
  uint8_t data[8] = {}, dlc = 0;
  bool seen = false;
};
inline uint32_t ageMs(const Sample &s, uint32_t now) { return now - s.observedMs; }
inline bool recent(const Sample &s, uint32_t now) { return s.seen && ageMs(s, now) < 300; }
constexpr uint32_t kPrearmPairHoldMs = 1500;
// Original cache starts at +0xc34; consumer reads +0xc35: payload byte 1.
// The migration notes incorrectly specified byte 2. Do not infer a mapping
// from byte 2, even if it happens to contain a plausible direction value.
inline uint8_t directionCode(const uint8_t *data) { return (data[1] >> 4) & 7; }
struct DisplayHintObserver {
  // The legacy diagnostic view remains brake-gated. The independent prearm
  // receiver can pair fresh advice before the driver's final brake press.
  bool brakeGated = true;
  Sample gear, advice, direction, brake;
  uint32_t parkSession = 0;
  uint32_t gearSession = 0;
  uint32_t brakeSession = 0;
  uint8_t currentGear = 0;
  bool eligible = false;
  bool brakeValid = false, brakeCounterSeen = false;
  uint8_t brakeCounter = 0;

  static bool supportedGear(uint8_t g) { return g == 1 || g == 2 || g == 4; }

  void clearPair() { advice = {}; direction = {}; }
  bool brakePressed() const {
    // Paired live samples: pedal released=0x20, pressed=0x40 in byte 3.
    // The separate apply bit stays 0 in both; it is diagnostic, not a gate.
    return brakeValid && ((brake.data[3] >> 5) & 3) == 2;
  }
  bool brakeReady(uint32_t now) const { return recent(brake, now) && brakePressed(); }
  const char *brakeState(uint32_t now) const {
    if (!brake.seen) return "MISSING";
    if (!brakeValid) return "INVALID";
    if (!recent(brake, now)) return "STALE";
    return brakePressed() ? "PRESSED" : "RELEASED";
  }
  static void save(Sample &s, const uint8_t *data, uint8_t dlc, uint32_t now) {
    ++s.count; s.observedMs = now; s.seen = true; s.dlc = dlc;
    memset(s.data, 0, sizeof(s.data));
    if (dlc) memcpy(s.data, data, dlc);
  }
  void observeBrake(uint8_t dlc, bool extended, bool remote, const uint8_t *data, uint32_t now) {
    const bool wasReady = brakeReady(now);
    // CHASSIS 0x145 only. The reference checksum excludes byte 0; its
    // four-bit rolling counter is byte 1's low nibble. Repeats never renew TTL.
    bool valid = !extended && !remote && data && dlc == 8;
    if (valid) {
      uint32_t sum = 0x45 + 0x01;
      for (uint8_t i = 1; i < 8; ++i) sum += data[i];
      valid = data[0] == static_cast<uint8_t>(sum);
    }
    if (valid && brakeCounterSeen && (data[1] & 15) == brakeCounter) {
      if (brakeValid && memcmp(brake.data, data, 8) == 0) return;
      valid = false; // Same counter with changed data, or a previously rejected sample.
    } else if (valid) {
      brakeCounterSeen = true; brakeCounter = data[1] & 15;
    }
    if (valid) {
      const uint8_t driver = (data[3] >> 5) & 3;
      valid = driver == 1 || driver == 2; // 0/3 are not a usable pedal state.
    }
    save(brake, data, data && dlc <= 8 ? dlc : 0, now);
    brakeValid = valid;
    if (brakeGated && (!wasReady || !brakeReady(now))) clearPair();
    if (!wasReady && brakeReady(now)) ++brakeSession;
  }
  void observe(uint8_t bus, uint32_t id, uint8_t dlc, bool extended,
               bool remote, const uint8_t *data, uint32_t now) {
    // A gap starts a new observation session even if the next gear is the
    // same. P/D/R expansion is diagnostic only: D/R semantics are unverified.
    if (eligible && !recent(gear, now)) { eligible = false; clearPair(); }
    if (brakeGated && !brakeReady(now)) clearPair();
    if (bus == 1 && id == 0x145) {
      observeBrake(dlc, extended, remote, data, now); return;
    }
    if (extended || remote) return;
    if (bus == 1 && id == 0x118) {
      if (!data || dlc < 3 || dlc > 8) {
        gear = {}; currentGear = 0; eligible = false; clearPair(); return;
      }
      const uint8_t nextGear = data[2] >> 5;
      const bool nextEligible = supportedGear(nextGear);
      const bool newSession = nextEligible && (!eligible || nextGear != currentGear);
      if (newSession || !nextEligible) clearPair();
      if (newSession) { ++gearSession; if (nextGear == 1) ++parkSession; }
      currentGear = nextGear; eligible = nextEligible;
      save(gear, data, dlc, now);
      return;
    }
    if (bus != 2 || (id != 0x255 && id != 0x12B)) return;
    Sample &source = id == 0x255 ? advice : direction;
    if (!eligible || !recent(gear, now) || (brakeGated && !brakeReady(now)) || !data || dlc != 4) {
      source = {}; return;
    }
    save(source, data, dlc, now);
  }
  HintResult result(uint32_t now, bool receiverAvailable,
                    uint32_t sourceFreshMs = 300) const {
    HintResult r;
    if (!receiverAvailable) { r.reason = HintReason::ReceiverUnavailable; return r; }
    if (!gear.seen) return r;
    if (!recent(gear, now)) { r.reason = HintReason::GearStale; return r; }
    if (!eligible) { r.reason = HintReason::UnsupportedGear; return r; }
    if (!brake.seen) { r.reason = HintReason::BrakeMissing; return r; }
    if (!brakeValid) { r.reason = HintReason::BrakeInvalid; return r; }
    if (!recent(brake, now)) { r.reason = HintReason::BrakeStale; return r; }
    if (brakeGated && !brakePressed()) { r.reason = HintReason::BrakeReleased; return r; }
    if (!advice.seen || !direction.seen) { r.reason = HintReason::SourcesMissing; return r; }
    if (!advice.seen || !direction.seen ||
        ageMs(advice, now) >= sourceFreshMs || ageMs(direction, now) >= sourceFreshMs) {
      r.reason = HintReason::SourcesStale; return r;
    }
    // Mapping from the user-supplied reverse-engineering document. The UI and
    // API always identify it as unverified, not a vehicle-certified decision.
    const uint8_t requested = advice.data[3] & 3;
    const uint8_t orientation = directionCode(direction.data);
    if (requested == 1 && orientation == 3) r.hint = DisplayHint::Forward;
    else if (requested == 2 && orientation == 2) r.hint = DisplayHint::Reverse;
    else { r.reason = HintReason::SourcesDisagree; return r; }
    uint32_t oldest = ageMs(gear, now);
    if (ageMs(advice, now) > oldest) oldest = ageMs(advice, now);
    if (ageMs(direction, now) > oldest) oldest = ageMs(direction, now);
    if (brakeGated && ageMs(brake, now) > oldest) oldest = ageMs(brake, now);
    r.remainingMs = sourceFreshMs - oldest;
    if (!r.remainingMs) { r.hint = DisplayHint::None; r.reason = HintReason::SourcesStale; }
    else r.reason = currentGear == 1 ? HintReason::Matched : HintReason::MatchedOutsidePark;
    return r;
  }
};

}  // namespace gearhint
