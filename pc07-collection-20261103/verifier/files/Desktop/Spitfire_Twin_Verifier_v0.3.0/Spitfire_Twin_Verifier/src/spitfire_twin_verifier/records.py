"""Session-scoped capture, immutable snapshots, and JSONL evidence."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import threading
from typing import Callable
import uuid

@dataclass(frozen=True, slots=True)
class Transaction:
    sequence: int
    datagram_sequence: int
    timestamp_utc: str
    client_key: str
    client_label: str
    source_ip: str
    source_port: int
    command_index: int
    command_id: int
    command: str
    base: str
    argument: str
    request_hex: str
    response_value: str | None
    response_hex: str
    latency_ms: float
    status: str
    note: str = ""
    session_id: str = ""
    sent_utc: str = ""
    processing_ms: float = 0.0
    configured_delay_ms: int = 0
    validation: str = "VALID"
    modelled: bool = True
    effect: str = "query"
    profile_json: str = "{}"
    scenario: str = ""
    request_line_hex: str = ""
    reply_line_hex: str = ""
    request_framing: str = ""
    reply_framing: str = ""
    scenario_time_ms: float | None = None
    scenario_phase: int = 0
    scenario_state_json: str = "{}"

    @property
    def writable(self) -> bool:
        return self.command_id >= 2000

@dataclass(frozen=True, slots=True)
class CaptureMessage:
    timestamp_utc: str
    level: str
    message: str
    source_ip: str = ""
    source_port: int = 0
    raw_hex: str = ""
    session_id: str = ""
    client_label: str = ""
    details_json: str = "{}"

@dataclass(frozen=True)
class CaptureSnapshot:
    session_id: str
    created_utc: str
    transactions: tuple[Transaction, ...]
    messages: tuple[CaptureMessage, ...]
    pending: tuple[dict, ...] = ()
    metadata: dict = field(default_factory=dict)

    def save_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            header = {"type": "session", "session_id": self.session_id,
                      "snapshot_utc": self.created_utc, "metadata": self.metadata,
                      "pending": list(self.pending)}
            stream.write(json.dumps(header, ensure_ascii=False) + "\n")
            for item in self.transactions:
                stream.write(json.dumps({"type": "transaction", **asdict(item)}, ensure_ascii=False) + "\n")
            for item in self.messages:
                stream.write(json.dumps({"type": "message", **asdict(item)}, ensure_ascii=False) + "\n")

class CaptureStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: list[Callable] = []
        self._transactions: list[Transaction] = []
        self._messages: list[CaptureMessage] = []
        self._pending: dict[int, dict] = {}
        self._metadata: dict = {}
        self._sequence = self._datagram_sequence = 0
        self.session_id = uuid.uuid4().hex
        self.scenario = ""

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    @contextmanager
    def locked(self):
        with self._lock:
            yield

    def set_metadata(self, **fields) -> None:
        with self._lock:
            self._metadata.update(copy.deepcopy(fields))

    def mark_scenario(self, name: str) -> None:
        with self._lock:
            self.scenario = name.strip()
            self.message("SCENARIO", self.scenario or "unnamed")

    def next_datagram_sequence(self) -> int:
        with self._lock:
            self._datagram_sequence += 1
            return self._datagram_sequence

    def begin_pending(self, seq: int, **fields) -> None:
        with self._lock:
            self._pending[seq] = copy.deepcopy(fields)

    def finish_pending(self, seq: int) -> None:
        with self._lock:
            self._pending.pop(seq, None)

    def add_listener(self, callback: Callable) -> None:
        with self._lock:
            self._listeners.append(callback)

    def _notify(self, item) -> None:
        # An optional GUI listener must never break acquisition.
        for listener in tuple(self._listeners):
            try:
                listener(item)
            except Exception:
                pass

    def add_transaction(self, **fields) -> Transaction | None:
        with self._lock:
            fields.setdefault("session_id", self.session_id)
            if fields["session_id"] != self.session_id:
                return None
            self._sequence += 1
            item = Transaction(sequence=self._sequence, **fields)
            self._transactions.append(item)
            self._notify(item)
            return item

    def message(self, level: str, message: str, *, source_ip="", source_port=0,
                raw_hex="", client_label="", details=None, session_id=None) -> CaptureMessage | None:
        with self._lock:
            sid = session_id or self.session_id
            if sid != self.session_id:
                return None
            item = CaptureMessage(self.now(), level, message, source_ip, source_port,
                                  raw_hex, sid, client_label,
                                  json.dumps(details or {}, ensure_ascii=False, sort_keys=True))
            self._messages.append(item)
            self._notify(item)
            return item

    def transactions(self) -> list[Transaction]:
        with self._lock:
            return list(self._transactions)

    def messages(self) -> list[CaptureMessage]:
        with self._lock:
            return list(self._messages)

    def snapshot(self) -> CaptureSnapshot:
        with self._lock:
            return CaptureSnapshot(self.session_id, self.now(), tuple(self._transactions),
                                   tuple(self._messages), tuple(copy.deepcopy(list(self._pending.values()))),
                                   copy.deepcopy(self._metadata))

    def clear(self) -> None:
        with self._lock:
            self._transactions.clear()
            self._messages.clear()
            self._pending.clear()
            self._metadata.clear()
            self._sequence = self._datagram_sequence = 0
            self.session_id = uuid.uuid4().hex
            self.scenario = ""

    def save_jsonl(self, path: Path) -> None:
        self.snapshot().save_jsonl(path)
