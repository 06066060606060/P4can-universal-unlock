const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../dashboard_source.html'),'utf8');
const code=html.slice(html.indexOf('// R79_TIMING_CAPTURE_BEGIN'),html.indexOf('// R79_TIMING_CAPTURE_END'));
const nodes=new Map();
for(const id of ['r79TimingState','r79TimingCount','r79TimingDropped','r79TimingElapsed','r79TimingStart','r79TimingStop','r79TimingDownload','r79TimingJson','r79TimingWarnings'])nodes.set(id,{disabled:false,textContent:'',classList:{toggle(name,on){this.hidden=on}}});
let current={session:0,active:false,count:0,capacity:32768,dropped:0,elapsedMs:0},fail=false,posts=[];
const ctx={$:id=>nodes.get(id),jget:async()=>({...current}),post:async url=>{posts.push(url);if(fail)throw Error('network');current={...current,session:1,active:url.endsWith('/start')};},downloadFile:async()=>{}};
vm.createContext(ctx);vm.runInContext(code,ctx);
(async()=>{
 ctx.renderR79TimingCapture(current);assert(nodes.get('r79TimingStop').disabled);assert(nodes.get('r79TimingDownload').disabled);assert(!nodes.get('r79TimingStart').disabled);
 await ctx.r79TimingCaptureAction('start');assert.equal(posts[0],'/api/r79/timing/start');assert(nodes.get('r79TimingStart').disabled);assert(!nodes.get('r79TimingStop').disabled);assert(nodes.get('r79TimingDownload').disabled);
 current={...current,schema:2,bootId:17,count:32768,dropped:9,elapsedMs:12150,driverErrorLost:3,driverSnapshotFailures:2,driverSequenceSaturated:true,driverImportPending:true};await ctx.fetchR79TimingCapture();assert.equal(nodes.get('r79TimingDropped').textContent,'9');assert(nodes.get('r79TimingElapsed').textContent.includes('12.2'));
 const warnings=nodes.get('r79TimingWarnings').textContent;assert.match(warnings,/9.*dropped/i);assert.match(warnings,/3.*CAN 2.*lost/i);assert.match(warnings,/2.*snapshot/i);assert.match(warnings,/saturat/i);assert.match(warnings,/pending/i);assert.equal(nodes.get('r79TimingWarnings').classList.hidden,false,'Loss warnings must be visible');
 current={...current,dropped:0,driverErrorLost:0,driverSnapshotFailures:0,driverSequenceSaturated:false,driverImportPending:false};await ctx.fetchR79TimingCapture();assert.equal(nodes.get('r79TimingWarnings').textContent,'','A clean refreshed status must clear all prior loss warnings');assert.equal(nodes.get('r79TimingWarnings').classList.hidden,true,'Empty warnings must not change the card spacing');
 await ctx.r79TimingCaptureAction('stop');assert.equal(posts[1],'/api/r79/timing/stop');assert(!nodes.get('r79TimingDownload').disabled);assert(nodes.get('r79TimingStop').disabled);
 fail=true;await ctx.r79TimingCaptureAction('start');assert(nodes.get('r79TimingState').textContent.includes('failed'));assert(!nodes.get('r79TimingStart').disabled);
 console.log('PASS: actual timing controls, Start/Stop routes, state transitions, overflow and retry after errors');
})().catch(e=>{console.error(e);process.exit(1)});
