"""Movement-related operations for the AI MUD server.

Pure helpers for moving a player through a named door or stairs. These return
emits (to send back to the acting player) and broadcasts (to notify others).
"""

from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING
from id_parse_utils import resolve_door_name, fuzzy_resolve

if TYPE_CHECKING:  # import only for typing to avoid runtime cycles
    from world import World, Room


def move_through_door(world: "World", sid: str, door_name: str) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Move through a named door or any Travel Point object in the player's current room.

    Contract:
    - Inputs: world (World), sid (str), door_name (str)
    - Output: (ok, err, emits, broadcasts)
    - Errors: returns (False, message, [], []) on invalid player/room/door/object
    """
    assert isinstance(sid, str) and sid != "", "sid must be a non-empty string"
    assert isinstance(door_name, str), "door_name must be a string"
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
        # Consider both doors and travel point objects
        candidates: List[str] = []
        try:
            doors_map = getattr(room, 'doors', {}) or {}
            candidates.extend(list(doors_map.keys()))
        except Exception:
            pass
        try:
            for _oid, obj in (getattr(room, 'objects', {}) or {}).items():
                try:
                    if 'Travel Point' in (obj.object_tags or set()):
                        dn = (getattr(obj, 'display_name', None) or '').strip()
                        if dn:
                            candidates.append(dn)
                except Exception:
                    continue
        except Exception:
            pass
        uniq = sorted(set(candidates))
        if len(uniq) == 1:
            name_in = uniq[0]
        else:
            return False, "Specify a door or travel point name: move through <name>", emits, broadcasts

    # 1) Try standard named doors first
    ok_res, err_res, resolved_door = resolve_door_name(room, name_in)
    target = None
    resolved_is_object = False
    if ok_res and resolved_door:
        name_in = resolved_door
        target = room.doors.get(resolved_door)
        if target not in world.rooms:
            return False, f"Door '{name_in}' is linked to unknown room '{target}'.", emits, broadcasts
    else:
        # 2) Fall back to Travel Point objects in the room (by display_name)
        # Collect candidates: any room.objects with tag 'Travel Point'
        tp_name_to_ids: dict[str, List[str]] = {}
        try:
            for oid, obj in (getattr(room, 'objects', {}) or {}).items():
                try:
                    tags = set(obj.object_tags or [])
                except Exception:
                    tags = set()
                if 'Travel Point' in tags:
                    dn = (getattr(obj, 'display_name', None) or '').strip()
                    if not dn:
                        continue
                    tp_name_to_ids.setdefault(dn, []).append(oid)
        except Exception:
            tp_name_to_ids = {}
        tp_names = list(tp_name_to_ids.keys())
        if tp_names:
            ok_tp, err_tp, resolved_tp = fuzzy_resolve(name_in, tp_names)
            if ok_tp and resolved_tp:
                name_in = resolved_tp
                # choose the first matching object id
                oid = tp_name_to_ids[resolved_tp][0]
                obj = room.objects.get(oid)
                target = getattr(obj, 'link_target_room_id', None)
                if not target:
                    return False, f"The {name_in} doesn't lead anywhere.", emits, broadcasts
                if target not in world.rooms:
                    return False, f"Travel point '{name_in}' leads to unknown room '{target}'.", emits, broadcasts
                resolved_is_object = True
            else:
                # Neither door nor travel point resolved
                return False, (err_res or err_tp or f"No door or travel point named '{door_name}' here."), emits, broadcasts
        else:
            # No travel points in room; propagate prior door error/message
            return False, (err_res or f"No door named '{door_name}' here."), emits, broadcasts

    # Enforce optional locks (by name) for both doors and travel point objects
    try:
        locks = getattr(room, 'door_locks', {}) or {}
        policy = locks.get(name_in)
        if name_in in locks:  # Policy exists (even if None) - door is locked
            # SECURITY FIX: Validate policy structure - deny access if corrupted
            if not isinstance(policy, dict):
                return False, f"The {name_in} is locked.", emits, broadcasts
            
            # Determine acting entity id (user id)
            actor_uid = None
            try:
                # world.users is keyed by user_id, but we need mapping from sid. Server session map isn't available here, so fall back:
                # Find a user whose sheet object is the same instance as the player's sheet.
                player_ref = world.players.get(sid)
                if player_ref:
                    for uid, user in getattr(world, 'users', {}).items():
                        if user.sheet is player_ref.sheet:
                            actor_uid = uid
                            break
            except Exception:
                actor_uid = None
            # If we couldn't resolve, deny by default to be safe
            if not actor_uid:
                return False, f"The {name_in} is locked. You are not permitted to pass.", emits, broadcasts
            
            allow_ids = set(policy.get('allow_ids') or [])
            rel_rules = policy.get('allow_rel') or []
            
            # SECURITY FIX: If no restrictions are defined, deny access (empty policy bypass)
            if not allow_ids and not rel_rules:
                return False, f"The {name_in} is locked.", emits, broadcasts
            
            if actor_uid in allow_ids:
                pass  # allowed
            else:
                # Check relationship rule(s)
                permitted = False
                relationships = getattr(world, 'relationships', {}) or {}
                for rule in rel_rules:
                    try:
                        rtype = str(rule.get('type') or '').strip()
                        to_id = rule.get('to')
                        if not rtype or not to_id:
                            continue
                        # Check if actor has relationship rtype towards to_id
                        if relationships.get(actor_uid, {}).get(to_id) == rtype:
                            # SECURITY FIX: Validate that relationship target user still exists (orphaned relationship fix)
                            if to_id not in getattr(world, 'users', {}):
                                continue  # Skip this relationship rule - target user deleted
                            permitted = True
                            break
                    except Exception:
                        continue  # Skip malformed rules
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


def move_stairs(world: "World", sid: str, direction: str) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
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


def teleport_player(world: "World", sid: str, target_room_id: str) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
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
