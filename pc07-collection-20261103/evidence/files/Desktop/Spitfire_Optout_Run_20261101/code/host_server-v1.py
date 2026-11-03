"""Isolated original-XP capture fixture. Only EMPOPTOUT 1 may alter RAM.
No controller forwarding, no physical I/O, and no on-disk source changes.
"""
import argparse,hashlib,http.server,json,re,socket,threading,time
from pathlib import Path
from datetime import datetime,timezone
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--values',required=True);p.add_argument('--seconds',type=int,default=2400);a=p.parse_args()
root=Path(a.root);root.mkdir(exist_ok=True);received=root/'received';received.mkdir(exist_ok=True)
raw=Path(a.values).read_bytes();values=json.loads(raw.decode('utf-8-sig'))
assert values['1068'] in ('0','1');assert values['1067']=='INT' and values['1085']=='0'
(root/'fixture-source.json').write_text(json.dumps({'source':a.values,'sha256':hashlib.sha256(raw).hexdigest(),'initial_optout':values['1068'],'policy':'queries and EMPOPTOUT1 RAM only; other mutations record-and-reject with matching synthetic ack','physical_controller':False},indent=2))
(root/'fixture-values-original.json').write_bytes(raw)
end=time.monotonic()+min(max(a.seconds,60),3600);done=threading.Event();lock=threading.Lock();sequence=0
stats={'requests':0,'responses':0,'applied_optout_on':0,'rejected_commands':0,'optout':values['1068']}
def log(kind,**data):
 with lock:
  with (root/'host-timeline.jsonl').open('a') as f:f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),kind=kind,**data))+'\n')
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);s.bind(('10.19.70.13',1024));s.settimeout(.4)
def udp():
 global sequence
 with (root/'udp-original.jsonl').open('a') as f:
  while not done.is_set() and time.monotonic()<end:
   try:data,peer=s.recvfrom(65535)
   except socket.timeout:continue
   sequence+=1;rec={'seq':sequence,'received_epoch':time.time(),'source':peer,'request_hex':data.hex(),'request_origin':'XP original Spitfire when independently matched to guest process evidence','responses_are_synthetic':True};lines=[];events=[]
   if peer!=('10.19.70.2',1024) or not data.startswith(b'Spectra-Physics:CMD_ECLIPSE,'):
    rec['rejected']='unexpected peer or envelope'
   else:
    stats['requests']+=1
    for line in data.split(b',',1)[1].decode('ascii','replace').splitlines():
     m=re.fullmatch(r'\[(\d+)\](.*)',line)
     if not m:events.append({'line':line,'action':'malformed rejected'});continue
     tag=int(m[1]);command=m[2]
     if 1000<=tag<2000:
      value=values.get(str(tag),'0');events.append({'tag':tag,'command':command,'action':'synthetic query reply','value':value,'modeled':str(tag) in values})
     elif tag==2036 and re.fullmatch(r'EMPOPTOUT\s+1\s*',command):
      before=values['1068'];values['1068']='1';stats['optout']='1';stats['applied_optout_on']+=1;value='0';events.append({'tag':tag,'command':command,'action':'authorized optout ON applied in RAM only','before':before,'after':'1'})
     elif tag>=2000:
      value='0';stats['rejected_commands']+=1;events.append({'tag':tag,'command':command,'action':'rejected no state change; matching synthetic ACK to keep original scheduler responsive'})
     else:events.append({'tag':tag,'command':command,'action':'unknown tag rejected'});continue
     lines.append('<%d>%s'%(tag,value))
    if lines:
     reply=('Spectra-Physics:REPLY_ECLIPSE:'+'\n'.join(lines)+'\n').encode('ascii');s.sendto(reply,('10.19.70.2',1024));stats['responses']+=1;rec.update(reply_hex=reply.hex(),sent_epoch=time.time())
   rec['messages']=events;f.write(json.dumps(rec)+'\n');f.flush();(root/'fixture-state.json').write_text(json.dumps(stats))
 s.close()
allowed={'bootstrap.hta','guest_driver.exe','host-isolation-proof.txt','control.txt'}
allowed_verbs={'inventory','launch','about','temperature','timing','faults','setup','exit','regensvc','close','optout_on','quit_agent','update'}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*x):pass
 def do_GET(self):
  name=self.path.split('?',1)[0].lstrip('/')
  if self.client_address[0]!='10.19.70.2' or name not in allowed:self.send_error(403);return
  path=root/name
  if not path.exists():self.send_error(404);return
  data=path.read_bytes();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
  if name!='control.txt':log('download',file=name,sha256=hashlib.sha256(data).hexdigest())
 def do_POST(self):
  name=self.path.removeprefix('/upload/');n=int(self.headers.get('Content-Length','0'))
  if self.client_address[0]!='10.19.70.2' or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',name) or not 0<=n<=12000000:self.send_error(403);return
  data=self.rfile.read(n)
  if len(data)!=n:self.send_error(400);return
  target=received/name
  try:
   with target.open('xb') as f:f.write(data)
  except FileExistsError:self.send_error(409);return
  self.send_response(200);self.end_headers();self.wfile.write(b'OK');log('upload',file=name,bytes=n,sha256=hashlib.sha256(data).hexdigest())
httpd=http.server.HTTPServer(('10.19.70.13',18979),Handler);httpd.timeout=.5
thread=threading.Thread(target=udp);thread.start();log('started',state=stats);print('READY: original-XP fixture bound .13:1024 / HTTP18979',flush=True)
try:
 while time.monotonic()<end and not (root/'STOP').exists():httpd.handle_request()
finally:
 done.set();thread.join();httpd.server_close();log('stopped',state=stats);print(json.dumps(stats),flush=True)
