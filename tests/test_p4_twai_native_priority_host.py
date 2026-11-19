"""Run production native scheduling functions with deterministic queue/HAL fakes."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'p4_twai_driver.c').read_text()
def function(name):
    start = source.index(name)
    start = source.rfind('\n', 0, start) + 1
    return source[start:source.index('\n}', start) + 2]

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "p4_twai_diag.h"
typedef int esp_err_t;
typedef unsigned TickType_t;
typedef int BaseType_t;
enum { ESP_OK=0,ESP_FAIL=-1,ESP_ERR_INVALID_ARG=2,ESP_ERR_INVALID_STATE=3,ESP_ERR_NOT_SUPPORTED=4,ESP_ERR_TIMEOUT=5,
 pdTRUE=1,pdFALSE=0,TWAI_FRAME_MAX_DLC=8,TWAI_MODE_NORMAL=0,TWAI_MODE_LISTEN_ONLY=1,
 TWAI_STATE_RUNNING=1,TWAI_STATE_STOPPED=2,TWAI_STATE_BUS_OFF=3,TWAI_STATE_RECOVERING=4,
 TWAI_HAL_STATE_FLAG_BUS_OFF=1,TWAI_HAL_STATE_FLAG_RUNNING=2,TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED=4,
 TWAI_ALERT_TX_SUCCESS=1,TWAI_ALERT_TX_FAILED=2,TWAI_ALERT_TX_IDLE=4,
 TWAI_ALERT_RX_DATA=32,TWAI_ALERT_RX_QUEUE_FULL=64,TWAI_ALERT_RX_FIFO_OVERRUN=128,TWAI_FRAME_MAX_LEN=8,ESP_ERR_INVALID_SIZE=9,SOC_TWAI_CONTROLLER_NUM=3 };
#define DRAM_ATTR
#define TWAI_CHECK(c,r) do { if(!(c)) return r; } while(0)
typedef struct { uint32_t identifier; uint8_t data_length_code; uint8_t data[8]; bool extd,rtr,ss,self,dlc_non_comp; } twai_message_t;
typedef struct { uint32_t id; uint8_t dlc; bool ide,rtr; } twai_frame_header_t;
typedef struct { twai_frame_header_t header; uint8_t data[8]; uint8_t dlc; } twai_hal_frame_t;
typedef struct { struct { twai_frame_header_t *header; uint8_t *buffer; unsigned buffer_len; } frame;
 struct { int retry_cnt; bool loopback; } config; } twai_hal_trans_desc_t;
typedef struct { unsigned flags; twai_hal_frame_t sent[64]; unsigned n; void *dev; twai_hal_frame_t fifo[16]; unsigned rxN,rxReads,readsAtR79Load; bool overrun; } twai_hal_context_t;
typedef struct { twai_hal_frame_t f[16]; unsigned n,cap; uint32_t tokens[16]; unsigned char extras[16][40]; bool rx; } Queue;
typedef struct twai_obj_t { int controller_id; twai_hal_context_t *hal; Queue *tx_queue,*rx_queue;
 int tx_msg_count,rx_msg_count,state,mode,spinlock; unsigned tx_failed_count,bus_error_count,arb_lost_count,rx_missed_count,rx_overrun_count; void *alert_semphr,*isr_handle; } twai_obj_t;
typedef twai_obj_t *twai_handle_t;
static unsigned lockDepth, nowMs, ticks, diagDepth;
static unsigned taskSignals,isrSignals,isrYields,rxDataAlerts,rxFullAlerts,rxOverrunAlerts;
static uint64_t fineUs;
static size_t rxExtraBytes=sizeof(uint32_t);
void diagFakeEnter(void) { assert(diagDepth==0); ++diagDepth; }
void diagFakeExit(void) { assert(diagDepth==1); --diagDepth; }
static void (*delayHook)(void);
static void (*timerHook)(void);
static void (*queueSendHook)(void);
#define portENTER_CRITICAL(p) do { (void)(p); assert(lockDepth==0); ++lockDepth; } while(0)
#define portEXIT_CRITICAL(p) do { (void)(p); assert(lockDepth==1); --lockDepth; } while(0)
static TickType_t xTaskGetTickCount(void) { return ticks; }
static void vTaskDelay(TickType_t t) { assert(!lockDepth); ticks+=t; nowMs+=t; if(delayHook) delayHook(); }
int64_t esp_timer_get_time(void) { if(timerHook){void (*hook)(void)=timerHook;timerHook=NULL;hook();}return (int64_t)nowMs*1000+fineUs; }
static int xQueueSend(Queue *q,const void *f,TickType_t wait) {
 assert(lockDepth==1 && wait==0); if(q->n==q->cap)return 0; q->f[q->n]=*(const twai_hal_frame_t*)f;
 if(q->rx)memcpy(&q->tokens[q->n],(const char*)f+sizeof(twai_hal_frame_t),sizeof(uint32_t));
 if(q->rx)memcpy(q->extras[q->n],(const char*)f+sizeof(twai_hal_frame_t),rxExtraBytes);
 ++q->n;if(q->rx && queueSendHook){void (*hook)(void)=queueSendHook;queueSendHook=NULL;hook();}return 1;
}
static int xQueueReceive(Queue *q,void *f,TickType_t wait) {
 (void)wait;if(!q->n)return 0; *(twai_hal_frame_t*)f=q->f[0];
 if(q->rx)memcpy((char*)f+sizeof(twai_hal_frame_t),&q->tokens[0],sizeof(uint32_t));
 if(q->rx)memcpy((char*)f+sizeof(twai_hal_frame_t),q->extras[0],rxExtraBytes);
 memmove(q->extras,q->extras+1,(q->n-1)*sizeof(q->extras[0]));
 memmove(q->f,q->f+1,--q->n*sizeof(q->f[0]));memmove(q->tokens,q->tokens+1,q->n*sizeof(q->tokens[0]));return 1;
}
static int xQueueReceiveFromISR(Queue *q,void *f,BaseType_t *w) { (void)w; return xQueueReceive(q,f,0); }
static int xQueueSendFromISR(Queue *q,const void *f,BaseType_t *w) { int sent=xQueueSend(q,f,0);if(sent&&w)*w=pdTRUE;return sent; }
static unsigned uxQueueMessagesWaiting(Queue *q) { return q->n; }
static void xQueueReset(Queue *q) { q->n=0; }
static bool twai_hal_check_state_flags(twai_hal_context_t *h,unsigned f) { return (h->flags&f)!=0; }
static void twai_hal_set_tx_buffer_and_transmit(twai_hal_context_t *h,const twai_hal_frame_t *f,int v) {
 if(f->header.id==0x3FD)h->readsAtR79Load=h->rxReads;
 (void)v; assert(!(h->flags&4)); assert(h->flags&2); h->flags|=4; h->sent[h->n++]=*f;
}
static void twai_hal_parse_frame(twai_hal_context_t *h,twai_hal_frame_t *f,twai_frame_header_t *out,uint8_t *data,uint8_t len) {
 (void)h;*out=f->header;if(!out->rtr)memcpy(data,f->data,out->dlc<len?out->dlc:len);
}
static void twai_hal_format_frame(twai_hal_trans_desc_t *d,twai_hal_frame_t *f) { f->header=*d->frame.header;f->dlc=f->header.dlc;memcpy(f->data,d->frame.buffer,8); }
static uint32_t twai_hal_get_rx_msg_count(twai_hal_context_t *h) { return h->rxN; }
static bool twai_hal_read_rx_fifo(twai_hal_context_t *h,twai_hal_frame_t *f) {
 assert(h->rxN);++h->rxReads;*f=h->fifo[0];memmove(h->fifo,h->fifo+1,--h->rxN*sizeof(h->fifo[0]));return !h->overrun;
}
static void xSemaphoreGive(void *s) { (void)s;assert(!lockDepth);++taskSignals; }
static void twai_hal_start(twai_hal_context_t *h) { h->flags=2; }
static void twai_hal_stop(twai_hal_context_t *h) { h->flags=0; }
static void twai_hal_start_bus_recovery(twai_hal_context_t *h) { h->flags=0; }
static void twai_alert_handler(twai_obj_t *o,unsigned a,int *r) {
 (void)o;*r=1;if(a==TWAI_ALERT_RX_DATA)++rxDataAlerts;
 if(a==TWAI_ALERT_RX_QUEUE_FULL)++rxFullAlerts;if(a==TWAI_ALERT_RX_FIFO_OVERRUN)++rxOverrunAlerts;
}
'''
header = (ROOT / 'p4_twai_priority.h').read_text()
# The added fixture field allows a behavioral RED against the predecessor,
# whose production guard ignores the new dynamic permission input.
if 'permission_deadline_ms' not in header:
    header = header.replace('} p4_twai_priority_guard_t;',
                            'const volatile uint32_t *permission_deadline_ms;\n} p4_twai_priority_guard_t;')
if 'preserve_pending' not in header:
    header = header.replace('} p4_twai_priority_guard_t;',
                            'bool preserve_pending;\n} p4_twai_priority_guard_t;')
# Fixture-only optional fields allow assertion RED before the native guard
# understands AP-retry revocation; no missing symbol/compile failure is RED.
if 'expected_retry_generation' not in header:
    header = header.replace('} p4_twai_priority_guard_t;',
                            'const volatile uint32_t *retry_generation;\nuint32_t expected_retry_generation;\n} p4_twai_priority_guard_t;')
fixture += header[header.index('typedef struct '):header.index('// Zero-wait')]
new_api = 'esp_err_t p4_twai_transmit_r79_v2(' in source
if new_api:
    start = source.index('// Native RX epochs') if '// Native RX epochs' in source else source.index('// P4 R79 priority state')
    end = source.index('/* -------------------- Sleep Retention', start)
    fixture += ('#define P4_BOUNDARY_FIXTURE 1\n' if '// Native RX epochs' in source else '') + source[start:end]
if 'p4_twai_boundary_observe(' not in source:
    fixture += r'''
static uint32_t p4_twai_boundary_observe(twai_obj_t *o,twai_hal_frame_t *f) { (void)o;(void)f;return 0; }
'''
if 'static void p4_twai_rx_drain(' in source:
    fixture += '\n#define SOC_TWAI_SUPPORTS_RX_STATUS 1\n'
    fixture += function('static inline void p4_twai_capture_rx(')
    # Skip forward declaration; extract the definition after capture helper.
    begin = source.index('static void p4_twai_rx_drain(', source.index('static inline void p4_twai_capture_rx('))
    fixture += source[begin:source.index('\n}', begin)+2]
    fixture += function('static inline void twai_handle_rx_buffer_frames(')
    fixture += function('static void p4_twai_dispatch_idle(')
    fixture += function('bool p4_twai_r79_periodic_ready_v2(')
    fixture += function('esp_err_t twai_receive_v2(')
    if 'bool p4_twai_r79_input_current_v2(' in source:
        fixture += '\n#define P4_RX_INPUT_FIXTURE 1\n'
        for name in ('bool p4_twai_r79_input_current_v2(', 'void p4_twai_r79_input_done_v2(', 'bool p4_twai_rx_metadata_v2('):
            fixture += function(name)
    else:
        fixture += 'static bool p4_twai_r79_input_current_v2(twai_handle_t h,uint32_t s){(void)h;(void)s;return true;}\n'

    fixture += function('esp_err_t twai_clear_receive_queue_v2(')
else:
    fixture += 'static void twai_handle_rx_buffer_frames(twai_obj_t *d,BaseType_t *w,int *a) { (void)d;(void)w;(void)a; }\n'
fixture += function('static inline void twai_handle_tx_buffer_frame(')
fixture += r'''
#define portENTER_CRITICAL_ISR portENTER_CRITICAL
#define portEXIT_CRITICAL_ISR portEXIT_CRITICAL
#define portYIELD_FROM_ISR() do {++isrYields;} while(0)
enum { TWAI_HAL_EVENT_RX_BUFF_FRAME=1, TWAI_HAL_EVENT_TX_BUFF_FREE=2,TWAI_HAL_EVENT_TX_SUCCESS=4,
 TWAI_HAL_EVENT_BUS_OFF=8,TWAI_HAL_EVENT_BUS_RECOV_CPLT=16,TWAI_HAL_EVENT_BUS_ERR=32,
 TWAI_HAL_EVENT_ARB_LOST=64,TWAI_HAL_EVENT_BUS_RECOV_PROGRESS=128,TWAI_HAL_EVENT_ERROR_PASSIVE=256,
 TWAI_HAL_EVENT_ERROR_ACTIVE=512,TWAI_HAL_EVENT_ERROR_WARNING=1024,TWAI_HAL_EVENT_BELOW_EWL=2048,
 TWAI_ALERT_BUS_OFF=10,TWAI_ALERT_BUS_RECOVERED=11,TWAI_ALERT_BUS_ERROR=12,TWAI_ALERT_ARB_LOST=13,
 TWAI_ALERT_RECOVERY_IN_PROGRESS=14,TWAI_ALERT_ERR_PASS=15,TWAI_ALERT_ERR_ACTIVE=16,
 TWAI_ALERT_ABOVE_ERR_WARN=17,TWAI_ALERT_BELOW_ERR_WARN=18 };
static uint32_t events;
static bool captureError;
static uint32_t twai_hal_get_events(twai_hal_context_t *h) {
 if(captureError) p4TwaiDiagRecordFromIsr(0,0xA5,0x41,7,8,h->flags);
 if(events&TWAI_HAL_EVENT_TX_BUFF_FREE)h->flags&=~4u;
 if(events&TWAI_HAL_EVENT_BUS_OFF)h->flags|=1u;
 return events;
}
static void twai_ll_set_mode(void *dev,bool a,bool b,bool c) { (void)dev;(void)a;(void)b;(void)c; }
static void twai_ll_enter_reset_mode(void *dev) { (void)dev; }
static void xSemaphoreGiveFromISR(void *s,BaseType_t *w) { (void)s;(void)w;assert(!lockDepth);++isrSignals; }
'''
fixture += function('static void twai_intr_handler_main(')
fixture += r'''
static twai_handle_t g_twai_objs[SOC_TWAI_CONTROLLER_NUM];
static int g_spinlock;
#define ESP_ERROR_CHECK(c) assert((c)==ESP_OK)
#define TWAI_PERI_ATOMIC()
#define TWAI_RCC_ATOMIC()
static esp_err_t esp_intr_disable(void *h) { (void)h; return ESP_OK; }
static void twai_hal_deinit(twai_hal_context_t *h) { h->flags=0; }
static void twai_ll_enable_clock(int c,bool v) { (void)c;(void)v; }
static void twai_ll_enable_bus_clock(int c,bool v) { (void)c;(void)v; }
static void twai_release_gpio(twai_obj_t *o) { (void)o; }
static void twai_free_driver_obj(twai_obj_t *o) { (void)o; }
'''
fixture += function('esp_err_t twai_driver_uninstall_v2(')


for name in ('twai_start_v2(', 'twai_stop_v2(', 'twai_transmit_v2(', 'twai_initiate_recovery_v2(', 'twai_clear_transmit_queue_v2('):
    fixture += function('esp_err_t '+name)
if new_api:
    fixture += function('esp_err_t p4_twai_transmit_r79_v2(')
else:
    fixture += r'''
static esp_err_t p4_twai_transmit_r79_v2(twai_handle_t h,const twai_message_t *m,const p4_twai_priority_guard_t *g) {
 (void)g; return twai_transmit_v2(h,m,0);
}
'''
# Until the production API is added, run the predecessor's ordinary admission
# so the RED boundary is a real accepted-stale-frame assertion, not compilation.
if 'esp_err_t p4_twai_transmit_mux1_now_v2(' in source:
    fixture += function('esp_err_t p4_twai_transmit_mux1_now_v2(')
else:
    fixture += '''
esp_err_t p4_twai_transmit_mux1_now_v2(twai_handle_t h,const twai_message_t *m) {
 return twai_transmit_v2(h,m,0);
}
'''
runtime = (ROOT/'can_runtime.h').read_text()
if 'static void r79ServiceCheckpoint()' in runtime:
    start = runtime.index('static void r79ServiceCheckpoint()')
    checkpoint = runtime[start:runtime.index('\n}', start)+2]
else:
    start = runtime.index('if (r79ServiceStateRefreshTry())', runtime.index('static void canTaskTwai('))
    checkpoint = 'static void r79ServiceCheckpoint(){' + runtime[start:runtime.index(';', start)+1] + '}'
fixture += '''
static twai_obj_t *checkpointDriver;
static bool checkpointRefresh=false;
static unsigned checkpointAdmissions;
static twai_handle_t p4CanHandleB(void){return checkpointDriver;}
static bool r79ServiceStateRefreshTry(void){return checkpointRefresh;}
static void r79TransportSliceTick(bool ready){(void)ready;checkpointAdmissions++;}
''' + checkpoint + '\n'
fixture += r'''
static volatile uint32_t generation=1,cancel=2,permissionDeadline=20,retryGeneration=7;
static volatile bool hold=false;
static p4_twai_priority_guard_t guard;
static twai_message_t normal={.identifier=0x111,.data_length_code=8}, priority={.identifier=0x3FD,.data_length_code=8,.data={1}};
static void finish(twai_obj_t *d) {
 assert(d->hal->flags&4);
 events=TWAI_HAL_EVENT_TX_BUFF_FREE|TWAI_HAL_EVENT_TX_SUCCESS;twai_intr_handler_main(d);
}
static void init(twai_obj_t *d,twai_hal_context_t *h,Queue *q,Queue *r,int id) {
 queueSendHook=NULL;
 taskSignals=isrSignals=isrYields=rxDataAlerts=rxFullAlerts=rxOverrunAlerts=0;
 fineUs=0;
 rxExtraBytes=sizeof(p4_twai_rx_item_t)-sizeof(twai_hal_frame_t);
 assert(rxExtraBytes<=40);
 if(id==0)p4TwaiDiagInit(99);
 *h=(twai_hal_context_t){0};*q=(Queue){.cap=8};*r=(Queue){.cap=8,.rx=true};
 *d=(twai_obj_t){.controller_id=id,.hal=h,.tx_queue=q,.rx_queue=r,.state=TWAI_STATE_STOPPED};
 assert(twai_start_v2(d)==ESP_OK);
#ifdef P4_BOUNDARY_FIXTURE
 twai_hal_frame_t mux2={.header={.id=0x3FD,.dlc=8},.data={2},.dlc=8};
 s_p4_rx_boundary[id].delivered=p4_twai_boundary_observe(d,&mux2);
#endif
 generation=1;cancel=2;retryGeneration=7;hold=false;nowMs=10;
 guard=(p4_twai_priority_guard_t){.generation=&generation,.expected_generation=1,
 .cancel_generation=&cancel,.expected_cancel_generation=2,.administrative_hold=&hold,.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE};
}
static twai_hal_frame_t rxFrame(uint32_t id,uint8_t mux) {
 twai_hal_frame_t f={.header={.id=id,.dlc=8},.dlc=8};f.data[0]=mux;return f;
}
static void halRx(twai_obj_t *d,twai_hal_frame_t f) { assert(d->hal->rxN<16);d->hal->fifo[d->hal->rxN++]=f; }
static void irqRx(twai_obj_t *d,twai_hal_frame_t f) { halRx(d,f);events=TWAI_HAL_EVENT_RX_BUFF_FRAME;twai_intr_handler_main(d); }
static void dequeueAll(twai_obj_t *d) { twai_message_t m;while(twai_receive_v2(d,&m,0)==ESP_OK){} }
static twai_obj_t *hookDriver;
static int revokeKind;
static unsigned lateId=0x3FD;
static void appendDuringDrain(void) { halRx(hookDriver,rxFrame(lateId,2)); }
static unsigned admissionClockReads;
static void appendAtRequestIdentity(void) {
 if(++admissionClockReads==2){halRx(hookDriver,rxFrame(0x123,0));queueSendHook=appendDuringDrain;}
 else timerHook=appendAtRequestIdentity;
}

static void revokeDuringRenewal(void) {
 permissionDeadline=100;
 if(revokeKind==0)generation++;if(revokeKind==1)cancel++;if(revokeKind==2)hold=true;if(revokeKind==3)retryGeneration++;
}
static void revokeRetryAtRequestIdentity(void) {
 if(++admissionClockReads==2)retryGeneration++;
 else timerHook=revokeRetryAtRequestIdentity;
}
static void admitDuringWait(void) { delayHook=NULL;assert(p4_twai_transmit_r79_v2(hookDriver,&priority,&guard)==ESP_OK); }
int main(void) {
 twai_obj_t d,b;twai_hal_context_t h,hb;Queue q,r,qb,rb;
 // An origin tag is metadata, not an IMMEDIATE RX fence. Observe the real HAL
 // register-write boundary without assigning artificial time to RX reads.
 unsigned orderingCases=0;
 const unsigned rxSizes[]={0,1,8};
 for(unsigned busy=0;busy<2;++busy)for(unsigned tagged=0;tagged<2;++tagged)for(unsigned k=0;k<3;++k){
  init(&d,&h,&q,&r,0);d.alert_semphr=&d;guard.rx_sequence=tagged?123:0;
  if(busy){
   assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);normal.identifier=0x111;
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  }
  h.rxReads=0;h.readsAtR79Load=UINT32_MAX;
  taskSignals=isrSignals=isrYields=rxDataAlerts=0;
  for(unsigned n=0;n<rxSizes[k];++n){twai_hal_frame_t f=rxFrame(0x123,0);f.data[7]=(uint8_t)n;halRx(&d,f);}
  if(busy)finish(&d);else assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  assert(h.readsAtR79Load==0 && "unrelated HAL RX must not precede authorized IMMEDIATE load");
  assert(h.n==(busy?2:1)&&h.sent[h.n-1].header.id==0x3FD&&!s_p4_priority[0].pending);
  assert(d.tx_msg_count==(busy?2:1)&&q.n==busy);
  if(tagged){
   assert(h.rxReads==rxSizes[k]&&h.rxN==0&&r.n==rxSizes[k]&&d.rx_msg_count==(int)rxSizes[k]);
   assert(rxDataAlerts==rxSizes[k]);
   if(busy)assert(isrSignals==1&&isrYields==(rxSizes[k]!=0)&&taskSignals==0);
   else assert(taskSignals==(rxSizes[k]!=0)&&isrSignals==0&&isrYields==0);
  }else{
   assert(h.rxReads==0&&h.rxN==rxSizes[k]&&r.n==0);
   events=TWAI_HAL_EVENT_RX_BUFF_FRAME;twai_intr_handler_main(&d);
  }
  assert(h.rxReads==rxSizes[k]&&h.rxN==0&&r.n==rxSizes[k]&&d.rx_missed_count==0&&d.rx_overrun_count==0);
  for(unsigned n=0;n<rxSizes[k];++n){twai_message_t got;assert(twai_receive_v2(&d,&got,0)==ESP_OK&&got.identifier==0x123&&got.data[7]==n);}
  assert(d.rx_msg_count==0&&r.n==0);finish(&d);
  if(busy){assert(h.sent[h.n-1].header.id==0x222);finish(&d);}
  assert(d.tx_msg_count==0&&q.n==0);++orderingCases;
 }
 assert(orderingCases==12);
 // Existing protected PERIODIC ownership must see a fresh HAL boundary before
 // IMMEDIATE admission, regardless of whether the incoming request has a tag.
 for(unsigned tagged=0;tagged<2;++tagged)for(unsigned changed=0;changed<5;++changed){
  init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);normal.identifier=0x111;
  guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;guard.preserve_pending=true;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  const uint32_t protectedId=s_p4_priority[0].request.requestId;
  if(changed==4)h.overrun=true;
  halRx(&d,rxFrame(changed>0&&changed<4?0x3FD:0x123,(uint8_t)(changed-1)));
  guard.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE;guard.preserve_pending=false;guard.rx_sequence=tagged?123:0;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==(changed?ESP_OK:ESP_ERR_TIMEOUT));
  assert(h.rxN==0&&r.n==(changed==4?0:1)&&h.n==1&&q.n==1&&d.tx_msg_count==3);
  assert(d.rx_overrun_count==(changed==4));h.overrun=false;
  assert(s_p4_priority[0].pending&&s_p4_priority[0].request.requestId==(changed?protectedId+1:protectedId));
  assert(s_p4_priority[0].guard.source==(changed?P4_TWAI_TX_SOURCE_R79_IMMEDIATE:P4_TWAI_TX_SOURCE_R79_PERIODIC));
  P4TwaiErrorSnapshot fenced;assert(p4TwaiDiagSnapshot(&fenced));
  if(changed)assert(fenced.buses[0].lifecycle.events[1].reason==P4_TWAI_TX_REASON_RX_BOUNDARY);
  finish(&d);assert(h.sent[1].header.id==0x3FD&&q.n==1);finish(&d);finish(&d);
  assert(d.tx_msg_count==0&&q.n==0);
 }
 // Moving tagged RX service after load retains queue-loss/unknown-overrun
 // accounting, alerts and resynchronization, for task and ISR paths.
 for(unsigned busy=0;busy<2;++busy)for(unsigned loss=0;loss<2;++loss){
  init(&d,&h,&q,&r,0);d.alert_semphr=&d;guard.rx_sequence=123;
  if(busy){assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);}
  if(loss==0)r.cap=0;else h.overrun=true;
  halRx(&d,rxFrame(0x123,0));taskSignals=isrSignals=isrYields=0;
  if(busy)finish(&d);else assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  assert(h.readsAtR79Load==0&&h.rxReads==1&&h.rxN==0&&r.n==0&&d.rx_msg_count==0);
  assert(d.rx_missed_count==(loss==0)&&d.rx_overrun_count==(loss==1));
  assert(rxFullAlerts==(loss==0)&&rxOverrunAlerts==(loss==1)&&isrYields==0);
  assert(busy?(isrSignals==1&&taskSignals==0):(taskSignals==1&&isrSignals==0));
  if(loss==1)assert(!p4_twai_r79_periodic_ready_v2(&d));
  h.overrun=false;r.cap=8;irqRx(&d,rxFrame(0x3FD,2));dequeueAll(&d);assert(p4_twai_r79_periodic_ready_v2(&d));
  finish(&d);assert(d.tx_msg_count==0);
 }
 // Actual combined RX/TX events retain their RX-first classification and wake
 // once. HAL-only RX is the optimized ordering case, not a change to IRQ order.
 init(&d,&h,&q,&r,0);d.alert_semphr=&d;guard.rx_sequence=123;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 halRx(&d,rxFrame(0x123,0));isrSignals=isrYields=0;
 events=TWAI_HAL_EVENT_RX_BUFF_FRAME|TWAI_HAL_EVENT_TX_BUFF_FREE|TWAI_HAL_EVENT_TX_SUCCESS;twai_intr_handler_main(&d);
 assert(h.readsAtR79Load==1&&h.n==2&&r.n==1&&d.tx_msg_count==1&&isrSignals==1&&isrYields==1);
 finish(&d);assert(d.tx_msg_count==0);
 // Guard rejection and hardware BUS OFF still drain tagged RX and notify the
 // consumer, without loading either direct or previously accepted work.
 for(unsigned pending=0;pending<2;++pending)for(unsigned deny=0;deny<6;++deny){
  init(&d,&h,&q,&r,0);d.alert_semphr=&d;guard.rx_sequence=123;
  guard.retry_generation=&retryGeneration;guard.expected_retry_generation=retryGeneration;
  guard.has_deadline=true;guard.deadline_ms=20;
  if(pending){assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);}
  halRx(&d,rxFrame(0x123,0));taskSignals=isrSignals=isrYields=0;
  if(deny==0)hold=true;if(deny==1)generation++;if(deny==2)cancel++;if(deny==3)retryGeneration++;
  if(deny==4)nowMs=21;if(deny==5)h.flags|=TWAI_HAL_STATE_FLAG_BUS_OFF;
  if(pending){events=TWAI_HAL_EVENT_TX_BUFF_FREE|TWAI_HAL_EVENT_TX_SUCCESS|(deny==5?TWAI_HAL_EVENT_BUS_OFF|TWAI_HAL_EVENT_RX_BUFF_FRAME:0);twai_intr_handler_main(&d);}
  else assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE);
  assert(h.n==(pending?1:0)&&h.rxN==0&&r.n==1&&d.rx_msg_count==1);
  assert(!s_p4_priority[0].pending&&d.tx_msg_count==0);
  assert(pending?(isrSignals==1&&isrYields==1):(taskSignals==1&&isrSignals==0));
 }
 puts("PASS native RX order: 12 load-order cases, 10 protected periodic fences, 4 RX-loss cases, 1 combined IRQ, 12 guard/BUS-OFF controls");
 // AP-only retry authority is separate from the general bypass gate. Its
 // generation revokes pending work without disturbing active TX or FIFO.
 for(int wrap=0;wrap<2;wrap++)for(int legacy=0;legacy<2;legacy++){
  init(&d,&h,&q,&r,0);retryGeneration=wrap?UINT32_MAX:7;
  guard.retry_generation=legacy?NULL:&retryGeneration;
  guard.expected_retry_generation=retryGeneration;
  normal.identifier=0x111;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x333;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  retryGeneration++; // AP invalidated; a later valid sample keeps this epoch.
  permissionDeadline=100;nowMs=11;
  finish(&d);assert(h.sent[1].header.id==(legacy?0x3FD:0x222));
  if(!legacy){
   P4TwaiErrorSnapshot cancelled;assert(p4TwaiDiagSnapshot(&cancelled));
   assert(cancelled.buses[0].lifecycle.events[1].kind==P4_TWAI_TX_CANCELLED);
   assert(cancelled.buses[0].lifecycle.events[1].reason==P4_TWAI_TX_REASON_CANCEL_GENERATION);
  }else finish(&d);
  assert(h.sent[legacy?2:1].header.id==0x222);
  finish(&d);assert(h.sent[legacy?3:2].header.id==0x333);finish(&d);
  assert(!s_p4_priority[0].pending&&q.n==0&&d.tx_msg_count==0);
  // Neither expiry renewal nor invalid-to-valid restores the captured epoch.
  if(!legacy){
   permissionDeadline=200;
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE);
   assert(h.n==3);
   guard.expected_retry_generation=retryGeneration;
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);finish(&d);
  }
 }
 // Direct admission checks the descriptor again after request bookkeeping.
 init(&d,&h,&q,&r,0);guard.retry_generation=&retryGeneration;guard.expected_retry_generation=7;
 admissionClockReads=0;timerHook=revokeRetryAtRequestIdentity;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE);
 assert(admissionClockReads==2&&h.n==0&&d.tx_msg_count==0&&!s_p4_priority[0].pending);
 // Revoke wins over expiry when both are already invalid.
 guard.has_deadline=true;guard.deadline_ms=0;
 assert(p4_twai_priority_guard_reason(&guard)==P4_TWAI_TX_REASON_CANCEL_GENERATION);
 normal.identifier=0x111;
 // A newer successfully queued MUX1 supersedes application echo A.
 init(&d,&h,&q,&r,0);
 twai_hal_frame_t old=rxFrame(0x3FD,1), latest=rxFrame(0x3FD,1);
 old.data[7]=0xA1;latest.data[7]=0xB2;
 irqRx(&d,old);uint32_t oldSequence=s_p4_rx_boundary[0].observed;
 irqRx(&d,latest);
 twai_message_t got={0};assert(twai_receive_v2(&d,&got,0)==ESP_OK);
 assert(!p4_twai_r79_input_current_v2(&d,oldSequence) && "older queued MUX1 must defer echo to valid newer queued MUX1");
#ifdef P4_RX_INPUT_FIXTURE
 p4_twai_rx_metadata_t meta={0};assert(p4_twai_rx_metadata_v2(&d,&meta));
 assert(meta.sequence==oldSequence && meta.observed_us==10000 && meta.dequeued_us==10000);
 assert(twai_receive_v2(&d,&got,0)==ESP_OK);assert(p4_twai_rx_metadata_v2(&d,&meta));
 assert(p4_twai_r79_input_current_v2(&d,meta.sequence));
 // Only an authorized B replaces pending A while hardware is still busy.
 init(&d,&h,&q,&r,0);irqRx(&d,old);assert(twai_receive_v2(&d,&got,0)==ESP_OK);
 assert(p4_twai_rx_metadata_v2(&d,&meta));
 guard.rx_sequence=meta.sequence;guard.rx_observed_us=meta.observed_us;guard.rx_dequeued_us=meta.dequeued_us;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 priority.data[7]=0xA1;assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 irqRx(&d,latest);assert(h.n==1 && s_p4_priority[0].pending);
 assert(twai_receive_v2(&d,&got,0)==ESP_OK);assert(p4_twai_rx_metadata_v2(&d,&meta));
 guard.rx_sequence=meta.sequence;guard.rx_observed_us=meta.observed_us;guard.rx_dequeued_us=meta.dequeued_us;
 priority.data[7]=0xB2;assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 p4_twai_r79_input_done_v2(&d,meta.sequence);assert(h.n==1 && s_p4_priority[0].pending);
 finish(&d);assert(h.n==2 && h.sent[1].data[7]==0xB2);finish(&d);
 // Completion loads approved A immediately even while newer B is unread.
 init(&d,&h,&q,&r,0);irqRx(&d,old);assert(twai_receive_v2(&d,&got,0)==ESP_OK);
 assert(p4_twai_rx_metadata_v2(&d,&meta));guard.rx_sequence=meta.sequence;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);priority.data[7]=0xA1;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 irqRx(&d,latest);finish(&d);assert(h.n==2 && h.sent[1].data[7]==0xA1 && !s_p4_priority[0].pending);
 assert(twai_receive_v2(&d,&got,0)==ESP_OK);assert(p4_twai_rx_metadata_v2(&d,&meta));
 guard.rx_sequence=meta.sequence;priority.data[7]=0xB2;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 p4_twai_r79_input_done_v2(&d,meta.sequence);
 assert(h.n==2 && h.sent[1].data[7]==0xA1 && s_p4_priority[0].pending);
 finish(&d);assert(h.n==3 && h.sent[2].data[7]==0xB2);finish(&d);

 // No idle handoff delay: protection, failed RX insertion, queue resets and
 // HAL-only newer input retain approved A; revocation still wins before load.
 for(unsigned kind=0;kind<7;++kind){
  init(&d,&h,&q,&r,0);irqRx(&d,old);assert(twai_receive_v2(&d,&got,0)==ESP_OK);
  assert(p4_twai_rx_metadata_v2(&d,&meta));
  guard.rx_sequence=meta.sequence;guard.rx_observed_us=meta.observed_us;guard.rx_dequeued_us=meta.dequeued_us;
  guard.preserve_pending=kind==1;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);priority.data[7]=0xA1;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  if(kind==2)r.cap=0; // unsuccessful enqueue must never obsolete A
  if(kind==6)halRx(&d,latest);else irqRx(&d,latest);
  if(kind==3)hold=true;
  if(kind==4)generation++;
  if(kind==5)assert(twai_clear_receive_queue_v2(&d)==ESP_OK);
  const unsigned beforeTicks=ticks;const uint64_t beforeUs=(uint64_t)esp_timer_get_time();
  finish(&d);
  assert(ticks==beforeTicks && (uint64_t)esp_timer_get_time()==beforeUs);
  if(kind==3||kind==4){assert(h.n==1&&d.tx_msg_count==0&&!s_p4_priority[0].pending);}
  else {assert(h.n==2&&h.sent[1].data[7]==0xA1&&d.tx_msg_count==1&&!s_p4_priority[0].pending);finish(&d);}
 }
 // Direct idle admission loads approved A despite newer queued input.
 init(&d,&h,&q,&r,0);irqRx(&d,old);assert(twai_receive_v2(&d,&got,0)==ESP_OK);
 assert(p4_twai_rx_metadata_v2(&d,&meta));guard.rx_sequence=meta.sequence;
 irqRx(&d,latest);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 assert(h.n==1&&!s_p4_priority[0].pending&&d.tx_msg_count==1);
 assert(h.sent[0].data[7]==0xA1 && nowMs==10 && fineUs==0);finish(&d);
 // A continuous burst cannot restart a native idle timer. Each idle admission
 // loads at its own timestamp, even while five/four/etc. newer inputs queue.
 // Busy hardware still permits latest replacement, without active preemption.
 for(unsigned busy=0;busy<2;++busy){
  init(&d,&h,&q,&r,0);
  if(busy)assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  for(unsigned i=0;i<6;++i){twai_hal_frame_t f=old;f.data[7]=(uint8_t)(0xA0+i);irqRx(&d,f);}
  const unsigned beforeTicks=ticks;
  for(unsigned i=0;i<6;++i){
   fineUs=i*300;
   assert(twai_receive_v2(&d,&got,0)==ESP_OK && p4_twai_rx_metadata_v2(&d,&meta));
   guard.rx_sequence=meta.sequence;guard.rx_observed_us=meta.observed_us;guard.rx_dequeued_us=meta.dequeued_us;
   priority.data[7]=got.data[7];
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
   p4_twai_r79_input_done_v2(&d,meta.sequence);
   assert(ticks==beforeTicks && nowMs==10 && fineUs==i*300);
   if(!busy){
    assert(h.n==i+1 && h.sent[i].data[7]==0xA0+i && !s_p4_priority[0].pending && d.tx_msg_count==1);
    P4TwaiErrorSnapshot burst;assert(p4TwaiDiagSnapshot(&burst));
    const P4TwaiTxIdentity loaded=burst.buses[0].lifecycle.events[burst.buses[0].lifecycle.count-1].tx;
    assert(loaded.loadedUs==10000+i*300 && loaded.rxSequence==meta.sequence);
    finish(&d);assert(d.tx_msg_count==0);
   }else if(i<5){
    assert(h.n==1 && s_p4_priority[0].frame.data[7]==0xA0+i && d.tx_msg_count==2);
    if(i==4){finish(&d);assert(h.n==2 && h.sent[1].data[7]==0xA4 && !s_p4_priority[0].pending);}
   }else{
    assert(h.n==2 && s_p4_priority[0].frame.data[7]==0xA5 && d.tx_msg_count==2);
    finish(&d);assert(h.n==3 && h.sent[2].data[7]==0xA5);finish(&d);
    P4TwaiErrorSnapshot burst;assert(p4TwaiDiagSnapshot(&burst));unsigned replaced=0;
    for(unsigned n=0;n<burst.buses[0].lifecycle.count;++n)
     if(burst.buses[0].lifecycle.events[n].reason==P4_TWAI_TX_REASON_REPLACED)++replaced;
    assert(replaced==4 && d.tx_msg_count==0 && q.n==0);
   }
  }
 }
 // Refresh contention must not let ordinary FIFO leapfrog accepted work, or
 // prevent FIFO resumption after genuine revocation. Residual unclassified
 // periodic RX still requires native progress independent of state refresh.
 for(unsigned revoke=0;revoke<2;++revoke){
  init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  normal.identifier=0x111;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  halRx(&d,rxFrame(0x456,0));hookDriver=&d;lateId=0x456;queueSendHook=appendDuringDrain;
  finish(&d);assert(h.n==1&&q.n==1&&d.tx_msg_count==2&&h.rxN==1);
  if(revoke)hold=true;
  checkpointDriver=&d;checkpointRefresh=false;checkpointAdmissions=0;r79ServiceCheckpoint();assert(checkpointAdmissions==0);
  if(revoke){assert(h.n==2&&h.sent[1].header.id==0x222&&q.n==0&&d.tx_msg_count==1);}
  else {assert(h.n==2&&h.sent[1].header.id==0x3FD&&q.n==1);finish(&d);assert(h.n==3&&h.sent[2].header.id==0x222&&q.n==0);}
 }
 normal.identifier=0x111;
 // RX-origin tags follow queueing, load and completion without reinterpretation.
 init(&d,&h,&q,&r,0);irqRx(&d,old);nowMs=12;
 assert(twai_receive_v2(&d,&got,0)==ESP_OK&&p4_twai_rx_metadata_v2(&d,&meta));
 assert(meta.observed_us==10000&&meta.dequeued_us==12000&&meta.sequence);
 guard.rx_sequence=meta.sequence;guard.rx_observed_us=meta.observed_us;guard.rx_dequeued_us=meta.dequeued_us;
 nowMs=13;assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);finish(&d);
 P4TwaiErrorSnapshot originOut;assert(p4TwaiDiagSnapshot(&originOut));
 for(unsigned i=0;i<3;i++){
  P4TwaiTxIdentity t=originOut.buses[0].lifecycle.events[i].tx;
  assert(t.rxSequence==meta.sequence&&t.rxObservedUs==10000&&t.rxDequeuedUs==12000&&t.queuedUs==13000);
 }
#endif
 init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 priority.data[7]=0xA1;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK && "newest immediate must replace pending native R79");
 finish(&d);assert(h.sent[1].data[7]==0xA1);finish(&d);
 // An accepted one-shot protects its pending payload until dispatch or cancellation.
 for(int previous=2;previous<=3;previous++) {
  init(&d,&h,&q,&r,0);normal.identifier=0x111;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  guard.source=previous;guard.preserve_pending=true;priority.data[4]=0x10;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  const uint32_t protectedId=s_p4_priority[0].request.requestId;
  guard.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE;guard.preserve_pending=false;priority.data[4]=0;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_TIMEOUT && "accepted one-shot must survive replacement attempt");
  assert(s_p4_priority[0].request.requestId==protectedId && s_p4_priority[0].frame.data[4]==0x10);
  assert(d.tx_msg_count==3 && q.n==1 && h.n==1);
  finish(&d);assert(h.sent[1].data[4]==0x10 && q.n==1);
  // Once the one-shot is loaded, the newest retry may occupy the free pending slot.
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  finish(&d);assert(h.sent[2].data[4]==0 && q.n==1);
  finish(&d);assert(h.sent[3].header.id==0x222);finish(&d);
  assert(d.tx_msg_count==0 && q.n==0);
 }
 // A new protected request may replace an unprotected one, then owns protection.
 init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 guard.preserve_pending=true;priority.data[4]=0x10;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 const uint32_t protectedId=s_p4_priority[0].request.requestId;
 guard.preserve_pending=false;priority.data[4]=0;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_TIMEOUT);
 assert(s_p4_priority[0].request.requestId==protectedId);
 // Protection does not prevent a revoked request from being retired.
 cancel++;assert(!p4_twai_priority_pending(&d));
 assert(d.tx_msg_count==1);finish(&d);assert(h.n==1);
 // The newest valid immediate replaces only the pending slot, on all controllers.
 for(int id=0;id<SOC_TWAI_CONTROLLER_NUM;id++) {
  for(int previous=2;previous<=3;previous++) {
   init(&d,&h,&q,&r,id);normal.identifier=0x111;
   assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   normal.identifier=0x333;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   guard.source=previous;priority.data[7]=0xAA;
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
   const uint32_t oldId=s_p4_priority[id].request.requestId;
   guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;priority.data[7]=0xBB;
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_TIMEOUT);
   assert(s_p4_priority[id].request.requestId==oldId);
   guard.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE;
   // Invalid replacement must retain the existing pending payload and identity.
   for(int invalid=0;invalid<9;invalid++) {
    p4_twai_priority_guard_t bad=guard;twai_message_t m=priority;
    volatile uint32_t badGeneration=7,badCancel=9,badDeadline=9;
    volatile bool badHold=true;
    if(invalid==0)bad.generation=&badGeneration;
    if(invalid==1)bad.cancel_generation=&badCancel;
    if(invalid==2)bad.administrative_hold=&badHold;
    if(invalid==3){bad.has_deadline=true;bad.deadline_ms=9;}
    if(invalid==4)bad.permission_deadline_ms=&badDeadline;
    if(invalid==5)m.identifier++;if(invalid==6)m.extd=true;
    if(invalid==7)m.rtr=true;if(invalid==8)m.data_length_code=7;
    assert(p4_twai_transmit_r79_v2(&d,&m,&bad)==(invalid<5?ESP_ERR_INVALID_STATE:ESP_ERR_INVALID_ARG));
    assert(s_p4_priority[id].request.requestId==oldId && s_p4_priority[id].frame.data[7]==0xAA);
    assert(q.n==2 && d.tx_msg_count==4 && h.n==1);
   }
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK && "newest immediate must replace pending native R79");
   const uint32_t newId=s_p4_priority[id].request.requestId;
   assert(newId!=oldId && newId && q.n==2 && d.tx_msg_count==4 && h.n==1);
   P4TwaiErrorSnapshot replaced;assert(p4TwaiDiagSnapshot(&replaced));
   const P4TwaiTxLifecycleSnapshot *life=&replaced.buses[id].lifecycle;
   assert(life->count>=3);
   const P4TwaiTxLifecycleEvent *cancelled=&life->events[life->count-2];
   assert(cancelled->kind==P4_TWAI_TX_CANCELLED && cancelled->reason==13 && cancelled->tx.requestId==oldId);
   assert(life->events[life->count-1].kind==P4_TWAI_TX_QUEUED && life->events[life->count-1].tx.requestId==newId);
   priority.data[7]=0xCC; // Admitted payload is copied.
   finish(&d);assert(h.sent[1].header.id==0x3FD && h.sent[1].data[7]==0xBB && q.n==2);
   finish(&d);assert(h.sent[2].header.id==0x222);finish(&d);assert(h.sent[3].header.id==0x333);finish(&d);
   assert(d.tx_msg_count==0 && q.n==0);
  }
 }
 // A live renewal must not mask generation/cancel/hold revoked after first reads.
 for(revokeKind=0;revokeKind<4;revokeKind++) {
  init(&d,&h,&q,&r,0);permissionDeadline=20;guard.permission_deadline_ms=&permissionDeadline;
  guard.retry_generation=&retryGeneration;guard.expected_retry_generation=retryGeneration;
  timerHook=revokeDuringRenewal;
  const uint8_t reasons[]={P4_TWAI_TX_REASON_GENERATION,P4_TWAI_TX_REASON_CANCEL_GENERATION,P4_TWAI_TX_REASON_HOLD,P4_TWAI_TX_REASON_CANCEL_GENERATION};
  assert(p4_twai_priority_guard_reason(&guard)==reasons[revokeKind]);
 }
 // Unspecified explicit R79 keeps its protected slot; only named sources replace.
 init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_UNKNOWN;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 guard.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_TIMEOUT);
 finish(&d);finish(&d);
 // Dynamic AP permission renews queued work, but never extends its hard deadline.
 for(int scenario=0;scenario<5;scenario++) {
  init(&d,&h,&q,&r,0);normal.identifier=0x111;
  permissionDeadline=20;guard.permission_deadline_ms=&permissionDeadline;
  if(scenario==2){guard.has_deadline=true;guard.deadline_ms=20;}
  if(scenario>=3){nowMs=UINT32_MAX-2;permissionDeadline=0;}
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  if(scenario==0 || scenario==2)permissionDeadline=30;
  nowMs=scenario>=3?(scenario==3?0:1):21;
  const bool allowed=scenario==0 || scenario==3;
  finish(&d);assert(h.sent[1].header.id==(allowed?0x3FD:0x222));
  P4TwaiErrorSnapshot expired;assert(p4TwaiDiagSnapshot(&expired));
  assert(expired.buses[0].lifecycle.events[1].kind==(allowed?P4_TWAI_TX_LOADED:P4_TWAI_TX_CANCELLED));
  if(!allowed)assert(expired.buses[0].lifecycle.events[1].reason==P4_TWAI_TX_REASON_DEADLINE);
  if(allowed)finish(&d);finish(&d);assert(d.tx_msg_count==0 && q.n==0);
  // Renewing permission after cancellation cannot resurrect the retired slot.
  permissionDeadline=100;assert(!s_p4_priority[0].pending);
 }

 // An ordinary state clone must not survive in FIFO behind a later R79.
 for(int id=0;id<SOC_TWAI_CONTROLLER_NUM;id++) {
  init(&d,&h,&q,&r,id);normal.identifier=0x111;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  unsigned oldTicks=ticks;
  assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_TIMEOUT);
  assert(q.n==1&&d.tx_msg_count==2&&ticks==oldTicks&&!s_p4_priority[id].pending);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_TIMEOUT&&q.n==1);
  finish(&d);assert(h.sent[1].header.id==0x3FD&&q.n==1);
  // R79 is in hardware; no new ordinary clone can queue behind it either.
  assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_TIMEOUT);
  finish(&d);assert(h.sent[2].header.id==0x222);finish(&d);
  assert(h.n==3&&d.tx_msg_count==0&&q.n==0);
  // Once idle, send the newest ordinary content directly, with no R79 authority.
  twai_message_t fresh=priority;fresh.data[7]=0xA6;
  assert(p4_twai_transmit_mux1_now_v2(&d,&fresh)==ESP_OK);
  assert(h.sent[3].data[7]==0xA6&&q.n==0&&d.tx_msg_count==1);
  finish(&d);
 }
 init(&d,&h,&q,&r,0);
 assert(p4_twai_transmit_mux1_now_v2(NULL,&priority)==ESP_ERR_INVALID_ARG);
 assert(p4_twai_transmit_mux1_now_v2(&d,NULL)==ESP_ERR_INVALID_ARG);
 for(int kind=0;kind<6;kind++) {
  twai_message_t bad=priority;
  if(kind==0)bad.identifier=0x3FE;if(kind==1)bad.data_length_code=7;
  if(kind==2)bad.extd=true;if(kind==3)bad.rtr=true;
  if(kind==4)bad.data[0]=0;if(kind==5)bad.data[0]=2;
  assert(p4_twai_transmit_mux1_now_v2(&d,&bad)==ESP_ERR_INVALID_ARG);
  assert(h.n==0&&d.tx_msg_count==0&&q.n==0);
 }
 d.mode=TWAI_MODE_LISTEN_ONLY;assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_NOT_SUPPORTED);d.mode=TWAI_MODE_NORMAL;
 d.state=TWAI_STATE_STOPPED;assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_INVALID_STATE);d.state=TWAI_STATE_RUNNING;
 h.flags|=TWAI_HAL_STATE_FLAG_BUS_OFF;assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_INVALID_STATE);h.flags&=~TWAI_HAL_STATE_FLAG_BUS_OFF;
 // Defensive hardware/accounting disagreement must never overwrite an active TX.
 h.flags|=TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED;assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_TIMEOUT);h.flags&=~TWAI_HAL_STATE_FLAG_TX_BUFF_OCCUPIED;
 // Revalidate a cancelled priority slot before deciding whether direct admission is possible.
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 generation++;assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_ERR_TIMEOUT);assert(!s_p4_priority[0].pending&&d.tx_msg_count==1);
 finish(&d);assert(p4_twai_transmit_mux1_now_v2(&d,&priority)==ESP_OK);finish(&d);
 normal.identifier=0x111;
 init(&d,&h,&q,&r,0);
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 normal.identifier=0x333;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 P4TwaiErrorSnapshot out;
 P4TwaiVehicleContext vehicle={.publishedMs=10,.gearObservedMs=9,.gear=4,.gearValid=1};
 p4TwaiDiagPublishVehicleContext(&vehicle);
 p4TwaiDiagRecordFromIsr(0,1,2,3,4,5);assert(p4TwaiDiagSnapshot(&out));
 assert(out.buses[0].last.tx.identifier==0x111 && out.buses[0].last.tx.source==0);
 assert(out.buses[0].lifecycle.count==1 && out.buses[0].lifecycle.events[0].kind==P4_TWAI_TX_QUEUED);
 uint32_t requestId=out.buses[0].lifecycle.events[0].tx.requestId;
 captureError=true; finish(&d); captureError=false;
 assert(p4TwaiDiagSnapshot(&out));
 assert(out.buses[0].last.tx.identifier==0x111 && out.buses[0].last.tx.active);
 p4TwaiDiagRecordFromIsr(0,1,2,3,4,5);assert(p4TwaiDiagSnapshot(&out));
 assert(out.buses[0].last.tx.identifier==0x3FD && out.buses[0].last.tx.requestId==requestId);
 assert(out.buses[0].last.tx.source==2 && out.buses[0].last.vehicle.gear==4);
 assert(h.sent[1].header.id==0x3FD && "R79 must precede queued ordinary frames");
 assert(q.n==2 && d.tx_msg_count==3);finish(&d);
 p4TwaiDiagRecordFromIsr(0,1,2,3,4,5);assert(p4TwaiDiagSnapshot(&out));
 assert(out.buses[0].last.tx.identifier==0x222 && out.buses[0].last.tx.source==0);
 assert(out.buses[0].lifecycle.events[2].kind==P4_TWAI_TX_COMPLETED);
 assert(out.buses[0].lifecycle.events[2].tx.requestId==requestId);
 finish(&d);finish(&d);
 assert(h.sent[2].header.id==0x222 && h.sent[3].header.id==0x333 && d.tx_msg_count==0);
 for(int reason=0;reason<5;reason++) {
  init(&d,&h,&q,&r,0);normal.identifier=0x111;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);normal.identifier=0x222;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  guard.has_deadline=true;guard.deadline_ms=20;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  p4_twai_priority_guard_t periodic=guard;periodic.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&periodic)==ESP_ERR_TIMEOUT);
  assert(twai_transmit_v2(&d,&normal,0)==ESP_ERR_TIMEOUT && q.n==1);
  init(&b,&hb,&qb,&rb,1);assert(twai_transmit_v2(&b,&normal,0)==ESP_OK);
  if(reason==0)generation++; if(reason==1)cancel++; if(reason==2)hold=true;
  if(reason==3)nowMs=21; if(reason==4)nowMs=20;
  finish(&d);
  assert(h.sent[1].header.id==(reason==4?0x3FD:0x222));
  assert(p4TwaiDiagSnapshot(&out));
  const P4TwaiTxLifecycleEvent *last=&out.buses[0].lifecycle.events[1];
  const uint8_t reasons[]={P4_TWAI_TX_REASON_GENERATION,P4_TWAI_TX_REASON_CANCEL_GENERATION,
    P4_TWAI_TX_REASON_HOLD,P4_TWAI_TX_REASON_DEADLINE,P4_TWAI_TX_REASON_NONE};
  assert(last->kind==(reason==4?P4_TWAI_TX_LOADED:P4_TWAI_TX_CANCELLED));
  assert(last->reason==reasons[reason]);
  if(reason==4)finish(&d); finish(&d);assert(d.tx_msg_count==0 && q.n==0);
 }
 // Copied descriptor, zero-valued rollover deadline, and late admission rejection.
 init(&d,&h,&q,&r,0);guard.has_deadline=true;guard.deadline_ms=0;nowMs=UINT32_MAX;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);guard.expected_generation=99;
 nowMs=0;finish(&d);assert(h.sent[1].header.id==0x3FD);finish(&d);
 guard.expected_generation=1;nowMs=1;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE);
 // Native queue-disabled slot clearing and lifecycle resets.
 for(int lifecycle=0;lifecycle<4;lifecycle++) {
  init(&d,&h,&q,&r,0);d.tx_queue=NULL;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  if(lifecycle==0) { assert(twai_clear_transmit_queue_v2(&d)==ESP_OK);assert(d.tx_msg_count==1);finish(&d); }
  if(lifecycle==1) { assert(twai_stop_v2(&d)==ESP_OK);assert(twai_start_v2(&d)==ESP_OK); }
  if(lifecycle==2) { d.state=TWAI_STATE_BUS_OFF;h.flags=1;assert(twai_initiate_recovery_v2(&d)==ESP_OK); }
  if(lifecycle==3) { finish(&d);assert(h.sent[1].header.id==0x3FD);finish(&d); }
  assert(d.tx_msg_count==0);
 }
 // Queue full task wait permits priority admission, then rejects ordinary retry.
 init(&d,&h,&q,&r,0);q.cap=1;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);hookDriver=&d;delayHook=admitDuringWait;
 assert(twai_transmit_v2(&d,&normal,2)==ESP_ERR_TIMEOUT);assert(q.n==1 && d.tx_msg_count==3);
 finish(&d);assert(h.sent[1].header.id==0x3FD);finish(&d);finish(&d);
 // Admission wait budget uses unsigned tick arithmetic across rollover.
 for(int wrap=0;wrap<2;wrap++) {
  init(&d,&h,&q,&r,0);q.cap=1;ticks=wrap?UINT32_MAX-1:100;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  TickType_t start=ticks;
  assert(twai_transmit_v2(&d,&normal,2)==ESP_ERR_TIMEOUT);
  assert((TickType_t)(ticks-start)==2 && q.n==1 && d.tx_msg_count==2);
  assert(twai_clear_transmit_queue_v2(&d)==ESP_OK && q.n==0 && d.tx_msg_count==1);finish(&d);
 }
 // Real ISR bus-off alone and coincident completion retire pending R79 once.
 for(int simultaneous=0;simultaneous<2;simultaneous++) {
  init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  events=TWAI_HAL_EVENT_BUS_OFF|(simultaneous?TWAI_HAL_EVENT_TX_BUFF_FREE:0);
  twai_intr_handler_main(&d);
  p4TwaiDiagRecordFromIsr(0,1,2,3,4,5);assert(p4TwaiDiagSnapshot(&out));
  assert(!out.buses[0].last.tx.active && out.buses[0].last.tx.valid);
  assert(out.buses[0].lifecycle.events[1].reason==P4_TWAI_TX_REASON_BUS_OFF);
  assert(d.state==TWAI_STATE_BUS_OFF && d.tx_msg_count==2-simultaneous && q.n==1 && h.n==1);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE);
  assert(twai_initiate_recovery_v2(&d)==ESP_OK && d.tx_msg_count==0 && q.n==0);
  events=TWAI_HAL_EVENT_BUS_RECOV_CPLT;twai_intr_handler_main(&d);
  assert(twai_start_v2(&d)==ESP_OK);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  finish(&d);assert(d.tx_msg_count==0);
 }
 // ID alone never promotes an ordinary submission to the priority slot.
 init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);assert(twai_transmit_v2(&d,&priority,0)==ESP_OK);
 finish(&d);assert(h.sent[1].header.id==normal.identifier);finish(&d);assert(h.sent[2].header.id==0x3FD);finish(&d);
 // Uninstall retires the static slot before a new object reuses its controller.
 init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 d.state=TWAI_STATE_BUS_OFF;h.flags=1;g_twai_objs[0]=&d;
 assert(twai_driver_uninstall_v2(&d)==ESP_OK && g_twai_objs[0]==NULL && d.tx_msg_count==1);
 init(&d,&h,&q,&r,0);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 finish(&d);assert(d.tx_msg_count==0);
 // Direct periodic / unspecified explicit R79, failed completion, immutable payload,
 // BUS OFF/stop/recovery/uninstall retirement retain last identity but clear active.
 for(int reason=0;reason<5;++reason) {
  init(&d,&h,&q,&r,0);guard.source=reason==0?0:P4_TWAI_TX_SOURCE_R79_PERIODIC;
  priority.data[1]=0xA7;
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  assert(p4TwaiDiagSnapshot(&out));
  assert(out.buses[0].lifecycle.count==2);
  const P4TwaiTxIdentity loaded=out.buses[0].lifecycle.events[1].tx;
  assert(loaded.source==(reason==0?P4_TWAI_TX_SOURCE_R79_UNKNOWN:P4_TWAI_TX_SOURCE_R79_PERIODIC));
  assert(loaded.active && loaded.valid && loaded.requestId && loaded.loadedUs>=loaded.queuedUs);
  priority.data[1]=0x11;
  if(reason==0) { events=TWAI_HAL_EVENT_TX_BUFF_FREE;twai_intr_handler_main(&d); }
  if(reason==1) { events=TWAI_HAL_EVENT_BUS_OFF;captureError=true;twai_intr_handler_main(&d);captureError=false; }
  if(reason==2) assert(twai_stop_v2(&d)==ESP_OK);
  if(reason==3) { d.state=TWAI_STATE_BUS_OFF;h.flags=1;assert(twai_initiate_recovery_v2(&d)==ESP_OK); }
  if(reason==4) { d.state=TWAI_STATE_BUS_OFF;h.flags=1;g_twai_objs[0]=&d;assert(twai_driver_uninstall_v2(&d)==ESP_OK); }
  assert(p4TwaiDiagSnapshot(&out));
  if(reason==1)assert(out.buses[0].last.tx.active && out.buses[0].last.tx.data[1]==0xA7);
  p4TwaiDiagRecordFromIsr(0,1,2,3,4,5);assert(p4TwaiDiagSnapshot(&out));
  assert(!out.buses[0].last.tx.active && out.buses[0].last.tx.valid);
  assert(out.buses[0].last.tx.data[1]==0xA7 && out.buses[0].last.tx.requestId==loaded.requestId);
  const P4TwaiTxLifecycleEvent event=out.buses[0].lifecycle.events[2];
  const uint8_t reasons[]={P4_TWAI_TX_REASON_FAILED,P4_TWAI_TX_REASON_BUS_OFF,
    P4_TWAI_TX_REASON_STOP,P4_TWAI_TX_REASON_RECOVERY,P4_TWAI_TX_REASON_UNINSTALL};
  assert(out.buses[0].lifecycle.count==3 && event.reason==reasons[reason]);
  assert(event.kind==(reason==0?P4_TWAI_TX_COMPLETED:P4_TWAI_TX_CANCELLED));
 }
 // Same-ID ordinary TX must not claim R79 source, token, or lifecycle.
 init(&d,&h,&q,&r,0);assert(twai_transmit_v2(&d,&priority,0)==ESP_OK);
 p4TwaiDiagRecordFromIsr(0,1,2,3,4,5);assert(p4TwaiDiagSnapshot(&out));
 assert(out.buses[0].last.tx.identifier==0x3FD && out.buses[0].last.tx.source==P4_TWAI_TX_SOURCE_UNKNOWN);
 assert(out.buses[0].last.tx.requestId==0 && out.buses[0].lifecycle.count==0);finish(&d);
 // Request token rollover skips zero and copied token survives retirement.
 init(&d,&h,&q,&r,0);s_p4_priority[0].requestSequence=UINT32_MAX;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);finish(&d);
 assert(p4TwaiDiagSnapshot(&out));
 for(unsigned i=0;i<3;++i)assert(out.buses[0].lifecycle.events[i].tx.requestId==1);
 // An expired pending permission cancels once; later renewal alone does not rearm it.
 init(&d,&h,&q,&r,0);permissionDeadline=20;guard.permission_deadline_ms=&permissionDeadline;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 nowMs=21;assert(!p4_twai_priority_pending(&d));
 permissionDeadline=100;finish(&d);assert(h.n==1 && d.tx_msg_count==0);
 assert(p4TwaiDiagSnapshot(&out));assert(out.buses[0].lifecycle.count==2);
 assert(out.buses[0].lifecycle.events[1].reason==P4_TWAI_TX_REASON_DEADLINE);
 // A newly observed native MUX obsoletes periodic work before app dequeue.
 for(unsigned mux=0;mux<=2;++mux) {
  init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  twai_hal_frame_t boundary={.header={.id=0x3FD,.dlc=8},.data={2},.dlc=8};
  boundary.data[0]=(uint8_t)mux;
  (void)p4_twai_boundary_observe(&d,&boundary);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE &&
         "new native MUX boundary must reject periodic before app observes it");
  assert(h.n==0 && d.tx_msg_count==0);
 }
 // Unrelated software AND HAL backlog permit periodic admission and dispatch.
 init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
 for(unsigned n=0;n<4;++n)irqRx(&d,rxFrame(0x123,0));
 halRx(&d,rxFrame(0x456,0));assert(p4_twai_r79_periodic_ready_v2(&d));
 assert(d.rx_msg_count==5 && r.n==5 && h.rxN==0);
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 halRx(&d,rxFrame(0x777,0));finish(&d);
 assert(h.sent[1].header.id==0x3FD && r.n==6 && q.n==1);
 finish(&d);assert(h.sent[2].header.id==0x222);finish(&d);
 // Only standard DATA/DLC8 MUX0..2 advances the fence.
 for(unsigned kind=0;kind<5;++kind) {
  init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  twai_hal_frame_t irrelevant=rxFrame(0x3FD,3);
  if(kind==0)irrelevant.header.id=0x123;
  if(kind==1){irrelevant.header.ide=true;irrelevant.data[0]=1;}
  if(kind==2){irrelevant.header.rtr=true;irrelevant.data[0]=1;}
  if(kind==3){irrelevant.header.dlc=irrelevant.dlc=7;irrelevant.data[0]=1;}
  uint32_t before=s_p4_rx_boundary[0].observed;
  halRx(&d,irrelevant);assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  assert(s_p4_rx_boundary[0].observed==before);finish(&d);
 }
 // HAL-only boundaries at admission and actual IRQ load reject obsolete work.
 for(unsigned mux=0;mux<=2;++mux) for(unsigned phase=0;phase<3;++phase) {
  init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  if(phase==0) {
   halRx(&d,rxFrame(0x3FD,(uint8_t)mux));
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_STATE);
   assert(h.n==0 && r.n==1);
  } else {
   assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
   if(phase==1)irqRx(&d,rxFrame(0x3FD,(uint8_t)mux));
   else halRx(&d,rxFrame(0x3FD,(uint8_t)mux)); // no RX IRQ flag in finish
   finish(&d);assert(h.sent[1].header.id==0x222 && d.tx_msg_count==1);
   assert(p4TwaiDiagSnapshot(&out));bool found=false;
   for(unsigned n=0;n<out.buses[0].lifecycle.count;++n)
    if(out.buses[0].lifecycle.events[n].reason==P4_TWAI_TX_REASON_RX_BOUNDARY)found=true;
   assert(found);finish(&d);
  }
  assert(!p4_twai_r79_periodic_ready_v2(&d));
  dequeueAll(&d);assert(p4_twai_r79_periodic_ready_v2(&d)==(mux==2));
 }
 // A lost MUX cannot be acknowledged by an older queued MUX2.
 init(&d,&h,&q,&r,0);r.cap=1;irqRx(&d,rxFrame(0x3FD,2));
 irqRx(&d,rxFrame(0x3FD,0));assert(d.rx_missed_count==1);
 dequeueAll(&d);assert(!p4_twai_r79_periodic_ready_v2(&d));
 irqRx(&d,rxFrame(0x3FD,2));dequeueAll(&d);assert(p4_twai_r79_periodic_ready_v2(&d));
 // Unknown hardware loss invalidates all old tokens until a fresh boundary.
 h.overrun=true;irqRx(&d,rxFrame(0x123,0));h.overrun=false;
 assert(!p4_twai_r79_periodic_ready_v2(&d));
 irqRx(&d,rxFrame(0x3FD,2));dequeueAll(&d);assert(p4_twai_r79_periodic_ready_v2(&d));
 // Clear/start epochs cannot revive an old pending periodic, even after resync.
 for(unsigned reset=0;reset<2;++reset) {
  init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  if(reset==0)assert(twai_clear_receive_queue_v2(&d)==ESP_OK);
  else {assert(twai_stop_v2(&d)==ESP_OK);assert(twai_start_v2(&d)==ESP_OK);}
  assert(!p4_twai_r79_periodic_ready_v2(&d));
  irqRx(&d,rxFrame(0x3FD,2));dequeueAll(&d);assert(p4_twai_r79_periodic_ready_v2(&d));
  if(reset==0)finish(&d);
  assert(h.n==1 && d.tx_msg_count==0);
 }
 // Epoch rollover skips zero. The physical controller fence is independent.
 init(&d,&h,&q,&r,0);init(&b,&hb,&qb,&rb,1);
 s_p4_rx_boundary[0].observed=UINT32_MAX;
 irqRx(&d,rxFrame(0x3FD,2));assert(s_p4_rx_boundary[0].observed==1);
 assert(!p4_twai_r79_periodic_ready_v2(&d) && p4_twai_r79_periodic_ready_v2(&b));
 dequeueAll(&d);assert(p4_twai_r79_periodic_ready_v2(&d));
 // Immediate recovery remains permitted across unread periodic boundaries.
 irqRx(&d,rxFrame(0x3FD,0));guard.source=P4_TWAI_TX_SOURCE_R79_IMMEDIATE;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);finish(&d);
 // RX arriving during the snapshot drain is deferred, never guessed safe.
 for(unsigned phase=0;phase<3;++phase) {
  init(&d,&h,&q,&r,0);hookDriver=&d;lateId=0x3FD;
  guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  if(phase==2) {
   assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
   assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  }
  halRx(&d,rxFrame(0x123,0));queueSendHook=appendDuringDrain;
  if(phase==0)assert(!p4_twai_r79_periodic_ready_v2(&d) && "HAL residual must defer readiness");
  if(phase==1)assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_TIMEOUT);
  if(phase==2) {
   finish(&d);assert(h.n==1 && !(h.flags&4) && s_p4_priority[0].pending && d.tx_msg_count==2 && q.n==1);
   // RX-only IRQ must cancel obsolete periodic AND start preserved ordinary FIFO.
   events=TWAI_HAL_EVENT_RX_BUFF_FRAME;twai_intr_handler_main(&d);
   assert(h.n==2 && h.sent[1].header.id==0x222 && d.tx_msg_count==1 && q.n==0);
   finish(&d);
  } else assert(h.n==0);
 }
 // Residual unrelated RX retains the accepted priority request and wakes it
 // ahead of ordinary FIFO, with either RX IRQ or task-side progress.
 for(unsigned taskKick=0;taskKick<2;++taskKick) {
  init(&d,&h,&q,&r,0);hookDriver=&d;lateId=0x456;
  guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  const uint32_t request=s_p4_priority[0].request.requestId;
  halRx(&d,rxFrame(0x123,0));queueSendHook=appendDuringDrain;finish(&d);
  assert(h.n==1 && d.tx_msg_count==2 && s_p4_priority[0].request.requestId==request);
  assert(twai_transmit_v2(&d,&normal,0)==ESP_ERR_TIMEOUT); // cannot pass R79
  if(taskKick)assert(p4_twai_r79_periodic_ready_v2(&d));
  else {events=TWAI_HAL_EVENT_RX_BUFF_FRAME;twai_intr_handler_main(&d);}
  assert(h.n==2 && h.sent[1].header.id==0x3FD && d.tx_msg_count==2 && q.n==1);
  assert(p4TwaiDiagSnapshot(&out));
  for(unsigned n=0;n<out.buses[0].lifecycle.count;++n)
   assert(out.buses[0].lifecycle.events[n].kind!=P4_TWAI_TX_CANCELLED);
  finish(&d);assert(h.sent[2].header.id==0x222);finish(&d);
 }
 // Simultaneous RX/TX-complete dispatches once; idle RX-only kick preserves count.
 init(&d,&h,&q,&r,0);guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
 assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
 halRx(&d,rxFrame(0x123,0));events=TWAI_HAL_EVENT_RX_BUFF_FRAME|TWAI_HAL_EVENT_TX_BUFF_FREE|TWAI_HAL_EVENT_TX_SUCCESS;
 twai_intr_handler_main(&d);assert(h.n==2 && d.tx_msg_count==1);
 events=TWAI_HAL_EVENT_RX_BUFF_FRAME;twai_intr_handler_main(&d);assert(h.n==2&&d.tx_msg_count==1);finish(&d);
 // Genuine deadline/permission cancellation while deferred resumes FIFO.
 for(unsigned deny=0;deny<2;++deny) {
  init(&d,&h,&q,&r,0);hookDriver=&d;lateId=0x456;
  guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;guard.has_deadline=true;guard.deadline_ms=20;
  assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  normal.identifier=0x222;assert(twai_transmit_v2(&d,&normal,0)==ESP_OK);
  assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_OK);
  halRx(&d,rxFrame(0x123,0));queueSendHook=appendDuringDrain;finish(&d);
  if(deny==0)nowMs=21;else hold=true;
  (void)p4_twai_r79_periodic_ready_v2(&d);
  assert(h.n==2&&h.sent[1].header.id==0x222&&d.tx_msg_count==1);finish(&d);
 }
 // The second/final direct-load drain has its own residual fence and reason.
 init(&d,&h,&q,&r,0);hookDriver=&d;lateId=0x3FD;
 guard.source=P4_TWAI_TX_SOURCE_R79_PERIODIC;
 admissionClockReads=0;timerHook=appendAtRequestIdentity;
 assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_TIMEOUT);
 assert(admissionClockReads==2 && h.n==0 && d.tx_msg_count==0 && h.rxN==1);
 assert(p4TwaiDiagSnapshot(&out));assert(out.buses[0].lifecycle.count==2);
 assert(out.buses[0].lifecycle.events[1].reason==P4_TWAI_TX_REASON_RX_PENDING);
 assert(!p4_twai_r79_periodic_ready_v2(&d));dequeueAll(&d);
 assert(p4_twai_r79_periodic_ready_v2(&d));
 // Strict explicit API domain and required guards.
 init(&d,&h,&q,&r,0);
 for(int invalid=0;invalid<6;invalid++) {
  twai_message_t m=priority;p4_twai_priority_guard_t g=guard;
  if(invalid==0)m.identifier++;if(invalid==1)m.extd=true;if(invalid==2)m.rtr=true;
  if(invalid==3)m.data_length_code=7;if(invalid==4)m.data[0]=2;if(invalid==5)g.generation=NULL;
  assert(p4_twai_transmit_r79_v2(&d,&m,&g)==ESP_ERR_INVALID_ARG);
 }
 guard.administrative_hold=NULL;assert(p4_twai_transmit_r79_v2(&d,&priority,&guard)==ESP_ERR_INVALID_ARG);
 assert(h.n==0 && d.tx_msg_count==0 && !lockDepth);
 puts("PASS native priority: FIFO/order, cancellation, deadline/rollover, controller isolation, lifecycle, locked admission and API guards");
}
'''
with tempfile.TemporaryDirectory(prefix='p4-native-priority-') as directory:
    temp = Path(directory)
    (temp/'esp_attr.h').write_text('#define IRAM_ATTR\n#define DRAM_ATTR\n')
    (temp/'esp_timer.h').write_text('#include <stdint.h>\nint64_t esp_timer_get_time(void);\n')
    (temp/'freertos').mkdir()
    (temp/'freertos/FreeRTOS.h').write_text('#pragma once\ntypedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\nvoid diagFakeEnter(void); void diagFakeExit(void);\n#define portENTER_CRITICAL(p) ((void)(p),diagFakeEnter())\n#define portEXIT_CRITICAL(p) ((void)(p),diagFakeExit())\n#define portENTER_CRITICAL_ISR portENTER_CRITICAL\n#define portEXIT_CRITICAL_ISR portEXIT_CRITICAL\n')
    (temp/'freertos/portmacro.h').write_text('#include "FreeRTOS.h"\n')
    (temp/'native.c').write_text(fixture)
    subprocess.run([os.environ.get('CC','/usr/bin/cc'),'-std=c11','-Wall','-Wextra',
                    '-Wno-unused-function','-Wno-misleading-indentation','-I',str(temp),'-I',str(ROOT),str(ROOT/'p4_twai_diag.c'),str(temp/'native.c'),'-o',str(temp/'native')],check=True)
    subprocess.run([str(temp/'native')],check=True)
