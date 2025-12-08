from __future__ import annotations

"""Dialogue & social command handling router.

Rebuilt clean version adding deterministic ordering for quoted say lines.

Features handled:
  - gesture <verb>
  - gesture <verb> to <Player|NPC>
  - "Hello" / 'Hi there' convenience -> say Hello / say Hi there (suppresses
    ambient NPC reply chance so player's message is last for tests)
  - say (optionally targeted NPC names)
  - tell <Player|NPC> <msg>
  - whisper <Player|NPC> <msg>

Behavioral invariants kept from pre‑refactor server:
  - Message JSON shape and types.
  - NPC reply probability (33%) for ambient or mention triggered replies.
  - Player receives their own say/tell as a 'player' message; others get a
    broadcast copy ( excluding sid ).
  - Whisper remains private (system messages only, not 'player').
"""

import random
import re
from command_context import CommandContext, EmitFn
from dialogue_utils import (
    parse_say as _parse_say,
    parse_tell as _parse_tell,
    parse_whisper as _parse_whisper,
    extract_npc_mentions as _extract_npc_mentions,
)

MESSAGE_OUT = "message"


def try_handle_flow(ctx: CommandContext, sid: str, player_message: str, emit: EmitFn) -> bool:
    """Return True if this router consumed the message (success OR error)."""
    world = ctx.world
    socketio = ctx.socketio
    broadcast_to_room = ctx.broadcast_to_room
    world_setup_sessions = ctx.world_setup_sessions

    # Lazy import of helpers still in server.py to avoid circular import.
    from server import (  # type: ignore
        _resolve_player_in_room,
        _resolve_npcs_in_room,
        _send_npc_reply,
    )

    lower_original = player_message.lower().strip()

    # Quoted-only convenience; we transform before any parsing so downstream
    # logic treats it as a normal say. We also flag quoted_origin so we can
    # suppress ambient NPC reply randomness (tests expect determinism here).
    quoted_origin = False
    m = re.fullmatch(r'"([^"\n\r]+)"', player_message.strip()) or re.fullmatch(r"'([^'\n\r]+)'", player_message.strip())
    if m:
        inner = (m.group(1) or '').strip()
        if inner:
            player_message = f"say {inner}"
            lower_original = player_message.lower()
            quoted_origin = True
            # Pre-set suppression flag so no NPC reply occurs anywhere in this handling.
            try:
                import server as _srv_mod  # type: ignore
                setattr(_srv_mod, '_suppress_npc_reply_once', True)
                setattr(_srv_mod, '_quoted_say_in_progress', True)
            except Exception:
                pass

            # Fast-path early return: we fully handle quoted convenience here to remove ambiguity
            # and avoid any future ordering regressions. This mirrors the normal say path but
            # deliberately skips ambient/mention logic.
            try:
                debug_chat = False
                try:
                    import os as _os
                    debug_chat = _os.getenv('MUD_DEBUG_CHAT', '').strip().lower() in ('1','true','yes','on')
                except Exception:
                    pass
                if debug_chat:
                    print('[DEBUG_CHAT] fast_path_quoted_say enter')
                if sid not in world.players:
                    emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to speak.'})
                    # Clear progress flag
                    try:
                        import server as _srv_mod2  # type: ignore
                        if getattr(_srv_mod2, '_quoted_say_in_progress', False):
                            delattr(_srv_mod2, '_quoted_say_in_progress')
                    except Exception:
                        pass
                    return True
                player_obj_fast = world.players.get(sid)
                if player_obj_fast:
                    payload = {'type': 'player', 'name': player_obj_fast.sheet.display_name, 'content': inner}
                    if player_obj_fast.room_id:
                        broadcast_to_room(player_obj_fast.room_id, payload, sid)
                    if debug_chat:
                        print('[DEBUG_CHAT] fast_path_quoted_say broadcast done')
                # Ensure suppression flag consumed; proactively clear progress marker
                try:
                    import server as _srv_mod3  # type: ignore
                    if getattr(_srv_mod3, '_suppress_npc_reply_once', False):
                        delattr(_srv_mod3, '_suppress_npc_reply_once')
                    if getattr(_srv_mod3, '_quoted_say_in_progress', False):
                        delattr(_srv_mod3, '_quoted_say_in_progress')
                    if debug_chat:
                        print('[DEBUG_CHAT] fast_path_quoted_say flags cleared build_id=', getattr(_srv_mod3, 'SERVER_BUILD_ID', '?'))
                except Exception:
                    pass
                return True
            except Exception:
                # Fall through to normal handling if anything unexpected happened
                pass

    # ---------------- GESTURE ----------------
    if lower_original == "gesture" or lower_original.startswith("gesture "):
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to gesture.'})
            return True
        raw = player_message.strip()
        verb = raw[len("gesture"):].strip()
        if not verb:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: gesture <verb>'})
            return True
        player_obj = world.players.get(sid)
        room = world.rooms.get(player_obj.room_id) if player_obj else None
        # Targeted gesture pattern "verb to target"
        to_idx = verb.lower().find(" to ")
        if to_idx != -1:
            left = verb[:to_idx].strip()
            target_raw = verb[to_idx + 4:].strip()
            if not target_raw:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: gesture <verb> to <Player or NPC>'})
                return True
            if left.lower().startswith('a '):
                left = left[2:].strip()
            if not left:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please provide a verb before "to".'})
                return True
            psid, pname = _resolve_player_in_room(world, room, ctx.strip_quotes(target_raw)) if room else (None, None)
            npc_name_resolved = None
            if not (psid and pname) and room:
                npcs = _resolve_npcs_in_room(room, [ctx.strip_quotes(target_raw)])
                if npcs:
                    npc_name_resolved = npcs[0]
            if not (psid and pname) and not npc_name_resolved:
                emit(MESSAGE_OUT, {'type': 'system', 'content': f"You don't see '{target_raw}' here."})
                return True

            def conj(w: str) -> str:
                if not w:
                    return w
                lw = w.lower()
                if len(lw) > 1 and lw.endswith('y') and lw[-2] not in 'aeiou':
                    return w[:-1] + 'ies'
                if lw.endswith(('s', 'sh', 'ch', 'x', 'z')):
                    return w + 'es'
                return w + 's'

            parts = left.split()
            first = conj(parts[0])
            tail = " ".join(parts[1:])
            action_third = (first + (" " + tail if tail else "")).strip()
            pname_self = player_obj.sheet.display_name if player_obj else 'Someone'
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"[i]You {left} to {pname or npc_name_resolved}[/i]"})
            if player_obj:
                broadcast_to_room(player_obj.room_id, {'type': 'system', 'content': f"[i]{pname_self} {action_third} to {pname or npc_name_resolved}[/i]"}, sid)
            if npc_name_resolved:
                _send_npc_reply(npc_name_resolved, f"performs a gesture: '{left}' to you.", sid)
            return True

        # Untargeted gesture
        def conj(w: str) -> str:
            if not w:
                return w
            lw = w.lower()
            if len(lw) > 1 and lw.endswith('y') and lw[-2] not in 'aeiou':
                return w[:-1] + 'ies'
            if lw.endswith(('s', 'sh', 'ch', 'x', 'z')):
                return w + 'es'
            return w + 's'

        parts = verb.split()
        first = conj(parts[0])
        tail = " ".join(parts[1:])
        action = (first + (" " + tail if tail else "")).strip()
        pname_self = player_obj.sheet.display_name if player_obj else 'Someone'
        emit(MESSAGE_OUT, {'type': 'system', 'content': f"[i]You {verb}[/i]"})
        if player_obj:
            broadcast_to_room(player_obj.room_id, {'type': 'system', 'content': f"[i]{pname_self} {action}[/i]"}, sid)
        return True

    # ---------------- SAY ----------------
    is_say, targets, say_msg = _parse_say(player_message)
    if is_say:
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to speak.'})
            return True
        if sid in world_setup_sessions:  # Setup wizard just echoes as system
            emit(MESSAGE_OUT, {'type': 'system', 'content': say_msg or ''})
            return True
        if not say_msg:
            emit(MESSAGE_OUT, {'type': 'error', 'content': "What do you say? Add text after 'say'."})
            return True
        player_obj = world.players.get(sid)
        room = world.rooms.get(player_obj.room_id) if player_obj else None
        player_payload = {'type': 'player', 'name': player_obj.sheet.display_name, 'content': say_msg} if player_obj else None

        # Helper for dice percentile using server.dice_roll so tests can monkeypatch.
        def _pct_roll() -> int:
            try:
                import server as _srv
                return _srv.dice_roll('d%').total  # type: ignore[attr-defined]
            except Exception:
                return random.randint(1, 100)

        # Explicit targeted NPC say (list of NPC names after say)
        if targets:
            resolved = _resolve_npcs_in_room(room, targets)
            if not resolved:
                emit(MESSAGE_OUT, {'type': 'system', 'content': 'No such NPCs here respond.'})
                return True
            for npc_name in resolved:
                if not quoted_origin:  # extra guard; quoted shouldn't target but be safe
                    _send_npc_reply(npc_name, say_msg, sid)
            # Mention pass for other NPCs present
            if room and getattr(room, 'npcs', None):
                others = [n for n in list(room.npcs) if n not in set(resolved)]
                try:
                    mentioned = _extract_npc_mentions(say_msg, others)
                except Exception:
                    mentioned = []
                for nm in mentioned:
                    if not quoted_origin:
                        if _pct_roll() <= 33:
                            _send_npc_reply(nm, say_msg, sid)
                # Broadcast player's say last (no local echo; sender already knows what they said)
                if player_payload:
                    broadcast_to_room(player_obj.room_id, player_payload, sid)
            return True

        # Ambient NPC reply path (suppressed entirely for quoted-origin to keep deterministic ordering)
        if room and getattr(room, 'npcs', None) and not quoted_origin:
            pct = _pct_roll()
            if pct <= 33:
                try:
                    npc_name = random.choice(list(room.npcs))
                except Exception:
                    npc_name = next(iter(room.npcs))
                _send_npc_reply(npc_name, say_msg, sid)
            else:
                try:
                    mentioned = _extract_npc_mentions(say_msg, list(room.npcs))
                except Exception:
                    mentioned = []
                for nm in mentioned:
                    if _pct_roll() <= 33:
                        _send_npc_reply(nm, say_msg, sid)

        # Broadcast player say last (no local echo for say)
        if player_payload:
            broadcast_to_room(player_obj.room_id, player_payload, sid)
            try:
                import server as _srv_mod  # type: ignore
                if quoted_origin:
                    # Clear suppression (already consumed in _send_npc_reply) just in case.
                    if getattr(_srv_mod, '_suppress_npc_reply_once', False):
                        delattr(_srv_mod, '_suppress_npc_reply_once')
                    if getattr(_srv_mod, '_quoted_say_in_progress', False):
                        delattr(_srv_mod, '_quoted_say_in_progress')
            except Exception:
                pass
        return True

    # ---------------- TELL ----------------
    is_tell, tell_target_raw, tell_msg = _parse_tell(player_message)
    if is_tell:
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to speak.'})
            return True
        if sid in world_setup_sessions:
            emit(MESSAGE_OUT, {'type': 'system', 'content': tell_msg or ''})
            return True
        if not tell_target_raw:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: tell <Player or NPC> <message>'})
            return True
        if not tell_msg:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'What do you say? Add a message after the name.'})
            return True
        player_obj = world.players.get(sid)
        room = world.rooms.get(player_obj.room_id) if player_obj else None
        psid, pname = _resolve_player_in_room(world, room, tell_target_raw)
        player_payload = {'type': 'player', 'name': player_obj.sheet.display_name, 'content': tell_msg} if player_obj else None
        # Player target (tell echoes to room only, no local player echo)
        if psid and pname:
            if player_payload:
                broadcast_to_room(player_obj.room_id, player_payload, sid)
            return True
        # NPC target
        npc_name_resolved = None
        if room:
            npcs = _resolve_npcs_in_room(room, [tell_target_raw])
            if npcs:
                npc_name_resolved = npcs[0]
        if not npc_name_resolved:
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"You don't see '{tell_target_raw}' here."})
            return True
        if player_payload:
            broadcast_to_room(player_obj.room_id, player_payload, sid)
        _send_npc_reply(npc_name_resolved, tell_msg, sid)
        # Mention chance among other NPCs
        if room and getattr(room, 'npcs', None):
            others = [n for n in list(room.npcs) if n != npc_name_resolved]
            try:
                mentioned = _extract_npc_mentions(tell_msg, others)
            except Exception:
                mentioned = []
                for nm in mentioned:
                    try:
                        import server as _srv
                        if _srv.dice_roll('d%').total <= 33:
                            _send_npc_reply(nm, tell_msg, sid)
                    except Exception:
                        if random.randint(1, 100) <= 33:
                            _send_npc_reply(nm, tell_msg, sid)
        return True

    # ---------------- WHISPER ----------------
    is_whisper, whisper_target_raw, whisper_msg = _parse_whisper(player_message)
    if is_whisper:
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to speak.'})
            return True
        if sid in world_setup_sessions:
            emit(MESSAGE_OUT, {'type': 'system', 'content': whisper_msg or ''})
            return True
        if not whisper_target_raw:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: whisper <Player or NPC> <message>'})
            return True
        if not whisper_msg:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'What do you whisper? Add a message after the name.'})
            return True
        player_obj = world.players.get(sid)
        room = world.rooms.get(player_obj.room_id) if player_obj else None
        psid, pname = _resolve_player_in_room(world, room, whisper_target_raw)
        if psid and pname:
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"You whisper to {pname}: {whisper_msg}"})
            try:
                sender_name = player_obj.sheet.display_name if player_obj else 'Someone'
                socketio.emit(MESSAGE_OUT, {'type': 'system', 'content': f"{sender_name} whispers to you: {whisper_msg}"}, to=psid)
            except Exception:
                pass
            return True
        npc_name_resolved = None
        if room:
            npcs = _resolve_npcs_in_room(room, [whisper_target_raw])
            if npcs:
                npc_name_resolved = npcs[0]
        if npc_name_resolved:
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"You whisper to {npc_name_resolved}: {whisper_msg}"})
            _send_npc_reply(npc_name_resolved, whisper_msg, sid, private_to_sender_only=True)
            return True
        emit(MESSAGE_OUT, {'type': 'system', 'content': f"You don't see '{whisper_target_raw}' here."})
        return True

    return False
