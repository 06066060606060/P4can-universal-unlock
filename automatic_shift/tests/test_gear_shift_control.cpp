#include "../gear_shift_pure.h"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace gearshift;

static void fill678(Template &t, uint32_t now, uint8_t counter=3) {
  uint8_t d[7]={};
  d[1]=counter; for(uint8_t i=2;i<7;++i)d[i]=i;
  d[0]=sum8(d+1,6,0x7E);
  memset(t.data,0,sizeof(t.data)); t.dlc=7; t.observedMs=now; t.count=kTemplateMinCount; t.seen=true;
  memcpy(t.data,d,sizeof(d));
}
static void fill229(Template &t, uint32_t now, uint8_t counter=3) {
  uint8_t d[8]={}; d[1]=counter; d[2]=1;
  d[0]=v12Checksum(0,counter);
  memset(t.data,0,sizeof(t.data)); t.dlc=3; t.observedMs=now; t.count=kTemplateMinCount; t.seen=true;
  memcpy(t.data,d,sizeof(d));
}
static SafetyInputs safe() {
  SafetyInputs s; s.gear=1; s.driverBrake=2; s.brakeApply=1; s.accelerator=0;
  s.speedCentiKph=0; s.speedValid=true; s.leftFront=2; s.leftRear=2;
  s.rightFront=2; s.rightRear=2; s.trunk=2; s.buckle=2; s.brakeEpoch=1; s.brakeEpochValid=true; s.brakeEdge=true; return s;
}
static Config active229() {
  Config c; c.enabled=true; c.protocol=Protocol::V12; return c;
}
int main() {
  unsigned checks=0;
  Template v13; fill678(v13,1000); uint8_t d[8]; memcpy(d,v13.data,8);
  assert(editGear678(d,7,Target::Reverse)); assert(d[1]==0x24); assert(d[0]==sum8(d+1,6,0x7E)); ++checks;
  memcpy(d,v13.data,8); assert(!editGear678(d,7,Target::None)); ++checks;

  Template v12; fill229(v12,1000); memcpy(d,v12.data,8);
  assert(editGear229(d,3,Target::Drive)); assert((d[1]>>4)==4); assert((d[1]&15)==4);
  assert(d[0]==v12Checksum(4,4)); assert((d[2]&3)==0); ++checks;
  d[0]^=1; assert(!validTemplate229(d,3)); ++checks;

  BrakeEpochTracker brake; assert(brake.epoch()==0 && !brake.armed(true)); ++checks;
  brake.update(true); assert(brake.epoch()==0 && !brake.armed(true)); ++checks;
  brake.update(false); assert(brake.releaseSeen() && !brake.armed(false)); ++checks;
  brake.update(true); assert(brake.epoch()==1 && brake.armed(true)); ++checks;
  brake.update(true); assert(brake.epoch()==1 && brake.armed(true)); ++checks;
  brake.update(false); brake.update(true); assert(brake.epoch()==2 && brake.armed(true)); ++checks;

  TemplateObserver obs; uint8_t bad[8]={}; bad[0]=1; bad[1]=3;
  obs.observe(1,0x229,3,false,false,bad,100); assert(!obs.v12.seen); ++checks;
  for(uint32_t i=0;i<kTemplateMinCount;++i) obs.observe(0,0x229,3,false,false,v12.data,1000+i);
  assert(obs.v12.count==kTemplateMinCount && templateReady(obs.v12,1100)); ++checks;

  Config cfg=active229(); assert(gearshift::configValid(cfg)); ++checks;
  assert(cfg.cooldownMs==200&&cfg.parkConfirmDeg==15&&
         cfg.driveReverseConfirmDeg==30&&cfg.obstacleThresholdCm==60); ++checks;
  cfg.obstacleThresholdCm=500; assert(!gearshift::configValid(cfg)); ++checks;
  cfg.obstacleThresholdCm=100; assert(gearshift::configValid(cfg)); ++checks;
  Decision decision{true,Target::Reverse,"TEST"};
  SafetyInputs in=safe(); ExecutionEngine engine; TemplateObserver templates; fill229(templates.v12,1000);
  in.brakeApply=0; auto blocked=engine.service(1000,true,in,cfg,decision,templates);
  assert(!blocked.send && blocked.reason==Deny::BrakeInvalid); ++checks;
  // Model Y Juniper reports driver state 2 with apply=0. Only that runtime
  // profile clears brakeApplyRequired; a stale apply signal still fails closed.
  in.brakeApplyRequired=false;
  auto juniper=engine.service(1001,true,in,cfg,decision,templates);
  assert(juniper.send && juniper.reason==Deny::Ready); ++checks; engine.reset();
  in.brakeApply=-1; blocked=engine.service(1002,true,in,cfg,decision,templates);
  assert(!blocked.send && blocked.reason==Deny::BrakeInvalid); ++checks;
  in=safe(); in.buckle=0; cfg.requireSeatbelt=true;
  blocked=engine.service(1000,true,in,cfg,decision,templates);
  assert(blocked.reason==Deny::BuckleOff); ++checks;
  cfg.requireSeatbelt=false;
  blocked=engine.service(1000,true,in,cfg,decision,templates);
  assert(blocked.send && blocked.reason==Deny::Ready); ++checks; engine.reset(); // disabled belt no longer blocks

  in=safe(); auto sent=engine.service(1000,true,in,cfg,decision,templates);
  assert(sent.send && sent.canId==0x229 && sent.dlc==3 && sent.reason==Deny::Ready); ++checks;
  auto wait=engine.service(1010,true,in,cfg,decision,templates);
  assert(!wait.send && wait.reason==Deny::WaitConfirm); ++checks;
  in.gear=2; auto done=engine.service(1020,true,in,cfg,decision,templates);
  assert(done.reason==Deny::ConfirmedSameGear && engine.state.state==ExecutionState::Confirmed); ++checks;
  auto suppressed=engine.service(1030,true,in,cfg,decision,templates);
  assert(!suppressed.send); ++checks;

  in.gear=4; decision.target=Target::Reverse; ExecutionEngine timeout; TemplateObserver late=templates; fill229(late.v12,1000);
  sent=timeout.service(1000,true,in,cfg,decision,late); assert(sent.send); ++checks;
  auto timedOut=timeout.service(1000+kConfirmTimeoutMs+1,true,in,cfg,decision,late);
  assert(timedOut.reason==Deny::ConfirmTimeout); ++checks;
  auto noRetry=timeout.service(3000,true,in,cfg,decision,late);
  assert(!noRetry.send); ++checks;

  in.gear=4; decision.target=Target::Reverse; ++in.brakeEpoch;
  fill229(late.v12,4002);
  auto rearmed=timeout.service(4002,true,in,cfg,decision,late);
  assert(rearmed.send && rearmed.target==Target::Reverse); ++checks;

  ExecutionEngine chain; in.gear=4; decision.target=Target::Reverse;
  sent=chain.service(1000,true,in,cfg,decision,templates); assert(sent.send); ++checks;
  in.gear=2; done=chain.service(1010,true,in,cfg,decision,templates); assert(done.reason==Deny::ConfirmedSameGear); ++checks;
  decision.target=Target::Drive;
  auto sameBrakeReverse=chain.service(1100,true,in,cfg,decision,templates);
  assert(!sameBrakeReverse.send && sameBrakeReverse.reason==Deny::BrakeActionUsed); ++checks;
  fill229(templates.v12,2511);
  auto noCooldownRearm=chain.service(1010+(cfg.cooldownMs>kRetryCooldownMs?cfg.cooldownMs:kRetryCooldownMs)+1,true,in,cfg,decision,templates);
  assert(!noCooldownRearm.send && noCooldownRearm.reason==Deny::BrakeActionUsed); ++checks;
  ++in.brakeEpoch;
  auto newBrake=chain.service(2512,true,in,cfg,decision,templates);
  assert(newBrake.send && newBrake.target==Target::Drive); ++checks;

  // Returning to P under the same brake press cannot rearm. A release/press
  // edge and cooldown are both required for the next P→R/P→D request.
  in.gear=4; decision.target=Target::Reverse;
  auto driveConfirmed=chain.service(2513,true,in,cfg,decision,templates);
  assert(driveConfirmed.reason==Deny::ConfirmedSameGear); ++checks;
  in.gear=1;
  auto parkSameBrake=chain.service(2514,true,in,cfg,decision,templates);
  assert(!parkSameBrake.send && parkSameBrake.reason==Deny::BrakeActionUsed); ++checks;
  ++in.brakeEpoch; fill229(templates.v12,4014);
  auto parkNewBrake=chain.service(4014,true,in,cfg,decision,templates);
  assert(parkNewBrake.send && parkNewBrake.target==Target::Reverse); ++checks;

  // Toggling execution off/on cannot bypass the consumed brake epoch.
  in.gear=2; done=chain.service(4015,true,in,cfg,decision,templates); assert(done.reason==Deny::ConfirmedSameGear); ++checks;
  decision.target=Target::Drive; cfg.enabled=false; chain.service(4016,true,in,cfg,decision,templates);
  cfg.enabled=true; auto toggleBypass=chain.service(4017,true,in,cfg,decision,templates);
  assert(!toggleBypass.send && toggleBypass.reason==Deny::BrakeActionUsed); ++checks;

  // Invalid telemetry cannot manufacture another release/press edge.
  brake.update(false,false);brake.update(true);assert(!brake.armed(true));++checks;
  brake.update(false);brake.update(true);assert(brake.armed(true));++checks;
  assert(strcmp(denyName(Deny::Ready),"READY")==0);++checks;
  assert(strcmp(denyName(Deny::Disabled),"DISABLED")==0);++checks;
  in=safe();cfg=active229();in.speedCentiKph=801;
  assert(safetyDeny(in,cfg)==Deny::Moving);++checks;
  in.speedCentiKph=1001;
  assert(safetyDeny(in,cfg)==Deny::HardSpeedCut);++checks;
  // Gear changes revoke the candidate; pending confirmation must still finish.
  ExecutionEngine confirmWithoutCandidate;in=safe();fill229(templates.v12,5000);
  assert(confirmWithoutCandidate.service(5000,true,in,cfg,decision,templates).send);++checks;
  in.gear=static_cast<int>(decision.target);
  auto confirmed=confirmWithoutCandidate.service(5010,true,in,cfg,Decision{},templates);
  assert(confirmed.reason==Deny::ConfirmedSameGear&&confirmWithoutCandidate.state.confirmations==1);++checks;
  // Brake-held manual steering may trigger after the press edge. It still
  // consumes the same brake epoch and cannot issue a second request.
  {ExecutionEngine heldAuthorize;TemplateObserver templatesHeld;in=safe();cfg=active229();
    fill229(templatesHeld.v12,6000);in.brakeEdge=false;
    Decision heldDecision{true,Target::Reverse,"DR_STEERING",true};
    auto sent=heldAuthorize.service(6000,true,in,cfg,heldDecision,templatesHeld);
    assert(sent.send&&heldAuthorize.state.brakeEpoch==in.brakeEpoch);++checks;
    auto repeat=heldAuthorize.service(6010,true,in,cfg,heldDecision,templatesHeld);
    assert(!repeat.send&&repeat.reason==Deny::WaitConfirm);++checks;
  }
  // A failed final gate cannot execute later during the same held pedal.
  {ExecutionEngine held;TemplateObserver missing;in=safe();cfg=active229();
    auto denied=held.service(6000,true,in,cfg,decision,missing);
    assert(!denied.send&&denied.reason==Deny::TemplateMissing);++checks;
    fill229(missing.v12,6010);in.brakeEdge=false;
    denied=held.service(6010,true,in,cfg,decision,missing);
    assert(!denied.send&&denied.reason==Deny::BrakeNotArmed);++checks;
    ++in.brakeEpoch;in.brakeEdge=true;
    assert(held.service(6020,true,in,cfg,decision,missing).send);++checks;
  }
  // The normal successful-action cooldown follows the user's 1000ms input.
  {ExecutionEngine smooth;in=safe();cfg=active229();fill229(templates.v12,7000);
    assert(smooth.service(7000,true,in,cfg,decision,templates).send);++checks;
    in.gear=static_cast<int>(decision.target);
    smooth.service(7010,true,in,cfg,{},templates);
    in.gear=1;++in.brakeEpoch;fill229(templates.v12,8000);
    assert(smooth.service(8000,true,in,cfg,decision,templates).send);++checks;
  }
  // All previous persisted record sizes migrate with safe new-field defaults.
  {Config old=active229();old.steeringFallback=true;old.parkSteeringFallback=true;old.hardCutSpeedKph=12;
    uint8_t bytes[22];serializeConfig(old,bytes);Config loaded;
    assert(deserializeConfig(bytes,22,loaded)&&loaded.hardCutSpeedKph==12&&loaded.parkSteeringFallback);++checks;
    assert(loaded.enabled);++checks;
    bytes[0]=1;bytes[18]=bytes[19]=0;
    assert(deserializeConfig(bytes,20,loaded)&&loaded.steeringFallback&&loaded.hardCutSpeedKph==10&&!loaded.parkSteeringFallback);++checks;
    assert(!loaded.enabled);++checks;
    bytes[17]=0;
    assert(deserializeConfig(bytes,18,loaded)&&!loaded.steeringFallback);++checks;
    bytes[15]=0;
    assert(deserializeConfig(bytes,16,loaded)&&loaded.obstacleThresholdCm==60);++checks;
    for(size_t size=0;size<16;++size){assert(!deserializeConfig(bytes,size,loaded));++checks;}
    serializeConfig(old,bytes);bytes[18]=7;assert(!deserializeConfig(bytes,22,loaded));++checks;
    serializeConfig(old,bytes);bytes[19]=2;assert(!deserializeConfig(bytes,22,loaded));++checks;
    serializeConfig(old,bytes);bytes[5]=3;assert(!deserializeConfig(bytes,22,loaded));++checks;
    assert(!deserializeConfig(nullptr,22,loaded));++checks;
    serializeConfig(old,bytes);bytes[0]=1;
    assert(deserializeConfig(bytes,22,loaded)&&!loaded.enabled&&loaded.parkSteeringFallback);++checks;
    serializeConfig(old,bytes);assert(!deserializeConfig(bytes,20,loaded));++checks;
  }
  printf("PASS: %u gear-shift encoder/template/interlock/one-shot checks; one request per brake press, no D/R loop\n",checks);
}
