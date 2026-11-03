import json,re
from pathlib import Path
f=json.loads(Path('work/analysis/functions.json').read_text());syms=json.loads(Path('work/analysis/symbols.json').read_text())
from importlib.util import spec_from_file_location,module_from_spec
import sys
spec=spec_from_file_location('callback_specs',Path('work/spitfire_python/spitfire/callbacks.py'));m=module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
byname={x['name']:x for x in syms}
manifest={
 'evidence':{'original':'SPITFIRE.EXE','build':'2005-03-18','method':'native symbol map, x86 disassembly, Ghidra decompilation'},
 'panel_ids':{'main':6,'setup':9,'info':5,'ecu':2,'faults':3,'help':4,'secrets':7,'empower':8,'programmer':1},
 'action_contract':{'command':'target: command ID, value: exact parameter suffix','query':'target: query ID','attribute':'target: [panel ID, control ID, CVI attribute ID], value: new value','set':'target: [panel ID, control ID], value: new value','panel_attribute':'target: [panel ID,CVI attribute ID], value: new value','panel':'target: panel ID, value: visible','state':'target: variable name, value: new value'},
 'numeric':{}, 'integer':{},'show_panels':m.SHOW_PANELS,'hide_panels':m.HIDE_PANELS,'callback_evidence':{}
}
for n,v in m.NUMERIC_CALLBACKS.items():manifest['numeric'][n]={'command':v[0],'followup_query_when_connected':v[1],'scale':v[2],'fixed_source':v[3],'format':' %5.2f'}
for n,v in m.INTEGER_CALLBACKS.items():manifest['integer'][n]={'command':v[0],'followup_query_when_connected':v[1],'fixed_source':v[2],'format':' %i'}
for n,lines in f.items():
 if n not in byname or not 0x40ab10<=byname[n]['address']<=0x413148:continue
 if not any(x in n for x in ('Callback','callback','_set','_slide','_secret','_close','_open','_cllbck','_Monitor','_HV','_humoverride','_trig','_osc','_optout','_empoweroptout','_Divisor','_BW','_LBO','_teconoff','_Quit','_Shutdown','_display_faults','_esc')):continue
 queues=[]
 for i,l in enumerate(lines):
  if 'call' in l and '_push_' in l:
   vals=re.findall(r'push\s+(0x[0-9a-f]+|\d+)',' '.join(lines[max(0,i-3):i]))
   if vals:queues.append(int(vals[-1],0))
 manifest['callback_evidence'][n.lstrip('_')]={'address':hex(byname[n]['address']),'queue_ids_in_source_order':queues}
Path('work/analysis/callbacks.json').write_text(json.dumps(manifest,indent=2)+'\n')
