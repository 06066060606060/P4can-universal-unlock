from pathlib import Path
import re, subprocess, tempfile, gzip, hashlib, json
from html.parser import HTMLParser
root=Path(__file__).resolve().parents[1]
html=(root/'dashboard_source.html').read_text(encoding='utf8')
class DOM(HTMLParser):
 def __init__(self): super().__init__(); self.ids=[]
 def handle_starttag(self,tag,attrs):
  for key,value in attrs:
   if key=='id':self.ids.append(value)
d=DOM();d.feed(html)
assert len(d.ids)==len(set(d.ids)), 'Duplicate DOM IDs'
for n in range(1,4):
 for key in [f'homeCan{n}Name',f'can{n}Badge',f'can{n}Traffic',f'can{n}Age']:assert key in d.ids,key
assert 'data-topology=' not in html
assert "pendingTopology=pendingProfile===1?1:2" in html
assert "canABadge" not in html and "canBBadge" not in html
scripts=re.findall(r'<script[^>]*>(.*?)</script>',html,re.S)
with tempfile.TemporaryDirectory() as temp:
 for n,script in enumerate(scripts):
  path=Path(temp)/f'script{n}.js';path.write_text(script,encoding='utf8')
  subprocess.run(['node','--check',str(path)],check=True)
embedded=(root/'index_html.h').read_text(encoding='utf8')
assert gzip.decompress(bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',embedded)))==(root/'dashboard_source.html').read_bytes()
for p in list(root.glob('*.h'))+list(root.glob('*.ino'))+list(root.glob('*.md')):
 text=p.read_text(encoding='utf-8-sig')
 assert not re.search(r'\bMCP2515\b|\bSPI\b',text,re.I),p.name
 assert not re.search(r't-?2-?can',text,re.I),p.name
 assert not re.search(r'\btwai_(?:transmit|receive|driver_install|driver_uninstall|start|stop)\(',text),p.name
print(f'PASS: {len(scripts)} JavaScript scripts parsed, physical DOM IDs, fixed profile selection, gzip/source identity, native API and removed transport scan')

# Removed menus and APIs must not survive in the shipped dashboard.
for retired in ('panelLabR79','panelLabSummonHeartbeat','panelLabAutoLaneChange','panelLabDriverWindow','panelLabDriverMonitor','bannedCarToggle','tlsscRestoreToggle'):
 assert retired not in d.ids, retired
assert 'data-panel="panelR79"' in html
# Settings retain their original navigation and inline root controls.
settings=re.search(r'<main\b[^>]*data-page="settings"[^>]*>(.*?)</main>',html,re.S).group(1)
assert not re.search(r'class="[^"]*\b(?:settingsCategory|categoryReveal|settingsItem)\b',settings), 'Settings rows must retain the original visible layout'
expected_features=['panelNag','panelVisionControl','panelBlink','panelSummon','panelR79','panelCountry','panelTlssc','panelAutoLaneChange','panelUlc','panelPedalMap','panelContinuousAp','panelApDriveProfile','panelSmartShift','panelBatteryPreheat']
expected_system=['panelAbout','panelWireless','panelCanGpio','panelDiag','panelResearchCapture','panelOta','panelServiceMode']
assert re.findall(r'data-panel="([^"]+)"',settings)==[x for x in expected_features if x not in ('panelR79','panelSmartShift','panelCountry','panelUlc','panelContinuousAp')]+['panelR79','panelFsd','panelSmartShift','panelCountry','panelUlc','panelContinuousAp']+expected_system, '3.29.1 Features/System detail row order; ISA, monitoring, menu and choices remain inline'
assert re.findall(r'class="sectiontitle">([^<]+)</div>',settings)==['Features','Experimental','System'], 'Original static section headings'
assert '<details' not in settings and '<button type="button" class="categorySummary' not in settings
for action in ('rebootRow','resetSettingsBtn','resetNvsKeepBleBtn','factoryResetBtn'):
 assert re.search(r'<div\b(?=[^>]*class="listrow clickable")(?=[^>]*id="'+action+r'")[^>]*>',settings), action+' remains a direct action row'
diag=html.split('<section class="panel" id="panelDiag">',1)[1].split('<section class="panel"',1)[0]
diag_sections=['system','memory','wireless','ble','can1','can2','can3','recovery']
assert re.findall(r'data-diag-category="([^"]+)"',diag)==diag_sections, 'Diagnostics must expand eight inline categories in the same screen'
assert 'data-panel=' not in diag, 'Diagnostics categories must not navigate to detail/subview panels'
assert '<details' not in diag
assert re.findall(r'data-diag-section="([^"]+)"',diag)==diag_sections, 'Each category has one inline diagnostic region'
assert 'data-diag-view=' not in html, 'CAN Status/Traffic/Errors/Recovery must share the selected bus region'
for key in diag_sections:
 suffix=key.capitalize()
 assert re.search(r'<button\b(?=[^>]*id="diagToggle'+suffix+r'")(?=[^>]*data-diag-toggle="'+key+r'")(?=[^>]*aria-controls="diagBody'+suffix+r'")(?=[^>]*aria-expanded="false")[^>]*>',diag), key+' must begin collapsed with a native accessible toggle'
 assert re.search(r'<div\b(?=[^>]*id="diagBody'+suffix+r'")(?=[^>]*data-diag-section="'+key+r'")(?=[^>]*role="region")(?=[^>]*aria-labelledby="diagToggle'+suffix+r'")(?=[^>]*\binert(?:\s|=|>))[^>]*>',diag),key+' closed content must be labelled and inert'
for old in ('panelDiagSystem','panelDiagMemory','panelDiagWireless','panelDiagBle','panelDiagRecovery'):
 assert old not in d.ids,old+' must be inline content, not another panel'
for n in range(1,4):
 for suffix in ('','Status','Traffic','Errors','Recovery'):
  assert f'panelDiagCan{n}{suffix}' not in d.ids,'CAN subview navigation must be removed'
 for suffix in ('State','Pins','Mode','Init','TrafficState','Rx','Polls','Queues','Tx','ErrorsState','Errors','DriverErrors','Loss','RecoveryState','BusOff','Recovery'):
  assert f'diagCan{n}{suffix}' in d.ids,'Selected CAN accordion must preserve '+suffix+' information'
for action in ('btnResetStats','btnReinit'):
 assert html.count('id="'+action+'"')==1,action+' must have one persistent Diagnostics action'
 assert re.search(r'id="diagActionsCard"[\s\S]*id="'+action+'"',diag),action+' must remain outside accordion content'
for download in ('diagSystemStatsJson','diagBleCsvSystem','diagBleCsv'):
 assert download in d.ids,download+' must remain available'
assert 'href="/api/system/boot-capture.csv"' in diag
# Frozen BUS OFF evidence uses the existing managed-download path so exports
# own the busy indicator and suspend dashboard polling until they finish.
recovery_downloads=diag.split('id="diagBodyRecovery"',1)[1].split('id="diagActionsCard"',1)[0]
recovery_grid=re.search(r'<div class="diagButtons">(.*?)</div>',recovery_downloads,re.S).group(1)
for route in ('A','B'):
 button=f'diagCan{route}TxCsv'
 assert button in d.ids,button+' must expose the existing TX trace export'
 assert re.search(r'<button class="btn linkbtn" id="'+button+r'">Route '+route+r' TX CSV</button>',recovery_grid),button+' must reuse Logs & Recovery download controls with an honest unloaded-profile label'
 assert re.search(r"\$\('"+button+r"'\)\.onclick=\(\)=>downloadFile\('/api/system/can"+route.lower()+r"-tx\.csv','P4-CAN_CAN"+route+r"_TX_TRACE\.csv','[^']+'\)",html),button+' must use the existing managed download helper and unchanged endpoint/filename'
assert '<button class="btn linkbtn" id="diagCanErrorsJson">CAN Error JSON</button>' in recovery_grid, 'CAN Error JSON must reuse the existing recovery controls'
assert "$('diagCanErrorsJson').onclick=()=>downloadFile('/api/system/can-errors.json','P4-CAN_CAN_ERRORS.json','Preparing CAN Error JSON')" in html, 'CAN Error JSON must pause polling through the managed helper'
assert 'function setCategoryOpen' not in html and 'setupSettingsAccordions' not in html
assert 'function setupSettingsPanels' in html and 'setupSettingsPanels();' in html
for retired in ('activeProfileCan','activeProfileTurn','activeProfileCaps'):
 assert retired not in d.ids,retired
for key in ('preheatToggle','preheatTargetC','preheatRaw','thermalFold','thPipes','thFlowPtLine','thFlowBatLine','batteryPreheatSettingsRow'):
 assert key in d.ids,key
assert 'id="homeCanCard"' in html and 'id="homeCanDetails"' in html
assert not re.search('[\uac00-\ud7a3]',html),'Dashboard labels must remain English'
for region in ('homeCanDetails','panelCanGpio','panelDiag'):
 area=html.split('id="'+region+'"',1)[1].split('</details>' if region=='homeCanDetails' else '<section class="panel"',1)[0]
 for n in range(1,4):assert 'data-can-role="'+str(n)+'"' in area,region+' must label every physical bus for the active profile'
setup=html.split('id="topologyStep"',1)[1].split('id="highlandTurnStep"',1)[0]
assert not re.search(r'TX\d|RX\d',setup),'Setup must not present fixed defaults as current wiring'
assert 'saved CAN GPIO mapping or firmware defaults' in setup and 'Check active pins' in setup
assert 'r79TimingWarnings' in d.ids
# Canonical 3.29.1 Settings DOM. Retired profile chips and the Banned Car /
# TLSSC Restore danger zone stay removed. The sole new row, Actions Menu,
# must reuse the original LAB Menu inline toggle structure. This signature is
# self-contained so source-ZIP test runs do not require another package.
class SettingsDOM(HTMLParser):
 def __init__(self): super().__init__(); self.root={'tag':'root','attrs':{},'children':[]}; self.stack=[self.root]
 def handle_starttag(self,tag,attrs):
  node={'tag':tag,'attrs':dict(attrs),'children':[]}; self.stack[-1]['children'].append(node)
  if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'): self.stack.append(node)
 def handle_startendtag(self,tag,attrs): self.handle_starttag(tag,attrs)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i]['tag']==tag: self.stack=self.stack[:i]; break
 def handle_data(self,text):
  text=' '.join(text.split())
  if text:self.stack[-1]['children'].append(text)
def descendants(node):
 yield node
 for child in node['children']:
  if isinstance(child,dict):yield from descendants(child)
def original_settings_signature(markup):
 parser=SettingsDOM(); parser.feed(markup)
 def canonical(node):
  attrs=node['attrs']; classes=attrs.get('class','').split()
  if 'profileChips' in classes or attrs.get('id') in ('bannedDangerHead','bannedDangerZone'):return None
  if 'listrow' in classes and any(n['attrs'].get('id') in ('actionsMenuToggle','labMenuToggle') for n in descendants(node)):return None
  if attrs.get('id')=='serviceModeSettingsCard':return None
  if attrs.get('id')=='canGpioSettingsRow' or attrs.get('data-panel') in ('panelFsd','panelServiceMode','panelAutoLaneChange','panelSmartShift','panelBatteryPreheat','panelResearchCapture'):return None
  children=[]
  for child in node['children']:
   value=canonical(child) if isinstance(child,dict) else child
   if value is not None:children.append(value)
  return [node['tag'],sorted(attrs.items()),children]
 data=json.dumps(canonical(parser.root),ensure_ascii=False,separators=(',',':')).encode()
 return hashlib.sha256(data).hexdigest(),parser
expected_signature='f00fc0b62fd076f00cad25a327fe25150ed3e1982d44115abb9d8d27f6102ceb'
reference=root/'tests'/'fixtures'/'settings_v3291_reference.html'
if reference.exists():
 reference_bytes=reference.read_bytes()
 assert hashlib.sha256(reference_bytes).hexdigest()=='1458fd4892b313e953032f6e6a3d611fb9af361798ef3eb4d65a678a966f584a','3.29.1 reference provenance'
 reference_settings=re.search(r'<main\b[^>]*data-page="settings"[^>]*>(.*?)</main>',reference_bytes.decode(),re.S).group(0)
 expected_signature=original_settings_signature(reference_settings)[0]
assert 'Configure R79 timing and bit policy.' in settings
normalized_settings=settings.replace('data-panel="panelSummon" hidden style="display:none"','data-panel="panelSummon"').replace('<div class="listrow clickable" data-panel="panelAbout"><div><div class="listkey">About</div><div class="listdesc">Firmware and project links</div></div><span class="value" id="sysFw" hidden></span><span class="chev">›</span></div>','<div class="listrow"><div><div class="listkey">Firmware</div><div class="listdesc">Current application</div></div><span class="value" id="sysFw">—</span></div>').replace('Configure R79 timing and bit policy.','Choose the R79 override mode and timing.')
normalized_settings=re.sub(r'<div class="listrow clickable" data-panel="panelAbout">.*?</span></div></div>','<div class="listrow"><div><div class="listkey">Firmware</div><div class="listdesc">Current application</div></div><span class="value" id="sysFw">—</span></div>',normalized_settings,flags=re.S)
# Normalize the approved new grouping only for comparison with the historical baseline.
exp=re.search(r'<div class="sectionhead"><div class="sectiontitle">Experimental</div></div>\s*<section class="card" id="experimentalSettingsCard">(.*?)</section>',normalized_settings,re.S)
assert exp is not None
exp_rows={panel:next(l for l in exp.group(1).splitlines(True) if 'data-panel="'+panel+'"' in l) for panel in ['panelR79','panelFsd','panelSmartShift','panelCountry','panelUlc','panelContinuousAp']}
normalized_settings=normalized_settings[:exp.start()]+normalized_settings[exp.end():]
for panel,before in [('panelR79','panelTlssc'),('panelCountry','panelTlssc'),('panelFsd','panelTlssc'),('panelUlc','panelPedalMap'),('panelContinuousAp','panelApDriveProfile'),('panelSmartShift','panelBatteryPreheat')]:
 anchor=next(l for l in normalized_settings.splitlines(True) if 'data-panel="'+before+'"' in l)
 normalized_settings=normalized_settings.replace(anchor,exp_rows[panel]+anchor,1)
normalized_settings=normalized_settings.replace('Auto lane change for standard AP','Experimental auto lane change for standard AP')
normalized_settings=normalized_settings.replace('id="setAlcDesc">Off-Highway lane change','id="setAlcDesc">Auto Blinker is inactive while Confirm-Free Lane Change is on.')
normalized_settings=normalized_settings.replace('Trigger turn signal automatically in NOA','Signal automatically for NOA lane changes.')
actual_signature,settings_dom=original_settings_signature('<main class="page" data-page="settings">'+normalized_settings+'</main>')
assert actual_signature==expected_signature,'Settings must restore original 3.29.1 DOM, labels, descriptions, inline controls and reset styles (except retired sections, Actions Menu and the approved CAN GPIO row)'
for retired in ('panelIsaSuppression','panelDriverMonitoring','panelAppearance','panelRefresh','panelMenu','panelActionsMenu'):
 assert retired not in d.ids,retired+' must be an inline Settings control, not a new detail page'
nodes=list(descendants(settings_dom.root))
assert 'actionsMenuToggle' not in d.ids and 'actionsNavBtn' not in d.ids
assert settings.index('id="serviceModeSettingsCard"')>settings.index('id="factoryResetBtn"')
assert 'id="panelBatteryPreheat"' in html
for control in ('isaSuppressionToggle','driverMonitoringToggle','s3xyFeatureToggle','dashboardThemeMode','dashboardPollRate','sysFw'):
 assert any(n['attrs'].get('id')==control for n in nodes),control+' must be in Settings root'
print('PASS: proven 3.29.1 Settings DOM restoration with explicit removed-section/Actions exceptions; retained details, single CAN card and English UI')

# Existing Settings details keep their original Settings header + hero hierarchy.
# Their feature bodies retain current AP control, capture and P4 diagnostics.
original_detail_headers={'panelNag': '9b537f93ad8a3c210b901734a1e8138921a8ac092f1f50564c364fc01cf5aa7f', 'panelNagModeH': '9b1ef21f1e2d9eb7964fde6d2c9940b61a3920c36341e69afc5c56c833e28f36', 'panelVisionControl': '89b32c4328f9d5ba6d2f98d51c33c9d5380e3ac777c33d5acb4151f8ac1c3d7a', 'panelBlink': '0cb00c193c259140aed279bdf079900a72d034c4dc3976588b68bc09691a403d', 'panelSummon': 'd74e0cca26dc1a132e85f2c57e99f7c5fb6d8ffe8c043b015a23bc6053118f82', 'panelR79': 'ffb0915b114be7291d4c16c07b667ec7f0c7e4da7b84360f62c594f5faff2b2b', 'panelCountry': '8ffb50d36eabe2a8efc41c5e66da1bf06daf0fd3925a13fdc10558b064b2d3d0', 'panelTlssc': '87e22d30494de7ccef8ff8dfe11519aee4c3d14e226068cf9a2f7a2390d3af55', 'panelUlc': '398041803b4125b15a7965468fa58a508ed37d2f16e9acfe7bfef02ab22341ab', 'panelPedalMap': '202a41117641751bb6c8dcc8ddfc861a8ff77b51c73c88c20e23955862e77965', 'panelContinuousAp': '61e17d0795a992df1922f2a499e6a8a360edb712490a04ae3e0c5ff06c291a8e', 'panelApDriveProfile': '8c05e455de9c70525b8e5ecc7ae2fd50aa0b85a1f0addbe5c3197f4c0e22cbc7', 'panelWireless': '543a1b39db74ef57a22dbf57e6f3a9be13045509cac33bb5af2c336bc801e7ee', 'panelDiag': '41e6032c1a01a5d8ccc1594829cfcf7e641d38d5766875358c8433783989c53e', 'panelOta': '799b2d2219a7f77d0ebe095d8425a8a3d288d85779a003dc6aee3f2c87fc4a3c'}
full_dom=SettingsDOM();full_dom.feed(html)
def node_structure(node):
 return [node['tag'],sorted(node['attrs'].items()),[node_structure(c) if isinstance(c,dict) else c for c in node['children']]]
for panel_id,expected in original_detail_headers.items():
 panel=next(n for n in descendants(full_dom.root) if n['attrs'].get('id')==panel_id)
 panelin=next(n for n in panel['children'] if isinstance(n,dict) and 'panelin' in n['attrs'].get('class','').split())
 heading=[node_structure(n) for n in panelin['children'] if isinstance(n,dict) and set(n['attrs'].get('class','').split())&{'paneltop','panelHero','panelSub'}][:3]
 # The approved R79-only text change removes its retired transport choice.
 # Normalize exactly that subtitle before comparing the original structure hash.
 if panel_id=='panelR79':
  assert heading[2][2]==['Configure R79 timing, behavior and bit policy.']
  heading[2][2]=['Mode 1 / 2 · manual D/R suppression.']
 digest=hashlib.sha256(json.dumps(heading,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 assert digest==expected,panel_id+' must restore its original paneltop/panelHero/panelSub structure and labels'
print('PASS: 15 original Settings detail header/hero structures retained with current feature bodies')

# Fields and side effects belong to their inline region, not a hidden old panel.
all_nodes=list(descendants(full_dom.root))
for n in range(1,4):
 region=next(node for node in all_nodes if node['attrs'].get('id')==f'diagBodyCan{n}')
 ids={node['attrs'].get('id') for node in descendants(region)}
 for suffix in ('State','Pins','Mode','Init','TrafficState','Rx','Polls','Queues','Tx','ErrorsState','Errors','DriverErrors','Loss','RecoveryState','BusOff','Recovery'):
  assert f'diagCan{n}{suffix}' in ids,f'CAN {n} must show every metric inside its one accordion'
 labels=[node['children'] for node in descendants(region) if node['attrs'].get('class')=='detailSectionLabel']
 assert labels==[['STATUS'],['TRAFFIC'],['ERRORS'],['RECOVERY']],f'CAN {n} retains four static information groups'
actions=next(node for node in all_nodes if node['attrs'].get('id')=='diagActionsCard')
assert {node['attrs'].get('id') for node in descendants(actions)} >= {'btnResetStats','btnReinit'}
for node in all_nodes:
 if node['attrs'].get('data-diag-section'):
  ids={child['attrs'].get('id') for child in descendants(node)}
  assert not ids&{'btnResetStats','btnReinit'},'Single actions must remain outside expandable content'
print('PASS: eight accessible inline Diagnostics regions, complete CAN groups, persistent single actions and original downloads')
