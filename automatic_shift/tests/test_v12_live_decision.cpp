#include "../gear_hint_v12_live_pure.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <initializer_list>
using namespace gearhintv12live;
static unsigned checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
struct Fixture {
  Observer o;
  uint32_t now=0,tick=0;
  int gear=1,brake=0xCF,buckle=2,occupancy=2,accel=0,speed=500,wheel=0,angleValidity=1,angleStatus=0;
  int left=0x22,right=0x22,trunk=2,aux=0,skip=-1;
  uint16_t front[6]={200,500,500,500,500,500},rear[6]={50,500,500,500,500,500};
  void emit(uint8_t bus,uint16_t id,uint8_t *d,uint8_t dlc=8,bool ext=false,bool remote=false) {
    const int s=signalIndex(id),cp=checksumPosition(s);
    if(cp>=0&&dlc==8) d[cp]=checksum(id,d,cp);
    o.observe(bus,id,dlc,ext,remote,d,now);
  }
  void frame(int s) {
    if(s==skip) return;
    uint8_t d[8]={};const uint8_t bus=s<=Rear?1:(s==Speed||s==Steering?aux:0);
    if(s==Gear){const uint8_t bytes[]={0,0x32,0x55,0x72,0x95};d[2]=gear>=0&&gear<=4?bytes[gear]:uint8_t(gear<<5);d[4]=accel;}
    if(s==Brake)d[3]=brake;
    if(s==Speed){d[1]=(speed&15)<<4;d[2]=speed>>4;}
    if(s==Steering){const unsigned raw=wheel+8192;d[2]=raw;d[3]=((raw>>8)&63)|(angleValidity<<6);d[1]=angleStatus<<6;}
    if(s==LeftDoors)d[0]=left;
    if(s==RightDoors){d[0]=right;d[7]=trunk;}
    if(s==Buckle)d[6]=buckle|(occupancy<<2);
    if(s==Front||s==Rear){
      uint64_t word=uint64_t(tick&3)<<54;const auto *v=s==Front?front:rear;
      for(int i=0;i<6;++i)word|=uint64_t(v[i])<<(9*i);
      for(int i=0;i<7;++i)d[i]=word>>(8*i);
    } else if(counterValue(s,d)>=0)d[1]=(d[1]&0xf0)|(tick&15);
    emit(bus,kSignalIds[s],d);
  }
  void step(){for(int s=0;s<SignalCount;++s)frame(s);++tick;now+=40;}
  void run(unsigned count=50){for(unsigned i=0;i<count;++i)step();}
  Result result(bool confirm=false,uint8_t source=0){Config c;c.requireSteering=confirm;return o.result(source,now,true,c);}
};
static PrearmResult prearmReady(Fixture &f,const Config &c,const Proposal *external=nullptr) {
  f.brake=0x2F;
  PrearmTracker pre;
  PrearmResult r;
  const int requestedWheel=f.wheel;
  f.wheel=0;f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c,external);
  f.wheel=requestedWheel;
  for(unsigned i=0;i<4;++i) {f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c,external);}
  return r;
}
static void centerSteering(Fixture &f,PrearmTracker &pre,const Config &c,const Proposal *external=nullptr) {
  const int requestedWheel=f.wheel;
  f.wheel=0;f.step();pre.update(f.o.inputs(0,f.now),f.now,c,external);
  f.wheel=requestedWheel;
}
int main(){
  {Fixture f;CHECK(f.result().reason==Reason::Missing);f.run();CHECK(f.result().candidate==Candidate::Forward);
   CHECK(strcmp(f.result().rule,"P_REAR_CLOSER_TO_D")==0);
   CHECK(f.result(true).candidate==Candidate::Forward);
   CHECK(f.o.result(0,f.now,false).candidate==Candidate::None);
   CHECK(f.result(false,1).candidate==Candidate::None);CHECK(f.result(false,3).candidate==Candidate::None);
   CHECK(f.o.result(0,f.now+300,true).reason==Reason::Stale);}
  {Fixture f;f.front[0]=50;f.rear[0]=200;f.run();CHECK(f.result().candidate==Candidate::Reverse);}
  {Fixture f;f.front[0]=40;f.rear[0]=40;f.run();CHECK(f.result().reason==Reason::EqualDistance);}
  {Fixture f;f.front[0]=499;f.rear[0]=500;f.run();auto r=f.result();
   CHECK(r.candidate==Candidate::Forward);CHECK(strcmp(r.rule,"P_BOTH_CLEAR_TO_D")==0);}
  {Fixture f;f.front[0]=500;f.rear[0]=499;f.run();auto r=f.result();
   CHECK(r.candidate==Candidate::Forward);CHECK(strcmp(r.rule,"P_BOTH_CLEAR_TO_D")==0);}
  {Fixture f;f.front[0]=500;f.rear[0]=500;f.run();CHECK(f.result().candidate==Candidate::Forward);
   const auto in=f.o.inputs(0,f.now);CHECK(in.front.noObjectCount==6&&in.front.minCm==-1);}
  {Fixture f;f.front[0]=400;f.rear[0]=450;f.run();CHECK(f.result().candidate==Candidate::Forward);
   CHECK(strcmp(f.result().rule,"P_BOTH_CLEAR_TO_D")==0);
   Config wide;wide.obstacleThresholdCm=300;auto r=f.o.result(0,f.now,true,wide);
   CHECK(r.candidate==Candidate::Forward);CHECK(strcmp(r.rule,"P_BOTH_CLEAR_TO_D")==0);}
  {Fixture f;f.front[0]=400;f.rear[0]=450;f.run();Config narrow;narrow.obstacleThresholdCm=399;
   auto r=f.o.result(0,f.now,true,narrow);CHECK(r.candidate==Candidate::Forward);CHECK(strcmp(r.rule,"P_BOTH_CLEAR_TO_D")==0);}
  {Fixture f;f.front[0]=1;f.rear[0]=2;f.run();CHECK(f.result().candidate==Candidate::Reverse);}
  {Fixture f;f.front[0]=2;f.rear[0]=1;f.run();CHECK(f.result().candidate==Candidate::Forward);}
  {Fixture f;f.front[0]=1;f.rear[0]=1;f.run();CHECK(f.result().reason==Reason::EqualDistance);}
  {Fixture f;f.gear=4;f.front[0]=499;f.rear[0]=1;f.wheel=0;f.run();CHECK(f.result().reason==Reason::ObstacleBeyondThreshold);}
  {Fixture f;f.gear=4;f.front[0]=500;f.rear[0]=1;f.run();CHECK(f.result().reason==Reason::NoObject);}
  {Fixture f;f.gear=2;f.rear[0]=499;f.front[0]=1;f.run();CHECK(f.result().reason==Reason::ObstacleBeyondThreshold);}
  {Fixture f;f.gear=2;f.rear[0]=500;f.front[0]=1;f.run();CHECK(f.result().reason==Reason::NoObject);}
  {Fixture f;f.gear=4;f.front[0]=400;f.rear[0]=500;f.run();CHECK(f.result().candidate==Candidate::None);
   CHECK(f.result().reason==Reason::ObstacleBeyondThreshold);CHECK(strcmp(f.result().rule,"D_FRONT_BEYOND_THRESHOLD")==0);
   Config wide;wide.obstacleThresholdCm=450;CHECK(f.o.result(0,f.now,true,wide).candidate==Candidate::Reverse);
   Config narrow;narrow.obstacleThresholdCm=399;CHECK(f.o.result(0,f.now,true,narrow).candidate==Candidate::None);}
  {Fixture f;f.gear=2;f.rear[0]=400;f.front[0]=500;f.run();CHECK(f.result().reason==Reason::ObstacleBeyondThreshold);
   Config wide;wide.obstacleThresholdCm=400;CHECK(f.o.result(0,f.now,true,wide).candidate==Candidate::Forward);}
  {Fixture f;f.gear=4;f.front[0]=1;f.rear[0]=500;f.run();CHECK(f.result().candidate==Candidate::Reverse);}
  {Fixture f;f.gear=2;f.rear[0]=1;f.front[0]=500;f.run();CHECK(f.result().candidate==Candidate::Forward);}
  {Fixture f;f.gear=2;f.front[0]=500;f.rear[0]=500;f.run();Config c;c.steeringFallback=true;
   auto r=f.o.result(0,f.now,true,c);CHECK(r.candidate==Candidate::None);CHECK(r.reason==Reason::WaitWheel);
   f.wheel=-250;f.step();r=f.o.result(0,f.now,true,c);CHECK(r.reason==Reason::WaitWheel);
   f.wheel=-350;f.step();r=f.o.result(0,f.now,true,c);
   CHECK(r.candidate==Candidate::Forward);CHECK(strcmp(r.rule,"R_COUNTERSTEER_TO_D")==0);++checks;}
  {Fixture f;f.gear=2;f.front[0]=500;f.rear[0]=400;f.run();Config c;c.steeringFallback=true;c.obstacleThresholdCm=100;
   f.wheel=650;f.step();CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Forward);++checks;}
  {Fixture f;f.gear=4;f.front[0]=400;f.rear[0]=500;f.run();Config c;c.steeringFallback=true;c.obstacleThresholdCm=100;
   f.wheel=-650;f.step();auto r=f.o.result(0,f.now,true,c);CHECK(r.candidate==Candidate::Reverse);
   CHECK(strcmp(r.rule,"D_COUNTERSTEER_TO_R")==0);++checks;}
  {Fixture f;f.gear=2;f.front[0]=500;f.rear[0]=500;f.run();Config c;c.steeringFallback=false;
   f.wheel=650;f.step();CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::None);++checks;}
  // Brake-first manual steering: capture a baseline on the press edge, then
  // trigger on relative motion. A locked steering angle alone never triggers.
  {Fixture f;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;
   c.steeringFallback=c.parkSteeringFallback=true;c.parkSteeringCalibrated=true;c.parkSteeringLeftIsNegative=true;
   BrakeSteeringTracker manual;PrearmResult r;
   f.wheel=0;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true);
   CHECK(!r.ready&&r.reason==Reason::WaitWheel&&r.baselineWheelDeci==0);
   f.brake=0xCF;f.wheel=-350;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(r.ready&&r.candidate==Candidate::Forward&&r.source==CandidateSource::ParkSteering);
   CHECK(r.baselineWheelDeci==0&&r.wheelDeltaDeci==-350);++checks;}
  {Fixture f;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;
   c.steeringFallback=c.parkSteeringFallback=true;c.parkSteeringCalibrated=true;c.parkSteeringLeftIsNegative=true;
   BrakeSteeringTracker manual;f.wheel=0;f.step();
   auto r=manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true);
   f.brake=0xCF;f.wheel=350;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(r.ready&&r.candidate==Candidate::Reverse&&strcmp(r.rule,"P_RIGHT_STEERING_TO_R")==0);++checks;}
  // D/R uses the magnitude relative to the pedal-press baseline. Returning from
  // -120 degrees to -60 degrees is a +60 delta and must trigger immediately.
  {Fixture f;f.gear=4;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;c.steeringFallback=true;
   BrakeSteeringTracker manual;f.wheel=-1200;f.step();
   auto r=manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true);CHECK(!r.ready);
   f.brake=0xCF;f.wheel=-600;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(r.ready&&r.candidate==Candidate::Reverse&&r.baselineWheelDeci==-1200&&r.wheelDeltaDeci==600);
   CHECK(strcmp(r.rule,"D_RELATIVE_STEERING_TO_R")==0);++checks;}
  {Fixture f;f.gear=2;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;c.steeringFallback=true;
   BrakeSteeringTracker manual;f.wheel=1300;f.step();
   auto r=manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true);CHECK(!r.ready);
   f.brake=0xCF;f.wheel=700;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(r.ready&&r.candidate==Candidate::Forward&&r.wheelDeltaDeci==-600);++checks;}
  // One pedal epoch consumes one manual trigger. Holding or reversing the wheel
  // cannot create a second request; a new edge takes a new baseline.
  {Fixture f;f.gear=4;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;c.steeringFallback=true;
   BrakeSteeringTracker manual;f.wheel=0;f.step();manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true);
   f.brake=0xCF;f.wheel=600;f.step();auto r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);CHECK(r.ready);
   f.wheel=-600;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(!r.ready&&r.reason==Reason::BrakeActionUsed);++checks;
   f.brake=0x2F;f.wheel=-600;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(!r.ready&&r.reason==Reason::BrakeReleased);
   f.brake=0xCF;f.wheel=-600;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,2,true,true);
   CHECK(!r.ready&&r.baselineWheelDeci==-600);
   f.brake=0xCF;f.wheel=0;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,2,false,true);CHECK(r.ready);++checks;}
  // The per-source allowed speed gates manual steering before it can even
  // report a ready candidate. Returning under the limit takes a fresh baseline.
  {Fixture f;f.gear=4;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;c.steeringFallback=true;
   BrakeSteeringTracker manual;f.wheel=0;f.step();CHECK(!manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true).ready);
   f.wheel=600;f.speed=601;f.step();auto r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(!r.ready&&r.reason==Reason::Moving);++checks;
   f.speed=500;f.wheel=600;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(!r.ready&&r.reason==Reason::WaitWheel&&r.baselineWheelDeci==600);++checks;
   f.wheel=1200;f.step();r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);CHECK(r.ready);++checks;
  }
  // D/R radar confirmation: prearm the radar candidate while released, then
  // capture the wheel baseline on the press edge and trigger on relative motion.
  {Fixture f;f.gear=4;f.brake=0x2F;f.front[0]=50;f.rear[0]=500;f.wheel=-1200;
   Config c;c.requireSteering=true;c.obstacleDeg=30;
   PrearmTracker pre;PrearmResult ready;
   for(unsigned i=0;i<4;++i){f.step();ready=pre.update(f.o.inputs(0,f.now),f.now,c);}
   CHECK(ready.ready&&ready.source==CandidateSource::Radar&&ready.radarSteeringRequired);
   f.brake=0xCF;f.step();ready=pre.update(f.o.inputs(0,f.now),f.now,c);
   RadarSteeringTracker radar;auto r=radar.update(f.o.inputs(0,f.now),f.now,c,
       1,true,true,ready.ready&&ready.source==CandidateSource::Radar,ready.candidate);
   CHECK(!r.ready&&r.radarPriority&&r.reason==Reason::WaitWheel);++checks;
   r=radar.update(f.o.inputs(0,f.now),f.now,c,1,false,true,
       ready.ready&&ready.source==CandidateSource::Radar,ready.candidate);
   CHECK(!r.ready&&r.baselineWheelDeci==-1200);++checks;
   f.wheel=-900;f.step();ready=pre.update(f.o.inputs(0,f.now),f.now,c);
   r=radar.update(f.o.inputs(0,f.now),f.now,c,1,false,true,
       ready.ready&&ready.source==CandidateSource::Radar,ready.candidate);
   CHECK(r.ready&&r.candidate==Candidate::Reverse&&r.wheelDeltaDeci==300);
   CHECK(strcmp(r.rule,"D_RADAR_RELATIVE_TO_R")==0);++checks;
   r=radar.update(f.o.inputs(0,f.now),f.now,c,1,false,true,
       ready.ready&&ready.source==CandidateSource::Radar,ready.candidate);
   CHECK(!r.ready&&r.reason==Reason::BrakeActionUsed);++checks;
  }
  // If the priority radar candidate disappears during the held pedal, this
  // brake epoch cannot fall back to the independent D/R manual selector.
  {Fixture f;f.gear=4;f.brake=0x2F;f.front[0]=50;f.rear[0]=500;Config c;c.requireSteering=true;
   PrearmTracker pre;PrearmResult ready;
   for(unsigned i=0;i<4;++i){f.step();ready=pre.update(f.o.inputs(0,f.now),f.now,c);}
   f.brake=0xCF;f.step();ready=pre.update(f.o.inputs(0,f.now),f.now,c);
   RadarSteeringTracker radar;radar.update(f.o.inputs(0,f.now),f.now,c,1,true,true,
       ready.ready&&ready.source==CandidateSource::Radar,ready.candidate);
   f.front[0]=500;f.step();ready=pre.update(f.o.inputs(0,f.now),f.now,c);
   auto r=radar.update(f.o.inputs(0,f.now),f.now,c,1,false,true,
       ready.ready&&ready.source==CandidateSource::Radar,ready.candidate);
   CHECK(!r.ready&&r.radarPriority&&r.reason==Reason::RadarCandidateLost);++checks;
  }
  // P radar never requests this D/R-only steering confirmation.
  {Fixture f;f.brake=0x2F;f.front[0]=50;f.rear[0]=500;Config c;c.requireSteering=true;
   PrearmTracker pre;PrearmResult r;
   for(unsigned i=0;i<4;++i){f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c);}
   CHECK(r.ready&&r.source==CandidateSource::Radar&&!r.radarSteeringRequired);++checks;
  }
  // P direction remains fail-closed until its physical sign is calibrated.
  {Fixture f;f.brake=0xCF;f.front[0]=500;f.rear[0]=500;Config c;c.parkSteeringFallback=true;
   BrakeSteeringTracker manual;f.wheel=0;f.step();manual.update(f.o.inputs(0,f.now),f.now,c,1,true,true);
   f.brake=0xCF;f.wheel=-350;f.step();auto r=manual.update(f.o.inputs(0,f.now),f.now,c,1,false,true);
   CHECK(!r.ready&&r.reason==Reason::SteeringCalibrationRequired);++checks;}
  {Fixture f;f.brake=0x2F;f.front[0]=500;f.rear[0]=500;f.speed=626;Config c;
   auto r=prearmReady(f,c);CHECK(r.speedCut&&r.reason==Reason::HardSpeedCut);++checks;}
  {Fixture f;f.brake=0x2F;f.front[0]=500;f.rear[0]=500;Config c;
   auto ready=prearmReady(f,c);CHECK(ready.ready);f.speed=626;PrearmTracker pre;
   f.step();auto cut=pre.update(f.o.inputs(0,f.now),f.now,c);CHECK(cut.speedCut);
   f.speed=500;f.step();auto recovery=pre.update(f.o.inputs(0,f.now),f.now,c);
   CHECK(!recovery.ready&&recovery.stableForMs<kPrearmStableMs);++checks;}
  {Fixture f;f.gear=4;f.front[0]=50;f.skip=Rear;f.run();CHECK(f.result().candidate==Candidate::Reverse);
   CHECK(f.result().remainingMs>0&&f.result().remainingMs<=300);}
  {Fixture f;f.gear=2;f.skip=Front;f.run();CHECK(f.result().candidate==Candidate::Forward);}
  {Fixture f;f.skip=Steering;f.run();CHECK(f.result().candidate==Candidate::Forward);}
  for(int raw:{0,1,2,3}){Fixture f;f.occupancy=raw;f.run();CHECK(f.result().candidate==Candidate::Forward);}
  {Fixture f;f.run();for(int i=0;i<100;++i){f.occupancy=i&3;f.step();CHECK(f.result().candidate==Candidate::Forward);}}
  for(int raw:{0,501,511}){Fixture f;f.front[3]=raw;f.run();CHECK(f.result().candidate==Candidate::None);
   CHECK(f.result().reason==(raw==0?Reason::ProbeBlocked:raw==511?Reason::ProbeUnavailable:Reason::ProbeUnknown));}
  for(int g:{0,3,7}){Fixture f;f.gear=g;f.run();CHECK(f.result().reason==Reason::GearInvalid);}
  {Fixture f;f.run();f.brake=0x2F;f.step();CHECK(f.result().reason==Reason::BrakeReleased);}
  {Fixture f;f.run();f.brake=0xEF;f.step();CHECK(f.result().reason==Reason::BrakeInvalid);}
  {Fixture f;f.run();f.brake=0x4F;f.step();CHECK(f.result().reason==Reason::BrakeReleased);}
  {Fixture f;f.run();f.accel=1;f.step();CHECK(f.result().reason==Reason::AcceleratorPressed);}
  {Fixture f;f.run();f.accel=255;f.step();CHECK(f.result().reason==Reason::AcceleratorInvalid);}
  {Fixture f;f.run();f.speed=601;f.step();CHECK(f.result().reason==Reason::Moving);}
  {Fixture f;f.run();f.speed=4095;f.step();CHECK(f.result().reason==Reason::SpeedInvalid);}
  for(int raw:{0,1,3}){Fixture f;f.run();f.buckle=raw;f.step();CHECK(f.result().candidate==Candidate::None);}
  {Fixture f;f.run();f.left=0x21;f.step();CHECK(f.result().reason==Reason::DoorNotClosed);}
  {Fixture f;f.run();f.right=0x21;f.step();CHECK(f.result().reason==Reason::DoorNotClosed);}
  {Fixture f;f.run();f.trunk=1;f.step();CHECK(f.result().reason==Reason::DoorNotClosed);}
  {Fixture f;f.run();f.angleValidity=0;f.angleStatus=2;f.step();CHECK(f.result().candidate==Candidate::Forward);}
  for(int s=0;s<SignalCount;++s){if(s==Steering)continue;Fixture f;f.skip=s;f.run();CHECK(f.result().reason==Reason::Missing);}
  {Fixture f;f.run();uint8_t d[8]={};f.o.observe(1,0x145,8,false,false,d,f.now);CHECK(f.result().reason==Reason::Checksum);}
  {Fixture f;f.run();uint8_t d[8]={};f.emit(1,0x118,d,7);CHECK(f.result().reason==Reason::Length);}
  {Fixture f;f.run();auto t=f.o.tracks[1][Front];uint8_t d[8];memcpy(d,t.frame.data,8);
   f.o.observe(1,0x20E,8,false,false,d,f.now);CHECK(f.o.tracks[1][Front].generation==t.generation);
   CHECK(f.o.tracks[1][Front].frame.observedMs==t.frame.observedMs);
   d[0]^=1;d[7]=checksum(0x20E,d,7);f.o.observe(1,0x20E,8,false,false,d,f.now);CHECK(f.result().reason==Reason::CounterConflict);}
  {Fixture f;f.run();auto before=f.o.tracks[0][Buckle].frame.observedMs;uint8_t d[8]={1,0,0,0,0,0,0,0};
   f.emit(0,0x3C2,d);CHECK(f.o.tracks[0][Buckle].frame.observedMs==before);}
  {Fixture f;f.skip=Front;f.run();uint8_t d[8]={};f.emit(0,0x20E,d);CHECK(f.result().reason==Reason::Missing);}
  {Fixture f;f.now=UINT32_MAX-1200;f.run(80);CHECK(f.result().candidate==Candidate::Forward);}
  {Fixture f;f.aux=2;f.run();CHECK(f.result(false,2).candidate==Candidate::Forward);CHECK(f.result().candidate==Candidate::None);}
  {Fixture f;f.run(3);CHECK(f.result().reason==Reason::WaitStable);f.run(4);CHECK(f.result().candidate==Candidate::Forward);}
  {Fixture f;f.run();const auto gen=f.o.tracks[1][Front].generation;
   f.o.observe(1,0x20E,8,true,false,f.o.tracks[1][Front].frame.data,f.now);
   f.o.observe(1,0x20E,8,false,true,f.o.tracks[1][Front].frame.data,f.now);
   CHECK(f.o.tracks[1][Front].generation==gen);f.o.reset();CHECK(f.result().reason==Reason::Missing);}
  {Fixture f;f.speed=600;f.run();CHECK(f.result().candidate==Candidate::Forward);Config c;c.maxSpeedKph=7;
   CHECK(f.o.result(0,f.now,true,c).reason==Reason::Moving);}
  {Fixture f;f.speed=400;f.run();CHECK(f.result().candidate==Candidate::Forward);f.speed=399;f.step();CHECK(f.result().reason==Reason::Moving);}
  {Fixture f;f.skip=Buckle;f.run();CHECK(f.result().reason==Reason::Missing);Config c;c.requireSeatbelt=false;
   auto r=f.o.result(0,f.now,true,c);CHECK(r.candidate==Candidate::Forward);CHECK(r.remainingMs>0&&r.remainingMs<=300);}
  {Fixture f;f.buckle=1;f.run();Config c;c.requireSeatbelt=false;CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Forward);
   CHECK((f.o.tracks[0][Buckle].frame.data[6]&3)==1);}
  {Fixture f;f.run(4);Config c;c.maxSpeedKph=0;CHECK(f.o.result(0,f.now,true,c).reason==Reason::ZeroDwell);
   f.run(12);CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Forward);
   f.speed=501;f.step();CHECK(f.o.result(0,f.now,true,c).reason==Reason::Moving);CHECK(f.result().candidate==Candidate::Forward);}
  // P ignores D/R radar steering confirmation entirely.
  {Fixture f;f.run();Config c;c.requireSteering=true;
   CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Forward);
   f.skip=Steering;f.step();CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Forward);}
  // D/R radar confirmation is relative to the brake-valid baseline and uses
  // obstacleDeg only (not the manual D/R angle).
  {Fixture f;f.gear=4;f.front[0]=50;f.run();Config c;c.requireSteering=true;
   f.wheel=200;f.step();CHECK(f.o.result(0,f.now,true,c).reason==Reason::WaitWheel);
   f.wheel=350;f.step();CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Reverse);
   c.obstacleDeg=40;CHECK(f.o.result(0,f.now,true,c).reason==Reason::WaitWheel);
   f.wheel=450;f.step();CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Reverse);}
  {Fixture f;f.gear=4;f.front[0]=50;f.skip=Steering;f.run();Config c;c.requireSteering=true;
   CHECK(f.o.result(0,f.now,true,c).reason==Reason::Missing);}
  {Fixture f;f.run();f.front[0]=50;f.rear[0]=200;f.run(7);Config c;c.cooldownMs=300;
   auto r=f.o.result(0,f.now,true,c);CHECK(r.reason==Reason::Cooldown&&r.cooldownRemainingMs>0);
   c.cooldownMs=0;CHECK(f.o.result(0,f.now,true,c).candidate==Candidate::Reverse);
   f.run(30);CHECK(f.result().candidate==Candidate::Reverse);}
  {Fixture f;f.run();Config c;c.maxSpeedKph=9;CHECK(f.o.result(0,f.now,true,c).reason==Reason::ConfigInvalid);
   c.maxSpeedKph=8;c.pConfirmDeg=0;CHECK(f.o.result(0,f.now,true,c).reason==Reason::ConfigInvalid);
   c.pConfirmDeg=30;c.obstacleThresholdCm=500;CHECK(f.o.result(0,f.now,true,c).reason==Reason::ConfigInvalid);}
  // Missing, invalid and stale core data revoke an already-ready candidate.
  for(int signal:{int(Gear),int(Brake),int(Speed),int(LeftDoors),int(RightDoors),int(Buckle)}) {
    Fixture f;f.brake=0x2F;Config c;PrearmTracker pre;PrearmResult r;
    for(int i=0;i<4;++i){f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c);}
    CHECK(r.ready);auto in=f.o.inputs(0,f.now);
    in.tracks[signal].frame.observedMs=f.now-kFreshMs;
    r=pre.update(in,f.now,c);CHECK(!r.ready&&r.candidate==Candidate::None);
    in=f.o.inputs(0,f.now);in.tracks[signal].valid=false;
    r=pre.update(in,f.now,c);CHECK(!r.ready);
  }
  // The physical driver pedal is held even when the separate apply bit is 0.
  {Fixture f;f.brake=0x4F;Config c;PrearmTracker pre;PrearmResult r;
    for(int i=0;i<8;++i){f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c);}
    CHECK(!r.ready&&r.reason==Reason::PrearmBrakeHeld);
    f.brake=0xCF;f.step();CHECK(!pre.update(f.o.inputs(0,f.now),f.now,c).ready);
    f.brake=0x2F;for(int i=0;i<4;++i){f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c);}
    CHECK(r.ready);f.brake=0xCF;f.step();CHECK(pre.update(f.o.inputs(0,f.now),f.now,c).ready);
  }
  // Manual P/D-R steering is no longer a pre-brake candidate even when its
  // switch is enabled; it is handled by BrakeSteeringTracker above.
  for(int gear:{1,2,4})for(int wheel:{-600,0,600}) {
    Fixture f;f.gear=gear;f.brake=0x2F;f.front[0]=f.rear[0]=500;f.wheel=wheel;
    Config c;c.steeringFallback=c.parkSteeringFallback=true;
    CHECK(!prearmReady(f,c).ready);++checks;
  }
  // V13/V14 advice uses the same pre-brake candidate authorization tracker.
  {Fixture f;f.brake=0x2F;Config c;PrearmTracker pre;PrearmResult r;
    Proposal vision{Candidate::Reverse,Reason::CandidateReady,"V13V14_PAIR"};
    for(int i=0;i<4;++i){f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c,&vision);}
    CHECK(r.ready&&r.candidate==Candidate::Reverse);
    f.brake=0xCF;f.step();CHECK(pre.update(f.o.inputs(0,f.now),f.now,c,&vision).ready);
    vision.candidate=Candidate::Forward;CHECK(!pre.update(f.o.inputs(0,f.now),f.now,c,&vision).ready);
    vision.candidate=Candidate::Reverse;CHECK(!pre.update(f.o.inputs(0,f.now),f.now,c,&vision).ready);
  }
  // At the hard boundary decisions may run; above it they clear, and recovery
  // while still holding the brake does not recreate authorization.
  {Fixture f;f.brake=0x2F;Config c;c.maxSpeedKph=8;c.hardCutSpeedKph=8;
    f.speed=600;CHECK(prearmReady(f,c).ready);
    f.speed=601;CHECK(prearmReady(f,c).speedCut);
    f.speed=500;f.o.setDecisionSpeedCut(true);f.step();
    for(const auto &w:f.o.windows)CHECK(!w.active);
    f.o.setDecisionSpeedCut(false);f.step();
    CHECK(f.o.tracks[0][Speed].valid);
  }
  // Prearm handles radar and vehicle-pair sources only. A same-gear field is
  // ignored and never masquerades as the independent brake-held steering input.
  for(int gear:{2,4}) {
    Fixture f;f.gear=gear;f.brake=0x2F;f.skip=Front;
    Config c;c.steeringFallback=true;c.requireSteering=true;c.obstacleDeg=700;
    Proposal field{gear==4?Candidate::Forward:Candidate::Reverse,Reason::CandidateReady,"V13V14_PAIR"};
    PrearmTracker pre;PrearmResult r;
    for(int i=0;i<4;++i){f.step();auto in=f.o.inputs(0,f.now);in.front.valid=in.rear.valid=false;
      r=pre.update(in,f.now,c,&field);}
    CHECK(!r.ready&&r.sameGearIgnored&&r.source==CandidateSource::None);++checks;
  }
  // The three switches stay isolated in prearm: radar uses only obstacleDeg;
  // P/D-R manual switches do not borrow that angle or source.
  for(unsigned mask=0;mask<8;++mask) {
    Config c;c.steeringFallback=(mask&1)!=0;c.parkSteeringFallback=(mask&2)!=0;
    c.requireSteering=(mask&4)!=0;c.pConfirmDeg=30;c.drConfirmDeg=60;c.obstacleDeg=700;
    {Fixture f;f.gear=4;f.brake=0x2F;f.front[0]=50;f.rear[0]=500;f.wheel=350;
      Config radar=c;radar.pConfirmDeg=radar.drConfirmDeg=700;radar.obstacleDeg=30;
      auto r=prearmReady(f,radar);CHECK(r.ready&&r.source==CandidateSource::Radar);
      CHECK(r.radarSteeringRequired==radar.requireSteering);
      f.wheel=250;r=prearmReady(f,radar);CHECK(r.ready);++checks;
    }
    {Fixture f;f.gear=4;f.brake=0x2F;f.skip=Steering;Proposal field{Candidate::Reverse,Reason::CandidateReady,"V13V14_PAIR"};
      PrearmTracker pre;PrearmResult r;
      for(int i=0;i<4;++i){f.step();r=pre.update(f.o.inputs(0,f.now),f.now,c,&field);}
      CHECK(r.ready&&r.source==CandidateSource::VehiclePair);++checks;
    }
    {Fixture f;f.gear=4;f.brake=0x2F;f.skip=Front;f.rear[0]=500;f.wheel=650;
      auto r=prearmReady(f,c);CHECK(!r.ready&&r.source!=CandidateSource::DriveReverseSteering);++checks;
    }
  }
  // Radar has priority: an obstacle candidate remains ready regardless of the
  // manual P/D-R switches. The runtime does not invoke manual steering then.
  for(unsigned mask=0;mask<4;++mask) {
    Fixture f;f.gear=4;f.brake=0x2F;f.front[0]=50;f.rear[0]=500;f.wheel=0;
    Config c;c.steeringFallback=(mask&1)!=0;c.parkSteeringFallback=(mask&2)!=0;
    c.pConfirmDeg=c.drConfirmDeg=700;c.obstacleDeg=30;
    auto r=prearmReady(f,c);CHECK(r.ready&&r.source==CandidateSource::Radar);++checks;
  }
  printf("PASS: %u simplified live-rule checks with two-phase prearm, P clear-to-D and hard speed cut: simple D/R/P rules, occupancy chatter immunity, optional seatbelt, configurable speed/cooldown/angle confirmation/obstacle distance threshold/steering fallback, CRC/counter/stale/source/rollover and 200ms stability; no CAN output\n",checks);
}
