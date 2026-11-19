from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 page=browser.new_page(viewport=dict(width=1280,height=1000));errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 url=(root/'dashboard_demo.html').as_uri()
 page.goto(url);page.wait_for_function('universalBootReady')
 assert not page.locator('body').evaluate("e=>e.classList.contains('setup-active')")
 page.evaluate("openPanel('panelFsd');fetchFsdSettings()")
 page.wait_for_function('fsdSettingsSaved!==null')
 assert page.locator('#fsdBus,#gpsEnabled,#gpsLatitude,#gpsLongitude').count()==0
 def toggle(id):
  page.locator('label.toggle').filter(has=page.locator('#'+id)).click()
  page.wait_for_function('!fsdSettingsBusy')
 toggle('fsdMaster');toggle('fsdField1');toggle('fsdSuspendAp')
 assert page.evaluate('fsdSettingsSaved.enabled&&fsdSettingsSaved.suspendDuringAp')
 assert page.locator('#fsdBus,#gpsEnabled,#gpsLatitude,#gpsLongitude').count()==0
 page.evaluate("__t2PreviewSetAp('AUTOSTEER');fetchFsdSettings()")
 page.wait_for_function("document.getElementById('fsdSettingsStatus').textContent.includes('Suspended')")
 page.evaluate("__t2PreviewSetAp('OFF');fetchFsdSettings()")
 page.wait_for_function("document.getElementById('fsdSettingsStatus').textContent==='Echo enabled'")
 page.reload();page.wait_for_function('universalBootReady');page.evaluate("openPanel('panelFsd');fetchFsdSettings()")
 page.wait_for_function('fsdSettingsSaved?.enabled===true')
 page.evaluate("showPage('settings')")
 assert page.locator('#actionsMenuToggle,#actionsNavBtn').count()==0
 page.locator('[data-panel=panelBatteryPreheat]').click();assert page.locator('#panelBatteryPreheat').is_visible()
 page.locator('#panelBatteryPreheat .backbtn').click()
 for model in [1,2,3,4,5]:
  page.goto(url+'?previewModel='+str(model));page.wait_for_function('universalBootReady')
  assert page.evaluate('__p4ProfileId')==model
 for width in [360,430,1280]:
  page.set_viewport_size(dict(width=width,height=1000))
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.evaluate("openPanel('panelFsd')");assert page.locator('#panelFsd').evaluate('e=>e.scrollWidth<=e.clientWidth')
 assert not errors,errors
 browser.close()
print('PASS: simulated boot, five models, FSD save/AP suspension/resume, Actions and responsive controls')
