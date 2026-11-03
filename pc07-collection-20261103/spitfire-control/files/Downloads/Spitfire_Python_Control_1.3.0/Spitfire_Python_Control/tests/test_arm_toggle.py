"""ARM click handler tests using real controller authorization, without a display."""
import tempfile
import unittest
from unittest.mock import Mock, patch

from spitfire_control.config import AppConfig
from spitfire_control.controller import LaserController
from spitfire_control.protocol import Reply
from spitfire_control.transport import SimulatorTransport
from spitfire_control.ui import SpitfireApp


class HardwareSimulator(SimulatorTransport):
    name = 'UDP hardware'


class ArmToggleTests(unittest.TestCase):
    def setUp(self):
        self.logs = tempfile.TemporaryDirectory()
        self.c = LaserController(HardwareSimulator(), auto_poll=False, log_directory=self.logs.name)
        self.app = SpitfireApp.__new__(SpitfireApp)
        self.app.root = Mock()
        self.app.controller = self.c
        self.app.config = AppConfig(mode='udp')
        self.app.state = self.c.state
        self.app._refresh_ui = Mock()
        self.app._append_log = Mock()

    def tearDown(self):
        self.c.stop()
        self.logs.cleanup()

    def live(self):
        self.c._state.connected = self.c._state.transport_open = True
        self.c._state.apply(Reply(1000, 'Spitfire', '<1000>Spitfire'))

    def test_default_disarm_and_two_clicks_toggle_without_phrase_or_write(self):
        self.assertFalse(self.c.state.armed)
        self.live()
        with patch('spitfire_control.ui.simpledialog.askstring') as prompt:
            self.app._toggle_arm()
            self.assertTrue(self.c.state.armed)
            self.assertTrue(self.app.state.armed)
            self.app._toggle_arm()
            self.assertFalse(self.c.state.armed)
            self.assertFalse(self.app.state.armed)
            prompt.assert_not_called()
        self.assertFalse(self.c._commands)
        self.assertFalse(self.c._urgent)

    def test_disarm_click_cancels_already_queued_writes(self):
        self.live()
        self.app._toggle_arm()
        self.c.submit(2027)
        self.app._toggle_arm()
        self.assertFalse(self.c._commands)
        with self.assertRaises(PermissionError):
            self.c.submit(2027)

    def test_stale_gui_state_does_not_reverse_click_direction(self):
        self.live()
        self.c.arm(True)
        self.assertFalse(self.app.state.armed)
        self.app._toggle_arm()
        self.assertFalse(self.c.state.armed)

    def test_unverified_connection_cannot_arm(self):
        with patch('spitfire_control.ui.messagebox.showwarning') as warning:
            self.app._toggle_arm()
            warning.assert_called_once()
        self.assertFalse(self.c.state.armed)
        self.assertFalse(self.app.state.armed)

    def test_disconnect_immediately_clears_the_displayed_arm_state(self):
        self.live()
        self.app._toggle_arm()
        self.app.connection_indicator = Mock()
        self.app.connection_text = Mock()
        self.app.disconnect()
        self.assertFalse(self.app.state.armed)
        self.assertFalse(self.app.state.connected)
        self.app._refresh_ui.assert_called()
