"""NPC admin operations for /npc commands.

Supports:
    - /npc add <room_id> | <npc name> | <npc description>
    - /npc remove <npc name>  (removes from the admin's current room)

Backward compatibility:
    - /npc add <room_id> <npc name...>
    - /npc remove <room_id> <npc name...>
    - /npc setdesc <npc name> | <description>
"""

from __future__ import annotations

from typing import List, Tuple

from world import CharacterSheet
from id_parse_utils import (
    strip_quotes as _strip_quotes,
    parse_pipe_parts as _parse_pipe_parts,
    resolve_room_id as _resolve_room_id,
    resolve_npcs_in_room as _resolve_npcs_in_room,
)


def _normalize_room_input(world, sid: str | None, typed: str) -> tuple[bool, str | None, str | None]:
    t = _strip_quotes(typed or "")
    if t.lower() == 'here':
        if not sid or sid not in getattr(world, 'players', {}):
            return False, 'You are nowhere.', None
        player = world.players.get(sid)
        rid = getattr(player, 'room_id', None)
        if not rid:
            return False, 'You are nowhere.', None
        return True, None, rid
    return True, None, t


def handle_npc_command(world, state_path: str, sid: str | None, args: list[str]) -> Tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    if not args:
        return True, 'Usage: /npc <add|remove|setdesc> ...', emits

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == 'add':
        # New syntax: /npc add <room_id> | <npc name> | <npc description>
        parts_joined = " ".join(sub_args)
        if '|' in parts_joined:
            try:
                room_in, name_in, desc_in = _parse_pipe_parts(parts_joined, expected=3)
            except Exception:
                return True, 'Usage: /npc add <room_id> | <npc name> | <npc description>', emits
            room_in = _strip_quotes(room_in)
            name_in = _strip_quotes(name_in)
            desc_in = desc_in.strip()
            if not room_in or not name_in:
                return True, 'Usage: /npc add <room_id> | <npc name> | <npc description>', emits
            okn, errn, norm = _normalize_room_input(world, sid, room_in)
            if not okn:
                return True, errn, emits
            val = norm if isinstance(norm, str) else room_in
            rok, rerr, room_res = _resolve_room_id(world, val)
            if not rok or not room_res:
                return True, (rerr or f"Room '{room_in}' not found."), emits
            room = world.rooms.get(room_res)
            if not room:
                return True, f"Room '{room_res}' not found.", emits
            npc_name = name_in
            room.npcs.add(npc_name)
            # Ensure NPC sheet with provided description (create or update)
            sheet = world.npc_sheets.get(npc_name)
            if sheet is None:
                sheet = CharacterSheet(display_name=npc_name, description=(desc_in or f"An NPC named {npc_name}."))
                world.npc_sheets[npc_name] = sheet
            else:
                if desc_in:
                    sheet.description = desc_in
            # Ensure a stable id for this NPC
            try:
                world.get_or_create_npc_id(npc_name)
            except Exception:
                pass
            _save_silent(world, state_path)
            emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added to room '{room_res}'."})
            return True, None, emits

        # Legacy syntax fallback: /npc add <room_id> <npc name...>
        if len(sub_args) < 2:
            return True, 'Usage: /npc add <room_id> | <npc name> | <npc description>', emits
        room_id = _strip_quotes(sub_args[0])
        npc_name = _strip_quotes(" ".join(sub_args[1:]).strip())
        okn, errn, norm = _normalize_room_input(world, sid, room_id)
        if not okn:
            return True, errn, emits
        val = norm if isinstance(norm, str) else room_id
        rok, rerr, room_res = _resolve_room_id(world, val)
        if not rok or not room_res:
            return True, (rerr or f"Room '{room_id}' not found."), emits
        room = world.rooms.get(room_res)
        if not room:
            return True, f"Room '{room_res}' not found.", emits
        room.npcs.add(npc_name)
        if npc_name not in world.npc_sheets:
            world.npc_sheets[npc_name] = CharacterSheet(display_name=npc_name, description=f"An NPC named {npc_name}.")
        try:
            world.get_or_create_npc_id(npc_name)
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added to room '{room_res}'."})
        return True, None, emits

    if sub == 'remove':
        # New default: remove by name from the admin's current room
        parts_joined = " ".join(sub_args).strip()
        if parts_joined and '|' not in parts_joined and len(sub_args) >= 1 and sid is not None:
            npc_in = _strip_quotes(parts_joined)
            player = world.players.get(sid)
            if not player:
                return True, 'Please authenticate first.', emits
            room = world.rooms.get(player.room_id)
            if not room:
                return True, 'You are nowhere.', emits
            # Fuzzy resolve within current room
            resolved = _resolve_npcs_in_room(room, [npc_in])
            if not resolved:
                return True, f"NPC '{npc_in}' not found in this room.", emits
            npc_name = resolved[0]
            room.npcs.discard(npc_name)
            _save_silent(world, state_path)
            emits.append({'type': 'system', 'content': f"NPC '{npc_name}' removed from room '{room.id}'."})
            return True, None, emits

        # Legacy/explicit: /npc remove <room_id> | <npc name>  or  /npc remove <room_id> <npc name...>
        if '|' in parts_joined:
            try:
                room_in, npc_in = _parse_pipe_parts(parts_joined, expected=2)
            except Exception:
                return True, 'Usage: /npc remove <room_id> | <npc name>', emits
            room_in = _strip_quotes(room_in)
            npc_in = _strip_quotes(npc_in)
        else:
            if len(sub_args) < 2:
                return True, 'Usage: /npc remove <npc name>', emits
            room_in = _strip_quotes(sub_args[0])
            npc_in = _strip_quotes(" ".join(sub_args[1:]).strip())
        okn, errn, norm = _normalize_room_input(world, sid, room_in)
        if not okn:
            return True, errn, emits
        val = norm if isinstance(norm, str) else room_in
        rok, rerr, room_res = _resolve_room_id(world, val)
        if not rok or not room_res:
            return True, (rerr or f"Room '{room_in}' not found."), emits
        room = world.rooms.get(room_res)
        if not room:
            return True, f"Room '{room_res}' not found.", emits
        # Try fuzzy resolve in that room
        resolved = _resolve_npcs_in_room(room, [npc_in])
        npc_name = resolved[0] if resolved else npc_in
        if npc_name not in room.npcs:
            return True, f"NPC '{npc_in}' not in room '{room_res}'.", emits
        room.npcs.discard(npc_name)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' removed from room '{room_res}'."})
        return True, None, emits

    if sub == 'setdesc':
        try:
            parts_joined = " ".join(sub_args)
            npc_name, desc = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /npc setdesc <npc name> | <description>', emits
        npc_name = _strip_quotes(npc_name)
        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            sheet = CharacterSheet(display_name=npc_name)
            world.npc_sheets[npc_name] = sheet
        # Ensure a stable id for this NPC as well
        try:
            world.get_or_create_npc_id(npc_name)
        except Exception:
            pass
        sheet.description = desc
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' description updated."})
        return True, None, emits

    return False, None, emits


def _save_silent(world, state_path: str) -> None:
    try:
        world.save_to_file(state_path)
    except Exception:
        pass
