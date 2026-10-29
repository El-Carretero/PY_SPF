"""Broad callback differential oracle: original x86, in-memory CVI/CRT stubs.

No original Windows process, DLL execution, file/device access or socket calls.
The resource's actual default numeric data types drive GetCtrlVal writes.
"""
from __future__ import annotations
import json,struct,sys,math
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP,UC_X86_REG_EAX
from native_oracle import NativeOracle,PANEL_GLOBALS,ROOT
from spitfire.callbacks import dispatch
from spitfire.protocol import format_message

RESOURCE=ROOT/'spitfire/resources'
SPEC=json.loads((RESOURCE/'gui_spec.json').read_text())
SERVER=json.loads((ROOT/'analysis/server_gui_spec.json').read_text())
DTYPES={(p['id'],c['id']):c['data_type'] for p in SPEC['panels'] for c in p['controls']}
DEFAULTS={(p['id'],c['id']):c.get('value',0) for p in SPEC['panels'] for c in p['controls']}
ATTR_TYPES={v['id']:v['type'] for v in json.loads((ROOT/'spitfire/resources/cvi_attributes.json').read_text()).values()}

class ExtendedCallbackOracle(NativeOracle):
 def run(self,name,values=None,*,panel=6,control=0,event=1,state=None,server=False):
  self.values=dict(values or {});self.sent=[];self.calls=[];self.mouse=state or {};self.isserver=server
  self.u=Uc(UC_ARCH_X86,UC_MODE_32);u=self.u
  u.mem_map(0x400000,0x50000);u.mem_write(0x400000,self.pe.get_memory_mapped_image())
  u.mem_map(0x1000000,0x100000);u.mem_map(0x2000000,0x10000);u.mem_map(0xf000000,0x1000)
  # Actual CVI startup initializes x87; do the same before each isolated callback.
  u.mem_write(0x2000000,b'\xdb\xe3');u.emu_start(0x2000000,0x2000002)
  esp=0x10ff000;u.mem_write(esp,struct.pack('<7I',0xf000000,panel,control,event,0,0,0));u.reg_write(UC_X86_REG_ESP,esp)
  for p,a in PANEL_GLOBALS.items():u.mem_write(a,struct.pack('<I',p))
  for key,val in (state or {}).items():
   if '_'+key in self.symbols:u.mem_write(self.symbols['_'+key],struct.pack('<I',int(val)&0xffffffff))
  handlers={'_GetCtrlVal@12':self.getctrl,'_sprintf':self.sprintf,'_SetCtrlVal':self.setctrl,
   '_SetCtrlAttribute':self.setattr,'_SetPanelAttribute':self.panelattr,
   '_push_inside_stack':self.pushinside,'_push_outside_stack':self.pushinside,
   '_GetPanelMenuBar@4':self.getmenu,'_SetMenuBarAttribute':self.menuattr,
   '_DisplayPanel@4':self.showpanel,'_HidePanel@4':self.hidepanel,
   '_GetGlobalMouseState@24':self.getmouse,'_time':self.time,
   '_server_DisplayPanel':self.showserver,'_server_HidePanel':self.hideserver,
   '_ResetTextBox@12':self.resettextbox,'_ServerTCPWrite@16':self.serverwrite,
   '_strlen':self.strlen,'_strcat':self.strcat,'_QuitUserInterface@4':self.quit}
  addrs={self.symbols[k]:h for k,h in handlers.items()}
  runtime={a:n for n,a in self.symbols.items() if n.startswith('_') and a<0x4048f8}
  def hook(emu,addr,size,data):
   if addr==0xf000000:emu.emu_stop();return
   if addr in addrs:addrs[addr]();return
   if addr in runtime:raise RuntimeError('unhandled original call '+runtime[addr])
  u.hook_add(UC_HOOK_CODE,hook);u.emu_start(self.symbols['_'+name],0xf000000,count=100000)
  if u.reg_read(UC_X86_REG_EIP)!=0xf000000:raise RuntimeError('instruction budget exhausted')
  return self.sent,self.calls
 def retvalue(self,value,pop=0):self.ret(pop);self.u.reg_write(UC_X86_REG_EAX,value&0xffffffff)
 def getctrl(self):
  _,p,c,ptr=self.stack(4);value=self.values.get((p,c),0)
  if self.isserver:
   dtype=next((c1['data_type'] for p1 in SERVER['panels'] for c1 in p1['controls'] if c1['id']==c),1)
  else:dtype=DTYPES.get((p,c),3)
  if dtype==5:data=str(value).encode('cp1252')+b'\0'
  elif dtype==1:data=struct.pack('<I',int(value)&0xffffffff)
  else:data=struct.pack('<f',float(value))
  self.u.mem_write(ptr,data);self.ret(12)
 def signed(self,v):return v if v<0x80000000 else v-0x100000000
 def setctrl(self):
  ret,p,c,arg=self.stack(4);following=bytes(self.u.mem_read(ret,3))
  if following==b'\x83\xc4\x10':value=struct.unpack('<d',self.u.mem_read(self.u.reg_read(UC_X86_REG_ESP)+12,8))[0]
  elif 0x400000<=arg<0x450000 or 0x1000000<=arg<0x1100000:value=self.cstr(arg)
  else:value=self.signed(arg)
  self.calls.append(('set',(p,c),value));self.values[p,c]=value;self.ret()
 def setattr(self):
  _,p,c,a,arg=self.stack(5)
  if ATTR_TYPES.get(a)==9:value=struct.unpack('<d',self.u.mem_read(self.u.reg_read(UC_X86_REG_ESP)+16,8))[0]
  elif ATTR_TYPES.get(a)==5:value=self.cstr(arg)
  else:value=self.signed(arg)
  self.calls.append(('attribute',(p,c,a),value));self.ret()
 def panelattr(self):
  _,p,a,arg=self.stack(4);value=self.cstr(arg) if ATTR_TYPES.get(a)==5 else self.signed(arg)
  self.calls.append(('panel_attribute',(p,a),value));self.ret()
 def getmenu(self):self.retvalue(self.stack(2)[1],4)
 def menuattr(self):
  _,p,item,a,arg=self.stack(5);self.calls.append(('menu_attribute',(p,item,a),self.signed(arg)));self.ret()
 def showpanel(self):self.calls.append(('panel',self.stack(2)[1],True));self.ret(4)
 def hidepanel(self):self.calls.append(('panel',self.stack(2)[1],False));self.ret(4)
 def showserver(self):self.calls.append(('server_panel',None,True));self.ret()
 def hideserver(self):self.calls.append(('server_panel',None,False));self.ret()
 def getmouse(self):
  s=self.stack(7)
  for ptr in s[2:]:self.u.mem_write(ptr,struct.pack('<I',0))
  self.u.mem_write(s[4],struct.pack('<I',int(self.mouse.get('left_mouse_down',0))))
  self.u.mem_write(s[5],struct.pack('<I',int(self.mouse.get('right_mouse_down',0))));self.ret(24)
 def time(self):
  ptr=self.stack(2)[1]
  if ptr:self.u.mem_write(ptr,struct.pack('<I',100))
  self.retvalue(100)
 def resettextbox(self):
  _,p,c,ptr=self.stack(4);self.calls.append(('reset_textbox',(p,c),self.cstr(ptr)));self.ret(12)
 def serverwrite(self):
  _,p,ptr,n,timeout=self.stack(5);text=bytes(self.u.mem_read(ptr,n)).decode('cp1252')
  self.calls.append(('server_write',None,text));self.retvalue(n,16)
 def strlen(self):self.retvalue(len(self.cstr(self.stack(2)[1])))
 def strcat(self):
  _,dst,src=self.stack(3);self.u.mem_write(dst,(self.cstr(dst)+self.cstr(src)).encode('cp1252')+b'\0');self.retvalue(dst)
 def quit(self):self.calls.append(('quit',None,None));self.ret(4)

GUI_KINDS={'set','attribute','panel_attribute','panel','menu_attribute','server_panel','reset_textbox','server_write','quit'}
ORACLE = None

def same(a,b):
 if isinstance(a,(float,int))and isinstance(b,(float,int)):
  if math.isnan(a)and math.isnan(b):return True
  return a==b or math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13)
 return a==b

def compare(name,panel,ctrl,value,connected,event=1,*,state=None,server=False,overrides=None):
 values=dict(DEFAULTS);values.update({(6,48):connected,(panel,ctrl):value})
 # Exercise branch calculations with nontrivial fixed-source frequencies.
 values.update({(5,43):3.0,(5,28):1000.0,(9,9):500.0})
 values.update(overrides or {})
 if (panel,ctrl) in ((5,43),(5,28),(9,9)):values[panel,ctrl]=value
 state={'gAccessLevel':2,**(state or {})}
 global ORACLE
 if ORACLE is None:ORACLE=ExtendedCallbackOracle()
 oracle=ORACLE
 record={'callback':name,'panel':panel,'control':ctrl,'value':value,'connected':connected,'event':event}
 try:
  native_commands,native_calls=oracle.run(name,values,panel=panel,control=ctrl,event=event,state=state,server=server)
  py=dispatch(name,value,read=lambda p,c:values.get((p,c),0),event=event,panel=panel,control=ctrl,state=state)
  pycommands=[format_message(x.target,x.value or '') for x in py if x.kind in ('command','query')]
  pycalls=[(x.kind,x.target,x.value) for x in py if x.kind in GUI_KINDS]
  # Native stores update `oracle.values`; Python read uses the pre-callback
  # view. Compare observable final mutations, preserving command order.
  n={(k,str(t)):(t,v) for k,t,v in native_calls};p={(k,str(t)):(t,v) for k,t,v in pycalls}
  diffs=[]
  for key in sorted(set(n)|set(p)):
   a=n.get(key,('MISSING','MISSING'))[1];b=p.get(key,('MISSING','MISSING'))[1]
   if not same(a,b):diffs.append({'kind':key[0],'target':key[1],'native':a,'python':b})
  record.update(native_commands=native_commands,python_commands=pycommands,native_gui=native_calls,python_gui=pycalls,
                differences=diffs,passed=native_commands==pycommands and not diffs)
 except Exception as exc:record.update(passed=False,error=f'{type(exc).__name__}: {exc}')
 return record

def verify():
 bindings=json.loads((RESOURCE/'callback_bindings.json').read_text());unique={}
 for b in bindings['SPITFIRE']:
  if b['kind']=='control':unique.setdefault(b['name'],b)
 cases=[]
 skip={'tmr_Data_Logger','MainCallBack','reconnect','QuitProgram'}
 for name,b in sorted(unique.items()):
  if name in skip:continue
  p,c=b['panel'],b['control'];dtype=DTYPES.get((p,c),1)
  vals=(0.0,1.0,12.345) if dtype==3 else ((0,1,2) if name=='setopmode' else (0,1))
  events={'parse_command5':(3,), 'BW_reset':(3,), 'cllbck':(1,2,3),
          'picture_Callback1':(3,5), 'picture_Callback2':(3,4,5,6), 'tmr_Mouse_Callback1':(15,)}.get(name,(1,))
  for value in vals:
   for connected in (0,1):
    for event in events:
     cases.append(compare(name,p,c,value,connected,event,
                          overrides={(6,59):'EMP:STB?'} if name=='strnsendcllback' else None))
 # Extra direct helper paths and per-access-mode GUI mutation checks.
 for name in ['hide_emp_controls','show_emp_controls','hide_ecu_controls','show_ecu_controls','open_curtain','close_curtain']:
  cases.append(compare(name,6,0,0,0))
 for level in (0,1,2,3):cases.append(compare('cmtRETUSERMODE',6,45,0,0,state={'gAccessLevel':level}))
 # Mouse timer must preserve motion while either button remains pressed.
 for left,right in ((0,1),(1,0),(1,1)):
  cases.append(compare('tmr_Mouse_Callback1',6,4,0,0,15,state={'left_mouse_down':left,'right_mouse_down':right}))
 for b in bindings['SERVER']:
  if b['name']in ('TransmitCB','ClearScreenCB'):
   cases.append(compare(b['name'],1,b['control'],'hello' if b['name']=='TransmitCB' else 0,0,server=True,
                        overrides={(1,3):'hello'}))
 failures=[x for x in cases if not x['passed']]
 result={'method':'Unicorn original x86 callback execution with CVI/CRT intercepted and resource-derived GetCtrlVal data types',
         'case_count':len(cases),'callback_count':len(set(x['callback'] for x in cases)),
         'passed':len(cases)-len(failures),'failed':len(failures),'cases':cases}
 (ROOT/'analysis/native_callback_extended_results.json').write_text(json.dumps(result,indent=2,allow_nan=True)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='cases'}));
 for x in failures:print(json.dumps(x,allow_nan=True))
 return not failures
if __name__=='__main__':sys.exit(0 if verify() else 1)
