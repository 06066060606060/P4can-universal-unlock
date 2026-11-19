#pragma once
#include "gear_hint_v12_raw_pure.h"

// Experimental DISPLAY-ONLY distance rules. There is no actuator/transport API.
// Reference fields: commaai/opendbc Model 3 vehicle/party + model3dbc SDI.
// No swept path, road-wheel conversion, TTC, pressure or hold certification.
namespace gearhintv12live {
constexpr uint32_t kFreshMs = 300;
constexpr uint32_t kZeroDwellMs = 500;
constexpr uint32_t kStableMs = 200;
enum Signal : uint8_t { Gear, Brake, Front, Rear, Speed, Steering, LeftDoors, RightDoors, Buckle, SignalCount };
struct Config {
  // requireSteering applies to RADAR candidates only; each manual steering
  // source has its own switch and angle. Names remain API-compatible.
  bool requireSeatbelt=true, requireSteering=false, steeringFallback=false;
  bool parkSteeringFallback=false;
  // P steering needs a physical sign calibration. D/R uses relative magnitude only.
  bool parkSteeringCalibrated=false, parkSteeringLeftIsNegative=false;
  uint8_t maxSpeedKph=8, hardCutSpeedKph=10;
  uint16_t cooldownMs=200,pConfirmDeg=15,drConfirmDeg=30,obstacleDeg=30;
  uint16_t obstacleThresholdCm=60;
};
constexpr uint16_t kSignalIds[SignalCount] = {0x118,0x145,0x20E,0x22E,0x257,0x129,0x102,0x103,0x3C2};
inline const char *signalName(uint8_t s) {
  static const char *const n[] = {"gear","brake","front","rear","speed","steering","leftDoors","rightDoors","buckle"};
  return s < SignalCount ? n[s] : "unknown";
}
inline int signalIndex(uint32_t id) {
  for (uint8_t i=0;i<SignalCount;++i) if (kSignalIds[i]==id) return i;
  return -1;
}
enum class Candidate : uint8_t { None, Forward, Reverse };
enum class CandidateSource : uint8_t { None, Radar, VehiclePair, ParkSteering, DriveReverseSteering };
inline const char *sourceName(CandidateSource source) {
  switch(source) {
    case CandidateSource::Radar:return "RADAR";
    case CandidateSource::VehiclePair:return "VEHICLE_PAIR";
    case CandidateSource::ParkSteering:return "P_STEERING";
    case CandidateSource::DriveReverseSteering:return "DR_STEERING";
    default:return "NONE";
  }
}
inline bool sameGear(Candidate candidate,int gear) {
  return (gear==4&&candidate==Candidate::Forward)||(gear==2&&candidate==Candidate::Reverse);
}
inline const char *candidateName(Candidate c) {
  return c==Candidate::Forward ? "FORWARD" : c==Candidate::Reverse ? "REVERSE" : "NONE";
}
enum class Reason : uint8_t {
  ReceiverUnavailable, Missing, Stale, Length, Checksum, CounterConflict,
  GearInvalid, BrakeInvalid, BrakeReleased, AcceleratorInvalid, AcceleratorPressed,
  SpeedInvalid, Moving, ZeroDwell, DoorNotClosed, BuckleInvalid,
  BuckleOff, ProbeUnavailable, ProbeBlocked, ProbeUnknown,
  WaitPair, WaitStable, CandidateReady, EqualDistance, NoObject, ObstacleBeyondThreshold, SteeringInvalid, WaitWheel, SteeringRearmRequired, BrakeActionUsed, SteeringCalibrationRequired, Cooldown, HardSpeedCut, PrearmBrakeHeld, RadarWaitBrake, RadarCandidateLost, ConfigInvalid
};
inline const char *reasonName(Reason r) {
  static const char *const n[] = {"RECEIVER_UNAVAILABLE","INPUT_MISSING","INPUT_STALE","INPUT_LENGTH",
    "INPUT_CHECKSUM","COUNTER_CONFLICT","GEAR_INVALID","BRAKE_INVALID","BRAKE_RELEASED",
    "ACCELERATOR_INVALID","ACCELERATOR_PRESSED","SPEED_INVALID","VEHICLE_MOVING","WAIT_ZERO_SPEED_DWELL",
    "DOOR_NOT_CLOSED","BUCKLE_INVALID","BUCKLE_OFF",
    "PROBE_UNAVAILABLE","PROBE_BLOCKED","PROBE_UNKNOWN","WAIT_DISTINCT_SENSOR_UPDATE",
    "WAIT_STABLE_DISTANCE","DISTANCE_RULE_CANDIDATE",
    "EQUAL_FRONT_REAR_DISTANCE","NO_OBJECT_DETECTED","OBSTACLE_BEYOND_DISTANCE_THRESHOLD","STEERING_INVALID","WAIT_STEERING_CONFIRMATION","CANDIDATE_COOLDOWN","STEERING_REARM_REQUIRED","BRAKE_ACTION_USED","STEERING_CALIBRATION_REQUIRED","HARD_SPEED_CUT","PREARM_BRAKE_HELD","RADAR_WAIT_BRAKE","RADAR_CANDIDATE_LOST","CONFIG_INVALID"};
  const unsigned i=static_cast<unsigned>(r); return i<sizeof(n)/sizeof(n[0])?n[i]:"UNKNOWN";
}
inline int checksumPosition(uint8_t s) {
  return s==Gear||s==Brake||s==Speed ? 0 : s==Front||s==Rear ? 7 : -1;
}
inline int counterValue(uint8_t s,const uint8_t *d) {
  return s==Front||s==Rear ? d[6]>>6 : s==Gear||s==Brake||s==Speed||s==Steering ? d[1]&15 : -1;
}
inline uint8_t checksum(uint32_t id,const uint8_t *d,int excluded) {
  uint32_t sum=(id&255)+(id>>8);
  for(int i=0;i<8;++i) if(i!=excluded) sum+=d[i];
  return static_cast<uint8_t>(sum);
}
inline uint16_t speedRaw(const uint8_t *d) { return (d[1]>>4)|(uint16_t(d[2])<<4); }
inline int16_t wheelDeciDeg(const uint8_t *d) { return int16_t((d[2]|(uint16_t(d[3]&63)<<8))-8192); }
struct Track {
  gearhintv12::Frame frame;
  uint32_t generation=0, zeroSince=0, zeroSamples=0;
  bool seen=false, valid=false, counterSeen=false, zeroWindow=false;
  uint8_t counter=0;
  Reason invalidReason=Reason::Missing;
};
struct Scan {
  uint16_t raw[6]={};
  int16_t minCm=-1;
  uint8_t noObjectCount=0, measuredCount=0;
  bool near=false, valid=false;
  Reason reason=Reason::ProbeUnavailable;
};
inline Scan scan(const gearhintv12::Frame &f) {
  Scan s;
  if (!gearhintv12::referenceSdiRaw(f,s.raw)) return s;
  for (uint16_t v:s.raw) {
    if(v==511) {s.reason=Reason::ProbeUnavailable;return s;}
    if(v==0) {s.reason=Reason::ProbeBlocked;return s;}
    if(v==1) {s.near=true;continue;}
    if(v==500) {++s.noObjectCount;continue;} // Enum, NEVER a measured 500 cm.
    if(v>500) {s.reason=Reason::ProbeUnknown;return s;}
    ++s.measuredCount;
    if(s.minCm<0||v<s.minCm) s.minCm=v;
  }
  s.valid=true; return s;
}
inline bool objectDetected(const Scan &s) { return s.valid&&(s.near||s.measuredCount>0); }
// NEAR_DETECTION has no usable distance and is always treated as inside the
// threshold. A measured echo such as 400 cm remains valid but only blocks the
// travel direction when it is at or below the configured threshold.
inline bool objectWithinThreshold(const Scan &s,uint16_t thresholdCm) {
  if(!s.valid) return false;
  if(s.near) return true;
  return s.measuredCount>0&&s.minCm>=0&&uint16_t(s.minCm)<=thresholdCm;
}
inline bool required(uint8_t signal,int gear,const Config &config) {
  if(signal==Steering) return config.requireSteering&&gear!=1;
  if(signal==Buckle) return config.requireSeatbelt;
  if(signal==Front&&gear==2) return false;
  if(signal==Rear&&gear==4) return false;
  return signal<SignalCount;
}
struct Inputs {
  Track tracks[SignalCount];
  Scan front,rear;
  int gear=-1,driverBrake=-1,brakeApply=-1,accelRaw=-1,speedCentiKph=0,wheelAngleDeci=0;
  int buckle=-1,occupancy=-1,leftFront=-1,leftRear=-1,rightFront=-1,rightRear=-1,trunk=-1;
  uint32_t zeroForMs=0;
};
struct Gate { bool ready=false; Reason reason=Reason::Missing; int signal=-1; };
struct Proposal { Candidate candidate=Candidate::None; Reason reason=Reason::NoObject; const char *rule="NONE"; };
struct Window {
  bool active=false,proposalSeen=false;
  int gear=-1;
  bool baselineValid=false,directionChanged=false;
  int baselineWheel=0;
  Candidate lastDirection=Candidate::None;
  uint32_t directionChangedMs=0;
  uint32_t frontGeneration=0,rearGeneration=0,stableSince=0,pairs=0;
  Proposal proposal;
};
struct Result {
  Candidate candidate=Candidate::None;
  Reason reason=Reason::Missing;
  int blockedSignal=-1;
  uint32_t remainingMs=0,stableForMs=0,pairs=0;
  uint32_t cooldownRemainingMs=0;
  int wheelDeltaDeci=0,confirmationDeci=0;
  const char *rule="NONE";
};

inline bool validSteering(const Inputs &in,uint32_t now);
inline Proposal propose(const Inputs &in,const Config &config);
constexpr uint32_t kPrearmStableMs = 100;
constexpr int kManualSteeringRearmDeci = 50;  // 5 degrees from center
struct PrearmResult {
  bool ready=false, speedCut=false, sameGearIgnored=false, radarAvailable=false;
  bool radarSteeringRequired=false, radarPriority=false;
  CandidateSource source=CandidateSource::None;
  Candidate candidate=Candidate::None;
  Reason reason=Reason::Missing;
  int blockedSignal=-1, wheelAngleDeci=0, baselineWheelDeci=0, wheelDeltaDeci=0;
  uint32_t stableForMs=0, remainingMs=0, brakeEpoch=0;
  const char *rule="NONE";
};
inline bool freshTrack(const Track &t,uint32_t now) {
  return t.seen&&t.valid&&t.frame.dlc==8&&now-t.frame.observedMs<kFreshMs;
}
inline bool hardSpeedCut(const Inputs &in,uint32_t now,uint8_t limitKph) {
  const auto &t=in.tracks[Speed];
  if(!freshTrack(t,now)||speedRaw(t.frame.data)==4095) return false;
  const int speed=in.speedCentiKph<0?-in.speedCentiKph:in.speedCentiKph;
  return speed>int(limitKph)*100;
}

// One tracker is owned by the execution service, never by a browser request.
// A ready candidate must exist BEFORE the physical pedal press. While held,
// safety/source changes can revoke it but can never arm a replacement.
class PrearmTracker {
 public:
  void reset() { seen_=ready_=false; candidate_=Candidate::None; gear_=0; rule_="NONE"; since_=0; }
  PrearmResult update(const Inputs &in,uint32_t now,const Config &config,
                      const Proposal *external=nullptr) {
    PrearmResult out=evaluate(in,now,config,external);
    out.radarSteeringRequired=config.requireSteering&&in.gear!=1&&
        out.source==CandidateSource::Radar;
    const bool held=in.driverBrake==2;
    if(out.speedCut||out.candidate==Candidate::None) { reset(); return out; }
    const bool same=seen_&&out.candidate==candidate_&&in.gear==gear_&&strcmp(rule_,out.rule)==0;
    if(held) {
      if(!same||!ready_) {
        reset(); out.reason=Reason::PrearmBrakeHeld; return out;
      }
      out.ready=true; out.reason=Reason::CandidateReady;
      out.stableForMs=now-since_;
      return out;
    }
    if(!same) {
      reset(); seen_=true; candidate_=out.candidate; gear_=in.gear;
      rule_=out.rule; since_=now;
    }
    out.stableForMs=now-since_;
    ready_=out.stableForMs>=kPrearmStableMs;
    out.ready=ready_; out.reason=ready_?Reason::CandidateReady:Reason::WaitStable;
    return out;
  }
 private:
  PrearmResult evaluate(const Inputs &in,uint32_t now,const Config &c,const Proposal *external) const {
    PrearmResult out; out.wheelAngleDeci=in.wheelAngleDeci;
    if(c.maxSpeedKph>8||c.hardCutSpeedKph<1||c.hardCutSpeedKph>30||c.hardCutSpeedKph<c.maxSpeedKph||
       c.cooldownMs>10000||c.pConfirmDeg<1||c.pConfirmDeg>720||c.drConfirmDeg<1||c.drConfirmDeg>720||
       c.obstacleDeg<1||c.obstacleDeg>720||c.obstacleThresholdCm<1||c.obstacleThresholdCm>499) {
      out.reason=Reason::ConfigInvalid; return out;
    }
    // This cheap check precedes brake, radar and steering decision work.
    if(hardSpeedCut(in,now,c.hardCutSpeedKph)) {
      out.speedCut=true; out.reason=Reason::HardSpeedCut; return out;
    }
    out.remainingMs=kFreshMs;
    const auto require=[&](uint8_t signal) {
      const auto &t=in.tracks[signal];
      if(!freshTrack(t,now)) {
        out.reason=!t.seen?Reason::Missing:!t.valid?t.invalidReason:
            t.frame.dlc!=8?Reason::Length:Reason::Stale;
        out.blockedSignal=signal; out.remainingMs=0; return false;
      }
      const uint32_t remaining=kFreshMs-(now-t.frame.observedMs);
      if(remaining<out.remainingMs) out.remainingMs=remaining;
      return true;
    };
    const uint8_t core[]={Gear,Brake,Speed,LeftDoors,RightDoors};
    for(uint8_t signal:core)
      if(!require(signal)) return out;
    if(c.requireSeatbelt&&!require(Buckle)) return out;
    if(in.gear!=1&&in.gear!=2&&in.gear!=4) {out.reason=Reason::GearInvalid;return out;}
    if(in.driverBrake!=1&&in.driverBrake!=2) {out.reason=Reason::BrakeInvalid;return out;}
    if(speedRaw(in.tracks[Speed].frame.data)==4095) {out.reason=Reason::SpeedInvalid;return out;}
    const int speed=in.speedCentiKph<0?-in.speedCentiKph:in.speedCentiKph;
    if(speed>int(c.maxSpeedKph)*100) {out.reason=Reason::Moving;return out;}
    if(c.maxSpeedKph==0&&in.zeroForMs<kZeroDwellMs) {out.reason=Reason::ZeroDwell;return out;}
    if(in.accelRaw!=0) {out.reason=in.accelRaw==255?Reason::AcceleratorInvalid:Reason::AcceleratorPressed;return out;}
    if(in.leftFront!=2||in.leftRear!=2||in.rightFront!=2||in.rightRear!=2||in.trunk!=2)
      {out.reason=Reason::DoorNotClosed;return out;}
    if(c.requireSeatbelt&&in.buckle!=2)
      {out.reason=in.buckle==0||in.buckle==3?Reason::BuckleInvalid:Reason::BuckleOff;return out;}
    out.radarAvailable=in.front.valid&&in.rear.valid;
    Proposal p;
    CandidateSource source=CandidateSource::None;
    if(external) {
      p=*external;
      if(sameGear(p.candidate,in.gear)) {
        // Same-gear advice is not a usable candidate and must not suppress
        // the P or D/R steering selector evaluated below.
        out.sameGearIgnored=true;p={};
      }
      if(p.candidate!=Candidate::None) source=CandidateSource::VehiclePair;
    } else {
      // Missing radar blocks radar inference, not the independent driver
      // steering source. Do not interpret unavailable probes as clear space.
      bool radarReady=true;
      const uint8_t radarSignals[]={Front,Rear};
      for(uint8_t signal:radarSignals) {
        if((signal==Front&&in.gear==2)||(signal==Rear&&in.gear==4)) continue;
        const auto &scan=signal==Front?in.front:in.rear;
        if(!require(signal)||!scan.valid) {
          if(!scan.valid&&freshTrack(in.tracks[signal],now)) out.reason=scan.reason;
          out.blockedSignal=signal;radarReady=false;break;
        }
      }
      if(radarReady) {p=propose(in,c);out.reason=p.reason;}
      else {p.reason=out.reason;}
      if(sameGear(p.candidate,in.gear)) {out.sameGearIgnored=true;p={};}
      if(p.candidate!=Candidate::None) source=CandidateSource::Radar;
    }
    // Radar steering confirmation is deferred until after the brake edge. P
    // never uses this switch; D/R keeps radar priority and confirms relative
    // motion in the runtime RadarSteeringTracker below.
    out.source=source;
    out.candidate=p.candidate;out.reason=p.reason;out.rule=p.rule;
    return out;
  }
  bool seen_=false,ready_=false;
  Candidate candidate_=Candidate::None;
  int gear_=0;
  uint32_t since_=0;
  const char *rule_="NONE";
};
// Manual steering is authorized after the pedal edge, not before it. The
// baseline is captured when braking starts (or on the first valid angle while
// the pedal is held); any later relative change can trigger immediately.
class BrakeSteeringTracker {
 public:
  void reset() {
    epoch_=0; gear_=-1; baselineValid_=false; used_=false;
    baseline_=0; since_=0;
  }
  PrearmResult update(const Inputs &in,uint32_t now,const Config &c,
                      uint32_t brakeEpoch,bool brakeEdge,bool brakeValid) {
    PrearmResult out; out.wheelAngleDeci=in.wheelAngleDeci; out.brakeEpoch=brakeEpoch;
    if(c.maxSpeedKph>8||c.hardCutSpeedKph<1||c.hardCutSpeedKph>30||
       c.hardCutSpeedKph<c.maxSpeedKph||c.cooldownMs>10000||c.pConfirmDeg<1||
       c.pConfirmDeg>720||c.drConfirmDeg<1||c.drConfirmDeg>720||c.obstacleDeg<1||
       c.obstacleDeg>720||c.obstacleThresholdCm<1||c.obstacleThresholdCm>499) {
      reset(); out.reason=Reason::ConfigInvalid; return out;
    }
    if(hardSpeedCut(in,now,c.hardCutSpeedKph)) {
      reset(); out.speedCut=true; out.reason=Reason::HardSpeedCut; return out;
    }
    const auto &speed=in.tracks[Speed];
    if(!freshTrack(speed,now)||speedRaw(speed.frame.data)==4095) {
      baselineValid_=false; out.reason=Reason::SpeedInvalid; return out;
    }
    const int absSpeed=in.speedCentiKph<0?-in.speedCentiKph:in.speedCentiKph;
    if(absSpeed>int(c.maxSpeedKph)*100) {
      // A transient over-limit sample invalidates the pedal baseline while
      // preserving the pedal epoch and any already-consumed one-shot action.
      baselineValid_=false; out.reason=Reason::Moving; return out;
    }
    if(c.maxSpeedKph==0&&in.zeroForMs<kZeroDwellMs) {
      baselineValid_=false; out.reason=Reason::ZeroDwell; return out;
    }
    if(!brakeValid||in.driverBrake!=2) {
      reset(); out.reason=Reason::BrakeReleased; return out;
    }
    if(brakeEdge) {
      epoch_=brakeEpoch; gear_=in.gear; baselineValid_=false; used_=false;
      baseline_=in.wheelAngleDeci; since_=now;
    }
    if(brakeEpoch!=epoch_) {reset(); out.reason=Reason::BrakeReleased; return out;}
    if(in.gear!=1&&in.gear!=2&&in.gear!=4) {
      reset(); out.reason=Reason::GearInvalid; return out;
    }
    if(in.gear!=gear_) {
      gear_=in.gear; baselineValid_=false; baseline_=in.wheelAngleDeci; since_=now;
      if(!used_) used_=false;
    }
    const bool enabled=in.gear==1?c.parkSteeringFallback:c.steeringFallback;
    if(!enabled) {out.reason=Reason::WaitWheel; return out;}
    if(!freshTrack(in.tracks[Steering],now)||!validSteering(in,now)) {
      baselineValid_=false; out.reason=Reason::SteeringInvalid; return out;
    }
    if(used_) {out.reason=Reason::BrakeActionUsed; return out;}
    if(!baselineValid_) {
      baselineValid_=true; baseline_=in.wheelAngleDeci; since_=now;
      out.baselineWheelDeci=baseline_; out.wheelDeltaDeci=0;
      out.reason=Reason::WaitWheel; return out;
    }
    out.baselineWheelDeci=baseline_;
    out.wheelDeltaDeci=in.wheelAngleDeci-baseline_;
    out.stableForMs=now-since_;
    const uint32_t age=now-in.tracks[Steering].frame.observedMs;
    out.remainingMs=age<kFreshMs?kFreshMs-age:0;
    const int magnitude=out.wheelDeltaDeci<0?-out.wheelDeltaDeci:out.wheelDeltaDeci;
    const int threshold=10*int(in.gear==1?c.pConfirmDeg:c.drConfirmDeg);
    if(magnitude<threshold) {out.reason=Reason::WaitWheel; return out;}
    if(in.gear==1&&!c.parkSteeringCalibrated) {
      used_=true; out.reason=Reason::SteeringCalibrationRequired; return out;
    }
    used_=true;
    out.ready=true; out.reason=Reason::CandidateReady;
    if(in.gear==1) {
      const bool left=out.wheelDeltaDeci<0;
      if(left!=c.parkSteeringLeftIsNegative) {
        out.candidate=Candidate::Reverse; out.rule="P_RIGHT_STEERING_TO_R";
      } else {
        out.candidate=Candidate::Forward; out.rule="P_LEFT_STEERING_TO_D";
      }
      out.source=CandidateSource::ParkSteering;
    } else if(in.gear==4) {
      out.candidate=Candidate::Reverse; out.rule="D_RELATIVE_STEERING_TO_R";
      out.source=CandidateSource::DriveReverseSteering;
    } else {
      out.candidate=Candidate::Forward; out.rule="R_RELATIVE_STEERING_TO_D";
      out.source=CandidateSource::DriveReverseSteering;
    }
    return out;
  }
 private:
  uint32_t epoch_=0,since_=0;
  int gear_=-1,baseline_=0;
  bool baselineValid_=false,used_=false;
};

// D/R radar steering confirmation. A radar candidate must already be ready on
// the pedal edge; the baseline is captured then, and relative motion triggers
// immediately. If that radar candidate disappears, manual D/R cannot downgrade
// into the same pedal epoch.
class RadarSteeringTracker {
 public:
  void reset() {
    epoch_=0; gear_=-1; baseline_=0; since_=0; candidate_=Candidate::None;
    baselineValid_=false; used_=false; priorityEpoch_=UINT32_MAX;
  }
  PrearmResult update(const Inputs &in,uint32_t now,const Config &c,
                      uint32_t brakeEpoch,bool brakeEdge,bool brakeValid,
                      bool radarReady,Candidate radarCandidate) {
    PrearmResult out; out.wheelAngleDeci=in.wheelAngleDeci; out.brakeEpoch=brakeEpoch;
    out.radarSteeringRequired=true; out.radarPriority=brakeEpoch==priorityEpoch_;
    if(!brakeValid||in.driverBrake!=2) {reset(); out.reason=Reason::BrakeReleased; return out;}
    if(brakeEdge) {
      if(radarReady&&radarCandidate!=Candidate::None&&(in.gear==2||in.gear==4)) {
        epoch_=brakeEpoch; priorityEpoch_=brakeEpoch; gear_=in.gear;
        candidate_=radarCandidate; baselineValid_=false; used_=false;
        baseline_=in.wheelAngleDeci; since_=now;
        out.radarPriority=true; out.reason=Reason::WaitWheel; return out;
      }
      reset(); out.reason=Reason::RadarWaitBrake; return out;
    }
    if(brakeEpoch!=priorityEpoch_) {
      out.reason=Reason::RadarWaitBrake; return out;
    }
    out.radarPriority=true;
    if(!radarReady||radarCandidate!=candidate_||in.gear!=gear_) {
      candidate_=Candidate::None; out.reason=Reason::RadarCandidateLost; return out;
    }
    if(used_) {out.reason=Reason::BrakeActionUsed; return out;}
    if(!freshTrack(in.tracks[Steering],now)||!validSteering(in,now)) {
      baselineValid_=false; out.reason=Reason::SteeringInvalid; return out;
    }
    if(!baselineValid_) {
      baselineValid_=true; baseline_=in.wheelAngleDeci; since_=now;
      out.baselineWheelDeci=baseline_; out.wheelDeltaDeci=0;
      out.reason=Reason::WaitWheel; return out;
    }
    out.baselineWheelDeci=baseline_;
    out.wheelDeltaDeci=in.wheelAngleDeci-baseline_;
    const int magnitude=out.wheelDeltaDeci<0?-out.wheelDeltaDeci:out.wheelDeltaDeci;
    if(magnitude<10*int(c.obstacleDeg)) {out.reason=Reason::WaitWheel; return out;}
    used_=true; out.ready=true; out.reason=Reason::CandidateReady;
    out.candidate=candidate_; out.source=CandidateSource::Radar;
    out.rule=in.gear==4?"D_RADAR_RELATIVE_TO_R":"R_RADAR_RELATIVE_TO_D";
    out.stableForMs=now-since_;
    return out;
  }
 private:
  uint32_t epoch_=0,since_=0,priorityEpoch_=UINT32_MAX;
  int gear_=-1,baseline_=0;
  Candidate candidate_=Candidate::None;
  bool baselineValid_=false,used_=false;
};

inline bool validSteering(const Inputs &in,uint32_t now) {
  const auto &t=in.tracks[Steering];const auto &f=t.frame;
  return t.seen&&t.valid&&now-f.observedMs<kFreshMs&&((f.data[3]>>6)&3)==1&&((f.data[1]>>6)&3)==0;
}
inline Gate gate(const Inputs &in,uint32_t now,const Config &config) {
  for(uint8_t s=0;s<SignalCount;++s) {
    if(!required(s,in.gear,config)) continue;
    const auto &t=in.tracks[s];
    if(!t.seen) return {false,Reason::Missing,s};
    if(!t.valid) return {false,t.invalidReason,s};
    if(now-t.frame.observedMs>=kFreshMs) return {false,Reason::Stale,s};
  }
  if(in.gear!=1&&in.gear!=2&&in.gear!=4) return {false,Reason::GearInvalid,Gear};
  if(in.driverBrake==0||in.driverBrake==3) return {false,Reason::BrakeInvalid,Brake};
  if(in.driverBrake!=2||in.brakeApply!=1) return {false,Reason::BrakeReleased,Brake};
  if(in.accelRaw==255) return {false,Reason::AcceleratorInvalid,Gear};
  if(in.accelRaw!=0) return {false,Reason::AcceleratorPressed,Gear};
  const auto &speed=in.tracks[Speed];
  if(speedRaw(speed.frame.data)==4095) return {false,Reason::SpeedInvalid,Speed};
  const int absSpeed=in.speedCentiKph<0?-in.speedCentiKph:in.speedCentiKph;
  if(absSpeed>int(config.maxSpeedKph)*100) return {false,Reason::Moving,Speed};
  if(config.maxSpeedKph==0&&(!speed.zeroWindow||speed.zeroSamples<2||in.zeroForMs<kZeroDwellMs))
    return {false,Reason::ZeroDwell,Speed};
  if(config.requireSteering&&in.gear!=1&&!validSteering(in,now))
    return {false,Reason::SteeringInvalid,Steering};
  if(in.leftFront!=2||in.leftRear!=2) return {false,Reason::DoorNotClosed,LeftDoors};
  if(in.rightFront!=2||in.rightRear!=2||in.trunk!=2) return {false,Reason::DoorNotClosed,RightDoors};
  if(config.requireSeatbelt&&(in.buckle==0||in.buckle==3)) return {false,Reason::BuckleInvalid,Buckle};
  if(config.requireSeatbelt&&in.buckle!=2) return {false,Reason::BuckleOff,Buckle};
  if(required(Front,in.gear,config)&&!in.front.valid) return {false,in.front.reason,Front};
  if(required(Rear,in.gear,config)&&!in.rear.valid) return {false,in.rear.reason,Rear};
  return {true,Reason::CandidateReady,-1};
}
inline Proposal propose(const Inputs &in,const Config &config) {
  const auto &f=in.front; const auto &b=in.rear;
  if(in.gear==4) {
    if(objectWithinThreshold(f,config.obstacleThresholdCm))
      return {Candidate::Reverse,Reason::CandidateReady,"D_FRONT_OBJECT_TO_R"};
    if(objectDetected(f)) return {Candidate::None,Reason::ObstacleBeyondThreshold,"D_FRONT_BEYOND_THRESHOLD"};
    return {Candidate::None,Reason::NoObject,"D_NO_FRONT_OBJECT"};
  }
  if(in.gear==2) {
    if(objectWithinThreshold(b,config.obstacleThresholdCm))
      return {Candidate::Forward,Reason::CandidateReady,"R_REAR_OBJECT_TO_D"};
    if(objectDetected(b)) return {Candidate::None,Reason::ObstacleBeyondThreshold,"R_REAR_BEYOND_THRESHOLD"};
    return {Candidate::None,Reason::NoObject,"R_NO_REAR_OBJECT"};
  }
  const bool fo=objectWithinThreshold(f,config.obstacleThresholdCm),
             bo=objectWithinThreshold(b,config.obstacleThresholdCm);
  // Both ends are valid and neither contains a threshold-sized obstacle. This
  // includes NO_OBJECT and measured-but-far echoes. Keep the same forward bias
  // as the original parking rule: offer D when both travel directions are open.
  if(!fo&&!bo) {
    if(config.parkSteeringFallback)
      return {Candidate::None,Reason::NoObject,"P_WAIT_STEERING_CHOICE"};
    return {Candidate::Forward,Reason::CandidateReady,"P_BOTH_CLEAR_TO_D"};
  }
  if(f.near&&b.near) return {Candidate::None,Reason::EqualDistance,"P_BOTH_NEAR"};
  if(f.near||(!b.near&&fo&&(!bo||f.minCm<b.minCm)))
    return {Candidate::Reverse,Reason::CandidateReady,"P_FRONT_CLOSER_TO_R"};
  if(b.near||(bo&&(!fo||b.minCm<f.minCm)))
    return {Candidate::Forward,Reason::CandidateReady,"P_REAR_CLOSER_TO_D"};
  return {Candidate::None,Reason::EqualDistance,"P_EQUAL_DISTANCE"};
}

// Steering fallback is a driver-command path only when both ends are valid and
// neither has an echo inside the obstacle threshold. Unavailable/blocked SDI is
// not treated as "clear"; it fails closed. D/R use an absolute counter-steer
// angle from the brake-valid baseline; direction selection is still the gear's
// opposite direction. P has no prior travel direction, so it is not inferred.
inline Proposal applySteeringFallback(const Proposal &radar,const Inputs &in,
                                      const Window &w,const Config &config) {
  if(!config.steeringFallback||radar.candidate!=Candidate::None) return radar;
  if(in.gear!=2&&in.gear!=4) return radar;
  if(!in.front.valid||!in.rear.valid) return radar;
  if(objectWithinThreshold(in.front,config.obstacleThresholdCm)||
     objectWithinThreshold(in.rear,config.obstacleThresholdCm)) return radar;
  if(!w.baselineValid) return {Candidate::None,Reason::WaitWheel,"STEERING_FALLBACK_WAIT_BASELINE"};
  const int delta=in.wheelAngleDeci-w.baselineWheel;
  const int requiredDeci=10*int(config.drConfirmDeg>config.obstacleDeg?
      config.drConfirmDeg:config.obstacleDeg);
  const int magnitude=delta<0?-delta:delta;
  if(magnitude<requiredDeci) return {Candidate::None,Reason::WaitWheel,"STEERING_FALLBACK_WAIT_ANGLE"};
  return in.gear==2 ?
      Proposal{Candidate::Forward,Reason::CandidateReady,"R_COUNTERSTEER_TO_D"} :
      Proposal{Candidate::Reverse,Reason::CandidateReady,"D_COUNTERSTEER_TO_R"};
}
struct Observer {
  Track tracks[3][SignalCount];
  Window windows[3];
  uint32_t sequence=0;
  bool decisionSpeedCut=false;
  void setDecisionSpeedCut(bool cut) {
    if(cut&&!decisionSpeedCut) for(auto &w:windows) w={};
    decisionSpeedCut=cut;
  }
  void reset() {
    memset(static_cast<void *>(tracks),0,sizeof(tracks));
    for(auto &w:windows) w={}; sequence=0;decisionSpeedCut=false;
  }
  Inputs inputs(uint8_t aux,uint32_t now,bool decodeScans=true) const {
    Inputs in;
    if(aux>2) return in;
    for(uint8_t s=0;s<SignalCount;++s) {
      const uint8_t bus=s<=Rear?1:(s==Speed||s==Steering?aux:0);
      in.tracks[s]=tracks[bus][s];
    }
    const auto &g=in.tracks[Gear].frame; const auto &b=in.tracks[Brake].frame;
    in.gear=g.data[2]>>5; in.accelRaw=g.data[4];
    in.driverBrake=(b.data[3]>>5)&3; in.brakeApply=b.data[3]>>7;
    in.speedCentiKph=int(speedRaw(in.tracks[Speed].frame.data))*8-4000;
    in.wheelAngleDeci=wheelDeciDeg(in.tracks[Steering].frame.data);
    const auto &sw=in.tracks[Buckle].frame;
    in.buckle=sw.data[6]&3; in.occupancy=(sw.data[6]>>2)&3;
    const auto &l=in.tracks[LeftDoors].frame; const auto &r=in.tracks[RightDoors].frame;
    in.leftFront=l.data[0]&15; in.leftRear=l.data[0]>>4;
    in.rightFront=r.data[0]&15; in.rightRear=r.data[0]>>4; in.trunk=r.data[7]&15;
    if(in.tracks[Speed].zeroWindow) in.zeroForMs=now-in.tracks[Speed].zeroSince;
    if(!decodeScans) return in;
    in.front=scan(in.tracks[Front].frame); in.rear=scan(in.tracks[Rear].frame);
    if(!in.tracks[Front].seen||!in.tracks[Front].valid||now-in.tracks[Front].frame.observedMs>=kFreshMs) in.front.valid=false;
    if(!in.tracks[Rear].seen||!in.tracks[Rear].valid||now-in.tracks[Rear].frame.observedMs>=kFreshMs) in.rear.valid=false;
    return in;
  }
  void updateWindows(uint32_t now) {
    if(decisionSpeedCut) return;
    for(uint8_t aux=0;aux<3;++aux) {
      const Inputs in=inputs(aux,now); auto &w=windows[aux];
      Config baseConfig; baseConfig.requireSeatbelt=false;
      if(!gate(in,now,baseConfig).ready) {w={};continue;}
      if(!w.active||w.gear!=in.gear) {
        w={}; w.active=true; w.gear=in.gear;
      }
      if(validSteering(in,now)) {
        if(!w.baselineValid) {w.baselineValid=true;w.baselineWheel=in.wheelAngleDeci;}
      } else w.baselineValid=false;
      const uint32_t fg=in.tracks[Front].generation,rg=in.tracks[Rear].generation;
      if((required(Front,in.gear,baseConfig)&&fg==w.frontGeneration)||(required(Rear,in.gear,baseConfig)&&rg==w.rearGeneration)) continue;
      w.frontGeneration=fg; w.rearGeneration=rg;
      const Proposal p=propose(in,baseConfig);
      if(p.candidate!=Candidate::None&&p.candidate!=w.lastDirection) {
        if(w.lastDirection!=Candidate::None) {w.directionChanged=true;w.directionChangedMs=now;}
        w.lastDirection=p.candidate;
      }
      if(!w.proposalSeen||p.candidate!=w.proposal.candidate||strcmp(p.rule,w.proposal.rule)!=0) {
        w.proposalSeen=true; w.proposal=p; w.stableSince=now; w.pairs=1;
      } else if(w.pairs<UINT32_MAX) ++w.pairs;
    }
  }
  void observe(uint8_t bus,uint32_t id,uint8_t dlc,bool extended,bool remote,const uint8_t *data,uint32_t now) {
    const int s=signalIndex(id);
    if(bus>2||s<0||extended||remote||dlc>8||(dlc&&!data)||(s<=Rear&&bus!=1)) return;
    if(s==Buckle&&dlc&&((data[0]&3)!=0)) return; // MUX1 never refreshes MUX0.
    Track &t=tracks[bus][s];
    gearhintv12::Frame f;
    f.bus=bus; f.idIndex=gearhintv12::idIndex(id); f.dlc=dlc; f.observedMs=now; f.sequence=++sequence;
    if(dlc) memcpy(f.data,data,dlc);
    Reason invalid=Reason::CandidateReady;
    if(dlc!=8) invalid=Reason::Length;
    const int cp=checksumPosition(s);
    if(dlc==8&&cp>=0&&data[cp]!=checksum(id,data,cp)) invalid=Reason::Checksum;
    const int counter=dlc==8?counterValue(s,data):-1;
    if(invalid==Reason::CandidateReady&&counter>=0&&t.counterSeen&&counter==t.counter) {
      if(memcmp(t.frame.data,data,8)==0&&t.valid) {updateWindows(now);return;}
      invalid=Reason::CounterConflict;
    }
    if(invalid!=Reason::CandidateReady) {
      t.frame=f;t.seen=true;t.valid=false;t.zeroWindow=false;t.zeroSamples=0;t.invalidReason=invalid;
      updateWindows(now);return;
    }
    const bool previousFresh=t.valid&&now-t.frame.observedMs<kFreshMs;
    if(s==Speed) {
      if(speedRaw(data)==500) {
        if(!previousFresh||!t.zeroWindow) {t.zeroSince=now;t.zeroSamples=0;}
        t.zeroWindow=true; if(t.zeroSamples<UINT32_MAX) ++t.zeroSamples;
      } else {t.zeroWindow=false;t.zeroSamples=0;}
    }
    t.frame=f;t.seen=true;t.valid=true;t.invalidReason=Reason::CandidateReady;++t.generation;
    if(counter>=0) {t.counterSeen=true;t.counter=counter;}
    updateWindows(now);
  }
  Result result(uint8_t aux,uint32_t now,bool receiverAvailable,const Config &config=Config{}) const {
    Result out;
    if(config.maxSpeedKph>8||config.cooldownMs>10000||config.pConfirmDeg<1||config.pConfirmDeg>720||
        config.drConfirmDeg<1||config.drConfirmDeg>720||config.obstacleDeg<1||config.obstacleDeg>720||
        config.obstacleThresholdCm<1||config.obstacleThresholdCm>499||config.hardCutSpeedKph<1||
        config.hardCutSpeedKph>30||config.hardCutSpeedKph<config.maxSpeedKph) {
      out.reason=Reason::ConfigInvalid;return out;
    }
    if(aux>2||!receiverAvailable) {out.reason=Reason::ReceiverUnavailable;return out;}
    const Inputs speedOnly=inputs(aux,now,false);
    if(hardSpeedCut(speedOnly,now,config.hardCutSpeedKph)) {out.reason=Reason::HardSpeedCut;return out;}
    const Inputs in=inputs(aux,now);const Gate g=gate(in,now,config);
    if(!g.ready) {out.reason=g.reason;out.blockedSignal=g.signal;return out;}
    const auto &w=windows[aux];
    out.pairs=w.pairs;
    Proposal radar=propose(in,config);
    Proposal current=radar;
    if(current.candidate==Candidate::None)
      current=applySteeringFallback(current,in,w,config);
    out.rule=current.rule;
    out.wheelDeltaDeci=in.wheelAngleDeci-w.baselineWheel;
    if(current.candidate==Candidate::None) {out.reason=current.reason;return out;}
    // The observer's rolling stability window is updated when frames arrive and
    // therefore uses the default threshold. A read-only query may evaluate a
    // wider threshold later; permit that promotion after the same two-sample,
    // 200ms stability window rather than waiting forever for another frame.
    const bool promotedByThreshold=w.proposal.candidate==Candidate::None&&current.candidate!=Candidate::None;
    if(!w.active||!w.proposalSeen||w.pairs<2||
       (!promotedByThreshold&&w.proposal.candidate!=current.candidate)) {
      out.reason=Reason::WaitPair;return out;
    }
    out.stableForMs=now-w.stableSince;
    if(out.stableForMs<kStableMs) {out.reason=Reason::WaitStable;return out;}
    if(w.directionChanged&&now-w.directionChangedMs<config.cooldownMs) {
      out.cooldownRemainingMs=config.cooldownMs-(now-w.directionChangedMs);out.reason=Reason::Cooldown;return out;
    }
    if(config.requireSteering&&in.gear!=1&&radar.candidate!=Candidate::None) {
      out.wheelDeltaDeci=in.wheelAngleDeci-w.baselineWheel;
      out.confirmationDeci=10*int(config.obstacleDeg);
      const int delta=out.wheelDeltaDeci<0?-out.wheelDeltaDeci:out.wheelDeltaDeci;
      if(!w.baselineValid||delta<out.confirmationDeci) {out.reason=Reason::WaitWheel;return out;}
    }
    out.candidate=current.candidate;out.reason=Reason::CandidateReady;
    uint32_t oldest=0;
    for(uint8_t s=0;s<SignalCount;++s) if(required(s,in.gear,config)) {
      const uint32_t age=now-in.tracks[s].frame.observedMs;if(age>oldest)oldest=age;
    }
    out.remainingMs=kFreshMs-oldest;return out;
  }
};
} // namespace gearhintv12live
