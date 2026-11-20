#pragma once
static void httpLightingStats(){
  portENTER_CRITICAL(&lightingSettingsMux);
  const bool permission=lightingPermission,running=lightingState.run.running;
  const uint8_t brakeMode=lightingBrakeMode;
  const uint32_t ok=lightingTxOk,fail=lightingTxFail;
  portEXIT_CRITICAL(&lightingSettingsMux);
  String json;JsonWriterArduino jw(json);jw.boolean("ok",true);jw.boolean("apForcedHighBeam",permission);
  jw.u32("dynamicBrakeMode",brakeMode);jw.boolean("running",running);jw.boolean("apActive",lightingApSnapshot(millis()));
  jw.boolean("stalkSupported",activeTurnSignalVariant==TURN_SIGNAL_STALK);jw.u32("txOk",ok);jw.u32("txFail",fail);
  jw.finish();server.send(200,"application/json",json);
}
static void httpLightingUpdate(){
  portENTER_CRITICAL(&lightingSettingsMux);bool permission=lightingPermission;uint8_t mode=lightingBrakeMode;portEXIT_CRITICAL(&lightingSettingsMux);
  if(!server.hasArg("apForcedHighBeam")&&!server.hasArg("dynamicBrakeMode")){server.send(400,"application/json","{\"error\":\"no-setting\"}");return;}
  if(server.hasArg("apForcedHighBeam")&&!httpBoolArg("apForcedHighBeam",permission)){server.send(400,"application/json","{\"error\":\"invalid-permission\"}");return;}
  if(server.hasArg("dynamicBrakeMode")){
    const String value=server.arg("dynamicBrakeMode");
    if(value!="0"&&value!="1"&&value!="2"){server.send(400,"application/json","{\"error\":\"invalid-brake-mode\"}");return;}
    mode=(uint8_t)value.toInt();
  }
  if(server.hasArg("apForcedHighBeam")&&permission&&activeTurnSignalVariant!=TURN_SIGNAL_STALK){server.send(409,"application/json","{\"error\":\"stalk-required\"}");return;}
  if(!lightingSettingsSave(permission,mode)){server.send(503,"application/json","{\"error\":\"save-failed-or-busy\"}");return;}
  httpLightingStats();
}
