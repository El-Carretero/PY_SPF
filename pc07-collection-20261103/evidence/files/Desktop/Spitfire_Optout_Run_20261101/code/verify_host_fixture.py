import contextlib,errno,importlib.util,io,json,socket,sys,tempfile,time
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fixture',str(Path(__file__).with_name('host_server.py')));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
real_replace=m.os.replace
with tempfile.TemporaryDirectory(prefix='spf-fixture-v2-') as d:
 root=Path(d);vals=root/'source.json';vals.write_text(json.dumps({'1068':'0','1067':'INT','1085':'0'}))
 class FakeSocket:
  def __init__(self):self.events=[ConnectionResetError(errno.ECONNRESET,'injected recv reset'),b'Spectra-Physics:CMD_ECLIPSE,[2036]EMPOPTOUT 1\n',b'Spectra-Physics:CMD_ECLIPSE,[1068]EMPOPTOUT?\n'];self.sends=0
  def bind(self,endpoint):assert endpoint==('10.19.70.13',1024)
  def settimeout(self,t):pass
  def ioctl(self,code,value):raise ValueError('injected unsupported ioctl command')
  def setsockopt(self,*args):pass
  def close(self):pass
  def recvfrom(self,n):
   if not self.events:time.sleep(.003);raise socket.timeout()
   e=self.events.pop(0)
   if isinstance(e,Exception):raise e
   return e,('10.19.70.2',1024)
  def sendto(self,data,peer):
   assert peer==('10.19.70.2',1024);self.sends+=1
   if self.sends==1:raise ConnectionResetError(errno.ECONNRESET,'injected send reset')
   return len(data)
 class FakeServer:
  def __init__(self,address,handler):self.started=time.monotonic()
  def handle_request(self):
   time.sleep(.005);p=root/'udp-original.jsonl'
   if p.exists() and len(p.read_text().splitlines())>=2:(root/'STOP').write_text('test complete')
   if time.monotonic()-self.started>3:raise RuntimeError('test timed out')
  def server_close(self):pass
 count=[0]
 def failing_replace(src,dst):
  count[0]+=1
  if count[0]==1:raise PermissionError('injected snapshot reader sharing conflict')
  real_replace(src,dst)
 with patch.object(m.socket,'socket',return_value=FakeSocket()),patch.object(m.http.server,'ThreadingHTTPServer',FakeServer),patch.object(m,'os',SimpleNamespace(name='nt',replace=failing_replace,getpid=m.os.getpid)),patch.object(sys,'argv',['host_server.py','--root',d,'--values',str(vals),'--seconds','60']),contextlib.redirect_stdout(io.StringIO()):
  rc=m.main()
 assert rc==0
 records=[json.loads(x) for x in (root/'udp-original.jsonl').read_text().splitlines()]
 assert len(records)==2 and 'reply_send_error' in records[0] and 'reply_hex' not in records[0]
 assert 'reply_hex' in records[1]
 values=json.loads(vals.read_text());seq,stats=m.replay_log(root/'udp-original.jsonl',values)
 assert seq==2 and stats=={'requests':2,'responses':1,'applied_optout_on':1,'rejected_commands':0,'optout':'1'}
 kinds=[json.loads(x)['kind'] for x in (root/'host-timeline.jsonl').read_text().splitlines()]
 assert all(x in kinds for x in ['udp_connreset_disable_failed','udp_receive_error','udp_send_error','state_snapshot_error','state_snapshot_recovered','udp_worker_stopped'])
 malformed=root/'malformed.jsonl';bad=dict(records[1]);bad['reply_hex']=b'bad'.hex();malformed.write_text(json.dumps(bad)+'\n')
 try:m.replay_log(malformed,json.loads(vals.read_text()))
 except ValueError:pass
 else:raise AssertionError('bad response was accepted')
 print(json.dumps({'test':'fixture v2 fault injection, no sockets or remote execution','passed':True,'assertions':['unsupported Windows ioctl ValueError logged and continued','receive reset logged and continued','send failure not counted as sent response','RAM ON retained despite failed send','snapshot PermissionError did not kill UDP worker','snapshot recovered','resume counts and seq reconstructed from log','tampered response refused'],'recovered_state':stats,'last_sequence':seq},indent=2))
