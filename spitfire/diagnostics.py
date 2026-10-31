"""Optional, bounded, asynchronous communication evidence (never command logic).

Only the writer thread touches files. Producers never wait for disk or queue
space. Queue loss and writer failures are visible; this is not a lossless audit
or a packet capture. A session owns its files so concurrent apps cannot rotate
each other's logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
from queue import Queue, Empty, Full
import sys
from threading import Event, Lock, Thread
import time
from uuid import uuid4


@dataclass(frozen=True)
class DiagnosticConfig:
    directory: Path
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 4
    queue_capacity: int = 4096

    def __post_init__(self):
        for name, low, high in (("max_bytes", 4096, 1024**3),
                                ("backup_count", 0, 100),
                                ("queue_capacity", 1, 65536)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}..{high}")


class CommunicationLog:
    def __init__(self, config: DiagnosticConfig, *, mode="udp",
                 monotonic_ns=time.monotonic_ns, wall_ns=time.time_ns):
        self.config = config
        self.session_id = uuid4().hex
        self.path = Path(config.directory) / f"comm-{self.session_id}.jsonl"
        self._monotonic_ns, self._wall_ns = monotonic_ns, wall_ns
        self._origin = monotonic_ns()
        self._queue = Queue(maxsize=config.queue_capacity)
        self._lock = Lock()
        self._closing = Event()
        self._done = Event()
        self._sequence = self._dropped = self._written = self._oversized = 0
        self._error = None
        self._stream = None
        self._size = 0
        self._thread = Thread(target=self._run, name="spitfire-comm-log", daemon=True)
        self.emit("session_start", mode=mode, python=platform.python_version(),
                  platform=platform.platform(), max_bytes=config.max_bytes,
                  backup_count=config.backup_count, queue_capacity=config.queue_capacity)
        self._thread.start()

    @property
    def status(self):
        with self._lock:
            return dict(path=str(self.path), session_id=self.session_id,
                        dropped=self._dropped, written=self._written,
                        oversized=self._oversized, error=self._error,
                        closed=self._done.is_set())

    def emit(self, event, **fields):
        # Fields are immutable scalars/bytes or newly constructed snapshots.
        # No serialization, file work, callbacks, or blocking queue puts here.
        try:
            with self._lock:
                if self._closing.is_set() or self._error:
                    return
                self._sequence += 1
                record = dict(schema_version=1, session_id=self.session_id,
                              sequence=self._sequence, event=event,
                              wall_time_ns=self._wall_ns(),
                              elapsed_ns=self._monotonic_ns() - self._origin,
                              dropped_total=self._dropped, **fields)
                try:
                    self._queue.put_nowait(record)
                except Full:
                    self._dropped += 1
        except Exception as exc:
            self._fail(exc)

    def _fail(self, exc):
        with self._lock:
            if self._error:
                return
            self._error = f"{type(exc).__name__}: {exc}"
        try:
            print(f"Communication log disabled: {self._error}", file=sys.stderr)
        except Exception:
            pass

    def _open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("xb")

    def _rotate(self):
        self._stream.close()  # Windows requires closing before renaming.
        count = self.config.backup_count
        if count:
            Path(f"{self.path}.{count}").unlink(missing_ok=True)
            for index in range(count - 1, 0, -1):
                old = Path(f"{self.path}.{index}")
                if old.exists():
                    old.replace(f"{self.path}.{index + 1}")
            self.path.replace(f"{self.path}.1")
        else:
            self.path.unlink()
        self._stream = self.path.open("xb")
        self._size = 0

    def _write(self, record):
        record = dict(record)
        ns = record["wall_time_ns"]
        record["utc_time"] = datetime.fromtimestamp(ns // 10**9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{ns % 10**9:09d}Z"
        payload = record.pop("payload_bytes", None)
        if payload is not None:
            record.update(payload_hex=payload.hex(), payload_text=payload.decode("latin1"),
                          captured_bytes=len(payload))
        data = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(data) > self.config.max_bytes:
            # Never split a JSON record or exceed the advertised byte bound.
            record = {key: record[key] for key in ("schema_version", "session_id", "sequence",
                       "event", "wall_time_ns", "utc_time", "elapsed_ns", "dropped_total")}
            record.update(record_omitted="exceeds max_bytes", original_record_bytes=len(data))
            data = (json.dumps(record) + "\n").encode("utf-8")
            with self._lock:
                self._oversized += 1
        if self._size + len(data) > self.config.max_bytes:
            self._rotate()
        self._stream.write(data)
        self._stream.flush()
        self._size += len(data)
        with self._lock:
            self._written += 1

    def _run(self):
        try:
            self._open()
            while True:
                try:
                    record = self._queue.get(timeout=0.05)
                except Empty:
                    if self._closing.is_set():
                        break
                    continue
                self._write(record)
            # Serialized after draining, even when the producer queue was full.
            self._write(dict(schema_version=1, session_id=self.session_id,
                             sequence=self._sequence + 1, event="session_end",
                             wall_time_ns=self._wall_ns(), elapsed_ns=self._monotonic_ns() - self._origin,
                             dropped_total=self._dropped, oversized_total=self._oversized))
        except Exception as exc:
            self._fail(exc)
        finally:
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception as exc:
                    self._fail(exc)
            self._done.set()

    def close(self, timeout=1.0):
        with self._lock:
            self._closing.set()
        self._thread.join(timeout=max(0, timeout))
        return self._done.is_set()


def notify_observer(observer, event, **fields):
    """A diagnostic observer cannot change transport success/failure behavior."""
    if observer is not None:
        try:
            observer(event, **fields)
        except Exception:
            pass
