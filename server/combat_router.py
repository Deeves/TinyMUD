"""Router for combat commands (currently /attack).

Follows Router → Service → Emit pattern. Non-blocking, minimal logic.
"""
from typing import List
from command_context import CommandContext
import combat_service

def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: List[str], raw: str, emit) -> bool:
    if cmd == "attack":
        if not sid:
            emit(ctx.message_out, {"type": "error", "content": "Session required."})
            return True
        if not args:
            emit(ctx.message_out, {"type": "error", "content": "Usage: /attack <target>"})
            return True
        target = args[0]
        handled, err, emits, broadcasts = combat_service.attack(
            ctx.world,
            ctx.state_path,
            sid,
            target,
            ctx.sessions,
            ctx.admins,
            ctx.broadcast_to_room,
            lambda ev, payload: emit(ev, payload)
        )
        for payload in emits:
            emit(ctx.message_out, payload)
        room_id = ctx.world.players.get(sid).room_id if sid in ctx.world.players else None
        if room_id:
            for ev, payload in broadcasts:
                ctx.broadcast_to_room(room_id, payload, exclude_sid=None)
        return handled
    elif cmd == "flee":
        if not sid:
            emit(ctx.message_out, {"type": "error", "content": "Session required."})
            return True
        handled, err, emits, broadcasts = combat_service.flee(
            ctx.world,
            ctx.state_path,
            sid,
            ctx.sessions,
            ctx.admins,
            ctx.broadcast_to_room,
            lambda ev, payload: emit(ev, payload)
        )
        for payload in emits:
            emit(ctx.message_out, payload)
        room_id = ctx.world.players.get(sid).room_id if sid in ctx.world.players else None
        if room_id:
            for ev, payload in broadcasts:
                ctx.broadcast_to_room(room_id, payload, exclude_sid=None)
        return handled
    return False
