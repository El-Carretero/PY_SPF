"""Extract independent portable UI drawing spec, defaults and event metadata."""
from pathlib import Path
import struct,json,re,math
from parse_uir import parse

def u32(b,p):return struct.unpack_from('>I',b,p)[0]
def zero_decode(b):
 size=u32(b,4);src=b[12:];pos=(size+7)//8;o=bytearray()
 for i in range(size):
  if src[i//8]&(1<<(i%8)):o.append(src[pos]);pos+=1
  else:o.append(0)
 assert pos==len(src)
 return bytes(o)
def pascals(b,start=64):
 out=[];i=start
 while i<len(b):
  l=b[i]
  if 1<l<180 and i+1+l<=len(b):
   s=b[i+1:i+1+l]
   if all(x in (9,10,13) or 32<=x<127 for x in s):
    s=s.decode('ascii')
    if s not in ['Arial','NIDialog','NIDialogMetaFont','Ni7seg','NISystem']:out.append(s)
    i+=l+1;continue
  i+=1
 return list(dict.fromkeys(out))
def label_info(b):
 multi=b[4:8]==b'MLbl'; foff=60 if multi else 64
 flags=b[foff]; font='MS Shell Dlg 2'
 size=struct.unpack_from('>H',b,foff+2)[0] if flags!=1 else u32(b,44 if multi else 48)
 p=foff+4
 if flags!=1:
  p+=4;n=b[p];font=b[p+1:p+1+n].decode('cp1252','replace');p=(p+n+1+3)//4*4
 if p+4>len(b):return {'text':[],'font':font,'point_size':size}
 count=u32(b,p);p+=4;text=[]
 if multi:
  for i in range(min(count,10)):
   if p>=len(b):break
   n=b[p];text.append(b[p+1:p+1+n].decode('cp1252','replace'));p+=n+1
 else:text=[b[p:p+count].decode('cp1252','replace')]
 return {'text':list(dict.fromkeys(text)),'font':font,'point_size':size,'font_flags':flags}

def drawings(it):
 b=zero_decode(bytes.fromhex(it['hex']));n=u32(b,64);off=68;out=[]
 for idx in range(n):
  l=u32(b,off);r=b[off:off+l];nc=r[4];klass=r[5:5+nc].decode();p=(5+nc+3)//4*4;count=u32(r,p);p+=4;children=[]
  for k in range(count):
   cl=u32(r,p);c=r[p:p+cl];tag=c[4:8].decode('latin-1');item={'tag':tag,'hex':c.hex()}
   if tag in ['Labl','MLbl','Cosm','LScl','RScl'] and len(c)>=48:
    t,left,bt,right=struct.unpack_from('>4h',c,20);item['rect']=[left,t,right-left,bt-t]
    item['flags']=u32(c,8);item['colors']=[u32(c,x) for x in [28,32,36,40]]
    item['strings']=pascals(c)
    if tag in ['Labl','MLbl']:
     item.update(label_info(c));item['strings']=item['text']
   if tag=='BCos' and len(c)>=48:
    t,left,bt,right=struct.unpack_from('>4h',c,24);item['rect']=[left,t,right-left,bt-t];item['colors']=[u32(c,32),u32(c,36)]
   children.append(item);p+=cl
  out.append({'drawing_index':idx,'class':klass,'children':children,'strings':list(dict.fromkeys(s for c in children for s in c.get('strings',[])))})
  off+=l
 perm=list(struct.unpack_from('>'+str(n)+'I',b,off+4))
 return out,perm

def extract(path):
 r=parse(path);ctrl={it['id']:it for it in r['cTRl']};out={'source':Path(path).name,'panels':[],'menus':[]}
 for pan in r['pANl']:
  pid=pan['id'];p=bytes.fromhex(pan['hex']);dl=next(it for it in r['DLG3'] if it['id']==pid);db=zero_decode(bytes.fromhex(dl['hex']))
  drawing,perm=drawings(dl)
  panel={'id':pid,'name':pan['name'],'title':p[196:].split(b'\0')[0].decode('cp1252'),'width':u32(p,64),'height':u32(p,60),'background':u32(db,56),'controls':[],'drawings':drawing}
  cl=bytes.fromhex(next(it for it in r['cLSt'] if it['id']==pid)['hex']);count=u32(cl,24);ids=struct.unpack_from('>'+str(count)+'I',cl,36)
  pv=bytes.fromhex(next(it for it in r['pVAl'] if it['id']==pid)['hex']);off=12
  for cid in ids:
   c=bytes.fromhex(ctrl[cid]['hex']);callback=c[51:].split(b'\0',1)[0].decode();name=c[52+len(callback):].split(b'\0',1)[0].decode();style,dtype,l=struct.unpack_from('>III',pv,off);v=pv[off+12:off+12+l];off+=(12+l+3)//4*4
   draw_index=count-1-perm[int.from_bytes(c[40:42],'big')-1]
   drawing[draw_index]['control_id']=int.from_bytes(c[40:42],'big')+1
   data={'id':int.from_bytes(c[40:42],'big')+1,'resource_id':cid,'drawing_index':draw_index,'name':name,'callback':callback,'style':style,'data_type':dtype,'local_index':int.from_bytes(c[40:42],'big'),'value_hex':v.hex()}
   if dtype==5:data['value']=v.split(b'\0',1)[0].decode('cp1252')
   elif dtype==1 and l>=4:data['value']=struct.unpack_from('>i',v)[0]
   elif dtype==3 and l>=4:data['value']=struct.unpack_from('>f',v)[0]
   if style in range(100,150) and l==16:
    vals=struct.unpack('>4f' if dtype==3 else '>4i',v);data.update(dict(zip(['value','maximum','minimum','increment'],[x if math.isfinite(x) else None for x in vals])))
   # Ring values retain original list strings in addition to raw bytes.
   if style in range(300,340):
    first=4;nn=u32(v,first+16);data['item_values']=list(struct.unpack_from('>'+str(nn)+('f' if v[first+4:first+8]==b'fLSt' else 'i'),v,first+28));second=first+u32(v,first)+4;data['items']=[s.decode('cp1252') for s in v[second+28:].split(b'\0')[:nn]];data['value']=data['item_values'][u32(v,0)]
   panel['controls'].append(data)
  assert off==len(pv)
  out['panels'].append(panel)
 for it in r.get('mITm',[]):
  b=bytes.fromhex(it['hex']);out['menus'].append({'id':it['id'],'name':b[124:148].split(b'\0')[0].decode(),'label':b[148:].split(b'\0')[0].decode(),'callback':b[40:124].split(b'\0')[0].decode()})
 return out
if __name__=='__main__':
 dest=Path('work/spitfire_python/spitfire/resources');dest.mkdir(exist_ok=True,parents=True)
 spec=extract('work/extracted/SPITFIRE.UIR');(dest/'gui_spec.json').write_text(json.dumps(spec,indent=2,allow_nan=False))
 print([(p['id'],p['title'],p['width'],p['height'],len(p['controls'])) for p in spec['panels']])
