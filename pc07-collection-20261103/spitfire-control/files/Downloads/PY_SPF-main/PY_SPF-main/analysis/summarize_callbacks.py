import re,json,pefile,struct
from pathlib import Path
f=json.load(open('work/analysis/functions.json'));p=pefile.PE('work/extracted/SPITFIRE.EXE');base=0x400000

def s(a):return p.get_data(a-base,300).split(b'\0')[0].decode('latin1')
def title(i):
 if 1000<=i<1090:return s(0x435570+(i-1000)*30)
 if 2000<=i<2090:return s(0x435ffc+(i-2000)*30)
 return str(i)
for name,ls in f.items():
 if not ls or int(ls[0][:8],16)<0x40ab3c or name.startswith('__imp') or name.endswith('@4'):continue
 if name.startswith(('_decode','_WriteString','_gext','_Read','_str')):continue
 pushes=[];refs=[]
 for i,l in enumerate(ls):
  if 'call' in l and '_push_' in l and i>0:
   prev=' '.join(ls[max(0,i-3):i]); vals=re.findall(r'push\s+(0x[0-9a-f]+|\d+)',prev)
   if vals:
    n=int(vals[-1],0);pushes.append((n,title(n)))
  for a in re.findall(r'\[?(0x436[0-9a-f]{3})\]?',l):
   st=s(int(a,16))
   if 1<=len(st)<200 and all(c in '\r\n\t' or 32<=ord(c)<127 for c in st):refs.append((a,st))
 print(name, 'QUEUES',pushes,'STRINGS',list(dict.fromkeys(refs)))
