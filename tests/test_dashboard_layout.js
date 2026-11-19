// Real CSS/markup regression: no scripts, device requests or CAN access.
const fs=require('fs'),path=require('path'),assert=require('assert'),zlib=require('zlib'),crypto=require('crypto');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'dashboard_source.html'),'utf8');
const header=fs.readFileSync(path.join(root,'index_html.h'),'utf8');
assert.equal(zlib.gunzipSync(Buffer.from([...header.matchAll(/0x([0-9A-F]{2})/g)].map(m=>parseInt(m[1],16)))).toString(),source);
const referencePath=process.env.P4_SETTINGS_REFERENCE||path.join(root,'tests/fixtures/settings_v3291_reference.html');
const referenceSource=fs.readFileSync(referencePath,'utf8');
const referenceSha256=crypto.createHash('sha256').update(referenceSource).digest('hex');
assert.equal(referenceSha256,'1458fd4892b313e953032f6e6a3d611fb9af361798ef3eb4d65a678a966f584a','Reference must be the original 3.29.1 source bytes');
const originalHeader=path.join(root,'../P4-CAN-Universal-v3.29.2/index_html.h');
let referenceEmbeddedEqual=null;
if(fs.existsSync(originalHeader)){
 const originalEmbedded=zlib.gunzipSync(Buffer.from([...fs.readFileSync(originalHeader,'utf8').matchAll(/0x([0-9A-F]{2})/g)].map(m=>parseInt(m[1],16)))).toString();
 assert.equal(originalEmbedded,referenceSource,'Original generated dashboard must match the source reference');referenceEmbeddedEqual=true;
}
const output=process.env.P4_LAYOUT_OUTPUT;
if(output)fs.mkdirSync(output,{recursive:true});
const roles=source.slice(source.indexOf('function physicalCanRole'),source.indexOf('function diagValue'));
const html=source.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||chromium.executablePath(),headless:true});
 const checks=[];
 try{
  const page=await browser.newPage({viewport:{width:390,height:1000},reducedMotion:'reduce'});
  const referencePage=await browser.newPage({viewport:{width:390,height:1000},reducedMotion:'reduce'});
  await referencePage.route('**/*',route=>route.abort());
  await referencePage.setContent(referenceSource.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''),{waitUntil:'domcontentloaded'});
  await referencePage.evaluate(()=>{
   document.querySelector('[data-panel=panelR79] .listdesc').textContent='Configure R79 timing and bit policy.';
   // Explicit restoration exceptions: historical chips and retired danger controls.
   document.querySelectorAll('.profileChips,#bannedDangerHead,#bannedDangerZone').forEach(e=>e.remove());
   document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.dataset.page==='settings'));
   document.querySelectorAll('#bottomNav .navbtn').forEach(n=>n.classList.remove('hiddenByProfile'));
   document.getElementById('bottomNav').classList.remove('labHidden','devicesHidden');
  });
  const referenceMetrics=[];
  const settingsMetrics=()=>{
   const root=document.querySelector('main[data-page="settings"]');
   const styleKeys=['display','fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','borderTopWidth','borderTopColor','borderRadius','paddingTop','paddingRight','paddingBottom','paddingLeft','gap','minHeight'];
   const metric=e=>{
    const r=e.getBoundingClientRect(),style=getComputedStyle(e);
    const directText=[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim()).map(n=>n.textContent.trim()).join(' ');
    const paintedText=[e,...e.querySelectorAll('.listkey,.listdesc,.chev,.value')].filter(n=>[...n.childNodes].some(c=>c.nodeType===Node.TEXT_NODE&&c.textContent.trim())).map(n=>{const c=getComputedStyle(n),b=n.getBoundingClientRect();return {tag:n.tagName,id:n.id,classes:n.className,text:n.textContent.trim(),color:c.color,opacity:c.opacity,display:c.display,visibility:c.visibility,width:b.width,height:b.height}});
    return {tag:e.tagName,classes:e.className,directText,paintedText,style:Object.fromEntries(styleKeys.map(k=>[k,style[k]])),rect:{x:r.x,width:r.width,height:r.height}};
   };
   const rows=[...root.querySelectorAll('.listrow')].filter(e=>!e.querySelector('#actionsMenuToggle')&&e.id!=='canGpioSettingsRow');
   const bodyStyle=getComputedStyle(document.body),rootStyle=getComputedStyle(document.documentElement);
   const context={theme:document.documentElement.dataset.theme,ap:document.body.dataset.ap,bodyClass:document.body.className,bodyColor:bodyStyle.color,bodyBackground:bodyStyle.backgroundColor,rootColor:rootStyle.color,variables:Object.fromEntries(['--ink','--muted','--muted2','--field','--field-ink','--accent','--accent-rgb','--card','--line'].map(k=>[k,{root:rootStyle.getPropertyValue(k).trim(),body:bodyStyle.getPropertyValue(k).trim()}]))};
   return {context,rows:rows.map(e=>({key:e.id||e.dataset.panel||e.querySelector('input')?.id||e.querySelector('.listkey')?.textContent,metric:metric(e),children:[...e.querySelectorAll('.listkey,.listdesc,.chev,.value,.toggle,.track,.settingChoiceButtons,.settingChoiceButtons button,.settingSourceSelect')].map(metric)})),headings:[...root.querySelectorAll('.pageTitle,.pageSub,.sectionhead,.profileCompact')].map(metric)};
  };
  let comparisonContext=null;
  const compareMetrics=(actual,expected,label)=>{
   assert.equal(actual.tag,expected.tag,label+' tag');assert.equal(actual.classes,expected.classes,label+' class structure');
   const styleDiff=Object.keys(expected.style).filter(key=>actual.style[key]!==expected.style[key]).map(key=>({property:key,current:actual.style[key],reference:expected.style[key]}));
   assert.deepEqual(actual.style,expected.style,label+' computed styles must match 3.29.1: '+JSON.stringify({differences:styleDiff,current:actual,reference:expected,context:comparisonContext}));
   for(const key of ['x','width','height'])assert(Math.abs(actual.rect[key]-expected.rect[key])<.8,label+' '+key+': '+actual.rect[key]+' vs '+expected.rect[key]);
  };
  const detailHeaders=['panelNag','panelNagModeH','panelVisionControl','panelBlink','panelSummon','panelR79','panelCountry','panelTlssc','panelUlc','panelPedalMap','panelContinuousAp','panelApDriveProfile','panelWireless','panelDiag','panelOta'];
  const headerMetrics=id=>[...document.querySelectorAll('#'+id+' .panelin>.paneltop,#'+id+' .panelin>.panelHero,#'+id+' .panelin>.panelSub')].slice(0,3).map(e=>{
   const r=e.getBoundingClientRect(),style=getComputedStyle(e);
   return {tag:e.tagName,classes:e.className,text:e.textContent.trim(),style:Object.fromEntries(['display','fontFamily','fontSize','fontWeight','lineHeight','color','paddingTop','paddingRight','paddingBottom','paddingLeft','marginTop','marginBottom'].map(k=>[k,style[k]])),rect:{x:r.x,width:r.width,height:r.height}};
  });
  // Full-document screenshots otherwise include closed sheets transformed below
  // the viewport. Hide only those closed layers in snapshots, not production CSS.
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
  await page.route('**/*',route=>route.abort());
  await page.setContent(html,{waitUntil:'domcontentloaded'});
  await page.addScriptTag({content:roles});await page.evaluate(()=>{window.$=id=>document.getElementById(id);window.__p4ProfileId=1;renderPhysicalCanLabels(1)});
  for(const profile of [1,2,3,4,5]){
   await page.evaluate(id=>renderPhysicalCanLabels(id),profile);
   const expected=profile===1?['VEHICLE','BODY','PARTY']:['BODY','CHASSIS','PARTY'];
   assert.deepEqual(await page.locator('#homeCanCard .homeBusRole').allTextContents(),expected);
   for(const area of ['#homeCanDetails','#panelCanGpio','#panelDiag'])assert.deepEqual(await page.locator(area+' [data-can-role]').allTextContents(),expected);
  }
  await page.evaluate(()=>renderPhysicalCanLabels(1));
  await page.evaluate(()=>{document.querySelectorAll('#bottomNav .navbtn').forEach(n=>n.classList.remove('hiddenByProfile'));document.getElementById('bottomNav').classList.remove('labHidden','devicesHidden')});
  const activate=async(panel,rootPage='home')=>{await page.evaluate(({id,rootPage})=>{
   document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.dataset.page===(id?'settings':rootPage)));
   document.querySelectorAll('.panel').forEach(p=>{p.classList.toggle('show',p.id===id);p.scrollTop=0});window.scrollTo(0,0);
  },{id:panel,rootPage});
   // Layout assertions and pictures must observe the final panel geometry.
   await page.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   });
  };
  const settingsPanels=['panelNag','panelVisionControl','panelBlink','panelSummon','panelR79','panelCountry','panelTlssc','panelUlc','panelPedalMap','panelContinuousAp','panelApDriveProfile','panelWireless','panelCanGpio','panelDiag','panelOta'];
  const diagnosticSections=['system','memory','wireless','ble','can1','can2','can3','recovery'];
  const activateDiag=async section=>{
   await activate('panelDiag');
   await page.evaluate(section=>document.querySelectorAll('#panelDiag [data-diag-category]').forEach(card=>{
    const open=card.dataset.diagCategory===section,button=card.querySelector('[data-diag-toggle]'),body=card.querySelector('[data-diag-section]');
    card.classList.toggle('open',open);button.setAttribute('aria-expanded',String(open));body.inert=!open;body.setAttribute('aria-hidden',String(!open));
   }),section);
   await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))});
  };
  const assertDiagLayout=async(section,width,theme)=>{
   assert.deepEqual(await page.locator('#panelDiag [data-diag-category]').evaluateAll(es=>es.map(e=>e.dataset.diagCategory)),diagnosticSections);
   assert.equal(await page.locator('#panelDiag [data-panel],#panelDiag details').count(),0,'Diagnostics stays inline');
   const invalid=await page.locator('#panelDiag [data-diag-category]').evaluateAll((cards,selected)=>cards.flatMap(card=>{
    const toggle=card.querySelector('[data-diag-toggle]'),body=card.querySelector('[data-diag-section]'),open=card.dataset.diagCategory===selected,r=toggle.getBoundingClientRect(),arrow=toggle.querySelector('.chev').getBoundingClientRect(),problems=[];
    if(toggle.tagName!=='BUTTON'||toggle.getAttribute('aria-controls')!==body.id||toggle.getAttribute('aria-expanded')!==String(open)||body.inert===open)problems.push('ARIA/keyboard region state');
    if(!r.height||r.left<-.5||r.right>innerWidth+.5)problems.push('toggle outside viewport');
    const range=document.createRange();range.selectNodeContents(toggle.querySelector('.listkey'));
    if([...range.getClientRects()].some(t=>t.width&&(t.left<r.left-.5||t.right>arrow.left+.5)))problems.push('toggle text overlaps chevron');
    const b=body.getBoundingClientRect();if(!open&&b.height>.5)problems.push('closed content reserves height');
    if(open){if(!b.height)problems.push('open content hidden');if(body.scrollWidth>body.clientWidth+1)problems.push('open content scroll overflow');
     for(const e of body.querySelectorAll('.r>span,.softNote,button,a')){const range=document.createRange();range.selectNodeContents(e);if([...range.getClientRects()].some(t=>t.width&&(t.left<b.left-.5||t.right>b.right+.5)))problems.push('content outside category: '+e.textContent.trim())}
    }
    return problems.map(reason=>({section:card.dataset.diagCategory,reason}));
   }),section);
   assert.deepEqual(invalid,[],`${width}/${theme} Diagnostics ${section||'closed'} must fit`);
   for(const id of ['btnResetStats','btnReinit'])assert(await page.locator('#'+id).evaluate(e=>!e.closest('[data-diag-section]')&&!e.closest('[inert]')&&getComputedStyle(e).visibility==='visible'),'Single actions remain available outside accordion content');
  };
  const assertMenuLayout=async(selector,expected,width,theme)=>{
   const menu=page.locator(selector),rows=menu.locator('.listrow[data-panel]');
   assert.deepEqual(await rows.evaluateAll(es=>es.map(e=>e.dataset.panel)),expected);
   assert.equal(await menu.locator('.category,.categorySummary,.categoryReveal,details').count(),0,'Original navigation has no expanding categories');
   const invalid=await rows.evaluateAll(es=>es.flatMap(e=>{
    const r=e.getBoundingClientRect(),arrow=e.querySelector('.chev').getBoundingClientRect();
    if(!r.height||!r.width||e.closest('[inert]')||getComputedStyle(e).visibility!=='visible')return [{panel:e.dataset.panel,reason:'hidden row'}];
    if(r.left<-.5||r.right>innerWidth+.5)return [{panel:e.dataset.panel,reason:'row outside viewport'}];
    return [...e.querySelectorAll('.listkey,.listdesc')].flatMap(label=>{
     const range=document.createRange();range.selectNodeContents(label);
     return [...range.getClientRects()].filter(t=>t.width&&(t.left<r.left-.5||t.right>r.right+.5||t.top<r.top-.5||t.bottom>r.bottom+.5||(t.right>arrow.left+.5&&t.left<arrow.right&&t.top<arrow.bottom&&t.bottom>arrow.top))).map(()=>({panel:e.dataset.panel,reason:'clipped or overlapping text',text:label.textContent}));
    });
   }));
   assert.deepEqual(invalid,[],`${width}/${theme} ${selector} list rows must remain displayed and readable`);
  };
  for(const theme of ['light','dark'])for(const width of [320,390,430]){
   await page.setViewportSize({width,height:1000});await referencePage.setViewportSize({width,height:1000});
   await referencePage.evaluate(t=>{document.documentElement.dataset.theme=t;document.body.dataset.ap='STANDBY';document.querySelectorAll('.panel').forEach(p=>p.classList.remove('show'));window.scrollTo(0,0)},theme);
   await page.evaluate(t=>{document.documentElement.dataset.theme=t;document.body.dataset.ap='STANDBY'},theme);
   const navClipped=await page.locator('#bottomNav').evaluate(nav=>{const r=nav.getBoundingClientRect();return [...nav.querySelectorAll('.navbtn')].filter(n=>{const b=n.getBoundingClientRect();const range=document.createRange();range.selectNodeContents(n);const t=range.getBoundingClientRect();return b.left<r.left-.5||b.right>r.right+.5||t.left<r.left-.5||t.right>r.right+.5}).map(n=>n.textContent)});
   assert.deepEqual(navClipped,[],`${width}/${theme} five-tab navigation clips`);
   await activate('');await page.evaluate(()=>document.getElementById('homeCanDetails').open=false);
   for(const profile of [1,2]){
    await page.evaluate(id=>renderPhysicalCanLabels(id),profile);
    const clipped=await page.locator('#homeCanCard .homeBusRole').evaluateAll(es=>es.flatMap(e=>{const r=e.closest('.homeBus').getBoundingClientRect(),range=document.createRange();range.selectNodeContents(e);return [...range.getClientRects()].filter(t=>t.width&&(t.left<r.left-.5||t.right>r.right+.5)).map(()=>e.textContent)}));
    assert.deepEqual(clipped,[],`${width}/${theme}/profile${profile} Home roles must fit`);
   }
   await page.evaluate(()=>renderPhysicalCanLabels(1));
   let maxCenterErrorPx=0;
   for(const labels of [['RUNNING','RUNNING','RUNNING'],['STOPPED','BUS OFF','RECOVERING']]){
    const metrics=await page.evaluate(states=>{
     return states.map((state,i)=>{
      const badge=document.getElementById('can'+(i+1)+'Badge');badge.textContent=state;document.getElementById('can'+(i+1)+'Traffic').textContent=state==='RUNNING'?'LIVE':'WAITING';badge.className='badge '+(state==='RUNNING'?'good':'bad');
      const column=badge.closest('.homeBus'),range=document.createRange();range.selectNodeContents(badge);
      const r=range.getBoundingClientRect(),c=column.getBoundingClientRect();
      return {state,textCenter:r.x+r.width/2,columnCenter:c.x+c.width/2,textLeft:r.left,textRight:r.right,columnLeft:c.left,columnRight:c.right,fontSize:parseFloat(getComputedStyle(badge).fontSize),textTop:r.top};
     });
    },labels);
    for(const m of metrics){maxCenterErrorPx=Math.max(maxCenterErrorPx,Math.abs(m.textCenter-m.columnCenter));assert(Math.abs(m.textCenter-m.columnCenter)<=1,`${width}/${theme} ${m.state} status is off center: ${JSON.stringify(m)}`);assert(m.fontSize>=10,'CAN status text must remain readable');assert(m.textLeft>=m.columnLeft&&m.textRight<=m.columnRight,'CAN status text is clipped')}
    assert(Math.max(...metrics.map(m=>m.textTop))-Math.min(...metrics.map(m=>m.textTop))<1,'CAN status rows must share a baseline');
    if(output&&labels[0]==='RUNNING')await page.locator('#homeCanCard').screenshot({path:path.join(output,`home-running-${width}-${theme}.png`)});
   }
   await page.evaluate(()=>{document.getElementById('homeCanDetails').open=true;for(let n=1;n<=3;n++)document.getElementById('can'+n+'Age').textContent=document.getElementById('can'+n+'Badge').textContent+' · no recent frames'});
   const homeNote=await page.locator('#homeCanDetails').evaluate(e=>({body:e.querySelector('.body').getBoundingClientRect().left+parseFloat(getComputedStyle(e.querySelector('.body')).paddingLeft),note:e.querySelector('.softNote').getBoundingClientRect().left+parseFloat(getComputedStyle(e.querySelector('.softNote')).paddingLeft)}));
   assert(Math.abs(homeNote.body-homeNote.note)<1,'Home Details note must align with telemetry text');
   assert(await page.evaluate(()=>getComputedStyle(document.querySelector('#homeCanDetails>.softNote')).fontSize===getComputedStyle(document.getElementById('r79ApSaveState')).fontSize),'Home explanation must share the detail paragraph text size');
   if(output)await page.locator('#homeCanCard').screenshot({path:path.join(output,`home-${width}-${theme}.png`)});
   await activate('','settings');await assertMenuLayout('main[data-page="settings"]',settingsPanels,width,theme);
   assert.deepEqual(await page.locator('main[data-page="settings"] .sectiontitle').allTextContents(),['Features','System']);
   // The historical Settings root stays displayed while theme changes. Its
   // inherited card/page color transitions must settle just like the current
   // page's finite animations; hidden current pages otherwise jump to final
   // colors while the visible reference can still be between light and dark.
   await referencePage.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   });
   const actual=await page.evaluate(settingsMetrics),expected=await referencePage.evaluate(settingsMetrics);
   comparisonContext={current:actual.context,reference:expected.context};
   assert.deepEqual(actual.rows.map(r=>r.key),expected.rows.map(r=>r.key),'Original inline/list row order');
   for(let i=0;i<actual.rows.length;i++){
    const a=actual.rows[i],b=expected.rows[i];compareMetrics(a.metric,b.metric,`${width}/${theme} ${a.key}`);
    assert.equal(a.children.length,b.children.length,a.key+' original child hierarchy');
    a.children.forEach((m,j)=>compareMetrics(m,b.children[j],`${width}/${theme} ${a.key} child ${j}`));
   }
   assert.equal(actual.headings.length,expected.headings.length);actual.headings.forEach((m,i)=>compareMetrics(m,expected.headings[i],`${width}/${theme} root heading ${i}`));
   const warningColors=await page.evaluate(()=>({normal:getComputedStyle(document.querySelector('main[data-page="settings"] [data-panel="panelOta"] .listkey')).color,actions:['rebootRow','resetSettingsBtn','resetNvsKeepBleBtn','factoryResetBtn'].map(id=>({id,color:getComputedStyle(document.querySelector('#'+id+' .listkey')).color}))}));
   for(const action of warningColors.actions)assert.equal(action.color===warningColors.normal,action.id!=='factoryResetBtn',`${width}/${theme} only Factory Reset uses original danger color`);
   referenceMetrics.push({width,theme,actual,reference:expected,warningColors,exceptions:['profileChips','Banned Car / TLSSC Restore','new inline Actions Menu']});
   if(output){
    // Apply the same closed-sheet capture rule to the historical comparison.
    const saved=await referencePage.locator('.sheet:not(.show),.sheetback:not(.show)').evaluateAll(es=>es.map(e=>{const s={id:e.id,style:e.getAttribute('style')};e.style.setProperty('transition','none','important');e.style.setProperty('visibility','hidden','important');return s}));
    try{await referencePage.screenshot({path:path.join(output,`settings-reference-${width}-${theme}.png`),fullPage:true})}
    finally{await referencePage.evaluate(saved=>saved.forEach(({id,style})=>{const e=document.getElementById(id);if(style===null)e.removeAttribute('style');else e.setAttribute('style',style)}),saved)}
   }
   if(output)await page.screenshot({path:path.join(output,`settings-root-${width}-${theme}.png`),fullPage:true});
   if(output){await page.locator('#factoryResetBtn').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,`settings-actions-${width}-${theme}.png`)});}
   for(const id of detailHeaders){
    await activate(id);await referencePage.evaluate(id=>{document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('show',p.id===id));document.getElementById(id).scrollTop=0},id);
    await referencePage.evaluate(async()=>{await document.fonts.ready;await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))});
    const a=await page.evaluate(headerMetrics,id),b=await referencePage.evaluate(headerMetrics,id);
    assert.equal(a.length,b.length,id+' original heading hierarchy');
    a.forEach((m,i)=>{
     let expectedText=b[i].text;
     if(id==='panelR79'&&i===2){
      assert.equal(expectedText,'Mode 1 / 2 · manual D/R suppression.');
      expectedText='Mode 1 · manual D/R suppression.';
     }
     assert.equal(m.text,expectedText,id+' heading text');
     compareMetrics(m,b[i],`${width}/${theme} ${id} header ${i}`);
    });
    if(output&&['panelNag','panelR79','panelWireless','panelDiag','panelOta'].includes(id)){
     await page.screenshot({path:path.join(output,`header-current-${id}-${width}-${theme}.png`)});
     // Panel screenshots are viewport-only, so the closed offscreen layers do not overlap.
     await referencePage.screenshot({path:path.join(output,`header-reference-${id}-${width}-${theme}.png`)});
    }
   }
   await activateDiag('');await assertDiagLayout('',width,theme);
   if(output)await page.screenshot({path:path.join(output,`diagnostics-root-${width}-${theme}.png`)});
   for(const section of diagnosticSections){
    await activateDiag(section);
    if(section==='can2')await page.evaluate(()=>{
     document.getElementById('diagCan2Mode').textContent='LISTEN_ONLY · 500 kbit/s';
     document.getElementById('diagCan2ErrorNote').textContent='TEC and REC are frozen in LISTEN_ONLY; zero does not mean no errors. Bus Error and ECC are separate observations.';
    });
    await assertDiagLayout(section,width,theme);
    if(output){
     // Diagnostics is a fixed, internally scrolling panel. A full-document
     // screenshot would expose the Settings document beneath its viewport.
     await page.locator('#panelDiag [data-diag-toggle="'+section+'"]').evaluate(e=>{e.scrollIntoView({block:'start',behavior:'instant'});e.closest('.panel').scrollBy({top:-60,left:0,behavior:'instant'})});
     await page.screenshot({path:path.join(output,`diagnostics-${section}-${width}-${theme}.png`),fullPage:false});
    }
    await activateDiag('');await assertDiagLayout('',width,theme);
   }
   for(const panel of ['panelR79','panelDiag']){
    if(panel==='panelDiag')await activateDiag('can1');else await activate(panel);
    const scope=panel==='panelDiag'?'#diagBodyCan1':'#panelR79';
    await page.evaluate(()=>{
     document.getElementById('r79TimingCount').textContent='12345 / 32768';
     document.getElementById('r79TimingWarnings').classList.remove('tuUiHidden');document.getElementById('r79TimingWarnings').textContent='9 dropped records · 3 CAN 2 errors lost · 2 driver snapshot failures · CAN 2 error sequence saturated · CAN 2 error import pending';
     document.getElementById('diagCan1Polls').textContent='200 / ESP_ERR_TIMEOUT';
     document.getElementById('diagCan1State').textContent='RUNNING · 50 ms ago';
    });
    const rows=await page.locator(scope+' .r').evaluateAll(nodes=>nodes.filter(e=>e.getBoundingClientRect().height).map(e=>{
     const spans=e.querySelectorAll(':scope>span'),a=spans[0].getBoundingClientRect(),b=spans[1].getBoundingClientRect(),r=e.getBoundingClientRect();
     return {label:spans[0].textContent,ax:a.left,ay:a.top,ab:a.bottom,bx:b.left,by:b.top,br:b.right,left:r.left,right:r.right};
    }));
    assert(rows.length>0);
    for(const r of rows){assert(Math.abs(r.ax-r.left)<1,'Telemetry labels must align to the row start');
     if(width<=390){assert(Math.abs(r.bx-r.left)<1,`${width}/${panel} ${r.label}: wrapped value must align left`);assert(r.by>=r.ab-1,'Stacked telemetry overlaps its label')}
     else assert(Math.abs(r.br-r.right)<1,`${width}/${panel} ${r.label}: values must align to a common right edge`);
    }
    const notes=await page.locator(scope+' .softNote').evaluateAll(nodes=>nodes.filter(e=>e.getBoundingClientRect().height&&e.previousElementSibling?.classList.contains('body')).map(e=>{
     const body=e.previousElementSibling,br=body.getBoundingClientRect(),r=e.getBoundingClientRect(),a=getComputedStyle(body),b=getComputedStyle(e);
     return {bodyLeft:br.left+parseFloat(a.paddingLeft),noteLeft:r.left+parseFloat(b.paddingLeft),bodyRight:br.right-parseFloat(a.paddingRight),noteRight:r.right-parseFloat(b.paddingRight)};
    }));
    for(const n of notes)assert(Math.abs(n.bodyLeft-n.noteLeft)<1&&Math.abs(n.bodyRight-n.noteRight)<1,`${panel} paragraph inset differs from its card body: ${JSON.stringify(n)}`);
    if(output){const target=panel==='panelR79'?'#panelR79 .card:has(#r79TimingCount)':'#panelDiag [data-diag-category=can1]';await page.locator(target).screenshot({path:path.join(output,`${panel}-${width}-${theme}.png`)});}
    if(panel==='panelDiag'){
     const note=page.locator('#diagBodyCan1 .softNote').last();await note.evaluate(e=>e.scrollIntoView({block:'center'}));
     const visible=await note.evaluate(e=>{const r=e.getBoundingClientRect(),nav=document.getElementById('bottomNav').getBoundingClientRect();return r.top>=48&&r.bottom<=nav.top});
     assert(visible,'Diagnostics paragraph must be scrollable clear of fixed navigation');
     if(output)await page.screenshot({path:path.join(output,`paragraph-readable-${width}-${theme}.png`)});
    }
   }
   await page.evaluate(()=>{document.querySelectorAll('.panel').forEach(p=>p.classList.remove('show'));document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.dataset.page==='actions'));document.getElementById('preheatRaw').open=true});
   const overlap=await page.locator('#preheatRaw .listrow').evaluateAll(rows=>rows.filter(row=>{const key=row.querySelector('.listkey'),value=row.querySelector('.rowRight .value');if(!key||!value)return false;const range=document.createRange();range.selectNodeContents(key);const v=value.getBoundingClientRect(),r=row.getBoundingClientRect();return [...range.getClientRects()].some(k=>k.right>r.right+.5||(k.right>v.left+.5&&k.left<v.right&&k.top<v.bottom&&k.bottom>v.top))}).map(r=>r.querySelector('.listkey').textContent));
   assert.deepEqual(overlap,[],`${width}/${theme} raw signal names overlap their values`);
   if(output)await page.locator('#preheatRaw').screenshot({path:path.join(output,`preheat-raw-${width}-${theme}.png`)});
   checks.push({width,theme,maxCenterErrorPx,fiveTabNavFits:true,settingsListAlwaysVisible:true,diagnosticsInlineCategories:8,diagnosticsSingleActionsAlwaysAvailable:true,listTextReadable:true,originalResetColors:true,settingsMatchOriginalStyles:true,rawSignalNoOverlap:true,statusCentered:true,paragraphInsets:true,telemetryAligned:true,paragraphScrollableAboveNav:true});
  }
  if(output)fs.writeFileSync(path.join(output,'layout-report.json'),JSON.stringify({checks,sourceEmbeddedEqual:true,referenceSha256,referenceEmbeddedEqual,referenceMetrics,detailHeaderCount:detailHeaders.length,networkRequests:false},null,2));
  console.log('PASS: 3.29.1 reference/current Settings DOM/computed styles and 15 detail heroes, inline control geometry and eight inline Diagnostics categories, actual CAN text centering, Home note insets and R79/Diagnostics telemetry alignment at 320/390/430px in both themes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
