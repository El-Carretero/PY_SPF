from pathlib import Path
import pefile,struct,re,json
p=next(Path('work/extracted').glob('cvirte.dll*'));b=p.read_bytes();pe=pefile.PE(data=b);base=pe.OPTIONAL_HEADER.ImageBase
out={}
for m in re.finditer(rb'ATTR_[A-Z0-9_]+\x00',b):
 name=m.group()[:-1].decode();va=base+pe.get_rva_from_offset(m.start());needle=struct.pack('<I',va);off=0
 while True:
  off=b.find(needle,off)
  if off<0:break
  vals=struct.unpack_from('<6I',b,off)
  if vals[1]<100000 and vals[2]<10:
   out[name]={'id':vals[1],'type':vals[2],'words':list(vals[3:])}
  off+=1
Path('work/analysis/cvi_attributes.json').write_text(json.dumps(out,indent=2))
print(len(out))
for k,v in out.items(): print(k,v)
