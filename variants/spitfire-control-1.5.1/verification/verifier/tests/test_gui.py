"""Tk workflow tests; run with a desktop, or xvfb-run on Linux."""
import json
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from dataclasses import asdict
from spitfire_twin_verifier.app import VerifierApp
from spitfire_twin_verifier.config import AppConfig
from spitfire_twin_verifier.records import Transaction
from test_compare import tx

@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform == 'win32', 'Tk display required')
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=tk.Tk();self.root.withdraw()
        self.app=VerifierApp(self.root,AppConfig())
        self.app.output_directory.set(self.temp.name)
    def tearDown(self):
        if self.app.server:self.app.server.stop()
        for job in self.root.tk.call('after','info'):
            self.root.after_cancel(job)
        self.root.destroy();self.temp.cleanup()
    def add(self,item):
        data=asdict(item);data.pop('sequence');data.pop('session_id')
        self.app.capture.add_transaction(**data)
    def add_pair(self):
        self.add(tx(1,self.app.original_label.get(),1000,'*idn?',response='ID'))
        self.add(tx(2,self.app.python_label.get(),1000,'*idn?',response='ID'))

    def test_export_refreshes_cached_result(self):
        self.add_pair();self.app.generate_comparison()
        self.assertEqual(self.app.latest_result.verdict,'MATCH')
        self.add(tx(3,self.app.python_label.get(),2005,'EMP:ON'))
        with patch('spitfire_twin_verifier.app.messagebox.askyesno',return_value=False):
            self.app.export_report()
        report=json.loads(next(Path(self.temp.name).glob('comparison_*/report.json')).read_text(encoding='utf-8'))
        self.assertEqual(report['comparison']['verdict'],'DIFFERENT')
        self.assertEqual(report['metadata']['snapshot_transactions'],3)

    def test_old_events_are_ignored_after_clear(self):
        self.add_pair();self.app.clear_capture()
        self.add(tx(3,self.app.python_label.get(),1000,'*idn?'))
        self.app._poll_events()
        self.assertEqual(len(self.app.traffic_tree.get_children()),1)
        self.assertEqual(len(self.app.capture.transactions()),1)

    def test_protocol_errors_are_visible(self):
        self.app.capture.message('PROTOCOL','bad packet',client_label='XP')
        self.app._poll_events()
        self.assertIn('bad packet',self.app.diagnostics.get('1.0','end'))
        self.assertIn('PROTOCOL',self.app.compare_summary.get())

    def test_profile_and_request_loss_controls_are_saved(self):
        self.app.inject_id.set('2004');self.app.inject_request_drop.set(True)
        self.app.inject_delay.set('125');self.app.apply_profile()
        profile=self.app.device.get_profile()
        self.assertIn(2004,profile.request_drop_ids)
        self.assertEqual(profile.delay_ms[2004],125)
        self.assertEqual(self.app.capture.snapshot().metadata['response_profile']['request_drop_ids'],[2004])
        self.app.clear_profile()
        self.assertFalse(self.app.device.get_profile().request_drop_ids)

    def test_scenario_and_observation_export(self):
        self.app.start_scenario();self.add_pair()
        self.app.observation_original.set('1250 Hz');self.app.observation_python.set('1250 Hz')
        self.app.record_observation();self.app.finish_scenario()
        with patch('spitfire_twin_verifier.app.messagebox.askyesno',return_value=False):self.app.export_report()
        report=json.loads(next(Path(self.temp.name).glob('comparison_*/report.json')).read_text(encoding='utf-8'))
        self.assertEqual(report['comparison']['gui_verdict'],'MANUAL_MATCH')
        self.assertEqual(len(report['metadata']['ui_observations']),1)

    def test_demo_runs_inside_application(self):
        self.app.run_demo()
        self.app._poll_events();self.app.generate_comparison()
        self.assertEqual(len(self.app.capture.transactions()),18)
        self.assertEqual(self.app.latest_result.verdict,'MATCH')

if __name__=='__main__':unittest.main()
