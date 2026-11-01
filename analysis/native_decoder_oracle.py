"""Differential x86 response decoder oracle with CVI/CRT intercepted.

Maps PE sections in Unicorn only. No OS process, DLL loading, device, sockets,
or Windows execution is used. x87 results are preserved by tiny arithmetic
stubs; all widget I/O and queued commands are captured in memory.
"""
from __future__ import annotations
from pathlib import Path
import ctypes,json,struct,math,re,sys
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'analysis')]
from spitfire.decoders import ResponseDecoder,c_atof,c_atoi
from native_oracle import NativeOracle,PANEL_GLOBALS

class DecoderOracle(NativeOracle):
 def run(self,query_id,payload,values=None,state=None):
  self.values=dict(values or {});self.sent=[];self.calls=[];self.tokens=0
  self.u=Uc(UC_ARCH_X86,UC_MODE_32);u=self.u
  u.mem_map(0x400000,0x50000);u.mem_write(0x400000,self.pe.get_memory_mapped_image())
  u.mem_map(0x1000000,0x100000);u.mem_map(0x2000000,0x10000);u.mem_map(0xf000000,0x1000)
  # Initialize the x87 environment as the normal CVI startup would.
  u.mem_write(0x2000100,b'\xdb\xe3');u.emu_start(0x2000100,0x2000102)
  # CRT atof return stub: fld double[scratch];ret. ftol pop stub: fstp st0;ret.
  u.mem_write(0x2000200,b'\xdd\x05'+struct.pack('<I',0x2000300)+b'\xc3')
  u.mem_write(0x2000210,b'\xdd\xd8\xc3')
  message=f'(1,1)<{query_id}>{payload}'.encode('cp1252')+b'\0'
  u.mem_write(0x2001000,message)
  esp=0x10ff000;u.mem_write(esp,struct.pack('<II',0xf000000,0x2001000));u.reg_write(UC_X86_REG_ESP,esp)
  for panel,addr in PANEL_GLOBALS.items():u.mem_write(addr,struct.pack('<I',panel))
  initial={key:val for key,val in ResponseDecoder().state.items()if isinstance(val,int)and '_'+key in self.symbols}
  initial.update(state or {})
  for key,val in initial.items():u.mem_write(self.symbols['_'+key],struct.pack('<I',val))
  handlers={'_GetCtrlVal@12':self.getctrl,'_SetCtrlVal':self.setctrl,'_SetCtrlAttribute':self.setattr,
   '_atoi':self.atoi,'_atof':self.atof,'__ftol':self.ftol,'_strtok':self.strtok,
   '_strcpy':self.strcpy,'_strcat':self.strcat,'_strstr':self.strstr,'_sprintf':self.sprintf,
   '_sscanf':self.sscanf,'_time':self.time,'_push_inside_stack':self.pushinside,
   '_push_outside_stack':self.pushinside,'_open_curtain':self.nop,
   '_hide_ecu_controls':self.nop,'_show_ecu_controls':self.nop,
   '_hide_emp_controls':self.nop,'_show_emp_controls':self.nop}
  addrs={self.symbols[k]:(k,v) for k,v in handlers.items()}
  runtime={address:name for name,address in self.symbols.items()if name.startswith('_') and address<0x4048f8}
  def hook(emu,addr,size,data):
   if addr==0xf000000:emu.emu_stop();return
   if addr in addrs:addrs[addr][1]();return
   if addr in runtime:raise RuntimeError('unhandled original call '+runtime[addr])
  u.hook_add(UC_HOOK_CODE,hook)
  u.emu_start(self.symbols['_gextHandleReceivedMsg'],0xf000000,count=500000)
  if u.reg_read(UC_X86_REG_EIP)!=0xf000000:raise RuntimeError('native instruction budget exhausted')
  return self.calls
 def retvalue(self,value,pop=0):
  self.ret(pop);self.u.reg_write(UC_X86_REG_EAX,value&0xffffffff)
 def nop(self):self.ret()
 def setctrl(self):
  ret,panel,ctrl,arg=self.stack(4)
  following=bytes(self.u.mem_read(ret,3))
  if following==b'\x83\xc4\x10':value=struct.unpack('<d',self.u.mem_read(self.u.reg_read(UC_X86_REG_ESP)+12,8))[0]
  elif 0x400000<=arg<0x450000 or 0x2000000<=arg<0x2010000:value=self.cstr(arg)
  else:value=arg if arg<0x80000000 else arg-0x100000000
  self.calls.append((panel,ctrl,None,value));self.values[panel,ctrl]=value;self.ret()
 def setattr(self):
  ret,panel,ctrl,attr,arg=self.stack(5)
  if attr==0x2da:value=struct.unpack('<d',self.u.mem_read(self.u.reg_read(UC_X86_REG_ESP)+16,8))[0]
  elif attr==0x281:value=self.cstr(arg)
  else:value=arg
  self.calls.append((panel,ctrl,attr,value));self.ret()
 def atoi(self):self.retvalue(c_atoi(self.cstr(self.stack(2)[1])))
 def atof(self):
  value=c_atof(self.cstr(self.stack(2)[1]));self.u.mem_write(0x2000300,struct.pack('<d',value))
  self.u.reg_write(UC_X86_REG_EIP,0x2000200)
 def ftol(self):
  sw=self.u.reg_read(UC_X86_REG_FPSW);top=(sw>>11)&7
  mantissa,exp=self.u.reg_read(globals()['UC_X86_REG_FP'+str(top)])
  value=math.ldexp(float(mantissa), (exp&0x7fff)-16383-63)
  if exp&0x8000:value=-value
  integer=math.trunc(value)
  self.u.reg_write(UC_X86_REG_EAX,integer&0xffffffff);self.u.reg_write(UC_X86_REG_EDX,(integer>>32)&0xffffffff)
  self.u.reg_write(UC_X86_REG_EIP,0x2000210)
 def strtok(self):
  _,source,delim=self.stack(3)
  if source:self.tokens=source
  if not self.tokens:self.retvalue(0);return
  delim=self.cstr(delim).encode('cp1252')
  start=self.tokens
  while bytes(self.u.mem_read(start,1))[0] in delim and bytes(self.u.mem_read(start,1))!=b'\0':start+=1
  if bytes(self.u.mem_read(start,1))==b'\0':self.tokens=0;self.retvalue(0);return
  end=start
  while True:
   char=bytes(self.u.mem_read(end,1))[0]
   if char==0:self.tokens=0;break
   if char in delim:self.u.mem_write(end,b'\0');self.tokens=end+1;break
   end+=1
  self.retvalue(start)
 def strcpy(self):
  _,dst,src=self.stack(3);self.u.mem_write(dst,self.cstr(src).encode('cp1252')+b'\0');self.retvalue(dst)
 def strcat(self):
  _,dst,src=self.stack(3);self.u.mem_write(dst,(self.cstr(dst)+self.cstr(src)).encode('cp1252')+b'\0');self.retvalue(dst)
 def strstr(self):
  _,src,needle=self.stack(3);idx=self.cstr(src).find(self.cstr(needle));self.retvalue(src+idx if idx>=0 else 0)
 def sscanf(self):
  _,src,fmt,dst=self.stack(4);text=self.cstr(src);form=self.cstr(fmt)
  if form!='%x':raise RuntimeError('unexpected scanf format '+repr(form))
  # Use an independent C runtime conversion. Reusing the Python decoder's
  # regex previously masked its incorrect handling of real 0X-prefixed data.
  crt=ctypes.CDLL('msvcrt' if sys.platform=='win32' else None)
  value=ctypes.c_uint()
  converted=crt.sscanf(ctypes.c_char_p(text.encode('cp1252')),
                       ctypes.c_char_p(form.encode('ascii')),ctypes.byref(value))
  if converted==1:self.u.mem_write(dst,struct.pack('<I',value.value))
  self.retvalue(converted)
 def time(self):
  _,ptr=self.stack(2)
  if ptr:self.u.mem_write(ptr,struct.pack('<I',100))
  self.retvalue(100)


def final(updates):
 return {(p,c,a):v for p,c,a,v in updates}

def compare(q,payload,values=None,state=None):
 inputs={'widget_values':[{'panel_id':p,'control_id':c,'value':v}for(p,c),v in sorted((values or {}).items())],
         'state_overrides':dict(state or {}),
         'decoder_initial_state':dict(ResponseDecoder().state)}
 o=DecoderOracle()
 try:
  native=o.run(q,payload,values,state)
 except Exception as e:return {'query':q,'payload':payload,'inputs':inputs,'error':str(e)}
 d=ResponseDecoder();d.values.update(values or {});d.state.update(state or {})
 py=d.decode(q,payload);python=[(x.panel_id,x.control_id,x.attribute,x.value)for x in py]
 n=final(native);p=final(python)
 differences=[]
 for k in sorted(set(n)|set(p),key=str):
  a=n.get(k,'MISSING');b=p.get(k,'MISSING')
  same=a==b
  if isinstance(a,float)and isinstance(b,float):same=math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13)
  if not same:differences.append({'key':k,'native':a,'python':b})
 return {'query':q,'payload':payload,'inputs':inputs,'pass':not differences,'differences':differences,'native':native,'python':python}


def verify():
 cases=[]
 queries=json.loads((ROOT/'analysis/command_tables.json').read_text())['queries']
 for q in range(1000,1090):
  if q in (1034,1035,1036,1037,1038):samples=['Maker,Model,Revision,Firmware extra','NOT CONNECTED']
  elif q in (1045,1046,1047,1048,1049,1058,1059,1063,1064):samples=['1 ENA BWD ON 0 0 12.75','1 NENA NBWD OFF 0 0 -4.5']
  elif q==1052:samples=['0 1 2 8.5']
  elif q==1014:samples=['0 0 0 0','127 254 19 1']
  elif q in (1050,1051,1067):samples=['INT','EXT']
  elif q==1054:samples=['SING NEG','DUAL POS']
  elif q==1080:samples=['CONT','SING']
  elif q in (1039,1066):samples=['0','30001','f800']
  elif q in (1013,1015,1019,1028,1029,1057,1088):samples=['0','1','256','512','2048','3843']
  else:samples=['0','1','123.5','-9']
  for payload in samples:cases.append(compare(q,payload,values={(5,43):4,(5,28):1000,(9,9):2000}))
 # First and steady-state PRF, optout, and health-related flags.
 for q in (1009,1010,1011,1012,1071,1076):
  cases.append(compare(q,'123.5',values={(5,43):4,(5,28):1000,(9,9):2000},state={'initial_secrets_fill':0,'initial_secrets_read':0}))
 for q,name in ((1013,'emp_optout'),(1015,'hed_optout'),(1028,'ecu_optout')):
  cases.append(compare(q,'3843',state={name:1}))
 failures=[x for x in cases if not x.get('pass')]
 result={'method':'Original x86 _gextHandleReceivedMsg emulated in Unicorn; CRT/CVI intercepted; no Windows process or hardware','case_count':len(cases),'passed':len(cases)-len(failures),'cases':cases}
 (ROOT/'analysis/native_decoder_oracle_results.json').write_text(json.dumps(result,indent=2))
 print(json.dumps({'cases':len(cases),'passed':len(cases)-len(failures),'failures':[{k:v for k,v in x.items()if k not in ('native','python')}for x in failures]},indent=2))
 return not failures
def verify_extra():
 """Reproduce the additional23 divisor and BWD-mode differential cases.

 Each result records widget values, state overrides and the shared baseline
 decoder state, so every precondition is explicit in the saved evidence.
 """
 cases=[]
 for payload in ('100000','200000','300000'):
  cases.append(compare(1039,payload))
 for query in (1010,1024,1025,1053,1062):
  for divisor in (0,1,-4,2.5):
   cases.append(compare(query,'123.5',values={(5,43):divisor,(5,28):1000,(9,9):2000}))
 failures=[case for case in cases if not case.get('pass')]
 result={'method':'Original x86 decoder extra divisor/BWD cases; Unicorn with intercepted CRT/CVI; no hardware',
         'case_count':len(cases),'passed':len(cases)-len(failures),'cases':cases}
 (ROOT/'analysis/native_decoder_extra_results.json').write_text(json.dumps(result,indent=2))
 summary={'cases':len(cases),'passed':len(cases)-len(failures),
          'failures':[{k:v for k,v in case.items()if k not in ('native','python')}for case in failures]}
 (ROOT/'analysis/native_decoder_extra_summary.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary,indent=2))
 return not failures

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--extra',action='store_true',help='Run the additional23 divisor/BWD differential cases')
 args=parser.parse_args()
 sys.exit(0 if (verify_extra() if args.extra else verify()) else 1)

