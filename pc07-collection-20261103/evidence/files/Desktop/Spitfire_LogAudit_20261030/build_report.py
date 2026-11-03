from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import json,hashlib,zipfile
root=Path(__file__).resolve().parent
received=root/'received'
trace=received/'trace-final.jsonl'
events=[json.loads(x) for x in trace.read_text(encoding='utf-8-sig').splitlines() if x]
finished=[x for x in events if x.get('event')=='trace_finished']
assert finished, 'Original process exit not yet captured'
assert finished[-1]['all_hooks_installed']
comparison=[json.loads(x) for x in (received/'trace-comm-after.jsonl').read_text().splitlines() if x]
assert not any(x.get('event')=='ERROR' for x in comparison)
errors=[x for x in events if x.get('event')=='ERROR']
assert all(x.get('reason')=='SuspendThread failed' for x in errors)
first_error_index=next((i for i,x in enumerate(events) if x.get('event')=='ERROR'),len(events))
first_error_previous=events[first_error_index-1] if errors else None
assert not errors or first_error_previous.get('utc','') >= '2026-10-30T12:31:09'
writes=[x for x in events if x.get('event')=='file_api_enter' and x.get('api')=='NtWriteFile']
returns={x['id']:x for x in events if x.get('event')=='file_api_return' and x.get('api')=='NtWriteFile'}
groups=defaultdict(list)
for entry in writes:groups[entry.get('path','')].append(entry)
paths=[]
for path,items in groups.items():
 category='named_pipe_ipc' if 'PIPE' in path.upper() or 'NAMEDPIPE' in path.upper() else 'disk_file'
 paths.append({'path':path,'category':category,'calls':len(items),'requested_bytes':sum(x.get('requested_bytes',0) for x in items),'successful_calls':sum(returns.get(x['id'],{}).get('status')=='0x00000000' for x in items),'first_utc':items[0]['utc'],'last_utc':items[-1]['utc']})
disk=[p for p in paths if p['category']=='disk_file']
assert len(disk)==1 and disk[0]['path'].lower().endswith('datalog.csv'),disk
csv=(received/'datalog.csv').read_bytes()
rows=csv.decode('ascii').splitlines()
assert len(rows)==67 and all(row=='0.55, 36.78' for row in rows)
assert disk[0]['requested_bytes']==len(csv) and disk[0]['calls']==134
identity=hashlib.sha256((received/'original-SPITFIRE.EXE').read_bytes()).hexdigest()
assert identity=='8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b'
udp=[json.loads(x) for x in (root/'virtual-udp.jsonl').read_text().splitlines() if x]
selftest=[json.loads(x) for x in (received/'selftest.jsonl').read_text().splitlines() if x]
actions=(root/'actions.txt').read_text()
summary={'original_sha256':identity,'environment':(received/'metadata.txt').read_text(encoding='utf-8-sig'),'method':'Original XP process under native file API debugger; captured actual UDP queries/replies against VMware host-only virtual responder','original_pid':finished[-1]['pid'],'trace_started_utc':events[0]['utc'],'trace_finished':finished[-1],'event_count':len(events),'file_writes':paths,'csv':{'path':'C:\\Program Files\\Spectra-Physics\\Spitfire\\datalog.csv','bytes':len(csv),'rows':len(rows),'unique_lines':sorted(set(rows))},'virtual_udp_datagrams':len(udp),'comparison_errors':0,'shutdown_tracer_error_count':len(errors),'first_shutdown_error_preceding_event':first_error_previous,'selftest_finished':selftest[-1],'ui_actions_utc':actions.splitlines(),'conclusion':'No communication-log disk file written in tested XP run; Show Messages is an in-memory UI display. Only datalog.csv received disk writes when Data Logging was enabled.','limits':['Virtual replies, not physical laser hardware','Only original process native file APIs tracked; child-process and memory-mapped writes not directly traced','At normal exit, the tracer reported SuspendThread failures on terminating threads; shutdown capture is incomplete. The communication/CSV comparison snapshots contain no tracer errors.','The debugger temporarily used process-memory breakpoints; original EXE file hash matched attachment'],'unused_helper':'A read-only memory diagnostic helper was blocked by host antivirus and not used; protection settings were not disabled.'}
(root/'runtime-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
kst=timezone(timedelta(hours=9))
first=datetime.fromisoformat(events[0]['utc'].replace('Z','+00:00')).astimezone(kst)
last=datetime.fromisoformat(finished[-1]['utc'].replace('Z','+00:00')).astimezone(kst)
text="XP \uc6d0\ubcf8 Spitfire \ud1b5\uc2e0 \ub85c\uadf8 \uc2e4\ud589 \ud655\uc778\n\nVMware\uc758 Windows XP Professional SP3\uc5d0\uc11c \ucca8\ubd80 \uc6d0\ubcf8 EXE\ub97c \uc9c1\uc811 \uc2e4\ud589\ud588\uc2b5\ub2c8\ub2e4.\nShow Messages\ub97c \ucf1c\uace0 UDP \uc1a1\uc218\uc2e0 \ud654\uba74\uc774 \uac31\uc2e0\ub418\ub294 \ub3d9\uc548 \ud1b5\uc2e0 \ub85c\uadf8 \ud30c\uc77c \uc4f0\uae30\ub294 \uad00\ucc30\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.\nData Logging\uc744 \ucf1c\uc790 datalog.csv\uc5d0 \uce21\uc815\uac12 0.55, 36.78\uc774 67\uc904, \ucd1d871\ubc14\uc774\ud2b8 \uae30\ub85d\ub410\uc2b5\ub2c8\ub2e4. \uc131\uacf5\ud55c NtWriteFile134\ud68c\uc640 \ud30c\uc77c \ub0b4\uc6a9\uc774 \uc77c\uce58\ud588\uc2b5\ub2c8\ub2e4.\n\ub2e4\uc2dc Off\ub85c \ubc14\uafbc \ud6c4\uc5d0\ub3c4 \ud1b5\uc2e0\uc740 \uacc4\uc18d\ub410\uc9c0\ub9cc CSV \uae30\ub85d\uc740 \uba48\ucdc4\uc2b5\ub2c8\ub2e4. \ub514\uc2a4\ud06c \uc4f0\uae30 \uacbd\ub85c\ub294 \uc774 CSV \ud558\ub098\uc600\uc73c\uba70 lsarpc \uc4f0\uae30\ub294 Windows named-pipe IPC\uc600\uc2b5\ub2c8\ub2e4.\n\uc6d0\ubcf8\uc740 X \ub2eb\uae30 \ubc84\ud2bc\uc73c\ub85c \uc815\uc0c1 \uc885\ub8cc\ud588\uace0 \uc885\ub8cc \ucf54\ub4dc0\uc744 \ud655\uc778\ud588\uc2b5\ub2c8\ub2e4.\n\n\ud55c\uacc4: \uc2e4\uc7a5\ube44 \ub300\uc2e0 Host-only \uac00\uc0c1 \uc751\ub2f5\uc744 \uc0ac\uc6a9\ud588\uc2b5\ub2c8\ub2e4. \uc6d0\ubcf8 \ud504\ub85c\uc138\uc2a4\uc758 \uc77c\ubc18 \ud30c\uc77c API\ub97c \ucd94\uc801\ud588\uc73c\uba70 \uc790\uc2dd \ud504\ub85c\uc138\uc2a4\uc640 \uba54\ubaa8\ub9ac \ub9e4\ud551 \uc4f0\uae30\ub294 \uc9c1\uc811 \ucd94\uc801\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4. \ud1b5\uc2e0/CSV \ube44\uad50 \uad6c\uac04\uc758 \ucd94\uc801 \uc624\ub958\ub2940\uac1c\uc600\uc73c\ub098, \uc885\ub8cc \ub9c8\uc9c0\ub9c9 \ub2e8\uacc4\uc5d0\ub294 \uc885\ub8cc \uc2a4\ub808\ub4dc\uc758 \uc77c\uc2dc \uc815\uc9c0 \uc2e4\ud328\uac00 \ubc1c\uc0dd\ud574 \uc885\ub8cc \uad6c\uac04 \ucd94\uc801\uc758 \uc644\uc804\uc131\uc740 \ubcf4\uc7a5\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.\n\ubbf8\uc0ac\uc6a9 \uba54\ubaa8\ub9ac \uc9c4\ub2e8 \ubcf4\uc870 \ub3c4\uad6c\ub294 \ud638\uc2a4\ud2b8 \ubc31\uc2e0\uc774 \ucc28\ub2e8\ud558\uc5ec \uc0ac\uc6a9\ud558\uc9c0 \uc54a\uc558\uace0 \ubc31\uc2e0 \ubcf4\ud638 \uc124\uc815\uc740 \ubcc0\uacbd\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.\n\ud14c\uc2a4\ud2b8 CSV\ub294 C:\\SPF_AUDIT_20261030\\datalog-test.csv\ub85c \ubcf4\uc874\ud588\uc2b5\ub2c8\ub2e4. \uc2dc\ud5d8\uc6a9 C:\\config.sp\ub294 \uc6d0\ub798 \uc5c6\ub358 \uc0c1\ud0dc\ub85c \ubcf5\uc6d0\ud588\uc2b5\ub2c8\ub2e4.\n"
text+='\nKST runtime: '+first.isoformat()+' ~ '+last.isoformat()+'\n'
text+='EXE SHA-256: '+identity+'\n'
(root/'RESULT.ko.txt').write_text(text,encoding='utf-8')
files=[(trace,'spitfire-final.jsonl'),(received/'selftest.jsonl','selftest.jsonl'),(received/'metadata.txt','metadata.txt'),(received/'datalog.csv','datalog.csv'),(root/'actions.txt','actions.txt'),(root/'virtual-udp.jsonl','virtual-udp.jsonl'),(root/'runtime-summary.json','runtime-summary.json'),(root/'RESULT.ko.txt','RESULT.ko.txt'),(root/'comm-before-csv.jsonl','comm-before-csv.jsonl'),(received/'trace-comm-after.jsonl','trace-comm-after.jsonl')]
for name in ['windows-before.txt','windows-after.txt','ui-finish-exit-menu.txt','cleanup-guest.json']:
 p=received/name
 if p.exists():files.append((p,name))
with zipfile.ZipFile(root/'Spitfire_XP_Runtime_Evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for path,name in files:z.write(path,name)
print(json.dumps({'original_exit':finished[-1],'disk_write_files':disk,'csv_rows':len(rows),'csv_bytes':len(csv),'udp_datagrams':len(udp),'evidence_zip_bytes':(root/'Spitfire_XP_Runtime_Evidence.zip').stat().st_size},ensure_ascii=False))
