import argparse,json,sys,time,queue
from pathlib import Path
from datetime import datetime,timezone
w=Path(__file__).resolve().parent
project=w.parent.parent/'output/Spitfire_Python_Control_1.3.1/Spitfire_Python_Control'
sys.path.insert(0,str(project/'src'))
from spitfire_control.commands import COMMANDS,format_command
from spitfire_control.profiles import query_allowed
from spitfire_control.protocol import decode_command_datagram,decode_reply_datagram
from spitfire_control.transport import UdpTransport,UdpSettings
from spitfire_control.controller import LaserController
ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--interval',type=float,choices=[0.0,0.1,0.2],required=True);ap.add_argument('--auto-poll',choices=['on','off'],default='on');args=ap.parse_args()
if not args.name.replace('_','').isalnum():raise ValueError('Invalid name')
folder=w/args.name;folder.mkdir(exist_ok=False)
allowed={cid for cid,s in COMMANDS.items() if cid<2000 and not s.writable and s.text.endswith('?') and query_allowed(cid,'external')}
packets=[];write_attempts=[]
class SocketFence:
 def __init__(self,sock):self.sock=sock
 def __getattr__(self,k):return getattr(self.sock,k)
 def sendto(self,data,dest):
  commands=decode_command_datagram(data)
  if dest!=('10.19.70.13',1024) or len(commands)!=1:raise PermissionError('Unexpected datagram')
  c=commands[0]
  if c.command_id not in allowed or c.command!=COMMANDS[c.command_id].text:
   write_attempts.append(c.command);raise PermissionError('Only exact allowlisted read commands are permitted')
  record={'utc':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic(),'cid':c.command_id,'data_hex':data.hex()};packets.append(record)
  with (folder/'tx_packets.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
  return self.sock.sendto(data,dest)
 def recvfrom(self,n):
  data,sender=self.sock.recvfrom(n)
  record={'utc':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic(),'sender':sender,'data_hex':data.hex()}
  try:record['decoded']=[{'id':r.command_id,'value':r.value} for r in decode_reply_datagram(data)]
  except Exception as exc:record['decode_error']=str(exc)
  with (folder/'rx_packets.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
  return data,sender
class GuardedTransport(UdpTransport):
 def __init__(self):super().__init__(UdpSettings(remote_host='10.19.70.13',remote_port=1024,local_host='10.19.70.1',local_port=1024));self.last_tx=None
 def connect(self):
  super().connect()
  if not isinstance(self._socket,SocketFence):self._socket=SocketFence(self._socket)
 def exchange(self,line,timeout,*,send_guard=None):
  if self.last_tx is not None:time.sleep(max(0.0,args.interval-(time.monotonic()-self.last_tx)))
  self.last_tx=time.monotonic()
  return super().exchange(line,timeout,send_guard=send_guard)
t=GuardedTransport();c=None;events=[];reason='completed';start=None
try:
 t.connect();ident=t.exchange(format_command(1000),3.0);time.sleep(1)
 if not any('Spectra' in r.value and 'SASC' in r.value for r in ident):raise RuntimeError('Identity mismatch')
 hv=t.exchange(format_command(1021),3.0)
 if len(hv)!=1 or hv[0].value.strip()!='0':raise RuntimeError('Fresh HV OFF required')
 c=LaserController(t,timeout=3.0,poll_interval=1.0,auto_poll=args.auto_poll=='on',monitor_hv=False,log_directory=str(folder),pump_mode='external')
 c.start();start=time.monotonic();last_print=0;consecutive_timeouts=0
 with (folder/'events.jsonl').open('w',encoding='utf-8') as f:
  while time.monotonic()-start<60 and c.running:
   try:
    event=c.events.get(timeout=0.2)
   except queue.Empty:continue
   record={'utc':datetime.now(timezone.utc).isoformat(),'kind':event.kind,'message':event.message};events.append(record);f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
   if event.kind=='error' and 'Timed out' in event.message:consecutive_timeouts+=1
   elif event.kind=='log' and event.message.startswith('RX '):consecutive_timeouts=0
   if c.state.high_voltage is True:reason='HV ON observed; stopped without changing output';break
   if consecutive_timeouts>=3:reason='Three consecutive timeouts';break
   if time.monotonic()-last_print>=10:
    last_print=time.monotonic();print(json.dumps({'elapsed':round(time.monotonic()-start,1),'tx':len(packets),'transport_timeouts':sum(e['kind']=='error' and 'Timed out' in e['message'] for e in events),'armed':c.state.armed}),flush=True)
except Exception as exc:reason=str(exc);print('STOP',reason,flush=True)
finally:
 if c:c.stop()
 else:t.close()
 summary={'reason':reason,'software_version':'1.3.1','scheduler':'unmodified product scheduling','auto_poll':args.auto_poll,'test_transport_min_interval':args.interval,'duration_s':time.monotonic()-start if start else 0,'packets_sent':len(packets),'write_attempts_blocked':write_attempts,'writes_sent':sum(p['cid']>=2000 for p in packets),'transport_timeouts':sum(e['kind']=='error' and 'Timed out' in e['message'] for e in events),'state_errors':sum(e['kind']=='error' for e in events),'automatic_writes_enabled':False,'all_packet_ids_below_2000':all(p['cid']<2000 for p in packets),'finished_utc':datetime.now(timezone.utc).isoformat()}
 (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
