"""Actual scheduler and guarded retry: latest queued MUX1 must not wait for old recovery."""
import ast
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'tests'))
def load(name,all_top=False):
 path=P/'tests'/name
 text=path.read_text()
 nodes=[]
 for node in ast.parse(text).body:
  if isinstance(node,ast.With):
   if not all_top:break
   continue
  if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='print':continue
  nodes.append(node)
 ns={'__file__':str(path)}
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
 return ns

transport=load('test_r79_queue_preservation_host.py',all_top=True)
integration=load('test_r79_periodic_backlog_host.py')
rows=[]
for scenario in ('combined',):
 scheduling=load('test_r79_service_scheduling_host.py')
 rx=scheduling['code'].split('int main(){')[0]
 headers='\n'.join(re.findall(r'^#include .*$',rx,re.M))
 rx=re.sub(r'^#include .*$','',rx,flags=re.M)
 old='bool r79ProcessStockFrame(const twai_message_t&,uint8_t,uint32_t){return stockClaimed;}'
 assert rx.count(old)==1
 rx=rx.replace(old,'bool r79ProcessStockFrame(const twai_message_t&,uint8_t,uint32_t);')
 old='void r79TransportSliceTick(bool allowPeriodic){if(checkInputDone)assert(inputDone==1);services.push_back({processed,nowMs,unsigned(queue.size()),allowPeriodic});nowMs+=serviceStepMs;if(advanceEpochOnService)++epoch;}'
 assert rx.count(old)==1
 rx=rx.replace(old,'void r79TransportSliceTick(bool);')
 due=integration['due_helper']
 if due in rx:rx=rx.replace(due,'static bool r79ServiceWorkDueSnapshot(uint32_t);')
 old='*f=queue.front();queue.pop_front();return ESP_OK;'
 assert rx.count(old)==1
 rx=rx.replace(old,'*f=queue.front();queue.pop_front();if(f->identifier==0x3FD)newestDequeueMs=nowMs;return ESP_OK;')
 rx=rx.replace('template<typename... T> void r79LabObserve3fdMux1(T...){}', 'void r79LabObserve3fdMux1(const uint8_t*,uint8_t);')
 rx='static uint32_t newestDequeueMs=UINT32_MAX;\n'+rx
 pre=transport['p']
 pre=pre.replace('bool p4CanR79InputCurrent(){return inputCurrent;}', '''bool p4CanR79InputCurrent(){return inputCurrent&&std::none_of(runtime::queue.begin(),runtime::queue.end(),[](const runtime::twai_message_t& f){return !f.extd&&!f.rtr&&f.identifier==0x3FD&&f.data_length_code==8&&(f.data[0]&7)==1;});}''')
 pre=pre.replace('uint32_t millis(){return nowMs;}','uint32_t millis(){return runtime::nowMs;}')
 start=pre.index('void vTaskDelay(unsigned)');end=pre.index('\n',start)
 pre=pre[:start]+'''static bool arriveDuringRetry=false;
void vTaskDelay(unsigned){++runtime::nowMs;nowMs=runtime::nowMs;if(arriveDuringRetry){arriveDuringRetry=false;runtime::twai_message_t b;b.identifier=0x3FD;b.data[0]=1;b.data[7]=0xB2;runtime::queue.push_back(b);}}'''+pre[end:]
 pre=pre.replace('static int calls=0,clears=0;', 'static uint32_t newestAttemptMs=UINT32_MAX;static int calls=0,clears=0;')
 pre=pre.replace('esp_err_t send(const twai_message_t*f){++calls;', 'esp_err_t send(const twai_message_t*f){if(f->data[7]==0xB2&&newestAttemptMs==UINT32_MAX)newestAttemptMs=millis();++calls;')
 pre=pre.replace('void p4R79TimingGateRejected(int,const twai_message_t*,unsigned,int,uint8_t,int){++rejects;}',
  'void p4R79TimingGateRejected(int,const twai_message_t*f,unsigned,int,uint8_t,int){++rejects;if(f&&f->data[7]==0xB2&&newestAttemptMs==UINT32_MAX)newestAttemptMs=millis();}')
 main=transport['setup']+r'''
void setupCase(bool ap,bool native){
 ::reset();runtime::reset(0);runtime::newestDequeueMs=UINT32_MAX;newestAttemptMs=UINT32_MAX;
 latest[7]=0xA1;available=native;result=ESP_ERR_TIMEOUT;arriveDuringRetry=false;
 if(ap){gear=TESLA_GEAR_D;dasValid=true;dasState=3;}
 runtime::nowMs=nowMs=1000;r79RetrySchedule(R79LAB_TX_IMMEDIATE,1000,gen);
 assert(r79RetryPending&&r79RetryDueMs==1005);
 runtime::nowMs=nowMs=1005;runtime::nativeReady=false;
 runtime::beforeReceive=[](unsigned){if(!runtime::queue.empty()&&runtime::queue.front().identifier==0x3FD){
  assert(r79RetryPending&&r79RetryIndex==0&&r79RetryDueMs==1005&&"deferring obsolete recovery must retain budget/due");
 }};
}
void append(unsigned count,bool mux){
 for(unsigned i=0;i<count;++i){runtime::twai_message_t f;f.identifier=0x123;runtime::queue.push_back(f);}
 if(mux){runtime::twai_message_t f;f.identifier=0x3FD;f.data[0]=1;f.data[7]=0xB2;runtime::queue.push_back(f);}
}
int main(){
 for(bool ap:{false,true})for(bool native:{false,true}){
  // A normal initial echo, not an older retry, must also stop waiting when
  // the next relevant MUX1 arrives. Its authorized zero-wait fallback remains.
  setupCase(ap,native);r79RetryCancel();runtime::beforeReceive=nullptr;
  runtime::twai_message_t a;a.identifier=0x3FD;a.data[0]=1;a.data[7]=0xA1;
  runtime::queue.push_back(a);arriveDuringRetry=true;
  runtime::productionRxAndService();
  assert(runtime::processed==2&&!arriveDuringRetry);
  assert(newestAttemptMs==1006&&runtime::newestDequeueMs==1006&&"initial echo must yield to a new MUX1 arriving during admission wait");
  for(unsigned prefix:{0u,8u,63u}){
   setupCase(ap,native);append(prefix,true);runtime::productionRxAndService();
   assert(runtime::processed==prefix+1&&newestAttemptMs==1005&&runtime::newestDequeueMs==1005&&"latest queued input cannot wait for old recovery");
  }
  // A relevant input arriving during a bounded retry must stop further waiting
  // and leave the old retry reservation untouched until the new input is handled.
  setupCase(ap,native);append(8,false);arriveDuringRetry=true;
  runtime::productionRxAndService();
  assert(!arriveDuringRetry&&runtime::processed==9);
  assert(newestAttemptMs==1006&&runtime::newestDequeueMs==1006);
  // Unrelated backlog must not suppress due recovery itself.
  setupCase(ap,native);append(16,false);runtime::productionRxAndService();
  assert(r79RetryIndex==1&&r79LastRetryMs==1005);
 }
 puts("PASS actual P/AP queued input before recovery, arrival during wait, reservation preservation and unrelated backlog");
}
'''
 helpers=integration['helpers'].replace('uint32_t canTxCancellationGenerationSnapshot(const volatile uint32_t*g){return *g;}','')
 code=headers+'\nnamespace runtime{\n'+rx+'\n}\n'+pre+transport['f']+helpers+integration['bridge']+'\nnamespace runtime {void r79LabObserve3fdMux1(const uint8_t*d,uint8_t){memcpy(::latest,d,8);}}\n'+main
 with tempfile.TemporaryDirectory(prefix='p4-prewait-regression-') as td:
  path=Path(td)/'probe.cpp';path.write_text(code);out=Path(td)/'probe'
  subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',
   '-Wno-unused-function','-Wno-unused-variable','-I'+str(P/'tests'),'-I'+str(P/'tests/r79_timing_fakes'),'-I'+str(P),str(path),'-o',str(out)],check=True)
  output=subprocess.check_output([str(out)],text=True)
  print(output,end='',flush=True);rows.append(output.strip())

