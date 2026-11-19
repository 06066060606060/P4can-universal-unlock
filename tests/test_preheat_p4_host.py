"""Execute the production preheat runtime with deterministic physical CAN/NVS providers."""
import os
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#if !__has_include("preheat_runtime.h")
int main(){assert(false && "Battery Preheat engine must be available in the shipped package");}
#else
#include <cstring>
#include <map>
#include <string>
#include <functional>
#include "preheat_pure.h"
static uint8_t activeVehicleProfile=1,activeVehicleTopology=1;
static bool activeProfileConfigured=true;
#include "vehicle_profile.h"
bool activeProfilePreheatSupported(){return vehicleProfilePreheatSupported(activeVehicleProfile,activeVehicleTopology);}
bool activeProfileVehicleBusOnCanA(){return vehicleProfileVehicleBusOnCanA(activeVehicleProfile,activeVehicleTopology);}
bool activeProfileVehicleBusOnCanB(){return vehicleProfileVehicleBusOnCanB(activeVehicleProfile,activeVehicleTopology);}
using esp_err_t=int;
constexpr int ESP_OK=0,ESP_FAIL=-1,P4_BODY=0,CAN_TX_FRESH_VH=2,CAN_TX_TRACE_SOURCE_DEFAULT=0,S3XY_LOG_INFO=0;
constexpr uint32_t RECOVERY_BUS_FRESH_MS=1000;
enum NativeATxResultReason{NATIVE_A_TX_OK,NATIVE_A_TX_INVALID_MSG,NATIVE_A_TX_SEND_ERROR};
struct CanFrame{uint32_t can_id;uint8_t can_dlc,data[8],bus;};
struct twai_message_t{uint32_t identifier;uint8_t data_length_code,data[8];};
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
static int criticalDepth=0;
#define portENTER_CRITICAL(x) (++criticalDepth)
#define portEXIT_CRITICAL(x) (--criticalDepth)
static uint32_t nowMs=100000,canInitTime=0,p4CanRxCount[3]={10000,0,0},p4CanLastRxMs[3]={100000,0,0};
static bool passive=false,canTxAdministrativeHold=false,maintenance=false,nvsOpen=true,nvsWrite=true;
static std::map<std::string,int32_t> nvs;
static std::function<void()> onReadBack;
static bool nonSummonAdmission=true;static unsigned nvsBeginCount=0;
using TickType_t=uint32_t;
constexpr int pdTRUE=1;constexpr uint32_t portMAX_DELAY=UINT32_MAX;
struct FakeMutex{bool held=false;};using SemaphoreHandle_t=FakeMutex*;
SemaphoreHandle_t xSemaphoreCreateMutex(){static FakeMutex m;return &m;}
int xSemaphoreTake(SemaphoreHandle_t m,TickType_t){if(m->held)return 0;m->held=true;return pdTRUE;}
void xSemaphoreGive(SemaphoreHandle_t m){assert(m->held);m->held=false;}
bool twaiNonSummonAdmissionOpen(){return nonSummonAdmission;}
struct Preferences{
 bool begin(const char*ns,bool){assert(criticalDepth==0);++nvsBeginCount;assert(std::string(ns)=="preheat");return nvsOpen;}
 void end(){}
 bool getBool(const char*k,bool d){bool value=nvs.count(k)?nvs[k]!=0:d;if(onReadBack){auto f=onReadBack;onReadBack=nullptr;f();}return value;}
 size_t putBool(const char*k,bool v){if(!nvsWrite)return 0;nvs[k]=v;return 1;}
 int32_t getInt(const char*k,int32_t d){int32_t value=nvs.count(k)?nvs[k]:d;if(onReadBack){auto f=onReadBack;onReadBack=nullptr;f();}return value;}
 size_t putInt(const char*k,int32_t v){if(!nvsWrite)return 0;nvs[k]=v;return 4;}
};
uint32_t millis(){return nowMs;}uint32_t micros(){return nowMs*1000;}
bool canUsbPassive(){return passive;}bool canMaintenanceActive(){return maintenance;}
void s3xyLogPush(int,const char*){}
uint32_t canTxCancellationGenerationSnapshot(const volatile uint32_t*g){return *g;}
void canTxCancellationGenerationAdvance(volatile uint32_t*g){++*g;}
uint32_t canTxEpochSnapshot(){return 1;}
static int attempts=0;static uint32_t lastId=0;static std::function<void()> beforeSend;
bool canTxNativeASendTaggedGuarded(const CanFrame*f,uint32_t,uint8_t,const volatile uint32_t*g,uint32_t expected,esp_err_t&err,NativeATxResultReason*r){
 assert(f->bus==P4_BODY && activeVehicleProfile!=1 && f->can_dlc==8);if(beforeSend)beforeSend();
 err=*g==expected&&!passive&&!maintenance&&!canTxAdministrativeHold?ESP_OK:ESP_FAIL;*r=err==ESP_OK?NATIVE_A_TX_OK:NATIVE_A_TX_SEND_ERROR;
 if(err==ESP_OK){++attempts;lastId=f->can_id;assert(memcmp(f->data,preheatTripFramePure(lastId==0x082?PREHEAT_TRIP_082:PREHEAT_TRIP_347),8)==0);}return err==ESP_OK;
}
int canTxTwaiTransmitWithMaskTaggedGuarded(const twai_message_t*f,uint32_t,uint8_t mask,uint8_t,const volatile uint32_t*g,uint32_t expected){
 assert(activeVehicleProfile==1&&mask==CAN_TX_FRESH_VH&&f->data_length_code==8);if(beforeSend)beforeSend();
 if(*g!=expected||passive||maintenance||canTxAdministrativeHold)return ESP_FAIL;
 ++attempts;lastId=f->identifier;assert(memcmp(f->data,preheatTripFramePure(lastId==0x082?PREHEAT_TRIP_082:PREHEAT_TRIP_347),8)==0);return ESP_OK;
}
#include "preheat_runtime.h"
void tickWithoutNvs(){unsigned n=nvsBeginCount;preheatRuntimeTick();assert(nvsBeginCount==n);}
static bool r79OwnsLastSlot=false;
void driverWindowLabServiceTick(){}
bool r79ServiceStateRefreshTry(){return true;}
int p4CanHandleB(){return 0;}
bool p4_twai_r79_periodic_ready_v2(int){return true;}
void r79TransportSliceTick(bool){r79OwnsLastSlot=attempts==0;nonSummonAdmission=false;}
void p4PublishVehicleDiagnosticContext(uint32_t){}
//ACTUAL_R79_CHECKPOINT
void actualServiceOrder(){
//ACTUAL_CAN_SERVICE_ORDER
}
int main(){
 assert(preheatSettingsQuiesceForMaintenance());
 preheatMenuLoad();assert(!preheatMenuEnabled&&!preheatEnabled);
#ifdef PREHEAT_MAINTENANCE_REGRESSION
 maintenance=true;nvs.clear();togglePreheatEnabledFromButton();
 assert(!preheatEnabled&&!nvs.count("enabled") && "button arriving after reset may not recreate enabled NVS");
 assert(!preheatSetEnabled(true) && "already-extracted owner work cannot persist during maintenance");
 return 0;
#endif
#ifdef PREHEAT_ADMISSION_REGRESSION
 preheatEnabled=true;preheatTripId=PREHEAT_TRIP_082;nonSummonAdmission=false;
 preheatRuntimeTransmit(nowMs);assert(attempts==0 && "preheat cannot consume a reserved R79 queue slot");
 return 0;
#endif
 // Auto-off must remain durable work after a failed write. Retry with a
 // bounded cadence, keep OFF across a clean reboot, and let explicit ON win.
 assert(preheatSetEnabled(true));preheatAvgValid=true;preheatAvgMs=nowMs;preheatPackAvgCx10=500;
 tickWithoutNvs();assert(!preheatEnabled&&preheatAutoOffPersistPending&&nvs["enabled"]==1);
 nvsWrite=false;preheatSettingsService();
 assert(preheatAutoOffPersistPending && "failed OFF save must retain retry work");
 unsigned retryBegins=nvsBeginCount;preheatSettingsService();assert(nvsBeginCount==retryBegins);
 nowMs+=999;preheatSettingsService();assert(nvsBeginCount==retryBegins);
 nvsWrite=true;++nowMs;preheatSettingsService();assert(!preheatAutoOffPersistPending&&nvs["enabled"]==0);
 preheatMenuLoad();assert(!preheatEnabled);
 assert(preheatSetEnabled(true));preheatAvgMs=nowMs;tickWithoutNvs();nvsOpen=false;preheatSettingsService();assert(preheatAutoOffPersistPending);
 nvsOpen=true;preheatAvgValid=false;assert(preheatSetEnabled(true));nowMs+=1000;preheatSettingsService();assert(preheatEnabled&&nvs["enabled"]==1);
 // Retry interval crosses uint32 rollover. Maintenance must flush immediately
 // despite backoff and must report failure while retaining outstanding work.
 nowMs=UINT32_MAX-500;preheatAvgMs=nowMs;preheatAvgValid=true;tickWithoutNvs();nvsWrite=false;preheatSettingsService();
 maintenance=true;assert(!preheatSettingsQuiesceForMaintenance()&&preheatAutoOffPersistPending);maintenance=false;
 nowMs=498;nvsWrite=true;retryBegins=nvsBeginCount;preheatSettingsService();assert(nvsBeginCount==retryBegins);
 nowMs=499;preheatSettingsService();assert(!preheatAutoOffPersistPending&&nvs["enabled"]==0);
 nowMs=100000;p4CanLastRxMs[0]=nowMs;
 preheatEnabled=true;preheatAvgValid=true;preheatAvgMs=nowMs;preheatPackAvgCx10=500;
 onReadBack=[](){tickWithoutNvs();};(void)preheatSetEnabled(true);
 assert(preheatEnabled==(nvs["enabled"]!=0) && "settings commit must serialize against CAN auto-off");
 preheatRuntimeTick();assert(!preheatEnabled&&nvs["enabled"]==1);
 preheatSettingsService();assert(nvs["enabled"]==0);
 // A later explicit ON supersedes an already-deferred auto-off; it must not
 // be overwritten by the web owner after it returns durable success.
 assert(preheatSetEnabled(true));preheatRuntimeTick();assert(!preheatEnabled);
 preheatAvgValid=false;assert(preheatSetEnabled(true));preheatSettingsService();assert(preheatEnabled&&nvs["enabled"]==1);
 for(bool menu:{false,true}){
  preheatAvgValid=true;preheatAvgMs=nowMs;preheatPackAvgCx10=500;
  onReadBack=[](){tickWithoutNvs();};assert(preheatMenuSetEnabled(menu));
  assert(preheatEnabled&&nvs["enabled"]==1&&preheatMenuEnabled==menu);
  preheatRuntimeTick();preheatSettingsService();assert(!preheatEnabled&&nvs["enabled"]==0);
  preheatAvgValid=false;assert(preheatSetEnabled(true));
 }
 onReadBack=[](){tickWithoutNvs();};assert(preheatSetTargetCx10(355));
 assert(preheatTargetCx10==nvs["target"]&&preheatEnabled==bool(nvs["enabled"]));
 preheatAvgValid=false;preheatEnabled=false;nvs.clear();
 assert(preheatSetEnabled(true));assert(preheatMenuSetEnabled(false));assert(preheatEnabled&&!preheatMenuEnabled);
 preheatEnabled=false;preheatMenuLoad();assert(preheatEnabled&&!preheatMenuEnabled);
 assert(preheatSetTargetCx10(355)&&preheatTargetCx10==355);nvsWrite=false;assert(!preheatSetEnabled(false)&&preheatEnabled);assert(!preheatSetTargetCx10(400)&&preheatTargetCx10==355);nvsWrite=true;
 nvsOpen=false;preheatMenuLoad();assert(!preheatEnabled&&!preheatMenuEnabled);nvsOpen=true;
 for(activeVehicleProfile=1;activeVehicleProfile<=5;++activeVehicleProfile){
  activeVehicleTopology=vehicleProfileDefaultTopology(activeVehicleProfile);assert(preheatProfileSupported());
  for(uint8_t trip=PREHEAT_TRIP_082;trip<=PREHEAT_TRIP_347;++trip){
   preheatTripId=trip;preheatEnabled=true;int n=attempts;preheatRuntimeTransmit(nowMs);assert(attempts==n+1);
   passive=true;preheatRuntimeTransmit(nowMs);passive=false;assert(attempts==n+1);
   canTxAdministrativeHold=true;preheatRuntimeTransmit(nowMs);canTxAdministrativeHold=false;assert(attempts==n+1);
   maintenance=true;preheatRuntimeTransmit(nowMs);maintenance=false;assert(attempts==n+1);
   beforeSend=[](){assert(preheatSetEnabled(false));};preheatRuntimeTransmit(nowMs);beforeSend=nullptr;assert(attempts==n+1);
  }
 }
 activeVehicleProfile=1;activeVehicleTopology=1;preheatEnabled=true;preheatTripId=PREHEAT_TRIP_UNKNOWN;
 uint8_t d[8]={};preheatRuntimeIngestPhysical(2,0x082,8,d);assert(preheatTripId==PREHEAT_TRIP_UNKNOWN);
 preheatRuntimeIngestPhysical(1,0x082,8,d);assert(preheatTripId==PREHEAT_TRIP_UNKNOWN);
 preheatRuntimeIngestPhysical(0,0x082,8,d);assert(preheatTripId==PREHEAT_TRIP_082);
 preheatRuntimeResetUnderTxBarrier();assert(preheatTripId==PREHEAT_TRIP_082&&!preheatReplyArmed);
 preheatSessionRestart();preheatLastTxMs=0;preheatAvgValid=false;preheatMenuEnabled=false;
 int n=attempts;preheatRuntimeTick();assert(attempts==n+1&&preheatEnabled);nowMs+=50;preheatRuntimeTick();assert(attempts==n+1);nowMs+=50;preheatRuntimeTick();assert(attempts==n+2);
 preheatAvgValid=true;preheatAvgMs=nowMs;preheatPackAvgCx10=preheatTargetCx10;preheatRuntimeTick();assert(!preheatEnabled&&preheatAutoOffReason==PREHEAT_AUTOOFF_TARGET);
 preheatAvgValid=false;assert(preheatSetEnabled(true));preheatLastTxMs=nowMs;preheatStatorZeroSinceMs=nowMs;nowMs+=PREHEAT_STATOR_STALL_OFF_MS+1;preheatRuntimeTick();assert(!preheatEnabled&&preheatAutoOffReason==PREHEAT_AUTOOFF_STATOR_STALL);
 preheatAvgValid=false;preheatEnabled=true;preheatLastTxMs=0;preheatTripId=PREHEAT_TRIP_082;
 nowMs=200000;p4CanLastRxMs[0]=nowMs;attempts=0;nonSummonAdmission=true;
 actualServiceOrder();assert(r79OwnsLastSlot&&attempts==0);
 // Admission suppresses transmission alone: target auto-off must still run.
 preheatAvgValid=true;preheatAvgMs=nowMs;preheatPackAvgCx10=500;preheatRuntimeTick();assert(!preheatEnabled);
 preheatSettingsService();assert(nvs["enabled"]==0);
 // A reboot arriving before the deferred write must preserve auto-off.
 preheatAvgValid=false;assert(preheatSetEnabled(true));preheatAvgValid=true;
 preheatAvgMs=nowMs;preheatPackAvgCx10=500;tickWithoutNvs();assert(!preheatEnabled&&nvs["enabled"]==1);
 maintenance=true;assert(preheatSettingsQuiesceForMaintenance());assert(nvs["enabled"]==0);nvs.clear();
 togglePreheatEnabledFromButton();assert(!preheatEnabled&&!nvs.count("enabled"));
 assert(!preheatSetEnabled(true)&&!preheatMenuSetEnabled(true)&&!preheatSetTargetCx10(400));
 preheatSettingsService();assert(nvs.empty());maintenance=false;preheatMenuLoad();assert(!preheatEnabled);
 puts("PASS: production preheat physical BODY all five profiles, exact payloads, guards/cancel, menu independence/NVS/cadence/auto-off");
}
#endif
'''
runtime=(ROOT/'can_runtime.h').read_text()
service_end=runtime.index('    // R79 immediate/retry/periodic work always gets first access')
# Anchor to the service stage, not an inline implementation of R79 servicing.
# Execute the real ordering whether servicing is inline or delegated to a helper.
stage=runtime.rindex('CAN_TASK_STAGE_SERVICE,',0,service_end)
service_start=runtime.index(';',stage)+1
service=runtime[service_start:service_end]
checkpoint=''
if 'r79ServiceCheckpoint();' in service:
 start=runtime.index('static void r79ServiceCheckpoint()')
 opening=runtime.index('{',start)
 depth=1;end=opening+1
 while depth:
  depth+=(runtime[end]=='{')-(runtime[end]=='}');end+=1
 checkpoint=runtime[start:end]
assert 'preheatRuntimeTick();' in service
CODE=CODE.replace('//ACTUAL_R79_CHECKPOINT',checkpoint)
CODE=CODE.replace('//ACTUAL_CAN_SERVICE_ORDER',service)
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'preheat.cpp';out=Path(td)/'preheat';p.write_text(CODE)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable']+([os.environ['P4_PREHEAT_TEST_DEFINE']] if os.environ.get('P4_PREHEAT_TEST_DEFINE') else [])+['-I'+str(ROOT),str(p),'-o',str(out)],check=True)
 subprocess.run([str(out)],check=True)
