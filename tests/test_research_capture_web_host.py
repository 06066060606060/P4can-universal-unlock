"""Execute production CSV admission against unfinished RAW prehistory."""
from pathlib import Path
import os, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'web_api.h').read_text()
prefix=source[source.index('static void httpResearchCaptureCsv() {'):source.index('  const uint32_t exportRows =',source.index('static void httpResearchCaptureCsv() {'))]
fixture=r'''
#include <cassert>
#include <cstdint>
struct ResearchCaptureEntry {}; struct ResearchCaptureRawEntry {};
int researchCaptureMux=0,depth=0;
void portENTER_CRITICAL(int*){assert(depth++==0);} void portEXIT_CRITICAL(int*){assert(--depth==0);}
constexpr uint8_t RESEARCH_CAPTURE_CAPTURING=2;
uint8_t researchCaptureState=3,researchCaptureMode=1;
uint32_t researchCaptureCount=0;uint16_t researchCaptureCompletedSegments=0;
ResearchCaptureEntry*researchCaptureEntries=nullptr;
bool researchCaptureExporting=false,pending=false,researchCaptureSnapshotBusy=false;
bool researchCaptureRawCopyPendingLocked(){assert(depth==1);return pending;}
ResearchCaptureRawEntry*researchCaptureRawArchiveBase(){return nullptr;}
struct Server {int status=0;void send(int code,const char*,const char*){assert(depth==0);status=code;}} server;
'''+prefix+r'''
(void)mode;(void)count;(void)rawCompleted;(void)entries;(void)archive;
server.send(200,"text/csv","");}
int main(){
// FULL or completed-looking state must not expose reserved, unwritten PRE rows.
pending=true;httpResearchCaptureCsv();assert(server.status==409&&!researchCaptureExporting&&depth==0);
pending=false;researchCaptureSnapshotBusy=true;httpResearchCaptureCsv();assert(server.status==409&&!researchCaptureExporting&&depth==0);
researchCaptureSnapshotBusy=false;httpResearchCaptureCsv();assert(server.status==200&&researchCaptureExporting&&depth==0);
httpResearchCaptureCsv();assert(server.status==409&&researchCaptureExporting&&depth==0);
researchCaptureExporting=false;researchCaptureState=RESEARCH_CAPTURE_CAPTURING;httpResearchCaptureCsv();assert(server.status==409&&!researchCaptureExporting);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'main.cpp').write_text(fixture)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(p/'main.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS: actual CSV admission rejects pending PRE even in FULL state; locks and export ownership retained')

# Execute the real LAB disable/enable handler: an off/on between recorder chunks
# must leave cancellation latched without stealing the active copy owner's lock.
from test_s3xy_pairing_host import source_block
lab=source_block(source,'static void httpFeatureLab() {')
lab_fixture=r"""
#include <cassert>
#include <cstdint>
static int researchCaptureMux=0,depth=0;
void portENTER_CRITICAL(int*){assert(depth++==0);}void portEXIT_CRITICAL(int*){assert(--depth==0);}
static bool arg=false,labMenuEnabled=true,researchCaptureSnapshotBusy=true,researchCaptureSnapshotCancelled=false,researchCaptureExporting=false;
static int researchCaptureState=2;constexpr int RESEARCH_CAPTURE_CAPTURING=2,RESEARCH_CAPTURE_PAUSED=3;
static int dummy=1;static int*researchCaptureEntries=&dummy;static int*driverMonitorPreRing=&dummy;
bool httpBoolArg(const char*,bool&v){v=arg;return true;}
bool researchCaptureInit(){return true;}bool countryOverrideSetLabEnabledWithBarrier(bool enabled,bool){labMenuEnabled=enabled;return true;}
void driverMonitorCaptureInit(){}void driverMonitorCaptureSuspend(){}void driverWindowLabResetRuntime(){}
const char*v3FeaturePolicyJson(){return "{}";}
struct Server {int status=0;void send(int code,const char*,const char*){assert(depth==0);status=code;}}server;
"""+lab+r"""
int main(){httpFeatureLab();assert(server.status==200&&!labMenuEnabled&&researchCaptureSnapshotCancelled&&researchCaptureSnapshotBusy&&researchCaptureState==RESEARCH_CAPTURE_PAUSED);
arg=true;httpFeatureLab();assert(server.status==200&&labMenuEnabled&&researchCaptureSnapshotCancelled&&researchCaptureSnapshotBusy);}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'lab.cpp').write_text(lab_fixture)
 subprocess.run([os.environ.get('CXX','/usr/bin/g++'),'-std=c++17','-Wall','-Wextra','-Werror',str(p/'lab.cpp'),'-o',str(p/'lab')],check=True)
 subprocess.run([str(p/'lab')],check=True)
print('PASS: actual LAB off/on handler latches snapshot cancellation without clearing owner busy')
