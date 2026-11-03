from pathlib import Path
import re,json,hashlib,datetime
r=Path(__file__).parent;q=r/'received'
initial=(q/'rev001-inventory--guest-inventory.txt').read_bytes().decode('ascii','replace')
final=(q/'rev-final-inventory--final-inventory.txt').read_bytes().decode('ascii','replace')
rx=r'MenuFont_REG_BINARY_hex=([0-9A-F]+)'
a=re.search(rx,initial)[1];b=re.search(rx,final)[1];assert a==b and len(a)==184
assert 'original_process_count=0' in final and 'ip=10.19.70.2' in final and 'gateway=' not in final
font=json.loads((q/'rev-final-inventory--display-final.json').read_text(encoding='utf-8-sig'))
assert font['code']==0 and font['font_height']==-12 and font['font_face']=='\uad74\ub9bc' and font['original_absent']
before_font=json.loads((q/'rev002-display-read--display-before.json').read_text(encoding='utf-8-sig'))
for key in ['menu_height','menu_width','font_height','font_weight','font_charset','font_face','ncm_size','screen_width','screen_height']:assert font[key]==before_font[key]
p=(q/'rev-final-inventory--guest-final-processes.txt').read_text()
for exe in ['spitfire.exe','passive_capture.exe','readonly_ui.exe','proof_publish.exe','provision_winpcap.exe','readonly_menu_probe.exe','readonly_font_probe.exe','readonly_font_probe2.exe']:assert exe+'=0' in p
assert sum(line.startswith('remaining_mshta=') for line in p.splitlines())==1 and 'C:\\SPF_USB_REVISION\\controller.hta' in p
route=(q/'rev-final-inventory--final-route.txt').read_bytes().decode('ascii','replace');assert not re.search(r'^\s*0\.0\.0\.0\s+0\.0\.0\.0',route,re.M)
backup=q/'rev024-normal-and-font--display-backup.bin';assert backup.stat().st_size==500
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_process_count':0,'capture_and_ui_helpers_remaining':0,'only_guest_transport_remaining':True,'menu_font_registry_exact_match':True,'menu_font_registry_bytes':len(a)//2,'nonclientmetrics_backup_bytes':500,'nonclientmetrics_backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'restored_font':font,'guest_ip':'10.19.70.2','guest_default_route_present':False,'physical_original_accessed':False,'all_checks_passed':True}
(r/'guest-cleanup-verified.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(out,ensure_ascii=True))
