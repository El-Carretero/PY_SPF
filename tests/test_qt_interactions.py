"""Real Qt input events use the independent controller and urgent OFF paths."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
try:
 from PySide6.QtCore import QPoint,Qt
 from PySide6.QtTest import QTest
 from PySide6.QtWidgets import QApplication
 from spitfire.gui import SpitfireWindow
 from spitfire.controller import Controller
 HAS_QT=True
except ImportError:HAS_QT=False

@unittest.skipUnless(HAS_QT,'optional PySide6 GUI is not installed')
class QtInteractionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.view=SpitfireWindow();self.control=Controller(self.view,demo=True,tcp_port=None,clock=lambda:0.)
  self.view.callback.connect(self.control.handle_callback);self.view.key_pressed.connect(self.control.key_pressed);self.view.mouse_released.connect(self.control.mouse_released)
  self.view.show();self.app.processEvents()
 def tearDown(self):self.control.stop();self.view.close();self.app.processEvents()
 def point(self,pid,cid):
  panel=self.view.panels[pid];a=panel.controls[cid]['attrs']
  return panel,QPoint(a['left']+a['width']//2,a['top']+a['height']//2+panel.offset_y)
 def commands(self):return [(r.tag,r.parameter)for r in (*self.control.scheduler.urgent,*self.control.scheduler.inside)]
 def test_run_hold_begins_on_left_press_and_cancels_on_release(self):
  panel,pos=self.point(6,10);QTest.mousePress(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.control.state['evnt_cmt'],1)
  QTest.mouseRelease(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.control.state['evnt_cmt'],0)
  self.assertFalse(self.control.state['left_mouse_down'])
 def test_stop_click_and_escape_stop_both_pc_channels(self):
  panel,pos=self.point(6,11);QTest.mouseClick(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.commands(),[(2019,' 1 OFF'),(2019,' 2 OFF')])
  QTest.keyClick(panel,Qt.Key_Escape)
  self.assertEqual(self.commands(),[(2019,' 1 OFF'),(2019,' 2 OFF')])
 def test_escape_without_prior_stop_requests_both_pc_off(self):
  QTest.keyClick(self.view.panels[6],Qt.Key_Escape)
  self.assertEqual(self.commands(),[(2019,' 1 OFF'),(2019,' 2 OFF')])
 def test_motor_reverse_forward_stop_and_jog_events(self):
  panel,pos=self.point(6,52);QTest.mousePress(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.commands(),[(2009,'')])
  QTest.mouseRelease(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.commands(),[(2013,'')])  # unsent motion is cancelled
  self.control.scheduler.clear();QTest.mousePress(panel,Qt.RightButton,pos=pos)
  QTest.mouseRelease(panel,Qt.RightButton,pos=pos)
  self.assertEqual(self.commands(),[(2013,'')])
  self.control.scheduler.clear();panel,pos=self.point(6,51)
  QTest.mouseClick(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.commands(),[(2012,'')])
 def test_numeric_drag_uses_same_value_and_commit_callback(self):
  panel,pos=self.point(6,43);before=self.view.read(6,43)
  QTest.mousePress(panel,Qt.LeftButton,pos=pos);QTest.mouseMove(panel,pos-QPoint(0,30));QTest.mouseRelease(panel,Qt.LeftButton,pos=pos-QPoint(0,30))
  self.assertGreater(self.view.read(6,43),before)
  self.assertTrue(self.commands())
 def test_server_console_uses_separate_panel_namespace_and_transmit_callback(self):
  from unittest.mock import patch
  self.view.show_server(True);self.app.processEvents()
  panel,pos=self.point('server',3)
  with patch('spitfire.gui.QInputDialog.getText',return_value=('hello',True)):
   QTest.mouseDClick(panel,Qt.LeftButton,pos=pos)
  self.assertEqual(self.view.read('server',2),'hello\n')
  self.assertEqual(self.view.read('server',3),'')
  self.assertEqual(self.control.values['server',2],'hello\n')
 def test_dynamic_labels_colors_and_visibility_repaint_without_value_change(self):
  panel=self.view.panels[6];self.view.set_attribute(6,45,530,1)
  self.view.set_attribute(6,45,641,'SERVICE MODE');self.view.set_attribute(6,45,880,0x008000)
  self.view.set_attribute(6,30,920,0xff0000);self.view.set_attribute(6,30,500,1)
  self.app.processEvents();panel.grab()
  self.assertEqual(self.view.read_attribute(6,45,641),'SERVICE MODE')
  self.view.set_menu_attribute(6,5,500,1)
  self.assertFalse(self.view.menu_actions[5].isEnabled())

if __name__=='__main__':unittest.main()
