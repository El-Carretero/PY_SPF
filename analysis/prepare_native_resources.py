"""Remove unresolved application callback names; retain original CVI layout/resources.
Never modifies input files. NI's per-record checksum is recalculated.
"""
from pathlib import Path
import struct,json
from parse_uir import parse

def prepare(path,destination):
 path=Path(path);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 src=bytearray(path.read_bytes());rsrc=parse(path);bindings=[]
 ctl_panels={}
 for it in rsrc.get('cLSt',[]):
  b=bytes.fromhex(it['hex']);n=struct.unpack_from('>I',b,24)[0]
  for cid in struct.unpack_from('>'+str(n)+'I',b,36):ctl_panels[cid]=it['id']
 for tag,offset,width in [('cTRl',51,None),('pANl',96,84),('mITm',40,84)]:
  for it in rsrc.get(tag,[]):
   b=bytearray.fromhex(it['hex']);end=b.index(0,offset);callback=b[offset:end].decode('ascii')
   if tag=='cTRl':
    const=b[end+1:].split(b'\0',1)[0].decode('ascii');panel=ctl_panels[it['id']]
   elif tag=='pANl':const=it['name'];panel=it['id']
   else:const=b[124:148].split(b'\0',1)[0].decode('ascii');panel=0
   if callback:bindings.append({'name':callback,'panel':panel,'control':int.from_bytes(bytes.fromhex(it['hex'])[40:42],'big')+1 if tag=='cTRl' else 0,'resource_id':it['id'],'kind':{'cTRl':'control','pANl':'panel','mITm':'menu'}[tag],'constant':const})
   if not callback:continue
   if width is None:
    tail=b[end+1:];b[offset:]=b'\0'+tail+b'\0'*(end-offset)
   else:b[offset:offset+width]=b'\0'*width
   # All framed NI UIR metadata records have body checksum and 8bit length.
   checksum=((sum(b[12:])&0xffffff)<<8)|((len(b)-12)&0xff)
   struct.pack_into('>I',b,4,checksum)
   assert len(b)==it['length']
   src[it['offset']:it['offset']+len(b)]=b
 out=destination/path.name;out.write_bytes(src)
 return out,bindings
if __name__=='__main__':
 dest=Path('work/spitfire_python/spitfire/resources');dest.mkdir(parents=True,exist_ok=True)
 allbindings={}
 for n in ['SPITFIRE','SERVER']:
  p,b=prepare('work/extracted/'+n+'.UIR',dest);allbindings[n]=b;print(p,len(b))
 (dest/'callback_bindings.json').write_text(json.dumps(allbindings,indent=2))
