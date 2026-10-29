"""Headless tests of actual GUI handlers (no claim of visual/DPI validation)."""
from dataclasses import asdict
import json
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from spitfire_twin_verifier.app import VerifierApp
from spitfire_twin_verifier.model import VirtualSpitfire
from spitfire_twin_verifier.records import CaptureStore
from test_compare import tx

class Value:
    def __init__(self,value=''):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value
class Tree:
    def __init__(self):self.rows=[]
    def get_children(self):return tuple(range(len(self.rows)))
    def delete(self,*args):self.rows.clear()
    def configure(self,**kwargs):pass
    def insert(self,*args,**kwargs):self.rows.append(kwargs);return str(len(self.rows))
    def see(self,*args):pass
class Text:
    def __init__(self):self.text=''
    def configure(self,**kwargs):pass
    def insert(self,index,text):self.text+=text
    def delete(self,*args):self.text=''
    def see(self,*args):pass

class GuiHandlerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app=VerifierApp.__new__(VerifierApp)
        self.app=app
        app.root=SimpleNamespace(after=lambda *args:None)
        app.capture=CaptureStore();app.device=VirtualSpitfire();app.server=None;app.latest_result=None
        app.event_queue=queue.Queue();app.capture.add_listener(app.event_queue.put)
        app._traffic_items={};app._client_keys={}
        app.traffic_tree=Tree();app.compare_tree=Tree();app.state_tree=Tree();app.state_client_box=Tree();app.diagnostics=Text()
        for name,value in {'original_label':'XP','python_label':'PY','output_directory':self.tmp.name,'ignore_polling':True,
                           'compare_summary':'','state_client':'','original_status':'','python_status':'','capture_summary':'',
                           'scenario_name':'Q-switch','scenario_status':'','observation_field':'frequency','observation_expected':'1250 Hz',
                           'observation_original':'1250 Hz','observation_python':'1250 Hz','observation_notes':'',
                           'inject_id':'2004','inject_delay':'100','inject_value':'','inject_error':False,'inject_drop':False,
                           'inject_request_drop':True,'inject_crlf':False,'inject_bad_header':False,'profile_summary':''}.items():
            setattr(app,name,Value(value))
    def tearDown(self):self.tmp.cleanup()
    def add(self,item):
        fields=asdict(item);fields.pop('sequence');fields.pop('session_id');self.app.capture.add_transaction(**fields)
    def pair(self):
        self.add(tx(1,'XP',1000,'*idn?'));self.add(tx(2,'PY',1000,'*idn?'))

    def test_export_handler_refreshes_result(self):
        self.pair();self.app.generate_comparison()
        self.add(tx(3,'PY',2005,'EMP:ON'))
        with patch('spitfire_twin_verifier.app.messagebox.askyesno',return_value=False):self.app.export_report()
        data=json.loads(next(Path(self.tmp.name).glob('comparison_*/report.json')).read_text())
        self.assertEqual(data['comparison']['verdict'],'DIFFERENT')
        self.assertEqual(data['metadata']['snapshot_transactions'],3)

    def test_clear_handler_filters_old_events_and_keeps_new_events(self):
        self.pair();self.app.clear_capture()
        self.add(tx(3,'PY',1000,'*idn?'));self.app._poll_events()
        self.assertEqual(len(self.app.traffic_tree.rows),1)

    def test_protocol_diagnostic_handler_displays_error(self):
        self.app.capture.message('PROTOCOL','bad packet',client_label='PY');self.app._poll_events()
        self.assertIn('bad packet',self.app.diagnostics.text)
        self.assertIn('PROTOCOL',self.app.compare_summary.get())

    def test_profile_handler_persists_full_conditions(self):
        self.app.apply_profile()
        p=self.app.capture.snapshot().metadata['response_profile']
        self.assertEqual(p['request_drop_ids'],[2004]);self.assertEqual(p['delay_ms'],{2004:100})
        self.app.clear_profile();self.assertFalse(self.app.device.get_profile().request_drop_ids)

    def test_observation_handler_persists_values(self):
        self.app.start_scenario();self.app.record_observation();self.pair();self.app.finish_scenario()
        self.app.generate_comparison()
        self.assertEqual(self.app.latest_result.gui_verdict,'MANUAL_MATCH')
        self.assertEqual(self.app.capture.snapshot().metadata['ui_observations'][0]['expected'],'1250 Hz')

if __name__=='__main__':unittest.main()
