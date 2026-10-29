"""Compare portable initial rendering with the captured original CVI runtime.
Menu bar text is platform-native Qt; the CVI panel image is the comparison area.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from pathlib import Path
try:
 from PySide6.QtWidgets import QApplication
 from PySide6.QtGui import QImage
 from spitfire.gui import SpitfireWindow,RESOURCE
 HAS_QT=True
except ImportError:HAS_QT=False

@unittest.skipUnless(HAS_QT,'optional PySide6 GUI is not installed')
class OriginalRuntimeSnapshotTests(unittest.TestCase):
 def test_initial_panel_matches_original_native_control_artwork(self):
  app=QApplication.instance() or QApplication([]);window=SpitfireWindow(external=False)
  try:
   window.show();app.processEvents()
   actual=window.grab().toImage().convertToFormat(QImage.Format_ARGB32)
   reference=QImage(str(RESOURCE/'native_main_reference.png')).convertToFormat(QImage.Format_ARGB32)
   self.assertEqual(actual.size(),reference.size())
   a=bytes(actual.bits());b=bytes(reference.bits());offset=reference.bytesPerLine()*20
   same=sum(a[i:i+4]==b[i:i+4] for i in range(offset,len(a),4))
   fraction=same/((reference.height()-20)*reference.width())
   self.assertGreater(fraction,.99,f'Native panel matching pixels: {fraction:.5%}')
  finally:window.close();app.processEvents()

if __name__=='__main__':unittest.main()
