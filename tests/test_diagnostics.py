"""Communication evidence tests: simulator and loopback only (conftest guard)."""
from __future__ import annotations

import json
from pathlib import Path
import select
import socket
import threading
import time

import pytest

from spitfire.__main__ import MemoryView, arguments, make_controller
from spitfire.controller import Controller
from spitfire.diagnostics import CommunicationLog, DiagnosticConfig
from spitfire.external_policy import RESET_COMMAND_IDS
from spitfire.protocol import PACKET_PREFIX, UDPTransport
from spitfire.scheduling import Request
from spitfire.simulator import SimulatedTransport


def records(log):
    assert log.close(3), log.status
    paths = sorted(log.path.parent.glob(log.path.name + '*'))
    rows = [json.loads(line) for path in paths for line in path.read_text().splitlines()]
    return sorted(rows, key=lambda r: r['sequence'])


def wait_for(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.001)
    assert predicate()


def controller(tmp_path, **kwargs):
    now = [1.0]
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: now[0],
                     request_timeout=.2, diagnostic_config=DiagnosticConfig(tmp_path, queue_capacity=65536), **kwargs)
    return app, now


def ticks(app, now, count):
    for _ in range(count):
        app.tick()
        now[0] += .005


def test_default_off_and_cli_opt_in(tmp_path):
    opts = arguments(['--demo', '--headless', '--tcp-port', '0', '--data-dir', str(tmp_path)])
    app = make_controller(MemoryView(), opts)
    try:
        app.start()
        for _ in range(150):
            app.tick()
        assert app.diagnostic_status == {'enabled': False, 'error': None}
    finally:
        app.stop()
    assert not list(tmp_path.iterdir())
    opts = arguments(['--demo', '--tcp-port', '0', '--comm-log-dir', str(tmp_path),
                      '--comm-log-max-bytes', '8192', '--comm-log-backups', '2'])
    app = make_controller(MemoryView(), opts)
    app.stop()
    assert app.diagnostics.config.max_bytes == 8192
    assert app.diagnostics.config.backup_count == 2
    assert list(tmp_path.glob('comm-*.jsonl'))


@pytest.mark.parametrize('args', [['--comm-log-max-bytes', '0'], ['--comm-log-max-bytes', '4095'],
                                  ['--comm-log-backups', '-1']])
def test_cli_rejects_unbounded_or_invalid_limits(args):
    with pytest.raises(SystemExit) as exc:
        arguments(args)
    assert exc.value.code == 2


def test_wall_clock_adjustment_does_not_change_elapsed_order(tmp_path):
    wall = [1700000000000000000]
    mono = [100]
    log = CommunicationLog(DiagnosticConfig(tmp_path), wall_ns=lambda: wall[0], monotonic_ns=lambda: mono[0])
    mono[0] += 20
    log.emit('before')
    wall[0] -= 5_000_000_000
    mono[0] += 30
    log.emit('after')
    rows = records(log)
    before, after = [r for r in rows if r['event'] in ('before', 'after')]
    assert before['wall_time_ns'] > after['wall_time_ns']
    assert before['elapsed_ns'] < after['elapsed_ns']
    assert all(r['utc_time'].endswith('Z') for r in rows)
    assert [r['sequence'] for r in rows] == list(range(1, len(rows) + 1))


@pytest.mark.parametrize('backups', [0, 2])
def test_rotation_strict_byte_bound_and_complete_json_lines(tmp_path, backups):
    log = CommunicationLog(DiagnosticConfig(tmp_path, max_bytes=4096, backup_count=backups))
    for i in range(70):
        log.emit('packet', index=i, payload_bytes=bytes(range(256)))
    rows = records(log)
    paths = list(tmp_path.iterdir())
    assert len(paths) == backups + 1
    assert all(p.stat().st_size <= 4096 for p in paths)
    assert rows[-1]['event'] == 'session_end'
    assert max(r.get('index', -1) for r in rows) == 69
    assert log.status['dropped'] == 0


def test_oversized_record_is_explicit_and_sessions_do_not_collide(tmp_path):
    a, b = [CommunicationLog(DiagnosticConfig(tmp_path, max_bytes=4096)) for _ in range(2)]
    a.emit('huge', text='x' * 5000)
    rows_a, rows_b = records(a), records(b)
    assert a.path != b.path
    assert next(r for r in rows_a if r['event'] == 'huge')['record_omitted'] == 'exceeds max_bytes'
    assert a.status['oversized'] == 1
    assert all(r['session_id'] == b.session_id for r in rows_b)
    assert all(p.stat().st_size <= 4096 for p in tmp_path.iterdir())


def test_slow_disk_queue_overflow_and_bounded_close(monkeypatch, tmp_path):
    entered, release = threading.Event(), threading.Event()
    original = CommunicationLog._open
    def slow_open(self):
        entered.set()
        assert release.wait(3)
        original(self)
    monkeypatch.setattr(CommunicationLog, '_open', slow_open)
    log = CommunicationLog(DiagnosticConfig(tmp_path, queue_capacity=2))
    try:
        assert entered.wait(1)
        for i in range(100):
            log.emit('busy', index=i)
        assert log.status['dropped'] > 0
        assert not log.close(.01)
    finally:
        release.set()
    rows = records(log)
    assert rows[-1]['dropped_total'] == log.status['dropped']
    assert rows[-1]['event'] == 'session_end'


def scenario(config):
    now = [1.0]
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: now[0],
                     request_timeout=.2, diagnostic_config=config)
    try:
        app.start()
        ticks(app, now, 150)
        app.handle_callback('cllbckcmd_reset', event=1)
        ticks(app, now, 160)
        app.transport.values['COMSTATUS?'] = '5'
        ticks(app, now, 80)
        packets = list(app.transport.sent_packets)
        result = (packets, list(app.events), dict(app.values), dict(app.state))
    finally:
        app.stop()
    return app, result


def test_logging_and_open_failure_preserve_wire_and_state(tmp_path):
    _, baseline = scenario(None)
    on, enabled = scenario(DiagnosticConfig(tmp_path / 'on', queue_capacity=65536))
    assert enabled == baseline
    invalid = tmp_path / 'is-a-file'
    invalid.write_text('occupied')
    failed, failure_result = scenario(DiagnosticConfig(invalid))
    assert failure_result == baseline
    assert failed.diagnostic_status['error']
    rows = records(on.diagnostics)
    assert on.diagnostic_status['dropped'] == 0
    assert [bytes.fromhex(r['payload_hex']) for r in rows if r['event'] == 'udp_tx'] == baseline[0]
    assert all(r['mode'] == 'simulator' for r in rows if r['event'] in ('udp_tx', 'udp_rx'))
    assert not list((tmp_path / 'on').glob('*datalog*'))
    reset = [r for r in rows if r['event'] == 'request_sent' and r.get('request_id') in RESET_COMMAND_IDS]
    assert [r['request_id'] for r in reset] == list(RESET_COMMAND_IDS)
    assert len({r['reset_id'] for r in reset}) == 1
    assert [r['reset_step'] for r in reset] == [1, 2, 3]
    for sent in reset:
        assert any(r['event'] == 'reset_step_result' and r['outcome'] == 'ack'
                   and r['request_seq'] == sent['request_seq'] for r in rows)
        assert any(r.get('readback_for_request_seq') == sent['request_seq']
                   and r['event'] == 'response' and r['disposition'] == 'valid_readback' for r in rows)
    states = [r for r in rows if r['event'] == 'state']
    assert any(r['readbacks']['1089']['value'] == 4 and not r['fault_reason'] for r in states)
    assert any(r['readbacks']['1089']['value'] == 5 and r['fault_reason'] for r in states)


def test_writer_failure_isolated_after_open(monkeypatch, tmp_path):
    def fail_write(self, record):
        raise OSError('simulated disk full')
    monkeypatch.setattr(CommunicationLog, '_write', fail_write)
    _, baseline = scenario(None)
    app, actual = scenario(DiagnosticConfig(tmp_path))
    assert actual == baseline
    assert 'disk full' in app.diagnostic_status['error']


def test_reset_blocked_timeout_and_cancellation_are_distinct(tmp_path):
    app, now = controller(tmp_path)
    try:
        app._pc_running = True
        app.handle_callback('cllbckcmd_reset', event=1)  # existing PC operation guard
        app._pc_running = False
        app.start()
        ticks(app, now, 150)
        app.scheduler.clear()
        app.handle_callback('cllbckcmd_reset', event=1)
        app.tick()  # first reset command sent
        app.transport.pending.clear()  # deliberately lose its ACK
        now[0] += .3
        app.tick()
        app.request_pc_stop()  # cancels unsent reset writes
        app.tick()
    finally:
        app.stop()
    rows = records(app.diagnostics)
    assert any(r['event'] == 'reset_blocked' for r in rows)
    assert any(r['event'] == 'request_failed' and r['outcome'] == 'timeout'
               and r['request_id'] == 2049 and r['reset_id'] == 'reset-2' for r in rows)
    assert any(r['event'] == 'reset_step_cancelled' and r['reset_step'] == 2 for r in rows)
    assert any(r.get('readback_for_request_seq') for r in rows)


def test_startup_timeout_reconnect_and_malformed_readback(tmp_path):
    app, now = controller(tmp_path)
    try:
        app.start()
        app.transport.pending.clear()
        now[0] += 3.1
        app.tick()
        ticks(app, now, 150)
        app.scheduler.clear()
        app.scheduler.push(1089)
        app.tick()
        app.transport.pending.clear()
        app._receive('(999,1)<1089>bad-value')
        app.connect()
        ticks(app, now, 5)
    finally:
        app.stop()
    rows = records(app.diagnostics)
    assert any(r['event'] == 'startup_result' and r['outcome'] == 'timeout' for r in rows)
    assert any(r['event'] == 'response' and r['disposition'] == 'invalid_readback' for r in rows)
    assert {r['connection_id'] for r in rows if r['event'] == 'transport_open'} == {1, 2}


def test_localhost_raw_bytes_peers_drain_and_multiline(tmp_path):
    log = CommunicationLog(DiagnosticConfig(tmp_path))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
        server.bind(('127.0.0.1', 0))
        server_port = server.getsockname()[1]
        other.bind(('127.0.0.1', 0))
        server.settimeout(1)
        transport = UDPTransport('localhost', server.getsockname()[1], bind_port=0, timeout=.2)
        transport.observer = log.emit
        try:
            transport.open()
            packet = PACKET_PREFIX + b'[1089]COMSTATUS?\n'
            transport.send_packet(packet)
            received, destination = server.recvfrom(4096)
            assert received == packet
            other.sendto(b'wrong-peer', destination)
            assert transport.receive() == []
            server.sendto(b'old\x00\xff', destination)
            assert select.select([transport.socket], [], [], 1)[0]
            transport.discard_pending()
            server.sendto(b'bad-header\r\n', destination)
            assert transport.receive() == []
            raw = b'Spectra-Physics:REPLY_ECLIPSE:<1089>5\r\n<1066>4000\n\0tail\xff'
            server.sendto(raw, destination)
            assert [r.body for r in transport.receive()] == ['<1089>5', '<1066>4000']
        finally:
            transport.close()
    rows = records(log)
    rx = [r for r in rows if r['event'] == 'udp_rx']
    assert [r['disposition'] for r in rx] == ['unexpected_peer', 'drained_before_request', 'unparsed', 'parsed']
    assert [r['datagram_id'] for r in rx] == [1, 2, 3, 4]
    assert bytes.fromhex(rx[-1]['payload_hex']) == raw
    assert rx[-1]['sender_endpoint'][0] == '127.0.0.1'
    assert rx[-1]['peer_endpoint'][1] == server_port
    assert next(r for r in rows if r['event'] == 'udp_tx')['payload_hex'] == packet.hex()


def test_throwing_transport_observer_cannot_change_localhost_io():
    def broken(*args, **kwargs):
        raise RuntimeError('observer failed')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(('127.0.0.1', 0))
        server.settimeout(1)
        transport = UDPTransport('127.0.0.1', server.getsockname()[1], bind_port=0, timeout=.2)
        transport.observer = broken
        try:
            transport.open()
            transport.send_packet(PACKET_PREFIX + b'[1000]*idn?\n')
            packet, sender = server.recvfrom(4096)
            server.sendto(b'Spectra-Physics:REPLY_ECLIPSE:<1000>Spitfire\n', sender)
            assert transport.receive()[0].body == '<1000>Spitfire'
        finally:
            transport.close()


@pytest.mark.parametrize('lose_reset_ack', [False, True])
def test_controller_reset_over_real_loopback_udp(tmp_path, lose_reset_ack):
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(('127.0.0.1', 0))
    server.settimeout(.05)
    board = SimulatedTransport()
    done = threading.Event()
    errors = []
    def serve():
        try:
            while not done.is_set():
                try:
                    data, peer = server.recvfrom(4096)
                except socket.timeout:
                    continue
                board.send_packet(data)
                if lose_reset_ack and b'[2049]' in data:
                    board.pending.clear()
                while board.pending:
                    server.sendto(board.pending.popleft(), peer)
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    app = Controller(MemoryView(), host='127.0.0.1', port=server.getsockname()[1],
                     local_port=0, tcp_port=None, request_timeout=.2,
                     diagnostic_config=DiagnosticConfig(tmp_path, queue_capacity=65536))
    def until(predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            app.tick()
            if predicate():
                return
            time.sleep(.001)
        pytest.fail('localhost controller did not reach expected state')
    try:
        app.start()
        until(lambda: not app.decoder.readbacks.fault_reason(time.monotonic()))
        app.handle_callback('cllbckcmd_reset', event=1)
        until(lambda: any(b'[2050]RESET' in p for p in board.sent_packets))
        until(lambda: not app._diagnostic_resets and not app._diagnostic_request.get('reset_id'))
    finally:
        # Stop the mock board before closing its UDP peer. Windows otherwise
        # reports ICMP port-unreachable as WSAECONNRESET in server.recvfrom().
        done.set()
        worker.join(1)
        app.stop()
        server.close()
    assert not worker.is_alive()
    assert not errors
    rows = records(app.diagnostics)
    assert app.diagnostic_status['dropped'] == 0
    tx = [bytes.fromhex(r['payload_hex']) for r in rows if r['event'] == 'udp_tx']
    # The final outstanding query can be logged after the server loop exits;
    # all received commands must be exactly the logged prefix.
    assert tx[:len(board.sent_packets)] == board.sent_packets
    writes = [p for p in board.sent_packets if b'[20' in p]
    assert writes == [PACKET_PREFIX + f'[{tag}]'.encode() + command + b'\n'
                      for tag, command in zip(RESET_COMMAND_IDS, (b'ECU:RESETFAULTS', b'TDG:RESFAULT', b'RESET'))]
    results = [r for r in rows if r['event'] == 'reset_step_result' and r.get('request_id') == 2049]
    assert len(results) == 1
    assert results[0]['outcome'] == ('failed' if lose_reset_ack else 'ack')
    if lose_reset_ack:
        assert results[0]['reason'] == 'response timeout'


def test_rotate_failure_does_not_propagate_to_controller(monkeypatch, tmp_path):
    def fail_rotate(self):
        raise PermissionError('simulated Windows file lock')
    monkeypatch.setattr(CommunicationLog, '_rotate', fail_rotate)
    _, baseline = scenario(None)
    app, result = scenario(DiagnosticConfig(tmp_path, max_bytes=4096, queue_capacity=65536))
    assert result == baseline
    assert 'file lock' in app.diagnostic_status['error']


def test_udp_send_error_is_recorded_and_still_raised(tmp_path):
    class FailedSocket:
        def getsockname(self):
            return ('127.0.0.1', 50000)
        def sendto(self, *args):
            raise OSError('injected send error')
        def close(self):
            pass
    log = CommunicationLog(DiagnosticConfig(tmp_path))
    transport = UDPTransport('127.0.0.1', 9, bind_port=0)
    transport.socket = FailedSocket()
    transport.observer = log.emit
    packet = PACKET_PREFIX + b'[1000]*idn?\n'
    with pytest.raises(OSError, match='injected send error'):
        transport.send_packet(packet)
    transport.close()
    rows = records(log)
    error = next(r for r in rows if r['event'] == 'udp_send_error')
    assert error['payload_hex'] == packet.hex()
    assert not any(r['event'] == 'udp_tx' for r in rows)


def test_csv_export_merges_rotations_and_preserves_epoch_and_payload(tmp_path):
    import csv
    from spitfire.diagnostic_export import export
    log = CommunicationLog(DiagnosticConfig(tmp_path, max_bytes=4096, backup_count=2))
    for i in range(40):
        log.emit('udp_tx', payload_bytes=PACKET_PREFIX + f'[{1000+i}]x\n'.encode(),
                 local_endpoint=('0.0.0.0', 12345), peer_endpoint=('127.0.0.1', 1024))
    expected = records(log)
    output = tmp_path / 'comparison.csv'
    paths = list(tmp_path.glob('comm-*'))
    export(list(reversed(paths)), output)
    with output.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert [int(r['sequence']) for r in rows] == [r['sequence'] for r in expected]
    for original, row in zip(expected, rows):
        assert row['udp.payload'] == original.get('payload_hex', '')
        seconds, nanos = row['frame.time_epoch'].split('.')
        assert int(seconds) * 10**9 + int(nanos) == original['wall_time_ns']
    with pytest.raises(ValueError, match='overwrite'):
        export(paths, paths[0])


def test_headless_process_shutdown_persists_reported_records(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'tools' / 'ci_exec.py'), 'spitfire',
                             '--demo', '--headless', '--tcp-port', '0', '--duration', '.2',
                             '--comm-log-dir', str(tmp_path)], cwd=root, capture_output=True,
                            text=True, encoding='utf-8', timeout=10, check=True)
    status = json.loads(result.stdout)['communication_log']
    assert status['closed'] and not status['error'] and not status['dropped']
    rows = [json.loads(line) for line in Path(status['path']).read_text().splitlines()]
    assert len(rows) == status['written']
    assert rows[-1]['event'] == 'session_end'
