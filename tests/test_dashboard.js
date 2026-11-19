const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../dashboard_source.html'),'utf8');
const blocks=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const main=blocks.find(x=>x.includes('function renderHomeFast'));
const roleNodes={1:[],2:[],3:[]};
for(const m of html.replace(/<script[^>]*>[\s\S]*?<\/script>/g,'').matchAll(/data-can-role="([123])"/g))roleNodes[Number(m[1])].push({textContent:''});
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{id,dataset:{},style:{},disabled:false,textContent:'',className:'',classList:{toggle(){},add(){},remove(){}}});return elements.get(id);}
for(const m of html.matchAll(/id="([^"]+)"/g))element(m[1]);
const profiles=['MODEL_YL','MODEL_Y_JUNIPER','MODEL_Y_LEGACY','MODEL_3_HIGHLAND','MODEL_3_LEGACY'].map((vehicle,i)=>Object.assign(element('vehicle'+i),{dataset:{vehicle}}));
const turns=['STALK','STALKLESS'].map(turn=>Object.assign(element(turn),{dataset:{turn}}));
const document={getElementById:id=>elements.get(id)||null,querySelectorAll:q=>q==='.vehicleChoice'?profiles:q==='.turnChoice'?turns:[],body:element('body')};
const baseQuerySelectorAll=document.querySelectorAll;document.querySelectorAll=q=>{const role=q.match(/data-can-role="([123])"/);return role?roleNodes[Number(role[1])]:baseQuerySelectorAll(q)};
for(let n=1;n<=3;n++)element('homeCan'+n+'Name').querySelector=()=>element('homeCan'+n+'Role');
let profileScript=blocks.find(x=>x.includes('const PROFILES='));
profileScript=profileScript.replace('  boot();','  profileStatusReady=true; profileStatus={nvsError:false};');
const context={$:id=>elements.get(id)||null,document,window:{},console,setTimeout(){},clearTimeout(){}};
vm.createContext(context);vm.runInContext(main.slice(main.indexOf('function physicalCanRole'),main.indexOf('function diagValue')),context);vm.runInContext(profileScript,context);
for(let i=0;i<profiles.length;i++){
 profiles[i].onclick();
 if(i===3){assert(element('saveProfileBtn').disabled);turns[1].onclick();}
 assert(!element('saveProfileBtn').disabled,'Profile must be selectable with all 3 buses');
 assert.equal(element('setupCanSummary').textContent,i===0?'CAN 1 VEHICLE · CAN 2 BODY · CAN 3 PARTY':'CAN 1 BODY · CAN 2 CHASSIS · CAN 3 PARTY');
 element('saveProfileBtn').onclick();
 const expected=i===0?['VEHICLE','BODY','PARTY']:['BODY','CHASSIS','PARTY'];
 assert(element('profileConfirmSummary').textContent.includes(i===0?'CAN 1 VEHICLE / CAN 2 BODY / CAN 3 PARTY':'CAN 1 BODY / CAN 2 CHASSIS / CAN 3 PARTY'),'Profile confirmation must identify the actual physical buses');
 context.renderPhysicalCanLabels(i+1);
 for(let n=1;n<=3;n++){
  assert.equal(context.physicalCanRole(n,i+1),expected[n-1]);
  assert.equal(element('homeCan'+n+'Name').dataset.role,expected[n-1]);
  assert.equal(element('homeCan'+n+'Role').textContent,expected[n-1]);
  assert(roleNodes[n].length>=3,'Home Details, GPIO cards and Diagnostics need profile-aware roles for CAN '+n);
  for(const label of roleNodes[n])assert.equal(label.textContent,expected[n-1]);
 }
}
// Execute the actual home renderer with physical bus data and strict DOM lookup.
let render=main.slice(main.indexOf('function renderHomeFast'),main.indexOf('function renderHomeSlow'));
Object.assign(context,{$:id=>elements.get(id)||null,nagCfg:{method:0},fmtMs:n=>n+' ms',renderApPresentation(){},renderHomeBlinkerState(){},renderR79Summary(){}});
vm.runInContext(render,context);
const t={};for(let n=1;n<=3;n++){t['can'+n+'State']=1;t['can'+n+'Ready']=true;t['can'+n+'TrafficSeen']=true;t['can'+n+'TrafficOnline']=n!==2;t['can'+n+'TrafficAgeMs']=n===2?5000:10;}
context.renderHomeFast({cantraffic:t,nag:{torque:1,apActive:true},blink:{},summon:{},r79:{}});
assert.equal(element('can1Traffic').textContent,'LIVE');assert.equal(element('can2Traffic').textContent,'NO DATA');assert.equal(element('can3Traffic').textContent,'LIVE');
console.log('PASS: actual dashboard profile selection for all five models, Highland choice, three home traffic states');
// Exercise the real diagnostics renderer with independent physical counters.
const diagnostics=main.slice(main.indexOf('function diagValue'),main.indexOf('function fmtMs'));
context.fmtUptime=n=>n+' s';vm.runInContext(diagnostics,context);
const stats={fwVersion:'test-net2',networkState:'READY',hostedHostVersion:'2.6.1',hostedC6Version:'2.6.0'};
for(let n=1;n<=3;n++)Object.assign(stats,{
 ['can'+n+'State']:n===2?2:1,['can'+n+'Ready']:n!==2,['can'+n+'StatusSeen']:true,['can'+n+'StatusAgeMs']:25,
 ['can'+n+'RxCount']:100*n,['can'+n+'RxPolls']:1000*n,['can'+n+'RxResult']:'ESP_ERR_TIMEOUT',
 ['can'+n+'InitResult']:'ESP_OK',['can'+n+'Mode']:'NORMAL',['can'+n+'Controller']:n-1,
 ['can'+n+'TxPin']:[20,50,26][n-1],['can'+n+'RxPin']:[21,49,27][n-1],['can'+n+'Tec']:n,['can'+n+'Rec']:n+10
});
Promise.resolve().then(()=>{
 context.renderSystemDiagnostics(stats);
 for(let n=1;n<=3;n++){
  assert(element('diagCan'+n+'Rx').textContent.startsWith(String(100*n)+' /'));
  assert(element('diagCan'+n+'Polls').textContent.startsWith(String(1000*n)+' /'));
  assert.equal(element('diagCan'+n+'Errors').textContent,n+' / '+(n+10));
 }
 assert(element('diagCan2State').textContent.startsWith('BUS OFF'));
 assert.equal(element('diagHostedVersion').textContent,'2.6.1 / 2.6.0');
 console.log('PASS: full system diagnostics render three independent physical buses and Hosted versions');
});
// Always-visible navigation lists must never impersonate an active detail panel.
{
 const calls=[],detail={id:'panelR79'},pollContext={
  document:{hidden:false,querySelector:()=>null},
  currentPage:'settings',otaUploading:false,downloadInProgress:false,settingsLiteValid:true,
  dashboardPollMs:500,pollLast:{},Date,activeDiagSection:'',window:{__refreshFeatures:()=>calls.push('refreshFeatures')},
  activeDiagBody:()=>pollContext.activeDiagSection?{dataset:{diagSection:pollContext.activeDiagSection}}:null,
 };
 for(const name of ['fetchNag','fetchBlink','fetchSum','fetchR79','fetchR79ApControl','fetchSys','fetchS3','fetchContinuousAp','fetchVisionControlLab','fetchCountryOverrideLab','fetchNagHumanLab','fetchPedalMap','fetchLab','fetchResearchCapture','fetchSettingsSnapshot','fetchHeartbeat','fetchDriverMonitoringControl','fetchIsaSuppressionControl','fetchHomeSnapshot','fetchPreheat'])pollContext[name]=()=>{calls.push(name)};
 vm.createContext(pollContext);
 vm.runInContext(main.slice(main.indexOf('function activePanelId'),main.indexOf('function forcePoll')),pollContext);
 pollContext.pollTick(true);
 assert(!calls.some(name=>['fetchNag','fetchBlink','fetchSum','fetchR79','fetchSys','fetchS3'].includes(name)),'Settings root must not poll hidden detail content');
 assert(calls.includes('fetchDriverMonitoringControl')&&calls.includes('fetchIsaSuppressionControl')&&calls.includes('refreshFeatures'),'Visible inline Settings controls refresh their saved state');
 pollContext.document.querySelector=q=>q==='.panel.show'?detail:null;calls.length=0;pollContext.pollTick(true);
 assert.deepEqual(calls,['fetchR79','fetchR79ApControl'],'Only the visible R79 detail polls');
 detail.id='panelWireless';calls.length=0;pollContext.pollTick(true);
 assert.deepEqual(calls,['fetchS3'],'Switching details stops old requests');
 detail.id='panelDiag';pollContext.activeDiagSection='';
 let heartbeatNow=300000;pollContext.Date={now:()=>heartbeatNow};pollContext.pollLast.heartbeat=heartbeatNow-3000;calls.length=0;pollContext.pollTick(true);
 assert.deepEqual(calls,['fetchHeartbeat'],'All collapsed Diagnostics keeps the transport heartbeat without polling stats');
 detail.id='panelCanGpio';calls.length=0;heartbeatNow+=3000;pollContext.pollTick();assert.deepEqual(calls,['fetchHeartbeat'],'CAN GPIO keeps the transport heartbeat without repolling configuration');detail.id='panelDiag';
 calls.length=0;heartbeatNow+=2999;pollContext.pollTick();assert.deepEqual(calls,[],'Closed Diagnostics heartbeat waits the full 3000ms');
 heartbeatNow++;pollContext.pollTick();assert.deepEqual(calls,['fetchHeartbeat'],'Closed Diagnostics heartbeat refreshes at 3000ms');pollContext.Date=Date;
 for(const section of ['system','memory','wireless','ble','can1','can2','can3','recovery']){
  pollContext.activeDiagSection=section;calls.length=0;pollContext.pollTick(true);
  assert.deepEqual(calls,['fetchSys'],'Only the single open Diagnostics category polls');
 }
 let clockNow=160000;pollContext.Date={now:()=>clockNow};pollContext.pollLast.sys=clockNow;calls.length=0;
 clockNow+=1599;pollContext.pollTick();assert.deepEqual(calls,[],'Selected Diagnostics waits the full 1600ms interval');
 clockNow++;pollContext.pollTick();assert.deepEqual(calls,['fetchSys'],'Selected Diagnostics refreshes at 1600ms');pollContext.Date=Date;
 pollContext.document.hidden=true;calls.length=0;pollContext.pollTick(true);assert.deepEqual(calls,[],'Hidden documents never poll Diagnostics');pollContext.document.hidden=false;
 pollContext.document.querySelector=()=>({id:'panelBatteryPreheat'});pollContext.currentPage='settings';calls.length=0;pollContext.pollTick(true);
 assert.deepEqual(calls,['fetchPreheat'],'Only visible Actions polls preheat');
 console.log('PASS: navigation lists are passive; only active details and Actions poll');
}
// Missing measurements are unknown; stale physical-controller status is explicit.
Promise.resolve().then(()=>{
 const missing={can1State:1,can1StatusSeen:true,can1StatusAgeMs:2100,can1Ready:true};
 context.renderCanDiagnostics(missing);
 assert(element('diagCan1State').textContent.includes('STALE'));
 assert.equal(element('diagCan1Errors').textContent,'— / —');
 assert.equal(element('diagCan1Mode').textContent,'— · —');
 assert.equal(element('diagCan1Tx').textContent,'— / —');
 context.renderSystemDiagnostics({internalRamFreeBytes:1024,internalRamMinFreeBytes:512,internalRamLargestBlockBytes:256,psramFreeBytes:null,psramTotalBytes:null});
 assert.equal(element('sysPsram').textContent,'— / —');
 console.log('PASS: unknown memory/CAN metrics and stale physical status');
});
// Detail entry aliases and inline aliases must retain their respective targets.
{
 const calls=[],listeners=[],state={textContent:''};
 const panel={addEventListener:(name,fn)=>listeners.push({name,fn}),querySelector:q=>q==='.settingsSaveState'?state:null};
 const targets=new Map([...elements].map(([id])=>[id,{id,tagName:'INPUT',focus:()=>calls.push(['focus',id]),scrollIntoView:()=>calls.push(['scroll',id]),closest(){return this},querySelector(){return this},getAttribute:()=>null,matches:()=>true}]));
 const ctx={document:{querySelectorAll:q=>q==='.panel'?[panel]:[],querySelector:()=>null},$:id=>targets.get(id)||null,showPage:page=>calls.push(['page',page]),openPanel:id=>calls.push(['panel',id]),setTimeout:fn=>fn()};
 vm.createContext(ctx);vm.runInContext(main.slice(main.indexOf('function openSettingsItem'),main.indexOf('// Save feedback belongs')),ctx);
 for(const id of ['panelNag','panelR79','panelWireless']){
  calls.length=0;assert(ctx.openSettingsItem(id));assert.deepEqual(calls,[['page','settings'],['panel',id]]);
 }
 for(const alias of ['isaSuppressionRow','driverMonitoringRow','appearance','refresh']){
  calls.length=0;assert(ctx.openSettingsItem(alias));assert.deepEqual(calls[0],['page','settings']);
  assert(!calls.some(c=>c[0]==='panel'),'Inline aliases must leave the Settings root visible');
  assert(calls.some(c=>c[0]==='scroll'||c[0]==='focus'),'Inline aliases locate a visible root control');
 }
 assert.equal(ctx.openSettingsItem('missingPanel'),false);
 ctx.setupSettingsPanels();assert.equal(listeners.length,1);assert.equal(listeners[0].name,'input');
 listeners[0].fn({target:{matches:()=>true}});assert.equal(state.textContent,'Unsaved · use Apply where shown');
 state.textContent='Saved';listeners[0].fn({target:{matches:()=>false}});assert.equal(state.textContent,'Saved','Checkbox input must retain its save state');
 console.log('PASS: retained detail navigation, inline root aliases and originating input feedback');
}
// Execute supplied Actions controls and full Thermal renderer with real source fields.
{
 const own=new Map();for(const id of elements.keys())own.set(id,{id,textContent:'',disabled:false,checked:false,dataset:{},style:{},classList:{toggle(){}},children:[],querySelector:()=>null,closest:()=>null,previousElementSibling:null,parentNode:{querySelectorAll:()=>[]},setAttribute(){},appendChild(n){this.children.push(n)}});
 const target=own.get('preheatTargetC');target.options=[20,25,30,35,40,45,50].map(n=>({value:n.toFixed(1),dataset:{}}));
 const posts=[],ctx={$:id=>own.get(id)||null,document:{activeElement:null},setInterval(){},window:{matchMedia:()=>({matches:false})},Date,featurePostJson:async url=>{posts.push(url);return {...state,enabled:new URL('http://test'+url).searchParams.get('enabled')==='1',targetC:Number(new URL('http://test'+url).searchParams.get('targetC'))||40}},jget:async()=>state};
 const state={supported:true,enabled:true,active:true,blocked:true,blockedReason:'NO_TRIP_ID',targetC:40,packSeen:true,packTempMinC:18,packTempMaxC:22,packTempAvgC:20,evalAgeMs:0,thModeAgeMs:0,thValveMode:1,thVitalsAgeMs:0,thPumpBatRpm:1200,thPumpPtRpm:900};
 vm.createContext(ctx);vm.runInContext(main.slice(main.indexOf('let preheatSaved='),main.indexOf("if($('countryOverrideMode'))")),ctx);
 ctx.renderPreheat(state);assert.equal(own.get('preheatStatus').textContent,'No trip frame');assert(own.get('preheatToggle').checked);assert.equal(target.value,'40.0');assert.equal(own.get('thModeChip').textContent,'Parallel');assert.equal(own.get('thPumpBat').textContent,'1200');assert(own.get('preheatTempValue').textContent.includes('20.0'));
 ctx.renderPreheat({...state,evalAgeMs:4000});assert.equal(own.get('preheatStatus').textContent,'No CAN data');
 ctx.renderPreheat({...state,enabled:false,active:false,autoOffReason:'STATOR_STALL'});assert.equal(own.get('preheatStatus').textContent,'Stall auto-off');
 ctx.renderPreheat(state);own.get('preheatToggle').checked=false;
 Promise.resolve(ctx.updatePreheat()).then(async()=>{assert(posts[0].includes('enabled=0'));target.value='45.0';await ctx.updatePreheatTarget();assert(posts.some(u=>u.includes('targetC=45.0')));console.log('PASS: actual preheat status, source telemetry, Thermal valves/pumps and saved engine/target commands')}).catch(e=>{console.error(e);process.exitCode=1});
}
// Execute the actual async stats fetcher with controllable completions. A
// section response must belong to the currently visible selection generation.
(async()=>{
 const own=new Map([...elements.keys()].map(id=>[id,{id,textContent:'',className:'',classList:{toggle(){},add(){},remove(){}}}]));
 const fresh=Object.fromEntries(['memory','can2'].map(section=>[section,{textContent:'Open to refresh'}]));
 const bodies=Object.fromEntries(Object.keys(fresh).map(section=>[section,{dataset:{diagSection:section},querySelector:()=>fresh[section]}]));
 const pending=[];let shown=true;
 const ctx={document:{hidden:false},currentPage:'settings',activeDiagSection:'memory',diagSelectionGeneration:1,lastSys:null,
  $:id=>own.get(id)||null,fmtUptime:n=>n+' s',fmtMs:n=>n+' ms',Date,
  activeDiagBody:()=>shown&&ctx.currentPage==='settings'&&!ctx.document.hidden?bodies[ctx.activeDiagSection]||null:null,
  jget:url=>new Promise((resolve,reject)=>pending.push({url,resolve,reject}))};
 vm.createContext(ctx);vm.runInContext(diagnostics,ctx);
 own.get('sysInternalRam').textContent='unchanged';
 let old=ctx.fetchSys();assert.equal(pending[0].url,'/api/system/stats?section=memory');
 assert.equal(pending.length,1);await ctx.fetchSys();assert.equal(pending.length,1,'Same selection never overlaps stats requests');
 ctx.activeDiagSection='can2';ctx.diagSelectionGeneration++;
 let current=ctx.fetchSys();assert.equal(pending[1].url,'/api/system/stats?section=can2','CAN fetches the complete selected physical bus without view');
 pending[1].resolve({can2State:1,can2Ready:true,can2StatusSeen:true,can2StatusAgeMs:10,can2RxCount:222});await current;
 const activeStatus=fresh.can2.textContent;assert(own.get('diagCan2Rx').textContent.startsWith('222 /'));
 pending[0].resolve({internalRamFreeBytes:111000});await old;
 assert.equal(own.get('sysInternalRam').textContent,'unchanged');assert.equal(fresh.can2.textContent,activeStatus,'Old reply cannot alter current freshness');
 ctx.activeDiagSection='memory';ctx.diagSelectionGeneration++;old=ctx.fetchSys();
 ctx.activeDiagSection='';ctx.diagSelectionGeneration++;await ctx.fetchSys();assert.equal(pending.length,3,'All-closed state never requests stats');
 ctx.activeDiagSection='memory';ctx.diagSelectionGeneration++;current=ctx.fetchSys();assert.equal(pending.length,4,'A reopened section is allowed to request before the old reply');
 pending[3].resolve({internalRamFreeBytes:333000,internalRamMinFreeBytes:280000});await current;
 const newMemory=own.get('sysInternalRam').textContent,newFreshness=fresh.memory.textContent;
 pending[2].resolve({internalRamFreeBytes:111000,internalRamMinFreeBytes:1});await old;
 assert.equal(own.get('sysInternalRam').textContent,newMemory,'Same section reopening rejects its previous generation');assert.equal(ctx.lastSys.internalRamFreeBytes,333000);assert.equal(fresh.memory.textContent,newFreshness);
 await ctx.fetchSys({fwVersion:'prefetched-fw',internalRamFreeBytes:999000,internalRamMinFreeBytes:1});
 assert.equal(own.get('sysInternalRam').textContent,newMemory,'A late prefetched Settings/Home snapshot cannot replace active Diagnostics');assert(own.get('sysFw').textContent.includes('prefetched-fw'),'Prefetched firmware data remains available to Settings');
 old=ctx.fetchSys();shown=false;ctx.diagSelectionGeneration++;pending[4].reject(new Error('old selection failed'));await old;
 assert.equal(fresh.memory.textContent,'Refreshing…','A stale failure cannot mark a hidden selection unavailable');
 await ctx.fetchSys();assert.equal(pending.length,5,'Hidden Diagnostics never requests stats');
 ctx.activeDiagSection='';await ctx.fetchSys({fwVersion:'home-fw',internalRamFreeBytes:777000,internalRamMinFreeBytes:1});assert(own.get('sysFw').textContent.includes('home-fw'),'Existing Home/Settings prefetched updates remain');
 console.log('PASS: actual async section fetch, full selected CAN, generation fences for switch/reopen/hidden/error, and prefetched firmware preservation');
})().catch(e=>{console.error(e);process.exitCode=1});
// Wrong A/B routing, unmanaged event handlers or lost finally cleanup must
// fail through the actual label, click, download and polling functions.
(async()=>{
 const own=new Map([...elements.keys()].map(id=>[id,{id,textContent:'',className:'',dataset:{}}]));
 const role={textContent:''},indicators=[{textContent:'',className:''},{textContent:'',className:''}];
 for(let n=1;n<=3;n++)own.get('homeCan'+n+'Name').querySelector=selector=>selector==='.homeBusRole'?role:null;
 const requests=[],saved=[];let clockNow=10000,watchdog,polls=0;
 const ctx={
  $:id=>own.get(id)||null,window:{},Blob,AbortController,TextDecoder,alert(){},Date:{now:()=>clockNow},
  document:{hidden:false,querySelector:()=>({id:'panelDiag'}),querySelectorAll:selector=>selector==='[data-conn]'?indicators:selector==='[data-can-role="2"]'?[role]:[]},
  currentPage:'settings',otaUploading:false,otaUiPhase:'idle',downloadInProgress:false,downloadManaged:false,downloadProgress:null,downloadStartedAt:0,lastOk:clockNow,
  pollLast:{},activeDiagBody:()=>({dataset:{diagSection:'recovery'}}),fetchSys:()=>polls++,
  dashboardFetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject})),
  saveDownloadedBlob:(blob,name)=>saved.push({blob,name}),setInterval:fn=>{watchdog=fn},setTimeout:(fn,ms)=>{if(!ms)fn();return 1},clearTimeout(){},
 };
 vm.createContext(ctx);
 vm.runInContext(main.slice(main.indexOf('function physicalCanRole'),main.indexOf('function diagValue')),ctx);
 vm.runInContext(main.slice(main.indexOf('function setConn'),main.indexOf('function fmtUptime')),ctx);
 ctx.saveDownloadedBlob=(blob,name)=>saved.push({blob,name});
 vm.runInContext(main.slice(main.indexOf('function activePanelId'),main.indexOf('setupSettingsPanels();')),ctx);
 for(const id of ['diagCanATxCsv','diagCanBTxCsv','diagCanErrorsJson']){
  const wire=main.match(new RegExp("\\$\\('"+id+"'\\)\\.onclick=[^;]+;"));assert(wire,id+' must be wired');vm.runInContext(wire[0],ctx);
 }
 for(const [profile,a,b] of [[1,'CAN 3 TX CSV','CAN 1 TX CSV'],[2,'CAN 1 TX CSV','CAN 2 TX CSV'],[3,'CAN 1 TX CSV','CAN 2 TX CSV'],[4,'CAN 1 TX CSV','CAN 2 TX CSV'],[5,'CAN 1 TX CSV','CAN 2 TX CSV']]){
  ctx.renderPhysicalCanLabels(profile);assert.equal(own.get('diagCanATxCsv').textContent,a);assert.equal(own.get('diagCanBTxCsv').textContent,b);
 }
 const flush=async()=>{for(let n=0;n<30;n++)await Promise.resolve()};
 const cases=[['diagCanATxCsv','/api/system/cana-tx.csv','P4-CAN_CANA_TX_TRACE.csv'],['diagCanBTxCsv','/api/system/canb-tx.csv','P4-CAN_CANB_TX_TRACE.csv'],['diagCanErrorsJson','/api/system/can-errors.json','P4-CAN_CAN_ERRORS.json']];
 for(const [id,url,filename] of cases){
  const beforePolls=polls,beforeRequests=requests.length,done=own.get(id).onclick(),request=requests.at(-1);
  assert.equal(request.url,url);assert.equal(request.options.cache,'no-store');
  assert(ctx.downloadInProgress&&ctx.downloadManaged);assert.equal(ctx.downloadProgress,0);
  clockNow+=5000;watchdog();ctx.pollTick(true);
  assert(indicators.every(e=>e.textContent==='Downloading… 0%'&&e.className==='live busy'),'Held download stays busy after the connection watchdog threshold');
  assert.equal(polls,beforePolls,'Downloads suppress forced polling');
  await own.get(id==='diagCanATxCsv'?'diagCanBTxCsv':'diagCanATxCsv').onclick();assert.equal(requests.length,beforeRequests+1,'A second trace click cannot overlap the active download');
  const reads=[],body=id==='diagCanErrorsJson'?'{"ok":1}':'a,b\n1,2\n',payload=Uint8Array.from(Buffer.from(body));
  request.resolve({ok:true,status:200,headers:{get:key=>key==='Content-Length'?'8':key==='Content-Type'?(id==='diagCanErrorsJson'?'application/json':'text/csv'):null},body:{getReader:()=>({read:()=>new Promise(resolve=>reads.push(resolve)),cancel:async()=>{},releaseLock(){}})}});
  await flush();reads[0]({done:false,value:payload.slice(0,4)});await flush();
  assert.equal(ctx.downloadProgress,50);assert(indicators.every(e=>e.textContent==='Downloading… 50%'));
  ctx.pollTick(true);assert.equal(polls,beforePolls,'Body consumption also suppresses polling');
  reads[1]({done:false,value:payload.slice(4)});await flush();reads[2]({done:true});await done;
  assert.equal(saved.at(-1).name,filename);assert.equal(await saved.at(-1).blob.text(),body);assert.equal(saved.at(-1).blob.type,id==='diagCanErrorsJson'?'application/json':'text/csv');
  assert(!ctx.downloadInProgress&&!ctx.downloadManaged);assert.equal(ctx.downloadProgress,null);
  assert(indicators.every(e=>e.textContent==='Connected'&&e.className==='live ok'));assert.equal(polls,beforePolls+1,'Successful exports resume actual selected-section polling');
  const savedBefore=saved.length,failed=own.get(id).onclick();requests.at(-1).resolve({ok:false,status:503});await failed;
  assert.equal(saved.length,savedBefore,'HTTP failure must not save a diagnostic file');assert(!ctx.downloadInProgress&&!ctx.downloadManaged);assert.equal(ctx.downloadProgress,null);assert.equal(polls,beforePolls+2,'Failed exports also resume polling');
  const disconnected=own.get(id).onclick();requests.at(-1).reject(new Error('offline peer disconnected'));await disconnected;
  assert.equal(saved.length,savedBefore,'Transport failure must not save a diagnostic file');assert(!ctx.downloadInProgress&&!ctx.downloadManaged);assert.equal(ctx.downloadProgress,null);assert.equal(polls,beforePolls+3,'Transport failure must release polling ownership');
 }
 console.log('PASS: actual physical TX labels, managed A/B CSV and CAN-error JSON routing and filenames, streamed progress, held-download polling/watchdog, overlap guard and success/failure cleanup');
})().catch(e=>{console.error(e);process.exitCode=1});

// Frozen listen-only counters must not look like evidence of repaired wiring.
for(let n=1;n<=3;n++)element('diagCan'+n+'ErrorNote');
context.renderCanDiagnostics({can2State:1,can2Ready:true,can2StatusSeen:true,can2StatusAgeMs:0,can2Mode:'LISTEN_ONLY',can2ErrorCountersFrozen:true,can2Tec:0,can2Rec:0});
assert(element('diagCan2ErrorNote').textContent.includes('frozen'),'Listen-only zero TEC/REC needs a visible frozen-counter explanation');
context.renderCanDiagnostics({can2State:1,can2Ready:true,can2StatusSeen:true,can2StatusAgeMs:0,can2Mode:'NORMAL',can2ErrorCountersFrozen:false});
assert(!element('diagCan2ErrorNote').textContent.includes('frozen'),'NORMAL mode must retain the ordinary counter description');

async function verifyFixedR79Controls(){
 const own=new Map(['r79Mode1TxWait','r79Mode1Reinject','r79Mode1DelayMs'].map(id=>[id,{value:'',checked:true}]));
 const sent=[],rendered=[];
 const ctx={$:id=>own.get(id)||null,URLSearchParams,
  post:async url=>{sent.push(new URL(url,'http://p4.local'));return {ok:true,json:async()=>({mode:1})}},
  fetchR79:async result=>rendered.push(result)};
 vm.createContext(ctx);
 const update=main.match(/async function updateR79Settings\(\)\{[^\n]+/);assert(update);
 vm.runInContext(update[0],ctx);
 assert(!html.includes('id="r79Mode"')&&!html.includes('id="r79Mode2Controls"'));
 for(const wait of ['0','1'])for(const reinject of [false,true])for(const delay of ['0','150','340']){
  own.get('r79Mode1TxWait').value=wait;own.get('r79Mode1Reinject').checked=reinject;own.get('r79Mode1DelayMs').value=delay;
  const before=sent.length;await ctx.updateR79Settings();assert.equal(sent.length,before+1);
  const url=sent.at(-1);assert.equal(url.pathname,'/api/r79/update');
  assert.deepEqual([...url.searchParams.keys()],['mode1TxWaitMode','mode1Reinject','mode1DelayMs']);
  assert.equal(url.searchParams.get('mode1TxWaitMode'),wait);assert.equal(url.searchParams.get('mode1Reinject'),reinject?'1':'0');assert.equal(url.searchParams.get('mode1DelayMs'),delay);
 }
 for(const delay of ['','-1','341','1.5','garbage']){
  own.get('r79Mode1DelayMs').value=delay;const before=sent.length;await ctx.updateR79Settings();assert.equal(sent.length,before);
 }
 assert.equal(rendered.length,12);
 console.log('PASS: fixed Mode1 controls preserve wait/reinjection/delay requests and reject invalid input without retired mode parameters');
}
verifyFixedR79Controls().catch(e=>{console.error(e);process.exitCode=1});
