from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
root=Path(__file__).resolve().parent
p=root/'runtime-summary.json'
s=json.loads(p.read_text(encoding='utf-8'))
s['virtual_udp_exchanges']=s.pop('virtual_udp_datagrams')
s['ui_action_timestamp_note']='UI action log timestamps were recorded after the clicks; native file API timestamps are authoritative for writes.'
p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
archive=root/'Spitfire_XP_Runtime_Evidence.zip'
with ZipFile(archive) as z:data={n:z.read(n) for n in z.namelist()}
data['runtime-summary.json']=p.read_bytes()
data['cleanup-host.txt']=(root/'cleanup-host.txt').read_bytes()
temporary=archive.with_suffix('.tmp')
with ZipFile(temporary,'w',ZIP_DEFLATED,compresslevel=9) as z:
 for name,content in data.items():z.writestr(name,content)
temporary.replace(archive)
print('Evidence labels corrected and host cleanup record included')
