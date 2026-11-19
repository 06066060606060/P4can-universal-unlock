"""Execute actual pinned/native RX function: malformed DLC must never reach memset.

The production function is extracted unchanged. Only queue/HAL/platform primitives
are faked; bounded memset instrumentation rejects unsafe calls before any write.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'p4_twai_driver.c'
source = (path if path.exists() else ROOT / 'vendor/twai/twai.c.txt').read_text()
begin = source.index('esp_err_t twai_receive_v2(')
receive = source[begin:source.index('\n}', begin) + 2]
begin = source.index('typedef struct {\n    twai_hal_frame_t frame;')
boundary_types = source[begin:source.index('static uint32_t p4_twai_boundary_advance(', begin)]
header = (ROOT/'p4_twai_priority.h').read_text()
meta_start = header.index('typedef struct {')
meta_end = header.index('} p4_twai_rx_metadata_t;', meta_start)+len('} p4_twai_rx_metadata_t;')
boundary_types = header[meta_start:meta_end] + '\nstatic int64_t esp_timer_get_time(void){return 10000;}\n' + boundary_types
fixture = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
typedef int esp_err_t;
typedef unsigned TickType_t;
enum { ESP_OK=0, ESP_ERR_INVALID_ARG=0x102, ESP_ERR_INVALID_SIZE=0x104, ESP_ERR_TIMEOUT=0x107,
       TWAI_FRAME_MAX_LEN=8, pdTRUE=1 };
typedef struct { union { struct { uint32_t extd:1,rtr:1,ss:1,self:1,dlc_non_comp:1,reserved:27; }; uint32_t flags; };
 uint32_t identifier; uint8_t data_length_code; uint8_t data[8]; } twai_message_t;
typedef struct { uint32_t id; uint8_t dlc; bool ide,rtr; } twai_frame_header_t;
typedef struct { twai_frame_header_t header; uint8_t data[8]; } twai_hal_frame_t;
typedef struct { int bus; } twai_hal_context_t;
typedef struct twai_obj_t { twai_hal_context_t *hal; void *rx_queue; int rx_msg_count; int spinlock; int controller_id; } twai_obj_t;
typedef twai_obj_t *twai_handle_t;
#define TWAI_CHECK(cond, ret_val) do { if (!(cond)) return ret_val; } while(0)
static int queueOk=1, receives=0, parses=0, locks=0, unlocks=0;
static unsigned unsafeWrites=0, zeroWrites=0;
static void *expectedQueue;
static twai_hal_context_t *expectedHal;
static TickType_t expectedWait;
static twai_hal_frame_t incoming;
static uint32_t incomingBoundary;
static uint8_t *payload;
#define portENTER_CRITICAL(lock) do { assert((lock)!=NULL); ++locks; } while(0)
#define portEXIT_CRITICAL(lock) do { assert((lock)!=NULL); ++unlocks; } while(0)
#define DRAM_ATTR
#define SOC_TWAI_CONTROLLER_NUM 3
''' + boundary_types + r'''
static int xQueueReceive(void *queue, void *frame, TickType_t wait) {
 assert(queue==expectedQueue && wait==expectedWait); ++receives;
 if(queueOk) { p4_twai_rx_item_t item={.frame=incoming,.boundary=incomingBoundary}; memcpy(frame,&item,sizeof(item)); }
 return queueOk;
}
static void twai_hal_parse_frame(twai_hal_context_t *hal, twai_hal_frame_t *frame,
                                twai_frame_header_t *header,uint8_t *data,uint8_t len) {
 assert(hal==expectedHal && len==8 && data==payload); ++parses; *header=frame->header;
 if(!header->rtr) { size_t n=header->dlc<8?header->dlc:8; memcpy(data,frame->data,n); }
}
static void *checked_memset(void *pointer,int value,size_t size) {
 uintptr_t address=(uintptr_t)pointer, start=(uintptr_t)payload;
 ++zeroWrites;
 if(address<start || address>start+8 || size>8 || size>start+8-address) {
   ++unsafeWrites; return pointer; /* Never execute the SDK's underflow write. */
 }
 return memset(pointer,value,size);
}
#undef memset
#define memset checked_memset
'''
fixture += receive + r'''
#undef memset
int main(void) {
 unsigned cases=0;
 for(unsigned bus=0;bus<3;bus++) for(unsigned dlc=0;dlc<16;dlc++) for(unsigned flags=0;flags<4;flags++) {
  struct { uint64_t before; twai_message_t message; uint64_t after; } box;
  memset(&box,0xa5,sizeof(box));
  uint64_t before=box.before, after=box.after;
  payload=box.message.data;
  twai_hal_context_t hal={(int)bus}; int queue=0;
  twai_obj_t driver={&hal,&queue,17,0,(int)bus};
  s_p4_rx_boundary[bus].delivered=11;incomingBoundary=23;
  expectedHal=&hal; expectedQueue=&queue; expectedWait=37;
  incoming.header=(twai_frame_header_t){flags&1?0x1fffffff:0x7ff,(uint8_t)dlc,flags&1,flags&2};
  for(unsigned i=0;i<8;i++) incoming.data[i]=(uint8_t)(0x30+i);
  receives=parses=locks=unlocks=0; unsafeWrites=zeroWrites=0;queueOk=1;
  esp_err_t result=twai_receive_v2(&driver,&box.message,37);
  assert(unsafeWrites==0 && "invalid DLC reached an unsafe native memset");
  assert(result==(dlc>8?ESP_ERR_INVALID_SIZE:ESP_OK));
  assert(driver.rx_msg_count==16 && receives==1 && parses==1 && locks==1 && unlocks==1);
  assert(box.before==before && box.after==after);
  assert(s_p4_rx_boundary[bus].delivered==23);
  assert(box.message.identifier==incoming.header.id && box.message.data_length_code==dlc);
  assert((box.message.flags&3)==flags && (box.message.flags&~3u)==(0xa5a5a5a5u&~3u));
  assert(zeroWrites==(dlc>8?0u:1u));
  for(unsigned i=0;i<8;i++) {
   uint8_t want=(dlc<=8 && i>=dlc)?0:(!(flags&2)?(uint8_t)(0x30+i):0xa5);
   assert(box.message.data[i]==want);
  }
  twai_message_t snapshot=box.message;
  queueOk=0; receives=parses=locks=unlocks=0;
  assert(twai_receive_v2(&driver,&box.message,37)==ESP_ERR_TIMEOUT);
  assert(memcmp(&snapshot,&box.message,sizeof(snapshot))==0 && driver.rx_msg_count==16);
  assert(receives==1 && parses==0 && locks==0 && unlocks==0);
  assert(s_p4_rx_boundary[bus].delivered==23);
  receives=0;
  assert(twai_receive_v2(NULL,&box.message,37)==ESP_ERR_INVALID_ARG);
  assert(twai_receive_v2(&driver,NULL,37)==ESP_ERR_INVALID_ARG);
  assert(receives==0 && memcmp(&snapshot,&box.message,sizeof(snapshot))==0);
  ++cases;
 }
 printf("PASS: %u native RX bus/DLC/EXT/RTR cases plus timeout/null boundaries; canaries and zero-fill bounds intact\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='p4-native-rx-') as directory:
    temp = Path(directory)
    (temp / 'native.c').write_text(fixture)
    subprocess.run([os.environ.get('CC', '/usr/bin/cc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', str(temp / 'native.c'), '-o', str(temp / 'native')], check=True)
    subprocess.run([str(temp / 'native')], check=True)

# Execute the actual ISR FIFO drain. A successful hardware read is captured
# before queue admission; malformed DLC must not enter the parser.
def extract(marker):
    begin = source.index(marker)
    return source[begin:source.index('\n}', begin)+2]
helper = (extract('static inline void p4_twai_capture_rx(')
          if 'static inline void p4_twai_capture_rx(' in source else '')
boundary = '\n'.join(extract(marker) for marker in (
    'static uint32_t p4_twai_boundary_advance(',
    'static void p4_twai_boundary_reset(',
    'static uint32_t p4_twai_boundary_observe(',
    'static bool p4_twai_periodic_ready_locked('))
# The drain has a forward declaration; select its definition independently.
begin = source.index('static void p4_twai_rx_drain(', source.index('static inline void p4_twai_capture_rx('))
drain = source[begin:source.index('\n}', begin)+2]
isr = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#define IRAM_ATTR
#define DRAM_ATTR
#define SOC_TWAI_CONTROLLER_NUM 3
#define SOC_TWAI_SUPPORTS_RX_STATUS 1
typedef int BaseType_t;
typedef int esp_err_t;
typedef unsigned TickType_t;
enum {ESP_OK=0,ESP_ERR_INVALID_ARG=0x102,ESP_ERR_INVALID_SIZE=0x104,ESP_ERR_TIMEOUT=0x107,
 TWAI_FRAME_MAX_LEN=8,pdTRUE=1,TWAI_ALERT_RX_DATA=1,TWAI_ALERT_RX_QUEUE_FULL=2,TWAI_ALERT_RX_FIFO_OVERRUN=3};
typedef struct { union { struct { uint32_t extd:1,rtr:1,ss:1,self:1,dlc_non_comp:1,reserved:27; }; uint32_t flags; };
 uint32_t identifier; uint8_t data_length_code; uint8_t data[8]; } twai_message_t;
typedef struct {uint32_t id;uint8_t dlc;bool ide,rtr;} twai_frame_header_t;
typedef struct {uint8_t dlc;twai_frame_header_t header;uint8_t data[8];} twai_hal_frame_t;
typedef struct {int unused;} twai_hal_context_t;
typedef struct {twai_hal_context_t *hal;int controller_id;void *rx_queue;int rx_msg_count,rx_missed_count,rx_overrun_count,spinlock;} twai_obj_t;
typedef twai_obj_t* twai_handle_t;
#define TWAI_CHECK(cond, ret_val) do { if (!(cond)) return ret_val; } while(0)
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
''' + boundary_types + r'''
static twai_hal_frame_t incoming;
static p4_twai_rx_item_t queued[8];
static unsigned head,tail;
static int reads,parses,captures,queueCalls,enabled=1,readOk=1,queueOk=1,isrSends,taskSends;
static unsigned invalids;
bool p4TwaiDiagRxCaptureEnabledFromIsr(uint8_t bus) {return bus==1&&enabled;}
void p4TwaiDiagRxFromIsr(uint8_t bus,uint32_t id,uint8_t dlc,uint8_t flags,const uint8_t *data) {
 assert(bus==1&&reads==1&&queueCalls==0);++captures;
 if(dlc>8){++invalids;assert(data==NULL);return;}
 assert(id==incoming.header.id && flags==((incoming.header.ide?1:0)|(incoming.header.rtr?2:0)));
 for(unsigned i=0;i<8;i++)assert(data[i]==((!incoming.header.rtr&&i<dlc)?incoming.data[i]:0));
}
static unsigned twai_hal_get_rx_msg_count(twai_hal_context_t *h){(void)h;return 1;}
static bool twai_hal_read_rx_fifo(twai_hal_context_t *h,twai_hal_frame_t *f){(void)h;++reads;*f=incoming;return readOk;}
void twai_hal_parse_frame(twai_hal_context_t *h,twai_hal_frame_t *f,twai_frame_header_t *hdr,uint8_t *data,unsigned n){
 (void)h;assert(f->dlc<=8&&n==8);++parses;*hdr=f->header;if(!hdr->rtr)memcpy(data,f->data,hdr->dlc);
}
static int enqueue(void *f){++queueCalls;if(queueOk){assert(tail<8);queued[tail++]=*(p4_twai_rx_item_t*)f;}return queueOk;}
static int xQueueSendFromISR(void *q,void *f,BaseType_t *w){(void)q;assert(w);++isrSends;return enqueue(f);}
static int xQueueSend(void *q,void *f,unsigned wait){(void)q;assert(wait==0);++taskSends;return enqueue(f);}
static int xQueueReceive(void *q,void *f,TickType_t wait){(void)q;(void)wait;if(head==tail)return 0;*(p4_twai_rx_item_t*)f=queued[head++];return pdTRUE;}
static void twai_alert_handler(twai_obj_t *o,int a,int *r){(void)o;(void)a;(void)r;}
'''
isr += boundary + '\n' + helper + '\n' + drain + '\n' + extract('static inline void twai_handle_rx_buffer_frames(') + '\n' + receive + r'''
static void load(twai_obj_t* obj,unsigned id,uint8_t mux,bool from_isr){
 incoming=(twai_hal_frame_t){.dlc=8,.header={id,8,false,false},.data={mux}};
 reads=parses=captures=queueCalls=isrSends=taskSends=0;
 BaseType_t wake=0;int alert=0;
 if(from_isr)twai_handle_rx_buffer_frames(obj,&wake,&alert);
 else p4_twai_rx_drain(obj,NULL,&alert,false);
}
int main(void){
 unsigned cases=0;
 for(unsigned bus=0;bus<3;bus++)for(unsigned dlc=0;dlc<16;dlc++)for(unsigned flags=0;flags<4;flags++)
 for(enabled=0;enabled<2;enabled++)for(readOk=0;readOk<2;readOk++)for(queueOk=0;queueOk<2;queueOk++)
 for(unsigned from_isr=0;from_isr<2;from_isr++){
  twai_hal_context_t hal={0};twai_obj_t obj={&hal,(int)bus,NULL,0,0,0,0};BaseType_t wake=0;int alert=0;
  incoming.dlc=dlc;incoming.header=(twai_frame_header_t){0x123456,(uint8_t)dlc,flags&1,flags&2};
  for(unsigned n=0;n<8;n++)incoming.data[n]=n+1;
  head=tail=0;memset(s_p4_rx_boundary,0,sizeof(s_p4_rx_boundary));
  reads=parses=captures=queueCalls=invalids=isrSends=taskSends=0;
  if(from_isr)twai_handle_rx_buffer_frames(&obj,&wake,&alert);
  else p4_twai_rx_drain(&obj,NULL,&alert,false);
  int wanted=bus==1&&enabled&&readOk;
  assert(captures==wanted && "native successful FIFO RX must reach bounded observer before queue admission");
  assert(parses==(wanted&&dlc<=8)+(readOk&&dlc==8));assert(invalids==(unsigned)(wanted&&dlc>8));
  assert(reads==1&&queueCalls==readOk);assert(obj.rx_msg_count==(readOk&&queueOk));
  assert(isrSends==(readOk&&from_isr)&&taskSends==(readOk&&!from_isr));
  assert(obj.rx_missed_count==(readOk&&!queueOk));assert(obj.rx_overrun_count==!readOk);
  if(readOk&&queueOk)assert(queued[0].boundary==0);++cases;
 }
 // Real observe -> queue token -> receive publication, in both ISR/task drains.
 for(unsigned from_isr=0;from_isr<2;from_isr++){
  twai_hal_context_t hal={0};twai_obj_t obj={&hal,1,NULL,0,0,0,0};twai_message_t message={0};
  enabled=0;readOk=queueOk=1;head=tail=0;memset(s_p4_rx_boundary,0,sizeof(s_p4_rx_boundary));
  load(&obj,0x3FD,2,from_isr);assert(!p4_twai_periodic_ready_locked(&obj));
  assert(twai_receive_v2(&obj,&message,0)==ESP_OK&&p4_twai_periodic_ready_locked(&obj));
  // Unrelated traffic carries no token and cannot undo delivered readiness.
  load(&obj,0x123,0,from_isr);assert(queued[tail-1].boundary==0);
  assert(twai_receive_v2(&obj,&message,0)==ESP_OK&&p4_twai_periodic_ready_locked(&obj));
  // Overflow loses latest MUX2. Delivering an older queued MUX2 must not
  // resynchronize; a subsequent successfully delivered fresh MUX2 must.
  load(&obj,0x3FD,2,from_isr);const uint32_t old=queued[tail-1].boundary;
  queueOk=0;load(&obj,0x3FD,2,from_isr);assert(obj.rx_missed_count==1);
  assert(s_p4_rx_boundary[1].observed!=old&&!p4_twai_periodic_ready_locked(&obj));
  assert(twai_receive_v2(&obj,&message,0)==ESP_OK&&!p4_twai_periodic_ready_locked(&obj));
  queueOk=1;load(&obj,0x3FD,2,from_isr);
  assert(twai_receive_v2(&obj,&message,0)==ESP_OK&&p4_twai_periodic_ready_locked(&obj));
  // HAL overrun is an unknown boundary even when the last known frame was MUX2.
  readOk=0;load(&obj,0x123,0,from_isr);assert(obj.rx_overrun_count==1&&!p4_twai_periodic_ready_locked(&obj));
  readOk=1;load(&obj,0x3FD,2,from_isr);
  assert(twai_receive_v2(&obj,&message,0)==ESP_OK&&p4_twai_periodic_ready_locked(&obj));
  // Lifecycle reset and rollover skip the zero/no-boundary token.
  p4_twai_boundary_reset(&obj);assert(!p4_twai_periodic_ready_locked(&obj)&&s_p4_rx_boundary[1].delivered==0);
  s_p4_rx_boundary[1].observed=UINT32_MAX;load(&obj,0x3FD,2,from_isr);
  assert(queued[tail-1].boundary==1&&twai_receive_v2(&obj,&message,0)==ESP_OK&&p4_twai_periodic_ready_locked(&obj));
 }
 printf("PASS: %u ISR/task RX observation/decode/queue cases plus real boundary delivery, overflow, overrun and recovery\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='p4-native-rx-isr-') as directory:
    temp=Path(directory)
    (temp/'native.c').write_text(isr)
    subprocess.run([os.environ.get('CC','/usr/bin/cc'),'-std=c11','-Wall','-Wextra','-Werror',str(temp/'native.c'),'-o',str(temp/'native')],check=True)
    subprocess.run([str(temp/'native')],check=True)
