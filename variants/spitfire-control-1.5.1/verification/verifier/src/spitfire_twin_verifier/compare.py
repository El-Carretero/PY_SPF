"""Compare evidence without confusing equality with successful validation."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import json
import re
from typing import Iterable
from .catalog import POLL_IDS
from .records import CaptureSnapshot, CaptureMessage, Transaction

@dataclass(slots=True)
class ComparisonRow:
    status: str
    command_id: int | None
    original_sequence: int | None
    python_sequence: int | None
    original_command: str
    python_command: str
    original_argument: str
    python_argument: str
    original_response: str | None
    python_response: str | None
    note: str
    semantic_equal: bool = False
    framing_equal: bool | None = None
    polling: bool = False
    scenario: str = ""

@dataclass(slots=True)
class ComparisonResult:
    original_label: str
    python_label: str
    original_total: int
    python_total: int
    original_writes: int
    python_writes: int
    original_query_ids: list[int]
    python_query_ids: list[int]
    original_write_ids: list[int]
    python_write_ids: list[int]
    sequence_similarity: float
    matched: int
    differences: int
    only_original: int
    only_python: int
    poll_coverage_differences: list[int]
    ignored_polling: bool
    verdict: str
    rows: list[ComparisonRow]
    count_differences: list[dict]
    content_verdict: str = "INCOMPLETE"
    semantic_verdict: str = "INCOMPLETE"
    framing_verdict: str = "UNVERIFIED"
    transport_health: str = "UNVERIFIED"
    issues: list[dict] = field(default_factory=list)
    pending_datagrams: int = 0
    session_id: str = ""
    snapshot_utc: str = ""
    gui_verdict: str = "NOT_CHECKED"
    batching: dict = field(default_factory=dict)
    client_reaction_verdict: str = 'NOT_CHECKED'
    physical_validation: str = 'UNVERIFIED'

    def to_dict(self):
        return asdict(self)

_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
def _meaning(value):
    if value is not None and _NUMBER.fullmatch(value.strip()):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            pass
    return value

def _response_meaning(item):
    # These recovered handlers parse hexadecimal even without a 0x prefix.
    # Generic decimal/exponent normalization would falsely equate 1000 and 1e3.
    if item.command_id in {1023, 1039, 1066}:
        raw = item.response_value
        if isinstance(raw, str) and re.fullmatch(r'(?:0[xX])?[0-9a-fA-F]{1,8}', raw.strip()):
            return ('hex32', int(raw.strip(), 16))
        return ('invalid_hex', raw)
    return _meaning(item.response_value)

def _framing(item):
    if item.request_framing and item.reply_framing:
        return item.request_framing, item.reply_framing
    # Import compatibility: derive framing from raw packets, never compare entire batches.
    def describe(raw):
        if not raw:
            return None
        try:
            data = bytes.fromhex(raw)
        except ValueError:
            return "INVALID_HEX"
        opening = b"[" if b"CMD_ECLIPSE," in data else b"<"
        offset = data.find(opening)
        header = data[:offset] if offset >= 0 else data
        endings = sorted(set("CRLF" if line.endswith(b"\r\n") else "LF" if line.endswith(b"\n") else "NONE"
                              for line in data[offset:].splitlines(keepends=True)))
        return header.hex(), tuple(endings)
    request, reply = describe(item.request_hex), describe(item.response_hex)
    return (request, reply) if request is not None and reply is not None else None

def _profile(item):
    try:
        data = json.loads(item.profile_json)
        data.pop("name", None)
        return data
    except (ValueError, AttributeError):
        return {"invalid_profile": item.profile_json}

def _row(left, right, *, polling=False):
    item = left or right
    if left is None or right is None:
        return ComparisonRow("ONLY_PYTHON" if left is None else "ONLY_ORIGINAL", item.command_id,
                             left.sequence if left else None, right.sequence if right else None,
                             left.command if left else "", right.command if right else "",
                             left.argument if left else "", right.argument if right else "",
                             left.response_value if left else None, right.response_value if right else None,
                             "command/state transition observed on only one client", polling=polling, scenario=item.scenario)
    notes = []
    status = "MATCH"
    if left.scenario != right.scenario:
        status = "SCENARIO_DIFF"
        notes.append("scenario names differ")
    if left.scenario_phase != right.scenario_phase:
        status = "SCENARIO_PHASE_DIFF"
        notes.append("clients observed different event phases; rerun at matched checkpoints")
    if (left.command_id, left.base) != (right.command_id, right.base):
        status = "COMMAND_DIFF"
        notes.append("command ID/base differs")
    elif left.command != right.command:
        status = "ARGUMENT_DIFF" if left.argument != right.argument else "WIRE_TEXT_DIFF"
        notes.append("wire command text differs")
    if left.response_value != right.response_value:
        if status == "MATCH": status = "RESPONSE_DIFF"
        notes.append("observed response values differ")
    if left.status != right.status:
        if status == "MATCH": status = "TRANSPORT_DIFF"
        notes.append(f"transport {left.status} vs {right.status}")
    if _profile(left) != _profile(right):
        if status == "MATCH": status = "TEST_CONDITION_DIFF"
        notes.append("response profiles differ")
    lf, rf = _framing(left), _framing(right)
    framing = (lf == rf) if lf is not None and rf is not None else None
    if framing is False:
        if status == "MATCH": status = "FRAMING_DIFF"
        notes.append("request/reply header or line ending differs")
    # Per-command exact bytes, independent of batching. IDs and whitespace remain evidence.
    if left.request_line_hex and right.request_line_hex and left.request_line_hex != right.request_line_hex:
        if status == "MATCH": status = "WIRE_TEXT_DIFF"
        notes.append("request line bytes differ")
    if left.reply_line_hex and right.reply_line_hex and left.reply_line_hex != right.reply_line_hex:
        if status == "MATCH": status = "WIRE_TEXT_DIFF"
        notes.append("reply line bytes differ")
    semantic = ((left.command_id, left.base.upper(), _meaning(left.argument), _response_meaning(left), left.status)
                == (right.command_id, right.base.upper(), _meaning(right.argument), _response_meaning(right), right.status)
                and _profile(left) == _profile(right) and left.scenario == right.scenario
                and left.scenario_phase == right.scenario_phase)
    return ComparisonRow(status, left.command_id if left.command_id == right.command_id else None,
                         left.sequence, right.sequence, left.command, right.command,
                         left.argument, right.argument, left.response_value, right.response_value,
                         "; ".join(notes) or "same command, response and observed transport status",
                         semantic, framing, polling, left.scenario)

def _token(item):
    return item.scenario, item.command_id, item.base.upper()

def _align(left, right, *, polling=False):
    matcher = SequenceMatcher(a=[_token(x) for x in left], b=[_token(x) for x in right], autojunk=False)
    rows = []
    for tag, a, b, c, d in matcher.get_opcodes():
        ls, rs = left[a:b], right[c:d]
        n = max(len(ls), len(rs))
        for i in range(n):
            rows.append(_row(ls[i] if i < len(ls) else None, rs[i] if i < len(rs) else None, polling=polling))
    return rows, matcher.ratio()

def _poll_signature(item):
    return (item.command, item.response_value, item.status, item.validation, item.modelled,
            _framing(item), item.profile_json, item.request_line_hex, item.reply_line_hex, item.scenario_phase)

def _poll_groups(items):
    groups = defaultdict(list)
    for item in items:
        if item.command_id in POLL_IDS:
            group = groups[(item.scenario, item.command_id)]
            # Collapse repeated identical observations only; retain every state/error transition.
            if not group or _poll_signature(group[-1]) != _poll_signature(item):
                group.append(item)
    return groups

def compare_transactions(transactions: Iterable[Transaction] | CaptureSnapshot,
                         original_label: str, python_label: str, *, ignore_polling=True,
                         messages: Iterable[CaptureMessage] = ()) -> ComparisonResult:
    snapshot = transactions if isinstance(transactions, CaptureSnapshot) else None
    items = list(snapshot.transactions if snapshot else transactions)
    messages = list(snapshot.messages if snapshot else messages)
    pending = len(snapshot.pending) if snapshot else 0
    # Completion order may differ across clients; compare receive order within each client.
    ordered = sorted(items, key=lambda x: (x.datagram_sequence, x.command_index, x.sequence))
    left_all = [x for x in ordered if x.client_label == original_label]
    right_all = [x for x in ordered if x.client_label == python_label]
    if ignore_polling:
        left = [x for x in left_all if x.command_id not in POLL_IDS]
        right = [x for x in right_all if x.command_id not in POLL_IDS]
    else:
        left, right = left_all, right_all
    rows, ratio = _align(left, right)
    if ignore_polling:
        lg, rg = _poll_groups(left_all), _poll_groups(right_all)
        for key in sorted(set(lg) | set(rg)):
            poll_rows, _ = _align(lg[key], rg[key], polling=True)
            rows.extend(poll_rows)
    lc, rc = Counter(x.command_id for x in left_all), Counter(x.command_id for x in right_all)
    counts = [{"command_id": cid, "original": lc[cid], "python": rc[cid]}
              for cid in sorted(set(lc) | set(rc)) if lc[cid] != rc[cid]]
    issues = []
    for message in messages:
        if message.level in {"PROTOCOL", "ERROR", "UNASSIGNED"}:
            issues.append({"kind": message.level, "client": message.client_label, "note": message.message})
    selected = left_all + right_all
    unknown = [x for x in items if x.client_label not in {original_label, python_label}]
    if unknown:
        issues.append({"kind": "UNASSIGNED", "note": f"{len(unknown)} transactions outside the selected pair"})
    faults, errors, unmodelled = 0, 0, 0
    for item in selected:
        try:
            scenario_state = json.loads(item.scenario_state_json)
        except (ValueError, TypeError):
            scenario_state = {}
        if isinstance(scenario_state, dict) and (scenario_state.get('active_faults') or scenario_state.get('latched_faults')):
            faults += 1
            issues.append({'kind': 'SYNTHETIC_FAULT', 'client': item.client_label,
                           'sequence': item.sequence, 'note': 'scenario fault present; equal replies do not verify client response'})
        if item.validation != "VALID" or item.status in {"SEND_ERROR", "STOPPED"}:
            errors += 1
            issues.append({"kind": "ERROR", "client": item.client_label, "sequence": item.sequence,
                           "note": f"{item.validation}; {item.status}"})
        elif item.status == "DROPPED" or item.response_value is None or (item.response_value or "").startswith("ERROR:") or "BROKEN_ECLIPSE" in item.reply_framing:
            faults += 1
            issues.append({"kind": "FAULT_OBSERVATION", "client": item.client_label, "sequence": item.sequence,
                           "note": item.note or item.status})
        if not item.modelled:
            unmodelled += 1
            issues.append({"kind": "UNMODELLED", "client": item.client_label, "sequence": item.sequence,
                           "note": "device effect not verified"})
    if original_label == python_label:
        issues.append({"kind": "ERROR", "note": "comparison labels must be distinct"})
    errors += sum(x['kind'] in {"ERROR", "PROTOCOL"} for x in issues if 'sequence' not in x)
    if snapshot and snapshot.metadata.get("isolated_client_state") is False:
        unmodelled += 1
        issues.append({"kind": "SHARED_STATE", "note": "shared state can contaminate the client comparison"})
    complete = bool(left_all and right_all and rows) and not pending
    framing_known = all(r.framing_equal is not None for r in rows if r.original_sequence is not None and r.python_sequence is not None)
    content_diff = any(r.status not in {"MATCH", "FRAMING_DIFF"} for r in rows)
    framing_diff = any(r.framing_equal is False for r in rows)
    matched = sum(r.status == "MATCH" for r in rows)
    diffs = len(rows) - matched
    if errors: verdict = "ERROR"
    elif not complete or unknown or any(x['kind'] == 'UNASSIGNED' for x in issues): verdict = "INCOMPLETE"
    elif diffs: verdict = "DIFFERENT"
    elif faults: verdict = "OBSERVATION_REQUIRED"
    elif unmodelled or not framing_known: verdict = "UNVERIFIED"
    else: verdict = "MATCH"
    health = "ERROR" if errors else "FAULT_OBSERVED" if faults else "OK" if complete else "INCOMPLETE"
    observations = snapshot.metadata.get("ui_observations", []) if snapshot else []
    gui = "NOT_CHECKED"
    if observations:
        filled = all(x.get('original') and x.get('python') for x in observations)
        equal = all(x.get('original') == x.get('python') and (not x.get('expected') or x['original'] == x['expected']) for x in observations)
        gui = "MANUAL_MATCH" if filled and equal else "MANUAL_DIFFERENT" if filled else "INCOMPLETE"
    def batching(seq):
        sizes = Counter(x.datagram_sequence for x in seq)
        return dict(Counter(sizes.values()))
    return ComparisonResult(
        original_label, python_label, len(left_all), len(right_all),
        sum(x.writable for x in left_all), sum(x.writable for x in right_all),
        sorted({x.command_id for x in left_all if not x.writable}), sorted({x.command_id for x in right_all if not x.writable}),
        sorted({x.command_id for x in left_all if x.writable}), sorted({x.command_id for x in right_all if x.writable}),
        ratio, matched, diffs, sum(r.status == 'ONLY_ORIGINAL' for r in rows), sum(r.status == 'ONLY_PYTHON' for r in rows),
        sorted(({x.command_id for x in left_all} ^ {x.command_id for x in right_all}) & POLL_IDS),
        ignore_polling, verdict, rows, counts,
        content_verdict=('DIFFERENT' if content_diff else 'MATCH') if complete else 'INCOMPLETE',
        semantic_verdict=('MATCH' if all(r.semantic_equal for r in rows) else 'DIFFERENT') if complete else 'INCOMPLETE',
        framing_verdict='DIFFERENT' if framing_diff else 'MATCH' if complete and framing_known else 'UNVERIFIED',
        transport_health=health, issues=issues, pending_datagrams=pending,
        session_id=snapshot.session_id if snapshot else '', snapshot_utc=snapshot.created_utc if snapshot else '',
        gui_verdict=gui, batching={original_label: batching(left_all), python_label: batching(right_all)},
    )
