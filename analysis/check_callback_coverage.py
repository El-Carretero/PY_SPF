"""Audit resource binding coverage without invoking external I/O or original code."""
from pathlib import Path
import importlib.util, json, sys, ast
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'work/spitfire_python/spitfire/callbacks.py'
spec=importlib.util.spec_from_file_location('callbacks_coverage',p);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
r=ROOT/'work/spitfire_python/spitfire/resources'
bindings=json.loads((r/'callback_bindings.json').read_text());gui=json.loads((r/'gui_spec.json').read_text())
control_lookup={(p['id'],c.get('resource_id',c['id'])):c for p in gui['panels'] for c in p['controls']}
controller=ast.parse((ROOT/'work/spitfire_python/spitfire/controller.py').read_text())
controller_kinds=set()
for n in ast.walk(controller):
 if isinstance(n,ast.Compare) and isinstance(n.left,ast.Name) and n.left.id=='kind':
  for comp in n.comparators:
   for x in ast.walk(comp):
    if isinstance(x,ast.Constant) and isinstance(x.value,str):controller_kinds.add(x.value)
events={'picture_Callback1':[3,5], 'picture_Callback2':[3,4,5,6], 'tmr_Mouse_Callback1':[15],
        'tmr_Data_Logger':[15], 'MainCallBack':[7,11], 'MainPanelCB':[11], 'cllbck':[1,2,3],
        'parse_command5':[3], 'BW_reset':[3]}
rows=[]
for source,entries in bindings.items():
 for b in entries:
  name=b['name'];row=dict(b,source=source)
  if b['kind']=='control' and source=='SPITFIRE':
   c=control_lookup[b['panel'],b['resource_id']];row['runtime_control']=c['local_index']+1
  elif b['kind']=='control' and source=='SERVER':
   server=json.loads((ROOT/'work/analysis/server_gui_spec.json').read_text())
   lookup={c['resource_id']:c['id'] for pan in server['panels'] for c in pan['controls']}
   row['runtime_control']=lookup[b['resource_id']]
  else:row['runtime_control']=None
  action_kinds=set();errors=[]
  for connected in (0,1):
   for value in (0,1):
    def read(p,c):
     if (p,c)==(6,48):return connected
     if (p,c)==(5,43):return 2
     if (p,c)==(6,59):return '*IDN?'
     return value
    for event in events.get(name,[1]):
     try:
      actions=mod.dispatch(name,value,read=read,event=event,panel=b['panel'],control=row['runtime_control'],state={'gAccessLevel':2})
      action_kinds.update(a.kind for a in actions)
     except Exception as e:errors.append(f'{type(e).__name__}: {e}')
  row.update(dispatcher_implemented=not errors,activated_events=events.get(name,[1]),
             action_kinds=sorted(action_kinds),errors=sorted(set(errors)),
             controller_unhandled_action_kinds=sorted(action_kinds-controller_kinds))
  rows.append(row)
report={'binding_count':len(rows),'unique_callback_count':len(set(x['name'] for x in rows)),
        'dispatcher_covered_count':sum(x['dispatcher_implemented'] for x in rows),
        'controller_action_kinds':sorted(controller_kinds),
        'dispatcher_missing_callbacks':sorted(set(x['name'] for x in rows if not x['dispatcher_implemented'])),
        'controller_unhandled_action_kinds':sorted(set(k for x in rows for k in x['controller_unhandled_action_kinds'])),
        'bindings':rows}
(ROOT/'work/analysis/callback_coverage.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='bindings'},indent=2))
