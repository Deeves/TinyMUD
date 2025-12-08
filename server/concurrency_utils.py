"""
Small concurrency helpers for cooperative (eventlet) and threaded environments.

Why this exists:
- Our server runs under Flask-SocketIO with eventlet where multiple greenlets can
  interleave on I/O boundaries. Global dicts like sessions/admins and world
  mutations can suffer from racey interleavings under high activity.
- We provide lightweight, named locks that work with eventlet (if available)
  and gracefully fall back to threading locks otherwise. Names let us coordinate
  critical sections across modules without wiring lock objects everywhere.

Usage:
    from concurrency_utils import atomic, atomic_many, get_lock

    # Single lock
    with atomic('world'):
        world.create_user(...)
        world.add_player(...)

    # Multiple related shared structures (deadlock-safe via name ordering)
    with atomic_many(['world', 'sessions', 'admins']):
        ... mutate all three ...

Design notes:
- Locks are greenlet-friendly when eventlet is present (Semaphore). We acquire
  them in a deterministic sorted order in atomic_many() to avoid deadlocks.
- This module keeps zero state outside a single global lock registry, which is
  itself protected by a plain threading.RLock (not monkey-patched by eventlet).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List

# Prefer eventlet's Semaphore when available for cooperative concurrency
try:  # pragma: no cover - environment dependent
    from eventlet.semaphore import Semaphore as _Lock
except Exception:  # pragma: no cover - CI without eventlet
    from threading import RLock as _Lock  # type: ignore

from threading import RLock as _RegistryLock  # always OK for guarding the map

_LOCKS: Dict[str, Any] = {}
_LOCKS_GUARD = _RegistryLock()


def get_lock(name: str) -> Any:
    """Return a process-wide lock for the given name, creating it if needed.

    Using a registry keeps callers from passing lock objects around while still
    allowing cross-module coordination on shared data structures by name.
    """
    # Double-checked creation is fine under the GIL; we still guard creation
    # explicitly to be clear and portable.
    lk = _LOCKS.get(name)
    if lk is not None:
        return lk
    with _LOCKS_GUARD:
        lk = _LOCKS.get(name)
        if lk is None:
            lk = _Lock()
            _LOCKS[name] = lk
        return lk


@contextmanager
def atomic(name: str) -> Iterator[None]:
    """Context manager that acquires a named lock for the duration.

    Example:
        with atomic('sessions'):
            sessions[sid] = user_id
    """
    lk = get_lock(name)
    lk.acquire()
    try:
        yield
    finally:
        try:
            lk.release()
        except Exception:
            # Be defensive; releasing a Semaphore shouldn't fail in normal cases.
            pass


@contextmanager
def atomic_many(names: Iterable[str]) -> Iterator[None]:
    """Acquire multiple named locks in a stable order to avoid deadlocks.

    Locks are sorted by name to guarantee a consistent acquisition order.
    """
    to_acquire: List[Any] = [get_lock(n) for n in sorted(set(names))]
    # Acquire all
    for lk in to_acquire:
        lk.acquire()
    try:
        yield
    finally:
        # Release in reverse order
        for lk in reversed(to_acquire):
            try:
                lk.release()
            except Exception:
                pass
