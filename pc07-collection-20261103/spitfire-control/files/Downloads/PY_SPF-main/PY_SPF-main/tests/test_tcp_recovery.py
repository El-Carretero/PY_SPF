"""Static-recovery examples plus real localhost single-client TCP behavior."""
import socket
import threading
import unittest

from spitfire.tcp import TCPBridge, trim_request


class TCPParserTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            (4, 16): '1.6.0', (4, 6): 'HED', (4, 7): 'EMP',
            (4, 5): 'TDG', (4, 4): 'ECU', (4, 3): 'GUI',
            (6, 43): 1.25, (6, 42): 2.5, (5, 42): 3.75,
            (5, 41): 4.0, (6, 41): 5.125, (5, 7): 80000.0,
            (9, 8): 10.0, (9, 2): 20.5, (8, 15): 30.25, (9, 9): 40.125,
            (6, 29): 1,
        }
        self.attributes = {(6, 50, 500): 0, (6, 5, 500): 1}
        self.bridge = TCPBridge(self.values, self.attributes)

    def test_four_exact_local_queries(self):
        self.assertEqual(self.bridge.handle_data('FAULTS?'), b'1\n')
        self.assertEqual(self.bridge.handle_data('*IDN?'), b'Spectra-Physics, Spitfire, 0, 1.6.0 / HED / EMP / TDG / ECU / GUI\n')
        self.assertEqual(self.bridge.handle_data('TDG_STATUS?'), b'1.250, 2.500, 3.750, 4.000, 5.125, 0, 80000\n')
        self.assertEqual(self.bridge.handle_data('TEMP_STATUS?'), b'10.000, 20.500, 30.250, 40.125, 0\n')

    def test_dimmed_attribute_is_inverted(self):
        self.attributes[6, 50, 500] = 1
        self.attributes[6, 5, 500] = 0
        self.assertEqual(self.bridge.handle_data('FAULTS?'), b'0\n')
        self.assertEqual(self.bridge.handle_data('TDG_STATUS?').split(b', ')[5], b'1')

    def test_original_cr_then_lf_trim_order(self):
        for suffix in ('', '\r', '\n', '\n\r'):
            self.assertEqual(self.bridge.handle_data('FAULTS?' + suffix), b'1\n')
        for suffix in ('\r\n', '\n\n', ' ', '\r\r'):
            self.assertEqual(self.bridge.handle_data('FAULTS?' + suffix), b'')
        self.assertEqual(trim_request(b'FAULTS?\0ignored'), 'FAULTS?')

    def test_case_sensitive_unknown_commands_are_silent(self):
        for command in ('faults?', '*idn?', ' FAULTS?', '[1000]*idn?', 'EMP:ON', 'FAULTS?\n*IDN?'):
            self.assertEqual(self.bridge.handle_data(command), b'')

    def test_last_active_temperature_indicator_wins(self):
        self.values[6, 31] = self.values[6, 24] = self.values[6, 25] = 1
        self.assertTrue(self.bridge.handle_data('TEMP_STATUS?').endswith(b', 3\n'))
        self.values[6, 22] = 1
        self.assertTrue(self.bridge.handle_data('TEMP_STATUS?').endswith(b', 4\n'))

    def test_numeric_controls_are_promoted_from_float32(self):
        self.values[6, 43] = 16777217.0
        self.assertTrue(self.bridge.handle_data('TDG_STATUS?').startswith(b'16777216.000,'))

    def test_import_and_construction_do_not_listen(self):
        self.assertFalse(self.bridge.running)
        self.assertFalse(self.bridge.connected)
        self.assertIsNone(self.bridge.address)


class TCPServerTests(unittest.TestCase):
    def setUp(self):
        self.connected = threading.Event()
        self.disconnected = threading.Event()
        self.refused = threading.Event()
        self.events = []
        def event(kind, payload):
            self.events.append((kind, payload))
            if kind == 'connected': self.connected.set()
            if kind == 'disconnected': self.disconnected.set()
            if kind == 'refused': self.refused.set()
        self.bridge = TCPBridge({}, {(6, 50, 500): 1}, on_event=event)
        self.address = self.bridge.start('127.0.0.1', 0)
        self.client = socket.create_connection(self.address, timeout=1)
        self.client.settimeout(1)
        self.assertTrue(self.connected.wait(1))

    def tearDown(self):
        self.client.close()
        self.bridge.stop()

    def test_live_status_and_manual_transmit(self):
        self.client.sendall(b'FAULTS?\n')
        self.assertEqual(self.client.recv(100), b'0\n')
        self.assertTrue(self.bridge.send_text('manual'))
        self.assertEqual(self.client.recv(100), b'manual\n')

    def test_second_client_is_refused_without_disrupting_first(self):
        second = socket.create_connection(self.address, timeout=1)
        second.settimeout(1)
        try:
            self.assertTrue(self.refused.wait(1))
            self.assertEqual(second.recv(100), b'')
            self.client.sendall(b'FAULTS?')
            self.assertEqual(self.client.recv(100), b'0\n')
        finally:
            second.close()

    def test_disconnect_allows_next_client(self):
        self.client.close()
        self.assertTrue(self.disconnected.wait(1))
        self.connected.clear()
        self.client = socket.create_connection(self.address, timeout=1)
        self.client.settimeout(1)
        self.assertTrue(self.connected.wait(1))
        self.client.sendall(b'FAULTS?\r')
        self.assertEqual(self.client.recv(100), b'0\n')

    def test_unknown_command_has_no_response(self):
        self.client.sendall(b'EMP:ON')
        self.client.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            self.client.recv(100)
        self.client.settimeout(1)
        self.client.sendall(b'FAULTS?')
        self.assertEqual(self.client.recv(100), b'0\n')


if __name__ == '__main__':
    unittest.main()
