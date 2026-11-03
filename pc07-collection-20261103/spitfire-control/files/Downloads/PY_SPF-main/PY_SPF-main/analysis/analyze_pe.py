from pathlib import Path
import pefile, struct,json, capstone
p=pefile.PE('work/extracted/SPITFIRE.EXE'); b=p.__data__; base=p.OPTIONAL_HEADER.ImageBase

def read(addr,n=256):
 try:return p.get_data(addr-base,n)
 except:return b''

def cstr(addr):
 v=read(addr)
 v=v.split(b'\0')[0]
 if v and all(x in (9,10,13) or 32<=x<127 for x in v):return v.decode('ascii')
 return ''
symbols={}
for o in range(0x1260f,0x2e000):
 n,a,t=struct.unpack_from('<III',b,o)
 if t not in (0,1) or not base<=a<base+p.OPTIONAL_HEADER.SizeOfImage: continue
 if not base+0x16000<=n<base+0x34000: continue
 name=cstr(n)
 if name.startswith('_'):symbols[a]={'name':name,'address':a,'type':t,'offset':o}
for imp in p.DIRECTORY_ENTRY_IMPORT:
 for x in imp.imports:
  symbols[x.address]={'name':(x.name or b'').decode(),'address':x.address,'type':'import'}
Path('work/analysis/symbols.json').write_text(json.dumps(list(symbols.values()),indent=2))
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32);md.detail=True;md.skipdata=True
out=[]; funcs={}; current=None
for ins in md.disasm(p.sections[0].get_data(),base+p.sections[0].VirtualAddress):
 if ins.address in symbols:
  current=symbols[ins.address]['name'];out.append('\n'+current+':'); funcs[current]=[]
 anns=[]
 for op in (ins.operands if ins.id else []):
  if op.type==capstone.x86.X86_OP_IMM:
   a=op.imm&0xffffffff
   if a in symbols:anns.append(symbols[a]['name'])
   elif a>base:
    s=cstr(a)
    if s:anns.append(repr(s))
  elif op.type==capstone.x86.X86_OP_MEM and op.mem.base==0:
   a=op.mem.disp&0xffffffff
   if a in symbols:anns.append(symbols[a]['name'])
 line=f'{ins.address:08x} {ins.mnemonic:8} {ins.op_str:36}' + (' ; '+', '.join(anns) if anns else '')
 out.append(line)
 if current:funcs[current].append(line)
Path('work/analysis/annotated_disasm.txt').write_text('\n'.join(out))
Path('work/analysis/functions.json').write_text(json.dumps(funcs,indent=2))
print('symbols',len(symbols),'app funcs',sum(x['type']==1 and 0x1260f<=x.get('offset',0)<0x138ab for x in symbols.values()))
for x in sorted(symbols.values(),key=lambda x:x['address']):
 if 0x404800<=x['address']<=0x413200: print(hex(x['address']),x['name'])
