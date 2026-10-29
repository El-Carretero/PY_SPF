from pathlib import Path
import pefile,struct,json,capstone
p=pefile.PE('work/extracted/SPITFIRE.EXE');b=p.__data__;base=p.OPTIONAL_HEADER.ImageBase
syms={x['address']:x['name'] for x in json.load(open('work/analysis/symbols.json'))}
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32);md.detail=True;md.skipdata=True

def cstr(a):
 try:v=p.get_data(a-base,200).split(b'\0')[0]
 except:return ''
 return v.decode('ascii','replace') if v and all(x in(9,10,13)or 32<=x<127 for x in v) else ''

def dis(a,z):
 out=[]
 for ins in md.disasm(p.get_data(a-base,z-a),a):
  notes=[]
  for op in (ins.operands if ins.id else []):
   a2=None
   if op.type==capstone.x86.X86_OP_IMM:a2=op.imm&0xffffffff
   elif op.type==capstone.x86.X86_OP_MEM and op.mem.base==0:a2=op.mem.disp&0xffffffff
   if a2 in syms:notes.append(syms[a2])
   elif a2 and a2>base:
    st=cstr(a2)
    if st:notes.append(repr(st))
  out.append(f'{ins.address:08x} {ins.mnemonic:8} {ins.op_str:34}'+(' ; '+', '.join(notes) if notes else ''))
 return out
cases={}
for q in range(1000,1090):
 a=struct.unpack('<I',p.get_data(0x40ad30+q*4-base,4))[0]
 title=b[0x30b70+(q-1000)*30:0x30b70+(q-1000)*30+30].split(b'\0')[0].decode('ascii','replace')
 cases[q]={'query':title,'address':a}
for q in range(2000,2007):
 a=struct.unpack('<I',p.get_data(0x409f28+q*4-base,4))[0]
 cases[q]={'query':'COMMAND'+str(q),'address':a}
starts=sorted(set(x['address'] for x in cases.values())|{0x40e38a})
for q,x in cases.items():
 if x['address']!=0x40e38a:
  z=starts[starts.index(x['address'])+1]
  x['asm']=dis(x['address'],z)
Path('work/analysis/decoder_cases.json').write_text(json.dumps(cases,indent=2))
for q,x in cases.items():
 print(q,x['query'],hex(x['address']))
 print('\n'.join(l for l in x.get('asm',[]) if ';' in l))
