"""Strict offline capture loading and bounded, wire-evidence reaction checks.

No code or commands in imported files are executed. A reaction PASS concerns
accepted requests observed by the virtual server, never optical safety or GUI
behaviour. A missing client, missing time base, or unfinished window cannot pass.
"""
from __future__ import annotations

from dataclasses import MISSING, fields
from datetime import datetime
import ipaddress
import json
import math
from pathlib import Path

from .records import CaptureMessage, CaptureSnapshot, Transaction

MAX_CAPTURE_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_LINE_BYTES = 1024 * 1024


class EvidenceError(ValueError):
    """Imported evidence is malformed, incomplete, or exceeds safe limits."""


def _finite(value, name, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise EvidenceError(f'{name} must be a finite number >= {minimum}')
    return value


def _integer(value, name, *, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
        raise EvidenceError(f'{name} is outside its integer range')


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def _json(text):
    def reject_constant(value):
        raise EvidenceError(f'non-finite JSON value: {value}')
    try:
        return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=reject_constant)
    except (ValueError, RecursionError) as exc:
        raise EvidenceError(f'invalid JSON: {exc}') from exc


def _timestamp(value, name):
    if not isinstance(value, str):
        raise EvidenceError(f'{name} must be a timestamp string')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise EvidenceError(f'invalid {name}') from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f'{name} must include a UTC offset')


def _hex(value, name):
    if not isinstance(value, str):
        raise EvidenceError(f'{name} must be a hex string')
    try:
        data = bytes.fromhex(value)
    except ValueError as exc:
        raise EvidenceError(f'invalid {name}') from exc
    if len(data) > 65507:
        raise EvidenceError(f'{name} exceeds UDP payload size')


def _record(cls, data, sid):
    schema = {field.name: field for field in fields(cls)}
    unknown = set(data) - set(schema)
    required = {name for name, field in schema.items() if field.default is MISSING and field.default_factory is MISSING}
    if unknown or not required <= set(data):
        raise EvidenceError(f'{cls.__name__} unknown/missing fields: {sorted(unknown | (required-set(data)))}')
    if data.get('session_id') != sid:
        raise EvidenceError('record session_id does not match the header')
    _timestamp(data['timestamp_utc'], 'timestamp_utc')
    numbers = {'sequence', 'datagram_sequence', 'command_index', 'command_id', 'source_port', 'scenario_phase'}
    floats = {'latency_ms', 'processing_ms', 'configured_delay_ms'}
    for name, value in data.items():
        if name in numbers:
            _integer(value, name, minimum=1 if name in {'sequence', 'datagram_sequence', 'command_index'} else 0,
                     maximum=65535 if name == 'source_port' else None)
        elif name in floats:
            _finite(value, name)
        elif name == 'scenario_time_ms':
            if value is not None:
                _finite(value, name)
        elif name == 'modelled':
            if not isinstance(value, bool):
                raise EvidenceError('modelled must be bool')
        elif name == 'response_value':
            if value is not None and not isinstance(value, str):
                raise EvidenceError('response_value must be string or null')
        elif not isinstance(value, str):
            raise EvidenceError(f'{name} must be string')
        if name.endswith('_hex'):
            _hex(value, name)
        if name.endswith('_json') and not isinstance(_json(value), dict):
            raise EvidenceError(f'{name} must contain a JSON object')
    if data.get('sent_utc'):
        _timestamp(data['sent_utc'], 'sent_utc')
    if data.get('source_ip'):
        try:
            ipaddress.ip_address(data['source_ip'])
        except ValueError as exc:
            raise EvidenceError('invalid source_ip') from exc
    if cls is Transaction and data['status'] not in {'REPLIED', 'DROPPED', 'STOPPED', 'SEND_ERROR'}:
        raise EvidenceError('unknown transaction status')
    return cls(**data)


def load_capture(path) -> CaptureSnapshot:
    """Read the export JSONL format with strict schemas and bounded resources.

    Exported files always end in a newline; a missing final newline is rejected
    as potentially truncated. Old captures without scenario timing may load but
    cannot pass time-based assertions. Unknown future schema fields fail closed.
    """
    path = Path(path)
    if path.stat().st_size > MAX_CAPTURE_BYTES:
        raise EvidenceError('capture exceeds 32 MiB')
    with path.open('rb') as stream:
        raw = stream.read(MAX_CAPTURE_BYTES + 1)
    if len(raw) > MAX_CAPTURE_BYTES:
        raise EvidenceError('capture exceeds 32 MiB')
    if not raw or not raw.endswith(b'\n'):
        raise EvidenceError('empty or possibly truncated capture (final newline missing)')
    lines = raw.splitlines()
    if len(lines) > MAX_RECORDS + 1 or any(len(line) > MAX_LINE_BYTES for line in lines):
        raise EvidenceError('capture exceeds record or line limit')
    objects = []
    for line in lines:
        if not line:
            raise EvidenceError('blank records are not allowed')
        try:
            item = _json(line.decode('utf-8'))
        except UnicodeError as exc:
            raise EvidenceError('capture must be UTF-8') from exc
        if not isinstance(item, dict):
            raise EvidenceError('each record must be an object')
        objects.append(item)
    header = objects[0]
    if set(header) != {'type', 'session_id', 'snapshot_utc', 'metadata', 'pending'} or header['type'] != 'session':
        raise EvidenceError('first record must be the complete session header')
    sid = header['session_id']
    if not isinstance(sid, str) or not sid or len(sid) > 256:
        raise EvidenceError('invalid session_id')
    _timestamp(header['snapshot_utc'], 'snapshot_utc')
    if not isinstance(header['metadata'], dict) or not isinstance(header['pending'], list) or not all(isinstance(x, dict) for x in header['pending']):
        raise EvidenceError('invalid metadata or pending list')
    transactions, messages = [], []
    sequences = set()
    for item in objects[1:]:
        kind = item.get('type')
        data = {key: value for key, value in item.items() if key != 'type'}
        if kind == 'transaction':
            record = _record(Transaction, data, sid)
            if record.sequence in sequences:
                raise EvidenceError('duplicate transaction sequence')
            sequences.add(record.sequence)
            transactions.append(record)
        elif kind == 'message':
            messages.append(_record(CaptureMessage, data, sid))
        else:
            raise EvidenceError(f'unknown record type: {kind}')
    if sequences and sequences != set(range(1, len(sequences) + 1)):
        raise EvidenceError('transaction sequence has missing records')
    return CaptureSnapshot(sid, header['snapshot_utc'], tuple(transactions), tuple(messages),
                           tuple(header['pending']), header['metadata'])


def assess_reactions(snapshot, rules, client_label):
    """Check accepted virtual requests against explicit time-window rules.

    Rules: {name?, kind: require|forbid, command_id: int, after_ms: number,
    before_ms: number, argument?: exact string}. Only VALID requests whose
    effect is not rejected/not_executed count. Reply-loss after execution still
    counts. PASS is accepted wire-command evidence, not internal GUI reaction.
    """
    if not isinstance(snapshot, CaptureSnapshot):
        raise EvidenceError('snapshot must be CaptureSnapshot')
    if not isinstance(client_label, str) or not client_label:
        raise EvidenceError('client_label is required')
    if not isinstance(rules, list) or not rules or len(rules) > 1000:
        raise EvidenceError('rules must be a nonempty list of at most 1000 items')
    checked = []
    for index, rule in enumerate(rules):
        required = {'kind', 'command_id', 'after_ms', 'before_ms'}
        if not isinstance(rule, dict) or not required <= set(rule) or set(rule)-required-{'name', 'argument'}:
            raise EvidenceError('rule contains unknown or missing fields')
        if rule['kind'] not in {'require', 'forbid'}:
            raise EvidenceError('rule kind must be require or forbid')
        _integer(rule['command_id'], 'command_id', maximum=2**31-1)
        start = _finite(rule['after_ms'], 'after_ms')
        end = _finite(rule['before_ms'], 'before_ms')
        if start > end:
            raise EvidenceError('after_ms must be <= before_ms')
        if any(key in rule and not isinstance(rule[key], str) for key in ('name', 'argument')):
            raise EvidenceError('name and argument must be strings')
        checked.append(dict(rule, name=rule.get('name', f'rule_{index+1}')))
    items = [item for item in snapshot.transactions if item.client_label == client_label]
    timed = [item for item in items if item.scenario_time_ms is not None]
    for item in timed:
        _finite(item.scenario_time_ms, 'scenario_time_ms')
    ordered_times = [item.scenario_time_ms for item in sorted(timed, key=lambda item: (item.datagram_sequence, item.command_index))]
    time_reversed = any(right < left for left, right in zip(ordered_times, ordered_times[1:]))
    coverage = max((item.scenario_time_ms for item in timed), default=None)
    start_coverage = min((item.scenario_time_ms for item in timed), default=None)
    scenario_names = {item.scenario for item in timed}
    diagnostic_error = any(item.level in {'ERROR', 'PROTOCOL'} and item.client_label in {'', client_label}
                           for item in snapshot.messages)
    rows = []
    for rule in checked:
        window = [item for item in timed if rule['after_ms'] <= item.scenario_time_ms <= rule['before_ms']]
        matches = [item for item in window if item.command_id == rule['command_id']
                   and ('argument' not in rule or item.argument == rule['argument'])
                   and item.validation == 'VALID' and item.effect not in {'not_executed', 'rejected'}
                   and item.status not in {'STOPPED', 'SEND_ERROR'}]
        unknown = any(not item.modelled for item in matches)
        if not items or len(timed) != len(items):
            verdict, reason = 'UNVERIFIED', 'Client evidence is missing or its scenario time base is incomplete'
        elif time_reversed:
            verdict, reason = 'UNVERIFIED', 'Scenario time reversed within the captured client session'
        elif len(scenario_names) != 1 or not next(iter(scenario_names)):
            verdict, reason = 'UNVERIFIED', 'Exactly one named scenario is required'
        elif snapshot.pending or diagnostic_error:
            verdict, reason = 'INCOMPLETE', 'Pending datagrams or acquisition/protocol errors'
        elif coverage < rule['before_ms'] or start_coverage > rule['after_ms']:
            verdict, reason = 'INCOMPLETE', 'Observed checkpoints do not bracket the complete window'
        elif unknown:
            verdict, reason = 'UNVERIFIED', 'Matching command has an unmodelled effect'
        else:
            passed = bool(matches) if rule['kind'] == 'require' else not matches
            verdict = 'PASS' if passed else 'FAIL'
            reason = 'Accepted wire requests checked against the explicit rule'
        rows.append({**rule, 'verdict': verdict, 'reason': reason,
                     'matching_sequences': [item.sequence for item in matches]})
    verdicts = {row['verdict'] for row in rows}
    overall = next((status for status in ('FAIL', 'INCOMPLETE', 'UNVERIFIED') if status in verdicts), 'PASS')
    return {'kind': 'wire_reaction_assessment', 'verdict': overall, 'client_label': client_label,
            'session_id': snapshot.session_id, 'coverage_start_ms': start_coverage, 'coverage_end_ms': coverage,
            'rules': rows, 'gui_validation': 'UNVERIFIED', 'physical_validation': 'UNVERIFIED',
            'scope': 'Accepted virtual-server requests only; no GUI, optical, or firmware safety certification'}
