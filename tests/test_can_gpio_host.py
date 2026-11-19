"""Actual boot-only GPIO storage and HTTP handlers with fault-injected NVS."""
from pathlib import Path
import json
import hashlib
import os
import re
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
web = (ROOT / 'web_api.h').read_text()
ino = (ROOT / (ROOT.name + '.ino')).read_text()
fault = ino[ino.index('  if (!p4CanGpioValid) {'):ino.index('  P4CAN_SERIAL_PRINTLN("Driver-wake')]
block = web[web.index('// CAN GPIO configuration:'):web.index('// End CAN GPIO configuration.')]
NVS = r'''
#pragma once
#include <cstddef>
using esp_err_t=int;using nvs_handle_t=int;
constexpr int ESP_OK=0,ESP_FAIL=1,ESP_ERR_NVS_NOT_FOUND=2,ESP_ERR_NVS_TYPE_MISMATCH=3,NVS_READONLY=0,NVS_READWRITE=1;
int nvs_open(const char*,int,nvs_handle_t*);
int nvs_get_blob(nvs_handle_t,const char*,void*,size_t*);
int nvs_set_blob(nvs_handle_t,const char*,const void*,size_t);
int nvs_erase_key(nvs_handle_t,const char*);
int nvs_commit(nvs_handle_t);
void nvs_close(nvs_handle_t);
'''
CODE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <map>
#include <algorithm>
#include "nvs.h"
static bool found=true,namespaceFound=true,wrongType=false,openReadFails=false,allReadsFail=false;
static int reads=0,sets=0,commits=0,erases=0,failReadAt=0,failSetAt=0,failCommitAt=0,failOpenWriteAt=0,writeOpens=0;
static bool corruptFirstWrite=false;
static std::vector<uint8_t> bytes;
static std::vector<std::string> events;
int nvs_open(const char*ns,int mode,nvs_handle_t*h){
 assert(std::string(ns)=="p4gpio");*h=42;
 if(mode==NVS_READONLY)return openReadFails?ESP_FAIL:namespaceFound?ESP_OK:ESP_ERR_NVS_NOT_FOUND;
 ++writeOpens;if(writeOpens==failOpenWriteAt)return ESP_FAIL;
 namespaceFound=true;return ESP_OK;
}
int nvs_get_blob(nvs_handle_t h,const char*key,void*out,size_t*size){
 assert(h==42&&std::string(key)=="map");
 if(!found)return ESP_ERR_NVS_NOT_FOUND;if(wrongType)return ESP_ERR_NVS_TYPE_MISMATCH;
 if(allReadsFail)return ESP_FAIL;
 if(!out){*size=bytes.size();return ESP_OK;}
 ++reads;events.push_back("read");if(reads==failReadAt)return ESP_FAIL;
 assert(*size>=bytes.size());memcpy(out,bytes.data(),bytes.size());*size=bytes.size();return ESP_OK;
}
int nvs_set_blob(nvs_handle_t h,const char*key,const void*value,size_t size){
 assert(h==42&&std::string(key)=="map");++sets;events.push_back("set");
 if(sets==failSetAt)return ESP_FAIL;
 const uint8_t*p=static_cast<const uint8_t*>(value);bytes.assign(p,p+size);found=true;wrongType=false;
 if(corruptFirstWrite&&sets==1)bytes[6]^=1;
 return ESP_OK;
}
int nvs_erase_key(nvs_handle_t,const char*){++erases;found=false;bytes.clear();return ESP_OK;}
int nvs_commit(nvs_handle_t){++commits;events.push_back("commit");return commits==failCommitAt?ESP_FAIL:ESP_OK;}
void nvs_close(nvs_handle_t){}
static int p4CanTxPins[]={20,50,26},p4CanRxPins[]={21,49,27};
static bool p4CanGpioValid=true;
#include "can_gpio_runtime.h"
class String:public std::string{
 public:using std::string::string;using std::string::operator+=;
 String(const std::string&s):std::string(s){}
 String&operator+=(unsigned long n){append(std::to_string(n));return *this;}
 String&operator+=(long n){append(std::to_string(n));return *this;}
};
#include "json_writer_arduino.h"
static void*p4CanHandles[]={reinterpret_cast<void*>(1),reinterpret_cast<void*>(2),reinterpret_cast<void*>(3)};
static volatile bool canMaintenanceStopped=false;
static bool maintenanceRequested=false,maintenanceSucceeds=true;
static int maintenanceCalls=0,reboots=0;
static bool canMaintenanceActive(){return maintenanceRequested;}
static bool prepareCanForMaintenance(){
 ++maintenanceCalls;events.push_back("stop");maintenanceRequested=true;
 if(!maintenanceSucceeds)return false;
 canMaintenanceStopped=true;for(auto&h:p4CanHandles)h=nullptr;return true;
}
static void delay(unsigned ms){assert(ms==250);events.push_back("delay");}
static void restartP4CanSafely(){assert(canMaintenanceStopped);++reboots;events.push_back("reboot");}
struct Server{
 std::map<std::string,String>args;int status=0,sends=0;String body;
 bool hasArg(const char*k){return args.count(k);}
 String arg(const char*k){return args[k];}
 void send(int code,const char*,const String&text){++sends;status=code;body=text;events.push_back("send");}
}server;
'''
CODE += block
CODE += r'''
static int wifiStarts=0,webStarts=0,canInstalls=0,canTaskStarts=0,bleStarts=0;
static bool vehicleProfileSetupMode=false,vehicleProfileNvsError=false;
using BaseType_t=int;constexpr int pdPASS=1;
static void webTask(void*){}static void*webTaskHandle=nullptr;
static void s3xyMapperTask(void*){}static void*s3xyTaskHandle=nullptr;
static bool masterEnabled=false;static int masterWrites=0;
static bool s3xyBluetoothMasterIsEnabled(){return masterEnabled;}
static bool s3xyMapperTaskIsRunning(){return false;}
static bool s3xyRuntimeStopIsPending(){return false;}
static void s3xyRequestRuntimeStop(){}
static bool s3xyWaitForRuntimeStopped(unsigned){return true;}
static bool s3xyBluetoothMasterPersist(bool enabled){++masterWrites;masterEnabled=enabled;return true;}
static void s3xyRuntimeRearmAutoReconnect(){}
static void wifiApBootStart(){++wifiStarts;}
static BaseType_t xTaskCreatePinnedToCore(void(*task)(void*),const char*name,int stack,void*arg,int priority,void**out,int core){
 assert(stack==8192&&!arg&&priority==1&&core==0);
 if(task==webTask){assert(std::string(name)=="web"&&out==&webTaskHandle);++webStarts;}
 else{assert(task==s3xyMapperTask&&std::string(name)=="s3xyMap"&&out==&s3xyTaskHandle);++bleStarts;}
 return pdPASS;
}
struct{void printf(const char*,const char*){}}Serial;
static void actualGpioBootBranch(){
'''+fault+r'''
 ++canInstalls;++canTaskStarts;++bleStarts;
}
static int nvs_flash_erase(){found=false;namespaceFound=false;wrongType=false;bytes.clear();return ESP_OK;}
static int nvs_flash_init(){return ESP_OK;}
static bool vehicleProfileWriteBootstrapMarker(bool notice){assert(!notice);return true;}
'''
start = web.index('static bool factoryResetAllNvs()')
end = web.index('\n}', start) + 2
CODE += web[start:end] + '\n'
start = web.index('static void httpS3xyBluetoothEnable()')
end = web.index('\n}', start) + 2
CODE += web[start:end] + '\n'
record = bytearray(b'P4GP\x01\x00' + bytes([20, 21, 50, 49, 26, 27]))
record += zlib.crc32(record).to_bytes(4, 'little')
CODE += '\nstatic const uint8_t original[]={' + ','.join(map(str, record)) + '};\n'
CODE += r'''
static void args(){server.args={{"tx1","22"},{"rx1","23"},{"tx2","50"},{"rx2","49"},{"tx3","26"},{"rx3","27"}};}
static void unchanged(){assert(p4CanTxPins[0]==20&&p4CanRxPins[0]==21&&p4CanTxPins[1]==50&&p4CanRxPins[1]==49&&p4CanTxPins[2]==26&&p4CanRxPins[2]==27);}
static void previous(){assert(found&&!wrongType&&bytes==std::vector<uint8_t>(original,original+16));}
int main(int argc,char**argv){
 assert(argc==2);const std::string scenario=argv[1];
 bytes.assign(original,original+16);
 if(scenario=="absent"){found=false;namespaceFound=false;assert(p4CanGpioLoadAtBoot());unchanged();httpCanGpioStatus();}
 else if(scenario=="corrupt"||scenario=="oversized"||scenario=="short"||scenario=="empty"||scenario=="wrong-type"){
  if(scenario=="corrupt")bytes[6]^=1;
  if(scenario=="oversized")bytes.resize(100,42);
  if(scenario=="short")bytes.resize(3);
  if(scenario=="empty")bytes.clear();
  if(scenario=="wrong-type")wrongType=true;
  assert(!p4CanGpioLoadAtBoot()&&!p4CanGpioValid);unchanged();
  actualGpioBootBranch();assert(wifiStarts==1&&webStarts==1&&canInstalls==0&&canTaskStarts==0&&bleStarts==0);
  assert(!vehicleProfileSetupMode&&!vehicleProfileNvsError);
  for(auto&h:p4CanHandles)h=nullptr;
  httpCanGpioStatus();assert(server.body.find("\"active\":null")!=std::string::npos);
  if(scenario!="corrupt"){
   args();httpCanGpioSet();assert(server.status==200&&reboots==1&&p4CanGpioValid==false);unchanged();
  }
 }
 else if(scenario=="boot-read-error"){
  openReadFails=true;assert(!p4CanGpioLoadAtBoot()&&!p4CanGpioValid);unchanged();
  actualGpioBootBranch();assert(wifiStarts==1&&webStarts==1&&canInstalls==0&&canTaskStarts==0&&bleStarts==0);
  for(auto&h:p4CanHandles)h=nullptr;httpCanGpioStatus();
 }
 else{
  assert(p4CanGpioLoadAtBoot());reads=0;events.clear();args();
  if(scenario=="gpio-ble-block"){
   p4CanGpioValid=false;httpS3xyBluetoothEnable();assert(server.status==409&&bleStarts==0&&masterWrites==0);
  }
  else if(scenario=="factory-reset"){
   assert(factoryResetAllNvs()&&!found&&!namespaceFound);unchanged();assert(p4CanGpioLoadAtBoot());httpCanGpioStatus();
  }
  else if(scenario=="invalid"){
   const auto complete=server.args;
   for(const char*k:{"tx1","rx1","tx2","rx2","tx3","rx3"}){
    server.args=complete;server.args.erase(k);httpCanGpioSet();assert(server.status==400);
    for(const char*v:{"","-20","+20","20x"," 20","20 ","2e1","256","4294967316","99999999999999999999","55","6","14","19","24","25","54","49"}){
     if(std::string(k)=="rx2"&&std::string(v)=="49")continue;
     server.args=complete;server.args[k]=v;httpCanGpioSet();
     // 49 is already in the complete map; rx2=49 alone is valid, so skip that one replacement.
     assert(server.status==400);
    }
   }
   server.args=complete;server.args["tx1"]=String("20\0x",4);httpCanGpioSet();assert(server.status==400);
   assert(maintenanceCalls==0&&sets==0&&commits==0&&reboots==0);previous();unchanged();
  }
  else if(scenario=="stop-failure"){
   maintenanceSucceeds=false;httpCanGpioSet();assert(server.status==503&&sets==0&&commits==0&&reboots==0&&maintenanceRequested);previous();unchanged();
  }
  else{
   if(scenario=="expanded")server.args={{"tx1","0"},{"rx1","2"},{"tx2","28"},{"rx2","33"},{"tx3","52"},{"rx3","53"}};
   if(scenario=="save-read-error")openReadFails=true;
   if(scenario=="set-failure")failSetAt=1;
   if(scenario=="commit-failure")failCommitAt=1;
   if(scenario=="write-open-failure")failOpenWriteAt=1;
   if(scenario=="readback-failure")failReadAt=2;
   if(scenario=="corrupt-readback")corruptFirstWrite=true;
   if(scenario=="rollback-failure"){failReadAt=2;failSetAt=2;}
   if(scenario=="missing-rollback"){found=false;failCommitAt=1;}
   if(scenario=="all-read-error")allReadsFail=true;
   httpCanGpioSet();unchanged();assert(canMaintenanceStopped&&maintenanceCalls==1);
   if(scenario=="success"||scenario=="expanded"){
    assert(server.status==200&&reboots==1&&sets==1&&commits==1);
    assert(events.front()=="stop"&&events[events.size()-3]=="send"&&events[events.size()-2]=="delay"&&events.back()=="reboot");
    httpCanGpioStatus();assert(server.body.find("\"active\":[{\"tx\":20,\"rx\":21}")!=std::string::npos);
    if(scenario=="expanded"){
     assert(server.body.find("\"saved\":[{\"tx\":0,\"rx\":2}")!=std::string::npos);
     assert(p4CanGpioLoadAtBoot()&&p4CanTxPins[0]==0&&p4CanRxPins[0]==2&&p4CanTxPins[1]==28&&p4CanRxPins[1]==33&&p4CanTxPins[2]==52&&p4CanRxPins[2]==53);
    }else{
     assert(server.body.find("\"saved\":[{\"tx\":22,\"rx\":23}")!=std::string::npos);
     assert(p4CanGpioLoadAtBoot()&&p4CanTxPins[0]==22&&p4CanRxPins[0]==23);
    }
   }else{
    assert(server.status==500&&reboots==0);
    if(scenario=="save-read-error"||scenario=="all-read-error")assert(sets==0&&commits==0);
    else if(scenario=="rollback-failure")assert(server.body.find("storage uncertain")!=std::string::npos);
    else if(scenario=="missing-rollback")assert(!found&&erases==1);
    else{previous();assert(server.body.find("previous storage verified")!=std::string::npos);}
   }
  }
 }
 printf("%s\n",server.body.c_str());
}
'''

# Missing only the intended schema/storage/HTTP behavior is a regression; compile
# failures or missing includes are not accepted as a RED result.
with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    (temp / 'nvs.h').write_text(NVS)
    (temp / 'gpio.cpp').write_text(CODE)
    binary = temp / 'gpio'
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-function', '-Wno-unused-variable', '-Wno-misleading-indentation',
                    '-I' + str(temp), '-I' + str(ROOT), str(temp / 'gpio.cpp'), '-o', str(binary)], check=True)
    scenarios = ['gpio-ble-block', 'wrong-type', 'absent', 'corrupt', 'oversized', 'short', 'empty', 'boot-read-error', 'invalid', 'stop-failure',
                 'save-read-error', 'set-failure', 'commit-failure', 'write-open-failure', 'readback-failure',
                 'corrupt-readback', 'rollback-failure', 'missing-rollback', 'all-read-error', 'success', 'expanded', 'factory-reset']
    for scenario in scenarios:
        result = subprocess.run([str(binary), scenario], text=True, capture_output=True)
        assert result.returncode == 0, scenario + '\n' + result.stdout + result.stderr
        payload = json.loads(result.stdout)
        if scenario in ('absent', 'corrupt', 'boot-read-error', 'success', 'expanded', 'factory-reset'):
            assert set(payload) == {'ok', 'valid', 'active', 'saved', 'defaults', 'allowedPins', 'rebootRequired', 'canStopped', 'error'}
            assert payload['ok'] is True
            assert payload['defaults'] == [{'tx':20,'rx':21},{'tx':50,'rx':49},{'tx':26,'rx':27}]
            assert payload['allowedPins'] == [pin for pin in range(55) if pin not in {6,14,15,16,17,18,19,24,25,54}]
            if scenario in ('corrupt', 'boot-read-error'):
                assert payload['valid'] is False and payload['active'] is None and payload['saved'] is None
                assert payload['rebootRequired'] is True and payload['canStopped'] is True
            elif scenario in ('absent', 'factory-reset'):
                assert payload['valid'] is True and payload['active'] == payload['saved'] == payload['defaults']
                assert payload['rebootRequired'] is False
            else:
                assert payload['active'][0] == {'tx':20,'rx':21} and payload['saved'][0] == ({'tx':0,'rx':2} if scenario == 'expanded' else {'tx':22,'rx':23})
                assert payload['rebootRequired'] is True and payload['canStopped'] is True
        elif scenario in ('wrong-type', 'oversized', 'short', 'empty'):
            assert payload == {'ok':True, 'rebooting':True}
        elif scenario == 'gpio-ble-block':
            assert payload['ok'] is False
        else:
            assert set(payload) == {'ok', 'error', 'canStopped', 'rebootRequired'}
            assert payload['ok'] is False
            assert payload['rebootRequired'] is (scenario != 'invalid')
            assert payload['canStopped'] is (scenario not in ('invalid', 'stop-failure'))
    print(f'PASS: {len(scenarios)} actual GPIO boot/storage/HTTP scenarios, no hot apply, checked rollback and explicit maintenance failures')

# Integration bindings: common recovery routes stay outside the profile gate;
# the actual GPIO-fault boot block returns before any CAN/BLE launch.
common = web[web.index('static void webTask('):web.index('  if (!vehicleProfileSetupMode && !vehicleProfileNvsError) {', web.index('static void webTask('))]
for method, handler in [('HTTP_GET', 'httpCanGpioStatus'), ('HTTP_POST', 'httpCanGpioSet')]:
    assert f'server.on("/api/system/can-gpio", {method}, {handler});' in common
assert ino.index('p4CanGpioLoadAtBoot();') < ino.index('if (vehicleProfileSetupMode || vehicleProfileNvsError)')
assert 'wifiApBootStart();' in fault and 'xTaskCreatePinnedToCore(webTask' in fault and 'return;' in fault
assert 'vehicleProfileSetupMode =' not in fault and 'vehicleProfileNvsError =' not in fault
assert ino.index(fault) < ino.index('const bool ready = p4CanInstall(') < ino.index('recoveryStartCanTasks()') < ino.index('xTaskCreatePinnedToCore(s3xyMapperTask')

# Keep inherited CAN policies, routing, timing/waits, HAL/SDK, storage and board
# configuration protected against the completed immediate base. The exact GPIO
# adapters below are the only inverse transformations; no broad file exemption.
baseline = json.loads((ROOT / 'tests/fixtures/can_gpio_v3318_backend_sha256.json').read_text())
assert baseline['basePackage'] == 'P4-CAN-Universal-v3.31.8'
# v3.33.1 adds explicitly scoped observation/naming edits, not GPIO changes.
from diagnostic_inverse import INVERSE as inverse, approved_base_bytes
assert inverse['basePackage'] == 'P4-CAN-Universal-v3.33.0'
def replace_one(text, old, new=''):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)
for relative, digest in baseline['files'].items():
    path = ROOT / (ROOT.name + '.ino') if relative == '@sketch' else ROOT / relative
    data = path.read_bytes()
    data = approved_base_bytes(relative, data)
    if relative == 'p4_can.h':
        text = data.decode()
        text = replace_one(text, '#include "can_gpio_pure.h"\n')
        text = replace_one(text, 'static int p4CanTxPins[]', 'static constexpr int p4CanTxPins[]')
        text = replace_one(text, 'static int p4CanRxPins[]', 'static constexpr int p4CanRxPins[]')
        text = replace_one(text, 'static bool p4CanGpioValid = true;\n')
        text = replace_one(text, '  if (!p4CanGpioValid) { p4CanInitError[bus] = ESP_ERR_INVALID_STATE; return false; }\n')
        data = text.encode()
    elif relative == 'web_api.h':
        text = data.decode()
        text = replace_one(text, '''  if (!p4CanGpioValid) {
    server.send(409, "application/json", "{\\"ok\\":false,\\"error\\":\\"Repair CAN GPIO and reboot before enabling Bluetooth\\"}");
    return;
  }
''')
        begin = text.index('// CAN GPIO configuration:')
        end = text.index('// End CAN GPIO configuration.', begin) + len('// End CAN GPIO configuration.\n\n')
        text = text[:begin] + text[end:]
        for method, handler in [('HTTP_GET', 'httpCanGpioStatus'), ('HTTP_POST', 'httpCanGpioSet')]:
            text = replace_one(text, f'  server.on("/api/system/can-gpio", {method}, {handler});\n')
        text = replace_one(text, '''      if (p4CanGpioValid) {
        number("TxPin", p4CanTxPins[bus]); number("RxPin", p4CanRxPins[bus]);
      } else {
        snprintf(key, sizeof(key), "can%uTxPin", bus + 1); jw.raw(key, "null");
        snprintf(key, sizeof(key), "can%uRxPin", bus + 1); jw.raw(key, "null");
      }
''', '      number("TxPin", p4CanTxPins[bus]); number("RxPin", p4CanRxPins[bus]);\n')
        data = text.encode()
    elif relative == '@sketch':
        text = data.decode().replace(inverse['basePackage'].replace('P4-CAN-Universal-', '', 1), 'v3.31.8')
        text = replace_one(text, '#include "can_gpio_runtime.h"\n')
        text = replace_one(text, '  (void)p4CanGpioLoadAtBoot();\n\n')
        text = replace_one(text, '''  // GPIO faults are separate from profile setup so the ordinary Settings page
  // remains available to repair wiring; never install CAN/start its tasks or BLE.
''' + fault)
        data = text.encode()
    assert hashlib.sha256(data).hexdigest() == digest, relative + ': changed beyond approved GPIO adapters'
print(f'PASS: {len(baseline["files"])} v3.31.8 backend source hashes after narrow GPIO-only inverse adapters')
