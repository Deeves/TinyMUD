"""NPC admin operations for /npc commands.

Terminology:
- "room name" (user input) is fuzzy-resolved to a stable internal room id.
- room id (internal) is the key in world.rooms and used for storage.

Supports:
    - /npc add <room name> | <npc name> | <npc description>
    - /npc remove <npc name>  (removes from the admin's current room)

Backward compatibility:
    - /npc add <room_id> <npc name...>
    - /npc remove <room_id> <npc name...>
    - /npc setdesc <npc name> | <description>
    - /npc setrelation <source name> | <relationship type> | <target name>
    - /npc removerelations <source name> | <target name>
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional

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
        return True, 'Usage: /npc <add|remove|setdesc|setrelation|removerelations> ...', emits

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == 'add':
    # New syntax (user-facing room name): /npc add <room name> | <npc name> | <npc description>
        parts_joined = " ".join(sub_args)
        if '|' in parts_joined:
            try:
                room_in, name_in, desc_in = _parse_pipe_parts(parts_joined, expected=3)
            except Exception:
                return True, 'Usage: /npc add <room name> | <npc name> | <npc description>', emits
            room_in = _strip_quotes(room_in)
            name_in = _strip_quotes(name_in)
            desc_in = desc_in.strip()
            if not room_in or not name_in:
                return True, 'Usage: /npc add <room name> | <npc name> | <npc description>', emits
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
            return True, 'Usage: /npc add <room name> | <npc name> | <npc description>', emits
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

    if sub == 'setrelation':
        # /npc setrelation <source name> | <relationship type> | <target name> [| mutual]
        try:
            parts_joined = " ".join(sub_args)
            # Accept 3 or 4 parts. The 4th optional part is the literal word 'mutual'.
            parts = _parse_pipe_parts(parts_joined)
            if len(parts) < 3:
                raise ValueError('not enough parts')
            # Rejoin extras beyond 3 into the 3rd slot to be tolerant of extra pipes in names
            if len(parts) > 4:
                parts = parts[:3] + ["mutual"]  # if too many, prioritize setting mutual
            if len(parts) == 3:
                src_in, rel_in, tgt_in = parts
                mutual_flag = False
            else:
                src_in, rel_in, tgt_in, mutual_raw = parts[:4]
                mutual_flag = str(mutual_raw).strip().lower() in ("mutual", "yes", "true", "both")
        except Exception:
            return True, 'Usage: /npc setrelation <source name> | <relationship type> | <target name> | mutual', emits

        src_name = _strip_quotes(src_in)
        tgt_name = _strip_quotes(tgt_in)
        rel_type = rel_in.strip()
        if not src_name or not tgt_name or not rel_type:
            return True, 'Usage: /npc setrelation <source name> | <relationship type> | <target name> | mutual', emits

        # Resolve entity IDs for source and target. Entities can be: connected players, any user by display name, or NPC by name.
        def resolve_entity_id(name: str) -> Tuple[Optional[str], Optional[str]]:
            # Try connected players first
            try:
                for psid, p in list(getattr(world, 'players', {}).items()):
                    if p.sheet and p.sheet.display_name.lower() == name.lower():
                        # Players map to their user id if connected
                        # Find user id via sessions if available, else derive by matching user display_name
                        for uid, user in list(getattr(world, 'users', {}).items()):
                            if user.display_name.lower() == name.lower():
                                return user.user_id, user.display_name
            except Exception:
                pass
            # Try any known user
            try:
                user = world.get_user_by_display_name(name)
                if user:
                    return user.user_id, user.display_name
            except Exception:
                pass
            # Try NPC by name
            try:
                if name in getattr(world, 'npc_sheets', {}):
                    npc_id = world.get_or_create_npc_id(name)
                    return npc_id, name
            except Exception:
                pass
            # Try fuzzy within NPC names
            try:
                names = list(getattr(world, 'npc_sheets', {}).keys())
                # simple ci-exact / prefix / substring
                cand = None
                for n in names:
                    if n.lower() == name.lower():
                        cand = n; break
                if cand is None:
                    prefs = [n for n in names if n.lower().startswith(name.lower())]
                    if len(prefs) == 1:
                        cand = prefs[0]
                if cand is None:
                    subs = [n for n in names if name.lower() in n.lower()]
                    if len(subs) == 1:
                        cand = subs[0]
                if cand is not None:
                    npc_id = world.get_or_create_npc_id(cand)
                    return npc_id, cand
            except Exception:
                pass
            return None, None

        src_id, src_resolved = resolve_entity_id(src_name)
        if not src_id:
            return True, f"Source '{src_name}' not found as a player, user, or NPC.", emits
        tgt_id, tgt_resolved = resolve_entity_id(tgt_name)
        if not tgt_id:
            return True, f"Target '{tgt_name}' not found as a player, user, or NPC.", emits

        # Set directed relationship
        rels: Dict[str, Dict[str, str]] = getattr(world, 'relationships', {})
        if src_id not in rels:
            rels[src_id] = {}
        rels[src_id][tgt_id] = rel_type
        # Optional reciprocal
        if mutual_flag:
            if tgt_id not in rels:
                rels[tgt_id] = {}
            rels[tgt_id][src_id] = rel_type
        world.relationships = rels
        _save_silent(world, state_path)
        # Report with resolved display names
        src_disp = src_resolved or src_name
        tgt_disp = tgt_resolved or tgt_name
        if mutual_flag:
            emits.append({'type': 'system', 'content': f"Relationship set (mutual): {src_disp} ⇄ {tgt_disp} as [{rel_type}]"})
        else:
            emits.append({'type': 'system', 'content': f"Relationship set: {src_disp} —[{rel_type}]→ {tgt_disp}"})
        return True, None, emits

    if sub == 'removerelations':
        # /npc removerelations <source> | <target>
        try:
            parts_joined = " ".join(sub_args)
            src_in, tgt_in = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /npc removerelations <source> | <target>', emits

        src_name = _strip_quotes(src_in)
        tgt_name = _strip_quotes(tgt_in)
        if not src_name or not tgt_name:
            return True, 'Usage: /npc removerelations <source> | <target>', emits

        # Reuse resolver from setrelation
        def resolve_entity_id(name: str) -> Tuple[Optional[str], Optional[str]]:
            try:
                for psid, p in list(getattr(world, 'players', {}).items()):
                    if p.sheet and p.sheet.display_name.lower() == name.lower():
                        for uid, user in list(getattr(world, 'users', {}).items()):
                            if user.display_name.lower() == name.lower():
                                return user.user_id, user.display_name
            except Exception:
                pass
            try:
                user = world.get_user_by_display_name(name)
                if user:
                    return user.user_id, user.display_name
            except Exception:
                pass
            try:
                if name in getattr(world, 'npc_sheets', {}):
                    npc_id = world.get_or_create_npc_id(name)
                    return npc_id, name
            except Exception:
                pass
            try:
                names = list(getattr(world, 'npc_sheets', {}).keys())
                cand = None
                for n in names:
                    if n.lower() == name.lower():
                        cand = n; break
                if cand is None:
                    prefs = [n for n in names if n.lower().startswith(name.lower())]
                    if len(prefs) == 1:
                        cand = prefs[0]
                if cand is None:
                    subs = [n for n in names if name.lower() in n.lower()]
                    if len(subs) == 1:
                        cand = subs[0]
                if cand is not None:
                    npc_id = world.get_or_create_npc_id(cand)
                    return npc_id, cand
            except Exception:
                pass
            return None, None

        src_id, src_resolved = resolve_entity_id(src_name)
        if not src_id:
            return True, f"Source '{src_name}' not found as a player, user, or NPC.", emits
        tgt_id, tgt_resolved = resolve_entity_id(tgt_name)
        if not tgt_id:
            return True, f"Target '{tgt_name}' not found as a player, user, or NPC.", emits

        rels: Dict[str, Dict[str, str]] = getattr(world, 'relationships', {})
        changed = False
        if src_id in rels and tgt_id in rels[src_id]:
            try:
                del rels[src_id][tgt_id]
                changed = True
                if not rels[src_id]:
                    del rels[src_id]
            except Exception:
                pass
        if tgt_id in rels and src_id in rels.get(tgt_id, {}):
            try:
                del rels[tgt_id][src_id]
                changed = True
                if not rels[tgt_id]:
                    del rels[tgt_id]
            except Exception:
                pass
        world.relationships = rels
        if changed:
            _save_silent(world, state_path)
            src_disp = src_resolved or src_name
            tgt_disp = tgt_resolved or tgt_name
            emits.append({'type': 'system', 'content': f"Removed relationships between {src_disp} and {tgt_disp}."})
        else:
            emits.append({'type': 'system', 'content': 'No relationships existed to remove.'})
        return True, None, emits

    return False, None, emits


def _save_silent(world, state_path: str) -> None:
    try:
        world.save_to_file(state_path)
    except Exception:
        pass
