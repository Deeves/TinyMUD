"""Movement-related operations for the AI MUD server.

Pure helpers for moving a player through a named door or stairs. These return
emits (to send back to the acting player) and broadcasts (to notify others).
"""

from __future__ import annotations

from typing import List, Tuple


def move_through_door(world, sid: str, door_name: str) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    player = world.players.get(sid)
    if not player:
        return False, 'Player not found.', emits, broadcasts
    room = world.rooms.get(player.room_id)
    if not room:
        return False, 'You are nowhere.', emits, broadcasts

    # Auto select only door if door_name empty
    name_in = door_name.strip()
    low = name_in.lower()
    for art in ("the ", "a ", "an "):
        if low.startswith(art):
            name_in = name_in[len(art):]
            break

    if not name_in:
        if len(room.doors) == 1:
            name_in = next(iter(room.doors.keys()))
        else:
            return False, 'Specify a door name: move through <door name>', emits, broadcasts

    target = room.doors.get(name_in)
    if not target:
        # try case-insensitive
        for dname, rid in room.doors.items():
            if dname.lower() == name_in.lower():
                target = rid
                name_in = dname
                break
    if not target:
        return False, f"No door named '{door_name}' here.", emits, broadcasts
    if target not in world.rooms:
        return False, f"Door '{name_in}' is linked to unknown room '{target}'.", emits, broadcasts

    # Announce departure
    broadcasts.append((player.room_id, {'type': 'system', 'content': f"{player.sheet.display_name} leaves through the {name_in}."}))
    # Move
    world.move_player(sid, target)
    # Announce arrival
    broadcasts.append((target, {'type': 'system', 'content': f"{player.sheet.display_name} enters."}))
    emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
    return True, None, emits, broadcasts


def move_stairs(world, sid: str, direction: str) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Move up or down stairs. direction is 'up' or 'down'."""
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    player = world.players.get(sid)
    if not player:
        return False, 'Player not found.', emits, broadcasts
    room = world.rooms.get(player.room_id)
    if not room:
        return False, 'You are nowhere.', emits, broadcasts

    if direction == 'up':
        target = room.stairs_up_to
        if not target:
            return False, 'There are no stairs leading up here.', emits, broadcasts
        if target not in world.rooms:
            return False, f"Stairs up lead to unknown room '{target}'.", emits, broadcasts
        broadcasts.append((player.room_id, {'type': 'system', 'content': f"{player.sheet.display_name} ascends the stairs."}))
        world.move_player(sid, target)
        broadcasts.append((target, {'type': 'system', 'content': f"{player.sheet.display_name} arrives from below."}))
        emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
        return True, None, emits, broadcasts

    if direction == 'down':
        target = room.stairs_down_to
        if not target:
            return False, 'There are no stairs leading down here.', emits, broadcasts
        if target not in world.rooms:
            return False, f"Stairs down lead to unknown room '{target}'.", emits, broadcasts
        broadcasts.append((player.room_id, {'type': 'system', 'content': f"{player.sheet.display_name} descends the stairs."}))
        world.move_player(sid, target)
        broadcasts.append((target, {'type': 'system', 'content': f"{player.sheet.display_name} arrives from above."}))
        emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
        return True, None, emits, broadcasts

    return False, "Direction must be 'up' or 'down'.", emits, broadcasts
