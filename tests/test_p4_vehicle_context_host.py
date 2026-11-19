"""Execute the actual task-side diagnostic context publisher, including stale evidence."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'vehicle_logic.h').read_text()
marker = 'static void p4PublishVehicleDiagnosticContext(uint32_t now)'
if marker in source:
    start = source.index(marker)
    end = source.index('\n}', start) + 2
    publisher = source[start:end]
else:
    # Prior production has no publisher: compile a no-op representation so RED
    # demonstrates absent publication at an assertion, never a missing symbol.
    publisher = 'static void p4PublishVehicleDiagnosticContext(uint32_t) {}'

fixture = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "summon_state_pure.h"
#include "p4_twai_diag.h"
int stateMux=0,lockDepth=0,published=0;
void portENTER_CRITICAL(int *mux){assert(mux==&stateMux&&lockDepth==0);++lockDepth;}
void portEXIT_CRITICAL(int *mux){assert(mux==&stateMux&&lockDepth==1);--lockDepth;}
P4TwaiVehicleContext captured{};
void p4TwaiDiagPublishVehicleContext(const P4TwaiVehicleContext *context){
 assert(context&&lockDepth==1);captured=*context;++published;
}
int8_t gear118State=-1,gear186State=-1;
uint8_t gear118Raw=0,gear186Raw=0,dasAutopilotState4=0;
uint32_t gear118Ms=0,gear186Ms=0,lastDASStatusMillis=0,lastAcaMillis=0,lastSprMillis=0;
bool dasAutopilotStateValid=false,gateSummoning=false,acaValid=false,sprValid=false,allow186=true;
constexpr uint32_t SUMMON_GEAR_FRESH_MS=3000,SUMMON_ACA_FRESH_MS=750,SUMMON_SPR_FRESH_MS=2500;
SummonGearDecisionPure summonFreshGearDecisionLocked(uint32_t now){
 assert(lockDepth==1);
 return summonFreshGearPure(now,{gear118State,gear118Ms,gear118State>=0},
   {gear186State,gear186Ms,gear186State>=0},allow186,SUMMON_GEAR_FRESH_MS);
}
''' + publisher + r'''
void publish(uint32_t now){
 const int before=published;p4PublishVehicleDiagnosticContext(now);
 assert(published==before+1&&"Each publication must emit one diagnostic snapshot");
 assert(lockDepth==0&&captured.publishedMs==now&&captured.reserved==0);
}
int main(){
 // Unknown and reset state never borrow gateParked defaults or old raw bytes.
 publish(10000);
 assert(!captured.gearValid&&captured.gearSource==0&&captured.gearObservedMs==0);
 assert(!captured.apValid&&!captured.summonValid&&!captured.summonActive&&captured.summonObservedMs==0);
 // Fresh primary wins over more recent fallback, retaining the raw gear enum.
 gear118State=0;gear118Raw=4;gear118Ms=9000;
 gear186State=1;gear186Raw=1;gear186Ms=9900;
 dasAutopilotStateValid=true;dasAutopilotState4=3;lastDASStatusMillis=1;
 acaValid=sprValid=gateSummoning=true;lastAcaMillis=9500;lastSprMillis=8000;
 publish(10000);
 assert(captured.gearValid&&captured.gearSource==1&&captured.gear==4&&captured.gearObservedMs==9000);
 assert(captured.apValid&&captured.apState==3&&captured.apObservedMs==1);
 assert(captured.summonValid&&captured.summonActive&&captured.summonObservedMs==8000);
 // Each validity input is required even when both timestamps are fresh.
 acaValid=false;publish(10000);assert(!captured.summonValid&&captured.summonActive);
 acaValid=true;sprValid=false;publish(10000);assert(!captured.summonValid&&captured.summonActive);
 sprValid=true;
 // Inclusive freshness boundaries and first stale millisecond.
 gear118Ms=7000;lastAcaMillis=9250;lastSprMillis=7500;publish(10000);
 assert(captured.gearValid&&captured.gearSource==1&&captured.summonValid);
 publish(10001);assert(captured.gearValid&&captured.gearSource==2&&captured.gear==1&&captured.gearObservedMs==9900);
 assert(!captured.summonValid&&captured.summonActive&&captured.summonObservedMs==7500);
 // Profile-disallowed fallback keeps stale primary evidence, marked invalid.
 allow186=false;publish(10001);
 assert(!captured.gearValid&&captured.gearSource==1&&captured.gear==4&&captured.gearObservedMs==7000);
 // Stale fallback is still exported as raw evidence when primary is unknown.
 gear118State=-1;gear186Ms=2;publish(10001);
 assert(!captured.gearValid&&captured.gearSource==2&&captured.gear==1&&captured.gearObservedMs==2);
 // Recovery invalidation clears validity, regardless of retained timestamps/raw.
 gear186State=-1;dasAutopilotStateValid=false;acaValid=sprValid=false;
 publish(10001);assert(!captured.gearValid&&captured.gearSource==0&&captured.gearObservedMs==0);
 assert(!captured.apValid&&captured.apState==3&&captured.apObservedMs==1);
 assert(!captured.summonValid&&captured.summonActive&&captured.summonObservedMs==0);
 // One known Summon timestamp remains visible, even when confirmation is invalid.
 acaValid=false;sprValid=true;lastAcaMillis=0;lastSprMillis=9700;publish(10001);assert(captured.summonObservedMs==9700&&!captured.summonValid);
 acaValid=true;sprValid=false;lastAcaMillis=9800;lastSprMillis=0;publish(10001);assert(captured.summonObservedMs==9800&&!captured.summonValid);
 acaValid=sprValid=false;lastAcaMillis=lastSprMillis=0;publish(10001);assert(captured.summonObservedMs==0&&!captured.summonValid);
 // uint32 rollover: oldest signal is selected by age, not timestamp magnitude.
 gear118State=0;gear118Raw=2;gear118Ms=UINT32_MAX-10;
 acaValid=sprValid=true;lastAcaMillis=2;lastSprMillis=UINT32_MAX-20;
 publish(5);assert(captured.gearValid&&captured.gear==2&&captured.gearSource==1);
 assert(captured.summonValid&&captured.summonObservedMs==UINT32_MAX-20);
 assert((uint32_t)(captured.publishedMs-captured.gearObservedMs)==16);
 assert((uint32_t)(captured.publishedMs-captured.summonObservedMs)==26);
 lastAcaMillis=UINT32_MAX-30;lastSprMillis=3;publish(5);
 assert(captured.summonObservedMs==UINT32_MAX-30&&captured.summonValid);
 // Freshness is independent of derived active state; active=false can be valid.
 gateSummoning=false;publish(5);assert(!captured.summonActive&&captured.summonValid);
 lastAcaMillis=0;publish(5);assert(!captured.summonValid);
 puts("PASS: production vehicle-context publication, lock ownership, primary/fallback/raw retention, validity, stale evidence and rollover ages");
}
'''
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    (temp / 'esp_attr.h').write_text('#pragma once\n#define IRAM_ATTR\n')
    (temp / 'context.cpp').write_text(fixture)
    compiled = subprocess.run([os.environ.get('CXX', '/usr/bin/g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                               '-I'+str(temp), '-I'+str(ROOT), str(temp/'context.cpp'), '-o', str(temp/'context')],
                              capture_output=True, text=True)
    assert compiled.returncode == 0, 'INVALID-RED: '+compiled.stdout+compiled.stderr
    result = subprocess.run([str(temp/'context')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout+result.stderr
    print(result.stdout.strip())
