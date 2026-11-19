const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(path.join(__dirname,'../dashboard_source.html'),'utf8');
const source=html.slice(html.indexOf('async function downloadFile('),html.indexOf('function fmtUptime('));
const flush=async()=>{for(let n=0;n<30;n++)await Promise.resolve()};
function fixture(fetch){
 let now=1000,next=0;const timers=new Map(),saved=[],errors=[],signals=[];let polls=0,cancelled=0;
 const ctx={downloadInProgress:false,downloadManaged:false,downloadStartedAt:0,downloadProgress:null,lastOk:0,
  Date:{now:()=>now},AbortController,Blob,TextDecoder,console,
  setTimeout(fn,ms){const id=++next;timers.set(id,{at:now+ms,fn});return id},clearTimeout(id){timers.delete(id)},
  dashboardFetch(url,options){signals.push(options.signal);return fetch(url,options)},setConn(){},
  alert:message=>errors.push(message),forcePoll:()=>polls++};
 vm.createContext(ctx);vm.runInContext(source,ctx);ctx.saveDownloadedBlob=(blob,name)=>saved.push({blob,name});
 return {ctx,saved,errors,signals,timers,get polls(){return polls},
  async advance(ms){const end=now+ms;for(;;){await flush();let choice;for(const [id,t] of timers)if(t.at<=end&&(!choice||t.at<choice[1].at))choice=[id,t];if(!choice)break;now=choice[1].at;timers.delete(choice[0]);choice[1].fn()}now=end;await flush()},
  reader(read){return {read,cancel(){cancelled++;return Promise.resolve()},releaseLock(){}}},get cancelled(){return cancelled}};
}
function response(reader,headers={}){return {ok:true,status:200,headers:{get:key=>headers[key]||null},body:reader?{getReader:()=>reader}:null,blob:()=>Promise.resolve(new Blob(['fallback']))}}
async function stalled(kind,research=false){
 const never=new Promise(()=>{});let f;
 f=fixture(()=>kind==='headers'?never:Promise.resolve(kind==='blob'?{...response(null),blob:()=>never}:response(f.reader(()=>never),{'Content-Length':'100'})));
 const done=research?f.ctx.downloadResearchCaptureCsv():f.ctx.downloadFile('/export','test.csv','Test');
 await flush();assert(f.ctx.downloadInProgress);await f.advance(60000);
 assert.equal(f.ctx.downloadInProgress,false,`${kind}: a stalled download must release polling`);
 assert.equal(f.ctx.downloadManaged,false);assert(f.signals[0]?.aborted,'Abort network request on timeout');
 assert.equal(f.saved.length,0,'Never save partial data');assert.equal(f.errors.length,1);assert.match(f.errors[0],/retry/i);assert(f.polls>0);
 await done;assert.equal(f.timers.size,0,'No orphan watchdog');
 // A fresh retry must work and must not inherit an earlier watchdog.
 f.ctx.dashboardFetch=async()=>response(null);await flush();const retry=f.ctx.downloadFile('/export','retry.csv','Test');await f.advance(1000);await retry;assert.equal(f.saved.length,1);assert.equal(f.saved[0].name,'retry.csv');
}
(async()=>{
 for(const research of [false,true])for(const kind of ['headers','stream','blob'])await stalled(kind,research);
 for(const research of [false,true]){
  let resolveRead;const f=fixture(()=>Promise.resolve(response(f.reader(()=>new Promise(r=>resolveRead=r)),research?{'X-P4-CAN-CSV-Rows':'100000'}:{'Content-Length':'100000'})));
  const done=research?f.ctx.downloadResearchCaptureCsv():f.ctx.downloadFile('/export','test.csv','Test');await flush();
  // Each small positive chunk must refresh idle time even when percent stays 0.
  for(let n=0;n<6;n++){await f.advance(10000);assert(f.ctx.downloadInProgress);resolveRead({done:false,value:new Uint8Array([49,10])});await flush()}
  assert.equal(f.signals[0].aborted,false,'Progressing downloads may exceed total timeout');
  const duplicate=f.ctx.downloadFile('/other','duplicate.csv','Test');await duplicate;assert.equal(f.signals.length,1);
  resolveRead({done:true});await f.advance(1000);await done;assert.equal(f.saved.length,1);assert.equal(await f.saved[0].blob.text(),'1\n'.repeat(6));assert.equal(f.errors.length,0);assert(!f.ctx.downloadInProgress);assert(f.polls>0);
 }
 // Unknown-length streams still receive per-chunk deadlines, and success preserves bytes.
 let readCount=0;const f=fixture(()=>Promise.resolve(response(f.reader(async()=>++readCount===1?{done:false,value:new Uint8Array([97,98])}:{done:true}))));
 const done=f.ctx.downloadFile('/chunked','chunked.csv','Test');await f.advance(1000);await done;assert.equal(await f.saved[0].blob.text(),'ab');
 const fail=fixture(async()=>({...response(null),ok:false,status:503}));const failed=fail.ctx.downloadFile('/busy','busy.csv','Test');await fail.advance(1000);await failed;assert.equal(fail.saved.length,0);assert.match(fail.errors[0],/503/);assert(!fail.ctx.downloadInProgress);
 console.log('PASS: production download header/body/blob stalls abort, restore polling, notify and retry; progress, overlap, unknown length and HTTP failures');
 // Browser-native ReadableStream and AbortController must also unwind a pending read.
 const {chromium}=require('playwright');
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||chromium.executablePath(),headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.route('**/*',route=>route.abort());
  await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''));
  await page.clock.install();
  await page.evaluate(code=>{
   Object.assign(window,{downloadInProgress:false,downloadManaged:false,downloadStartedAt:0,downloadProgress:null,lastOk:0});
   window.result={polls:0,errors:[],saved:0,cancelled:0};
   window.forcePoll=()=>result.polls++;
   window.alert=message=>result.errors.push(message);
   window.setConn=()=>{};
   window.dashboardFetch=async(url,options)=>{
    window.downloadSignal=options.signal;
    return new Response(new ReadableStream({start(c){window.streamController=c},cancel(){result.cancelled++}}),{headers:{'Content-Length':'100'}});
   };
   (0,eval)(code);
   window.saveDownloadedBlob=()=>result.saved++;
   window.downloadTask=downloadFile('/local-fixture','test.csv','Test');
  },source);
  await page.waitForFunction(()=>!!window.streamController);
  await page.clock.fastForward(16000);
  await page.evaluate(()=>downloadTask);
  // Cleanup schedules polling for the next task; settle that explicit timer
  // before inspecting counters rather than racing the browser event loop.
  await page.clock.runFor(1);
  const result=await page.evaluate(()=>({...result,busy:downloadInProgress,aborted:downloadSignal.aborted}));
  assert(!result.busy&&result.aborted&&result.polls>0&&result.cancelled>0,JSON.stringify(result));assert.equal(result.saved,0);assert.match(result.errors[0],/retry/);
  console.log('PASS: browser native stream timeout aborts/cancels and restores polling without saving partial CSV');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
