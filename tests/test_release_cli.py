"""Release identity, production CLI wiring and local-only diagnostic lifecycle."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spitfire import __version__
from spitfire.__main__ import MemoryView, arguments, main, make_controller


class ReleaseCLITests(unittest.TestCase):
    def test_package_and_public_release_identity(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(__version__, '1.2.0')
        self.assertIn('version = "1.2.0"', (root/'pyproject.toml').read_text())
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as finished:
            arguments(['--version'])
        self.assertEqual(finished.exception.code, 0)
        self.assertIn('PY_SPF 1.2', output.getvalue())
        self.assertIn('NI GUI 1.6.0', output.getvalue())

    def test_read_only_flag_reaches_actual_controller(self):
        opts = arguments(['--read-only', '--tcp-port', '0'])
        with patch('socket.socket', side_effect=AssertionError('CLI wiring must not connect')):
            controller = make_controller(MemoryView(), opts)
        self.assertTrue(controller.read_only)
        self.assertIsNone(controller.transport)
        self.assertEqual(controller.min_request_interval, .25)
        self.assertIsNone(opts.diagnostics_dir)

    def test_default_is_normal_control_mode(self):
        opts = arguments(['--demo', '--tcp-port', '0'])
        controller = make_controller(MemoryView(), opts)
        self.assertFalse(controller.read_only)
        self.assertEqual(controller.min_request_interval, 0)

    def test_headless_diagnostics_are_local_and_close_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch('socket.socket', side_effect=AssertionError('Demo must not contact a device')):
                with contextlib.redirect_stdout(output):
                    code = main(['--demo', '--read-only', '--headless', '--duration', '.2',
                                 '--tcp-port', '0', '--diagnostics-dir', directory])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(result['read_only'])
            self.assertEqual(result['mode'], 'simulator')
            heartbeat = json.loads((Path(directory)/'heartbeat.json').read_text())
            self.assertEqual(heartbeat['package_version'], __version__)
            self.assertEqual(heartbeat['original_ni_gui_version'], '1.6.0')
            self.assertTrue(heartbeat['closed'])
            self.assertGreater(heartbeat['loops'], 0)
            records = [json.loads(line) for line in (Path(directory)/'events.jsonl').read_text().splitlines()]
            sent = [r['payload'] for r in records if r['kind'] == 'TX']
            self.assertTrue(sent)
            self.assertTrue(all(not text.startswith('[2') for text in sent))
            self.assertTrue((Path(directory)/'stacks.txt').is_file())


if __name__ == '__main__':
    unittest.main()
