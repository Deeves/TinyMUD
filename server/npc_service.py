"""NPC admin operations for /npc commands."""

from __future__ import annotations

from typing import List, Tuple

from world import CharacterSheet


def handle_npc_command(world, state_path: str, args: list[str]) -> Tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    if not args:
        return True, 'Usage: /npc <add|remove|setdesc> ...', emits

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == 'add':
        if len(sub_args) < 2:
            return True, 'Usage: /npc add <room_id> <npc name...>', emits
        room_id = sub_args[0]
        npc_name = " ".join(sub_args[1:]).strip()
        room = world.rooms.get(room_id)
        if not room:
            return True, f"Room '{room_id}' not found.", emits
        room.npcs.add(npc_name)
        if npc_name not in world.npc_sheets:
            world.npc_sheets[npc_name] = CharacterSheet(display_name=npc_name, description=f"An NPC named {npc_name}.")
        # Ensure a stable id for this NPC
        try:
            world.get_or_create_npc_id(npc_name)
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added to room '{room_id}'."})
        return True, None, emits

    if sub == 'remove':
        if len(sub_args) < 2:
            return True, 'Usage: /npc remove <room_id> <npc name...>', emits
        room_id = sub_args[0]
        npc_name = " ".join(sub_args[1:]).strip()
        room = world.rooms.get(room_id)
        if not room:
            return True, f"Room '{room_id}' not found.", emits
        if npc_name not in room.npcs:
            return True, f"NPC '{npc_name}' not in room '{room_id}'.", emits
        room.npcs.discard(npc_name)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' removed from room '{room_id}'."})
        return True, None, emits

    if sub == 'setdesc':
        try:
            parts_joined = " ".join(sub_args)
            npc_name, desc = [p.strip() for p in parts_joined.split('|', 1)]
        except Exception:
            return True, 'Usage: /npc setdesc <npc name> | <description>', emits
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
