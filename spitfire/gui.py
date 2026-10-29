"""Portable Qt preview using measured CVI bounds and original control sprites.
The Windows CVI backend is the fidelity target; this preview retains exact resource
positions and native static artwork, with Qt handling edits and events.
"""
from __future__ import annotations
import json,math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,Signal,QPoint,QEvent
from PySide6.QtGui import QColor,QPainter,QPixmap,QFont,QKeySequence,QLinearGradient
from PySide6.QtWidgets import QMainWindow,QWidget,QDialog,QInputDialog,QMenu,QApplication,QMessageBox,QLabel

from .external_ui import HIDDEN_PANELS, TITLE, apply_presentation, constrain_attribute

RESOURCE=Path(__file__).with_name('resources')
ATTR_NAMES={v['id']:k[5:].lower() for k,v in json.loads((RESOURCE/'cvi_attributes.json').read_text()).items()}
def attr_name(attr):
 return ATTR_NAMES.get(attr,str(attr)) if isinstance(attr,int) else str(attr).lower().removeprefix('attr_')
def color(value,default=0):
 value=default if value is None else int(value)
 return QColor(value>>16&255,value>>8&255,value&255)
def rect(a,prefix=''):
 return QRectF(a.get(prefix+'left',0),a.get(prefix+'top',0),max(1,a.get(prefix+'width',1)),max(1,a.get(prefix+'height',1)))
def number(v,precision=2):
 try:return f'{float(v):.{precision}f}'
 except (ValueError,TypeError):return str(v)
def font(a,prefix='text_'):
 family=a.get(prefix+'font','Arial')
 if family in ['NIDialog','NIDialogMetaFont']:family='Tahoma'
 f=QFont(family);f.setPointSizeF(max(1,a.get(prefix+'point_size',11))*0.75)
 f.setBold(bool(a.get(prefix+'bold',0)));f.setItalic(bool(a.get(prefix+'italic',0)))
 return f

class PanelWidget(QWidget):
 def __init__(self,owner,spec,parent=None):
  super().__init__(parent);self.owner=owner;self.spec=spec;self.panel_id=spec['id'];self.offset_y=0;self.attributes=dict(spec.get('attributes',{}));self.controls={};self.active=None;self.start=None
  self.setFixedSize(spec['width'],spec['height']);self.setFocusPolicy(Qt.StrongFocus);self.setMouseTracking(True)
  for c in spec['controls']:
   a=dict(c['attributes']);self.controls[c['id']]={'spec':c,'attrs':a,'value':c.get('value',0),'initial':c.get('value',0),'dirty':set(),'blank':QPixmap(str(RESOURCE/c['bitmap_blank'])) if c.get('bitmap_blank') else QPixmap(),'pixmap':QPixmap(str(RESOURCE/c['bitmap'])) if c.get('bitmap') else QPixmap(),'states':{v:QPixmap(str(RESOURCE/c[f'state_{v}'])) for v in [0,1] if c.get(f'state_{v}')}}
 def bounds(self,c):
  a=c['attrs'];b=a.get('bounding_rect',[a.get('top',0),a.get('left',0),a.get('height',1),a.get('width',1)])
  return QRectF(b[1],b[0],b[3],b[2])
 def paintEvent(self,event):
  p=QPainter(self);p.fillRect(self.rect(),color(self.attributes.get('backcolor',self.spec['background'])));p.translate(0,self.offset_y)
  for cid,c in sorted(self.controls.items(),key=lambda x:x[1]['attrs'].get('zplane_position',0),reverse=True):
   a=c['attrs'];style=a.get('ctrl_style',0)
   if not a.get('visible',1) or style==490:continue
   b=self.bounds(c);value=c['value'];initial=c['initial'];dynamic=value!=initial
   p.save()
   if a.get('dimmed'):p.setOpacity(.45)
   pm=c['states'].get(int(bool(value)),c['pixmap']) if 200<=style<290 else c['pixmap']
   if style==160 and dynamic:self.paint_text(p,c)
   else:
    if not pm.isNull() and not (200<=style<220 and {'cmd_button_color','label_text'}&c['dirty']):p.drawPixmap(b.topLeft(),pm)
    if dynamic and 100<=style<150:self.paint_numeric(p,c)
    elif 200<=style<290 and ((dynamic and not c['states']) or {'on_color','off_color'}&c['dirty']):self.paint_bool(p,c)
    elif dynamic and style in [150,151,170,171]:self.paint_string(p,c)
    elif dynamic and 300<=style<340:self.paint_ring(p,c)
   if 'cmd_button_color' in c['dirty'] and 200<=style<220:self.paint_command(p,c)
   elif 'label_text' in c['dirty']:
    if 200<=style<220:self.paint_command(p,c)
    else:self.paint_label(p,c)
   if self.active==cid and style in range(200,206):
    p.fillRect(rect(a),QColor(0,0,0,35))
   p.restore()
  p.end()
 def paint_text(self,p,c):
  a=c['attrs'];r=rect(a);bg=a.get('text_bgcolor',16777216)
  if bg!=16777216:p.fillRect(r,color(bg))
  p.setFont(font(a));p.setPen(color(a.get('text_color',0)));justify=a.get('text_justify',0)
  align=Qt.AlignVCenter|(Qt.AlignHCenter if justify==32 else Qt.AlignRight if justify==16 else Qt.AlignLeft)
  p.drawText(r,int(align),str(c['value']))
 def paint_numeric(self,p,c):
  a=c['attrs'];r=rect(a,'dig_disp_') if a.get('show_dig_disp') else rect(a)
  r.adjust(11 if a.get('show_incdec_arrows') else 3,3,-3,-3)
  p.fillRect(r,color(a.get('text_bgcolor',16777215)));p.setPen(color(a.get('text_color',0)));p.setFont(font(a))
  p.drawText(r,int(Qt.AlignVCenter|Qt.AlignRight),number(c['value'],a.get('precision',2)))
 def paint_bool(self,p,c):
  a=c['attrs'];style=a['ctrl_style'];r=rect(a)
  if 260<=style<280:
   p.setPen(color(0x555555));p.setBrush(color(a.get('on_color',0x00ff00) if c['value'] else a.get('off_color',0x303030)));p.drawEllipse(r.adjusted(2,2,-2,-2))
  elif style==226 and c['value']:
   p.setPen(color(0));p.drawLine(r.topLeft()+QPoint(2,6),r.topLeft()+QPoint(5,10));p.drawLine(r.topLeft()+QPoint(5,10),r.topLeft()+QPoint(11,2))
 def label_rect(self,c):
  a=c['attrs']
  if 'label_left' in a:return rect(a,'label_')
  drawing=self.spec['drawings'][c['spec']['drawing_index']]
  labels=[ob for ob in drawing['children'] if ob['tag']=='MLbl' and 'rect' in ob]
  if labels:return QRectF(*labels[0]['rect'])
  return rect(a)
 def paint_label(self,p,c,clear=True):
  a=c['attrs'];r=rect(a).adjusted(2,2,-2,-2) if 200<=a.get('ctrl_style',0)<220 else self.label_rect(c)
  if clear:
   bg=a.get('label_bgcolor',a.get('cmd_button_color',self.spec['background']))
   if bg==16777216:bg=self.attributes.get('backcolor',self.spec['background'])
   p.fillRect(r,color(bg))
  p.setFont(font(a,'label_'));p.setPen(color(a.get('label_color',0)));p.drawText(r,int(Qt.AlignCenter),str(a.get('label_text','')).replace('__',''))
 def paint_command(self,p,c):
  a=c['attrs'];r=rect(a)
  if not c['blank'].isNull() and a.get('cmd_button_color')==c['spec']['attributes'].get('cmd_button_color'):
   p.drawPixmap(self.bounds(c).topLeft(),c['blank']);self.paint_label(p,c,False);return
  base=color(a.get('cmd_button_color',0xd4d0c8));g=QLinearGradient(r.topLeft(),r.bottomLeft());g.setColorAt(0,base.lighter(140));g.setColorAt(.3,base);g.setColorAt(1,base.darker(140));p.setPen(base.darker(180));p.setBrush(g)
  if a['ctrl_style']==202:p.drawEllipse(r)
  else:p.drawRect(r)
  self.paint_label(p,c,False)
 def paint_string(self,p,c):
  a=c['attrs'];r=rect(a).adjusted(3,2,-3,-2);p.fillRect(r,color(a.get('text_bgcolor',16777215)));p.setFont(font(a));p.setPen(color(a.get('text_color',0)));p.drawText(r,int(Qt.AlignVCenter|Qt.AlignLeft),str(c['value']))
 def paint_ring(self,p,c):
  a=c['attrs'];r=rect(a).adjusted(3,2,-18,-2);items=c['spec'].get('items',[]);vals=c['spec'].get('item_values',[])
  try:text=items[vals.index(c['value'])]
  except (ValueError,IndexError):text=str(c['value'])
  p.fillRect(r,color(0xffffff));p.setFont(font(a));p.setPen(color(0));p.drawText(r,int(Qt.AlignVCenter|Qt.AlignLeft),text)
 def hit(self,pos):
  pos=pos-QPoint(0,self.offset_y)
  for cid,c in sorted(self.controls.items(),key=lambda x:x[1]['attrs'].get('zplane_position',0)):
   a=c['attrs']
   if a.get('visible',1) and not a.get('dimmed',0) and a.get('ctrl_mode',0) in [1,2] and self.bounds(c).contains(pos):return cid
  return None
 def emit_event(self,cid,event):
  c=self.controls[cid];name=c['spec'].get('callback','')
  if name:self.owner.callback.emit(name,c['value'],event,self.panel_id,cid)
 def mousePressEvent(self,e):
  self.setFocus();cid=self.hit(e.position());self.active=cid;self.start=e.position()
  if cid is not None:self.emit_event(cid,5 if e.button()==Qt.RightButton else 3)
  self.update()
 def mouseMoveEvent(self,e):
  if self.owner.external and self.panel_id==6 and self.active==10 and not self.bounds(self.controls[10]).contains(e.position()-QPoint(0,self.offset_y)):
   self.owner.cancel_run_hold()
  if self.active is None or self.start is None:return
  c=self.controls[self.active];a=c['attrs'];style=a.get('ctrl_style',0)
  if 100<=style<150 and a.get('ctrl_mode')==1:
   inc=a.get('incr_value',1) or 1;delta=int((self.start.y()-e.position().y())/3)
   if delta:
    v=float(c['value'])+delta*inc;v=max(a.get('min_value') or -math.inf,min(a.get('max_value') or math.inf,v));c['value']=v;self.start=e.position();self.emit_event(self.active,1);self.update()
 def mouseReleaseEvent(self,e):
  cid=self.active;self.active=None
  self.owner.mouse_released.emit()
  if cid is None:return
  c=self.controls[cid];style=c['attrs'].get('ctrl_style',0)
  if e.button()==Qt.LeftButton:
   if 220<=style<260 or 280<=style<290:c['value']=int(not c['value'])
   elif style in range(300,340):self.choose_ring(cid,e.globalPosition().toPoint());self.update();return
   self.emit_event(cid,1)
  self.update()
 def choose_ring(self,cid,point):
  c=self.controls[cid];items=c['spec'].get('items',[]);vals=c['spec'].get('item_values',list(range(len(items))));m=QMenu(self)
  for label,v in zip(items,vals):
   act=m.addAction(label);act.setData(v)
  selected=m.exec(point)
  if selected:c['value']=selected.data();self.emit_event(cid,1)
 def mouseDoubleClickEvent(self,e):
  cid=self.hit(e.position())
  if cid is None:return
  self.emit_event(cid,6 if e.button()==Qt.RightButton else 4)
  c=self.controls[cid];a=c['attrs'];style=a.get('ctrl_style',0)
  if 100<=style<150:
   lo=a.get('min_value');hi=a.get('max_value');v,ok=QInputDialog.getDouble(self,self.spec['title'],a.get('label_text',c['spec']['name']),float(c['value']),-1e12 if lo is None else lo,1e12 if hi is None else hi,max(0,a.get('precision',2)))
  elif style in [150,151,170,171]:v,ok=QInputDialog.getText(self,self.spec['title'],a.get('label_text',''),text=str(c['value']))
  else:return
  if ok:c['value']=v;self.emit_event(cid,1);self.update()
 def wheelEvent(self,e):
  cid=self.hit(e.position())
  if cid is None:return
  c=self.controls[cid];a=c['attrs']
  if 100<=a.get('ctrl_style',0)<150:
   c['value']=float(c['value'])+(1 if e.angleDelta().y()>0 else -1)*(a.get('incr_value') or 1);self.emit_event(cid,1);self.update()
 def leaveEvent(self,e):
  if self.owner.external and self.panel_id==6 and self.active==10:self.owner.cancel_run_hold()
  super().leaveEvent(e)
 def focusOutEvent(self,e):
  if self.owner.external:self.owner.cancel_run_hold()
  super().focusOutEvent(e)
 def keyPressEvent(self,e):self.owner.key_pressed.emit('\x1b' if e.key()==Qt.Key_Escape else e.text());super().keyPressEvent(e)

class SpitfireWindow(QMainWindow):
 callback=Signal(str,object,int,object,int)
 key_pressed=Signal(str)
 closing=Signal()
 mouse_released=Signal()
 def __init__(self,spec=None,*,external=True):
  super().__init__();self.external=external;self.spec=json.loads((RESOURCE/'gui_spec.json').read_text()) if spec is None else spec
  if spec is None and (RESOURCE/'server_gui_spec.json').exists():self.spec['panels'].extend(json.loads((RESOURCE/'server_gui_spec.json').read_text())['panels'])
  self.panels={};self.dialogs={};self.menu_actions={}
  for item in self.spec['panels']:
   pid=item['id']
   if self.external and pid in HIDDEN_PANELS:continue
   if pid==6:
    panel=PanelWidget(self,item);self.setCentralWidget(panel);self.setWindowTitle(item['title'])
   else:
    dialog=QDialog(self);dialog.setWindowTitle(item['title']);panel=PanelWidget(self,item,dialog);dialog.setFixedSize(panel.size());self.dialogs[pid]=dialog
   self.panels[pid]=panel
  self.make_menus();mh=self.menuBar().sizeHint().height();self.centralWidget().offset_y=-mh;self.centralWidget().setFixedHeight(self.centralWidget().height()-mh);self.setFixedSize(self.centralWidget().width(),self.centralWidget().height()+mh)
  if self.external:
   self.setWindowTitle(TITLE)
   self.external_status=QLabel(self);self.external_status.setWordWrap(True);self.external_status.setStyleSheet('background:#173d60;color:white;padding:5px;font-size:11px;')
   self.external_status.setGeometry(85,115,390,58);self.external_status.raise_()
   apply_presentation(self)
 def make_menus(self):
  structure=[('File',[(3,'E&xit','exit_from_menu')]),('View',[(5,'Timing and High Voltage','show_info'),(6,'Active Faults','show_faults'),(7,'Empower Setup','show_setup'),(8,'Temperature Control','show_ccu')]),('Help',[(10,'About','show_help')])]
  if self.external:
   structure[1][1][2]=(7,'Apply external pump opt-out','apply_external_optout')
   structure[1][1].append((11,'HV OFF','external_hv_off'))
  for name,items in structure:
   menu=self.menuBar().addMenu(name)
   for mid,label,callback in items:
    a=menu.addAction(label);a.triggered.connect(lambda checked=False,n=callback,i=mid:self.callback.emit(n,0,1,0,i));self.menu_actions[mid]=a
 def read(self,panel,control):return self.panels[panel].controls[control]['value']
 def set_value(self,panel,control,value):
  if panel in self.panels and control in self.panels[panel].controls:self.panels[panel].controls[control]['value']=value;self.panels[panel].update()
 def set_attribute(self,panel,control,attr,value):
  if panel not in self.panels or control not in self.panels[panel].controls:return
  c=self.panels[panel].controls[control];name=attr_name(attr)
  if self.external:value=constrain_attribute(panel,control,name,value)
  c['attrs'][name]=value;c['dirty'].add(name)
  if name in ['left','top','width','height']:
   a=c['attrs'];old=c['spec']['attributes'];b=list(a.get('bounding_rect',[old.get('top',0),old.get('left',0),old.get('height',1),old.get('width',1)]))
   if name=='left':b[1]+=value-old.get('left',0)
   if name=='top':b[0]+=value-old.get('top',0)
   a['bounding_rect']=b
  self.panels[panel].update()
 def set_panel_attribute(self,panel,attr,value):
  if self.external and panel in HIDDEN_PANELS:return
  if panel not in self.panels:return
  canvas=self.panels[panel];name=attr_name(attr);canvas.attributes[name]=value
  if name in ['height','width']:
   canvas.setFixedSize(canvas.attributes.get('width',canvas.width()),canvas.attributes.get('height',canvas.height())+canvas.offset_y)
   if panel==6:self.setFixedSize(canvas.width(),canvas.height()+self.menuBar().height())
   else:self.dialogs[panel].setFixedSize(canvas.size())
  if name=='visible':self.show_panel(panel,bool(value))
  canvas.update()
 def set_menu_attribute(self,panel,item,attr,value):
  if item==0:self.menuBar().setEnabled(not value if attr_name(attr)=='dimmed' else bool(value));return
  if item in self.menu_actions:
   a=self.menu_actions[item]
   if attr_name(attr)=='dimmed':a.setEnabled(not value)
   elif attr_name(attr)=='visible':a.setVisible(bool(value))
 def show_panel(self,panel,visible=True):
  if self.external and panel in HIDDEN_PANELS:visible=False
  if self.external and panel!=6 and visible:self.cancel_run_hold()
  target=self if panel==6 else self.dialogs.get(panel)
  if target:
   target.setVisible(visible)
   if visible:target.raise_()
 def cancel_run_hold(self):
  self.callback.emit('cancel_run_hold',0,1,6,10)
 def set_external_status(self,text):
  if self.external and hasattr(self,'external_status'):
   self.external_status.setText(str(text));self.external_status.setToolTip(str(text));self.external_status.raise_()
 def event(self,e):
  if getattr(self,'external',False) and e.type() in (QEvent.WindowDeactivate,QEvent.Hide):self.cancel_run_hold()
  return super().event(e)
 def read_attribute(self,panel,control,attr):return self.panels[panel].controls[control]['attrs'].get(attr_name(attr),0)
 def request_close(self):self.close()
 def show_warning(self,title,text,callback):
  QMessageBox.warning(self,title,text)
  callback()
 def show_server(self,visible=True):self.show_panel('server',visible)
 def log(self,message):pass
 def closeEvent(self,e):self.closing.emit();super().closeEvent(e)
