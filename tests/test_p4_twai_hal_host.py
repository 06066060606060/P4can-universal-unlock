"""Differential test of the actual unchanged and instrumented HAL error path."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
upstream = (ROOT / 'vendor/twai/twai_hal_v1.c.txt').read_text()
path = ROOT / 'p4_twai_hal_v1.c'
production = path.read_text() if path.exists() else upstream


def function(source, marker):
    begin = source.index(marker)
    return source[begin:source.index('\n}', begin) + 2]


helper = (function(production, 'static inline void p4_twai_capture_error(')
          if 'static inline void p4_twai_capture_error(' in production else '')
fixture = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
static unsigned reads=0, captures=0, arbClears=0;
struct Ecc { uint32_t value; operator uint32_t() const { ++reads; return value; } };
struct Hw { struct { Ecc val; } err_code_cap; uint32_t status,tec,rec; } hw[3];
#define TWAI_LL_GET_HW(id) (&hw[id])
using twai_ll_err_type_t=int;using twai_ll_err_dir_t=int;using twai_ll_err_seg_t=int;
constexpr int TWAI_LL_ERR_BIT=0,TWAI_LL_ERR_FORM=1,TWAI_LL_ERR_STUFF=2,TWAI_LL_ERR_OTHER=3;
constexpr int TWAI_LL_ERR_SEG_ACK_SLOT=25;
constexpr uint32_t TWAI_HAL_EVENT_BUS_OFF=1,TWAI_HAL_EVENT_BUS_ERR=128,TWAI_HAL_EVENT_ARB_LOST=256;
struct Errors {uint32_t bit_err=0,form_err=0,stuff_err=0,ack_err=0,arb_lost=0;};
struct twai_hal_context_t {Hw*dev;uint32_t state_flags;Errors errors;};
static uint32_t incoming=0,raw=0,seenBus=0,seenStatus=0,seenTec=0,seenRec=0,seenFlags=0;
static uint32_t twai_hal_decode_interrupt(twai_hal_context_t*){return incoming;}
static uint32_t twai_ll_get_status(Hw*d){return d->status;}
static uint32_t twai_ll_get_tec(Hw*d){return d->tec;}
static uint32_t twai_ll_get_rec(Hw*d){return d->rec;}
static void twai_ll_parse_err_code_cap(Hw*d,int*t,int*r,int*s){uint32_t v=d->err_code_cap.val;*t=(v>>6)&3;*r=(v>>5)&1;*s=v&31;}
static void twai_ll_clear_arb_lost_cap(Hw*){++arbClears;}
static void p4TwaiDiagRecordFromIsr(uint8_t b,uint32_t e,uint32_t s,uint32_t t,uint32_t r,uint32_t f){++captures;seenBus=b;raw=e;seenStatus=s;seenTec=t;seenRec=r;seenFlags=f;}
'''
fixture += function(upstream, 'uint32_t twai_hal_get_events(').replace(
    'twai_hal_get_events(', 'baseline_get_events(', 1) + '\n'
fixture += helper + '\n' + function(production, 'uint32_t twai_hal_get_events(') + r'''
int main(){
unsigned cases=0;
for(uint8_t bus=0;bus<3;bus++)for(uint32_t ecc=0;ecc<256;ecc++)for(unsigned mode=0;mode<8;mode++){
 incoming=(mode&1?TWAI_HAL_EVENT_BUS_ERR:0)|(mode&2?TWAI_HAL_EVENT_BUS_OFF:0)|(mode&4?TWAI_HAL_EVENT_ARB_LOST:0);
 hw[bus].err_code_cap.val.value=ecc|0xabc00000u;hw[bus].status=0x35;hw[bus].tec=127;hw[bus].rec=19;
 twai_hal_context_t original{&hw[bus],0x72,{}},instrumented=original;
 reads=captures=arbClears=0;uint32_t expected=baseline_get_events(&original);
 unsigned expectedReads=reads,expectedClears=arbClears;
 reads=captures=arbClears=0;uint32_t actual=twai_hal_get_events(&instrumented);
 assert(actual==expected&&reads==expectedReads&&arbClears==expectedClears);
 assert(instrumented.state_flags==original.state_flags);
 assert(instrumented.errors.bit_err==original.errors.bit_err);
 assert(instrumented.errors.form_err==original.errors.form_err);
 assert(instrumented.errors.stuff_err==original.errors.stuff_err);
 assert(instrumented.errors.ack_err==original.errors.ack_err);
 assert(instrumented.errors.arb_lost==original.errors.arb_lost);
 assert(captures==unsigned((incoming&TWAI_HAL_EVENT_BUS_ERR)!=0));
 if(captures){assert(reads==1&&seenBus==bus&&raw==(ecc|0xabc00000u));assert(seenStatus==0x35&&seenTec==127&&seenRec==19&&seenFlags==0x72);}
 ++cases;
}
std::printf("PASS: %u physical bus/ECC/interrupt combinations; single ECC read and unchanged HAL behavior\n",cases);
}
'''
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    (temp / 'hal.cpp').write_text(fixture)
    subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-function', str(temp / 'hal.cpp'), '-o', str(temp / 'hal')], check=True)
    subprocess.run([str(temp / 'hal')], check=True)
