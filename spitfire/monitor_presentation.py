"""Bounded, file-snapshot-only presentation shared by the native and Qt views."""
from __future__ import annotations
import math
from datetime import datetime
import textwrap


def _age(value):
    try:
        if isinstance(value, (int, float)) and math.isfinite(value):
            return f'{max(0., value):.1f}s'
    except OverflowError:
        pass
    return '--'


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _text(value, limit=240):
    return ' '.join(str(value).replace('\x00', '').split())[:limit]


def event_key(record):
    """Identity used by Clear display; the saved files are never modified."""
    if isinstance(record.get('seq'), int):
        return str(record.get('session_id', '')), record['seq']
    return tuple(str(record.get(key, '')) for key in ('utc', 'monotonic', 'kind', 'payload'))


def is_problem(record):
    kind = str(record.get('kind', '')).lower()
    event = str(record.get('event', _mapping(record.get('fields')).get('event', ''))).lower()
    if kind in ('tx', 'rx'):
        return False
    words = ('error', 'timeout', 'retry', 'ignored', 'warning', 'suppressed', 'coalesced',
             'canceled', 'failed', 'overflow', 'dropped')
    if any(word in kind or word in event for word in words):
        return True
    if kind in ('connection', 'frequency', 'read only', 'callback'):
        message = str(record.get('payload', '')).lower()
        return any(word in message for word in (
            'no ', 'not ', 'disconnect', 'reconnect', 'blocked', 'ignored',
            'pause', 'disabled', 'failed', 'error', 'unconfirmed'))
    return False


def _event_time(value):
    try:
        timestamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return timestamp.strftime('%m-%d %H:%M:%S.') + f'{timestamp.microsecond // 1000:03d}Z'
    except (ValueError, OverflowError, TypeError):
        return _text(value, 24)


def _event_detail(record):
    """Prefer the structured queue fields over their long Python dict repr."""
    fields = _mapping(record.get('fields'))
    event = fields.get('event', record.get('event'))
    if str(record.get('kind', '')).upper() != 'QUEUE' or not event:
        return _text(record.get('payload', ''), 360)
    parts = ['duplicate suppressed' if event == 'coalesced' else str(event).replace('_', ' ')]
    for name, label in (('tag', 'tag'), ('request_id', 'request'), ('batch_id', 'batch')):
        value = fields.get(name, record.get(name))
        if value is not None:
            parts.append(f'{label} {_text(value, 45)}')
    if fields.get('suppressed') is not None:
        parts.append(f"suppressed {fields['suppressed']}")
    if fields.get('wait_seconds') is not None:
        parts.append('wait ' + _age(fields['wait_seconds']))
    if fields.get('retry'):
        parts.append('retry')
    if fields.get('result'):
        parts.append('result ' + _text(fields['result'], 30))
    if 'queue_inside' in fields and 'queue_outside' in fields:
        parts.append(f"queue {fields['queue_inside']}+{fields['queue_outside']}")
    if fields.get('origin'):
        parts.append('source ' + _text(fields['origin'], 60))
    return _text(' | '.join(parts), 360)


def format_snapshot(snapshot, *, problems_only=False, cleared=(), max_events=300,
                    max_chars=48000):
    """Format already-cached records without reading files or accessing devices."""
    heartbeat = _mapping(snapshot.get('heartbeat'))
    communication = _mapping(heartbeat.get('communication'))
    counters = _mapping(snapshot.get('counters'))
    controller = _mapping(counters.get('controller'))
    logger = _mapping(counters.get('logger'))
    reader = _mapping(counters.get('reader'))
    log_status = str(snapshot.get('log_status', snapshot.get('status', 'waiting')))
    device_status = str(snapshot.get('device_status', 'unknown'))
    mode = (' | READ ONLY' if heartbeat.get('read_only') else '')
    warnings = []
    if log_status == 'disabled':
        warnings.append('Logging disabled. Start with --diagnostics-dir to enable this monitor.')
    elif log_status in ('waiting', 'stale', 'read_error') or device_status == 'unknown':
        warnings.append('Current device state is unknown until a fresh saved sample is available.')
    for area, detail in _mapping(snapshot.get('errors')).items():
        warnings.append(f'Read {area}: {_text(detail, 180)}')
    for area, detail in _mapping(logger.get('errors')).items():
        warnings.append(f'Write {area}: {_text(detail, 180)}')
    if logger.get('dropped_events', 0):
        warnings.append(f"Dropped log events: {logger['dropped_events']}")
    if reader.get('malformed_lines', 0) or reader.get('lost_rotation_tails', 0):
        warnings.append('Some saved event rows could not be displayed; see reader counts.')
    records = snapshot.get('events', [])
    if not isinstance(records, (list, tuple)):
        records = []
    selected = [record for record in records if isinstance(record, dict)
                and event_key(record) not in cleared and (not problems_only or is_problem(record))]
    lines = []
    size = 0
    for record in reversed(selected[-max(1, int(max_events)):]):
        timestamp = _event_time(record.get('utc', ''))
        line = f"{timestamp}  {_text(record.get('kind', ''), 20):<12}  {_event_detail(record)}"
        # Fixed-width native text must keep time/kind visible. Bound physical
        # lines as well as records; long raw replies are continued underneath.
        line = textwrap.fill(line, width=105, subsequent_indent=' ' * 24,
                             break_long_words=True, break_on_hyphens=False).replace('\n', '\r\n')
        if size + len(line) + 2 > max_chars:
            break
        lines.append(line)
        size += len(line) + 2
    lines.reverse()
    queue = communication
    return {
        'log': f"LOG: {log_status.upper()} | heartbeat age {_age(snapshot.get('heartbeat_age_seconds'))}",
        'device': f"DEVICE (saved): {device_status.upper().replace('_', ' ')}{mode}",
        'freshness': ('Saved response age: ' + _age(snapshot.get('last_reply_age_seconds'))
                      + ' | STATUS: ' + _age(snapshot.get('last_status_age_seconds'))
                      + ' | sample: ' + _age(snapshot.get('main_sample_age_seconds'))),
        'traffic': (f"TX packets {controller.get('tx_packets', 0)} | matched RX {controller.get('matched_replies', 0)}"
                    f" | query retries {controller.get('query_retries', 0)} / timeouts {controller.get('query_timeouts', 0)}"
                    f" | ACK timeouts {controller.get('write_ack_timeouts', 0)}"),
        'queue': (f"Queue {queue.get('queue_total', '--')} (user {queue.get('queue_inside', '--')} / poll {queue.get('queue_outside', '--')})"
                  f" | waiting tag {queue.get('pending_tag') or '--'} | oldest {_age(queue.get('oldest_queued_age_seconds'))}"
                  f" | suppressed Reset/Fault/BWD {queue.get('suppressed_reset_batches', 0)}/{queue.get('suppressed_fault_batches', 0)}/{queue.get('suppressed_bwd_reset_batches', 0)}"),
        'logger': (f"Logger: saved {logger.get('written_events', 0)} | pending {logger.get('queue_depth', 0)}"
                   f" | dropped {logger.get('dropped_events', 0)} | rotations {logger.get('rotations', 0)}"),
        'reader': (f"Reader: rows {reader.get('events_read', 0)} | invalid {reader.get('malformed_lines', 0)}"
                   f" | read failures {reader.get('read_failures', 0)} | missing rotation tails {reader.get('lost_rotation_tails', 0)}"),
        'warning': ' '.join(warnings)[:1200],
        'events': '\r\n'.join(lines), 'event_count': len(lines),
        'log_ok': log_status == 'live', 'device_ok': device_status == 'ready',
    }
