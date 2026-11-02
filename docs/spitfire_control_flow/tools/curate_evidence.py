"""Rebuild documentation evidence from retained analysis artifacts; no device I/O.

The publication build uses the already-curated files. Re-curation requires the
private input artifacts identified by hashes in evidence/source_registry.json.
"""
from pathlib import Path
import argparse,csv,hashlib,json,subprocess

p=argparse.ArgumentParser();p.add_argument('--artifacts',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[3];out=root/'docs/spitfire_control_flow/evidence';out.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git_blob_sha256(commit,path):
 data=subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=root)
 return hashlib.sha256(data).hexdigest()
def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
b=a.artifacts/'bwd-history-pc1';s=read(b/'summary.json')
aliases={x['file']:f'P01-SOURCE-{i:02d}' for i,x in enumerate(s['sources'],1)}
sources=[{'id':aliases[x['file']],'logical_path':x['file'].split('\\logs\\')[-1] if '\\logs\\' in x['file'] else Path(x['file']).name,
          'sha256':x['sha256'],'response_lines':x['response_lines'],'first_utc':x['first_utc'],'last_utc':x['last_utc']} for x in s['sources']]
base={k:s[k] for k in ('scan_cutoff','original_jsonl_files_scanned','source_files_retained','response_lines','source_rx_records','first_utc','last_utc','word_counts','limits')}
base['sources']=sources;base['provenance']='Actual stored physical responses; synthetic/replay/mirrored files excluded; not continuous monitoring.'
base['per_tag']={t:{k:v for k,v in x.items() if k not in ('first','last')} for t,x in s['per_tag'].items()}
base['source_artifact_sha256']=sha(b/'summary.json')
reset=read(b/'reset-ack-summary.json');base['reset_commands']=reset['summary'].copy();base['reset_commands'].pop('tx_sources',None)
write('bwd_history_summary.json',base)
with (out/'bwd_rx.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,['utc','tag','word','bwd20_clear','bwd21_clear','both_bwd_clear','source_id','source_line_or_query_index'],lineterminator='\n');w.writeheader()
 for x in csv.DictReader((b/'bwd-rx.csv').open(encoding='utf-8-sig')):
  w.writerow({**{k:x[k] for k in w.fieldnames if k!='source_id'},'source_id':aliases[x['source_file']]})
v=a.artifacts/'PY_SPF_1.0-validation';modes={}
for mode in ('fault','bwd'):
 x=read(v/f'reset-retest-{mode}-analysis.json');z=x['summary']
 modes[mode]={'provenance':'Physical device, explicit Native adapter callback; allowlisted writes; not Windows mouse/NI event dispatch validation',
  'write_tag_counts':x['write_tag_counts'],'write_receipts':x['write_receipts'],
  'readbacks':{k:{'before':r['before'],'after':r['after']} for k,r in x['readbacks'].items()},
  'communication':z['communication'],'optout_one_verified_after':z['optout_one_verified_after'],
  'post_events':x['post_activation_non_wire_events'],'source_artifact_sha256':sha(v/f'reset-retest-{mode}-analysis.json')}
write('reset_retest_summary.json',{'sessions':modes,'limitations':['Separate sessions; no optical output measured; other automatic writes suppressed.']})
write('fault_burst_summary.json',{'provenance':'Stored normal Native control-session log plus separate socket-forbidden reproduction',
 'source_log':'private:P01/logs/reset-investigation-20261102-062651/events.jsonl',
 'source_sha256':'d4c7385b705312acff1b3a003cdb55f5eb88e3e462a37b99503a796dd36370a5',
 'reset_groups':8,'writes_transmitted':31,'write_acks':31,'cancelled_write_tag':2050,
 'last_status_before_utc':'2026-11-02T06:20:53.709+00:00','stale_utc':'2026-11-02T06:21:23.714+00:00',
 'next_status_utc':'2026-11-02T06:21:34.831+00:00','status_gap_seconds':41.122,'gui_unready_seconds':11.117,
 'cause_in_scope':'Priority reset queue delayed STATUS polling despite continuing matched replies; no UDP error/reconnect observed.',
 'not_proven':['Adapter failure','All physical states throughout gaps','Firmware-internal reset behavior']})
r=root/'analysis/release_1_0_validation.json';write('release_validation.json',{'tracked_source':'analysis/release_1_0_validation.json','sha256':sha(r),'record':read(r)})
refs={'native_1_0':'cebcc28490f48e9e5d4d1c2e2feef34d638244e7','reconstruction_post2':'c49fada3ffeb660acb56ceeeabc5c32647750df0',
 'main_post1':'78d3f447b1ca3dea35c5a737b75569a882bc0650','comparison_1_5_1':'e87225bdc904aeb5348daa409abfa49de449b017'}
write('branch_baselines.json',{'repository':'El-Carretero/PY_SPF','refs':refs,'native_field_scope':'native_1_0'})
files=['spitfire/controller.py','spitfire/decoders.py','spitfire/callbacks.py','spitfire/scheduling.py','spitfire/native.py','spitfire/native_ticker.py','spitfire/protocol.py','analysis/reference/SPITFIRE.EXE']
write('source_manifest.json',{'base_commit':refs['native_1_0'],'files':[{'path':f,'sha256':git_blob_sha256(refs['native_1_0'],f)} for f in files],
 'provided_documents':[{'id':'MAN-330A','title':"330A, Rev. A, Spitfire Pro User's Manual",'pdf_pages':110,'sha256':'d9bb260827f78a2ed67477043cb3036a26b771aaf19a0c3ec9aa6649449d5e29','availability':'User-provided attachment; original retained by owner; full PDF not redistributed'},
 {'id':'STD-XL','title':'XL-STD-DOC-001 xLaPPLAs Technical Publications Standards, Rev A','pdf_pages':63,'sha256':'3a59e249677683bc373a0a1f4ee35fbfb9e677310c49f778806a961654663157','availability':'User-provided attachment; formatting authority; full PDF not redistributed'}]})
print('Curated evidence written; no network/device access.')
