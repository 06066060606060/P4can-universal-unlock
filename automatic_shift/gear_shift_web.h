#pragma once

#include "../json_writer_arduino.h"

static String gearShiftHex(const uint8_t *data,uint8_t dlc){String result;char value[4];for(uint8_t i=0;i<dlc&&i<8;i++){snprintf(value,sizeof(value),"%02X",data[i]);if(i)result+=' ';result+=value;}return result;}
static bool gearShiftBoolArg(const char *name, bool &out) {
  const String value = server.arg(name);
  if (value == "1" || strcasecmp(value.c_str(), "true") == 0) { out = true; return true; }
  if (value == "0" || strcasecmp(value.c_str(), "false") == 0) { out = false; return true; }
  return false;
}
static bool gearShiftU32Arg(const char *name, uint32_t lo, uint32_t hi, uint32_t &out) {
  const String value = server.arg(name);
  if (!value.length() || value.length() > 10) return false;
  // HTML form encoders commonly send checkboxes as true/false. Accept that
  // spelling for boolean-valued 0/1 fields while retaining numeric validation.
  if (lo == 0 && hi == 1) {
    if (strcasecmp(value.c_str(), "true") == 0) { out = 1; return true; }
    if (strcasecmp(value.c_str(), "false") == 0) { out = 0; return true; }
  }
  uint32_t parsed = 0;
  for (char c : value) {
    if (c < '0' || c > '9') return false;
    if (parsed > (UINT32_MAX - (c - '0')) / 10) return false;
    parsed = parsed * 10 + (c - '0');
  }
  if (parsed < lo || parsed > hi) return false;
  out = parsed; return true;
}
static String gearShiftStatusToJson() {
  gearshift::Config cfg;
  gearshift::EngineState engine;
  gearshift::TemplateObserver templates;
  gearshift::SafetyInputs safety;
  gearshift::Decision decision;
  gearhintv12live::PrearmResult prearm;
  gearshift::Deny deny;
  int32_t txResult;
  uint32_t now, txMs, serviceCount;
  bool readOk, writeOk;
  portENTER_CRITICAL(&gearHintDisplayMux);
  portENTER_CRITICAL(&gearShiftMux);
  cfg=gearShiftConfig; engine=gearShiftEngine.state;
  templates=gearShiftTemplateObserver; safety=gearShiftLastSafety;
  decision=gearShiftLastDecision; prearm=gearShiftPrearmSnapshot(static_cast<uint32_t>(millis())); deny=gearShiftLastDeny;
  txResult=gearShiftLastTxResult; txMs=gearShiftLastTxMs;
  serviceCount=gearShiftServiceCount; readOk=gearShiftConfigReadOk;
  writeOk=gearShiftConfigWriteOk;
  now=static_cast<uint32_t>(millis());
  portEXIT_CRITICAL(&gearShiftMux);
  portEXIT_CRITICAL(&gearHintDisplayMux);

  const bool profileSupported=!vehicleProfileSetupMode && !vehicleProfileNvsError &&
      activeCanAIsBody() && activeCanBIsChassis();
  String out; out.reserve(2600); JsonWriterArduino j(out);
  j.boolean("ok",true); j.string("schema","p4can.gear-shift.control.v1");
  j.boolean("executionEnabled",cfg.enabled); j.boolean("displayOnly",!cfg.enabled);
  j.boolean("controlPermission",cfg.enabled && profileSupported);
  j.boolean("profileSupported",profileSupported); j.boolean("brakeRequired",true);
  j.string("brakeRule", (activeVehicleProfile==VEHICLE_MODEL_Y_JUNIPER)
      ? "MODEL_Y_JUNIPER_DRIVER_STATE_2" : "DRIVER_STATE_2_AND_APPLY_1");
  j.boolean("protocolVerified",false); j.boolean("vehicleBehaviorVerified",false);
  j.string("protocol",gearshift::protocolName(cfg.protocol));
  j.string("source",decision.valid?decision.source:""); j.string("target",gearshift::targetName(decision.target));
  j.string("reason",gearshift::denyName(deny)); j.string("state",gearshift::executionStateName(engine.state));
  j.u32("nowMs",now); j.u32("serviceCount",serviceCount);
  j.boolean("configReadOk",readOk); j.boolean("configWriteOk",writeOk);
  j.i32("lastTxResult",txResult); j.u32("lastTxMs",txMs);
  if(txMs) j.u32("lastTxAgeMs",now-txMs); else j.raw("lastTxAgeMs","null");
  j.beginObject("config");
  j.boolean("requireSeatbelt",cfg.requireSeatbelt); j.boolean("requireSteering",cfg.requireSteering); j.boolean("steeringFallback",cfg.steeringFallback); j.boolean("parkSteeringFallback",cfg.parkSteeringFallback);
  j.u32("maxSpeedKph",cfg.maxSpeedKph); j.u32("hardCutSpeedKph",cfg.hardCutSpeedKph); j.u32("speedBus",cfg.speedBus);
  j.u32("cooldownMs",cfg.cooldownMs); j.u32("parkConfirmDeg",cfg.parkConfirmDeg);
  j.u32("driveReverseConfirmDeg",cfg.driveReverseConfirmDeg); j.u32("obstacleConfirmDeg",cfg.obstacleConfirmDeg);
  j.u32("obstacleThresholdCm",cfg.obstacleThresholdCm);
  j.endObject();
  j.beginObject("prearm");
  j.boolean("ready",prearm.ready); j.boolean("speedCut",prearm.speedCut);
  j.string("candidate",gearhintv12live::candidateName(prearm.candidate));
  j.string("source",gearhintv12live::sourceName(prearm.source));
  j.boolean("sameGearIgnored",prearm.sameGearIgnored);j.boolean("radarAvailable",prearm.radarAvailable);
  j.boolean("radarSteeringRequired",prearm.radarSteeringRequired);j.boolean("radarPriority",prearm.radarPriority);
  j.string("reason",gearhintv12live::reasonName(prearm.reason));
  j.string("rule",prearm.rule); j.u32("stableForMs",prearm.stableForMs);
  j.i32("baselineWheelDeciDeg",prearm.baselineWheelDeci);
  j.i32("wheelDeltaDeciDeg",prearm.wheelDeltaDeci); j.u32("brakeEpoch",prearm.brakeEpoch);
  j.u32("remainingMs",prearm.remainingMs); j.i32("wheelAngleDeciDeg",prearm.wheelAngleDeci); j.endObject();
  j.beginObject("templates");
  j.beginObject("v12"); j.boolean("seen",templates.v12.seen); j.u32("count",templates.v12.count);
  j.boolean("ready",gearshift::templateReady(templates.v12,now));
  if(templates.v12.seen) j.u32("ageMs",now-templates.v12.observedMs); else j.raw("ageMs","null");
  j.string("data",templates.v12.seen?gearShiftHex(templates.v12.data,templates.v12.dlc):String("")); j.endObject();
  j.beginObject("v13V14"); j.boolean("seen",templates.v13V14.seen); j.u32("count",templates.v13V14.count);
  j.boolean("ready",gearshift::templateReady(templates.v13V14,now));
  if(templates.v13V14.seen) j.u32("ageMs",now-templates.v13V14.observedMs); else j.raw("ageMs","null");
  j.string("data",templates.v13V14.seen?gearShiftHex(templates.v13V14.data,templates.v13V14.dlc):String("")); j.endObject();
  j.endObject();
  j.beginObject("safety");
  j.i32("gearRaw",safety.gear); j.i32("driverBrakeRaw",safety.driverBrake);
  j.i32("brakeApplyRaw",safety.brakeApply); j.i32("acceleratorRaw",safety.accelerator);
  j.i32("speedCentiKph",safety.speedCentiKph); j.boolean("speedValid",safety.speedValid);
  j.u32("brakeEpoch",safety.brakeEpoch); j.boolean("brakeEpochValid",safety.brakeEpochValid);
  j.boolean("brakeEdge",safety.brakeEdge);
  j.i32("buckleRaw",safety.buckle); j.i32("leftFront",safety.leftFront);
  j.i32("leftRear",safety.leftRear); j.i32("rightFront",safety.rightFront);
  j.i32("rightRear",safety.rightRear); j.i32("trunk",safety.trunk); j.endObject();
  j.beginObject("engine");
  j.u32("sends",engine.sends); j.u32("confirmations",engine.confirmations);
  j.u32("failures",engine.failures); j.u32("fromGear",engine.fromGear);
  j.string("target",gearshift::targetName(static_cast<gearshift::Target>(engine.target)));
  if(engine.sentMs) j.u32("sentAgeMs",now-engine.sentMs); else j.raw("sentAgeMs","null");
  j.u32("lastCanId",engine.lastCanId); j.u32("lastDlc",engine.lastDlc);
  j.string("lastData",gearShiftHex(engine.lastData,engine.lastDlc)); j.endObject();
  j.finish(); return out;
}
static void httpGearShiftStatus() {
  server.sendHeader("Cache-Control","no-store");
  server.send(200,"application/json",gearShiftStatusToJson());
}
static void httpGearShiftConfig() {
  gearshift::Config next=gearShiftConfigSnapshot();
  bool changed=false;
  if(server.hasArg("enabled")) {
    bool value; if(!gearShiftBoolArg("enabled",value)) {
      server.send(400,"application/json","{\"ok\":false,\"error\":\"invalid enabled\"}");return;
    } next.enabled=value; changed=true;
  }
  if(server.hasArg("protocol")) {
    String value=server.arg("protocol"); value.toUpperCase();
    if(value=="AUTO"||value=="0") next.protocol=gearshift::Protocol::Auto;
    else if(value=="V12"||value=="1") next.protocol=gearshift::Protocol::V12;
    else if(value=="V13V14"||value=="2") next.protocol=gearshift::Protocol::V13V14;
    else {server.send(400,"application/json","{\"ok\":false,\"error\":\"invalid protocol\"}");return;}
    changed=true;
  }
  struct Numeric { const char *name; uint32_t lo,hi; uint32_t *value; };
  uint32_t speed=next.speedBus,belt=next.requireSeatbelt?1:0,steer=next.requireSteering?1:0,steerFallback=next.steeringFallback?1:0,parkSteer=next.parkSteeringFallback?1:0;
  uint32_t maxKph=next.maxSpeedKph,hardCut=next.hardCutSpeedKph,cooldown=next.cooldownMs,pDeg=next.parkConfirmDeg,
      drDeg=next.driveReverseConfirmDeg,obstacle=next.obstacleConfirmDeg,obstacleCm=next.obstacleThresholdCm;
  Numeric fields[]={{"speedBus",0,2,&speed},{"requireSeatbelt",0,1,&belt},
      {"requireSteering",0,1,&steer},{"steeringFallback",0,1,&steerFallback},{"parkSteeringFallback",0,1,&parkSteer},{"maxKph",0,8,&maxKph},{"hardCutKph",1,30,&hardCut},{"cooldownMs",0,10000,&cooldown},
      {"pDeg",1,720,&pDeg},{"drDeg",1,720,&drDeg},{"obstacleDeg",1,720,&obstacle},
      {"obstacleCm",1,499,&obstacleCm}};
  for(auto &field:fields) if(server.hasArg(field.name)) {
    if(!gearShiftU32Arg(field.name,field.lo,field.hi,*field.value)) {
      server.send(400,"application/json",String("{\"ok\":false,\"error\":\"invalid ")+field.name+"\"}");return;
    } changed=true;
  }
  if(!changed) {server.send(400,"application/json","{\"ok\":false,\"error\":\"missing settings\"}");return;}
  next.speedBus=static_cast<uint8_t>(speed); next.requireSeatbelt=belt!=0;
  next.requireSteering=steer!=0; next.steeringFallback=steerFallback!=0; next.parkSteeringFallback=parkSteer!=0;
  next.maxSpeedKph=static_cast<uint8_t>(maxKph); next.hardCutSpeedKph=static_cast<uint8_t>(hardCut);
  next.cooldownMs=static_cast<uint16_t>(cooldown); next.parkConfirmDeg=static_cast<uint16_t>(pDeg);
  next.driveReverseConfirmDeg=static_cast<uint16_t>(drDeg); next.obstacleConfirmDeg=static_cast<uint16_t>(obstacle);
  next.obstacleThresholdCm=static_cast<uint16_t>(obstacleCm);
  if(!gearshift::configValid(next)) {server.send(400,"application/json","{\"ok\":false,\"error\":\"invalid configuration\"}");return;}
  const bool profileSupported=!vehicleProfileSetupMode && !vehicleProfileNvsError &&
      activeCanAIsBody() && activeCanBIsChassis();
  if(next.enabled && !profileSupported) {server.send(409,"application/json","{\"ok\":false,\"error\":\"gear shift unavailable for current profile\"}");return;}
  if(!gearShiftConfigSave(next)) {server.send(500,"application/json","{\"ok\":false,\"error\":\"Settings could not be saved\"}");return;}
  server.sendHeader("Cache-Control","no-store");
  server.send(200,"application/json",gearShiftStatusToJson());
}
