from __future__ import annotations

"""
Utilities for persisting the world state with optional debouncing.

Service modules should call save_world(world, state_path, debounced=True)
instead of calling world.save_to_file directly for non-critical writes.

This reduces I/O bursts during wizards and quick successive mutations.
"""

from typing import Dict
import os

from debounced_saver import DebouncedSaver

_savers: Dict[str, DebouncedSaver] = {}


def _get_interval_ms() -> int:
    try:
        return int((os.getenv('MUD_SAVE_DEBOUNCE_MS') or '300').strip())
    except Exception:
        return 300


def _get_saver_for(path: str) -> DebouncedSaver:
    s = _savers.get(path)
    if s is None:
        s = DebouncedSaver(lambda: _save_now(path), interval_ms=_get_interval_ms())
        _savers[path] = s
    return s


def _save_now(path: str) -> None:
    # Late import to avoid any circulars; world type duck-typed below
    from world import World  # noqa: F401  # imported for type context only
    # The action passed to DebouncedSaver calls back into the bound world.save_to_file
    # but we can't close over a world reference across module boundaries in a stable way.
    # Callers will provide the world for immediate saves; for debounced we create a closure
    # at call time using the passed-in world.
    pass  # placeholder; actual saving occurs via closures created in save_world


def save_world(world, state_path: str, debounced: bool = True) -> None:
    """Persist the world state.

    - debounced=True: coalesce multiple calls via DebouncedSaver per-state_path.
    - debounced=False: write immediately.
    Swallows errors to keep server responsive (best-effort persistence).
    """
    try:
        if debounced:
            # Create a one-off DebouncedSaver bound to this world+path if not cached
            s = _savers.get(state_path)
            if s is None:
                s = DebouncedSaver(lambda: _save_world_immediate(world, state_path), interval_ms=_get_interval_ms())
                _savers[state_path] = s
            s.debounce()
        else:
            _save_world_immediate(world, state_path)
    except Exception:
        # Best-effort only
        pass


def _save_world_immediate(world, state_path: str) -> None:
    try:
        world.save_to_file(state_path)
    except Exception:
        pass
