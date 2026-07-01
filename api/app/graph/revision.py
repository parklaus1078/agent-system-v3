"""In-process per-project revision counter (Phase: night-bug #4).

Bumped by a SQLAlchemy commit listener (see db.py) whenever a project's nodes/edges change,
and exposed as a weak ETag by GET /graph. The 1.5s poll then sends If-None-Match and the
server short-circuits with 304 — no DB read, no serialization — when nothing changed. Single
process, single user: a plain dict guarded by a lock (the lifecycle background worker commits
on a different thread than request handlers). Resets to 0 on restart (handled by the BOOT
nonce in the ETag, so stale client ETags are invalidated)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_revs: dict[str, int] = {}


def get(pid: str) -> int:
    return _revs.get(pid, 0)  # lockless read; dict.get is atomic under the GIL


def bump(pid: str) -> int:
    with _lock:
        v = _revs.get(pid, 0) + 1
        _revs[pid] = v
        return v
