from __future__ import annotations

"""
persistence_utils.py — Centralized persistence façade for world state.

🎯 KEY CONTRACT: This module is the ONLY authorized way to persist world state.
   All services, routers, and handlers MUST use save_world() instead of calling
   world.save_to_file() directly.

Why this matters:
- Prevents I/O storms during rapid mutations (wizards, bulk edits, GOAP planning).
- Provides a single point of control for persistence strategy (debounced vs immediate).
- Makes testing easier: mock this module instead of patching world.save_to_file everywhere.
- Future-proof: We can add compression, backup rotation, or remote sync here without
  touching dozens of call sites.

Public API:
- save_world(world, state_path, debounced=True): Standard save with optional debouncing.
- flush_all_saves(): Force immediate flush of all pending debounced saves (shutdown/critical).
- get_save_stats(): Return dict of save statistics for monitoring/debugging.

Design:
- Debounced saves use DebouncedSaver to coalesce rapid writes (default 300ms window).
- Immediate saves bypass debouncing for critical operations (auth, admin commands).
- All errors are swallowed (best-effort) to keep the game responsive.
- Per-path DebouncedSaver instances are cached in module-level _savers dict.
"""

from typing import Dict, Optional, Any
import os
import time

from debounced_saver import DebouncedSaver

# Global registry of debounced savers, keyed by state_path.
# Each path gets its own DebouncedSaver instance to handle multiple worlds.
_savers: Dict[str, DebouncedSaver] = {}

# Tracking stats for monitoring and debugging
_stats = {
    'debounced_calls': 0,
    'immediate_calls': 0,
    'errors': 0,
    'last_save_time': None,
}


def _get_interval_ms() -> int:
    """Read debounce interval from environment, default 300ms."""
    try:
        return int((os.getenv('MUD_SAVE_DEBOUNCE_MS') or '300').strip())
    except Exception:
        return 300


def save_world(world, state_path: str, debounced: bool = True) -> None:
    """Persist the world state using the centralized persistence façade.

    This is the ONLY function that services and routers should call to save world state.
    Direct calls to world.save_to_file() are prohibited (see module docstring).

    Args:
        world: The World instance to persist.
        state_path: Absolute path to the JSON state file.
        debounced: If True (default), coalesce rapid saves via DebouncedSaver.
                   If False, write immediately (use for critical operations like logout).

    Usage patterns:
        # Standard pattern for most mutations (wizards, room edits, etc.)
        save_world(world, state_path, debounced=True)

        # Critical saves that must complete before continuing (auth, admin resets)
        save_world(world, state_path, debounced=False)

        # Using CommandContext (preferred in routers)
        from persistence_utils import save_world
        save_world(ctx.world, ctx.state_path, debounced=True)

    Error handling:
        All exceptions are swallowed to maintain server responsiveness. If persistence
        fails, the server continues running. Check logs for save errors.
    """
    try:
        if debounced:
            _stats['debounced_calls'] += 1
            # Get or create a DebouncedSaver for this path
            s = _savers.get(state_path)
            if s is None:
                # Bind world and path in the closure passed to DebouncedSaver
                s = DebouncedSaver(
                    lambda: _save_world_immediate(world, state_path),
                    interval_ms=_get_interval_ms()
                )
                _savers[state_path] = s
            s.debounce()
        else:
            _stats['immediate_calls'] += 1
            _save_world_immediate(world, state_path)
    except Exception:
        _stats['errors'] += 1
        # Best-effort only; server stays up even if saves fail


def _save_world_immediate(world, state_path: str) -> None:
    """Internal helper: perform the actual save to disk.

    This is the only place in the entire codebase that calls world.save_to_file().
    If you're tempted to call world.save_to_file() elsewhere, use save_world() instead!
    """
    try:
        world.save_to_file(state_path)
        _stats['last_save_time'] = time.time()
    except Exception:
        _stats['errors'] += 1
        # Swallow to maintain responsiveness


def flush_all_saves() -> None:
    """Force immediate flush of all pending debounced saves.

    Use this during:
    - Server shutdown (atexit handler)
    - Before critical operations that need consistent state
    - In tests that need to verify save side effects

    This is safe to call multiple times; already-flushed savers are no-ops.
    """
    for saver in _savers.values():
        try:
            saver.flush()
        except Exception:
            pass


def get_save_stats() -> Dict[str, Any]:
    """Return persistence statistics for monitoring and debugging.

    Returns:
        Dict with keys:
        - debounced_calls: Count of debounced save_world calls
        - immediate_calls: Count of immediate save_world calls
        - errors: Count of save errors (logged but swallowed)
        - last_save_time: Unix timestamp of most recent successful save (or None)
        - active_savers: Number of DebouncedSaver instances in the registry
    """
    return {
        **_stats,
        'active_savers': len(_savers),
    }
