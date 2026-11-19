#include "../gear_hint_display_pure.h"
#include <assert.h>
#include <initializer_list>
#include <stdio.h>

static unsigned checks = 0;
#define CHECK(condition) do { ++checks; assert(condition); } while (0)

static void gear(gearhint::DisplayHintObserver &s, uint8_t g, uint32_t now) {
  const uint8_t d[] = {0, 0, static_cast<uint8_t>(g << 5)};
  s.observe(1, 0x118, 3, false, false, d, now);
}
static void checksum(uint8_t *d) {
  uint32_t sum = 0x46;
  for (unsigned i=1;i<8;++i) sum += d[i];
  d[0] = static_cast<uint8_t>(sum);
}
static void brake(gearhint::DisplayHintObserver &s, bool pressed, uint32_t now) {
  uint8_t d[8] = {0, static_cast<uint8_t>(s.brakeCounterSeen ? (s.brakeCounter+1)&15 : 0),
      0, static_cast<uint8_t>(pressed ? 0x40 : 0x20), 0,0,0,0};
  checksum(d);
  s.observe(1,0x145,8,false,false,d,now);
}
static void rawPair(gearhint::DisplayHintObserver &s, uint8_t a, uint8_t b, uint32_t now) {
  const uint8_t request[] = {0, 0, 0, a};
  const uint8_t direction[] = {0, static_cast<uint8_t>(b << 4), 0, 0};
  s.observe(2, 0x255, 4, false, false, request, now);
  s.observe(2, 0x12B, 4, false, false, direction, now);
}
static void pair(gearhint::DisplayHintObserver &s, uint8_t a, uint8_t b, uint32_t now) {
  brake(s,true,now); rawPair(s,a,b,now);
}

static void testBrakeInterlock() {
  using namespace gearhint;
  for (uint8_t g : {uint8_t(1),uint8_t(2),uint8_t(4)}) {
    for (uint8_t request : {uint8_t(1),uint8_t(2)}) {
      DisplayHintObserver s;
      const uint8_t orientation = request==1 ? 3 : 2;
      const auto expected = request==1 ? DisplayHint::Forward : DisplayHint::Reverse;
      gear(s,g,0); rawPair(s,request,orientation,1);
      CHECK(s.result(1,true).reason==HintReason::BrakeMissing);
      CHECK(!s.advice.seen && !s.direction.seen);
      brake(s,true,2);
      CHECK(s.brakeSession==1 && s.result(2,true).reason==HintReason::SourcesMissing);
      rawPair(s,request,orientation,3);
      CHECK(s.result(3,true).hint==expected);
      CHECK(s.result(3,true).remainingMs==297); // Oldest source is still gear at 0.
      brake(s,false,4);
      CHECK(s.result(4,true).hint==DisplayHint::None);
      CHECK(s.result(4,true).reason==HintReason::BrakeReleased);
      CHECK(!s.advice.seen && !s.direction.seen);
      rawPair(s,request,orientation,5);
      CHECK(!s.advice.seen && !s.direction.seen);
      brake(s,true,6);
      CHECK(s.brakeSession==2 && s.result(6,true).reason==HintReason::SourcesMissing);
      const uint8_t advice[4]={0,0,0,request};
      s.observe(2,0x255,4,false,false,advice,7);
      CHECK(s.result(7,true).reason==HintReason::SourcesMissing);
      rawPair(s,request,orientation,8);
      CHECK(s.result(8,true).hint==expected);
      CHECK(s.result(8,false).hint==DisplayHint::None);
    }
  }

  // A held/frozen sample cannot keep the interlock open through duplicate RX.
  DisplayHintObserver s;
  gear(s,4,0); pair(s,2,2,1);
  uint8_t held[8]; memcpy(held,s.brake.data,8);
  gear(s,4,299);
  s.observe(1,0x145,8,false,false,held,299);
  rawPair(s,2,2,299);
  CHECK(s.result(299,true).remainingMs==2);
  CHECK(s.result(301,true).reason==HintReason::BrakeStale);
  CHECK(s.result(301,true).hint==DisplayHint::None);
  s.observe(1,0x145,8,false,false,held,301);
  CHECK(s.result(301,true).reason==HintReason::BrakeStale);
  CHECK(!s.advice.seen && !s.direction.seen);
  brake(s,true,302);
  CHECK(s.result(302,true).reason==HintReason::SourcesMissing);
  rawPair(s,2,2,303);
  CHECK(s.result(303,true).hint==DisplayHint::Reverse);

  // Bad brake frames revoke a previously valid direction immediately.
  for (unsigned fault=0;fault<9;++fault) {
    DisplayHintObserver t;
    gear(t,1,10); pair(t,1,3,11);
    CHECK(t.result(11,true).hint==DisplayHint::Forward);
    uint8_t d[8]; memcpy(d,t.brake.data,8);
    d[1] = (d[1]+1)&15;
    if (fault==2) d[3]=0x0F; // Uninitialized pedal field.
    if (fault==3) d[3]=0xEF; // Fault pedal field.
    if (fault==4) d[1]=t.brakeCounter; // Changed payload with unchanged counter.
    if (fault==4) d[4]=1;
    checksum(d);
    if (fault==1) d[0]^=1;
    t.observe(1,0x145,fault==0?7:fault==8?9:8,fault==5,fault==6,fault==7?nullptr:d,12);
    CHECK(t.result(12,true).reason==HintReason::BrakeInvalid);
    CHECK(t.result(12,true).hint==DisplayHint::None);
    CHECK(!t.advice.seen && !t.direction.seen);
    brake(t,true,13);
    CHECK(t.result(13,true).reason==HintReason::SourcesMissing);
    rawPair(t,1,3,14);
    CHECK(t.result(14,true).hint==DisplayHint::Forward);
  }

  DisplayHintObserver wrongBus;
  gear(wrongBus,1,0);
  uint8_t d[8]={0,15,0,0xCF,0,0,0,0}; checksum(d);
  wrongBus.observe(0,0x145,8,false,false,d,1);
  wrongBus.observe(2,0x145,8,false,false,d,1);
  rawPair(wrongBus,1,3,2);
  CHECK(wrongBus.result(2,true).reason==HintReason::BrakeMissing);
  wrongBus.observe(1,0x145,8,false,false,d,3);
  rawPair(wrongBus,1,3,4);
  CHECK(wrongBus.result(4,true).hint==DisplayHint::Forward);
  brake(wrongBus,true,5); // Counter 15 -> 0 is allowed.
  CHECK(wrongBus.brakeCounter==0 && wrongBus.result(5,true).hint==DisplayHint::Forward);
  d[3]=0x2F; checksum(d);
  wrongBus.observe(0,0x145,8,false,false,d,6);
  CHECK(wrongBus.result(6,true).hint==DisplayHint::Forward); // Other bus cannot release it either.

  // Driver pressed with apply=0 is enough; apply alone is not a pedal press.
  d[1]=1; d[3]=0x4F; checksum(d);
  wrongBus.observe(1,0x145,8,false,false,d,7);
  CHECK(wrongBus.brakePressed());
  CHECK(wrongBus.result(7,true).hint==DisplayHint::Forward);
  d[1]=2; d[3]=0xAF; checksum(d);
  wrongBus.observe(1,0x145,8,false,false,d,8);
  CHECK(wrongBus.result(8,true).reason==HintReason::BrakeReleased);
  CHECK(wrongBus.result(8,true).hint==DisplayHint::None);

  DisplayHintObserver wrap;
  gear(wrap,2,UINT32_MAX-10); pair(wrap,1,3,UINT32_MAX-5);
  CHECK(wrap.result(3,true).hint==DisplayHint::Forward);
  gear(wrap,2,250); rawPair(wrap,1,3,251);
  CHECK(wrap.result(294,true).reason==HintReason::BrakeStale);
  wrap={}; // Receiver restart discards pedal state and candidates.
  gear(wrap,2,295); rawPair(wrap,1,3,296);
  CHECK(wrap.result(296,true).reason==HintReason::BrakeMissing);

  // Exact paired frames supplied from the vehicle, without regenerating CRC.
  DisplayHintObserver live;
  const uint8_t released[8]={0x91,0x09,0x00,0x20,0x04,0x1E,0x00,0x00};
  const uint8_t pressed[8]={0xBC,0x0A,0x00,0x40,0x04,0x28,0x00,0x00};
  gear(live,1,0);
  live.observe(1,0x145,8,false,false,released,1);
  CHECK(live.brakeValid && !live.brakePressed());
  CHECK(live.result(1,true).reason==HintReason::BrakeReleased);
  rawPair(live,1,3,2);
  CHECK(!live.advice.seen && !live.direction.seen);
  live.observe(1,0x145,8,false,false,pressed,3);
  CHECK(live.brakeValid && live.brakePressed());
  CHECK(strcmp(live.brakeState(3),"PRESSED")==0);
  CHECK(live.result(3,true).reason==HintReason::SourcesMissing);
  rawPair(live,1,3,4);
  CHECK(live.result(4,true).hint==DisplayHint::Forward);
  rawPair(live,2,2,5);
  CHECK(live.result(5,true).hint==DisplayHint::Reverse);
  brake(live,false,6);
  CHECK(live.result(6,true).reason==HintReason::BrakeReleased);
  CHECK(!live.advice.seen && !live.direction.seen);
}
static void testRealPartyPair() {
  using namespace gearhint;
  DisplayHintObserver s;
  const uint8_t actualGear[8]={0x2F,0x6C,0x32,0x30,0,0x48,0,0};
  const uint8_t actualBrake[8]={0xBE,0x0D,0,0x40,0x04,0x27,0,0};
  const uint8_t actualAdvice[4]={0x22,0,0x48,0x09};
  const uint8_t actualDirection[4]={0x76,0x3B,0x0F,0};
  s.observe(1,0x118,8,false,false,actualGear,100);
  s.observe(1,0x145,8,false,false,actualBrake,101);
  s.observe(2,0x255,4,false,false,actualAdvice,102);
  s.observe(2,0x12B,4,false,false,actualDirection,103);
  CHECK(directionCode(actualDirection)==3);
  CHECK(s.brakePressed());
  CHECK(s.result(104,true).hint==DisplayHint::Forward);
  CHECK(s.result(104,true).reason==HintReason::Matched);
  CHECK(s.result(104,true).remainingMs==296);
  // Byte 2 must not fabricate a direction or override byte 1.
  const uint8_t thirdByteOnly[4]={0x76,0x0B,0x3F,0};
  s.observe(2,0x12B,4,false,false,thirdByteOnly,105);
  CHECK(directionCode(thirdByteOnly)==0);
  CHECK(s.result(105,true).reason==HintReason::SourcesDisagree);
  CHECK(s.result(105,true).hint==DisplayHint::None);
  const uint8_t reverse[4]={0x76,0x2B,0x3F,0};
  const uint8_t reverseAdvice[4]={0x22,0,0x48,0x0A};
  s.observe(2,0x12B,4,false,false,reverse,106);
  CHECK(s.result(106,true).hint==DisplayHint::None); // Advice 1 / direction 2.
  s.observe(2,0x255,4,false,false,reverseAdvice,107);
  CHECK(s.result(107,true).hint==DisplayHint::Reverse);
  CHECK(s.result(400,true).hint==DisplayHint::None);
}
int main() {
  using namespace gearhint;
  DisplayHintObserver s;
  assert(s.result(0, true).reason == HintReason::GearMissing);
  rawPair(s, 1, 3, 0);  // Before a valid gear: never reuse these later.
  gear(s, 1, 1);
  assert(s.result(1, true).reason == HintReason::BrakeMissing);
  brake(s, true, 1);
  assert(s.result(1, true).reason == HintReason::SourcesMissing);
  pair(s, 1, 3, 2);
  assert(s.result(3, true).hint == DisplayHint::Forward);
  assert(s.result(3, true).remainingMs == 298);
  assert(s.result(3, false).hint == DisplayHint::None);
  pair(s, 2, 2, 4);
  assert(s.result(4, true).hint == DisplayHint::Reverse);
  pair(s, 1, 2, 5);
  assert(s.result(5, true).reason == HintReason::SourcesDisagree);
  pair(s, 1, 3, 6);
  gear(s, 4, 7);
  assert(s.gearSession == 2);
  assert(s.result(7, true).reason == HintReason::SourcesMissing); // Old P pair cleared.
  const uint8_t forward[] = {0, 0, 0, 1};
  s.observe(2, 0x255, 4, false, false, forward, 8);
  assert(s.result(8, true).reason == HintReason::SourcesMissing); // Need both new frames.
  pair(s, 1, 3, 9);
  assert(s.result(9, true).hint == DisplayHint::Forward); // D can observe forward.
  assert(s.result(9, true).reason == HintReason::MatchedOutsidePark);
  gear(s, 4, 10); // Same D must preserve its current pair.
  assert(s.gearSession == 2 && s.result(10, true).hint == DisplayHint::Forward);
  pair(s, 2, 2, 11);
  assert(s.result(11, true).hint == DisplayHint::Reverse); // D can observe reverse.
  gear(s, 2, 12);
  assert(s.gearSession == 3 && s.result(12, true).reason == HintReason::SourcesMissing);
  pair(s, 1, 3, 13);
  assert(s.result(13, true).hint == DisplayHint::Forward); // R can observe forward.
  gear(s, 2, 14);
  assert(s.result(14, true).hint == DisplayHint::Forward);
  pair(s, 2, 2, 15);
  assert(s.result(15, true).hint == DisplayHint::Reverse); // R can observe reverse.
  gear(s, 1, 16);
  assert(s.parkSession == 2);
  assert(s.gearSession == 4 && s.result(16, true).reason == HintReason::SourcesMissing);
  pair(s, 1, 3, 17);
  assert(s.result(317, true).hint == DisplayHint::None);
  gear(s, 1, 400);  // Same gear after a freshness gap starts another session.
  brake(s, true, 400);
  assert(s.parkSession == 3);
  assert(s.gearSession == 5);
  assert(s.result(400, true).reason == HintReason::SourcesMissing);
  pair(s, 1, 3, 401);
  gear(s, 1, 650);
  assert(s.result(701, true).hint == DisplayHint::None);
  gear(s, 4, 702); pair(s, 2, 2, 703);
  assert(s.result(703, true).hint == DisplayHint::Reverse);
  const uint32_t oldSession = s.gearSession;
  gear(s, 4, 1100);
  brake(s, true, 1100);
  assert(s.gearSession == oldSession + 1 && s.result(1100, true).reason == HintReason::SourcesMissing);
  pair(s, 1, 3, 1101);
  gear(s, 3, 1102); // N is not a display-candidate gear.
  assert(s.result(1102, true).reason == HintReason::UnsupportedGear);
  pair(s, 2, 2, 1103); assert(!s.advice.seen && !s.direction.seen);
  gear(s, 7, 1104); assert(s.result(1104, true).reason == HintReason::UnsupportedGear);
  gear(s, 0, 1105); assert(s.result(1105, true).reason == HintReason::UnsupportedGear);
  gear(s, 2, 1106); assert(s.result(1106, true).reason == HintReason::SourcesMissing);
  pair(s, 1, 3, 1107); assert(s.result(1107, true).hint == DisplayHint::Forward);
  const uint8_t valid[] = {0, 0, 0, 1};
  s.observe(2, 0x255, 3, false, false, valid, 1108);
  assert(!s.advice.seen);
  s.observe(0, 0x255, 4, false, false, valid, 1109);
  assert(!s.advice.seen);
  s.observe(2, 0x255, 4, true, false, valid, 1110);
  assert(!s.advice.seen);
  gear(s, 1, UINT32_MAX - 10);
  pair(s, 2, 2, UINT32_MAX - 5);
  assert(s.result(3, true).hint == DisplayHint::Reverse);
  s.observe(1, 0x118, 2, false, false, valid, 4);
  assert(s.result(4, true).reason == HintReason::GearMissing);
  gear(s, 4, 5); pair(s, 2, 2, 6);
  assert(s.result(6, true).reason == HintReason::MatchedOutsidePark);
  const uint8_t remote[] = {0,0,0,1};
  s.observe(2, 0x255, 4, false, true, remote, 7);
  assert(s.result(7,true).hint == DisplayHint::Reverse); // RTR does not refresh/replace data.
  assert(s.result(307,true).hint == DisplayHint::None);
  // Independent prearm observation pairs before the brake, survives the press,
  // and still expires stale data or resets on a physical gear transition.
  {DisplayHintObserver pre;pre.brakeGated=false;
    gear(pre,1,0);brake(pre,false,1);rawPair(pre,2,2,2);
    CHECK(pre.result(2,true).hint==DisplayHint::Reverse);
    brake(pre,true,3);CHECK(pre.result(3,true).hint==DisplayHint::Reverse);
    gear(pre,1,250);
    CHECK(pre.result(303,true).hint==DisplayHint::None);
    // Juniper publishes its pair fields about once per second. Refresh only
    // core state; the old pair must stay available to the execution prearm.
    gear(pre,1,400);brake(pre,false,401);gear(pre,1,650);gear(pre,1,900);brake(pre,false,900);
    CHECK(pre.result(901,true).hint==DisplayHint::None);
    CHECK(pre.result(901,true,kPrearmPairHoldMs).hint==DisplayHint::Reverse);
    gear(pre,1,1000);brake(pre,true,1000);
    auto retained=pre.result(1000,true,kPrearmPairHoldMs);
    CHECK(retained.hint==DisplayHint::Reverse && retained.remainingMs==502);
    gear(pre,1,1250);gear(pre,1,1400);brake(pre,true,1400);
    CHECK(pre.result(1502,true,kPrearmPairHoldMs).reason==HintReason::SourcesStale);
    gear(pre,4,1503);CHECK(!pre.advice.seen&&!pre.direction.seen);
  }
  testBrakeInterlock();
  testRealPartyPair();
  printf("PASS: %u brake-interlock checks plus V13/V14 P/D/R pair observation, gear/gap/release resets, counter freeze/conflicts, checksum and malformed rejection, brake-bound TTL and rollover; no shift output\n", checks);
}
