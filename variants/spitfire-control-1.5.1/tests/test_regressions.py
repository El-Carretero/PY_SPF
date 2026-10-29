"""Failures found by comparing the supplied 1.1.0 source with GUI 1.6.0.

Fixtures with compound replies are synthetic, not real controller captures.
"""
from datetime import datetime, timezone, timedelta
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from spitfire_control.commands import engineering_argument, format_command
from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.protocol import Reply, encode_reply
from spitfire_control.state import DeviceState, decode_delay, MODULE_QUERY_IDS
from spitfire_control.transport import BaseTransport, UdpTransport, UdpSettings, TransportError


def reply(cid, value):
    return Reply(cid, str(value), f"<{cid}>{value}")

class ControlledTransport(BaseTransport):
    name = "UDP hardware"
    def __init__(self):
        self.sent = []
        self.before_send = lambda line: None
        self.after_send = lambda line: None
        self.answers = {}
    def connect(self): pass
    def close(self): pass
    def exchange(self, line, timeout, *, send_guard=None):
        self.before_send(line)
        (send_guard or (lambda action: action()))(lambda: self.sent.append(line))
        self.after_send(line)
        cid = int(line[1:line.index(']')])
        answer = self.answers.get(cid, "OK" if cid >= 2000 else "0")
        if isinstance(answer, Exception): raise answer
        return [reply(cid, answer)]

class SchedulerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.log = tempfile.TemporaryDirectory()
        self.t = ControlledTransport()
        self.c = LaserController(self.t, auto_poll=False, timeout=.3, log_directory=self.log.name)
        self.c._state.transport_open = True
        self.c._state.connected = True
        self.c._state.apply(reply(1000, "controller"))
    def tearDown(self):
        self.c.stop()
        self.log.cleanup()
    def drain(self, limit=30):
        for _ in range(limit):
            q = self.c._urgent or self.c._commands
            if not q: return
            self.c._execute(q.popleft())
        self.fail("Unexpected unbounded readback chain")
    def test_off_never_resurrects_queued_on(self):
        self.c.submit(2027)
        self.c.submit(2016)
        self.drain()
        self.assertFalse(any(']ON' in x for x in self.t.sent))
    def test_off_cancels_pending_on_and_precedes_queued_queries(self):
        for cid in (1009, 1010, 1011): self.c.submit(cid)
        self.c.submit(2027)
        self.c.submit(2028)
        self.c.submit(2016)
        self.drain()
        self.assertEqual(self.t.sent[:2], ['[2028]OFF', '[2016]TDG:HV:OFF'])
        self.assertNotIn('[2027]ON', self.t.sent)
    def test_off_wins_between_dequeue_and_actual_send(self):
        entered, release = threading.Event(), threading.Event()
        self.c.submit(2017)
        request = self.c._commands.popleft()
        def wait_before_send(line):
            entered.set()
            if not release.wait(1): raise RuntimeError('test barrier expired')
        self.t.before_send = wait_before_send
        worker = threading.Thread(target=self.c._execute, args=(request,))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            self.c.submit(2016)
        finally:
            release.set(); worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.t.sent, [])
    def test_stop_cancels_writes_and_rejects_more_work(self):
        self.c.stop()
        with self.assertRaises(PermissionError): self.c.submit(2027)
    def test_timeout_cancels_writes_and_marks_link_unknown(self):
        self.c.submit(2027)
        self.t.answers[1030] = TransportError('Timed out')
        self.c._execute(PendingCommand(1030, None, 'test'))
        self.assertFalse(self.c.state.connected)
        self.drain()
        self.assertNotIn('[2027]ON', self.t.sent)
    def test_write_requires_verified_readback(self):
        self.c._state = DeviceState(transport_open=True)
        with self.assertRaises(PermissionError): self.c.submit(2017)
    def test_bind_does_not_confirm_connection(self):
        reached, release = threading.Event(), threading.Event()
        self.t.after_send = lambda line: (reached.set(), release.wait(1))
        self.c.start()
        try:
            self.assertTrue(reached.wait(1))
            self.assertTrue(self.c.state.transport_open)
            self.assertFalse(self.c.state.connected)
        finally:
            release.set()
    def test_hv_write_waits_for_query_even_after_ok_ack(self):
        self.c._state.apply(reply(1021, 1))
        self.c.submit(2016)
        self.c._execute(self.c._urgent.popleft())
        self.assertIsNone(self.c.state.high_voltage)
        self.t.answers[1021] = '0'
        self.drain()
        self.assertFalse(self.c.state.high_voltage)
    def test_hv_unknown_ack_preserves_unknown_until_readback(self):
        self.c._state.apply(reply(1021, 1))
        self.t.answers[2016] = 'ERROR: interlock failure'
        self.c.submit(2016)
        self.c._execute(self.c._urgent.popleft())
        self.assertIsNone(self.c.state.high_voltage)
        self.assertIn('ERROR:', self.c.state.last_error)
        self.t.answers[1021] = '1'; self.drain()
        self.assertTrue(self.c.state.high_voltage)
    def test_setpoint_queries_are_queued_without_auto_poll(self):
        self.c.submit(2003, 22)
        self.drain()
        self.assertEqual(self.t.sent, ['[2003]EMP:DIODE:CURR 22', '[1009]EMP:DIODE:CURR?'])
    def test_failed_service_write_cancels_queued_commit(self):
        self.t.answers[2038] = 'NACK: bad value'
        self.c.submit(2038, 99); self.c.submit(2045)
        self.drain()
        self.assertNotIn('[2045]EMP:SECRETSCOMT', self.t.sent)
    def test_hv_pending_is_published_before_waiting_for_ack(self):
        self.c._state.apply(reply(1021, 0)); self.c.submit(2017)
        self.t.after_send = lambda line: self.assertIsNone(self.c.state.high_voltage)
        self.c._execute(self.c._commands.popleft())
    def test_malformed_input_does_not_reach_worker(self):
        for value in ('한글', 'X' * 1500):
            with self.assertRaises(ValueError): self.c.submit(2003, value)
        self.assertEqual(self.t.sent, [])

class DecodingRegressionTests(unittest.TestCase):
    def setUp(self): self.s = DeviceState(connected=True, transport_open=True)
    def test_qsw_hz_wire_roundtrip_matches_original_factor_ten(self):
        self.assertEqual(format_command(2004, engineering_argument(2004, '1000')), '[2004]EMP:QSW:PRF 100.00')
        self.s.apply(reply(1010, '100.00'))
        self.assertEqual(self.s.value(1010), 1000)
        self.assertEqual(self.s.raw_values[1010], '100.00')
        self.assertEqual(format_command(2004, '100'), '[2004]EMP:QSW:PRF 100')
    def test_qsw_resolution_and_nonfinite_values(self):
        for value in ('nan', 'inf', '-1', '1000.01'):
            with self.assertRaises(ValueError): engineering_argument(2004, value)
        self.assertEqual(engineering_argument(2004, '1000.1'), '100.01')
    def test_compound_delay_number_and_all_flags(self):
        self.assertTrue(self.s.apply(reply(1045, 'ON NBWD NENA DELAY VALUE = 12.50')))
        self.assertEqual(self.s.value(1045), 12.5)
        d = self.s.delays[1]
        self.assertEqual((d.switch, d.bwd, d.enable), ('ON', 'NBWD', 'NENA'))
    def test_numeric_delay_never_fabricates_modes(self):
        self.assertEqual(decode_delay('12.5').value, 12.5)
        self.assertIsNone(decode_delay('12.5').switch)
    def test_malformed_delay_does_not_leave_old_measurement_valid(self):
        self.s.apply(reply(1045, '12.5'))
        self.assertFalse(self.s.apply(reply(1045, 'ON NBWD NENA garbage')))
        self.assertIsNone(self.s.value(1045))
    def test_error_ack_never_changes_hv(self):
        self.s.apply(reply(1021, 1))
        for text in ('ERROR: interlock', 'FAIL 7', 'NACK', 'unknown', '', 'OK'):
            self.s.apply(reply(2016, text))
            self.assertTrue(self.s.high_voltage)
    def test_module_led_requires_that_modules_fresh_reply(self):
        self.s.apply(reply(1000, 'identity'))
        self.assertEqual(self.s.communication_state('MAIN'), 'ok')
        for name, cid in MODULE_QUERY_IDS.items():
            self.assertEqual(self.s.communication_state(name), 'unknown')
            self.s.apply(reply(cid, 0))
            self.assertEqual(self.s.communication_state(name), 'ok')
            self.s.apply(reply(cid, 0x800))
            self.assertEqual(self.s.communication_state(name), 'fault')
    def test_stale_values_cannot_show_hv_off_or_green_module(self):
        self.s.apply(reply(1021, 0)); self.s.apply(reply(1013, 0))
        old = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.s.updated_at[1021] = self.s.updated_at[1013] = old
        self.assertIsNone(self.s.high_voltage)
        self.assertEqual(self.s.communication_state('EMPOWER'), 'unknown')
        self.s.last_reply_at = old
        self.assertFalse(self.s.link_fresh())
    def test_bad_query_does_not_refresh_a_valid_readback(self):
        self.s.apply(reply(1021, 1)); stamp = self.s.updated_at[1021]
        self.assertFalse(self.s.apply(reply(1021, 'ERROR: not available')))
        self.assertEqual(self.s.updated_at[1021], stamp)
        self.assertIsNone(self.s.high_voltage)
    def test_short_fault_reply_does_not_claim_no_faults(self):
        self.s.apply(reply(1014, '0 4 0 0'))
        self.assertFalse(self.s.apply(reply(1014, '0')))
        self.assertFalse(self.s.is_fresh(1014))
    def test_copy_does_not_share_mutable_pending_or_delay_state(self):
        self.s.pending_readbacks.add(1021)
        copy = self.s.copy(); copy.pending_readbacks.clear()
        self.assertIn(1021, self.s.pending_readbacks)

class UdpPeerRegressionTests(unittest.TestCase):
    def test_wrong_port_and_ip_and_unrelated_ids_are_ignored(self):
        remote = ('10.19.70.13', 1024)
        packets = [
            (encode_reply([(1000, 'foreign port')]), (remote[0], 1025)),
            (encode_reply([(1000, 'foreign IP')]), ('10.19.70.14', 1024)),
            (encode_reply([(1021, '0')]), remote),
            (encode_reply([(1021, '0'), (1000, 'correct')]), remote),
        ]
        class Sock:
            def bind(self, _): pass
            def setsockopt(self, *_): pass
            def sendto(self, *_): pass
            def settimeout(self, _): pass
            def recvfrom(self, _): return packets.pop(0)
            def close(self): pass
        with patch('spitfire_control.transport.socket.socket', return_value=Sock()), patch('spitfire_control.transport.socket.gethostbyname', return_value=remote[0]):
            t = UdpTransport(UdpSettings()); t.connect()
            try: result = t.exchange('[1000]*idn?', .2)
            finally: t.close()
        self.assertEqual([(r.command_id, r.value) for r in result], [(1000, 'correct')])
    def test_real_loopback_foreign_sender_cannot_answer_request(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('127.0.0.1', 0)); other.bind(('127.0.0.1', 0)); server.settimeout(1)
        t = UdpTransport(UdpSettings('127.0.0.1', server.getsockname()[1], '127.0.0.1', 0)); t.connect()
        def responder():
            _, client = server.recvfrom(2048)
            other.sendto(encode_reply([(1000, 'wrong')]), client)
            server.sendto(encode_reply([(1000, 'right')]), client)
        worker = threading.Thread(target=responder); worker.start()
        try: self.assertEqual(t.exchange('[1000]*idn?', .5)[0].value, 'right')
        finally:
            worker.join(1); t.close(); server.close(); other.close()
