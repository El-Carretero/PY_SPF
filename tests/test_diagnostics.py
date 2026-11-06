"""Local diagnostics observe state without issuing GUI or transport requests."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from spitfire.diagnostics import SessionDiagnostics


def test_disabled_diagnostics_need_no_controller_or_files():
    diagnostics = SessionDiagnostics(None)
    diagnostics.tick()
    diagnostics.close()


def test_main_thread_samples_communication_and_timer_watchdog_is_bounded(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('spitfire.diagnostics.time.monotonic', lambda: now[0])
    arm = Mock()
    cancel = Mock()
    monkeypatch.setattr('spitfire.diagnostics.faulthandler.dump_traceback_later', arm)
    monkeypatch.setattr('spitfire.diagnostics.faulthandler.cancel_dump_traceback_later', cancel)
    thread = SimpleNamespace(start=Mock(), join=Mock(), is_alive=lambda: False)
    monkeypatch.setattr('spitfire.diagnostics.threading.Thread', lambda **kw: thread)

    class View:
        _read_diagnostics = {'get_ctrl_val_calls': 7, 'timer_values_skipped': 2}

        def read(self, panel, control):
            return 42

    original_log = Mock()
    communication = Mock(return_value={'controller': {'tx_packets': 12}, 'last_status_age_seconds': .5})
    controller = SimpleNamespace(view=View(), log=original_log, read_only=True,
                                 communication_diagnostics=communication,
                                 state={'connected': True, 'gui_ready': True, 'last_query_id': 1085},
                                 running=True)
    diagnostics = SessionDiagnostics(controller, tmp_path)
    assert controller.view.read(6, 8) == 42
    controller.log('TX', '[1085]STATUS?')
    original_log.assert_called_once_with('TX', '[1085]STATUS?')
    for _ in range(20):
        diagnostics.tick()
    assert arm.call_count == 1  # No watchdog thread recreation per GUI tick.
    assert communication.call_count == 1
    now[0] += 1.1
    diagnostics.tick()
    assert arm.call_count == 2
    assert communication.call_count == 2
    diagnostics._flush()
    diagnostics._heartbeat()
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert heartbeat['loops'] == 21
    assert heartbeat['read_only'] and heartbeat['gui_ready']
    assert heartbeat['communication']['controller']['tx_packets'] == 12
    assert heartbeat['native_reads']['timer_values_skipped'] == 2
    assert heartbeat['original_ni_gui_version'] == '1.6.0'
    assert set(heartbeat['source_sha256']) == {'native.py', 'native_ticker.py', 'controller.py', 'protocol.py'}
    events = [json.loads(row) for row in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert events[0]['payload'] == '[1085]STATUS?'
    diagnostics.close()
    assert controller.log is original_log
    assert controller.view.read(6, 8) == 42
    cancel.assert_called_once_with()


def _writer(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr('spitfire.diagnostics.faulthandler.dump_traceback_later', Mock())
    monkeypatch.setattr('spitfire.diagnostics.faulthandler.cancel_dump_traceback_later', Mock())
    thread = SimpleNamespace(start=Mock(), join=Mock(), is_alive=lambda: False)
    monkeypatch.setattr('spitfire.diagnostics.threading.Thread', lambda **kw: thread)
    controller = SimpleNamespace(view=SimpleNamespace(), log=Mock(),
                                 state={'connected': False}, running=True)
    return controller, SessionDiagnostics(controller, tmp_path, **kwargs)


def test_bounded_queue_reports_loss_and_structured_metadata(tmp_path, monkeypatch):
    controller, diagnostics = _writer(tmp_path, monkeypatch, queue_capacity=2,
                                      max_flush_entries=1)
    payload = {'event': 'queued', 'request_id': 12, 'tag': 1085, 'origin': 'fault'}
    controller.log('QUEUE', payload)
    controller.log('TX', '[1085]STATUS?')
    controller.log('RX', '<1085>0')
    diagnostics._flush()
    diagnostics._heartbeat()
    record = json.loads((tmp_path / 'events.jsonl').read_text())
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert record['schema_version'] == 2
    assert record['session_id'] == heartbeat['session_id']
    assert heartbeat['session_directory'] == tmp_path.name
    assert record['fields'] == payload and record['request_id'] == 12
    assert record['payload'] == str(payload) and record['seq'] == 1
    assert heartbeat['logger']['dropped_events'] == 1
    assert heartbeat['logger']['queue_depth'] == 1
    assert heartbeat['logger']['written_events'] == 1
    assert heartbeat['logger']['queue_high_watermark'] == 2
    diagnostics.close()


def test_writer_rotates_with_bounded_retention_and_sequence(tmp_path, monkeypatch):
    controller, diagnostics = _writer(tmp_path, monkeypatch, max_file_bytes=600,
                                      retained_files=3)
    for index in range(20):
        controller.log('TX', 'x' * 120 + str(index))
    while diagnostics._flush():
        pass
    files = sorted(tmp_path.glob('events*.jsonl'))
    assert {path.name for path in files} == {'events.jsonl', 'events.1.jsonl', 'events.2.jsonl'}
    assert all(path.stat().st_size <= 600 for path in files)
    rows = [json.loads(line) for path in files for line in path.read_text().splitlines()]
    assert max(row['seq'] for row in rows) == 20
    assert len({row['seq'] for row in rows}) == len(rows)
    diagnostics._heartbeat()
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert heartbeat['logger']['written_events'] == 20
    assert heartbeat['logger']['rotations'] > 0
    diagnostics.close()


def test_failed_event_write_is_retried_and_does_not_prevent_heartbeat(tmp_path, monkeypatch):
    from pathlib import Path
    controller, diagnostics = _writer(tmp_path, monkeypatch)
    controller.log('TX', '[1085]STATUS?')
    original_open = Path.open
    failing = [True]

    def broken_open(path, *args, **kwargs):
        if path.name == 'events.jsonl' and failing[0]:
            raise OSError('disk temporarily unavailable')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', broken_open)
    assert diagnostics._flush() == 0
    diagnostics._heartbeat()
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert heartbeat['logger']['queue_depth'] == 1
    assert heartbeat['logger']['event_write_failures'] == 1
    assert 'temporarily unavailable' in heartbeat['logger']['errors']['event']
    failing[0] = False
    assert diagnostics._flush() == 1
    diagnostics._heartbeat()
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert heartbeat['logger']['queue_depth'] == 0
    assert not heartbeat['logger']['errors']
    assert json.loads((tmp_path / 'events.jsonl').read_text())['seq'] == 1
    diagnostics.close()


def test_startup_directory_failure_is_nonfatal_and_recovers(tmp_path, monkeypatch):
    path = tmp_path / 'blocked'
    path.write_text('not a directory')
    controller, diagnostics = _writer(path, monkeypatch)
    controller.log('TX', 'test')
    diagnostics._flush()
    diagnostics._heartbeat()
    assert diagnostics._health['event_write_failures'] == 1
    assert diagnostics._health['heartbeat_write_failures'] == 1
    path.unlink()
    path.mkdir()
    diagnostics._open_stacks()
    diagnostics._flush()
    diagnostics._heartbeat()
    assert json.loads((path / 'heartbeat.json').read_text())['logger']['errors'] == {}
    diagnostics.close()


def test_failed_atomic_heartbeat_replace_recovers(tmp_path, monkeypatch):
    from pathlib import Path
    controller, diagnostics = _writer(tmp_path, monkeypatch)
    original_replace = Path.replace
    failing = [True]

    def broken_replace(path, target):
        if path.name == 'heartbeat.tmp' and failing[0]:
            raise PermissionError('temporary Windows sharing violation')
        return original_replace(path, target)

    monkeypatch.setattr(Path, 'replace', broken_replace)
    diagnostics._heartbeat()
    assert diagnostics._health['heartbeat_write_failures'] == 1
    assert 'heartbeat' in diagnostics._errors
    failing[0] = False
    diagnostics._heartbeat()
    diagnostics._heartbeat()
    heartbeat = json.loads((tmp_path / 'heartbeat.json').read_text())
    assert 'heartbeat' not in heartbeat['logger']['errors']
    diagnostics.close()


def test_flush_budget_preserves_heartbeat_work(tmp_path, monkeypatch):
    controller, diagnostics = _writer(tmp_path, monkeypatch, max_flush_entries=128,
                                      max_flush_seconds=.02)
    for _ in range(30):
        controller.log('TX', 'test')
    now = [100.]

    def advancing_clock():
        now[0] += .005
        return now[0]

    monkeypatch.setattr('spitfire.diagnostics.time.monotonic', advancing_clock)
    written = diagnostics._flush()
    assert 0 < written < 30
    diagnostics._heartbeat()
    assert (tmp_path / 'heartbeat.json').exists()
    assert diagnostics._queue.qsize() > 0
    diagnostics.close()


def test_short_event_write_recovers_line_boundary_and_retries_sequence(tmp_path, monkeypatch):
    from pathlib import Path
    from spitfire.communication_monitor import CommunicationMonitor
    controller, diagnostics = _writer(tmp_path, monkeypatch)
    controller.log('TX', '[1085]STATUS?')
    original_open = Path.open
    short_once = [True]

    class ShortWrite:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, data):
            if short_once[0]:
                short_once[0] = False
                return self.stream.write(data[:17])
            return self.stream.write(data)

    def short_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return ShortWrite(stream) if path.name == 'events.jsonl' and short_once[0] else stream

    monkeypatch.setattr(Path, 'open', short_open)
    assert diagnostics._flush() == 0
    assert diagnostics._flush() == 1
    reader = CommunicationMonitor(tmp_path)
    reader._poll_once()
    snapshot = reader.snapshot()
    assert len(snapshot['events']) == 1
    assert snapshot['events'][0]['seq'] == 1
    assert snapshot['counters']['reader']['malformed_lines'] == 1
    diagnostics.close()


def test_windows_current_rotation_failure_preserves_all_archives(tmp_path, monkeypatch):
    from pathlib import Path
    controller, diagnostics = _writer(tmp_path, monkeypatch, max_file_bytes=600)
    for index in range(4):
        name = 'events.jsonl' if index == 0 else f'events.{index}.jsonl'
        (tmp_path / name).write_text(f'archive-{index}\n' + 'x' * 600)
    before = {p.name: p.read_bytes() for p in tmp_path.glob('events*.jsonl')}
    original_replace = Path.replace
    denied = [True]

    def locked_current(path, target):
        if path.name == 'events.jsonl' and denied[0]:
            raise PermissionError('reader briefly has current file open')
        return original_replace(path, target)

    monkeypatch.setattr(Path, 'replace', locked_current)
    controller.log('TX', 'next')
    for _ in range(3):
        diagnostics._flush()
    assert {p.name: p.read_bytes() for p in tmp_path.glob('events*.jsonl')} == before
    assert not list(tmp_path.glob('.events-rotation-*.tmp'))
    denied[0] = False
    assert diagnostics._flush() == 1
    assert diagnostics._health['rotations'] == 1
    diagnostics.close()


def test_archive_rotation_failure_rolls_back_and_retries(tmp_path, monkeypatch):
    from pathlib import Path
    controller, diagnostics = _writer(tmp_path, monkeypatch, max_file_bytes=600)
    for index in range(4):
        name = 'events.jsonl' if index == 0 else f'events.{index}.jsonl'
        (tmp_path / name).write_text(f'archive-{index}\n' + 'x' * 600)
    before = {p.name: p.read_bytes() for p in tmp_path.glob('events*.jsonl')}
    original_replace = Path.replace
    denied = [True]

    def locked_archive(path, target):
        if path.name == 'events.2.jsonl' and denied[0]:
            raise PermissionError('archive locked')
        return original_replace(path, target)

    monkeypatch.setattr(Path, 'replace', locked_archive)
    controller.log('TX', 'next')
    diagnostics._flush()
    assert {p.name: p.read_bytes() for p in tmp_path.glob('events*.jsonl')} == before
    denied[0] = False
    assert diagnostics._flush() == 1
    diagnostics.close()


def test_multibyte_payloads_fit_reader_byte_limit(tmp_path, monkeypatch):
    from spitfire.communication_monitor import CommunicationMonitor
    controller, diagnostics = _writer(tmp_path, monkeypatch)
    controller.log('QUEUE', {'text': '🙂' * 15000})
    controller.log('QUEUE', {'text': '\x00' * 15000})
    diagnostics._flush()
    assert max(len(row) for row in (tmp_path / 'events.jsonl').read_bytes().splitlines()) < 64 * 1024
    reader = CommunicationMonitor(tmp_path)
    reader._poll_once()
    assert len(reader.snapshot()['events']) == 2
    assert reader.snapshot()['counters']['reader']['malformed_lines'] == 0
    diagnostics.close()


def test_reused_directory_gets_independent_event_session_ids(tmp_path, monkeypatch):
    controller, first = _writer(tmp_path, monkeypatch)
    controller.log('TX', 'first process')
    first._flush()
    first.close()
    controller, second = _writer(tmp_path, monkeypatch)
    controller.log('TX', 'second process')
    second._flush()
    rows = [json.loads(row) for row in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert rows[0]['seq'] == rows[1]['seq'] == 1
    assert rows[0]['session_id'] != rows[1]['session_id']
    second.close()
