"""interaction_router.py

Non-slash chat flow router for the plain text object interaction & crafting
feature ("interact with <object>").  Extracted from the monolithic
`server.py` to keep the core event handler small and composable alongside
`dialogue_router` and `movement_router`.

Contract:
    try_handle_flow(ctx, sid, player_message, text_lower, emit) -> bool
        Returns True if this router handled (and fully responded to) the
        incoming player message. When True the caller should stop further
        routing of this message.

Behaviors migrated (parity focused):
 1. Continuation of an active interaction session (sid present in
    ctx.interaction_sessions) via interaction_service.handle_interaction_input.
 2. New invocation starting with the phrase "interact with " which opens a
    menu of available affordances for the resolved object.

Notes:
 - All world mutations (inventory moves, crafting, container search, etc.)
   happen inside interaction_service. After successful handling we use the
   centralized persistence façade (save_world) to persist changes.
 - Messages / error wording intentionally preserved from the original in-line
   implementation (service already centralizes most text output).
 - This router purposefully avoids any socket.io calls other than emit; room
   broadcasts come back from the service as (room_id, payload) tuples.
"""

from __future__ import annotations

from typing import Callable

from command_context import CommandContext
from persistence_utils import save_world
from interaction_service import begin_interaction, handle_interaction_input


def try_handle_flow(
    ctx: CommandContext,
    sid: str | None,
    player_message: str,
    text_lower: str,
    emit: Callable[[str, dict], None],
) -> bool:
    # Fast exits: need a real sid & authenticated player for all flows
    if not sid:
        return False

    world = ctx.world
    interaction_sessions = ctx.interaction_sessions
    MESSAGE_OUT = ctx.message_out

    # 1. Active multi-turn interaction session continuation
    if sid in interaction_sessions:
        handled, err, emits_list, broadcasts_list = handle_interaction_input(world, sid, player_message, interaction_sessions)
        if handled:
            for payload in emits_list:
                emit(MESSAGE_OUT, payload)
            # Room broadcasts (room_id, payload)
            try:
                for room_id, payload in (broadcasts_list or []):
                    ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
            except Exception:
                pass
            # Persistence (debounced + best-effort immediate)
            ctx.mark_world_dirty()
            try:
                save_world(world, ctx.state_path, debounced=False)
            except Exception:
                pass
            return True
        # If not handled, fall through (the session might have cancelled and message can proceed)

    # 2. New interaction flow start: "interact with <object>"
    if text_lower.startswith('interact with '):
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first.'})
            return True
        # Extract raw object name preserving case (everything after first space*2)
        raw_name = player_message[len('interact with '):].strip()
        if not raw_name:
            emit(MESSAGE_OUT, {'type': 'error', 'content': "Usage: interact with <object name>"})
            return True
        player = world.players.get(sid)
        room = world.rooms.get(player.room_id) if player else None
        ok, err, emits_list, broadcasts_list = begin_interaction(world, sid, room, raw_name, interaction_sessions)
        if not ok:
            emit(MESSAGE_OUT, {'type': 'system', 'content': err or 'Unable to interact.'})
            return True
        for payload in emits_list:
            emit(MESSAGE_OUT, payload)
        # Room broadcasts (room_id, payload)
        try:
            for room_id, payload in (broadcasts_list or []):
                ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
        except Exception:
            pass
        # No immediate persistence needed (session only) but harmless to debounce.
        ctx.mark_world_dirty()
        return True

    return False
