"""Saved-log monitoring has no device/GUI dependencies or GUI-thread file IO."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

from spitfire.communication_monitor import CommunicationMonitor


NOW = 1700000000.


def _utc(timestamp=NOW):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _row(payload='ok', **extra):
    return (json.dumps({'utc': _utc(), 'kind': 'RX', 'payload': payload, **extra},
                       ensure_ascii=False) + '\n').encode('utf-8')


def _heartbeat(path, **extra):
    heartbeat = {'utc': _utc(), 'sampled_utc': _utc(), 'connected': True,
                 'gui_ready': True, 'running': True,
                 'communication': {'last_match_age_seconds': .5,
                                   'last_status_age_seconds': 1.}, **extra}
    (path / 'heartbeat.json').write_text(json.dumps(heartbeat))


def _reader(path, now=None, **kwargs):
    now = now if now is not None else [NOW]
    return CommunicationMonitor(path, wall_clock=lambda: now[0],
                                clock=lambda: now[0], **kwargs)


def test_partial_utf8_line_waits_for_newline_and_malformed_line_is_separate(tmp_path):
    reader = _reader(tmp_path)
    line = _row('통신 확인', seq=1, session_id='one')
    split = line.index('통'.encode('utf-8')) + 1
    events = tmp_path / 'events.jsonl'
    events.write_bytes(line[:split])
    reader._poll_once()
    assert reader.snapshot()['events'] == []
    with events.open('ab') as stream:
        stream.write(line[split:] + b'{broken}\n' + _row('next', seq=2, session_id='one'))
    reader._poll_once()
    snapshot = reader.snapshot()
    assert [row['payload'] for row in snapshot['events']] == ['통신 확인', 'next']
    assert snapshot['counters']['reader']['malformed_lines'] == 1
    assert snapshot['counters']['reader']['bytes_read'] == events.stat().st_size


def test_reader_drains_unread_archive_then_current_after_rotation(tmp_path):
    reader = _reader(tmp_path, max_read_bytes=256)
    events = tmp_path / 'events.jsonl'
    events.write_bytes(_row('first', seq=1))
    reader._poll_once()
    with events.open('ab') as stream:
        stream.write(_row('archive tail', seq=2))
    events.replace(tmp_path / 'events.1.jsonl')
    events.write_bytes(_row('current', seq=3))
    reader._poll_once()
    reader._poll_once()
    snapshot = reader.snapshot()
    assert [row['seq'] for row in snapshot['events']] == [1, 2, 3]
    assert snapshot['counters']['reader']['rotations'] == 1
    assert snapshot['counters']['reader']['lost_rotation_tails'] == 0


def test_truncation_and_same_inode_rewrite_do_not_reuse_old_partial_bytes(tmp_path):
    reader = _reader(tmp_path)
    events = tmp_path / 'events.jsonl'
    events.write_bytes(_row('before', seq=1) + b'partial')
    reader._poll_once()
    events.write_bytes(_row('a much longer replacement than before', seq=2))
    reader._poll_once()
    snapshot = reader.snapshot()
    assert [row['seq'] for row in snapshot['events']] == [1, 2]
    assert snapshot['counters']['reader']['truncations'] == 1
    assert snapshot['counters']['reader']['discarded_partial_lines'] == 1
    assert snapshot['counters']['reader']['malformed_lines'] == 0


def test_bounded_initial_tail_rows_and_replayed_sequences(tmp_path):
    events = tmp_path / 'events.jsonl'
    events.write_bytes(b''.join(_row(str(index), seq=index) for index in range(20)))
    reader = _reader(tmp_path, max_events=3, max_read_bytes=512)
    reader._poll_once()
    snapshot = reader.snapshot()
    assert len(snapshot['events']) == 3
    assert snapshot['events'][-1]['seq'] == 19
    assert snapshot['counters']['reader']['skipped_initial_bytes'] > 0
    assert snapshot['counters']['reader']['bytes_read'] <= 512
    with events.open('ab') as stream:
        stream.write(_row('replayed', seq=19) + _row('new', seq=20))
    reader._poll_once()
    assert [row['seq'] for row in reader.snapshot()['events']] == [18, 19, 20]
    assert reader.snapshot()['counters']['reader']['duplicate_events'] == 1


def test_stale_log_and_fresh_log_without_reply_are_distinct(tmp_path):
    now = [NOW]
    reader = _reader(tmp_path, now)
    _heartbeat(tmp_path, communication={'last_match_age_seconds': 12.})
    reader._poll_once()
    snapshot = reader.snapshot()
    assert snapshot['log_status'] == 'live'
    assert snapshot['device_status'] == 'no_recent_reply'
    now[0] += 4
    snapshot = reader.snapshot()
    assert snapshot['log_status'] == 'stale'
    assert snapshot['device_status'] == 'unknown'
    assert snapshot['last_reply_age_seconds'] == 16.


def test_old_main_sample_is_not_mistaken_for_live_instrument_data(tmp_path):
    reader = _reader(tmp_path)
    _heartbeat(tmp_path, sampled_utc=_utc(NOW - 10),
               main_loop_progress_age_seconds=10.)
    reader._poll_once()
    snapshot = reader.snapshot()
    assert snapshot['log_status'] == 'live'
    assert snapshot['device_status'] == 'unknown'
    assert snapshot['last_reply_age_seconds'] == 10.5


def test_malformed_heartbeat_and_event_do_not_break_snapshot(tmp_path):
    reader = _reader(tmp_path)
    heartbeat = tmp_path / 'heartbeat.json'
    heartbeat.write_text('{broken')
    (tmp_path / 'events.jsonl').write_bytes(b'[]\n{"kind":"RX","payload":NaN}\n')
    reader._poll_once()
    reader._poll_once()
    snapshot = reader.snapshot()
    assert snapshot['counters']['reader']['malformed_heartbeats'] == 1
    assert snapshot['counters']['reader']['malformed_lines'] == 2
    assert 'heartbeat' in snapshot['errors']
    _heartbeat(tmp_path, communication=[], logger=[])
    reader._poll_once()
    assert reader.snapshot()['log_status'] == 'live'
    assert reader.snapshot()['counters']['controller'] == {}


def test_snapshot_does_no_file_io_and_sessions_are_not_auto_selected(tmp_path, monkeypatch):
    session = tmp_path / 'active'
    session.mkdir()
    other = tmp_path / 'newer-self-test'
    other.mkdir()
    _heartbeat(session)
    (session / 'events.jsonl').write_bytes(_row('active only'))
    (other / 'events.jsonl').write_bytes(_row('wrong session'))
    reader = _reader(session)
    reader._poll_once()

    def forbidden(*args, **kwargs):
        raise AssertionError('snapshot touched a file')

    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(Path, 'stat', forbidden)
    snapshot = reader.snapshot()
    assert [row['payload'] for row in snapshot['events']] == ['active only']
    assert snapshot['log_status'] == 'live'


def test_read_error_is_visible_and_retried(tmp_path, monkeypatch):
    _heartbeat(tmp_path)
    reader = _reader(tmp_path)
    original_open = Path.open
    fail = [True]

    def sometimes_denied(path, *args, **kwargs):
        if path.name == 'heartbeat.json' and fail[0]:
            raise PermissionError('sharing violation')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', sometimes_denied)
    reader._poll_once()
    assert 'heartbeat' in reader.snapshot()['errors']
    fail[0] = False
    reader._poll_once()
    assert reader.snapshot()['errors'] == {}
    assert reader.snapshot()['log_status'] == 'live'


def test_reader_start_and_close_are_bounded_without_any_socket(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: (_ for _ in ()).throw(AssertionError('hardware IO')))
    reader = _reader(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def stalled_read():
        entered.set()
        release.wait(2)

    monkeypatch.setattr(reader, '_read_heartbeat', stalled_read)
    reader.start()
    assert entered.wait(.5)
    started = time.monotonic()
    reader.close(timeout=.01)
    assert time.monotonic() - started < .2
    release.set()
    reader._thread.join(timeout=.5)
    assert not reader._thread.is_alive()


def test_two_rotations_between_polls_do_not_skip_retained_middle_archive(tmp_path):
    reader = _reader(tmp_path)
    current = tmp_path / 'events.jsonl'
    current.write_bytes(_row('one', seq=1))
    reader._poll_once()
    with current.open('ab') as stream:
        stream.write(_row('two', seq=2))
    current.replace(tmp_path / 'events.2.jsonl')
    (tmp_path / 'events.1.jsonl').write_bytes(_row('three', seq=3))
    current.write_bytes(_row('four', seq=4))
    for _ in range(3):
        reader._poll_once()
    snapshot = reader.snapshot()
    assert [row['seq'] for row in snapshot['events']] == [1, 2, 3, 4]
    assert snapshot['counters']['reader']['lost_rotation_tails'] == 0


def test_pathological_json_cannot_escape_snapshot_or_poll(tmp_path):
    reader = _reader(tmp_path)
    _heartbeat(tmp_path, communication={'last_match_age_seconds': 10 ** 1000})
    (tmp_path / 'events.jsonl').write_bytes(
        b'{"kind":"RX","payload":"deep","fields":' + b'[' * 500 + b'0' + b']' * 500 + b'}\n')
    reader._poll_once()
    snapshot = reader.snapshot()
    assert snapshot['last_reply_age_seconds'] is None
    assert snapshot['counters']['reader']['malformed_lines'] == 1
    assert snapshot['events'] == []
