from pathlib import Path
import json,csv,re,statistics,datetime,ast,hashlib,sys,collections
root=Path.cwd();w=root/'tmp/live_review_20261027';p=root/'output/Spitfire_Python_Control_1.3.1/Spitfire_Python_Control'
sys.path.insert(0,str(p/'src'))
from spitfire_control.state import DeviceState
from spitfire_control.protocol import Reply
from spitfire_control.profiles import EXTERNAL_REQUIRED_READS
catalog={}
for node in ast.parse((p/'src/spitfire_control/commands.py').read_text(encoding='utf-8')).body:
 targets=node.targets if isinstance(node,ast.Assign) else [node.target] if isinstance(node,ast.AnnAssign) else []
 if any(isinstance(t,ast.Name) and t.id=='_QUERIES' for t in targets):catalog=ast.literal_eval(node.value)
assert catalog
names=['baseline_1s_01','step_500ms_01','capability_1s_01','step_200ms_01','recovery_1s_01','step_100ms_01','scheduler_unpaced_131','scheduler_paced100ms_131','scheduler_paced200ms_capture_131','scheduler_autopoll_off_capture_131']
def loadl(f):return [json.loads(x) for x in f.read_text(encoding='utf-8').splitlines() if x.strip()]
def utcsec(s):return datetime.datetime.fromisoformat(s).timestamp()
def kst(s):return datetime.datetime.fromisoformat(s).astimezone(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
def stats(v):
 if not v:return None
 a=sorted(v);return {'n':len(a),'min':a[0],'median':statistics.median(a),'p95':a[round((len(a)-1)*.95)],'max':a[-1],'mean':statistics.fmean(a)}
def txdecode(r):
 raw=bytes.fromhex(r['data_hex']).decode('ascii','strict');prefix='Spectra-Physics:CMD_ECLIPSE,';assert raw.startswith(prefix),raw;commands=[]
 for line in raw[len(prefix):].splitlines():
  if not line.strip():continue
  match=re.fullmatch(r'\[(\d+)\](.*)',line);assert match,line
  cid=int(match[1]);command=match[2];commands.append({'id':cid,'command':command,'line':line,'is_known_read_query':cid in catalog and command==catalog[cid]})
 assert commands
 return commands

def rxdecode(r):
 raw=bytes.fromhex(r['data_hex']).decode('ascii','replace');prefix='Spectra-Physics:REPLY_ECLIPSE:'
 if not raw.startswith(prefix):raise ValueError('Unknown reply packet header')
 ans=[]
 for line in raw[len(prefix):].splitlines():
  if not line.strip():continue
  m=re.fullmatch(r'\s*<(\d+)>\s?(.*)',line)
  if not m:raise ValueError('Malformed reply line: '+line)
  ans.append({'id':int(m[1]),'value':m[2].strip(),'raw':line})
 return ans

def tx_proof(records):
 cmds=[c for r in records for c in txdecode(r)]
 return {'datagrams':len(records),'decoded_commands':len(cmds),'multi_command_datagrams':sum(len(txdecode(r))>1 for r in records),'write_commands_by_id_ge_2000':sum(c['id']>=2000 for c in cmds),'non_catalog_query_commands':[c for c in cmds if not c['is_known_read_query']],'all_are_exact_catalog_queries':all(c['is_known_read_query'] for c in cmds),'command_id_counts':dict(collections.Counter(str(c['id']) for c in cmds))}

all_hv=[];stages=[]
for name in names:
 d=w/name;events=loadl(d/'events.jsonl');summary=json.loads((d/'summary.json').read_text(encoding='utf-8'));stage={'name':name,'supplied_summary':summary,'input_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in d.iterdir() if f.is_file()}}
 if not name.startswith('scheduler_'):
  txs=[e for e in events if e['kind']=='TX_DATAGRAM'];rxs=[e for e in events if e['kind']=='RX_DATAGRAM'];exchanges=[e for e in events if e['kind']=='EXCHANGE'];assert len(txs)==len(exchanges)
  pending=None;ordered=[];rx_parse=[]
  for e in events:
   if e['kind']=='TX_DATAGRAM':pending={'tx':e,'rx':[]}
   elif e['kind']=='RX_DATAGRAM':
    try:e['decoded_independent']=rxdecode(e)
    except Exception as exc:rx_parse.append(str(exc));e['decoded_independent']=[]
    for item in e['decoded_independent']:
     if item['id']==1021:all_hv.append({'stage':name,'utc':e['utc'],'value':item['value'],'raw':item['raw'],'source':'raw socket RX datagram'})
    if pending:pending['rx'].append(e)
   elif e['kind']=='EXCHANGE':
    assert pending is not None
    wire=txdecode(pending['tx']);assert len(wire)==1 and wire[0]['id']==e['command_id'] and wire[0]['line']==e['line']
    ordered.append({'exchange':e,**pending});pending=None
  measure=[x for x in ordered if x['exchange']['phase']=='measurement'];old_rejected=[];empty=[];new_rejected=[]
  for x in measure:
   for reply in x['exchange'].get('replies',[]):
    cid=x['exchange']['command_id'];value=reply['value'];s=DeviceState(pump_mode='external');ok=s.apply(Reply(cid,value,reply['raw']))
    if not reply['parser_130_accepts']:old_rejected.append({'id':cid,'raw':reply['raw']})
    if not value:empty.append({'id':cid,'raw':reply['raw']})
    elif not ok:new_rejected.append({'id':cid,'raw':reply['raw']})
  actual_measure_t=[x['tx']['monotonic'] for x in measure];rtt=[]
  for x in measure:
   same=[r for r in x['rx'] if any(v['id']==x['exchange']['command_id'] for v in r['decoded_independent'])]
   if same:rtt.append((same[0]['monotonic']-x['tx']['monotonic'])*1000)
  stage.update({'kind':'fixed_interval_readonly_probe','tx_proof':tx_proof(txs),'utc_start':txs[0]['utc'],'utc_end':events[-1]['utc'],'kst_start':kst(txs[0]['utc']),'kst_end':kst(events[-1]['utc']),'denominators':{'all_packets_including_preflight_boundary_postflight':len(txs),'measurement_requests':len(measure),'phase_counts':dict(collections.Counter(x['exchange']['phase'] for x in ordered))},'measurement_transport_successes':sum(x['exchange']['transport_ok'] for x in measure),'measurement_timeouts':sum(not x['exchange']['transport_ok'] for x in measure),'all_transport_timeouts':sum(not x['exchange']['transport_ok'] for x in ordered),'measurement_tx_interval_ms':stats([(b-a)*1000 for a,b in zip(actual_measure_t,actual_measure_t[1:])]),'measurement_packet_rtt_ms':stats(rtt),'measurement_exchange_latency_ms':stats([x['exchange']['elapsed_seconds']*1000 for x in measure if x['exchange']['transport_ok']]),'rx_datagrams':len(rxs),'rx_packet_parse_errors':rx_parse,'parser_130_rejected_measurement_replies':len(old_rejected),'empty_measurement_reply_count':len(empty),'empty_measurement_reply_ids':dict(collections.Counter(str(x['id']) for x in empty)),'final_131_nonempty_parser_rejections':new_rejected,'invalid_reply_audit_record_count':None,'parse_error_audit_record_count':None,'audit_reason':'Probe records 1.3.0 parser acceptance, not controller INVALID_REPLY/PARSE_ERROR audit rows.'})
 else:
  txs=loadl(d/'tx_packets.jsonl');rxfile=d/'rx_packets.jsonl';rxs=loadl(rxfile) if rxfile.exists() else None
  rows=list(csv.DictReader((d/'spitfire_audit_20261027.csv').open(encoding='utf-8-sig')));atx=[r for r in rows if r['direction']=='TX'];arx=[r for r in rows if r['direction']=='RX'];invalid=[r for r in rows if r['direction']=='INVALID_REPLY'];parse=[r for r in rows if r['direction']=='PARSE_ERROR']
  pre_count=len(txs)-len(atx);assert pre_count==2,(name,pre_count);assert [txdecode(r)[0]['id'] for r in txs[:pre_count]]==[1000,1021];main=txs[pre_count:]
  for t,a in zip(main,atx):
   cmd=txdecode(t);assert len(cmd)==1 and cmd[0]['id']==int(a['command_id']) and cmd[0]['line']==a['text']
  attempts=[];active=None;orphans=[];rtt=[]
  for r in rows:
   if r['direction']=='TX':
    if active:raise AssertionError('New TX without terminal event: '+str(active))
    t=main[len(attempts)];active={'command_id':int(r['command_id']),'origin':r['result'],'tx_utc':t['utc'],'tx_monotonic':t['monotonic'],'audit_tx_utc':r['utc_time'],'tx_wire':txdecode(t)[0]['line']}
   elif r['direction'] in ('RX','ERROR'):
    if active and active['command_id']==int(r['command_id']):
     active.update({'outcome':r['direction'],'terminal_utc':r['utc_time'],'terminal_text':r['text'],'terminal_result':r['result'],'audit_elapsed_ms':(utcsec(r['utc_time'])-utcsec(active['audit_tx_utc']))*1000});attempts.append(active);active=None
    else:orphans.append(r)
  assert len(attempts)==len(main)
  rx_errors=[]
  if rxs is not None:
   for r in rxs:
    try:r['decoded_independent']=rxdecode(r)
    except Exception as exc:r['decoded_independent']=[];rx_errors.append(str(exc))
    for v in r['decoded_independent']:
     if v['id']==1021:all_hv.append({'stage':name,'utc':r['utc'],'value':v['value'],'raw':v['raw'],'source':'raw socket RX datagram'})
  else:
   for r in arx:
    if r['command_id']=='1021':all_hv.append({'stage':name,'utc':r['utc_time'],'value':r['text'].split('>',1)[1].strip(),'raw':r['text'],'source':'audit RX line; raw packet capture unavailable'})
  timeout_windows=[]
  for i,a in enumerate(attempts):
   if a['outcome']=='RX':
    if rxs is not None:
     stop=main[i+1]['monotonic'] if i+1<len(main) else float('inf');rs=[r for r in rxs if a['tx_monotonic']<=r['monotonic']<stop and any(x['id']==a['command_id'] for x in r['decoded_independent'])];assert rs,(name,a);rtt.append((rs[0]['monotonic']-a['tx_monotonic'])*1000)
    else:rtt.append(a['audit_elapsed_ms'])
   else:
    start=utcsec(a['tx_utc']);end=utcsec(a['terminal_utc']);window=[r for r in rxs if start<=utcsec(r['utc'])<=end] if rxs is not None else None;after=[r for r in rxs if utcsec(r['utc'])>end] if rxs is not None else []
    timeout_windows.append({**a,'kst_start':kst(a['tx_utc']),'kst_timeout':kst(a['terminal_utc']),'socket_rx_datagrams_during_wait':len(window) if window is not None else None,'socket_rx_command_ids_during_wait':[v['id'] for r in window for v in r['decoded_independent']] if window is not None else None,'first_socket_rx_after_timeout':{'utc':after[0]['utc'],'ids':[x['id'] for x in after[0]['decoded_independent']]} if after else None,'interpretation':'No recvfrom datagram was recorded in this wait window; this is not a physical wire-loss measurement.' if window==[] else 'Raw RX packet capture unavailable or packets exist; inspect records.'})
  origins=collections.Counter(r['result'] for r in atx);external=collections.Counter(int(r['command_id']) for r in atx if r['result']=='external compatibility monitor');main_t=[r['monotonic'] for r in main]
  stage.update({'kind':'product_scheduler_readonly_socket_fence','tx_proof':tx_proof(txs),'utc_start':txs[0]['utc'],'utc_end':summary['finished_utc'],'kst_start':kst(txs[0]['utc']),'kst_end':kst(summary['finished_utc']),'denominators':{'all_packets_including_preflight':len(txs),'preflight_requests':pre_count,'scheduler_main_requests_including_initialization':len(main),'initialization_requests_inside_main':origins['initialization'],'steady_and_monitor_requests_excluding_initialization':len(main)-origins['initialization']},'measurement_transport_successes':sum(a['outcome']=='RX' for a in attempts),'measurement_timeouts':len(timeout_windows),'timeout_rate_of_main_requests':len(timeout_windows)/len(main),'main_tx_interval_ms':stats([(b-a)*1000 for a,b in zip(main_t,main_t[1:])]),'successful_reply_rtt_ms':stats(rtt),'rtt_basis':'raw TX/RX socket monotonic timestamps' if rxs is not None else 'audit TX-to-first matching RX UTC timestamps; tiny logging overhead included','audit_rx_reply_lines':len(arx),'duplicate_or_unpaired_audit_rx_lines':len(orphans),'invalid_reply_audit_record_count':len(invalid),'invalid_reply_ids':dict(collections.Counter(r['command_id'] for r in invalid)),'invalid_reply_reasons':dict(collections.Counter(r['result'] for r in invalid)),'parse_error_audit_record_count':len(parse),'rx_packet_parse_errors':rx_errors,'tx_origin_counts':dict(origins),'external_required_poll_counts':{str(cid):external[cid] for cid in EXTERNAL_REQUIRED_READS},'all_18_required_ids_polled':all(external[cid]>0 for cid in EXTERNAL_REQUIRED_READS),'timeout_windows':timeout_windows,'raw_rx_datagrams_including_preflight':len(rxs) if rxs is not None else None,'main_and_wire_tx_alignment_verified':True})
 stages.append(stage)
all_hv.sort(key=lambda r:r['utc'])
report={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Ten completed diagnostic stages only; excludes older user GUI logs and any later standalone query not present in these directories.','source_root':str(w),'independent_checks':['Every captured TX data_hex decoded independently and compared exactly against the original query catalog.','Command IDs and command bodies both checked; summary writes_sent was not used as proof.','Scheduler preflight excludes the first verified IDN and HV queries; scheduler main includes initialization.','Packet RX logs are recvfrom observations, not NIC/wire captures.'],'stages':stages,'totals':{'stage_count':len(stages),'all_tx_datagrams':sum(s['tx_proof']['datagrams'] for s in stages),'decoded_commands':sum(s['tx_proof']['decoded_commands'] for s in stages),'write_commands':sum(s['tx_proof']['write_commands_by_id_ge_2000'] for s in stages),'non_catalog_query_commands':sum(len(s['tx_proof']['non_catalog_query_commands']) for s in stages),'all_decoded_payloads_are_exact_known_read_queries':all(s['tx_proof']['all_are_exact_catalog_queries'] for s in stages),'direct_probe_measurement_requests':sum(s['denominators'].get('measurement_requests',0) for s in stages),'direct_probe_measurement_transport_timeouts':sum(s['measurement_timeouts'] for s in stages if s['kind']=='fixed_interval_readonly_probe'),'scheduler_main_requests':sum(s['denominators'].get('scheduler_main_requests_including_initialization',0) for s in stages),'scheduler_transport_timeouts':sum(s['measurement_timeouts'] for s in stages if s['kind']=='product_scheduler_readonly_socket_fence'),'scheduler_invalid_reply_records':sum(s['invalid_reply_audit_record_count'] or 0 for s in stages),'scheduler_parse_error_records':sum(s['parse_error_audit_record_count'] or 0 for s in stages)},'hv_observations':{'count':len(all_hv),'distinct_values':dict(collections.Counter(r['value'] for r in all_hv)),'last_recorded_reply_in_supplied_stage_logs':all_hv[-1] if all_hv else None,'all_recorded_hv_readbacks_zero':all(r['value']=='0' for r in all_hv)},'nic_observation_from_parent':{'link':'Up','link_speed':'100 Mbps','rx_tx_errors_and_discards':0,'basis':'Parent tool observation; not independently queried by this analysis.'},'conclusions':{'confirmed':['Real compound/unit-bearing response parser compatibility was corrected.','The actual 60-query capability sweep has 53 nonempty parseable replies and 7 empty replies retained as unknown.','Every decoded TX packet in the ten stages is an exact known read query; zero writes.','No socket RX datagram was recorded during the captured 200 ms and auto-poll-off timeout windows.','Auto-poll-off leaves heartbeat and all 18 mandatory external reads active.'],'not_determined':['Physical wire loss versus device firmware scheduling versus other network/OS causes of missing socket replies.','A causal polling-rate explanation: scheduler timeout counts 5/2/1/1 used different request counts, one nonrandomized run per condition, and different command mixes.','Laser emission, HV activation, optical timing or external pump operation were not tested by these read-only stages.']}}
f=w/'aggregate_final.json';f.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('SAVED',f);print('TOTAL',json.dumps(report['totals']));print('HV',json.dumps(report['hv_observations']))
for s in stages:
 print(s['name'],'N',s['denominators'],'timeout',s['measurement_timeouts'],'invalid',s['invalid_reply_audit_record_count'],'parse',s['parse_error_audit_record_count'],'interval_median_ms',(s.get('main_tx_interval_ms') or s.get('measurement_tx_interval_ms'))['median'],'rtt_median_ms',(s.get('successful_reply_rtt_ms') or s.get('measurement_packet_rtt_ms'))['median'])
 if s.get('timeout_windows'):print('RXWINDOWS',[(x['command_id'],x['socket_rx_datagrams_during_wait']) for x in s['timeout_windows']])
