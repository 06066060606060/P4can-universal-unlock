const fs=require('fs'),path=require('path'),assert=require('assert'),zlib=require('zlib'),vm=require('vm');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'dashboard_source.html'),'utf8');
assert(source.includes('id="canGpioSettingsRow"'),'Settings must expose the new CAN GPIO detail page');
const roles=source.slice(source.indexOf('function physicalCanRole'),source.indexOf('function diagValue'));
const block=source.slice(source.indexOf('// CAN_GPIO_SETTINGS_BEGIN'),source.indexOf('// CAN_GPIO_SETTINGS_END'));
assert(block.includes('/api/system/can-gpio'),'Use the shared physical mapping API');
const policy=block.slice(0,block.indexOf('const canGpioState')),validator=block.slice(block.indexOf('function canGpioMap('),block.indexOf('function canGpioResponse('));
assert.doesNotThrow(()=>vm.runInNewContext(policy+validator+'canGpioMap([{tx:0,rx:2},{tx:28,rx:33},{tx:52,rx:53}])'),'GPIOs outside the old whitelist must be selectable');
assert(!block.includes('setInterval('),'Mapping settings must not add periodic polling');
assert(source.includes("if(item.id==='panelCanGpio')return"),'Generic settings input feedback must not overwrite GPIO validation');
const embedded=zlib.gunzipSync(Buffer.from([...fs.readFileSync(path.join(root,'index_html.h'),'utf8').matchAll(/0x([0-9A-F]{2})/g)].map(m=>parseInt(m[1],16)))).toString();
assert.equal(embedded,source);
const defaults=[{tx:20,rx:21},{tx:50,rx:49},{tx:26,rx:27}],allowedPins=Array.from({length:55},(_,n)=>n).filter(n=>![6,14,15,16,17,18,19,24,25,54].includes(n));
const fixture=()=>({ok:true,valid:true,active:structuredClone(defaults),saved:structuredClone(defaults),defaults:structuredClone(defaults),allowedPins,rebootRequired:false,canStopped:false,error:''});
const output=process.env.P4_GPIO_OUTPUT||'/private/tmp/p4-v3330-gpio-browser';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||chromium.executablePath(),headless:true});
 let report=[];
 try{for(const [kind,html] of [['source',source],['embedded',embedded]]){
  const page=await browser.newPage({viewport:{width:390,height:1000}});let data=fixture(),gets=0,posts=[],failure=null,release=null,delayNext=false;const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('http://p4.test/**',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(url.pathname==='/api/system/can-gpio'){
    if(req.method()==='POST'){posts.push(url.searchParams);return route.fulfill({status:failure?500:200,contentType:'application/json',body:JSON.stringify(failure||{ok:true,rebooting:true})})}
    ++gets;const body=JSON.stringify(data);if(delayNext){delayNext=false;await new Promise(r=>release=r)}
    return route.fulfill({status:200,contentType:'application/json',body});
   }
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'')});
   return route.fulfill({status:204,body:''});
  });
  await page.goto('http://p4.test/');
  await page.evaluate(()=>{
   window.$=id=>document.getElementById(id);window.__p4ProfileId=1;
   window.dashboardFetch=(u,o)=>fetch(u,o);window.ok=()=>{};window.__confirm=true;window.confirm=s=>{window.__lastConfirm=s;return window.__confirm};
   window.waitForP4CanReconnect=()=>{window.__reconnect=true};
   document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.dataset.page==='settings'));
   $('canGpioSettingsRow').onclick=()=>{$('panelCanGpio').classList.remove('closing');$('panelCanGpio').classList.add('show')};
   $('panelCanGpio').querySelector('.backbtn').onclick=()=>$('panelCanGpio').classList.remove('show');
  });
  await page.addScriptTag({content:roles});await page.evaluate(()=>renderPhysicalCanLabels(1));
  await page.addScriptTag({content:block});
  const open=async()=>{await page.locator('#canGpioSettingsRow').click();await page.waitForFunction(()=>!document.getElementById('canGpio1Tx').disabled)};
  const fill=async(id,v)=>page.locator('#'+id).fill(String(v));
  await open();assert.equal(gets,1);assert.equal(await page.locator('#canGpio2Tx').inputValue(),'50');assert((await page.locator('#canGpio2Active').innerText()).includes('50'));
  assert.equal(await page.locator('#canGpioSave').isDisabled(),true);
  for(const profile of [1,2,3,4,5]){
   await page.evaluate(id=>{window.__p4ProfileId=id;renderPhysicalCanLabels(id);renderCanGpio()},profile);
   const expected=profile===1?['VEHICLE','BODY','PARTY']:['BODY','CHASSIS','PARTY'];
   assert.deepEqual(await page.locator('#panelCanGpio [data-can-role]').allTextContents(),expected,kind+' GPIO card roles for profile '+profile);
   for(let n=1;n<=3;n++)assert.equal(await page.locator('#canGpio'+n+'Tx').inputValue(),String(defaults[n-1].tx),'Role changes must not swap physical GPIO arrays');
  }
  await page.evaluate(()=>{window.__p4ProfileId=1;renderPhysicalCanLabels(1);renderCanGpio()});
  data={...fixture(),saved:[{tx:0,rx:2},{tx:28,rx:33},{tx:52,rx:53}],rebootRequired:true};await page.locator('#canGpioReload').click();await page.waitForFunction(()=>document.getElementById('canGpio1Tx').value==='0');
  assert.equal(await page.locator('#canGpio2Tx').inputValue(),'28');assert.equal(await page.locator('#canGpio2Active').innerText(),'Active · TX 50 / RX 49','Saved pins and active pins remain distinct');
  data=fixture();await page.locator('#canGpioReload').click();await page.waitForFunction(()=>document.getElementById('canGpio1Tx').value==='20');
  await fill('canGpio2Tx',20);assert(await page.locator('#canGpioSave').isDisabled());assert.match(await page.locator('#canGpioState').innerText(),/unique|duplicate/i);assert.equal(posts.length,0);
  await fill('canGpio2Tx',55);assert(await page.locator('#canGpioSave').isDisabled());
  await fill('canGpio2Tx',14);assert(await page.locator('#canGpioSave').isDisabled());
  await fill('canGpio2Tx',0);assert(!await page.locator('#canGpioSave').isDisabled());
  await fill('canGpio2Tx',28);await fill('canGpio2Rx',33);assert(!await page.locator('#canGpioSave').isDisabled());
  await page.evaluate(()=>window.__confirm=false);await page.locator('#canGpioSave').click();assert.equal(posts.length,0);
  assert.match(await page.evaluate(()=>window.__lastConfirm),/CAN 1 VEHICLE: TX20 \/ RX21[\s\S]*CAN 2 BODY: TX28 \/ RX33[\s\S]*CAN 3 PARTY: TX26 \/ RX27/);
  failure={ok:false,error:'CAN stop not confirmed',canStopped:false,rebootRequired:true};await page.evaluate(()=>window.__confirm=true);await page.locator('#canGpioSave').click();
  await page.waitForFunction(()=>document.getElementById('canGpioState').textContent.includes('CAN stop not confirmed'));
  assert(!/CAN is stopped/i.test(await page.locator('#canGpioState').innerText()),'An unconfirmed stop must not be displayed as confirmed stopped');
  failure={ok:false,error:'Storage write failed',canStopped:true,rebootRequired:true};await page.locator('#canGpioSave').click();
  await page.waitForFunction(()=>document.getElementById('canGpioState').textContent.includes('Storage write failed'));
  assert.match(await page.locator('#canGpioState').innerText(),/CAN.*stopped/i);assert(!await page.evaluate(()=>!!window.__reconnect));assert.equal(posts[0].get('tx2'),'28');assert.equal([...posts[0].keys()].length,6);
  // A delayed response from the previous open must not overwrite a new view.
  await page.locator('#panelCanGpio .backbtn').click();const closedGets=gets;
  await page.evaluate(()=>document.getElementById('panelCanGpio').classList.add('closing'));assert.equal(gets,closedGets);
  delayNext=true;await page.locator('#canGpioSettingsRow').click();await page.waitForFunction(()=>document.getElementById('canGpioState').textContent.includes('Loading'));
  await page.waitForTimeout(30);assert(release);await page.locator('#panelCanGpio .backbtn').click();
  data={...fixture(),valid:false,active:null,saved:null,canStopped:true,error:'Stored GPIO map is invalid'};
  await open();const invalidState=await page.locator('#canGpioState').innerText();assert.match(invalidState,/disabled|stopped/i);release();release=null;
  await page.waitForTimeout(30);assert.match(await page.locator('#canGpioState').innerText(),/disabled|stopped/i);assert.match(await page.locator('#canGpio2Active').innerText(),/unavailable|not active/i);
  await fill('canGpio2Tx',28);await fill('canGpio2Rx',33);
  for(const theme of ['light','dark'])for(const width of [320,390,430]){
   await page.setViewportSize({width,height:1000});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
   await page.evaluate(async()=>{await document.fonts.ready;await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))});
   assert(await page.locator('#panelCanGpio').evaluate(p=>p.scrollWidth<=p.clientWidth),`${kind}/${theme}/${width} overflow`);
   const fields=await page.locator('#panelCanGpio .field input').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect(),p=e.closest('.field').getBoundingClientRect();return r.left>=p.left&&r.right<=p.right+1&&r.height>0}));assert(fields.every(Boolean));
   await page.screenshot({path:path.join(output,`${kind}-${theme}-${width}.png`)});report.push({kind,theme,width});
  }
  // Recovery edits remain usable; successful submission enters reconnect only.
  failure=null;await page.locator('#canGpioSave').click();await page.waitForFunction(()=>window.__reconnect===true);
  assert.equal(posts.length,3);assert.equal(posts[2].get('rx2'),'33');assert.deepEqual(errors,[]);await page.close();
 }
 // Run the complete shipped scripts as well as the isolated settings controller.
 const full=await browser.newPage({viewport:{width:390,height:1000}}),fullErrors=[];let fullGets=0;
 full.on('pageerror',e=>fullErrors.push(String(e)));
 await full.route('http://p4-full.test/**',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:source});
  if(u.pathname==='/api/system/can-gpio'){++fullGets;return route.fulfill({contentType:'application/json',body:JSON.stringify(fixture())})}
  if(u.pathname.startsWith('/api/')){let value={ok:true};
   if(u.pathname==='/api/profile/status')value={ok:true,setupMode:false,nvsError:false,profile:1,topology:1,turn:1,canA:'PARTY',canB:'VH',canBusCount:3,nagSupported:false,advancedEapSupported:true,euUnlockSupported:true,pedalMapSupported:true};
   if(u.pathname==='/api/snapshot')value={nag:{},blink:{},summon:{},cantraffic:{},r79:{},s3xy:{},lab3f8:{}};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
  }return route.fulfill({status:204,body:''});
 });
 await full.goto('http://p4-full.test/');await full.waitForFunction(()=>typeof universalBootReady!=='undefined'&&universalBootReady);
 await full.evaluate(()=>showPage('settings'));await full.locator('#canGpioSettingsRow').click();
 await full.waitForFunction(()=>!document.getElementById('canGpio1Tx').disabled);
 await full.locator('#canGpio2Tx').fill('20');assert.match(await full.locator('#canGpioState').innerText(),/unique/i,'Generic feedback must preserve GPIO validation in the full application');
 await full.locator('#canGpio2Tx').fill('28');await full.locator('#canGpio2Rx').fill('33');
 assert(!await full.locator('#canGpioSave').isDisabled());assert.equal(fullGets,1);assert.deepEqual(await full.locator('#panelCanGpio [data-can-role]').allTextContents(),['VEHICLE','BODY','PARTY']);assert.deepEqual(fullErrors,[]);
 await full.evaluate(async()=>{await document.fonts.ready;await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))});
 assert.equal(await full.locator('#panelCanGpio').evaluate(p=>getComputedStyle(p).opacity),'1','Full application screenshot must follow the completed page animation');
 await full.screenshot({path:path.join(output,'full-application-390.png')});await full.close();
 }finally{await browser.close()}
 fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({checks:report,sourceEmbedded:true,errors:[]},null,2));
 console.log('PASS: source/embedded GPIO UI, all-profile physical roles, saved/active distinction, allowed/unique validation, confirmation, six-field API, save failure/CAN-stop recovery, stale-open fencing, corrupt recovery, reconnect and 320/390/430 light/dark');
})().catch(e=>{console.error(e);process.exit(1)});
