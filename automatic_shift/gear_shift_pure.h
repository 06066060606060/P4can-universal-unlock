#pragma once

#include <cstdint>
#include <cstddef>
#include <cstring>
#include <limits>

// Pure gear-request encoder and execution gate. This file must stay free of
// Arduino/ESP-IDF APIs so every checksum and interlock can be tested on host.
namespace gearshift {

constexpr uint32_t kTemplateFreshMs = 300;
constexpr uint16_t kTemplateMinCount = 5;
constexpr uint32_t kConfirmTimeoutMs = 1500;
constexpr uint32_t kRetryCooldownMs = 1500;

enum class Protocol : uint8_t { Auto = 0, V12 = 1, V13V14 = 2 };
enum class Target : uint8_t { None = 0, Park = 1, Reverse = 2, Drive = 4 };
enum class ExecutionState : uint8_t { Disabled, Idle, WaitConfirm, Confirmed, Failed };

inline const char *protocolName(Protocol p) {
  return p == Protocol::V12 ? "V12" : p == Protocol::V13V14 ? "V13V14" : "AUTO";
}
inline const char *targetName(Target t) {
  return t == Target::Drive ? "D" : t == Target::Reverse ? "R" :
         t == Target::Park ? "P" : "NONE";
}
inline const char *executionStateName(ExecutionState s) {
  return s == ExecutionState::WaitConfirm ? "WAIT_CONFIRM" :
         s == ExecutionState::Confirmed ? "CONFIRMED" :
         s == ExecutionState::Failed ? "FAILED" :
         s == ExecutionState::Disabled ? "DISABLED" : "IDLE";
}

struct Config {
  bool enabled = false;
  bool requireSeatbelt = true;
  bool requireSteering = false;       // RADAR confirmation only, not a global gate
  bool steeringFallback = false;
  bool parkSteeringFallback = false;
  uint8_t maxSpeedKph = 8, hardCutSpeedKph = 10;
  uint8_t speedBus = 2;               // physical bus: BODY=0, CHASSIS=1, PARTY=2
  uint16_t cooldownMs = 200;
  uint16_t parkConfirmDeg = 15;
  uint16_t driveReverseConfirmDeg = 30;
  uint16_t obstacleConfirmDeg = 30;
  uint16_t obstacleThresholdCm = 60;
  Protocol protocol = Protocol::Auto;
};

inline bool configValid(const Config &c) {
  return c.maxSpeedKph <= 8 && c.speedBus <= 2 && c.cooldownMs <= 10000 &&
      c.hardCutSpeedKph >= 1 && c.hardCutSpeedKph >= c.maxSpeedKph && c.hardCutSpeedKph <= 30 &&
      c.parkConfirmDeg >= 1 && c.parkConfirmDeg <= 720 &&
      c.driveReverseConfirmDeg >= 1 && c.driveReverseConfirmDeg <= 720 &&
      c.obstacleConfirmDeg >= 1 && c.obstacleConfirmDeg <= 720 &&
      c.obstacleThresholdCm >= 1 && c.obstacleThresholdCm <= 499;
}

inline void serializeConfig(const Config &c, uint8_t out[22]) {
  out[0] = 2;
  out[1] = c.enabled ? 1 : 0;
  out[2] = c.requireSeatbelt ? 1 : 0;
  out[3] = c.requireSteering ? 1 : 0;
  out[4] = c.maxSpeedKph;
  out[5] = c.speedBus;
  out[6] = c.cooldownMs & 0xFF;
  out[7] = c.cooldownMs >> 8;
  out[8] = c.parkConfirmDeg & 0xFF;
  out[9] = c.parkConfirmDeg >> 8;
  out[10] = c.driveReverseConfirmDeg & 0xFF;
  out[11] = c.driveReverseConfirmDeg >> 8;
  out[12] = c.obstacleConfirmDeg & 0xFF;
  out[13] = c.obstacleConfirmDeg >> 8;
  out[14] = static_cast<uint8_t>(c.protocol);
  out[15] = c.obstacleThresholdCm & 0xFF;
  out[16] = c.obstacleThresholdCm >> 8;
  out[17] = c.steeringFallback ? 1 : 0;
  out[18] = c.hardCutSpeedKph;
  out[19] = c.parkSteeringFallback ? 1 : 0;
  out[20] = 0;
  out[21] = 0;
}
inline bool deserializeConfig(const uint8_t *in, size_t length, Config &c) {
  if (!in || (length != 16 && length != 18 && length != 20 && length != 22)) return false;
  if ((in[0] != 1 && in[0] != 2) || (in[0] == 2 && length != 22) || in[1] > 1 || in[2] > 1 || in[3] > 1 || in[5] > 2 || in[14] > 2 ||
      (length == 16 && in[15] != 0)) return false;
  // Legacy v1 16-byte records reserved byte 15 as zero. They use the safe
  // default threshold; new 18-byte records carry a 16-bit threshold.
  const uint16_t threshold = length >= 18 ? (in[15] | (uint16_t(in[16]) << 8)) : 60;
  if (length == 18 && in[17] != 0) return false;
  if (length == 20 && (in[18] != 0 || in[19] != 0)) return false;
  if (length >= 20 && in[17] > 1) return false;
  if (length == 22 && (in[19] > 1 || in[20] != 0 || in[21] != 0)) return false;
  Config next;
  // v1 used a global angle gate. Migrating its meaning must not silently
  // retain live execution; preserve parameters and require an explicit re-enable.
  next.enabled = in[0] == 2 && in[1] != 0;
  next.requireSeatbelt = in[2] != 0;
  next.requireSteering = in[3] != 0;
  next.maxSpeedKph = in[4];
  next.speedBus = in[5] > 2 ? 2 : in[5];
  next.cooldownMs = in[6] | (uint16_t(in[7]) << 8);
  next.parkConfirmDeg = in[8] | (uint16_t(in[9]) << 8);
  next.driveReverseConfirmDeg = in[10] | (uint16_t(in[11]) << 8);
  next.obstacleConfirmDeg = in[12] | (uint16_t(in[13]) << 8);
  next.protocol = static_cast<Protocol>(in[14]);
  next.obstacleThresholdCm = threshold;
  next.steeringFallback = length >= 20 && in[17] != 0;
  next.hardCutSpeedKph = length == 22 ? in[18] : 10;
  next.parkSteeringFallback = length == 22 && in[19] != 0;
  if (!configValid(next)) return false;
  c = next;
  return true;
}

inline uint8_t sum8(const uint8_t *d, uint8_t count, uint8_t seed) {
  uint16_t sum = seed;
  for (uint8_t i = 0; i < count; ++i) sum += d[i];
  return static_cast<uint8_t>(sum);
}

inline bool validTemplate678(const uint8_t *d, uint8_t dlc) {
  return d && dlc == 7 && d[1] < 0x10 &&
      d[0] == sum8(d + 1, 6, 0x7E);
}
inline bool editGear678(uint8_t *d, uint8_t dlc, Target target) {
  if (!validTemplate678(d, dlc) ||
      (target != Target::Park && target != Target::Reverse && target != Target::Drive))
    return false;
  d[1] = (static_cast<uint8_t>(target) << 4) | ((d[1] + 1) & 0x0F);
  d[0] = sum8(d + 1, 6, 0x7E);
  return true;
}

inline uint8_t v12Checksum(uint8_t code, uint8_t counter) {
  static const uint8_t gearTable[8] = {0x00,0xE0,0xEF,0x0F,0xF1,0xE9,0x00,0x00};
  static const uint8_t countTable[16] = {
      0x46,0x44,0x52,0x6D,0x43,0x41,0xDD,0xF9,
      0x4C,0xA5,0xF6,0x8C,0x49,0x2F,0x31,0x3B};
  return gearTable[code] ^ countTable[counter];
}
inline bool validTemplate229(const uint8_t *d, uint8_t dlc) {
  if (!d || (dlc != 3 && dlc != 8)) return false;
  return d[0] == v12Checksum((d[1] >> 4) & 7, d[1] & 15);
}
inline bool editGear229(uint8_t *d, uint8_t dlc, Target target) {
  if (!validTemplate229(d, dlc) ||
      (target != Target::Park && target != Target::Reverse && target != Target::Drive))
    return false;
  uint8_t code = target == Target::Park ? 0 :
                 target == Target::Reverse ? 2 : 4;
  const uint8_t counter = (d[1] + 1) & 15;
  d[0] = v12Checksum(code, counter);
  d[1] = (d[1] & 0x80) | (code << 4) | counter;
  d[2] = (d[2] & 0xFC) | (target == Target::Park ? 1 : 0);
  return true;
}

struct Template {
  uint8_t data[8] = {};
  uint8_t dlc = 0;
  uint32_t observedMs = 0;
  uint16_t count = 0;
  bool seen = false;
};
struct TemplateObserver {
  Template v12;
  Template v13V14;

  void reset() {
    v12 = {};
    v13V14 = {};
  }
  void observe(uint8_t bus, uint32_t id, uint8_t dlc, bool extended,
              bool remote, const uint8_t *data, uint32_t now) {
    if (bus != 0 || extended || remote || dlc > 8 || (dlc && !data)) return;
    if (id == 0x678 && validTemplate678(data, dlc)) save(v13V14, data, dlc, now);
    else if (id == 0x229 && validTemplate229(data, dlc) &&
             ((data[1] >> 4) & 7) == 0) save(v12, data, dlc, now);
  }
  static void save(Template &t, const uint8_t *data, uint8_t dlc, uint32_t now) {
    if (t.count != UINT16_MAX) ++t.count;
    t.seen = true; t.observedMs = now; t.dlc = dlc;
    for (uint8_t i = 0; i < sizeof(t.data); ++i)
      t.data[i] = i < dlc ? data[i] : 0;
  }
};
inline bool templateReady(const Template &t, uint32_t now) {
  return t.seen && t.count >= kTemplateMinCount &&
      static_cast<uint32_t>(now - t.observedMs) < kTemplateFreshMs;
}

struct SafetyInputs {
  int gear = -1;
  int driverBrake = -1, brakeApply = -1, accelerator = -1;
  int speedCentiKph = 0;
  bool speedValid = false;
  int leftFront = -1, leftRear = -1, rightFront = -1, rightRear = -1, trunk = -1;
  int buckle = -1;
  uint32_t brakeEpoch = 0;
  bool brakeEpochValid = false;
  bool brakeEdge = false;
  // Model Y Juniper keeps the physical driver state but reports apply=0.
  // Other profiles retain the stricter both-signal final authorization.
  bool brakeApplyRequired = true;
};
struct Decision {
  bool valid = false;
  Target target = Target::None;
  const char *source = "";
  // Radar/pair candidates consume the physical press edge. The brake-held
  // steering authorizer may legitimately trigger after its baseline was taken.
  bool authorizeDuringBrakeHold = false;
};

// A brake epoch is a physical release→press edge, not a UI switch event or a
// candidate session. Execution is entitled to one request per epoch.
class BrakeEpochTracker {
 public:
  bool update(bool pressed, bool valid = true) {
    if (!valid) {
      // Missing/invalid pedal data is not a physical release.
      wasPressed_ = false;
      releaseSeen_ = false;
      return false;
    }
    if (!pressed) {
      wasPressed_ = false;
      releaseSeen_ = true;
      return false;
    }
    if (!wasPressed_ && releaseSeen_) {
      if (epoch_ != UINT32_MAX) ++epoch_;
      wasPressed_ = true;
      return true;
    }
    return false;
  }
  uint32_t epoch() const { return epoch_; }
  bool armed(bool pressed) const { return releaseSeen_ && pressed; }
  bool wasPressed() const { return wasPressed_; }
  bool releaseSeen() const { return releaseSeen_; }
 private:
  uint32_t epoch_ = 0;
  bool wasPressed_ = false;
  bool releaseSeen_ = false;
};
struct EngineState {
  ExecutionState state = ExecutionState::Idle;
  uint8_t fromGear = 0, target = 0;
  uint32_t sentMs = 0, resultMs = 0, lastAttemptMs = 0, brakeEpoch = 0;
  uint32_t sends = 0, confirmations = 0, failures = 0;
  uint8_t lastCanId = 0, lastDlc = 0;
  uint8_t lastData[8] = {};
};
enum class Deny : uint8_t {
  Disabled, Ready, ProfileUnavailable, NoCandidate, TargetNone, BrakeInvalid,
  BrakeReleased, GearInvalid, AcceleratorPressed, SpeedInvalid, Moving,
  DoorNotClosed, BuckleOff, TemplateMissing, TemplateStale, TemplateAmbiguous,
  EncoderInvalid, TxFailed, WaitConfirm, ConfirmTimeout, ConfirmedSameGear, Cooldown,
  BrakeActionUsed, BrakeNotArmed, HardSpeedCut, StateFailed
};
inline const char *denyName(Deny d) {
  static const char *const names[] = {
    "DISABLED","READY","PROFILE_UNAVAILABLE","NO_CANDIDATE","TARGET_NONE","BRAKE_INVALID",
    "BRAKE_RELEASED","GEAR_INVALID","ACCELERATOR_PRESSED","SPEED_INVALID","MOVING",
    "DOOR_NOT_CLOSED","BUCKLE_OFF","TEMPLATE_MISSING","TEMPLATE_STALE","TEMPLATE_AMBIGUOUS",
    "ENCODER_INVALID","TX_FAILED","WAIT_CONFIRM","CONFIRM_TIMEOUT","CONFIRMED_SAME_GEAR","COOLDOWN","BRAKE_ACTION_USED","BRAKE_NOT_ARMED","HARD_SPEED_CUT","STATE_FAILED"};
  return names[static_cast<unsigned>(d)];
}
struct Action {
  Deny reason = Deny::Disabled;
  bool send = false;
  uint32_t canId = 0;
  uint8_t dlc = 0;
  uint8_t data[8] = {};
  Target target = Target::None;
};

inline bool safetyReady(const SafetyInputs &in, const Config &cfg,
                       const Decision &decision = Decision{}) {
  if (!in.brakeEpochValid || (!in.brakeEdge && !decision.authorizeDuringBrakeHold))
    return false;
  if (in.gear != 1 && in.gear != 2 && in.gear != 4) return false;
  if (in.driverBrake != 2) return false;
  if (in.brakeApplyRequired && in.brakeApply != 1) return false;
  if (!in.brakeApplyRequired && in.brakeApply != 0 && in.brakeApply != 1) return false;
  if (in.accelerator != 0) return false;
  if (!in.speedValid) return false;
  const int speed = in.speedCentiKph < 0 ? -in.speedCentiKph : in.speedCentiKph;
  if (speed > static_cast<int>(cfg.maxSpeedKph) * 100) return false;
  if (speed > static_cast<int>(cfg.hardCutSpeedKph) * 100) return false;
  if (in.leftFront != 2 || in.leftRear != 2 ||
      in.rightFront != 2 || in.rightRear != 2 || in.trunk != 2) return false;
  if (cfg.requireSeatbelt && in.buckle != 2) return false;
  return true;
}
inline Deny safetyDeny(const SafetyInputs &in, const Config &cfg,
                      const Decision &decision = Decision{}) {
  if (!in.brakeEpochValid ||
      (!in.brakeEdge && !decision.authorizeDuringBrakeHold))
    return Deny::BrakeNotArmed;
  if (in.gear != 1 && in.gear != 2 && in.gear != 4) return Deny::GearInvalid;
  const bool applyUsable = in.brakeApply == 0 || in.brakeApply == 1;
  if (in.driverBrake == 0 || in.driverBrake == 3 || in.brakeApply == -1 ||
      (in.brakeApplyRequired ? in.brakeApply != 1 : !applyUsable))
    return Deny::BrakeInvalid;
  if (in.driverBrake != 2) return Deny::BrakeReleased;
  if (in.accelerator != 0) return Deny::AcceleratorPressed;
  if (!in.speedValid) return Deny::SpeedInvalid;
  const int speed = in.speedCentiKph < 0 ? -in.speedCentiKph : in.speedCentiKph;
  if (speed > static_cast<int>(cfg.hardCutSpeedKph) * 100) return Deny::HardSpeedCut;
  if (speed > static_cast<int>(cfg.maxSpeedKph) * 100) return Deny::Moving;
  if (in.leftFront != 2 || in.leftRear != 2 ||
      in.rightFront != 2 || in.rightRear != 2 || in.trunk != 2) return Deny::DoorNotClosed;
  if (cfg.requireSeatbelt && in.buckle != 2) return Deny::BuckleOff;
  return Deny::NoCandidate;
}

class ExecutionEngine {
 public:
  EngineState state;
  void reset() { state = {}; }

  Action service(uint32_t now, bool profileAvailable, const SafetyInputs &in,
                 const Config &cfg, const Decision &decision,
                 const TemplateObserver &templates) {
    if (!cfg.enabled) {
      // Preserve the consumed-brake state. Toggling the feature switch off/on
      // must not grant another request during the same physical brake press.
      return {};
    }
    if (state.state == ExecutionState::Disabled) state.state = ExecutionState::Idle;
    if (!profileAvailable || !configValid(cfg)) return {Deny::ProfileUnavailable};
    if (state.state == ExecutionState::WaitConfirm) {
      if (in.gear == static_cast<int>(state.target)) {
        state.state = ExecutionState::Confirmed;
        state.resultMs = now;
        if (state.confirmations != UINT32_MAX) ++state.confirmations;
        return {Deny::ConfirmedSameGear};
      }
      if (in.brakeEpoch != state.brakeEpoch) {
        state.state = ExecutionState::Failed;
        state.resultMs = now;
        if (state.failures != UINT32_MAX) ++state.failures;
        return {Deny::BrakeReleased};
      }
      if (static_cast<uint32_t>(now - state.sentMs) >= kConfirmTimeoutMs) {
        state.state = ExecutionState::Failed;
        state.resultMs = now;
        state.lastAttemptMs = now;
        if (state.failures != UINT32_MAX) ++state.failures;
        return {Deny::ConfirmTimeout};
      }
      return {Deny::WaitConfirm};
    }
    if (state.state == ExecutionState::Confirmed) {
      // Hard interlock: one CAN request per brake press. A reverse candidate
      // after D→R (or vice versa) cannot rearm until brake release is observed
      // and a fresh press creates a new brake epoch.
      if (in.brakeEpoch == state.brakeEpoch) return {Deny::BrakeActionUsed};
      if (state.lastAttemptMs &&
          static_cast<uint32_t>(now - state.lastAttemptMs) <
              cfg.cooldownMs)
        return {Deny::Cooldown};
      state.state = ExecutionState::Idle;
    } else if (state.state == ExecutionState::Failed) {
      // A timeout/TX failure never retries under the same brake press. A new
      // brake edge is required before another candidate can arm.
      if (in.brakeEpoch == state.brakeEpoch) return {Deny::StateFailed};
      if (state.lastAttemptMs &&
          static_cast<uint32_t>(now - state.lastAttemptMs) <
              (cfg.cooldownMs > kRetryCooldownMs ? cfg.cooldownMs : kRetryCooldownMs))
        return {Deny::Cooldown};
      state.state = ExecutionState::Idle;
    }

    if (!decision.valid || decision.target == Target::None) return {Deny::NoCandidate};
    const Deny safety = safetyDeny(in, cfg, decision);
    if (safety != Deny::NoCandidate) return {safety};
    if (in.gear == static_cast<int>(decision.target)) return {Deny::ConfirmedSameGear};

    const bool v12Ready = templateReady(templates.v12, now);
    const bool v13Ready = templateReady(templates.v13V14, now);
    Protocol selected = cfg.protocol;
    if (selected == Protocol::Auto) {
      if (v12Ready == v13Ready) return {v12Ready ? Deny::TemplateAmbiguous : Deny::TemplateMissing};
      selected = v12Ready ? Protocol::V12 : Protocol::V13V14;
    } else if ((selected == Protocol::V12 && !v12Ready) ||
               (selected == Protocol::V13V14 && !v13Ready)) {
      return {Deny::TemplateMissing};
    }

    uint8_t dlc;
    uint8_t data[8];
    uint32_t id;
    if (selected == Protocol::V12) {
      const Template &t = templates.v12;
      dlc = t.dlc; memcpy(data, t.data, sizeof(data)); id = 0x229;
      if (!editGear229(data, dlc, decision.target)) return {Deny::EncoderInvalid};
    } else {
      const Template &t = templates.v13V14;
      dlc = 7; memcpy(data, t.data, sizeof(data)); id = 0x678;
      if (!editGear678(data, dlc, decision.target)) return {Deny::EncoderInvalid};
    }

    Action out;
    out.send = true; out.reason = Deny::Ready;
    out.canId = id; out.dlc = dlc; out.target = decision.target;
    memcpy(out.data, data, sizeof(out.data));
    state.state = ExecutionState::WaitConfirm;
    state.fromGear = static_cast<uint8_t>(in.gear);
    state.target = static_cast<uint8_t>(decision.target);
    state.sentMs = now; state.lastAttemptMs = now; state.brakeEpoch = in.brakeEpoch;
    state.lastCanId = static_cast<uint8_t>(id); state.lastDlc = dlc;
    memcpy(state.lastData, data, sizeof(state.lastData));
    if (state.sends != UINT32_MAX) ++state.sends;
    return out;
  }
};

}  // namespace gearshift
