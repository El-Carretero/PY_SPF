from pathlib import Path
from PIL import Image
import json,math,sys
root=Path('work/spitfire_python/spitfire/resources');spec=json.loads((root/'gui_spec.json').read_text());export=Path(sys.argv[1] if len(sys.argv)>1 else 'work/runtime/gui_export');native=json.load(open(export/'gui_attributes.json'));assets=root/'sprites';assets.mkdir(exist_ok=True)
def clean(x):
 if isinstance(x,float) and not math.isfinite(x):return None
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 return x
for panel in spec['panels']:
 raw=next(x for x in native['panels'] if x['id']==panel['id']);panel['attributes']=clean(raw['attributes']);panel['background']=raw['attributes']['backcolor']
 for c in panel['controls']:
  item=next(x for x in raw['controls'] if x['id']==c['id']);c['attributes']=clean(item['attributes']);c['value']=c['attributes'].get('value',c.get('value',0))
  for key,name in [('bitmap',item.get('bitmap'))]+[(f'state_{k}',v) for k,v in item.get('state_bitmaps',{}).items()]:
   if not name:continue
   im=Image.open(export/name).convert('RGBA');bg=panel['background'];rgb=(bg>>16&255,bg>>8&255,bg&255)
   data=im.getdata();im.putdata([(r,g,b,0 if (r,g,b)==rgb else a) for r,g,b,a in data]);out=Path(name).with_suffix('.png').name;im.save(assets/out);c[key]='sprites/'+out
(root/'gui_spec.json').write_text(json.dumps(clean(spec),indent=2,allow_nan=False))
(root/'cvi_attributes.json').write_text(Path('work/analysis/cvi_attributes.json').read_text())
print('merged controls',sum(len(x['controls']) for x in spec['panels']))
