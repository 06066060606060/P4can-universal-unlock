// Offline Chromium verification. No device, serial, network service or CAN access.
const fs=require('fs'),path=require('path'),zlib=require('zlib'),assert=require('assert');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),output=path.resolve(process.argv[2]||'/private/tmp/p4-dashboard-ui');fs.mkdirSync(output,{recursive:true});
const source=fs.readFileSync(path.join(root,'dashboard_source.html'),'utf8');
const embedded=zlib.gunzipSync(Buffer.from([...fs.readFileSync(path.join(root,'index_html.h'),'utf8').matchAll(/0x([0-9A-F]{2})/g)].map(x=>parseInt(x[1],16)))).toString();assert.equal(source,embedded);
const profile={ok:true,setupMode:false,nvsError:false,profile:1,topology:1,turn:1,canA:'PARTY',canB:'VH',canBusCount:3,nagSupported:true,nagTorqueSupported:true,nagTsl9Supported:true,advancedEapSupported:true,euUnlockSupported:true,pedalMapSupported:true,preheatSupported:true};
const features={preheat:true,preheatSupported:true,lab:true,s3xy:true,doorCancel:false,pedalMapSupported:true,apDriveProfileSupported:true,apDriveProfile:false,apDriveProfileRegenRaw:10};
const nag={enabled:false,mode:7,method:0,torque:[],hoRatePct:50,burstMs:100,pauseMs:100,targetId:784,apStateId:921,steeringId:880};
const ble={bluetoothEnabled:true,bleInitialized:true,autoEnabled:true,scanning:false,connectedCount:0,pairedCount:0,devices:[],cryptoSelfTestChecked:true,cryptoSelfTestOk:true};
const r79={mode:1,mode1TxWaitMode:1,mode1ReinjectEnabled:true,mode1DelayMs:150,mode2DelayMs:150};
const traffic={};for(let n=1;n<=3;n++)Object.assign(traffic,{['can'+n+'State']:1,['can'+n+'Ready']:true,['can'+n+'TrafficSeen']:true,['can'+n+'TrafficOnline']:true,['can'+n+'TrafficAgeMs']:12});
const stats={fwVersion:path.basename(root).replace('P4-CAN-Universal-',''),uptimeS:3600,stackCanA:3000,stackCanB:3100,stackCanSup:2900,stackWeb:8000,stackS3xy:5000,internalRamFreeBytes:300000,internalRamMinFreeBytes:280000,internalRamLargestBlockBytes:200000,psramFreeBytes:30000000,psramTotalBytes:33554432,psramMinFreeBytes:29000000,psramLargestBlockBytes:28000000,networkState:'READY',hostedHostVersion:'2.6.1',hostedC6Version:'2.6.0',wifiStarted:true,apStarted:true,apIp:'192.168.4.1',apClients:1,canHardReinit:0,canHardReinitFail:0,canLastHardDiagReasonName:'NONE',...ble};
for(let n=1;n<=3;n++)Object.assign(stats,{['can'+n+'State']:1,['can'+n+'Ready']:true,['can'+n+'StatusSeen']:true,['can'+n+'StatusAgeMs']:50,['can'+n+'Controller']:n-1,['can'+n+'TxPin']:[20,50,26][n-1],['can'+n+'RxPin']:[21,49,27][n-1],['can'+n+'Bitrate']:500000,['can'+n+'Mode']:'NORMAL',['can'+n+'InitResult']:'ESP_OK',['can'+n+'RxCount']:n*100,['can'+n+'RxPolls']:n*200,['can'+n+'RxResult']:'ESP_ERR_TIMEOUT',['can'+n+'Tec']:0,['can'+n+'Rec']:0,['can'+n+'RxQueued']:n,['can'+n+'TxQueued']:0,['can'+n+'TxAccepted']:10*n,['can'+n+'TxRejected']:n,['can'+n+'BusErrors']:n,['can'+n+'ArbLost']:0,['can'+n+'DriverTxFailed']:0,['can'+n+'RxMissed']:0,['can'+n+'RxOverrun']:0,['can'+n+'BusOffCount']:0,['can'+n+'Recoveries']:0,['can'+n+'RecoveryFailures']:0});
// Match the production section serializer: unrelated measurements must not be
// available to accidentally hide a broad request or stale-response render.
function sectionStats(section){
 const measured={...stats,can2Mode:profile.profile===1?'LISTEN_ONLY':'NORMAL',can2ErrorCountersFrozen:profile.profile===1};
 if(!section)return {...measured};
 if(section==='ble')return {...ble,logCapacity:128};
 const groups={system:['fwVersion','uptimeS','stackCanA','stackCanB','stackCanSup','stackWeb','stackS3xy','chipModel','cpuCores','cpuFreqMHz'],memory:['internalRamFreeBytes','internalRamMinFreeBytes','internalRamLargestBlockBytes','psramFreeBytes','psramTotalBytes','psramMinFreeBytes','psramLargestBlockBytes'],wireless:['networkState','hostedHostVersion','hostedC6Version','wifiStarted','apStarted','apIp','apClients'],recovery:['canHardReinit','canHardReinitFail','canLastHardDiagReasonName']};
 if(/^can[123]$/.test(section))return Object.fromEntries(Object.entries(measured).filter(([key])=>key.startsWith(section)));
 assert(groups[section],'Unknown mocked section '+section);return Object.fromEntries(groups[section].filter(key=>key in measured).map(key=>[key,measured[key]]));
}
(async()=>{
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||chromium.executablePath(),headless:true});
const page=await browser.newPage({viewport:{width:390,height:1000},acceptDownloads:true});
// A full-page capture can paint a closed offscreen sheet over later document
// rows. Suppress only closed sheets during screenshots; interaction tests keep
// the real CSS and all open dialogs.
const snapshot=page.screenshot.bind(page);
page.screenshot=async options=>{
   // Full-page captures include translated-offscreen sheets. Their `all`
   // transition delays visibility:hidden, so suppress transitions only on
   // closed layers during the snapshot and restore their original styles.
   const hidden=await page.locator('.sheet:not(.show),.sheetback:not(.show)').evaluateAll(es=>es.map(e=>{
    const saved={id:e.id,style:e.getAttribute('style')};
    e.style.setProperty('transition','none','important');
    e.style.setProperty('visibility','hidden','important');return saved;
   }));
   try{
    assert(await page.locator('.sheet:not(.show)').evaluateAll(es=>es.every(e=>getComputedStyle(e).visibility==='hidden')),'Closed sheets must be hidden in full-page snapshots');
    return await snapshot(options);
   }finally{await page.evaluate(saved=>saved.forEach(({id,style})=>{
    const e=document.getElementById(id);if(style===null)e.removeAttribute('style');else e.setAttribute('style',style);
   }),hidden)}
  };
const errors=[],requests=[],checks=[];page.on('pageerror',e=>errors.push(String(e)));
let downloadEvents=0;page.on('download',()=>downloadEvents++);
let apControl={enabled:false,mode:0,delaySeconds:2,allowManualDriving:false,gateReason:'ALLOW'};
let preheat={supported:true,enabled:false,active:true,blocked:true,blockedReason:'NO_TRIP_ID',tripId:'0x082',targetC:40,evalAgeMs:0,packSeen:true,packTempMinC:18,packTempMaxC:22,packTempAvgC:20,srcRaw:'00 00 00 00 00 00 00 00',srcAgeMs:20,txOk:0,replyTx:0,thModeAgeMs:0,thValveMode:1,thVitalsAgeMs:0,thPumpBatRpm:1200,thPumpPtRpm:900};
const inlineSettings={'/api/isa-suppression/config':{supported:true,enabled:false},'/api/driver-monitoring/config':{supported:true,enabled:false}};
let heldStats=null;
const holdStats=section=>new Promise(resolve=>{assert.equal(heldStats,null);heldStats={section,resolve}});
const txTraceCsv={'/api/system/cana-tx.csv':'# fixture CAN A\nevent_ms,result\n0,ESP_OK\n','/api/system/canb-tx.csv':'# fixture CAN B\nevent_ms,result\n1,ESP_ERR_TIMEOUT\n','/api/system/can-errors.json':'{"schemaVersion":1,"buses":[]}'};
let heldTxCsv=null;
const holdTxCsv=pathname=>new Promise(resolve=>{assert.equal(heldTxCsv,null);heldTxCsv={pathname,resolve}});
let useEmbedded=false,failNextSave=false,timing={schema:2,bootId:19,session:0,active:false,count:0,capacity:32768,dropped:0,elapsedMs:0,driverErrorLost:0,driverSnapshotFailures:0,driverSequenceSaturated:false,driverImportPending:false};
await page.route('**/*',async route=>{
 const u=new URL(route.request().url());if(u.hostname!=='p4can.test')return route.abort();
 const p=u.pathname;if(p==='/')return route.fulfill({status:200,contentType:'text/html',body:useEmbedded?embedded:source});
 if(p.startsWith('/api/')){
  if(p==='/api/system/boot-capture.csv')return route.fulfill({status:200,contentType:'text/csv',headers:{'Content-Disposition':'attachment; filename=boot.csv'},body:'uptime_ms,event\n0,BOOT\n'});
  if(p==='/api/s3xy/log.csv')return route.fulfill({status:200,contentType:'text/csv',body:'uptime_ms,event\n0,READY\n'});
  requests.push({method:route.request().method(),path:p,search:u.search,time:Date.now()});
  if(p in txTraceCsv){
   const reply=status=>route.fulfill({status,contentType:status===200&&!p.endsWith('.json')?'text/csv':'application/json',headers:status===200?{'Content-Length':String(Buffer.byteLength(txTraceCsv[p]))}:{},body:status===200?txTraceCsv[p]:'{"error":"trace unavailable"}'});
   if(heldTxCsv?.pathname===p){const held=heldTxCsv;heldTxCsv=null;await new Promise(done=>held.resolve({pathname:p,release:async(status=200)=>{await reply(status);done()}}));return}
   return reply(200);
  }
  if(failNextSave&&route.request().method()==='POST'){failNextSave=false;return route.fulfill({status:500,contentType:'application/json',body:'{"error":"test failure"}'})}
  let data={ok:true,supported:true,enabled:false,countrySupported:true,countryMode:0,mapMode:0};
  if(inlineSettings[p]){if(route.request().method()==='POST')inlineSettings[p].enabled=u.searchParams.get('enabled')==='1';data=inlineSettings[p]}
  else if(p==='/api/profile/status')data=profile;
  else if(p==='/api/features/status')data=features;
  else if(p==='/api/features/lab'){features.lab=u.searchParams.get('enabled')==='1';data=features}
  else if(p==='/api/features/s3xy'){ble.bluetoothEnabled=u.searchParams.get('enabled')==='1';features.s3xy=ble.bluetoothEnabled;data=features}
  else if(p==='/api/features/preheat'){features.preheat=u.searchParams.get('enabled')==='1';data=features}
  else if(p==='/api/preheat/stats')data=preheat;
  else if(p==='/api/preheat/set'){if(u.searchParams.has('enabled'))preheat.enabled=u.searchParams.get('enabled')==='1';if(u.searchParams.has('targetC'))preheat.targetC=Number(u.searchParams.get('targetC'));data=preheat}
  else if(p==='/api/nag/config')data=nag;
  else if(p==='/api/nag/stats')data={torque:0,apActive:false};
  else if(p==='/api/blinkA/stats')data={enabled:false,delayMs:0,dasStateValid:false};
  else if(p==='/api/snapshot')data=u.searchParams.get('groups')==='heartbeat'?{ok:true}:{fast:{nag:{torque:0,apActive:false},blink:{dasStateValid:true,dasState:0},summon:{},cantraffic:traffic,r79},slow:{blink:{delayMs:0},summon:{},s3xy:ble,r79,lab3f8:{}},system:stats,s3xy:ble};
  else if(p==='/api/system/can-gpio')data={ok:true,valid:true,active:[{tx:20,rx:21},{tx:50,rx:49},{tx:26,rx:27}],saved:[{tx:20,rx:21},{tx:50,rx:49},{tx:26,rx:27}],defaults:[{tx:20,rx:21},{tx:50,rx:49},{tx:26,rx:27}],allowedPins:Array.from({length:55},(_,n)=>n).filter(n=>![6,14,15,16,17,18,19,24,25,54].includes(n)),rebootRequired:false,canStopped:false,error:''};
  else if(p==='/api/system/stats'){
   const section=u.searchParams.get('section');data=sectionStats(section);
   if(heldStats?.section===section){
    const held=heldStats;heldStats=null;
    await new Promise(done=>held.resolve({section,release:async patch=>{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...data,...patch})});done()}}));return;
   }
  }
  else if(p==='/api/s3xy/stats')data=ble;
  else if(p==='/api/wifi/status')data={ssid:'P4-CAN',ip:'192.168.4.1',passwordIsDefault:false};
  else if(p==='/api/r79/stats'||p==='/api/r79/update')data=r79;
  else if(p==='/api/r79/ap-control/stats'||p==='/api/r79/ap-control/update'){if(route.request().method()==='POST')apControl={...apControl,enabled:u.searchParams.get('enabled')==='1',mode:Number(u.searchParams.get('mode')),delaySeconds:Number(u.searchParams.get('delaySeconds'))};data=apControl;}
  else if(p==='/api/r79/timing/start')timing={...timing,session:1,active:true,count:8,elapsedMs:1000,driverErrorLost:3,driverSnapshotFailures:2,driverSequenceSaturated:true,driverImportPending:true};
  else if(p==='/api/r79/timing/stop')timing.active=false;
  else if(p==='/api/r79/timing/csv')return route.fulfill({status:200,contentType:'text/csv',body:'session,event_seq,stage\n1,1,RX\n'});
  if(p.startsWith('/api/r79/timing/'))data=timing;
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
 }
 const file=path.join(root,p);if(p.startsWith('/fonts/')&&fs.existsSync(file))return route.fulfill({status:200,contentType:'font/woff2',body:fs.readFileSync(file)});
 return route.fulfill({status:204,body:''});
});
await page.goto('http://p4can.test/',{waitUntil:'load'});
await page.waitForFunction(()=>typeof universalBootReady!=='undefined'&&universalBootReady,{timeout:10000});
assert.deepEqual(errors,[],'boot errors');
const open=async id=>{await page.evaluate(id=>openSettingsItem(id),id);await page.waitForTimeout(380)};
const diag=async(id)=>{await page.evaluate(id=>openPanel(id),id);await page.waitForTimeout(380)};
const onlyPanel=async id=>assert.equal(await page.locator('.panel.show').getAttribute('id'),id);
const assertPhysicalLabels=async(profileId,variant)=>{
 const expected=profileId===1?['VEHICLE','BODY','PARTY']:['BODY','CHASSIS','PARTY'];
 assert.deepEqual(await page.locator('#homeCanCard .homeBusRole').allTextContents(),expected,variant+' Home bus roles');
 for(const selector of ['#homeCanDetails','#panelCanGpio','#panelDiag'])assert.deepEqual(await page.locator(selector+' [data-can-role]').allTextContents(),expected,variant+' '+selector+' physical roles');
};
const settingsPanels=['panelNag','panelVisionControl','panelBlink','panelSummon','panelR79','panelCountry','panelTlssc','panelUlc','panelPedalMap','panelContinuousAp','panelApDriveProfile','panelWireless','panelCanGpio','panelDiag','panelOta'];
const diagnosticSections=['system','memory','wireless','ble','can1','can2','can3','recovery'];
const settle=()=>page.evaluate(async()=>{await document.fonts.ready;await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))});
const assertAccordion=async section=>{
 await onlyPanel('panelDiag');
 assert.deepEqual(await page.locator('#panelDiag [data-diag-category]').evaluateAll(es=>es.map(e=>e.dataset.diagCategory)),diagnosticSections);
 const states=await page.locator('#panelDiag [data-diag-toggle]').evaluateAll(es=>es.map(e=>{const body=document.getElementById(e.getAttribute('aria-controls'));return {section:e.dataset.diagToggle,expanded:e.getAttribute('aria-expanded'),native:e.tagName==='BUTTON',inert:body.inert,labelled:body.getAttribute('aria-labelledby')===e.id,open:body.closest('[data-diag-category]').classList.contains('open'),height:body.getBoundingClientRect().height}}));
 for(const state of states){const active=state.section===section;assert.equal(state.expanded,String(active));assert(state.native&&state.labelled);assert.equal(state.inert,!active);assert.equal(state.open,active);assert(active?state.height>0:state.height<.5,JSON.stringify(state))}
 assert.equal(await page.locator('#panelDiag [data-panel]').count(),0,'All diagnostic content stays in this panel');
 for(const id of ['btnResetStats','btnReinit'])assert(await page.locator('#'+id).evaluate(e=>!e.closest('[data-diag-section]')&&!e.closest('[inert]')),'Single actions remain outside accordions');
};
const clickDiag=async section=>{await page.locator('#panelDiag [data-diag-toggle="'+section+'"]').click();await settle()};
const showDiag=async section=>{await diag('panelDiag');await page.evaluate(section=>setDiagSection(section),section);await settle();await assertAccordion(section)};
// These use the real click handler, helper, status watchdog and selected-section
// poller. Only the offline HTTP peer is held or failed deliberately.
const assertTxCsvDownloads=async(profileId,variant,exerciseBusy=false)=>{
 await page.evaluate(()=>showPage('settings'));await showDiag('recovery');
 const wanted=profileId===1?['CAN 3 TX CSV','CAN 1 TX CSV']:['CAN 1 TX CSV','CAN 2 TX CSV'];
 assert.deepEqual(await page.locator('#diagCanATxCsv,#diagCanBTxCsv').allTextContents(),wanted,variant+' physical CAN labels');
 const cases=[['diagCanATxCsv','/api/system/cana-tx.csv','P4-CAN_CANA_TX_TRACE.csv'],['diagCanBTxCsv','/api/system/canb-tx.csv','P4-CAN_CANB_TX_TRACE.csv'],['diagCanErrorsJson','/api/system/can-errors.json','P4-CAN_CAN_ERRORS.json']];
 for(const [index,[id,endpoint,filename]] of cases.entries()){
  requests.length=0;const held=holdTxCsv(endpoint),ready=page.waitForEvent('download');
  await page.locator('#'+id).click();const response=await held;
  assert.equal(response.pathname,endpoint);assert(requests.some(r=>r.method==='GET'&&r.path===endpoint&&!r.search),variant+' '+id+' endpoint');
  await page.waitForFunction(()=>downloadInProgress&&downloadManaged);
  const pausedAt=requests.length;await page.evaluate(()=>pollTick(true));
  await page.waitForTimeout(exerciseBusy?(index===0?4700:1700):50);
  assert.equal(requests.length,pausedAt,variant+' '+id+' must suspend polling while the HTTP response is held');
  const busy=await page.locator('[data-conn]').evaluateAll(es=>es.map(e=>({text:e.textContent,busy:e.classList.contains('busy')})));
  assert(busy.length&&busy.every(e=>e.text.startsWith('Downloading…')&&e.busy),variant+' '+id+' retains Downloading state, including the connection watchdog');
  const resumed=page.waitForRequest(r=>{const u=new URL(r.url());return u.pathname==='/api/system/stats'&&u.search==='?section=recovery'});
  await response.release();const download=await ready;assert.equal(download.suggestedFilename(),filename);
  const saved=path.join(output,variant+'-'+filename);await download.saveAs(saved);assert.equal(fs.readFileSync(saved,'utf8'),txTraceCsv[endpoint]);
  await page.waitForFunction(()=>!downloadInProgress&&!downloadManaged&&downloadProgress===null);await resumed;
  assert((await page.locator('[data-conn]').allTextContents()).every(text=>text==='Connected'),variant+' '+id+' clears busy after success');
  if(exerciseBusy){
   const failedHold=holdTxCsv(endpoint),beforeDownloads=downloadEvents;await page.locator('#'+id).click();const failed=await failedHold;
   await page.waitForFunction(()=>downloadInProgress&&downloadManaged);
   const failedResumed=page.waitForRequest(r=>{const u=new URL(r.url());return u.pathname==='/api/system/stats'&&u.search==='?section=recovery'});
   await failed.release(503);await page.waitForFunction(()=>!downloadInProgress&&!downloadManaged&&downloadProgress===null);await failedResumed;
   assert.equal(downloadEvents,beforeDownloads,variant+' '+id+' HTTP 503 must not save a file');
   assert(await page.locator('[data-conn]').evaluateAll(es=>es.every(e=>!e.textContent.startsWith('Downloading…')&&!e.classList.contains('busy'))),variant+' '+id+' clears busy after failure');
  }
 }
 checks.push({txCsvVariant:variant,profile:profileId,physicalLabels:wanted,managedATrace:true,managedBTrace:true,managedCanErrorJson:true,heldResponsePollPause:true,successPollResume:true,http503Cleanup:exerciseBusy,watchdogHoldMs:exerciseBusy?4700:50});
};
const animateDiag=async(section,opening,reducedMotion)=>{
 // A protocol round-trip + wall-clock sleep does not establish that Chromium
 // committed the CSS change. Flush the initial style, click, await real
 // transition readiness and sample an animation frame on its own timeline.
 const {before,middle}=await page.evaluate(async section=>{
  const body=document.querySelector('[data-diag-section="'+section+'"]'),card=body.closest('[data-diag-category]'),button=card.querySelector('[data-diag-toggle]');
  const read=()=>({height:body.getBoundingClientRect().height,opacity:Number(getComputedStyle(body).opacity)});
  const before=read();button.click();read();
  const transitions=card.getAnimations({subtree:true}).filter(a=>['grid-template-rows','opacity','transform'].includes(a.transitionProperty));
  const describe=()=>transitions.map(a=>({property:a.transitionProperty,duration:a.effect.getTiming().duration,currentTime:a.currentTime,startTime:a.startTime,playState:a.playState}));
  const heightTransition=transitions.find(a=>a.effect?.target===body&&a.transitionProperty==='grid-template-rows');
  if(!heightTransition)return {before,middle:{...read(),animations:describe(),samples:[]}};
  await Promise.all(transitions.map(a=>a.ready));
  const samples=[];
  const middle=await new Promise((resolve,reject)=>{
   const timeout=setTimeout(()=>reject(new Error('No intermediate Diagnostics animation frame: '+JSON.stringify({before,samples,animations:describe()}))),1500);
   const frame=()=>{
    const sample={...read(),animations:describe()};samples.push(sample);
    const elapsed=Number(heightTransition.currentTime);
    if(elapsed>=60){clearTimeout(timeout);resolve({...sample,samples});return}
    requestAnimationFrame(frame);
   };requestAnimationFrame(frame);
  });
  return {before,middle};
 },section);
 await settle();const after=await page.locator('[data-diag-section="'+section+'"]').evaluate(e=>({height:e.getBoundingClientRect().height,opacity:Number(getComputedStyle(e).opacity)}));
 assert(middle.height>Math.min(before.height,after.height)+.1&&middle.height<Math.max(before.height,after.height)-.1,`${reducedMotion} height must animate ${opening?'open':'closed'}: `+JSON.stringify({before,middle,after}));
 assert(middle.opacity>0&&middle.opacity<1,`${reducedMotion} content must fade in both directions: `+JSON.stringify({before,middle,after}));
 for(const property of ['grid-template-rows','opacity','transform'])assert(middle.animations.some(a=>a.property===property&&Math.abs(Number(a.duration)-200)<1&&Number(a.currentTime)>0&&Number(a.currentTime)<200),`${reducedMotion} ${property} must use an active 200ms transition: `+JSON.stringify(middle));
 await assertAccordion(opening?section:'');checks.push({reducedMotion,direction:opening?'open':'close',animation:middle.animations,height:middle.height,opacity:middle.opacity,frameSamples:middle.samples});
};
const settingsRoot=page.locator('main[data-page="settings"]');
const showSettings=async()=>{await page.locator('#bottomNav [data-page="settings"]').click();await page.waitForTimeout(380);assert.equal(await page.locator('.panel.show').count(),0)};
const assertList=async(root,expected)=>{
 const rows=root.locator('.listrow[data-panel]');assert.deepEqual(await rows.evaluateAll(es=>es.map(e=>e.dataset.panel)),expected);
 assert.equal(await root.locator('.category,.categorySummary,.categoryReveal,details').count(),0,'Navigation lists must not require expansion');
 const hidden=await rows.evaluateAll(es=>es.filter(e=>!e.getBoundingClientRect().height||getComputedStyle(e).visibility!=='visible'||e.closest('[inert]')).map(e=>e.dataset.panel));assert.deepEqual(hidden,[],'Every navigation row must be displayed and interactive');
};
assert.equal(await page.locator('.settingsItem,.settingsNested,#activeProfileCan,#activeProfileTurn,#activeProfileCaps,#panelIsaSuppression,#panelDriverMonitoring,#panelAppearance,#panelRefresh,#panelMenu,#panelActionsMenu').count(),0);
// Settings remains original; Diagnostics expands in-place with native keyboard access.
for(const reducedMotion of ['no-preference','reduce']){
 await page.emulateMedia({reducedMotion});await showSettings();await assertList(settingsRoot,settingsPanels);
 assert.deepEqual(await settingsRoot.locator('.sectiontitle').allTextContents(),['Features','System']);
 await settingsRoot.locator('[data-panel="panelNag"]').click();await onlyPanel('panelNag');await page.locator('#panelNag .backbtn').click();await page.waitForTimeout(380);await assertList(settingsRoot,settingsPanels);
 await settingsRoot.locator('[data-panel="panelDiag"]').click();await settle();await assertAccordion('');
 await animateDiag('system',true,reducedMotion);await animateDiag('system',false,reducedMotion);
 await page.locator('[data-diag-toggle="memory"]').focus();await page.keyboard.press('Enter');await settle();await assertAccordion('memory');
 await page.keyboard.press('Space');await settle();await assertAccordion('');
 await clickDiag('can1');await assertAccordion('can1');await clickDiag('can2');await assertAccordion('can2');
 await page.locator('#panelDiag .backbtn').click();await page.waitForTimeout(380);assert.equal(await page.locator('.panel.show').count(),0);await assertList(settingsRoot,settingsPanels);
 requests.length=0;await page.waitForTimeout(1800);assert(!requests.some(r=>['/api/nag/stats','/api/r79/stats','/api/preheat/stats','/api/s3xy/stats','/api/system/stats'].includes(r.path)),'Settings lists must not poll any child');
 assert(requests.some(r=>r.path==='/api/isa-suppression/config')&&requests.some(r=>r.path==='/api/driver-monitoring/config')&&requests.some(r=>r.path==='/api/features/status'),'Root refreshes visible inline saved states');
 checks.push({reducedMotion,settingsRowsAlwaysVisible:true,inlineControlsVisible:true,diagnosticInlineAccordion:true,keyboard:true});
}
// Every top-level Settings row uses its actual click handler and returns to the original list.
for(const id of settingsPanels){
 await showSettings();await settingsRoot.locator('[data-panel="'+id+'"]').click();await onlyPanel(id);await page.locator('#'+id+' .backbtn').first().click();await page.waitForTimeout(380);assert.equal(await page.locator('.panel.show').count(),0);await assertList(settingsRoot,settingsPanels);
}
await page.emulateMedia({reducedMotion:'no-preference'});
await open('panelNag');await onlyPanel('panelNag');await page.locator('#nagModeHSettingsRow').click();await onlyPanel('panelNagModeH');await page.locator('#panelNagModeH .backbtn').click();await onlyPanel('panelNag');
await open('panelR79');assert(await page.locator('#r79ApControlToggle').locator('..').isVisible());
await page.waitForFunction(()=>!document.getElementById('r79TimingStart').disabled);await page.locator('#r79TimingStart').click();await page.waitForFunction(()=>!document.getElementById('r79TimingStop').disabled);assert.match(await page.locator('#r79TimingWarnings').innerText(),/3 CAN 2 errors lost.*2 driver snapshot failures.*saturated.*pending/);
await open('panelWireless');assert(timing.active,'Navigation must not stop capture');requests.length=0;await page.waitForTimeout(1800);assert(!requests.some(r=>r.path.startsWith('/api/r79/')),'Hidden R79 must stop polling');
await showSettings();await settingsRoot.locator('[data-panel="panelDiag"]').click();await settle();await assertAccordion('');requests.length=0;
await page.evaluate(()=>{const label=document.querySelector('.globaltop [data-conn]');window.__closedDiagConnectionLabels=[label.textContent];window.__closedDiagConnectionObserver=new MutationObserver(()=>window.__closedDiagConnectionLabels.push(label.textContent));window.__closedDiagConnectionObserver.observe(label,{childList:true,characterData:true,subtree:true})});
await page.waitForTimeout(5200);
const closedConnectionLabels=await page.evaluate(()=>{window.__closedDiagConnectionObserver.disconnect();return window.__closedDiagConnectionLabels});
assert(!requests.some(r=>r.path==='/api/system/stats'),'All-closed Diagnostics never requests diagnostic stats');
assert(requests.some(r=>r.path==='/api/snapshot'&&r.search==='?groups=heartbeat'),'All-closed Diagnostics keeps the existing transport heartbeat');
assert(closedConnectionLabels.length>0&&closedConnectionLabels.every(label=>label==='Connected'),'Connection must stay Connected beyond the 4200ms watchdog: '+JSON.stringify(closedConnectionLabels));
checks.push({allClosedDiagnosticStatsReads:0,transportHeartbeatPreserved:true,connectedForMs:5200,connectionLabels:closedConnectionLabels});
for(const section of diagnosticSections){
 requests.length=0;await clickDiag(section);await assertAccordion(section);await page.waitForTimeout(1800);
 const reads=requests.filter(r=>r.path==='/api/system/stats');assert(reads.some(r=>r.search==='?section='+section),'Selected section must refresh');
 assert(reads.every(r=>r.search==='?section='+section),'Only selected section, with full CAN bus and no subview parameter, is requested');assert(!requests.some(r=>r.path==='/api/s3xy/stats'),'BLE Diagnostics uses the same selected stats endpoint');
}
requests.length=0;await clickDiag('recovery');await assertAccordion('');await page.waitForTimeout(1800);assert(!requests.some(r=>r.path==='/api/system/stats'),'Closing the last category stops stats reads');
// Hold actual HTTP routes to prove both fast-switch and same-category reopen fences.
await page.evaluate(()=>document.getElementById('sysInternalRam').textContent='unchanged-memory');
let delayed=holdStats('memory');await clickDiag('memory');let oldReply=await delayed;
await clickDiag('can2');await page.waitForFunction(()=>document.getElementById('diagCan2Rx').textContent.startsWith('200 /'));
const activeFreshness=await page.locator('#diagBodyCan2 .diagFreshness').textContent();await oldReply.release({internalRamFreeBytes:111000});await page.waitForTimeout(100);
assert.equal(await page.locator('#sysInternalRam').textContent(),'unchanged-memory','A delayed old selection must not render');assert.equal(await page.locator('#diagBodyCan2 .diagFreshness').textContent(),activeFreshness,'Old selection must not change active freshness');
await clickDiag('can2');await page.evaluate(()=>document.getElementById('sysInternalRam').textContent='waiting-new-memory');
delayed=holdStats('memory');await clickDiag('memory');oldReply=await delayed;await clickDiag('memory');stats.internalRamFreeBytes=333000;await clickDiag('memory');
await page.waitForFunction(()=>document.getElementById('sysInternalRam').textContent!=='waiting-new-memory');
const reopenedValue=await page.locator('#sysInternalRam').textContent(),reopenedFreshness=await page.locator('#diagBodyMemory .diagFreshness').textContent();
await oldReply.release({internalRamFreeBytes:111000});await page.waitForTimeout(100);
assert.equal(await page.locator('#sysInternalRam').textContent(),reopenedValue,'Closing and reopening the same section rejects the earlier generation');assert.equal(await page.evaluate(()=>lastSys.internalRamFreeBytes),333000);assert.equal(await page.locator('#diagBodyMemory .diagFreshness').textContent(),reopenedFreshness);
await page.evaluate(()=>document.getElementById('sysInternalRam').textContent='before-hidden-response');await clickDiag('memory');
delayed=holdStats('memory');await clickDiag('memory');oldReply=await delayed;await open('panelR79');await oldReply.release({internalRamFreeBytes:222000});await page.waitForTimeout(100);assert.equal(await page.locator('#sysInternalRam').textContent(),'before-hidden-response','Leaving Diagnostics invalidates in-flight responses');
checks.push({delayedHttpSwitchFence:true,delayedHttpSameSectionReopenFence:true,delayedHttpHiddenFence:true,sectionFilteredMocks:true});
await showDiag('');
for(const [id,endpoint] of [['btnResetStats','/api/system/reset-stats'],['btnReinit','/api/system/reinit-can']]){
 assert.equal(await page.locator('#'+id).count(),1);requests.length=0;page.once('dialog',d=>d.dismiss());await page.locator('#'+id).click();assert(!requests.some(r=>r.method==='POST'),'Cancelled action must not POST');
 page.once('dialog',d=>d.accept());await Promise.all([page.waitForResponse(r=>new URL(r.url()).pathname===endpoint&&r.request().method()==='POST'),page.locator('#'+id).click()]);assert(requests.some(r=>r.method==='POST'&&r.path===endpoint));
}
await showDiag('recovery');const bootReady=page.waitForEvent('download');await page.locator('#diagBodyRecovery a[href="/api/system/boot-capture.csv"]').click();await (await bootReady).saveAs(path.join(output,'boot.csv'));for(const [id,name] of [['diagSystemStatsJson','stats.json'],['diagBleCsvSystem','ble.csv']]){const ready=page.waitForEvent('download');await page.locator('#'+id).click();await (await ready).saveAs(path.join(output,name));await page.waitForFunction(()=>!downloadInProgress)}
await assertTxCsvDownloads(1,'source-yl',true);
await open('panelR79');await page.locator('#r79TimingStop').click();await page.waitForFunction(()=>!document.getElementById('r79TimingDownload').disabled);
const downloading=page.waitForEvent('download');await page.locator('#r79TimingDownload').click();await (await downloading).saveAs(path.join(output,'timing.csv'));await page.waitForFunction(()=>!downloadInProgress);
features.lab=false;await page.evaluate(()=>window.__refreshFeatures());await open('panelR79');await page.locator('#r79ApControlToggle').locator('..').click();await page.waitForFunction(()=>!document.getElementById('r79ApControlMode').disabled);await page.locator('#r79ApControlMode').selectOption('1');await page.waitForFunction(()=>!document.getElementById('r79ApDelaySeconds').disabled);await page.locator('#r79ApDelaySeconds').fill('7');await page.locator('#r79ApDelaySeconds').press('Tab');await page.waitForTimeout(200);assert.equal(apControl.delaySeconds,7);assert(apControl.enabled&&apControl.mode===1);
// Restored inline controls use the original Settings rows and confirmed backend state.
await showSettings();
for(const [id,pathName] of [['isaSuppressionToggle','/api/isa-suppression/config'],['driverMonitoringToggle','/api/driver-monitoring/config']]){
 await page.waitForFunction(id=>!document.getElementById(id).disabled,id);
 assert(await settingsRoot.locator('#'+id).locator('..').isVisible(),id+' is an inline root toggle');
 await page.locator('#'+id).locator('..').click();
 await page.waitForFunction(id=>document.getElementById(id).checked&&!document.getElementById(id).disabled,id);
 assert.equal(inlineSettings[pathName].enabled,true,id+' saved');
 failNextSave=true;await page.locator('#'+id).locator('..').click();
 await page.waitForFunction(id=>document.getElementById(id).checked&&!document.getElementById(id).disabled,id);
 assert.equal(inlineSettings[pathName].enabled,true,id+' reloads confirmed saved state after a rejected save');
}
assert((await page.locator('#sysFw').innerText()).includes(stats.fwVersion),'Firmware version remains a root row');
// Root S3XY and Wireless Bluetooth Master control the same persisted preference.
await page.locator('#s3xyFeatureToggle').locator('..').click();
await page.waitForFunction(()=>!document.getElementById('s3xyFeatureToggle').checked&&document.getElementById('devicesNavBtn').classList.contains('hiddenByProfile'));
assert.equal(features.s3xy,false);await open('panelWireless');
await page.waitForFunction(()=>!document.getElementById('s3MasterToggle').checked);
await page.locator('#s3MasterToggle').locator('..').click();
await page.waitForFunction(()=>document.getElementById('s3MasterToggle').checked&&document.getElementById('s3xyFeatureToggle').checked);
assert(features.s3xy&&ble.bluetoothEnabled);await showSettings();
failNextSave=true;await page.locator('#s3xyFeatureToggle').locator('..').click();
await page.waitForFunction(()=>document.getElementById('s3xyFeatureToggle').checked);
assert(features.s3xy&&ble.bluetoothEnabled,'Rejected root save reloads the shared Wireless preference');
// Appearance and refresh remain original inline choice buttons, saved on this phone.
await settingsRoot.locator('[data-theme-choice="dark"]').click();
assert.deepEqual(await page.evaluate(()=>[document.documentElement.dataset.theme,localStorage.getItem('p4canDashboardTheme')]),['dark','dark']);
assert.equal(await settingsRoot.locator('[data-theme-choice="dark"]').getAttribute('aria-pressed'),'true');
await settingsRoot.locator('[data-poll-choice="1000"]').click();
assert.equal(await page.evaluate(()=>localStorage.getItem('p4canDashboardPollMs')),'1000');
await page.reload();await page.waitForFunction(()=>universalBootReady);await showSettings();
assert.equal(await page.locator('#dashboardThemeMode').inputValue(),'dark');assert.equal(await page.locator('#dashboardPollRate').inputValue(),'1000');
assert.equal(await settingsRoot.locator('[data-poll-choice="1000"]').getAttribute('aria-pressed'),'true');
await settingsRoot.locator('[data-theme-choice="system"]').click();await page.emulateMedia({colorScheme:'light'});
await page.waitForFunction(()=>document.documentElement.dataset.theme==='light');
await page.emulateMedia({colorScheme:'dark'});await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
assert.equal(await page.evaluate(()=>localStorage.getItem('p4canDashboardTheme')),'system');
await settingsRoot.locator('[data-poll-choice="500"]').click();
// LAB remains an inline menu visibility preference; historical LAB feature pages stay removed.
features.lab=true;await page.evaluate(()=>window.__refreshFeatures());await open('labMenu');
assert.equal(await page.locator('.panel.show').count(),0);failNextSave=true;
await page.locator('#labMenuToggle').locator('..').click();await page.waitForFunction(()=>document.getElementById('labMenuToggle').checked);
assert(features.lab&&!await page.locator('#labNavBtn').evaluate(e=>e.classList.contains('hiddenByProfile')),'LAB save failure restores the checked/menu state');
await page.locator('#labMenuToggle').locator('..').click();await page.waitForFunction(()=>document.getElementById('labNavBtn').classList.contains('hiddenByProfile'));assert.equal(features.lab,false);
await page.locator('#labMenuToggle').locator('..').click();await page.waitForFunction(()=>!document.getElementById('labNavBtn').classList.contains('hiddenByProfile'));assert.equal(features.lab,true);
await page.evaluate(()=>showPage('lab'));assert.equal(await page.locator('main[data-page="lab"] [data-panel]').count(),1);assert.equal(await page.locator('#panelLabR79,#panelLabSummonHeartbeat,#panelLabAutoLaneChange,#panelLabDriverWindow,#panelLabDriverMonitor,#bannedCarToggle,#tlsscRestoreToggle').count(),0);
// Direct reset rows show their established confirmation immediately, before any POST.
for(const [row,modal,cancel] of [['resetSettingsBtn','resetSettingsWarningModal','cancelResetSettings'],['resetNvsKeepBleBtn','resetNvsKeepBleWarningModal','cancelResetNvsKeepBle'],['factoryResetBtn','factoryWarningModal','cancelFactoryReset']]){
 await showSettings();requests.length=0;await page.locator('#'+row).click();assert(await page.locator('#'+modal).isVisible());assert(!requests.some(r=>r.method==='POST'));await page.locator('#'+cancel).click();
}
await showSettings();page.once('dialog',dialog=>dialog.dismiss());requests.length=0;await page.locator('#rebootRow').click();assert(!requests.some(r=>r.method==='POST'));
// Full source Actions/Thermal behavior and separate visibility preference.
await page.evaluate(()=>showPage('actions'));await page.waitForFunction(()=>!document.getElementById('preheatToggle').disabled);assert.equal(await page.locator('#preheatTargetC option').count(),7);assert.equal(await page.locator('#preheatTargetC').inputValue(),'40.0');
await page.locator('#preheatToggle').locator('..').click();await page.waitForFunction(()=>document.getElementById('preheatToggle').checked);assert(preheat.enabled);await page.locator('#preheatTargetC').selectOption('45.0');await page.waitForFunction(()=>document.getElementById('preheatTargetC').value==='45.0'&&!document.getElementById('preheatTargetC').disabled);assert.equal(preheat.targetC,45);
await page.locator('#preheatRaw>summary').click();await page.locator('#thermalFold>summary').click();assert.equal(await page.locator('#thermalFold svg').count(),1);assert((await page.locator('#ptSrcRawMeta').innerText()).includes('0x082'));assert.equal(await page.locator('#thModeChip').innerText(),'Parallel');
await open('panelActionsMenu');assert.equal(await page.locator('.panel.show').count(),0);await page.locator('#actionsMenuToggle').locator('..').click();await page.waitForFunction(()=>document.getElementById('actionsNavBtn').classList.contains('hiddenByProfile'));assert(preheat.enabled,'Hiding menu must preserve enabled engine');requests.length=0;await page.waitForTimeout(1800);assert(!requests.some(r=>r.path==='/api/preheat/stats'),'Hidden Actions must not poll');
await page.locator('#actionsMenuToggle').locator('..').click();await page.waitForFunction(()=>!document.getElementById('actionsNavBtn').classList.contains('hiddenByProfile'));await page.evaluate(()=>showPage('actions'));await page.waitForFunction(()=>document.getElementById('preheatToggle').checked);assert.equal(preheat.targetC,45);
await assertPhysicalLabels(1,'source-yl');
const panels=['panelNag','panelNagModeH','panelBlink','panelSummon','panelR79','panelTlssc','panelUlc','panelPedalMap','panelContinuousAp','panelVisionControl','panelCountry','panelApDriveProfile','panelWireless','panelCanGpio','panelDiag','panelOta'];
for(const theme of ['light','dark'])for(const width of [320,390,430]){
 await page.setViewportSize({width,height:1000});await page.evaluate(t=>{window.p4Theme.setMode(t);showPage('home')},theme);await page.waitForTimeout(700);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Home overflow ${width}/${theme}`);
 const navClipped=await page.locator('#bottomNav').evaluate(nav=>{const r=nav.getBoundingClientRect();return [...nav.querySelectorAll('.navbtn')].filter(n=>{const b=n.getBoundingClientRect();if(!b.width||!b.height)return false;const range=document.createRange();range.selectNodeContents(n);const t=range.getBoundingClientRect();return b.left<r.left-.5||b.right>r.right+.5||t.left<r.left-.5||t.right>r.right+.5}).map(n=>n.textContent)});assert.deepEqual(navClipped,[],`${width}/${theme} navigation internally clips`);
 const boxes=await page.locator('.homeCanColumns>.homeBus').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return{x:r.x,width:r.width}}));assert(Math.max(...boxes.map(x=>x.width))-Math.min(...boxes.map(x=>x.width))<1);assert(boxes[2].x>boxes[1].x);await page.screenshot({path:path.join(output,`home-${width}-${theme}.png`)});
 for(const id of panels){await open(id);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id} overflow ${width}/${theme}`);
 const clipped=await page.locator('.panel.show button,.panel.show select,.panel.show input').evaluateAll(nodes=>nodes.filter(n=>{const r=n.getBoundingClientRect();if(r.width<8||r.height<8)return false;const c=n.closest('.card')?.getBoundingClientRect();return r.left<-.5||r.right>innerWidth+.5||(c&&(r.left<c.left-.5||r.right>c.right+.5))}).map(n=>n.id||n.tagName));assert.deepEqual(clipped,[],`${id} clipped controls ${width}/${theme}`);
 if(id==='panelR79')assert(await page.locator('#panelR79 .labControlRow:has(select)>div:first-child').evaluateAll(nodes=>nodes.every(n=>!n.getBoundingClientRect().height||n.getBoundingClientRect().width>=95)),'R79 text columns must remain readable');}
 await showSettings();await assertList(settingsRoot,settingsPanels);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Settings list overflow ${width}/${theme}`);await page.screenshot({path:path.join(output,`settings-${width}-${theme}.png`),fullPage:true});
 await settingsRoot.locator('[data-panel="panelDiag"]').click();await settle();await assertAccordion('');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Diagnostics root overflow ${width}/${theme}`);await page.screenshot({path:path.join(output,`diagnostics-root-${width}-${theme}.png`)});
 for(const section of diagnosticSections){await clickDiag(section);await assertAccordion(section);
  const overflow=await page.locator('[data-diag-section="'+section+'"]').evaluate(e=>{const b=e.getBoundingClientRect(),bad=[];if(e.scrollWidth>e.clientWidth+1)bad.push('body scroll width');for(const n of e.querySelectorAll('.r>span,.softNote,button,a')){const r=document.createRange();r.selectNodeContents(n);if([...r.getClientRects()].some(t=>t.width&&(t.left<b.left-.5||t.right>b.right+.5)))bad.push(n.id||n.textContent.trim())}return bad});assert.deepEqual(overflow,[],`${width}/${theme} ${section} content overflow`);
  // Capture the real fixed-panel viewport with its selected summary below
  // the global header; the longer Settings document is not visual evidence.
  await page.locator('#panelDiag [data-diag-toggle="'+section+'"]').evaluate(e=>{e.scrollIntoView({block:'start',behavior:'instant'});e.closest('.panel').scrollBy({top:-60,left:0,behavior:'instant'})});
  await page.screenshot({path:path.join(output,`diagnostics-${section}-${width}-${theme}.png`),fullPage:false});await clickDiag(section);await assertAccordion('');
 }
 await page.locator('#panelDiag .backbtn').click();await page.waitForTimeout(380);await assertList(settingsRoot,settingsPanels);
 await open('panelR79');await page.screenshot({path:path.join(output,`settings-r79-${width}-${theme}.png`)});await page.locator('#r79ApControls').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,`settings-ap-${width}-${theme}.png`)});
 await showDiag('can1');await page.screenshot({path:path.join(output,`diagnostics-${width}-${theme}.png`)});
 await page.evaluate(()=>showPage('actions'));await page.waitForTimeout(380);await page.screenshot({path:path.join(output,`actions-${width}-${theme}.png`)});await page.locator('#thermalFold').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,`thermal-${width}-${theme}.png`)});
 const overlap=await page.locator('#preheatRaw .listrow').evaluateAll(rows=>rows.filter(row=>{const key=row.querySelector('.listkey'),value=row.querySelector('.rowRight .value');if(!key||!value)return false;const range=document.createRange();range.selectNodeContents(key);const v=value.getBoundingClientRect(),r=row.getBoundingClientRect();return [...range.getClientRects()].some(k=>k.right>r.right+.5||(k.right>v.left+.5&&k.left<v.right&&k.top<v.bottom&&k.bottom>v.top))}).map(r=>r.querySelector('.listkey').textContent));assert.deepEqual(overlap,[],`${width}/${theme} raw signal/value overlaps`);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Actions overflow ${width}/${theme}`);
 checks.push({width,theme,homeEqualColumns:true,detailPanels:panels.length,navInternalClipping:false,rawSignalOverlap:false,overflow:false});
}
await page.evaluate(()=>{showPage('home');window.p4Theme.setMode('dark');otaUploading=true;renderApPresentation(0,false)});await page.waitForTimeout(700);const unknown=await page.evaluate(()=>({theme:document.documentElement.dataset.theme,ap:document.body.dataset.ap,title:document.getElementById('apMode').textContent,background:getComputedStyle(document.body).backgroundColor}));assert.equal(unknown.theme,'dark');assert.equal(unknown.ap,'STANDBY');assert.equal(unknown.title,'AP Unknown');assert.equal(unknown.background,'rgb(29, 29, 33)');assert(!(await page.locator('main[data-page="home"]').innerText()).includes('NaN'));await page.screenshot({path:path.join(output,'home-unknown-dark.png')});
for(const id of [1,2,3,4,5]){profile.profile=id;profile.topology=id===1?1:2;profile.canA=id===1?'PARTY':'BODY';profile.canB=id===1?'VH':'CHASSIS';await page.goto('http://p4can.test/');await page.waitForFunction(()=>universalBootReady);await assertPhysicalLabels(id,'source-profile-'+id);await page.evaluate(()=>document.getElementById('changeProfileBtn').click());await page.locator('.vehicleChoice[data-vehicle="'+['MODEL_YL','MODEL_Y_JUNIPER','MODEL_Y_LEGACY','MODEL_3_HIGHLAND','MODEL_3_LEGACY'][id-1]+'"]').click();if(id===4)await page.locator('.turnChoice[data-turn="STALKLESS"]').click();assert.equal(await page.locator('#setupCanSummary').innerText(),id===1?'CAN 1 VEHICLE · CAN 2 BODY · CAN 3 PARTY':'CAN 1 BODY · CAN 2 CHASSIS · CAN 3 PARTY');assert(!/TX\d|RX\d/.test(await page.locator('#topologyStep').innerText()));await page.locator('#saveProfileBtn').click();assert.match(await page.locator('#profileConfirmSummary').innerText(),id===1?/CAN 1 VEHICLE \/ CAN 2 BODY \/ CAN 3 PARTY/:/CAN 1 BODY \/ CAN 2 CHASSIS \/ CAN 3 PARTY/);await page.locator('#cancelProfileSave').click();await page.locator('#cancelProfileChangeBtn').click()}
profile.profile=2;profile.topology=2;await page.goto('http://p4can.test/');await page.waitForFunction(()=>universalBootReady);
await assertTxCsvDownloads(2,'source-other');
profile.profile=1;profile.topology=1;profile.canA='PARTY';profile.canB='VH';useEmbedded=true;await page.goto('http://p4can.test/',{waitUntil:'load'});await page.waitForFunction(()=>universalBootReady);await showSettings();await assertList(settingsRoot,settingsPanels);await settingsRoot.locator('[data-panel="panelR79"]').click();await onlyPanel('panelR79');assert(await page.locator('#r79ApControlToggle').locator('..').isVisible());await page.locator('#panelR79 .backbtn').click();await page.waitForTimeout(380);await settingsRoot.locator('[data-panel="panelDiag"]').click();await onlyPanel('panelDiag');await settle();await assertAccordion('');await clickDiag('memory');await assertAccordion('memory');await clickDiag('memory');await assertAccordion('');await page.evaluate(()=>showPage('actions'));await page.waitForFunction(()=>!document.getElementById('preheatToggle').disabled);await assertPhysicalLabels(1,'embedded-yl');assert.deepEqual(errors,[]);
await assertTxCsvDownloads(1,'embedded-yl');
for(const id of [2,3,4,5]){profile.profile=id;profile.topology=2;profile.canA='BODY';profile.canB='CHASSIS';await page.goto('http://p4can.test/');await page.waitForFunction(()=>universalBootReady);await assertPhysicalLabels(id,'embedded-profile-'+id)}
profile.profile=2;profile.topology=2;await page.goto('http://p4can.test/');await page.waitForFunction(()=>universalBootReady);await assertTxCsvDownloads(2,'embedded-other');assert.deepEqual(errors,[]);
await browser.close();fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({sourceEmbeddedEqual:true,checks,errors,requests,originalListNavigation:true,diagnosticsInlineAccordion:true,diagnosticsSections:8,delayedResponseFences:true,inlineSettings:true,inlineFailureRecovery:true,s3xyWirelessSynchronized:true,phonePreferencesPersist:true,labInlineVisibility:true,scopedPolling:true,capturePreserved:true,saveFailure:true,embeddedFlow:true,apControlDelay:true,unknownDark:true,preheatEngine:true,thermal:true,directResetConfirmation:true,profileLabels:true,managedTxTraceDownloads:true,managedTxDownloadFailureCleanup:true},null,2));console.log('PASS: restored 3.29.1 inline Settings and inline Diagnostics accordion, actual toggles/choice persistence/Wireless sync and row/back navigation, selected full-CAN polling and delayed-response fences, managed A/B TX CSV routing/filenames/busy/pause/resume/failure cleanup for source/embedded YL/other profiles, capture/download, saves/direct confirmations, Actions/Thermal and source/embedded flow at 320/390/430 light/dark');
})().catch(e=>{console.error(e);process.exit(1)});
