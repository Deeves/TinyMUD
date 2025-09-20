"""Room admin operations for /room commands.

All functions return (handled: bool, error: str | None, emits: list[dict]).
They are pure of Flask/SocketIO and only touch the world model and save file.
"""

from __future__ import annotations

from typing import List, Tuple
import uuid

from world import Room


def _suggest_room_ids(world, typed_id: str) -> list[str]:
    """Return a list of room ids that start with the same first letter as typed_id (case-insensitive).
    If typed_id is empty or there are no matches, returns an empty list. Sorted for stable output.
    """
    try:
        first = (typed_id or "").strip()[:1].lower()
        if not first:
            return []
        candidates = [rid for rid in world.rooms.keys() if isinstance(rid, str) and rid[:1].lower() == first]
        return sorted(candidates)
    except Exception:
        return []


def handle_room_command(world, state_path: str, args: list[str]) -> Tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    if not args:
        return True, 'Usage: /room <create|setdesc|adddoor|removedoor|setstairs|linkdoor|linkstairs> ...', emits

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == 'create':
        try:
            parts_joined = " ".join(sub_args)
            room_id, desc = [p.strip() for p in parts_joined.split('|', 1)]
        except Exception:
            return True, 'Usage: /room create <id> | <description>', emits
        if not room_id:
            return True, 'Room id cannot be empty.', emits
        if room_id in world.rooms:
            return True, f"Room '{room_id}' already exists.", emits
        world.rooms[room_id] = Room(id=room_id, description=desc)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Room '{room_id}' created."})
        return True, None, emits

    if sub == 'setdesc':
        try:
            parts_joined = " ".join(sub_args)
            room_id, desc = [p.strip() for p in parts_joined.split('|', 1)]
        except Exception:
            return True, 'Usage: /room setdesc <id> | <description>', emits
        room = world.rooms.get(room_id)
        if not room:
            return True, f"Room '{room_id}' not found.", emits
        room.description = desc
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Room '{room_id}' description updated."})
        return True, None, emits

    if sub == 'adddoor':
        try:
            parts_joined = " ".join(sub_args)
            room_id, rest = [p.strip() for p in parts_joined.split('|', 1)]
            door_name, target_room = [p.strip() for p in rest.split('|', 1)]
        except Exception:
            return True, 'Usage: /room adddoor <room_id> | <door name> | <target_room_id>', emits
        room = world.rooms.get(room_id)
        if not room:
            # Offer a friendly suggestion list using the first letter (case-insensitive)
            suggestions = _suggest_room_ids(world, room_id)
            if suggestions:
                return True, (
                    f"Room '{room_id}' not found. Did you mean: "
                    + ", ".join(suggestions)
                    + "?"
                ), emits
            return True, f"Room '{room_id}' not found.", emits
        if not target_room:
            return True, 'Target room id cannot be empty.', emits
        # Create or update forward door
        room.doors[door_name] = target_room
        # Assign a stable id for this door if missing
        try:
            if door_name not in room.door_ids:
                room.door_ids[door_name] = str(uuid.uuid4())
        except Exception:
            pass

        # If the target room exists, also create a reciprocal door there
        tgt = world.rooms.get(target_room)
        created_back = None
        if tgt:
            # Try to use the same door name on the target; if it collides with an existing different link, pick a unique variant
            back_name = door_name
            if back_name in tgt.doors and tgt.doors.get(back_name) != room_id:
                # Propose a readable fallback like "<name> (to <room_id>)", then add numeric suffixes if necessary
                base = f"{door_name} (to {room_id})"
                candidate = base
                n = 2
                while candidate in tgt.doors and tgt.doors.get(candidate) != room_id:
                    candidate = f"{base} #{n}"
                    n += 1
                back_name = candidate
            # Create/update the back link
            tgt.doors[back_name] = room_id
            created_back = back_name
            try:
                if back_name not in tgt.door_ids:
                    tgt.door_ids[back_name] = str(uuid.uuid4())
            except Exception:
                pass
            emits.append({'type': 'system', 'content': f"Linked door '{door_name}' in '{room_id}' <-> '{back_name}' in '{target_room}'."})
        else:
            # Target does not exist yet: keep original one-way behavior and inform the admin
            emits.append({'type': 'system', 'content': f"Door '{door_name}' in room '{room_id}' now leads to '{target_room}'. (Note: target room not found; back-link not created)"})

        _save_silent(world, state_path)
        return True, None, emits

    if sub == 'removedoor':
        try:
            parts_joined = " ".join(sub_args)
            room_id, door_name = [p.strip() for p in parts_joined.split('|', 1)]
        except Exception:
            return True, 'Usage: /room removedoor <room_id> | <door name>', emits
        room = world.rooms.get(room_id)
        if not room:
            return True, f"Room '{room_id}' not found.", emits
        if door_name not in room.doors:
            return True, f"Door '{door_name}' not found in room '{room_id}'.", emits
        room.doors.pop(door_name, None)
        try:
            room.door_ids.pop(door_name, None)
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Door '{door_name}' removed from room '{room_id}'."})
        return True, None, emits

    if sub == 'setstairs':
        try:
            parts_joined = " ".join(sub_args)
            room_id, rest = [p.strip() for p in parts_joined.split('|', 1)]
            up_str, down_str = [p.strip() for p in rest.split('|', 1)]
        except Exception:
            return True, 'Usage: /room setstairs <room_id> | <up_room_id or -> | <down_room_id or ->', emits
        room = world.rooms.get(room_id)
        if not room:
            return True, f"Room '{room_id}' not found.", emits
        room.stairs_up_to = None if up_str in ('', '-') else up_str
        room.stairs_down_to = None if down_str in ('', '-') else down_str
        # Maintain stairs ids according to presence
        try:
            if room.stairs_up_to and not room.stairs_up_id:
                room.stairs_up_id = str(uuid.uuid4())
            if not room.stairs_up_to:
                room.stairs_up_id = None
            if room.stairs_down_to and not room.stairs_down_id:
                room.stairs_down_id = str(uuid.uuid4())
            if not room.stairs_down_to:
                room.stairs_down_id = None
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Stairs for '{room_id}' set. Up -> {room.stairs_up_to or 'none'}, Down -> {room.stairs_down_to or 'none'}."})
        return True, None, emits

    if sub == 'linkdoor':
        try:
            parts_joined = " ".join(sub_args)
            room_a, rest = [p.strip() for p in parts_joined.split('|', 1)]
            door_a, rest2 = [p.strip() for p in rest.split('|', 1)]
            room_b, door_b = [p.strip() for p in rest2.split('|', 1)]
        except Exception:
            return True, 'Usage: /room linkdoor <room_a> | <door_a> | <room_b> | <door_b>', emits
        ra = world.rooms.get(room_a)
        rb = world.rooms.get(room_b)
        if not ra or not rb:
            return True, 'Both rooms must exist.', emits
        ra.doors[door_a] = room_b
        rb.doors[door_b] = room_a
        # Ensure door ids on both sides
        try:
            if door_a not in ra.door_ids:
                ra.door_ids[door_a] = str(uuid.uuid4())
            if door_b not in rb.door_ids:
                rb.door_ids[door_b] = str(uuid.uuid4())
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Linked door '{door_a}' in '{room_a}' <-> '{door_b}' in '{room_b}'."})
        return True, None, emits

    if sub == 'linkstairs':
        try:
            parts_joined = " ".join(sub_args)
            room_a, rest = [p.strip() for p in parts_joined.split('|', 1)]
            direction, room_b = [p.strip() for p in rest.split('|', 1)]
        except Exception:
            return True, 'Usage: /room linkstairs <room_a> | <up|down> | <room_b>', emits
        ra = world.rooms.get(room_a)
        rb = world.rooms.get(room_b)
        if not ra or not rb:
            return True, 'Both rooms must exist.', emits
        d = direction.lower()
        if d not in ('up', 'down'):
            return True, "Direction must be 'up' or 'down'.", emits
        if d == 'up':
            ra.stairs_up_to = room_b
            rb.stairs_down_to = room_a
            # ids
            try:
                if not ra.stairs_up_id:
                    ra.stairs_up_id = str(uuid.uuid4())
                if not rb.stairs_down_id:
                    rb.stairs_down_id = str(uuid.uuid4())
            except Exception:
                pass
        else:
            ra.stairs_down_to = room_b
            rb.stairs_up_to = room_a
            try:
                if not ra.stairs_down_id:
                    ra.stairs_down_id = str(uuid.uuid4())
                if not rb.stairs_up_id:
                    rb.stairs_up_id = str(uuid.uuid4())
            except Exception:
                pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Linked stairs {d} from '{room_a}' <-> opposite in '{room_b}'."})
        return True, None, emits

    return False, None, emits


def _save_silent(world, state_path: str) -> None:
    try:
        world.save_to_file(state_path)
    except Exception:
        pass
