from __future__ import annotations

"""Movement & look router.

Handles non-slash player inputs related to:
  - move through <door name>
  - move up/down stairs (aliases: move/go up|down[ stairs])
  - look / l
  - look at <name> / l at <name>

Extracted verbatim from the former inline blocks in server.py; message strings
and error wording must remain identical for test parity.
"""

from typing import List
from command_context import CommandContext, EmitFn

MESSAGE_OUT = 'message'


def try_handle_flow(ctx: CommandContext, sid: str | None, player_message: str, text_lower: str, emit: EmitFn) -> bool:
    world = ctx.world
    broadcast_to_room = ctx.broadcast_to_room

    if not sid or sid not in world.players:
        # Movement / look require an authenticated player (except bare 'look' could error earlier)
        pass
    try:
        player_obj = world.players.get(sid) if sid else None
        current_room = world.rooms.get(player_obj.room_id) if player_obj else None
    except Exception:
        player_obj = None
        current_room = None

    # --- Movement through named door ---
    if sid and player_obj and current_room and text_lower.startswith("move through "):
        from server import move_through_door  # type: ignore
        door_name = player_message.strip()[len("move through "):].strip()
        ok, err, emits, broadcasts = move_through_door(world, sid, door_name)
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Unable to move.'})
            return True
        for payload in emits:
            emit(MESSAGE_OUT, payload)
        for room_id, payload in broadcasts:
            broadcast_to_room(room_id, payload, exclude_sid=sid)
        return True

    # --- Stairs movement ---
    if sid and player_obj and current_room and text_lower in ("move up", "move upstairs", "move up stairs", "go up", "go up stairs"):
        from server import move_stairs  # type: ignore
        ok, err, emits, broadcasts = move_stairs(world, sid, 'up')
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Unable to move up.'})
            return True
        for payload in emits:
            emit(MESSAGE_OUT, payload)
        for room_id, payload in broadcasts:
            broadcast_to_room(room_id, payload, exclude_sid=sid)
        return True
    if sid and player_obj and current_room and text_lower in ("move down", "move downstairs", "move down stairs", "go down", "go down stairs"):
        from server import move_stairs  # type: ignore
        ok, err, emits, broadcasts = move_stairs(world, sid, 'down')
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Unable to move down.'})
            return True
        for payload in emits:
            emit(MESSAGE_OUT, payload)
        for room_id, payload in broadcasts:
            broadcast_to_room(room_id, payload, exclude_sid=sid)
        return True

    # --- Look / look at ---
    if text_lower == "look" or text_lower == "l" or text_lower.startswith("look ") or text_lower.startswith("l "):
        from server import _format_look, _resolve_player_in_room, _resolve_npcs_in_room, _ensure_npc_sheet, _resolve_object_in_room  # type: ignore
        from server import sessions, admins  # globals
        from server import _strip_quotes  # type: ignore
        if text_lower in ("look", "l"):
            desc = _format_look(world, sid)
            emit(MESSAGE_OUT, {'type': 'system', 'content': desc})
            return True
        if text_lower.startswith("look at ") or text_lower.startswith("l at "):
            try:
                lower_parts = player_message.strip()
                at_idx = lower_parts.lower().find(" at ")
                name_raw = lower_parts[at_idx + 4:].strip() if at_idx != -1 else ""
                name_raw = _strip_quotes(name_raw)
            except Exception:
                name_raw = ""
            if not name_raw:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: look at <name>'})
                return True
            player = world.players.get(sid) if sid else None
            if not player:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to look at someone.'})
                return True
            room = world.rooms.get(player.room_id)
            psid, pname = _resolve_player_in_room(world, room, name_raw)
            if psid and pname:
                try:
                    p = world.players.get(psid)
                    if p:
                        rel_lines: list[str] = []
                        try:
                            viewer_id = sessions.get(sid) if sid in sessions else None
                            target_uid = sessions.get(psid) if psid in sessions else None
                            if viewer_id and target_uid:
                                rel_to = (world.relationships.get(viewer_id, {}) or {}).get(target_uid)
                                rel_from = (world.relationships.get(target_uid, {}) or {}).get(viewer_id)
                                if rel_to:
                                    rel_lines.append(f"Your relation to {p.sheet.display_name}: {rel_to}")
                                if rel_from:
                                    rel_lines.append(f"{p.sheet.display_name}'s relation to you: {rel_from}")
                        except Exception:
                            pass
                        rel_text = ("\n" + "\n".join(rel_lines)) if rel_lines else ""
                        admin_aura = "\nRadiates an unspoken authority." if psid in admins else ""
                        emit(MESSAGE_OUT, {'type': 'system', 'content': f"[b]{p.sheet.display_name}[/b]\n{p.sheet.description}{admin_aura}{rel_text}"})
                        return True
                except Exception:
                    pass
            npcs = _resolve_npcs_in_room(room, [name_raw])
            if npcs:
                npc_name = npcs[0]
                sheet = world.npc_sheets.get(npc_name)
                if not sheet:
                    sheet = _ensure_npc_sheet(npc_name)
                rel_lines: list[str] = []
                try:
                    viewer_id = sessions.get(sid) if sid in sessions else None
                    npc_id = world.get_or_create_npc_id(npc_name)
                    if viewer_id and npc_id:
                        rel_to = (world.relationships.get(viewer_id, {}) or {}).get(npc_id)
                        rel_from = (world.relationships.get(npc_id, {}) or {}).get(viewer_id)
                        if rel_to:
                            rel_lines.append(f"Your relation to {sheet.display_name}: {rel_to}")
                        if rel_from:
                            rel_lines.append(f"{sheet.display_name}'s relation to you: {rel_from}")
                except Exception:
                    pass
                rel_text = ("\n" + "\n".join(rel_lines)) if rel_lines else ""
                needs_text = ""
                try:
                    if sid in admins:
                        h = int(max(0, min(100, int(getattr(sheet, 'hunger', 100) or 0))))
                        t = int(max(0, min(100, int(getattr(sheet, 'thirst', 100) or 0))))
                        s = int(max(0, min(100, int(getattr(sheet, 'socialization', 100) or 0))))
                        sl = int(max(0, min(100, int(getattr(sheet, 'sleep', 100) or 0))))
                        ap = int(getattr(sheet, 'action_points', 0) or 0)
                        qlen = len(getattr(sheet, 'plan_queue', []) or [])
                        curr = int(getattr(sheet, 'currency', 0) or 0)
                        sleep_state = " (sleeping)" if int(getattr(sheet, 'sleeping_ticks_remaining', 0) or 0) > 0 else ""
                        needs_text = f"\n[i][color=#888]Needs — Hunger {h}, Thirst {t}, Social {s}, Sleep {sl}{sleep_state} | AP {ap}, Plan {qlen} | Currency {curr}[/color][/i]"
                except Exception:
                    pass
                emit(MESSAGE_OUT, {'type': 'system', 'content': f"[b]{sheet.display_name}[/b]\n{sheet.description}{rel_text}{needs_text}"})
                return True
            obj, suggestions = _resolve_object_in_room(room, name_raw)
            if obj is not None:
                emit(MESSAGE_OUT, {'type': 'system', 'content': _format_object_summary(obj, world)})
                return True
            if suggestions:
                emit(MESSAGE_OUT, {'type': 'system', 'content': "Did you mean: " + ", ".join(suggestions) + "?"})
                return True
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"You don't see '{name_raw}' here."})
            return True
        # (other look-prefixed text falls through)

    return False
