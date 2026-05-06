"""Durable, append-only session event log.

The session is NOT the model's context window. The brain re-reads any slice
on demand via `get_events`. If the harness restarts, `wake(session_id)`
recovers the entire log.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class SessionEvent:
    index: int
    session_id: str
    type: str
    payload: dict[str, Any]
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class SessionStore:
    """File-backed append-only event log."""

    def __init__(self, root_dir: str | os.PathLike[str] = "/tmp/sessions") -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, Lock] = {}
        self._global_lock = Lock()

    def create_session(self, session_id: str | None = None) -> str:
        sid = session_id or str(uuid.uuid4())
        self._log_path(sid).touch(exist_ok=True)
        return sid

    def wake(self, session_id: str) -> list[SessionEvent]:
        return self.get_events(session_id)

    def emit_event(self, session_id: str, type: str, payload: dict[str, Any]) -> SessionEvent:
        lock = self._lock_for(session_id)
        with lock:
            existing = self._count(session_id)
            event = SessionEvent(
                index=existing,
                session_id=session_id,
                type=type,
                payload=payload,
            )
            with self._log_path(session_id).open("a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
            return event

    def get_events(
        self,
        session_id: str,
        start: int = 0,
        end: int | None = None,
    ) -> list[SessionEvent]:
        path = self._log_path(session_id)
        if not path.exists():
            return []
        events: list[SessionEvent] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                events.append(SessionEvent(**data))
        return events[start:end]

    def get_session(self, session_id: str) -> dict[str, Any]:
        events = self.get_events(session_id)
        return {
            "session_id": session_id,
            "event_count": len(events),
            "last_event_ts": events[-1].ts if events else None,
        }

    def _log_path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_")
        return self._root / f"{safe}.jsonl"

    def _lock_for(self, session_id: str) -> Lock:
        with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = Lock()
            return self._locks[session_id]

    def _count(self, session_id: str) -> int:
        path = self._log_path(session_id)
        if not path.exists():
            return 0
        with path.open("rb") as f:
            return sum(1 for _ in f)
