from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path(__file__).resolve().parents[1];stats=dict(ok=True,enabled=False,suspendDuringAp=False,apBlocked=False,values=0,mux0Fresh=True,mux2Fresh=True,txOk=0,txFail=0,**{'stock'+str(i):i%2 for i in range(8)})
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 page=b.new_page(viewport=dict(width=430,height=1000));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto((root/'dashboard_demo.html').as_uri());page.wait_for_timeout(300)
 def api(route):
  from urllib.parse import urlparse,parse_qs
  url=urlparse(route.request.url)
  if url.path.endswith('/update'):
   args=parse_qs(url.query);stats['enabled']=args['enabled']==['1'];stats['values']=int(args['values'][0])
  route.fulfill(content_type='application/json',body=json.dumps(stats))
 page.evaluate('s=>{window.demoFsd=s;jget=async()=>({...window.demoFsd});featurePostJson=async url=>{const q=new URL(url,"http://demo").searchParams;window.demoFsd.enabled=q.get("enabled")==="1";window.demoFsd.values=Number(q.get("values"));window.demoFsd.suspendDuringAp=q.get("suspendDuringAp")==="1";return {...window.demoFsd}}}',stats)
 page.evaluate("openPanel('panelFsd');fetchFsdSettings()")
 page.wait_for_function('fsdSettingsSaved!==null')
 assert '1' in page.locator('#fsdRead1').inner_text()
 assert page.locator('#panelFsd input[type=checkbox]').count()==3
 page.locator('label.toggle').filter(has=page.locator('#fsdMaster')).click();page.wait_for_function('!fsdSettingsBusy');assert page.evaluate('demoFsd.enabled')
 for i in [1]:
  page.locator('label.toggle').filter(has=page.locator('#fsdField'+str(i))).click();page.wait_for_function('!fsdSettingsBusy')
 assert page.evaluate('demoFsd.values')==2
 page.locator('label.toggle').filter(has=page.locator('#fsdSuspendAp')).click();page.wait_for_function('!fsdSettingsBusy');assert page.evaluate('demoFsd.suspendDuringAp')
 page.evaluate('demoFsd.apBlocked=true;fetchFsdSettings()');page.wait_for_function("document.getElementById('fsdSettingsStatus').textContent.includes('Suspended')")
 page.evaluate('demoFsd.apBlocked=false;fetchFsdSettings()');page.wait_for_function("document.getElementById('fsdSettingsStatus').textContent==='Echo enabled'")
 for width in [360,430,1280]:
  page.set_viewport_size(dict(width=width,height=1000));assert page.locator('#panelFsd').evaluate('e=>e.scrollWidth<=e.clientWidth')
 assert not errors,errors
 print('PASS: browser controls, stock readback, single bit46 value, master, mobile layout');b.close()
