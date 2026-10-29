"""Connection checks remain live while optional telemetry is paused."""
from collections import Counter, defaultdict
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from spitfire_control.commands import ENVIRONMENT_POLL_IDS, FAST_POLL_IDS, FAULT_QUERY_IDS, HV_POLL_IDS
from spitfire_control.controller import LaserController
from spitfire_control.protocol import decode_command_datagram, encode_reply
from spitfire_control.transport import SimulatorTransport, UdpSettings, UdpTransport


class PollCadenceTests(unittest.TestCase):
    def setUp(self):
        self.c = LaserController(SimulatorTransport())

    def sample(self, seconds, step=.001):
        seen = defaultdict(list)
        for tick in range(round(seconds / step)):
            now = tick * step
            request = self.c._next_automatic_poll(now)
            if request:
                seen[request.command_id].append(now)
        return seen

    def test_environment_half_rate_without_speeding_up_other_queries(self):
        # Compare emitted times/counts, not internal scheduler counters.
        for monitor_hv in (False, True):
            with self.subTest(monitor_hv=monitor_hv):
                self.c = LaserController(SimulatorTransport(), monitor_hv=monitor_hv)
                seen = self.sample(20)
                normal = set(FAST_POLL_IDS + FAULT_QUERY_IDS) - set(ENVIRONMENT_POLL_IDS)
                if monitor_hv:
                    normal.update(HV_POLL_IDS)
                for cid in normal | set(ENVIRONMENT_POLL_IDS):
                    times = seen[cid]
                    period = 2 if cid in ENVIRONMENT_POLL_IDS else 1
                    self.assertAlmostEqual(len(times), 20 / period, delta=1)
                    for a, b in zip(times, times[1:]):
                        self.assertGreaterEqual(b - a + 1e-8, period)
                        self.assertLess(b - a, period * 1.04)
                if not monitor_hv:
                    self.assertFalse(set(HV_POLL_IDS) & set(seen))

    def test_custom_cycle_is_doubled_for_all_four_environment_queries(self):
        self.c = LaserController(SimulatorTransport(), poll_interval=2.5)
        seen = self.sample(25)
        for cid in ENVIRONMENT_POLL_IDS:
            self.assertEqual(len(seen[cid]), 5)
            self.assertGreaterEqual(min(b-a for a,b in zip(seen[cid], seen[cid][1:])), 5)
        self.assertEqual(len(seen[1007]), 10)

    def test_disable_and_reenable_do_not_replay_missed_polls(self):
        self.assertIsNotNone(self.c._next_automatic_poll(0))
        self.c.auto_poll = False
        for tick in range(1, 10):
            self.assertIsNone(self.c._next_automatic_poll(tick))
        self.c.auto_poll = True
        self.assertIsNotNone(self.c._next_automatic_poll(100))
        self.assertIsNone(self.c._next_automatic_poll(100))

    def test_long_scheduler_delay_does_not_catch_up_in_a_burst(self):
        self.c._next_automatic_poll(0)
        self.assertIsNotNone(self.c._next_automatic_poll(1000))
        for _ in range(10):
            self.assertIsNone(self.c._next_automatic_poll(1000))


class HeartbeatUdpTests(unittest.TestCase):
    def setUp(self):
        self.log = tempfile.TemporaryDirectory()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.settimeout(.05)
        self.stop_server = threading.Event()
        self.drop = threading.Event()
        self.sent = []
        self.server = threading.Thread(target=self.respond, daemon=True)
        self.server.start()
        self.c = LaserController(UdpTransport(UdpSettings('127.0.0.1', self.sock.getsockname()[1],
                                 '127.0.0.1', 0)), auto_poll=False, timeout=.15,
                                 log_directory=self.log.name)
        self.initial = patch('spitfire_control.controller.INITIAL_QUERY_IDS', (1000,))
        self.initial.start()

    def tearDown(self):
        self.c.stop()
        self.initial.stop()
        self.stop_server.set()
        self.server.join(1)
        self.sock.close()
        self.log.cleanup()

    def respond(self):
        while not self.stop_server.is_set():
            try:
                data, peer = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            # Single-line framing is checked by the production decoder.
            lines = decode_command_datagram(data)
            for line in lines:
                cid = line.command_id
                self.sent.append((time.monotonic(), cid))
                if not self.drop.is_set():
                    self.sock.sendto(encode_reply([(cid, 'Spitfire test controller' if cid == 1000 else '0')]), peer)

    def wait_for(self, predicate, timeout=2.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Timed out waiting for controller state')

    def test_polling_off_keeps_real_udp_link_fresh_past_stale_limit(self):
        self.c.start()
        self.wait_for(lambda: self.c.state.link_fresh())
        start = time.monotonic()
        deadline = start + self.c.state.stale_after_seconds + .6
        while time.monotonic() < deadline:
            self.assertTrue(self.c.state.link_fresh())
            time.sleep(.02)
        self.assertGreaterEqual(len(self.sent), 6)
        self.assertEqual({cid for _, cid in self.sent}, {1000, 1021, 1039, 1042, 1043, 1045, 1046})
        self.c.stop()
        self.assertFalse(self.c.state.connected)

    def test_missing_heartbeat_blocks_writes_until_fresh_recovery(self):
        self.c.start()
        self.wait_for(lambda: self.c.state.link_fresh())
        self.drop.set()
        self.wait_for(lambda: not self.c.state.connected)
        with self.assertRaises(PermissionError):
            self.c.submit(2003, 10)
        self.drop.clear()
        self.wait_for(lambda: self.c.state.link_fresh())
        self.assertFalse(any(cid >= 2000 for _, cid in self.sent))

    def test_ordinary_query_backlog_does_not_starve_connection_check(self):
        self.c.start()
        self.wait_for(lambda: self.c.state.link_fresh())
        # Keep a manual read queued after each completion, without a huge queue.
        execute = self.c._execute
        def replenish(request):
            execute(request)
            if not self.c._stop.is_set():
                try:
                    self.c.query_now((1009,))
                except PermissionError:
                    if not self.c._stop.is_set():
                        raise
        with patch.object(self.c, '_execute', side_effect=replenish):
            self.c.query_now((1009,))
            self.wait_for(lambda: Counter(cid for _, cid in self.sent)[1000] >= 2)
            self.c.stop()
        self.assertIn(1009, {cid for _, cid in self.sent})
        self.assertFalse(any(cid >= 2000 for _, cid in self.sent))
