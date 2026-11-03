import socket
import threading
import unittest
from emulator import (BinaryClient, BinaryServer, CAPTURED, EmpowerPeer,
                      FrameBuffer, JsonLog, SpitfireBridge, commands, decode,
                      parse_response, serve_udp)


class PeerTests(unittest.TestCase):
    def test_all_capture_templates_have_valid_checksums_and_length(self):
        for name, raw in CAPTURED.items():
            with self.subTest(name=name):
                self.assertEqual(decode(raw).raw, raw)

    def test_exact_captured_firmware_reply(self):
        self.assertEqual(EmpowerPeer().handle(bytes.fromhex('10 02 00 00 08 42 02 5e')), CAPTURED['firmware'])

    def test_exact_captured_stopped_status(self):
        self.assertEqual(EmpowerPeer().handle(bytes.fromhex('10 02 00 00 08 02 02 1e')), CAPTURED['stop'])

    def test_initial_qswitch_service_lbo_power_replies_match_capture(self):
        peer = EmpowerPeer()
        for request, name in [(commands.query_qswitch(), 'qswitch'),
                              (commands.service_read(), 'service'),
                              (commands.query_lbo(), 'lbo'),
                              (commands.query_power(), 'power')]:
            self.assertEqual(peer.handle(request), CAPTURED[name])

    def test_fault_reset_preserves_recorded_current_fault(self):
        for profile in ('key-fault', 'communication-fault'):
            peer = EmpowerPeer(profile)
            self.assertEqual(peer.handle(commands.reset_faults()), CAPTURED['reset'])
            self.assertEqual(peer.handle(commands.query_status()), CAPTURED[profile])

    def test_corrupted_packet_does_not_mutate_state(self):
        peer = EmpowerPeer()
        raw = bytearray(commands.set_run(True));raw[-1] ^= 1
        self.assertIsNone(peer.handle(bytes(raw)))
        self.assertEqual(peer.handle(commands.query_status()), CAPTURED['stop'])

    def test_stream_fragmentation_noise_and_checksum_recovery(self):
        parser = FrameBuffer(verify_checksum=True)
        packet = commands.query_status()
        self.assertEqual(parser.feed(b'noise' + packet[:3]), [])
        self.assertEqual(parser.feed(packet[3:])[0].raw, packet)
        broken = packet[:-1] + bytes([packet[-1] ^ 1])
        self.assertEqual(parser.feed(broken + packet)[0].raw, packet)
        self.assertEqual(parser.rejected, 1)

    def test_current_write_preserves_other_operating_words(self):
        peer = EmpowerPeer()
        result = parse_response(decode(peer.handle(commands.set_operating_words(145, 100, 40))), (1, 2))
        self.assertEqual(result['current_set_a'], 14.5)
        self.assertEqual(result['_raw_status_fields']['frequency_word'], 100)
        self.assertEqual(result['_raw_status_fields']['width_word'], 40)
        self.assertEqual(result['current_a'], .2)  # Preserve captured sensing, not invented current.

    def test_synthetic_countdown_and_stop_are_explicit(self):
        now = [0.0];peer = EmpowerPeer(clock=lambda: now[0])
        self.assertIsNone(peer.handle(commands.set_run(True)))
        self.assertEqual(peer.handle(commands.query_status())[28], 3)
        now[0] = 3.1
        self.assertEqual(peer.handle(commands.query_status())[28], 0)
        self.assertIsNone(peer.handle(commands.set_run(False)))
        self.assertEqual(peer.handle(commands.query_status())[28], 1)
        self.assertEqual(peer.handle(commands.query_power()), CAPTURED['power'])

    def test_unknown_opcode_gets_no_invented_reply(self):
        from emulator import encode
        self.assertIsNone(EmpowerPeer().handle(encode(0xfe)))

    def test_service_setting_not_falsely_acknowledged_as_changed(self):
        peer = EmpowerPeer()
        raw = bytes.fromhex('10 02 00 00 17 50 02 00 00 00 fa 00 02 58 00 00 3a 98 05 46 04 9c 8c')
        self.assertEqual(peer.handle(raw), CAPTURED['service'])


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.log = JsonLog()
        self.peer = EmpowerPeer(log=self.log)
        self.server = BinaryServer(('127.0.0.1', 0), self.peer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.client = BinaryClient(self.server.server_address)
        self.bridge = SpitfireBridge(self.client, self.log)

    def tearDown(self):
        self.client.close();self.server.close();self.thread.join(1)

    def test_empower_queries_reach_binary_endpoint(self):
        self.assertIn('1.2', self.bridge.answer(1035, 'EMP:VERS?'))
        self.assertEqual(self.bridge.answer(1077, 'EMP:LBOTEMP?'), '127.9')
        self.assertEqual(self.bridge.answer(1008, 'EMP:READ:POW?'), '0.0')
        self.assertEqual(self.bridge.answer(1014, 'EMP:FAULT?'), '0 0 0 0')
        self.assertEqual(self.log.counts['binary_transaction'], 4)

    def test_current_write_query_roundtrip_uses_binary_wire(self):
        self.assertEqual(self.bridge.answer(2003, 'EMP:DIODE:CURR 145'), '')
        self.assertEqual(self.bridge.answer(1009, 'EMP:DIODE:CURR?'), '145')

    def test_prf_units_match_fw12_and_original_spitfire_gui(self):
        # Captured binary word100 means 1 kHz; XP multiplies SASC value by10.
        self.assertEqual(float(self.bridge.answer(1010, 'EMP:QSW:PRF?')) * 10, 1000)
        self.bridge.answer(2004, 'EMP:QSW:PRF 200')
        self.assertEqual(float(self.bridge.answer(1010, 'EMP:QSW:PRF?')) * 10, 2000)
        reply = self.client.exchange(commands.query_status())
        self.assertEqual(parse_response(reply, (1, 2))['service']['qswitch_frequency_khz'], 2)

    def test_write_query_id_text_mismatch_is_rejected(self):
        self.assertEqual(self.bridge.answer(2003, 'EMP:ON'), 'ERROR:COMMAND')
        self.assertEqual(self.log.counts['binary_transaction'], 0)

    def test_synthetic_board_identity_cannot_be_mistaken_for_real_firmware(self):
        self.assertIn('EMU-', self.bridge.answer(1000, '*idn?'))

    def test_compound_modes_and_delay_channel_roundtrip(self):
        self.assertEqual(self.bridge.answer(2030, 'TDG:OSC:MODE INT'), '')
        self.assertEqual(self.bridge.answer(1067, 'TDG:OSC:MODE?'), 'INT')
        self.bridge.answer(2019, 'TDG:DEL 1 ON')
        self.assertEqual(self.bridge.answer(1045, 'TDG:DEL1?'), ' DELAY 1 ON BWD ENA 85.82')

    def test_actual_udp_request_reaches_binary_peer_and_gets_reply(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(('127.0.0.1', 0));port = probe.getsockname()[1];probe.close()
        stop = threading.Event()
        thread = threading.Thread(target=serve_udp, args=(self.bridge, ('127.0.0.1', port), '127.0.0.1', self.log, stop), daemon=True)
        thread.start()
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM);client.settimeout(1)
        try:
            client.sendto(b'Spectra-Physics:CMD_ECLIPSE,[1077]EMP:LBOTEMP?\n', ('127.0.0.1', port))
            self.assertEqual(client.recv(1500), b'Spectra-Physics:REPLY_ECLIPSE:<1077>127.9\n')
            self.assertEqual(self.log.counts['binary_transaction'], 1)
        finally:
            client.close();stop.set();thread.join(1)


if __name__ == '__main__':
    unittest.main()
