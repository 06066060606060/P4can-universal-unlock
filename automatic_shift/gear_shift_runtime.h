#pragma once
#include "gear_shift_pure.h"
#include "gear_hint_display_runtime.h"
// Application provides the native three-controller CAN transport.

// Order: TX barrier -> observer mux -> execution mux, also used during recovery.
struct GearShiftBarrierGuard {
 bool held;
 explicit GearShiftBarrierGuard(uint32_t wait=0):held(canTxBarrierMutex&&xSemaphoreTake(canTxBarrierMutex,wait)==pdTRUE){}
 ~GearShiftBarrierGuard(){if(held)xSemaphoreGive(canTxBarrierMutex);}
};
static gearshift::Config gearShiftConfig;
static gearshift::ExecutionEngine gearShiftEngine;
static portMUX_TYPE gearShiftMux = portMUX_INITIALIZER_UNLOCKED;
static bool gearShiftConfigReadOk = true;
static bool gearShiftConfigWriteOk = true;
static int32_t gearShiftLastTxResult = 0;
static uint32_t gearShiftLastTxMs = 0;
static gearshift::Deny gearShiftLastDeny = gearshift::Deny::Disabled;
static gearshift::SafetyInputs gearShiftLastSafety;
static gearshift::Decision gearShiftLastDecision;
static uint32_t gearShiftServiceCount = 0;
static gearshift::BrakeEpochTracker gearShiftBrakeEpochTracker;
static gearhintv12live::PrearmTracker gearShiftPrearmTracker;
static gearhintv12live::BrakeSteeringTracker gearShiftBrakeSteeringTracker;
static gearhintv12live::RadarSteeringTracker gearShiftRadarSteeringTracker;
static gearhintv12live::PrearmResult gearShiftLastPrearm;
static uint32_t gearShiftLastPrearmMs = 0;

static inline void gearShiftSerializeConfig(const gearshift::Config &c, uint8_t out[22]) {
  gearshift::serializeConfig(c, out);
}
static inline bool gearShiftDeserializeConfig(const uint8_t *in, size_t length, gearshift::Config &c) {
  return gearshift::deserializeConfig(in, length, c);
}
static inline void gearShiftConfigLoad() {
  gearshift::Config loaded;
  Preferences prefs;
  const bool opened = prefs.begin("features", true);
  const bool present = opened && prefs.isKey("autoShiftCfg");
  uint8_t bytes[22] = {};
  const size_t length = opened && present ? prefs.getBytesLength("autoShiftCfg") : 0;
  const bool read = present && (length == 16 || length == 18 || length == 20 || length == 22) &&
      prefs.getBytes("autoShiftCfg", bytes, sizeof(bytes)) == length;
  gearShiftConfigReadOk = opened && (!present || (read && gearShiftDeserializeConfig(bytes, length, loaded)));
  prefs.end();
  if (!gearShiftConfigReadOk) loaded.enabled = false;
  portENTER_CRITICAL(&gearShiftMux);
  gearShiftConfig = loaded;
  if (!gearShiftConfigReadOk) gearShiftEngine.reset();
  portEXIT_CRITICAL(&gearShiftMux);
}
static inline bool gearShiftConfigSave(const gearshift::Config &candidate) {
  if (!gearshift::configValid(candidate)) return false;
  GearShiftBarrierGuard barrier(pdMS_TO_TICKS(100));if(!barrier.held)return false;
  uint8_t bytes[22];
  gearShiftSerializeConfig(candidate, bytes);
  uint8_t expected[22];memcpy(expected,bytes,sizeof(bytes));
  Preferences prefs;
  if (!prefs.begin("features", false)) return false;
  const size_t written = prefs.putBytes("autoShiftCfg", bytes, sizeof(bytes));
  const bool ok = written == sizeof(bytes) && prefs.getBytesLength("autoShiftCfg") == sizeof(bytes) &&
      prefs.getBytes("autoShiftCfg", bytes, sizeof(bytes)) == sizeof(bytes) && memcmp(bytes,expected,sizeof(bytes))==0;
  prefs.end();
  gearShiftConfigWriteOk = ok;
  if (!ok) return false;
  gearShiftConfigReadOk = true;
  portENTER_CRITICAL(&gearShiftMux);
  uint8_t previous[22];
  gearShiftSerializeConfig(gearShiftConfig, previous);
  if (memcmp(previous, bytes, sizeof(bytes)) != 0) {
    gearShiftPrearmTracker.reset();
    gearShiftBrakeSteeringTracker.reset();
    gearShiftRadarSteeringTracker.reset();
    gearShiftLastPrearm = {};
  }
  gearShiftConfig = candidate;
  // Do not clear ExecutionEngine here: disable/re-enable must not bypass the
  // one-request-per-brake-press interlock.
  portEXIT_CRITICAL(&gearShiftMux);
  return true;
}
static inline gearshift::Config gearShiftConfigSnapshot() {
  gearshift::Config out;
  portENTER_CRITICAL(&gearShiftMux);
  out = gearShiftConfig;
  portEXIT_CRITICAL(&gearShiftMux);
  return out;
}

static inline gearshift::SafetyInputs gearShiftSafetyFromInputs(
    const gearhintv12live::Inputs &in, uint32_t now,
    bool brakeApplyRequired) {
  gearshift::SafetyInputs out;
  out.gear = in.gear;
  out.driverBrake = in.driverBrake;
  out.brakeApply = in.brakeApply;
  out.accelerator = in.accelRaw;
  out.speedCentiKph = in.speedCentiKph;
  const auto &speed = in.tracks[gearhintv12live::Speed];
  out.speedValid = speed.seen && speed.valid &&
      static_cast<uint32_t>(now - speed.frame.observedMs) < gearhintv12live::kFreshMs &&
      gearhintv12live::speedRaw(speed.frame.data) != 4095;
  out.leftFront = in.leftFront;
  out.leftRear = in.leftRear;
  out.rightFront = in.rightFront;
  out.rightRear = in.rightRear;
  out.trunk = in.trunk;
  out.buckle = in.buckle;
  out.brakeApplyRequired = brakeApplyRequired;
  // Stale cached values must never satisfy final execution authorization.
  if (!gearhintv12live::freshTrack(in.tracks[gearhintv12live::Gear], now))
    out.gear = out.accelerator = -1;
  if (!gearhintv12live::freshTrack(in.tracks[gearhintv12live::Brake], now))
    out.driverBrake = out.brakeApply = -1;
  if (!gearhintv12live::freshTrack(in.tracks[gearhintv12live::LeftDoors], now))
    out.leftFront = out.leftRear = -1;
  if (!gearhintv12live::freshTrack(in.tracks[gearhintv12live::RightDoors], now))
    out.rightFront = out.rightRear = out.trunk = -1;
  if (!gearhintv12live::freshTrack(in.tracks[gearhintv12live::Buckle], now)) out.buckle = -1;
  return out;
}
// Caller holds gearShiftMux. Age the service snapshot rather than renewing a
// candidate's TTL every time an HTTP request reads the cached result.
static inline gearhintv12live::PrearmResult gearShiftPrearmSnapshot(uint32_t now) {
  auto out = gearShiftLastPrearm;
  const uint32_t age = now - gearShiftLastPrearmMs;
  if (out.remainingMs && out.remainingMs <= age) {
    out.ready = false; out.candidate = gearhintv12live::Candidate::None;
    out.remainingMs = 0;
    if (!out.speedCut) out.reason = gearhintv12live::Reason::Stale;
  } else if (out.remainingMs > age) out.remainingMs -= age;
  return out;
}
static inline bool gearShiftProfileAvailable(const gearshift::Config &cfg) {
  if (vehicleProfileSetupMode || vehicleProfileNvsError || canSubsystemBusy ||
      canUsbTxHeld() || canUsbPassive() || canTxAdministrativeHold) return false;
  if (!activeCanAIsBody() || !activeCanBIsChassis() || cfg.speedBus > 2) return false;
  for (uint8_t bus = 0; bus < P4_CAN_COUNT; ++bus) {
    if (!p4CanOnline[bus] || p4CanState[bus] != TWAI_STATE_RUNNING) return false;
  }
  return true;
}
static inline gearshift::Decision gearShiftDecisionSnapshot(
    const gearshift::Config &cfg, const gearhint::DisplayHintObserver &vision,
    gearhintv12live::Observer &live, uint8_t speedBus, uint32_t now,
    bool profileAvailable, gearshift::SafetyInputs &safety,
    gearhintv12live::Inputs &liveInputs,
    gearhintv12live::PrearmResult &prearm) {
  // No radar scan or candidate/steering evaluation above the hard limit.
  auto in=live.inputs(speedBus,now,false);
  liveInputs=in;
  safety=gearShiftSafetyFromInputs(in,now,activeVehicleProfile != VEHICLE_MODEL_Y_JUNIPER);
  const bool speedCut=gearhintv12live::hardSpeedCut(in,now,cfg.hardCutSpeedKph);
  live.setDecisionSpeedCut(speedCut || !safety.speedValid);
  if(speedCut || !profileAvailable || !safety.speedValid) {
    gearShiftPrearmTracker.reset(); prearm={}; prearm.speedCut=speedCut;
    prearm.reason=speedCut?gearhintv12live::Reason::HardSpeedCut:
        !profileAvailable?gearhintv12live::Reason::ReceiverUnavailable:gearhintv12live::Reason::SpeedInvalid;
    return {};
  }
  in=live.inputs(speedBus,now);
  liveInputs=in;
  gearhintv12live::Config liveCfg;
  liveCfg.requireSeatbelt=cfg.requireSeatbelt; liveCfg.requireSteering=cfg.requireSteering;
  liveCfg.steeringFallback=cfg.steeringFallback; liveCfg.parkSteeringFallback=cfg.parkSteeringFallback;
  liveCfg.maxSpeedKph=cfg.maxSpeedKph; liveCfg.hardCutSpeedKph=cfg.hardCutSpeedKph;
  liveCfg.cooldownMs=cfg.cooldownMs; liveCfg.pConfirmDeg=cfg.parkConfirmDeg;
  liveCfg.drConfirmDeg=cfg.driveReverseConfirmDeg; liveCfg.obstacleDeg=cfg.obstacleConfirmDeg;
  liveCfg.obstacleThresholdCm=cfg.obstacleThresholdCm;
  // The 2021 Model Y field observation maps negative relative motion to left.
  // Juniper has not been calibrated, so its P selector remains display-only.
  liveCfg.parkSteeringCalibrated=activeVehicleProfile==VEHICLE_MODEL_Y_LEGACY;
  liveCfg.parkSteeringLeftIsNegative=true;
  gearhint::HintResult pair;
  if(cfg.protocol!=gearshift::Protocol::V12)
    pair=vision.result(now,profileAvailable,gearhint::kPrearmPairHoldMs);
  gearhintv12live::Proposal visionProposal;
  if(pair.hint!=gearhint::DisplayHint::None) {
    visionProposal.candidate=pair.hint==gearhint::DisplayHint::Forward?
        gearhintv12live::Candidate::Forward:gearhintv12live::Candidate::Reverse;
    visionProposal.reason=gearhintv12live::Reason::CandidateReady;
    visionProposal.rule="V13V14_PAIR";
  }
  const bool visionSelected=cfg.protocol==gearshift::Protocol::V13V14 ||
      (cfg.protocol==gearshift::Protocol::Auto&&visionProposal.candidate!=gearhintv12live::Candidate::None&&
       !gearhintv12live::sameGear(visionProposal.candidate,in.gear));
  if(cfg.protocol==gearshift::Protocol::Auto&&visionSelected) {
    auto radar=in.front.valid&&in.rear.valid?gearhintv12live::propose(in,liveCfg):gearhintv12live::Proposal{};
    if(gearhintv12live::sameGear(radar.candidate,in.gear)) radar={};
    if(radar.candidate!=gearhintv12live::Candidate::None&&radar.candidate!=visionProposal.candidate) {
      gearShiftPrearmTracker.reset(); prearm={};
      prearm.reason=gearhintv12live::Reason::ProbeUnknown;return {};
    }
  }
  prearm=gearShiftPrearmTracker.update(in,now,liveCfg,visionSelected?&visionProposal:nullptr);
  if(prearm.source==gearhintv12live::CandidateSource::VehiclePair&&pair.remainingMs<prearm.remainingMs)
    prearm.remainingMs=pair.remainingMs;
  gearshift::Decision decision;
  if(prearm.ready&&!(prearm.radarSteeringRequired&&
      prearm.source==gearhintv12live::CandidateSource::Radar)) {
    decision.valid=true;
    decision.target=prearm.candidate==gearhintv12live::Candidate::Forward?gearshift::Target::Drive:gearshift::Target::Reverse;
    decision.source=gearhintv12live::sourceName(prearm.source);
  }
  return decision;
}

static inline void gearShiftServiceTick() {
  static uint32_t nextServiceMs = 0;
  const uint32_t now = static_cast<uint32_t>(millis());
  if (static_cast<int32_t>(now - nextServiceMs) < 0) return;
  GearShiftBarrierGuard barrier;if(!barrier.held)return;
  nextServiceMs = now + 10; // reduced to 100ms by hard speed cut below

  gearshift::Action action;
  gearshift::Config cfg;
  gearshift::EngineState engineState;
  gearshift::TemplateObserver templates;
  gearshift::SafetyInputs safety;
  gearshift::Decision decision;
  gearhintv12live::Inputs liveInputs;
  bool profileAvailable = false;
  bool txFailed = false;
  CanFrame frame = {};

  // Keep the receive observers stable while the one-shot action is built and
  // submitted. p4CanSendFrame() is non-blocking; this critical section is short.
  portENTER_CRITICAL(&gearHintDisplayMux);
  portENTER_CRITICAL(&gearShiftMux);
  cfg = gearShiftConfig;
  templates = gearShiftTemplateObserver;
  profileAvailable = gearShiftProfileAvailable(cfg);
  gearhintv12live::PrearmResult prearm;
  decision = gearShiftDecisionSnapshot(cfg, gearHintPrearmVisionObserver,
      gearHintV12LiveObserver, cfg.speedBus, now, profileAvailable, safety,
      liveInputs, prearm);
  gearShiftLastPrearmMs = now;
  if(prearm.speedCut) nextServiceMs = now + 100;
  const bool brakePressed = safety.driverBrake == 2;
  safety.brakeEdge = gearShiftBrakeEpochTracker.update(
      brakePressed, safety.driverBrake == 1 || safety.driverBrake == 2);
  safety.brakeEpoch = gearShiftBrakeEpochTracker.epoch();
  safety.brakeEpochValid = gearShiftBrakeEpochTracker.armed(brakePressed);
  // D/R radar steering confirmation is brake-first. A ready radar candidate
  // on the edge locks radar priority; relative wheel motion then executes.
  bool radarPriority=false;
  if(cfg.requireSteering&&liveInputs.gear!=1&&!prearm.speedCut&&profileAvailable) {
    gearhintv12live::Config liveCfg;
    liveCfg.requireSeatbelt=cfg.requireSeatbelt; liveCfg.requireSteering=cfg.requireSteering;
    liveCfg.steeringFallback=cfg.steeringFallback; liveCfg.parkSteeringFallback=cfg.parkSteeringFallback;
    liveCfg.maxSpeedKph=cfg.maxSpeedKph; liveCfg.hardCutSpeedKph=cfg.hardCutSpeedKph;
    liveCfg.cooldownMs=cfg.cooldownMs; liveCfg.pConfirmDeg=cfg.parkConfirmDeg;
    liveCfg.drConfirmDeg=cfg.driveReverseConfirmDeg; liveCfg.obstacleDeg=cfg.obstacleConfirmDeg;
    liveCfg.obstacleThresholdCm=cfg.obstacleThresholdCm;
    auto radar=gearShiftRadarSteeringTracker.update(liveInputs,now,liveCfg,
        safety.brakeEpoch,safety.brakeEdge,safety.brakeEpochValid,
        prearm.ready&&prearm.source==gearhintv12live::CandidateSource::Radar,
        prearm.candidate);
    if(radar.radarPriority) {
      prearm=radar; radarPriority=true;
      if(radar.ready) {
        decision.valid=true;
        decision.target=radar.candidate==gearhintv12live::Candidate::Forward?
            gearshift::Target::Drive:gearshift::Target::Reverse;
        decision.source=gearhintv12live::sourceName(radar.source);
        decision.authorizeDuringBrakeHold=true;
      }
    }
  }
  // Radar/pair keeps its pre-brake candidate priority. Only when it has no
  // executable candidate does brake-held manual steering record a baseline and
  // potentially trigger during the same pedal press.
  if(!decision.valid && !prearm.speedCut && profileAvailable && !radarPriority) {
    const bool manualEnabled=liveInputs.gear==1?cfg.parkSteeringFallback:cfg.steeringFallback;
    if(manualEnabled) {
      gearhintv12live::Config liveCfg;
      liveCfg.requireSeatbelt=cfg.requireSeatbelt; liveCfg.requireSteering=cfg.requireSteering;
      liveCfg.steeringFallback=cfg.steeringFallback; liveCfg.parkSteeringFallback=cfg.parkSteeringFallback;
      liveCfg.parkSteeringCalibrated=activeVehicleProfile==VEHICLE_MODEL_Y_LEGACY;
      liveCfg.parkSteeringLeftIsNegative=true;
      liveCfg.maxSpeedKph=cfg.maxSpeedKph; liveCfg.hardCutSpeedKph=cfg.hardCutSpeedKph;
      liveCfg.cooldownMs=cfg.cooldownMs; liveCfg.pConfirmDeg=cfg.parkConfirmDeg;
      liveCfg.drConfirmDeg=cfg.driveReverseConfirmDeg; liveCfg.obstacleDeg=cfg.obstacleConfirmDeg;
      liveCfg.obstacleThresholdCm=cfg.obstacleThresholdCm;
      auto manual=gearShiftBrakeSteeringTracker.update(liveInputs,now,liveCfg,
          safety.brakeEpoch,safety.brakeEdge,safety.brakeEpochValid);
      prearm=manual;
      if(manual.ready) {
        decision.valid=true;
        decision.target=manual.candidate==gearhintv12live::Candidate::Forward?
            gearshift::Target::Drive:gearshift::Target::Reverse;
        decision.source=gearhintv12live::sourceName(manual.source);
        decision.authorizeDuringBrakeHold=true;
      }
    }
  }
  action = gearShiftEngine.service(now, profileAvailable, safety, cfg,
                                   decision, templates);
  gearShiftLastPrearm = prearm;
  engineState = gearShiftEngine.state;
  gearShiftLastDeny = action.reason;
  if(prearm.speedCut) gearShiftLastDeny = gearshift::Deny::HardSpeedCut;
  gearShiftLastSafety = safety;
  gearShiftLastDecision = decision;
  if (gearShiftServiceCount != UINT32_MAX) ++gearShiftServiceCount;
  portEXIT_CRITICAL(&gearShiftMux);

  if (action.send) {
    frame.bus = P4_BODY;
    frame.can_id = action.canId;
    frame.can_dlc = action.dlc;
    memcpy(frame.data, action.data, sizeof(frame.data));
    const esp_err_t result = p4CanSendFrame(&frame);
    gearShiftLastTxResult = static_cast<int32_t>(result);
    gearShiftLastTxMs = now;
    txFailed = result != ESP_OK;
    if (txFailed) {
      portENTER_CRITICAL(&gearShiftMux);
      gearShiftEngine.state.state = gearshift::ExecutionState::Failed;
      gearShiftEngine.state.resultMs = now;
      gearShiftEngine.state.lastAttemptMs = now;
      if (gearShiftEngine.state.failures != UINT32_MAX) ++gearShiftEngine.state.failures;
      engineState = gearShiftEngine.state;
      gearShiftLastDeny = gearshift::Deny::TxFailed;
      portEXIT_CRITICAL(&gearShiftMux);
    }
  }
  portEXIT_CRITICAL(&gearHintDisplayMux);
}

// Caller owns the TX barrier during a recovery epoch transition.
static void gearShiftInvalidateInputs(){
 for(uint8_t bus=0;bus<3;bus++)gearHintDisplayInvalidateBus(bus);
 portENTER_CRITICAL(&gearShiftMux);gearShiftPrearmTracker.reset();gearShiftBrakeSteeringTracker.reset();gearShiftRadarSteeringTracker.reset();gearShiftLastPrearm={};portEXIT_CRITICAL(&gearShiftMux);
 // Preserve the brake epoch / consumed-action state: recovery cannot create a new press.
}
static void gearShiftTask(void*){for(;;){gearShiftServiceTick();vTaskDelay(pdMS_TO_TICKS(10));}}
