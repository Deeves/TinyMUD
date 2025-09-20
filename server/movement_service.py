"""Movement-related operations for the AI MUD server.

Pure helpers for moving a player through a named door or stairs. These return
emits (to send back to the acting player) and broadcasts (to notify others).
"""

from __future__ import annotations

from typing import List, Tuple
from id_parse_utils import resolve_door_name


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

    ok_res, err_res, resolved_door = resolve_door_name(room, name_in)
    if not ok_res or not resolved_door:
        return False, (err_res or f"No door named '{door_name}' here."), emits, broadcasts
    name_in = resolved_door
    target = room.doors.get(resolved_door)
    if target not in world.rooms:
        return False, f"Door '{name_in}' is linked to unknown room '{target}'.", emits, broadcasts

    # Enforce optional door locks
    try:
        locks = getattr(room, 'door_locks', {}) or {}
        policy = locks.get(name_in)
        if policy:
            # Determine acting entity id (user id)
            actor_uid = None
            try:
                # world.users is keyed by user_id, but we need mapping from sid. Server session map isn't available here, so fall back:
                # Find a user whose sheet object is the same instance as player's sheet.
                for uid, user in getattr(world, 'users', {}).items():
                    if user.sheet is world.players.get(sid).sheet:
                        actor_uid = uid
                        break
            except Exception:
                actor_uid = None
            # If we couldn't resolve, deny by default to be safe
            if not actor_uid:
                return False, f"The {name_in} is locked. You are not permitted to pass.", emits, broadcasts
            allow_ids = set(policy.get('allow_ids') or [])
            if actor_uid in allow_ids:
                pass  # allowed
            else:
                # Check relationship rule(s)
                rel_rules = policy.get('allow_rel') or []
                permitted = False
                relationships = getattr(world, 'relationships', {}) or {}
                for rule in rel_rules:
                    rtype = str(rule.get('type') or '').strip()
                    to_id = rule.get('to')
                    if not rtype or not to_id:
                        continue
                    # Check if actor has relationship rtype towards to_id
                    if relationships.get(actor_uid, {}).get(to_id) == rtype:
                        permitted = True
                        break
                if not permitted:
                    return False, f"The {name_in} is locked. You are not permitted to pass.", emits, broadcasts
    except Exception:
        # On any error in checking, default to denying passage for safety
        return False, f"The {name_in} is locked.", emits, broadcasts

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


def teleport_player(world, sid: str, target_room_id: str) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Teleport a player to a specific room id without requiring a door.

    Returns (ok, err, emits, broadcasts) where:
      - emits: messages to send to the acting/affected player
      - broadcasts: (room_id, payload) tuples to notify other players of leave/arrive
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    player = world.players.get(sid)
    if not player:
        return False, 'Player not found.', emits, broadcasts
    if target_room_id not in world.rooms:
        return False, f"Room '{target_room_id}' not found.", emits, broadcasts

    cur_room_id = player.room_id
    # Announce departure from current room
    if cur_room_id in world.rooms:
        broadcasts.append((cur_room_id, {'type': 'system', 'content': f"{player.sheet.display_name} vanishes in a flash of light."}))

    # Move silently via world helper
    world.move_player(sid, target_room_id)

    # Announce arrival in target room
    broadcasts.append((target_room_id, {'type': 'system', 'content': f"{player.sheet.display_name} appears out of thin air."}))
    # Show the new room description to the player
    emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
    return True, None, emits, broadcasts
