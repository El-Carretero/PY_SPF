from pathlib import Path
import pefile,capstone,json
p=pefile.PE('work/extracted/SPITFIRE.EXE');base=p.OPTIONAL_HEADER.ImageBase
sym={x['address']:x['name'] for x in json.load(open('work/analysis/symbols.json'))}
fns=sorted(x['address'] for x in json.load(open('work/analysis/symbols.json')) if x['type']==1 and 0x401000<=x['address']<0x413148)
def cstr(a):
 try:s=p.get_data(a-base,256).split(b'\0')[0]
 except:return ''
 if s and all(x in (9,10,13) or 32<=x<127 for x in s):return s.decode()
 return ''
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32);md.detail=True;md.skipdata=True
out={}
for a,z in zip(fns,fns[1:]+[0x413148]):
 lines=[]
 for ins in md.disasm(p.get_data(a-base,z-a),a):
  ann=[]
  if ins.id:
   for op in ins.operands:
    if op.type==capstone.x86.X86_OP_IMM:
     v=op.imm&0xffffffff
     if v in sym:ann.append(sym[v])
     elif v>base:
      s=cstr(v)
      if s:ann.append(repr(s))
    if op.type==capstone.x86.X86_OP_MEM and op.mem.base==0:
     v=op.mem.disp&0xffffffff
     if v in sym:ann.append(sym[v])
  lines.append(f'{ins.address:08x} {ins.mnemonic:8} {ins.op_str:36}'+(' ; '+', '.join(ann) if ann else ''))
 out[sym[a]]=lines
Path('work/analysis/transport_functions.json').write_text(json.dumps(out,indent=2))
