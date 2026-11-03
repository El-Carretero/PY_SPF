"""Isolated XP fixture v2: logged resume; resilient UDP error handling.
Only EMPOPTOUT1 changes simulated RAM. No forwarding or physical I/O.
"""
import argparse,errno,hashlib,http.server,json,os,re,socket,threading,time
from pathlib import Path
from datetime import datetime,timezone
PREFIX=b'Spectra-Physics:CMD_ECLIPSE,'
HOST='10.19.70.13';GUEST=('10.19.70.2',1024)
POLICY='queries and EMPOPTOUT1 RAM only; other mutations record-and-reject with matching synthetic ack'
def utc():return datetime.now(timezone.utc).isoformat()
def error_info(e):return {'type':type(e).__name__,'message':str(e),'errno':getattr(e,'errno',None),'winerror':getattr(e,'winerror',None)}
def initial_stats(values):return {'requests':0,'responses':0,'applied_optout_on':0,'rejected_commands':0,'optout':values['1068']}
def make_response(data,peer,values,stats):
 """Unchanged fixture policy, producing evidence before any network send."""
 events=[];lines=[]
 if tuple(peer)!=GUEST or not data.startswith(PREFIX):return None,events,'unexpected peer or envelope'
 stats['requests']+=1
 for line in data[len(PREFIX):].decode('ascii','replace').splitlines():
  m=re.fullmatch(r'\[(\d+)\](.*)',line)
  if not m:events.append({'line':line,'action':'malformed rejected'});continue
  tag=int(m[1]);command=m[2]
  if 1000<=tag<2000:
   value=values.get(str(tag),'0');events.append({'tag':tag,'command':command,'action':'synthetic query reply','value':value,'modeled':str(tag) in values})
  elif tag==2036 and re.fullmatch(r'EMPOPTOUT\s+1\s*',command):
   before=values['1068'];values['1068']=stats['optout']='1';stats['applied_optout_on']+=1;value='0';events.append({'tag':tag,'command':command,'action':'authorized optout ON applied in RAM only','before':before,'after':'1'})
  elif tag>=2000:
   value='0';stats['rejected_commands']+=1;events.append({'tag':tag,'command':command,'action':'rejected no state change; matching synthetic ACK to keep original scheduler responsive'})
  else:events.append({'tag':tag,'command':command,'action':'unknown tag rejected'});continue
  lines.append('<%d>%s'%(tag,value))
 return (('Spectra-Physics:REPLY_ECLIPSE:'+'\n'.join(lines)+'\n').encode('ascii') if lines else None),events,None

def replay_log(path,values):
 """Recover only complete, ordered, internally consistent logged packets."""
 stats=initial_stats(values);sequence=0
 with path.open(encoding='utf-8-sig') as f:
  for number,line in enumerate(f,1):
   if not line.strip():continue
   try:
    rec=json.loads(line);seq=rec['seq']
    if not isinstance(seq,int) or seq<=sequence:raise ValueError('sequence is not strictly increasing')
    reply,events,rejected=make_response(bytes.fromhex(rec['request_hex']),rec['source'],values,stats)
    if rec.get('messages')!=events:raise ValueError('logged actions differ from replayed policy')
    if rec.get('rejected')!=rejected:raise ValueError('logged rejection differs from replayed policy')
    if 'reply_hex' in rec:
     if bytes.fromhex(rec['reply_hex'])!=reply or not isinstance(rec.get('sent_epoch'),(int,float)):raise ValueError('logged response differs from policy or lacks send time')
     stats['responses']+=1
    if 'reply_intended_hex' in rec and bytes.fromhex(rec['reply_intended_hex'])!=reply:raise ValueError('logged intended response differs from policy')
    sequence=seq
   except (ValueError,KeyError,TypeError) as e:raise ValueError('Cannot resume %s line %d: %s; original log unchanged'%(path.name,number,e)) from e
 return sequence,stats

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--values',required=True);p.add_argument('--seconds',type=int,default=2400);p.add_argument('--resume',action='store_true');a=p.parse_args()
 root=Path(a.root);root.mkdir(exist_ok=True);received=root/'received';received.mkdir(exist_ok=True)
 raw=Path(a.values).read_bytes();values=json.loads(raw.decode('utf-8-sig'))
 if values.get('1068') not in ('0','1') or values.get('1067')!='INT' or values.get('1085')!='0':raise ValueError('Fixture initial values do not meet reviewed policy')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');udp_path=root/'udp-original.jsonl';original=root/'fixture-values-original.json'
 segment={'version':2,'utc':utc(),'resume':a.resume,'server_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 if a.resume:
  if not udp_path.is_file() or not original.is_file() or not (root/'fixture-source.json').is_file():raise ValueError('Resume requires original metadata, values and UDP log')
  if original.read_bytes()!=raw:raise ValueError('Resume values differ from preserved original input')
  sequence,stats=replay_log(udp_path,values)
  segment.update(resumed_last_seq=sequence,recovered_state=dict(stats),prior_udp_log_sha256=hashlib.sha256(udp_path.read_bytes()).hexdigest(),recovery_basis='complete logged records only; no missing packet inference')
  checkpoint=root/'fixture-state.json'
  if checkpoint.exists():
   saved=checkpoint.read_bytes();archive=root/('fixture-state.before-resume-'+stamp+'.json')
   with archive.open('xb') as f:f.write(saved)
   segment.update(prior_state_snapshot_file=archive.name,prior_state_snapshot_sha256=hashlib.sha256(saved).hexdigest())
 else:
  if udp_path.exists() or original.exists() or (root/'fixture-source.json').exists():raise ValueError('Existing fixture evidence: use --resume; nothing overwritten')
  sequence=0;stats=initial_stats(values)
  (root/'fixture-source.json').write_text(json.dumps({'source':a.values,'sha256':hashlib.sha256(raw).hexdigest(),'initial_optout':values['1068'],'policy':POLICY,'physical_controller':False},indent=2),encoding='utf-8');original.write_bytes(raw)
 segment['initial_state']=dict(stats);stop=root/'STOP'
 if stop.exists():
  if not a.resume:raise ValueError('STOP marker exists; refusing fresh launch')
  archive=root/('STOP.before-resume-'+stamp);stop.rename(archive);segment['archived_stop_marker']=archive.name
 with (root/('fixture-segment-'+stamp+'.json')).open('x',encoding='utf-8') as f:json.dump(segment,f,indent=2)
 end=time.monotonic()+min(max(a.seconds,60),3600);done=threading.Event();lock=threading.Lock();failures=[]
 def log(kind,**data):
  with lock:
   with (root/'host-timeline.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(utc=utc(),kind=kind,**data))+'\n')
 def fatal(kind,e):
  detail=error_info(e);failures.append({'kind':kind,**detail});print(json.dumps({'utc':utc(),'fatal':kind,**detail}),flush=True)
  try:log(kind,error=detail,fatal=True)
  except OSError as other:print('Host error logging failed: '+str(other),flush=True)
  done.set()
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
 if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
 s.bind((HOST,1024));s.settimeout(.4)
 if os.name=='nt':
  try:s.ioctl(getattr(socket,'SIO_UDP_CONNRESET',0x9800000c),False);log('udp_connreset_disabled',value=False)
  except (OSError,ValueError) as e:log('udp_connreset_disable_failed',error=error_info(e),receive_errors_still_caught=True)
 next_snapshot=0;last_snapshot_error=None
 def snapshot(force=False):
  nonlocal next_snapshot,last_snapshot_error
  now=time.monotonic()
  if not force and now<next_snapshot:return
  next_snapshot=now+1;temporary=root/('fixture-state.json.tmp.'+str(os.getpid()))
  try:
   temporary.write_text(json.dumps(stats),encoding='utf-8');os.replace(str(temporary),str(root/'fixture-state.json'))
   if last_snapshot_error:log('state_snapshot_recovered',last_sequence=sequence)
   last_snapshot_error=None
  except OSError as e:
   detail=error_info(e)
   if detail!=last_snapshot_error:log('state_snapshot_error',error=detail,packet_log_preserved=True)
   last_snapshot_error=detail
  finally:
   try:temporary.unlink(missing_ok=True)
   except OSError:pass
 def udp():
  nonlocal sequence
  recoverable={errno.ECONNRESET,errno.ECONNREFUSED,10054,10061,10052}
  try:
   with udp_path.open('a',encoding='utf-8') as f:
    log('udp_worker_started',next_sequence=sequence+1,state=dict(stats))
    while not done.is_set() and time.monotonic()<end:
     try:data,peer=s.recvfrom(65535)
     except socket.timeout:continue
     except OSError as e:
      if getattr(e,'errno',None) in recoverable or getattr(e,'winerror',None) in recoverable:
       log('udp_receive_error',error=error_info(e),continued=True,note='recvfrom returned no datagram; no packet fabricated');continue
      raise
     sequence+=1;rec={'seq':sequence,'received_epoch':time.time(),'source':peer,'request_hex':data.hex(),'request_origin':'XP original Spitfire when independently matched to guest process evidence','responses_are_synthetic':True,'fixture_segment':stamp}
     reply,events,rejected=make_response(data,peer,values,stats);rec['messages']=events
     if rejected:rec['rejected']=rejected
     if reply is not None:
      rec['reply_intended_hex']=reply.hex()
      try:
       sent=s.sendto(reply,GUEST)
       if sent!=len(reply):raise OSError('UDP send returned %d of %d bytes'%(sent,len(reply)))
      except OSError as e:rec['reply_send_error']=error_info(e);log('udp_send_error',udp_seq=sequence,error=error_info(e),retried=False,counted_as_response=False)
      else:stats['responses']+=1;rec.update(reply_hex=reply.hex(),sent_epoch=time.time())
     f.write(json.dumps(rec)+'\n');f.flush();snapshot()
    snapshot(force=True);log('udp_worker_stopped',last_sequence=sequence,state=dict(stats))
  except Exception as e:fatal('udp_worker_failure',e)
  finally:s.close()
 allowed={'bootstrap.hta','guest_driver.exe','host-isolation-proof.txt','control.txt'}
 class Handler(http.server.BaseHTTPRequestHandler):
  def setup(self):super().setup();self.connection.settimeout(15)
  def log_message(self,*x):pass
  def send_error(self,code,message=None,explain=None):
   log('http_error',method=self.command,path=self.path,peer=self.client_address[0],status=code);super().send_error(code,message,explain)
  def serve_file(self,body):
   name=self.path.split('?',1)[0].lstrip('/')
   if self.client_address[0]!=GUEST[0] or name not in allowed:self.send_error(403);return
   path=root/name
   if not path.is_file():self.send_error(404);return
   data=path.read_bytes();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','application/hta' if name.endswith('.hta') else 'application/octet-stream');self.send_header('Cache-Control','no-store');self.end_headers()
   if body:self.wfile.write(data)
   if name!='control.txt':log('download' if body else 'head',file=name,sha256=hashlib.sha256(data).hexdigest())
  def do_GET(self):self.serve_file(True)
  def do_HEAD(self):self.serve_file(False)
  def do_POST(self):
   name=self.path.removeprefix('/upload/')
   try:n=int(self.headers.get('Content-Length','0'))
   except ValueError:self.send_error(400);return
   if self.client_address[0]!=GUEST[0] or not self.path.startswith('/upload/') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',name) or not 0<=n<=12000000:self.send_error(403);return
   data=self.rfile.read(n)
   if len(data)!=n:self.send_error(400);return
   target=received/name
   try:
    with target.open('xb') as f:f.write(data)
   except FileExistsError:self.send_error(409);return
   self.send_response(200);self.end_headers();self.wfile.write(b'OK');log('upload',file=name,bytes=n,sha256=hashlib.sha256(data).hexdigest())
 class Server(http.server.ThreadingHTTPServer):
  daemon_threads=True
  def handle_error(self,request,client_address):
   import sys
   log('http_handler_error',peer=client_address[0],error=error_info(sys.exc_info()[1]))
 try:httpd=Server((HOST,18979),Handler)
 except Exception:s.close();raise
 httpd.timeout=.5;thread=threading.Thread(target=udp,name='original-xp-udp');thread.start();log('resumed' if a.resume else 'started',state=dict(stats),segment=stamp,resumed_last_seq=segment.get('resumed_last_seq'));print('READY: original-XP fixture v2 bound .13:1024 / HTTP18979; next seq='+str(sequence+1),flush=True)
 try:
  while time.monotonic()<end and not stop.exists() and not done.is_set():
   if not thread.is_alive():fatal('udp_worker_unexpected_exit',RuntimeError('UDP worker ended while HTTP was active'));break
   httpd.handle_request()
 finally:
  done.set();thread.join(timeout=10);httpd.server_close();log('stopped',state=dict(stats),last_sequence=sequence,errors=failures);print(json.dumps({'state':stats,'last_sequence':sequence,'errors':failures}),flush=True)
 return 1 if failures else 0
if __name__=='__main__':raise SystemExit(main())
