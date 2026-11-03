"""One-guest immutable diagnostic fixture and bounded evidence transfer server.
Not a physical controller model. Does not launch the original or execute writes.
"""
import argparse, hashlib, http.server, json, re, socket, threading, time
from pathlib import Path
from datetime import datetime, timezone
p=argparse.ArgumentParser();p.add_argument('--values',required=True);p.add_argument('--root',required=True);p.add_argument('--seconds',type=int,default=900);a=p.parse_args()
root=Path(a.root).resolve();received=root/'received';received.mkdir(exist_ok=True)
source=Path(a.values);raw=source.read_bytes();values=json.loads(raw.decode('utf-8-sig'));value=values.get('1068')
if value not in ('0','1'):raise SystemExit('No valid existing Opt-out state; refusing fixture')
(root/'fixture-source.json').write_text(json.dumps({'source':str(source),'sha256':hashlib.sha256(raw).hexdigest(),'unchanged_optout':value,'immutable':True,'physical_controller':False},indent=2))
(root/'fixture-values-original.json').write_bytes(raw)
end=time.monotonic()+min(max(a.seconds,10),1800);done=threading.Event();lock=threading.Lock()
def log(kind,**data):
 with lock:
  with (root/'host-timeline.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),kind=kind,**data))+'\n')
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);s.bind(('10.19.70.13',1024));s.settimeout(.5)
def udp():
 with (root/'udp-diagnostic.jsonl').open('a') as f:
  while time.monotonic()<end and not done.is_set():
   try:data,peer=s.recvfrom(65535)
   except socket.timeout:continue
   rec={'utc':time.time(),'peer':peer,'rx_hex':data.hex(),'provenance':'diagnostic helper, not original application'}
   if peer!=('10.19.70.2',1024) or data!=b'Spectra-Physics:CMD_ECLIPSE,[1068]EMPOPTOUT?\n':rec['action']='rejected; no state changes or reply'
   else:
    reply=('Spectra-Physics:REPLY_ECLIPSE:<1068>'+value+'\n').encode('ascii');s.sendto(reply,peer);rec.update(action='immutable query response',tx_hex=reply.hex(),optout=value)
   f.write(json.dumps(rec)+'\n');f.flush()
 s.close()
allowed_get={'bootstrap.hta','bootstrap-local.hta','guest_probe.exe','host-isolation-proof.txt'}
allowed_upload={'identity.json','network.jsonl','processes.jsonl','windows.jsonl','desktop.bmp','timeline.jsonl','eligibility.json','host-isolation-proof.txt','diagnostic-tx-payload.bin','diagnostic-rx-payload.bin','bootstrap-status.txt'}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*x):pass
 def do_GET(self):
  name=self.path.split('?',1)[0].lstrip('/')
  if self.client_address[0]!='10.19.70.2' or name not in allowed_get:self.send_error(403);return
  data=(root/name).read_bytes();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','application/hta' if name.endswith('.hta') else 'application/octet-stream');self.end_headers();self.wfile.write(data);log('download',file=name,sha256=hashlib.sha256(data).hexdigest())
 def do_POST(self):
  name=self.path.removeprefix('/upload/');n=int(self.headers.get('Content-Length','0'))
  if self.client_address[0]!='10.19.70.2' or name not in allowed_upload or not 0<=n<=8000000:self.send_error(403);return
  data=self.rfile.read(n)
  if len(data)!=n:self.send_error(400);return
  target=received/name
  try:
   with target.open('xb') as f:f.write(data)
  except FileExistsError:self.send_error(409);return
  self.send_response(200);self.end_headers();self.wfile.write(b'OK');log('upload',file=name,bytes=n,sha256=hashlib.sha256(data).hexdigest())
httpd=http.server.HTTPServer(('10.19.70.13',18978),Handler);httpd.timeout=.5
thread=threading.Thread(target=udp);thread.start();log('fixture_started',optout=value,udp=s.getsockname(),http=httpd.server_address);print('READY immutable fixture; existing Opt-out='+value,flush=True)
try:
 while time.monotonic()<end and not (root/'STOP').exists():httpd.handle_request()
finally:
 done.set();thread.join();httpd.server_close();log('fixture_stopped');print('STOPPED',flush=True)
