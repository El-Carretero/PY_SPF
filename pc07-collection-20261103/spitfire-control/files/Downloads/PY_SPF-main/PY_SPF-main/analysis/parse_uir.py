from pathlib import Path
import struct,json,re

def parse(path):
 b=Path(path).read_bytes(); mo,ms,ds,dlen=struct.unpack_from('>4I',b,16)
 base=mo+struct.unpack_from('>I',b,mo+0x2c)[0]
 n=struct.unpack_from('>I',b,base)[0]+1
 names=mo+struct.unpack_from('>I',b,mo+0x30)[0]
 result={}
 for i in range(n):
  tag,cnt,off=struct.unpack_from('>4sII',b,base+4+i*12);tag=tag.decode('ascii')
  items=[]
  for j in range(cnt+1):
   rid,no,flags,do,ptr=struct.unpack_from('>iIIII',b,base+off+j*20)
   l=struct.unpack_from('>I',b,ds+do)[0]; data=b[ds+do+4:ds+do+4+l]
   name=None if no==0xffffffff else b[names+no+1:names+no+1+b[names+no]].decode('latin-1')
   items.append({'id':rid,'name':name,'flags':flags,'offset':ds+do+4,'length':l,'hex':data.hex(),'strings':[m.group().decode('latin-1') for m in re.finditer(rb'[ -~]{4,}',data)]})
  result[tag]=items
 return result
if __name__=='__main__':
 for p in Path('work/extracted').glob('*.UIR'):
  result=parse(p); out=Path('work/analysis')/(p.stem+'_uir.json');out.write_text(json.dumps(result,indent=2))
  for tag,items in result.items():
   print(p.stem,tag,len(items))
   for it in items:
    if tag in ['pANl','cTRl','cLSt','DLG3','pVAl','pXTr','pXT2']:
     print(it['id'],it['name'],hex(it['offset']),it['length'],it['strings'])
