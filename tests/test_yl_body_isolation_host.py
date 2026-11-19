"""Actual physical status/recovery and boot/supervisor decisions, no hardware."""
from pathlib import Path
import os, subprocess, tempfile
from test_s3xy_pairing_host import source_block
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'can_runtime.h').read_text()
functions='\n'.join(source_block(s[s.rfind(n):],n) for n in ('static void p4CanServiceNativeStatus(', 'static bool recoveryNativeAColdInit('))
# Compile actual startup decision after per-controller installation.
ino=(ROOT/(ROOT.name+'.ino')).read_text()
a=ino.index('  nativeAReady = p4CanOnline[p4CanBusA()];')
b=ino.index('  canTwaiResetErrorAlertWindow();',a)
boot='static void bootDecision(){\n'+ino[a:b]+'\n}\n'
a=s.index('      bool bothFresh = ');b=s.index('\n\n',a)
traffic='static void traffic(bool aFresh,bool bFresh,bool extraFresh,bool &all,bool &any){\n'+s[a:b]+'\nall=bothFresh;any=anyFresh;}\n'
prelude=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "driver/twai.h"
static bool yl=true,maintenance=false,nativeAReady=true,twaiReady=true,allCanReady=true;
static bool p4CanOnline[3]={true,true,true},p4CanExtraFresh=true;
static FakeController hw[3]={{0,TWAI_STATE_RUNNING,0,false,{}},{1,TWAI_STATE_RUNNING,1,false,{}},{2,TWAI_STATE_RUNNING,0,false,{}}};
static twai_handle_t p4CanHandles[3]={&hw[0],&hw[1],&hw[2]};
static unsigned p4CanBusOffCount[3]={},p4CanRecoveries[3]={},p4CanRecoveryFailures[3]={};
static uint8_t nativeALastControllerState=TWAI_STATE_RUNNING,nativeAState=0;
static uint32_t nativeALastControllerStateMs=0,nativeARxOverflowCount=0,nativeARxOverflowLastMs=0,nativeATxFailConsecutive=0;
static struct {uint32_t controllerOverrunObservations;} canARxDiagnostics;
static unsigned invalidateA=0,invalidateAll=0,restarts=0,reboots=0,recoveryCalls=0,startCalls=0,statusCalls=0,diagRecoveries=0;
static bool statusFail=false,recoveryFail=false,startFail=false,initAOk=true,initExtraOk=true;
static int lastRecovery=-1,lastStart=-1,lastReinstall=-1;
static uint32_t nowMs=100;
static uint32_t millis(){return nowMs;}
static bool activeProfileIsYl(){return yl;}
static uint8_t p4CanBusA(){return yl?2:0;}
static uint8_t p4CanBusB(){return yl?0:1;}
static uint8_t p4CanBusExtra(){return yl?1:2;}
static bool canMaintenanceActive(){return maintenance;}
static bool canUsbPassive(){return false;}
static bool nativeAInitChecked(){nativeAReady=initAOk;return initAOk;}
static bool p4CanReinstall(uint8_t b,bool){lastReinstall=b;return initExtraOk;}
static void restartP4CanSafely(){++reboots;}
static void invalidateCanTxStateForCanARecovery(){++invalidateA;}
static void invalidateCanTxStateForFullRecovery(){++invalidateAll;}
static void canATraceFreezeBusOff(uint32_t,uint8_t,uint32_t){}
static void canARxDiagnosticsObserveOverflowPure(decltype(canARxDiagnostics)&,uint32_t,int,bool,bool){}
constexpr int CAN_SUP_HARD_STALE=1,CAN_REC_NATIVE_A_REINIT_FAIL=2;
static void requestCanSubsystemRestart(int,int){++restarts;}
#define P4_CAN_DIAG_ALERTS(...) ((void)0)
#define P4_CAN_DIAG_RECOVERY(...) (++diagRecoveries)
static void p4CanPublishStatus(uint8_t,const twai_status_info_t&){}
static esp_err_t twai_read_alerts_v2(twai_handle_t,uint32_t*a,TickType_t){*a=TWAI_ALERT_BUS_ERROR;return ESP_OK;}
esp_err_t twai_get_status_info_v2(twai_handle_t h,twai_status_info_t*out){++statusCalls;if(statusFail)return ESP_FAIL;out->state=h->state;return ESP_OK;}
esp_err_t twai_start_v2(twai_handle_t h){++startCalls;lastStart=h->id;if(startFail)return ESP_FAIL;h->state=TWAI_STATE_RUNNING;return ESP_OK;}
static esp_err_t twai_initiate_recovery_v2(twai_handle_t h){++recoveryCalls;lastRecovery=h->id;if(recoveryFail)return ESP_FAIL;h->state=TWAI_STATE_RECOVERING;return ESP_OK;}
'''
main=r'''
static void reset(){
 yl=true;maintenance=statusFail=recoveryFail=startFail=false;nativeAReady=twaiReady=allCanReady=true;
 p4CanExtraFresh=true;initAOk=initExtraOk=true;
 invalidateA=invalidateAll=restarts=reboots=recoveryCalls=startCalls=statusCalls=diagRecoveries=0;
 for(unsigned b=0;b<3;b++){p4CanHandles[b]=&hw[b];p4CanOnline[b]=true;hw[b].state=TWAI_STATE_RUNNING;p4CanBusOffCount[b]=p4CanRecoveries[b]=p4CanRecoveryFailures[b]=0;}
}
int main(){
 (void)activeProfileIsYl();
 // Additional BODY BUS_OFF never invalidates VEHICLE/PARTY or asks full reset.
 reset();hw[1].state=TWAI_STATE_BUS_OFF;p4CanServiceNativeStatus(1,false);
 assert(invalidateAll==0&&invalidateA==0&&restarts==0);
 assert(lastRecovery==1&&recoveryCalls==1&&p4CanRecoveries[1]==1&&p4CanBusOffCount[1]==1);
 assert(!p4CanOnline[1]&&!p4CanExtraFresh&&p4CanOnline[0]&&p4CanOnline[2]&&nativeAReady&&twaiReady);
 p4CanServiceNativeStatus(1,false);assert(recoveryCalls==1&&startCalls==0); // RECOVERING only observed
 hw[1].state=TWAI_STATE_STOPPED;p4CanServiceNativeStatus(1,false);
 assert(startCalls==1&&lastStart==1&&p4CanOnline[1]&&!p4CanExtraFresh);
 assert(!invalidateAll&&!invalidateA&&!restarts);
 // Failures retry only that installed controller on the next existing status tick.
 reset();hw[1].state=TWAI_STATE_BUS_OFF;recoveryFail=true;
 for(unsigned i=0;i<4;i++)p4CanServiceNativeStatus(1,false);
 assert(recoveryCalls==4&&p4CanRecoveryFailures[1]==4&&!restarts&&!invalidateAll);
 assert(p4CanBusOffCount[1]==1);
 recoveryFail=false;p4CanServiceNativeStatus(1,false);assert(hw[1].state==TWAI_STATE_RECOVERING);
 hw[1].state=TWAI_STATE_STOPPED;startFail=true;
 for(unsigned i=0;i<4;i++)p4CanServiceNativeStatus(1,false);
 assert(!restarts&&!p4CanOnline[1]);startFail=false;p4CanServiceNativeStatus(1,false);assert(p4CanOnline[1]);
 reset();statusFail=true;p4CanServiceNativeStatus(1,false);assert(!p4CanOnline[1]&&!p4CanExtraFresh&&!restarts);
 // A disappeared handle degrades BODY without touching required controllers.
 reset();p4CanHandles[1]=nullptr;p4CanOnline[1]=false;p4CanExtraFresh=false;
 p4CanServiceNativeStatus(1,false);assert(statusCalls==0&&!restarts&&nativeAReady&&twaiReady);
 reset();hw[1].state=TWAI_STATE_STOPPED;maintenance=true;p4CanServiceNativeStatus(1,false);assert(startCalls==0);
 // PARTY and non-YL Extra retain their former invalidation/escalation behavior.
 reset();hw[2].state=TWAI_STATE_BUS_OFF;recoveryFail=true;p4CanServiceNativeStatus(2,true);
 assert(invalidateA==1&&restarts==1&&!nativeAReady);
 reset();yl=false;hw[2].state=TWAI_STATE_BUS_OFF;recoveryFail=true;p4CanServiceNativeStatus(2,false);
 assert(invalidateAll==1&&restarts==1);
 reset();yl=false;hw[2].state=TWAI_STATE_STOPPED;startFail=true;p4CanServiceNativeStatus(2,false);assert(restarts==1);
 // Regular bus errors while RUNNING do not force any controller restart.
 reset();p4CanServiceNativeStatus(1,false);assert(!recoveryCalls&&!startCalls&&!restarts&&!invalidateAll);
 // Actual boot predicate: only YL's optional BODY can fail independently.
 for(bool isYl:{false,true})for(unsigned mask=0;mask<8;mask++){
  reset();yl=isYl;allCanReady=mask==7;
  for(unsigned b=0;b<3;b++)p4CanOnline[b]=(mask&(1u<<b))!=0;
  bootDecision();const bool expected=(mask==7)||(isYl&&mask==5);
  assert((reboots==0)==expected);
 }
 // Controlled hard recovery: optional BODY failure cannot turn into a reboot.
 for(bool isYl:{false,true})for(bool a:{false,true})for(bool c:{false,true}){
  reset();yl=isYl;initAOk=a;initExtraOk=c;
  assert(recoveryNativeAColdInit()==(a&&(isYl||c)));
  assert(lastReinstall==p4CanBusExtra()&&!p4CanExtraFresh);
 }
 // Actual supervisor predicates keep YL BODY-only wake/no-RX out of pair recovery.
 for(bool isYl:{false,true})for(unsigned mask=0;mask<8;mask++){
  yl=isYl;const bool a=(mask&1),b=(mask&2),c=(mask&4);bool all=false,any=false;
  traffic(a,b,c,all,any);assert(all==(a&&b&&(isYl||c)));assert(any==(a||b||(!isYl&&c)));
 }
 puts("PASS: actual YL BODY-local recovery/failures, boot and hard-init isolation, supervisor required traffic, PARTY/non-YL preservation");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);src=p/'main.cpp';src.write_text('#include <initializer_list>\n'+prelude+functions+boot+traffic+main)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I'+str(ROOT/'tests'),str(src),'-o',str(p/'run')],check=True)
 subprocess.run([str(p/'run')],check=True)
