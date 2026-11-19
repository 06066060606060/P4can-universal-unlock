"""Host checks for AP S3XY commands using production queue and legacy encoder."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'vehicle_logic.h').read_text(encoding='utf8')
a=s.index('static bool blinkerLegacyStartLocked(');start=s.index('{',a);i=start+1;depth=1
while depth:
 if s[i]=='{':depth+=1
 elif s[i]=='}':depth-=1
 i+=1
fn=s[a:i]
source='''
#include <cassert>
#include "auto_blinker_pure.h"
constexpr uint8_t STALK_IDLE=0,STALK_DOWN_1=6,STALK_UP_1=2,TURN_SIGNAL_STALKLESS=2;
constexpr uint32_t BLINKA_STALKLESS_PRESS_MS=300,BLINKA_STALKLESS_RELEASE_MS=200,BLINKA_PULSE_MS=300;
uint8_t oneShotTurn=0,oneShotSource=0,activeTurn=0,activeTurnSignalVariant=1;
bool oneShotDirect=false;uint32_t oneShotReleaseAt=0,oneShotUntil=0;
uint8_t dirToTurn(uint8_t dir){return dir==1?6:dir==2?2:0;}
'''+fn+'''
int main(){
 BlinkerTxRequestStatePure q={};
 for(uint8_t dir=1;dir<=2;dir++){
  assert(blinkerTxArmPure(q,dir,BLINKER_TX_SOURCE_S3XY_AP_PURE,dir,100));
  auto r=blinkerTxConsumeStockPure(q,101,true,250);
  assert(r.transmit&&r.source==3&&blinkerApTurnPure(r.dir)==(dir==1?8:4));
  assert(!blinkerTxConsumeStockPure(q,102,true,250).transmit);
  assert(blinkerLegacyStartLocked(dir,BLINKER_TX_SOURCE_S3XY_AP_PURE,100));
  assert(oneShotTurn==(dir==1?8:4)&&oneShotDirect&&oneShotUntil==400);
  assert(blinkerLegacyStartLocked(dir,BLINKER_TX_SOURCE_AUTO_PURE,100));
  assert(oneShotTurn==(dir==1?6:2)&&!oneShotDirect);
  assert(blinkerLegacyStartLocked(dir,BLINKER_TX_SOURCE_S3XY_PURE,100));
  assert(oneShotTurn==(dir==1?6:2)&&oneShotDirect);
 }
 assert(!blinkerTxArmPure(q,1,4,9,100));
 assert(blinkerTxArmPure(q,1,3,9,100));assert(!blinkerTxConsumeStockPure(q,351,true,250).transmit);
 assert(blinkerTxArmPure(q,2,3,10,100));assert(!blinkerTxConsumeStockPure(q,101,false,250).transmit);
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'test.cpp';p.write_text(source);exe=Path(tmp)/'test'
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root),str(p),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('PASS: AP left/right raw values, single consumption, legacy encoding, normal Auto/S3XY values, expiry and physical-stalk priority')
