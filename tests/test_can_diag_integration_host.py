"""Actual checked NVS write path retains returns and brackets mutating calls."""
from pathlib import Path
import os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'nvs_checked.h').read_text();start=s.index('static inline bool nvsCheckedWriteBlob(');end=s.index('\n}',start)+2;body=s[start:end]
fixture=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <vector>
using esp_err_t=int; using nvs_handle_t=int;
constexpr int ESP_OK=0,NVS_READWRITE=1;
std::vector<int> order; int fail=0,sets=0,commits=0; const void*expected=nullptr;
struct Scope { explicit Scope(int source){assert(source==8);order.push_back(1);} ~Scope(){order.push_back(3);} };
#define P4_CAN_DIAG_NVS_WRITE(source, expression) ([&]() {Scope scope(source);return (expression);}())
int nvs_open(const char*,int,nvs_handle_t*h){*h=42;return ESP_OK;}
int nvs_set_blob(nvs_handle_t h,const char*,const void*p,size_t n){assert(h==42&&p==expected&&n==3);++sets;order.push_back(2);return fail==1?1:0;}
int nvs_commit(nvs_handle_t h){assert(h==42);++commits;order.push_back(2);return fail==2?1:0;}
void nvs_close(nvs_handle_t h){assert(h==42);}
'''+body+r'''
int main(){char bytes[3]={1,2,3};expected=bytes;
assert(nvsCheckedWriteBlob("features","cfg",bytes,3));
assert((order==std::vector<int>{1,2,3,1,2,3}));assert(sets==1&&commits==1);
order.clear();fail=1;assert(!nvsCheckedWriteBlob("features","cfg",bytes,3));
assert((order==std::vector<int>{1,2,3}));assert(sets==2&&commits==1);
order.clear();fail=2;assert(!nvsCheckedWriteBlob("features","cfg",bytes,3));assert((order==std::vector<int>{1,2,3,1,2,3}));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'main.cpp').write_text(fixture)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(p/'main.cpp'),'-o',str(p/'run')],check=True)
 subprocess.run([str(p/'run')],check=True)

# Actual logical-B alert handler must retain an isolated RX_QUEUE_FULL batch.
s=(ROOT/'can_runtime.h').read_text();start=s.index('static void canTwaiHandleAlerts()');end=s.index('\n}',start)+2
handler=s[start:end]
fixture=r'''
#include <cassert>
#include <cstdint>
constexpr int ESP_OK=0;
constexpr uint32_t TWAI_ALERT_TX_FAILED=1024,TWAI_ALERT_ERR_PASS=4096,TWAI_ALERT_BUS_ERROR=512,TWAI_ALERT_BUS_OFF=8192,TWAI_ALERT_RX_QUEUE_FULL=2048;
struct twai_status_info_t {int state;};
uint32_t alerts=0;int observed=0,legacy=0,reads=0,freezes=0,snaps=0;
int p4CanHandleB(){return 7;}uint8_t p4CanBusB(){return 0;}uint32_t millis(){return 10;}
int twai_read_alerts_v2(int h,uint32_t*out,int w){assert(h==7&&w==0);*out=alerts;return ESP_OK;}
int twai_get_status_info_v2(int,twai_status_info_t*s){++reads;s->state=2;return ESP_OK;}
void canTwaiObserveErrorAlerts(uint32_t,bool,uint32_t){++legacy;}
void canBTraceFreezeBusOff(uint32_t){++freezes;}
void recordTwaiBusOffSnapshot(const twai_status_info_t&,uint32_t){++snaps;}
#define P4_CAN_DIAG_ALERTS(bus, value) do {assert((bus)==0&&(value)==alerts);++observed;}while(0)
#define P4_CAN_DIAG_STATUS(bus, status, value) do {(void)(bus);(void)(status);(void)(value);}while(0)
'''+handler+r'''
int main(){
alerts=TWAI_ALERT_RX_QUEUE_FULL;canTwaiHandleAlerts();assert(observed==1&&reads==1&&legacy==0&&freezes==0&&snaps==0);
alerts=TWAI_ALERT_BUS_ERROR;canTwaiHandleAlerts();assert(observed==2&&reads==2&&legacy==1&&freezes==0);
alerts=TWAI_ALERT_BUS_OFF|TWAI_ALERT_ERR_PASS;canTwaiHandleAlerts();assert(observed==3&&reads==3&&legacy==2&&freezes==1&&snaps==1);
alerts=0;canTwaiHandleAlerts();assert(observed==3&&reads==3);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'main.cpp').write_text(fixture)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(p/'main.cpp'),'-o',str(p/'run')],check=True)
 subprocess.run([str(p/'run')],check=True)

# All inherited policy/storage bytes outside explicitly integrated adapters are
# protected against the immediately preceding completed package. Strip only
# observational wrappers, preserving original argument/return expressions.
import hashlib,json,re
from diagnostic_inverse import approved_base_bytes
baseline=json.loads((ROOT/'DIAGNOSTIC_BASELINE.json').read_text())
assert baseline['basePackage']=='P4-CAN-Universal-v3.31.5'
for name,expectedHash in baseline['protectedFiles'].items():
 text=approved_base_bytes(name,(ROOT/name).read_bytes()).decode().replace('\r\n','\n')
 if name == 'pin_config.h':
  # Only the user-requested physical CAN 2 GPIO move differs from this baseline.
  assert '#define CAN_CHASSIS_TX 50' in text and '#define CAN_CHASSIS_RX 49' in text
  text=text.replace('#define CAN_CHASSIS_TX 50','#define CAN_CHASSIS_TX 22').replace('#define CAN_CHASSIS_RX 49','#define CAN_CHASSIS_RX 23')
 if name in baseline['wrappedFiles']:
  text=text.replace('#include "can_error_diag_macros.h"\n','')
  marker=re.compile(r'P4_CAN_DIAG_NVS_WRITE\(\d+,\s*')
  while True:
   m=marker.search(text)
   if not m:break
   pos=m.end();depth=1;quote=None;escaped=False
   while depth:
    c=text[pos];pos+=1
    if quote:
     if escaped:escaped=False
     elif c=='\\':escaped=True
     elif c==quote:quote=None
    elif c in '\"\'':quote=c
    elif c=='(':depth+=1
    elif c==')':depth-=1
   text=text[:m.start()]+text[m.end():pos-1]+text[pos:]
 assert hashlib.sha256(text.encode()).hexdigest()==expectedHash,name+' policy/storage content changed beyond observation'
