from pathlib import Path
import json,hashlib,importlib.util,datetime,struct
r=Path(__file__).parent
spec=importlib.util.spec_from_file_location('fixture',r/'harness_server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
values=json.loads((r/'fixture-values-original.json').read_text(encoding='utf-8-sig'))
seq,stats=m.replay_log(r/'udp-original.jsonl',values)
assert stats==json.loads((r/'fixture-state.json').read_text(encoding='utf-8-sig'))
records=[json.loads(x) for x in (r/'udp-original.jsonl').read_text().splitlines() if x.strip()]
writes=[];rejected=[]
for row in records:
 if row.get('rejected'):rejected.append({'seq':row['seq'],'source':row['source'],'reason':row['rejected'],'request_hex':row['request_hex']})
 for event in row['messages']:
  if event.get('tag',0)>=2000:writes.append({'seq':row['seq'],'epoch':row['received_epoch'],'utc':datetime.datetime.fromtimestamp(row['received_epoch'],datetime.timezone.utc).isoformat(),'source':row['source'],**event})
assert stats['applied_optout_on']==0 and stats['optout']=='1'
assert all(x['tag']==2047 and x['command']=='EMP:LBOBREAK 1' and x['action'].startswith('rejected no state change') for x in writes)
ranges=[]
for s in sorted((r/'evidence'/'sessions').iterdir()):
 ts=[]
 for pc in (s/'capture').glob('*.pcap'):
  b=pc.read_bytes();assert b[:4]==bytes.fromhex('d4c3b2a1');off=24
  while off<len(b):
   sec,usec,inc,orig=struct.unpack_from('<IIII',b,off);off+=16;assert inc<=orig and off+inc<=len(b);off+=inc;ts.append(sec+usec/1e6)
  assert off==len(b)
 if ts:ranges.append({'session':s.name,'first_epoch':min(ts),'last_epoch':max(ts),'frames':len(ts)})
for x in writes:x['inside_any_product_capture']=any(z['first_epoch']<=x['epoch']<=z['last_epoch'] for z in ranges)
assert not any(x['inside_any_product_capture'] for x in writes)
out={'responses_are_synthetic':True,'physical_controller':False,'applied_state_changes':0,'fixture_policy':m.POLICY,'last_sequence':seq,'record_count':len(records),'replayed_state':stats,'startup_writes_rejected':writes,'rejected_envelopes':rejected,'capture_ranges':ranges,'ledger_sha256':hashlib.sha256((r/'udp-original.jsonl').read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((r/'harness_server.py').read_bytes()).hexdigest()}
(r/'fixture-ledger-audit.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'record_count':len(records),'rejected_startup_writes':len(writes),'applied_state_changes':0,'rejected_envelopes':len(rejected),'capture_ranges':len(ranges)}))
