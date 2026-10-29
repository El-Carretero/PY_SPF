import json,sys,time,threading,hashlib,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
b=Path(__file__).resolve().parents[2];p=b/'output/Spitfire_Python_Control_1.3.2/Spitfire_Python_Control';w=Path(__file__).parent/'live_gui_automated_run02'
w.mkdir(exist_ok=False);sys.path.insert(0,str(p/'src'))
from spitfire_control.commands import COMMANDS,format_command
from spitfire_control.profiles import query_allowed
from spitfire_control.protocol import decode_command_datagram,decode_reply_datagram
from spitfire_control.transport import UdpTransport,UdpSettings,CommandCancelled
from spitfire_control.controller import LaserController
from spitfire_control.config import AppConfig
from spitfire_control.ui import SpitfireApp
import tkinter as tk
lock=threading.Lock();tx=[];rx=[];attempts=[];transitions=[];started=time.monotonic()
config_path=AppConfig.config_path();before=config_path.read_bytes() if config_path.exists() else None
allowed={cid for cid,s in COMMANDS.items() if cid<2000 and not s.writable and s.text.endswith('?') and query_allowed(cid,'external')}
def record(name,d):
 d={'utc':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic(),**d}
 with lock:
  with (w/(name+'.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps(d,ensure_ascii=False)+'\n')
 return d
class SocketFence:
 def __init__(self,sock):self.sock=sock
 def __getattr__(self,k):return getattr(self.sock,k)
 def sendto(self,data,dest):
  cs=decode_command_datagram(data)
  if dest!=('10.19.70.13',1024) or len(cs)!=1:raise PermissionError('Unexpected packet')
  c=cs[0]
  if c.command_id not in allowed or c.command!=COMMANDS[c.command_id].text:raise PermissionError('No hardware writes permitted')
  tx.append(record('tx_packets',{'cid':c.command_id,'data_hex':data.hex()}));return self.sock.sendto(data,dest)
 def recvfrom(self,n):
  data,sender=self.sock.recvfrom(n);rs=decode_reply_datagram(data)
  rx.append(record('rx_packets',{'sender':sender,'data_hex':data.hex(),'replies':[{'cid':r.command_id,'value':r.value} for r in rs]}));return data,sender
class QueryOnlyTransport(UdpTransport):
 def __init__(self):
  super().__init__(UdpSettings(remote_host='10.19.70.13',remote_port=1024,local_host='10.19.70.1',local_port=1024));self.last=None
 def connect(self):
  super().connect()
  if not isinstance(self._socket,SocketFence):self._socket=SocketFence(self._socket)
 def exchange(self,line,timeout,*,send_guard=None):
  cid=int(line[1:line.index(']')])
  if cid>=2000:
   if cid not in (2049,2052):raise CommandCancelled('Read-only test: all hardware writes blocked')
   def withheld():
    attempts.append(record('reset_pretransmission',{'cid':cid,'line':line,'send_time_checks_passed':True,'sent':False}))
    raise CommandCancelled('Read-only test: reset withheld after send-time checks')
   if send_guard is None:raise PermissionError('Reset test requires the production authorization guard')
   return send_guard(withheld)
  if self.last is not None:time.sleep(max(0,.2-(time.monotonic()-self.last)))
  self.last=time.monotonic();return super().exchange(line,timeout,send_guard=send_guard)
t=QueryOnlyTransport();t.connect()
ident=t.exchange(format_command(1000),3)
if not any('Spectra' in r.value and 'SASC' in r.value for r in ident):raise RuntimeError('Identity mismatch')
hv=t.exchange(format_command(1021),3)
if not any(r.command_id==1021 and r.value=='0' for r in hv):raise RuntimeError('Fresh HV OFF required')
class TestApp(SpitfireApp):
 def _make_controller(self):return LaserController(t,pump_mode='external',timeout=3,poll_interval=1,auto_poll=False,log_directory=str(w))
 def _toggle_arm(self):
  super()._toggle_arm();record('ui_actions',{'action':'toggle_arm','armed_after_callback':self.controller.state.armed})
 def _clear_faults(self):
  super()._clear_faults();record('ui_actions',{'action':'clear_faults','armed_after_callback':self.controller.state.armed})
 def close(self):
  with patch.object(AppConfig,'save'):super().close()
root=tk.Tk();app=TestApp(root,AppConfig(mode='udp',pump_mode='external',auto_poll=False,timeout_seconds=3,local_host='10.19.70.1',log_directory=str(w)))
root.title('Spitfire 1.3.2 - AUTOMATED READ-ONLY ARM TEST');root.geometry('1100x780');root.attributes('-alpha',0.0)
last=None
def observe():
 global last
 if app._closed:return
 state=app.controller.state if app.controller else app.state
 snap={'armed':state.armed,'connected':state.connected,'hv':state.high_voltage,'disarm_reason':state.disarm_reason,'button':str(app.arm_button.cget('text')),'control_status':app.control_status_text.get()}
 if snap!=last:transitions.append(record('state_transitions',snap));last=snap
 (w/'current.json').write_text(json.dumps(snap,indent=2),encoding='utf-8')
 if state.high_voltage is True:record('abort',{'reason':'HV ON observed'});app.close();return
 root.after(250,observe)
stage=0;armed_at=None;baseline_empty=None;hv_stamp=None;checks=[];result={'status':'RUNNING'}
def check(name,ok,detail=None):
 checks.append(record('checks',{'name':name,'passed':bool(ok),'detail':detail}))
 if not ok:raise AssertionError(name+': '+str(detail))
def empty_counts():
 return {cid:sum(r['cid']==cid and r['value']=='' for x in rx for r in x['replies']) for cid in (1044,1069)}
def exercise():
 global stage,armed_at,baseline_empty,hv_stamp
 try:
  if app._closed:return
  if time.monotonic()-started>70:raise TimeoutError('Targeted live GUI test deadline')
  c=app.controller
  if c is None or not c.running:root.after(100,exercise);return
  app.state=c.state;app._refresh_ui();state=c.state
  if state.high_voltage is True:raise RuntimeError('HV ON observed')
  if stage==0 and state.link_fresh() and state.high_voltage is False and all(empty_counts().values()):
   with patch('spitfire_control.ui.messagebox.showwarning') as warning,patch('spitfire_control.ui.messagebox.askyesno') as confirm:
    app._clear_faults()
    check('Disarmed reset gives ARM reason',warning.called and 'ARM control' in warning.call_args.args[1])
    check('Disarmed reset does not confirm',not confirm.called)
   check('Disarmed button action is ARM',app.arm_button.cget('text')=='ARM')
   app.arm_button.invoke();check('ARM callback accepts live connection',c.state.armed)
   check('Armed button action is DISARM',app.arm_button.cget('text')=='DISARM')
   armed_at=time.monotonic();baseline_empty=empty_counts();stage=1
  elif stage==1:
   check_arm=c.state.armed
   if not check_arm:raise RuntimeError('ARM lost during live hold: '+c.state.disarm_reason)
   if time.monotonic()-armed_at>=6 and all(empty_counts()[cid]>baseline_empty[cid] for cid in (1044,1069)):
    check('ARM retained across fresh empty 1044 and 1069',True,{'seconds':time.monotonic()-armed_at,'empty_counts':empty_counts()})
    check('Output remains blocked',bool(c.state.external_enable_reason()),c.state.external_enable_reason())
    hv_stamp=state.updated_at.get(1021)
    app._query((1021,));stage='refresh_hv'
  elif stage=='refresh_hv':
   if not c.state.armed:raise RuntimeError('ARM lost before reset preflight: '+c.state.disarm_reason)
   if state.high_voltage is False and state.updated_at.get(1021)!=hv_stamp:
    check('HV OFF explicitly refreshed before reset',True,str(state.updated_at.get(1021)))
    with patch('spitfire_control.ui.messagebox.askyesno',return_value=True) as confirm,patch('spitfire_control.ui.messagebox.showwarning') as warning:
     app._clear_faults()
     check('Clear Faults reaches confirmation',confirm.called,str(warning.call_args))
     check('Clear Faults avoids repeated ARM warning',not warning.called)
    stage=2
  elif stage==2 and len(attempts)>=2:
   check('Both reset requests pass real send-time guards',[x['cid'] for x in attempts]==[2049,2052])
   check('No hardware write packets',all(x['cid']<2000 for x in tx))
   check('ARM retained after withheld reset requests',c.state.armed)
   app.state=c.state;app._refresh_ui();app.arm_button.invoke()
   check('Manual DISARM works',not c.state.armed)
   check('DISARM reason shown','Disarmed by operator' in app.control_status_text.get())
   check('Button returns to ARM',app.arm_button.cget('text')=='ARM')
   result.update(status='PASS',arm_hold_seconds=time.monotonic()-armed_at);app.close();return
  root.after(100,exercise)
 except Exception as exc:
  result.update(status='FAIL',error=str(exc));record('test_error',{'message':str(exc)});app.close()
root.after(300,observe);root.after(500,exercise);root.after(75000,app.close)
try:root.mainloop()
finally:
 if app.controller:app.controller.stop()
 else:t.close()
 after=config_path.read_bytes() if config_path.exists() else None
 summary={'targeted_gui_result':result,'checks':checks,'version':'1.3.2','actual_hardware_writes':sum(x['cid']>=2000 for x in tx),'query_packets':len(tx),'reset_requests_withheld':attempts,'hv_values':[r['value'] for x in rx for r in x['replies'] if r['cid']==1021],'empty_required_replies':sum(r['cid'] in (1044,1069) and r['value']=='' for x in rx for r in x['replies']),'settings_unchanged':before==after,'duration_seconds':time.monotonic()-started,'query_test_min_interval_seconds':.2,'product_scheduler_changed':False,'final_armed':app.controller.state.armed if app.controller else False}
 (w/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
