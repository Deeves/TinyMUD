"""Room admin operations for /room commands.

All functions return (handled: bool, error: str | None, emits: list[dict]).
They are pure of Flask/SocketIO and only touch the world model and save file.

Terminology:
- "room name" (user input): human-friendly name the admin types; we fuzzy-resolve it.
- room id (internal): stable identifier string used as keys in world.rooms and persisted.
"""

from __future__ import annotations

from typing import List, Tuple, Optional, TYPE_CHECKING
import uuid

from world import Room
if TYPE_CHECKING:
    from world import World
from id_parse_utils import (
    strip_quotes as _strip_quotes,
    parse_pipe_parts as _parse_pipe_parts,
    resolve_door_name as _resolve_door_name,
    resolve_room_id as _resolve_room_id,
)


def _normalize_room_input(world, sid: str | None, typed: str) -> tuple[bool, str | None, str | None]:
    """Normalize 'here' (case-insensitive) to the caller's current room id.

    Returns (ok, err, value) where value is either the concrete room id (for 'here')
    or the original input (quotes stripped) when not 'here'.
    """
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


def handle_room_command(world: "World", state_path: str, args: list[str], sid: str | None = None) -> Tuple[bool, str | None, List[dict]]:
    """Parse and execute /room admin operations.

    Contract:
    - Inputs: world (World), state_path (str), args (list[str]), sid optional
    - Returns: (handled, error, emits)
    - Errors: Non-fatal; never raises. Returns handled=True for known subcommands, False otherwise.
    """
    assert isinstance(state_path, str) and state_path != "", "state_path must be non-empty"
    assert isinstance(args, list), "args must be a list of strings"
    emits: List[dict] = []
    if not args:
        return True, 'Usage: /room <create|setdesc|rename|adddoor|removedoor|setstairs|linkdoor|linkstairs|lockdoor> ...', emits

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == 'create':
        try:
            parts_joined = " ".join(sub_args)
            room_id, desc = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /room create <id> | <description>', emits
        room_id = _strip_quotes(room_id)
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
            room_id, desc = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /room setdesc <id> | <description>', emits
        room_id = _strip_quotes(room_id)
        okn, errn, norm = _normalize_room_input(world, sid, room_id)
        if not okn:
            return True, errn, emits
        # norm is a concrete room id string or original input
        val = norm if isinstance(norm, str) else room_id
        rok, rerr, room_id_res = _resolve_room_id(world, val)
        if not rok or not room_id_res:
            return True, (rerr or f"Room '{room_id}' not found."), emits
        room = world.rooms.get(room_id_res)
        if room is None:
            return True, f"Room '{room_id_res}' not found.", emits
        room.description = desc
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Room '{room_id_res}' description updated."})
        return True, None, emits

    if sub == 'rename':
        # /room rename <room name> | <new room name>
        try:
            parts_joined = " ".join(sub_args)
            src_in, new_in = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /room rename <room name> | <new room name>', emits
        src_in = _strip_quotes(src_in)
        new_id = _strip_quotes(new_in)
        if not src_in or not new_id:
            return True, 'Usage: /room rename <room name> | <new room name>', emits
        # Normalize 'here' for source
        okn, errn, norm = _normalize_room_input(world, sid, src_in)
        if not okn:
            return True, errn, emits
        val = norm if isinstance(norm, str) else src_in
        rok, rerr, old_id = _resolve_room_id(world, val)
        if not rok or not old_id:
            # Provide gentle suggestions if possible
            suggestions = _suggest_room_ids(world, val)
            if suggestions:
                return True, (rerr or f"Room '{src_in}' not found.") + ' Did you mean: ' + ", ".join(suggestions[:10]) + '?', emits
            return True, (rerr or f"Room '{src_in}' not found."), emits
        if new_id == old_id:
            return True, 'New room id is the same as current.', emits
        if not new_id:
            return True, 'New room id cannot be empty.', emits
        if new_id in world.rooms:
            return True, f"Room '{new_id}' already exists.", emits

        # Perform rename: move Room object to new key and update its id
        room_obj = world.rooms.get(old_id)
        if not room_obj:
            return True, f"Room '{old_id}' not found.", emits
        # Update references in other structures first, then remap key
        # 1) Update all door targets and stairs in all rooms
        for r in list(world.rooms.values()):
            # Doors
            try:
                for dname, target in list((r.doors or {}).items()):
                    if target == old_id:
                        r.doors[dname] = new_id
            except Exception:
                pass
            # Stairs
            try:
                if getattr(r, 'stairs_up_to', None) == old_id:
                    r.stairs_up_to = new_id
                if getattr(r, 'stairs_down_to', None) == old_id:
                    r.stairs_down_to = new_id
            except Exception:
                pass
        # 2) Update players currently in the room
        try:
            for psid, p in list(getattr(world, 'players', {}).items()):
                if getattr(p, 'room_id', None) == old_id:
                    p.room_id = new_id
        except Exception:
            pass
        # 3) Update world.start_room_id if needed
        try:
            if getattr(world, 'start_room_id', None) == old_id:
                world.start_room_id = new_id
        except Exception:
            pass
        # 4) Remap the world.rooms key and update the room object's id
        try:
            # Preserve current players set on the object; just change its id field
            world.rooms.pop(old_id, None)
            room_obj.id = new_id
            world.rooms[new_id] = room_obj
        except Exception:
            return True, 'Internal error while renaming room.', emits

        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Room '{old_id}' renamed to '{new_id}'."})
        return True, None, emits

    if sub == 'adddoor':
        try:
            parts_joined = " ".join(sub_args)
            room_id, rest = _parse_pipe_parts(parts_joined, expected=2)
            door_name, target_room = _parse_pipe_parts(rest, expected=2)
        except Exception:
            # Note: usage mentions user-facing room names; internally we resolve to ids
            return True, 'Usage: /room adddoor <room name> | <door name> | <target room name>', emits
        room_id = _strip_quotes(room_id)
        door_name = _strip_quotes(door_name)
        target_room = _strip_quotes(target_room)
        # Normalize 'here' for both source and target
        okn_src, errn_src, norm_src = _normalize_room_input(world, sid, room_id)
        if not okn_src:
            return True, errn_src, emits
        okn_dst, errn_dst, norm_dst = _normalize_room_input(world, sid, target_room)
        if not okn_dst:
            return True, errn_dst, emits
        val_src = norm_src if isinstance(norm_src, str) else room_id
        rok, rerr, room_id_res = _resolve_room_id(world, val_src)
        if not rok or not room_id_res:
            return True, (rerr or f"Room '{room_id}' not found."), emits
        room = world.rooms.get(room_id_res)
        if room is None:
            return True, f"Room '{room_id_res}' not found.", emits
        target_room = norm_dst
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
            emits.append({'type': 'system', 'content': f"Linked door '{door_name}' in '{room_id_res}' <-> '{back_name}' in '{target_room}'."})
        else:
            # Target does not exist yet: keep original one-way behavior and inform the admin
            emits.append({'type': 'system', 'content': f"Door '{door_name}' in room '{room_id_res}' now leads to '{target_room}'. (Note: target room not found; back-link not created)"})

        _save_silent(world, state_path)
        return True, None, emits

    if sub == 'removedoor':
        try:
            parts_joined = " ".join(sub_args)
            room_id, door_name = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /room removedoor <room name> | <door name>', emits
        room_id = _strip_quotes(room_id)
        door_name = _strip_quotes(door_name)
        okn, errn, norm = _normalize_room_input(world, sid, room_id)
        if not okn:
            return True, errn, emits
        val = norm if isinstance(norm, str) else room_id
        rok, rerr, room_id_res = _resolve_room_id(world, val)
        if not rok or not room_id_res:
            return True, (rerr or f"Room '{room_id}' not found."), emits
        room = world.rooms.get(room_id_res)
        if not room:
            return True, f"Room '{room_id_res}' not found.", emits
        # Fuzzy resolve existing door name within the room
        okd, derr, resolved = _resolve_door_name(room, door_name)
        if not okd or not resolved:
            return True, (derr or f"Door '{door_name}' not found in room '{room_id}'."), emits
        room.doors.pop(resolved, None)
        try:
            room.door_ids.pop(resolved, None)
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Door '{door_name}' removed from room '{room_id}'."})
        return True, None, emits

    if sub == 'setstairs':
        try:
            parts_joined = " ".join(sub_args)
            room_id, rest = _parse_pipe_parts(parts_joined, expected=2)
            up_str, down_str = _parse_pipe_parts(rest, expected=2)
        except Exception:
            return True, 'Usage: /room setstairs <room name> | <up room name or -> | <down room name or ->', emits
        room_id = _strip_quotes(room_id)
        up_str = _strip_quotes(up_str)
        down_str = _strip_quotes(down_str)
        room_id = _strip_quotes(room_id)
        okn, errn, norm = _normalize_room_input(world, sid, room_id)
        if not okn:
            return True, errn, emits
        val = norm if isinstance(norm, str) else room_id
        rok, rerr, room_id_res = _resolve_room_id(world, val)
        if not rok or not room_id_res:
            return True, (rerr or f"Room '{room_id}' not found."), emits
        room = world.rooms.get(room_id_res)
        if not room:
            return True, f"Room '{room_id_res}' not found.", emits
        # Normalize 'here' for targets too
        def _norm_stairs(val: str) -> str | None:
            if val in ('', '-'):
                return None
            okx, errx, nx = _normalize_room_input(world, sid, val)
            if not okx:
                # Preserve previous behavior: if invalid, still set raw
                return val
            return nx
        room.stairs_up_to = _norm_stairs(up_str)
        room.stairs_down_to = _norm_stairs(down_str)
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
            room_a, rest = _parse_pipe_parts(parts_joined, expected=2)
            door_a, rest2 = _parse_pipe_parts(rest, expected=2)
            room_b, door_b = _parse_pipe_parts(rest2, expected=2)
        except Exception:
            return True, 'Usage: /room linkdoor <room_a> | <door_a> | <room_b> | <door_b>', emits
        room_a = _strip_quotes(room_a)
        room_b = _strip_quotes(room_b)
        door_a = _strip_quotes(door_a)
        door_b = _strip_quotes(door_b)
        okn_a, errn_a, norm_a = _normalize_room_input(world, sid, room_a)
        if not okn_a:
            return True, errn_a, emits
        okn_b, errn_b, norm_b = _normalize_room_input(world, sid, room_b)
        if not okn_b:
            return True, errn_b, emits
        val_a = norm_a if isinstance(norm_a, str) else room_a
        val_b = norm_b if isinstance(norm_b, str) else room_b
        rok_a, rerr_a, room_a_res = _resolve_room_id(world, val_a)
        rok_b, rerr_b, room_b_res = _resolve_room_id(world, val_b)
        if not rok_a or not rok_b or not room_a_res or not room_b_res:
            err_msg = rerr_a or rerr_b or 'Both rooms must exist.'
            return True, err_msg, emits
        ra = world.rooms.get(room_a_res)
        rb = world.rooms.get(room_b_res)
        if not ra or not rb:
            return True, 'Both rooms must exist.', emits
        ra.doors[door_a] = room_b_res
        rb.doors[door_b] = room_a_res
        # Ensure door ids on both sides
        try:
            if door_a not in ra.door_ids:
                ra.door_ids[door_a] = str(uuid.uuid4())
            if door_b not in rb.door_ids:
                rb.door_ids[door_b] = str(uuid.uuid4())
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Linked door '{door_a}' in '{room_a_res}' <-> '{door_b}' in '{room_b_res}'."})
        return True, None, emits

    if sub == 'linkstairs':
        try:
            parts_joined = " ".join(sub_args)
            room_a, rest = _parse_pipe_parts(parts_joined, expected=2)
            direction, room_b = _parse_pipe_parts(rest, expected=2)
        except Exception:
            return True, 'Usage: /room linkstairs <room_a> | <up|down> | <room_b>', emits
        room_a = _strip_quotes(room_a)
        room_b = _strip_quotes(room_b)
        direction = _strip_quotes(direction)
        okn_a, errn_a, norm_a = _normalize_room_input(world, sid, room_a)
        if not okn_a:
            return True, errn_a, emits
        okn_b, errn_b, norm_b = _normalize_room_input(world, sid, room_b)
        if not okn_b:
            return True, errn_b, emits
        val_a = norm_a if isinstance(norm_a, str) else room_a
        val_b = norm_b if isinstance(norm_b, str) else room_b
        rok_a, rerr_a, room_a_res = _resolve_room_id(world, val_a)
        rok_b, rerr_b, room_b_res = _resolve_room_id(world, val_b)
        if not rok_a or not rok_b or not room_a_res or not room_b_res:
            err_msg = rerr_a or rerr_b or 'Both rooms must exist.'
            return True, err_msg, emits
        ra = world.rooms.get(room_a_res)
        rb = world.rooms.get(room_b_res)
        if not ra or not rb:
            return True, 'Both rooms must exist.', emits
        d = direction.lower()
        if d not in ('up', 'down'):
            return True, "Direction must be 'up' or 'down'.", emits
        if d == 'up':
            ra.stairs_up_to = room_b_res
            rb.stairs_down_to = room_a_res
            # ids
            try:
                if not ra.stairs_up_id:
                    ra.stairs_up_id = str(uuid.uuid4())
                if not rb.stairs_down_id:
                    rb.stairs_down_id = str(uuid.uuid4())
            except Exception:
                pass
        else:
            ra.stairs_down_to = room_b_res
            rb.stairs_up_to = room_a_res
            try:
                if not ra.stairs_down_id:
                    ra.stairs_down_id = str(uuid.uuid4())
                if not rb.stairs_up_id:
                    rb.stairs_up_id = str(uuid.uuid4())
            except Exception:
                pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Linked stairs {d} from '{room_a_res}' <-> opposite in '{room_b_res}'."})
        return True, None, emits

    if sub == 'lockdoor':
        # Syntax:
        # /room lockdoor <door name> | <comma separated list of players and NPCs permitted>
        # or
        # /room lockdoor <door name> | <relationship: <type> with <player or NPC>>
        # Applies to the admin's current room ('here').
        if sid is None or sid not in getattr(world, 'players', {}):
            return True, 'You must be in a room to lock a door. Please authenticate.', emits
        player = world.players.get(sid)
        rid = getattr(player, 'room_id', None)
        if not isinstance(rid, str) or not rid:
            return True, 'You are nowhere.', emits
        room = world.rooms.get(rid)
        if room is None:
            return True, 'You are nowhere.', emits
        parts_joined = " ".join(sub_args)
        try:
            door_in, policy_in = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /room lockdoor <door name> | <name1, name2, ...>  or  /room lockdoor <door name> | relationship: <type> with <name>', emits
        door_in = _strip_quotes(door_in)
        policy_in = policy_in.strip()
        if not door_in or not policy_in:
            return True, 'Usage: /room lockdoor <door name> | <names...> or relationship: <type> with <name>', emits
        # Resolve door name within current room
        okd, derr, door_name = _resolve_door_name(room, door_in)
        if not okd or not door_name:
            return True, (derr or f"Door '{door_in}' not found in this room."), emits

        # Helper: resolve an entity display name to a stable id (user.user_id or npc_id)
        def resolve_entity_id_by_name(name: str) -> Tuple[Optional[str], Optional[str]]:
            n = _strip_quotes(name).strip()
            if not n:
                return None, None
            # Try user exact/ci-exact
            try:
                for uid, user in getattr(world, 'users', {}).items():
                    if user.display_name.lower() == n.lower():
                        return user.user_id, user.display_name
            except Exception:
                pass
            # Try NPCs by fuzzy
            try:
                cand = None
                names = list(getattr(world, 'npc_sheets', {}).keys())
                for nm in names:
                    if nm.lower() == n.lower():
                        cand = nm; break
                if cand is None:
                    prefs = [nm for nm in names if nm.lower().startswith(n.lower())]
                    if len(prefs) == 1:
                        cand = prefs[0]
                if cand is None:
                    subs = [nm for nm in names if n.lower() in nm.lower()]
                    if len(subs) == 1:
                        cand = subs[0]
                if cand:
                    return world.get_or_create_npc_id(cand), cand
            except Exception:
                pass
            return None, None

        # Parse policy
        allow_ids: list[str] = []
        rel_rules: list[dict] = []
        if policy_in.lower().startswith('relationship:'):
            # Expect: relationship: <type> with <name>
            raw = policy_in[len('relationship:'):].strip()
            # Split on ' with '
            rel_type = None
            who_raw = None
            low = raw.lower()
            if ' with ' in low:
                idx = low.index(' with ')
                rel_type = raw[:idx].strip()
                who_raw = raw[idx + len(' with '):].strip()
            else:
                return True, 'Usage: relationship: <type> with <name>', emits
            if not rel_type or not who_raw:
                return True, 'Usage: relationship: <type> with <name>', emits
            # Resolve target entity id
            tgt_id, tgt_disp = resolve_entity_id_by_name(who_raw)
            if not tgt_id:
                return True, f"'{who_raw}' not found as a player or NPC.", emits
            rel_rules.append({'type': rel_type, 'to': tgt_id})
        else:
            # Comma separated names
            names = [p.strip() for p in policy_in.split(',') if p.strip()]
            if not names:
                return True, 'Provide at least one name.', emits
            resolved_disp: list[str] = []
            for nm in names:
                eid, disp = resolve_entity_id_by_name(nm)
                if not eid:
                    return True, f"'{nm}' not found as a player or NPC.", emits
                allow_ids.append(eid)
                resolved_disp.append(disp or nm)

        # Store policy on the room
        if not hasattr(room, 'door_locks') or room.door_locks is None:
            room.door_locks = {}
        room.door_locks[door_name] = {
            'allow_ids': allow_ids,
            'allow_rel': rel_rules,
        }
        _save_silent(world, state_path)
        if allow_ids:
            emits.append({'type': 'system', 'content': f"Door '{door_name}' is now locked. Permitted: {len(allow_ids)} entity(s)."})
        else:
            # relationship rule
            rule = rel_rules[0]
            emits.append({'type': 'system', 'content': f"Door '{door_name}' is now locked. Permitted: anyone with relationship [{rule['type']}] to the specified entity."})
        return True, None, emits

    return False, None, emits


def _save_silent(world, state_path: str) -> None:
    try:
        world.save_to_file(state_path)
    except Exception:
        pass
