"""Execute selected original x86 callbacks in Unicorn with CVI calls intercepted.

No Windows binary process/network is started. This maps only the supplied PE in
an emulator, handles a small audited subset of external APIs, and stops at ret.
"""
from __future__ import annotations
from pathlib import Path
import json,re,struct,sys
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP,UC_X86_REG_ESP,UC_X86_REG_EAX

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spitfire.callbacks import dispatch
from spitfire.protocol import format_message

PANEL_GLOBALS={6:0x41417c,5:0x414180,7:0x414184,2:0x414188,9:0x41418c,
               3:0x414190,4:0x414194,8:0x41419c,1:0x4141a0}

class NativeOracle:
 def __init__(self):
  self.pe=pefile.PE(str(ROOT/'analysis/reference/SPITFIRE.EXE'))
  syms=json.loads((ROOT/'analysis/symbols.json').read_text())
  self.symbols={x['name']:x['address'] for x in syms}
 def run(self,name,values=None,*,panel=9,control=8,event=1,state=None):
  self.values=values or {};self.sent=[];self.calls=[]
  u=Uc(UC_ARCH_X86,UC_MODE_32);self.u=u
  u.mem_map(0x400000,0x50000);u.mem_write(0x400000,self.pe.get_memory_mapped_image())
  u.mem_map(0x1000000,0x100000);u.mem_map(0xf000000,0x1000)
  esp=0x10ff000
  u.mem_write(esp,struct.pack('<7I',0xf000000,panel,control,event,0,0,0));u.reg_write(UC_X86_REG_ESP,esp)
  for p,a in PANEL_GLOBALS.items():u.mem_write(a,struct.pack('<I',p))
  for key,val in (state or {}).items():u.mem_write(self.symbols['_'+key],struct.pack('<I',val))
  handlers={'_GetCtrlVal@12':self.getctrl,'_sprintf':self.sprintf,
    '_push_inside_stack':self.pushinside,'_push_outside_stack':self.pushinside}
  addrs={self.symbols[k]:(k,v) for k,v in handlers.items()}
  def hook(emu,addr,size,data):
   if addr==0xf000000:emu.emu_stop();return
   if addr in addrs:
    n,h=addrs[addr];h();return
   # Fail explicitly on an unexpected imported runtime call.
   for name,address in self.symbols.items():
    if address==addr and name.startswith('_') and addr<0x4048f8:
     raise RuntimeError('unhandled original call '+name)
  u.hook_add(UC_HOOK_CODE,hook)
  u.emu_start(self.symbols['_'+name],0xf000000,count=10000)
  return self.sent
 def stack(self,n=8):
  return struct.unpack('<'+'I'*n,self.u.mem_read(self.u.reg_read(UC_X86_REG_ESP),4*n))
 def ret(self,pop=0):
  s=self.stack(1)[0];self.u.reg_write(UC_X86_REG_EAX,0)
  self.u.reg_write(UC_X86_REG_ESP,self.u.reg_read(UC_X86_REG_ESP)+4+pop)
  self.u.reg_write(UC_X86_REG_EIP,s)
 def cstr(self,ptr):
  return bytes(self.u.mem_read(ptr,1024)).split(b'\0')[0].decode('cp1252')
 def getctrl(self):
  _,panel,control,ptr=self.stack(4)
  value=self.values.get((panel,control),0)
  self.u.mem_write(ptr,struct.pack('<f',float(value)));self.ret(12)
 def sprintf(self):
  esp=self.u.reg_read(UC_X86_REG_ESP);_,dst,fmtptr=self.stack(3);fmt=self.cstr(fmtptr)
  args=[];offset=12
  for match in re.finditer(r'%(?:[-+ #0]*\d*(?:\.\d+)?)?([sdiufxX])',fmt):
   t=match.group(1)
   if t=='f':arg=struct.unpack('<d',self.u.mem_read(esp+offset,8))[0];offset+=8
   else:
    arg=struct.unpack('<I',self.u.mem_read(esp+offset,4))[0];offset+=4
    if t=='s':arg=self.cstr(arg)
    elif t in 'di' and arg>=0x80000000:arg-=0x100000000
   args.append(arg)
  text=(fmt%tuple(args)).encode('cp1252')+b'\0';self.u.mem_write(dst,text);self.ret()
 def pushinside(self):
  _,tag=self.stack(2);parameter=self.cstr(0x416b64)
  self.sent.append(format_message(tag,parameter));self.ret()

def verify():
 oracle=NativeOracle();cases=[]
 for name,panel,ctrl in [('slidesetcurr',9,8),('SetHVCallback1',5,37),('SetHVCallback2',5,38),('HV_switch',5,39),('setbwd1',5,20),('secretcall2',8,10),('com_motor_speed',9,12),('LBOstabilitybreak',9,13)]:
  for val in (0,1,12.345):
   for connected in (0,1):
    if name=='LBOstabilitybreak':continue # integer source needs separate CVI type
    values={(panel,ctrl):val,(6,48):connected}
    native=oracle.run(name,values,panel=panel,control=ctrl)
    actions=dispatch(name,val,read=lambda p,c:values.get((p,c),0),panel=panel,control=ctrl,event=1)
    python=[format_message(a.target,a.value or '') for a in actions if a.kind in ('command','query')]
    cases.append({'callback':name,'value':val,'connected':connected,'native':native,'python':python,'pass':native==python})
 failures=[x for x in cases if not x['pass']]
 output={'method':'Unicorn x86 original callback execution with intercepted CVI I/O','case_count':len(cases),'passed':len(cases)-len(failures),'cases':cases}
 (ROOT/'analysis/native_oracle_results.json').write_text(json.dumps(output,indent=2))
 print(json.dumps({'cases':len(cases),'passed':len(cases)-len(failures),'failures':failures},indent=2))
 return not failures
def verify_extended():
 """Run all feasible bound callback paths with typed CVI I/O and GUI capture."""
 from native_callback_extended import verify as verify_callbacks
 return verify_callbacks()

if __name__=='__main__':
 sys.exit(0 if (verify_extended() if '--extended' in sys.argv else verify()) else 1)
