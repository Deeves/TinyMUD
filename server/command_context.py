from __future__ import annotations

"""Shared command routing context.

This lightweight dataclass lets the monolithic `server.py` shed inline command
logic. Routers receive a `CommandContext` plus the parsed command tokens and
emit/broadcast helpers. Keeping it deliberately small + explicit makes
dependencies (world state, helper functions) visible and easier to unit test.

Incremental refactor strategy:
 1. Extract one command family at a time (admin, auth, dialogue, movement...).
 2. Keep behavior identical (string messages, error wording) so existing tests
    continue to pass while we carve the file apart.
 3. When all families are migrated, the slash command switch in `server.py`
    shrinks to a tiny dispatcher registry.

Future niceties (not done yet):
  - Per‑router unit tests (call handle() with a fake context + fake emit).
  - Metrics / timing decorators around handlers.
  - Plug‑in discovery via entry points or a simple folder scan.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Set, Protocol


class BroadcastFn(Protocol):
    """Protocol for broadcast_to_room with optional exclude_sid.
    
    Supports both calling patterns:
      - broadcast_to_room(room_id, payload, exclude_sid=sid)  # keyword
      - broadcast_to_room(room_id, payload, sid)             # positional
    """
    def __call__(self, room_id: str, payload: Dict[str, Any], exclude_sid: str | None = None) -> None: ...


EmitFn = Callable[[str, Dict[str, Any]], None]


@dataclass(slots=True)
class CommandContext:
    # Core world + persistence
    world: Any
    state_path: str
    saver: Any  # DebouncedSaver

    # Networking / IO
    socketio: Any
    message_out: str

    # Session + privilege tracking
    sessions: Dict[str, str]
    admins: Set[str]
    pending_confirm: Dict[str, str]
    # Wizard / flow session state dicts (progressively migrated from server globals)
    world_setup_sessions: Dict[str, dict]
    barter_sessions: Dict[str, dict]
    trade_sessions: Dict[str, dict]
    interaction_sessions: Dict[str, dict]

    # Helper callables (dependency‑injected to avoid circular imports)
    strip_quotes: Callable[[str], str]
    resolve_player_sid_global: Callable[[Any, str], tuple[bool, str | None, str | None, str | None]]
    normalize_room_input: Callable[[str | None, str], tuple[bool, str | None, str | None]]
    resolve_room_id_fuzzy: Callable[[str | None, str], tuple[bool, str | None, str | None]]

    # Services / operations
    teleport_player: Callable[..., tuple[bool, str | None, list, list]]
    handle_room_command: Callable[..., tuple[bool, str | None, list, list]]
    handle_npc_command: Callable[..., tuple[bool, str | None, list, list]]
    handle_faction_command: Callable[..., tuple[bool, str | None, list, list]]

    # Admin / purge helpers
    purge_prompt: Callable[[], dict]
    execute_purge: Callable[[str], Any]
    redact_sensitive: Callable[[Any], Any]

    # Safety helpers
    is_confirm_yes: Callable[[str], bool]
    is_confirm_no: Callable[[str], bool]

    # Misc constants / utilities used by handlers (injected for testability)
    broadcast_to_room: BroadcastFn

    # Optional: dice / other utilities could be added later.

    def mark_world_dirty(self) -> None:
        """Request a debounced save after mutation (ignore failures)."""
        try:  # pragma: no cover - defensive
            if self.saver:
                self.saver.debounce()
        except Exception:
            pass

