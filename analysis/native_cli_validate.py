import sys,time,json
sys.path.insert(0,r'Z:\workspace\work\spitfire_python')
from spitfire import native
from spitfire.__main__ import arguments
from spitfire.callbacks import access_level_actions
old_attach=native.NativeGui.attach;old_process=native.NativeGui.process_events;old_close=native.NativeGui.close
calls=[];counter=0;levels=[];panels=[]
def attach(self,c):
 old_attach(self,c);old=c.handle_callback
 def cb(*a,**kw):
  if a[0]not in ['tmr_Data_Logger','tmr_Mouse_Callback1']:calls.append(a[:5])
  return old(*a,**kw)
 c.handle_callback=cb
def process(self):
 global counter,levels,panels
 old_process(self);counter+=1
 if counter==30:
  for level in range(4):self.controller.apply(access_level_actions(level));levels.append(level)
  panels=list(self.panels)
  for p in panels:self.show_panel(p);old_process(self);self.show_panel(p,False)
  self.controller.apply(access_level_actions(0));self.show_panel(6)
  print('CLICK_READY',flush=True)
def close(self):
 c=self.controller
 proof={'callbacks':calls,'motor_stop_packets':[e[2] for e in c.events if e[1]=='TX' and '[2013]'in str(e[2])],'motor_move_packets':[e[2] for e in c.events if e[1]=='TX' and '[2009]'in str(e[2])],'connected':c.state.get('connected'),'access_levels':levels,'panels':panels,'callback_errors':[x for x in self.events if 'CVI error' in x]}
 print('PROOF',json.dumps(proof),flush=True);old_close(self);print('CLOSED',flush=True)
native.NativeGui.attach=attach;native.NativeGui.process_events=process;native.NativeGui.close=close
native.run(arguments(['--demo','--backend','native','--tcp-port','0']))
