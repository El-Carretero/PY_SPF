"""Bounded responder for one XP guest on VMware host-only network."""
import socket,time,json,re
from pathlib import Path
root=Path(__file__).resolve().parent
values=json.loads((root/'reply-values.json').read_text())
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
sock.bind(('10.19.70.13',1024))
sock.settimeout(.5)
end=time.monotonic()+1800
count=0
print('Virtual responder bound10.19.70.13:1024; accepts only XP10.19.70.2; no forwarding',flush=True)
with (root/'virtual-udp.jsonl').open('a',encoding='utf-8') as log:
 while time.monotonic()<end and not (root/'STOP-UDP').exists():
  try:data,peer=sock.recvfrom(4096)
  except socket.timeout:continue
  if peer[0]!='10.19.70.2':continue
  if not data.startswith(b'Spectra-Physics:CMD_ECLIPSE,'):continue
  replies=[]
  for line in data.split(b',',1)[1].decode('ascii','replace').splitlines():
   m=re.match(r'\[(\d+)\]',line)
   if m:
    tag=int(m[1]);replies.append('<'+str(tag)+'>'+values.get(str(tag),'0'))
  if not replies:continue
  reply=('Spectra-Physics:REPLY_ECLIPSE:'+'\n'.join(replies)+'\n').encode('ascii')
  sock.sendto(reply,('10.19.70.2',1024))
  log.write(json.dumps({'utc':time.time(),'source':peer,'request':data.decode('ascii','replace'),'reply':reply.decode('ascii')})+'\n');log.flush()
  count+=1
sock.close()
print('Virtual responder finished; datagrams='+str(count),flush=True)
