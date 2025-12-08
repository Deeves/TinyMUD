from __future__ import annotations

"""
object_service.py — Admin helpers for Objects and Object Templates.

Mission briefing:
- Keep object creation, listing, viewing, and deletion tidy and decoupled
  from the web socket layer. We operate purely on the world state and return
  emit payloads; the caller decides how to deliver them to clients.

Great first change ideas:
- Add more template fields? Just thread them through here.
- Expand fuzzy matching for template keys or add categories. Easy win.

Service Contract:
    All public functions return 4-tuple: (handled, error, emits, broadcasts)
    - handled: bool - whether the command was recognized
    - error: str | None - error message if any
    - emits: List[dict] - messages to send to the acting player
    - broadcasts: List[Tuple[str, dict]] - (room_id, message) pairs for room broadcasts
"""

from typing import List, Tuple
from persistence_utils import save_world
from rate_limiter import check_rate_limit, OperationType

from id_parse_utils import (
    strip_quotes as _strip_quotes,
    parse_pipe_parts as _pipe_parts,
)


def _resolve_room_id_fuzzy(world, sid: str | None, typed: str) -> tuple[bool, str | None, str | None]:
    # Local minimal normalizer for 'here' alias
    t = _strip_quotes(typed or "")
    if t.lower() == 'here':
        if not sid or sid not in world.players:
            return False, 'You are nowhere.', None
        player = world.players.get(sid)
        rid = getattr(player, 'room_id', None)
        if not rid:
            return False, 'You are nowhere.', None
        return True, None, rid
    # Defer to id_parse_utils generic resolver
    from id_parse_utils import resolve_room_id as _resolve_room_id_generic
    ok, err, rid = _resolve_room_id_generic(world, t)
    return ok, err, rid


def create_object(world, state_path: str, sid: str | None, args: list[str]) -> tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Create a concrete Object instance in a room, optionally from a template.

    Syntax: /object createobject <room> | <display name> | <description> | <tags csv OR template_key>
    Returns: (handled, error, emits, broadcasts)
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    
    # Rate limiting: object creation can be expensive and spammable
    if not check_rate_limit(sid, OperationType.MODERATE, "object_creation"):
        return (True, 'You are creating objects too quickly. '
                      'Please wait before creating another object.', emits, broadcasts)
    try:
        joined = " ".join(args)
        p_room, p_name, p_desc, p_third = _pipe_parts(joined, expected=4)
    except Exception:
        return True, 'Usage: /object createobject <room> | <display name> | <description> | <tags or template_key>', emits, broadcasts

    name = _strip_quotes(p_name or "").strip()
    desc = _strip_quotes(p_desc or "").strip()
    third = (p_third or "").strip()
    if not name:
        return True, 'Display name required.', emits, broadcasts

    room_input = _strip_quotes(p_room or "").strip()
    rok, rerr, rid = _resolve_room_id_fuzzy(world, sid, room_input or 'here')
    if not rok or not rid:
        return True, (rerr or 'Room not found.'), emits, broadcasts
    room = world.rooms.get(rid)
    if not room:
        return True, 'Room not found.', emits, broadcasts

    from world import Object as _Obj
    new_obj: _Obj
    used_template = False

    tpl_store = getattr(world, 'object_templates', {}) or {}
    template_key = None
    if third:
        if third in tpl_store:
            template_key = third
        else:
            for k in tpl_store.keys():
                if k.lower() == third.lower():
                    template_key = k
                    break

    if template_key:
        base = tpl_store.get(template_key)
        if not base:
            return True, f"Template '{third}' not found.", emits, broadcasts
        try:
            base_dict = base.to_dict()
            new_obj = _Obj.from_dict(base_dict)
        except Exception:
            new_obj = _Obj(
                display_name=base.display_name,
                description=base.description,
                object_tags=set(base.object_tags or set()),
                material_tag=base.material_tag,
                value=base.value,
                loot_location_hint=base.loot_location_hint,
                durability=base.durability,
                quality=base.quality,
                crafting_recipe=list(base.crafting_recipe or []),
                deconstruct_recipe=list(base.deconstruct_recipe or []),
                link_target_room_id=base.link_target_room_id,
                link_to_object_uuid=base.link_to_object_uuid,
            )
        # Fresh identity and overrides
        new_obj.uuid = str(__import__('uuid').uuid4())
        new_obj.display_name = name
        new_obj.description = desc
        # Do not inherit ownership from templates; start unowned
        try:
            new_obj.owner_id = None  # type: ignore[attr-defined]
        except Exception:
            pass
        used_template = True
    else:
        tags = [t.strip() for t in third.split(',') if t.strip()] if third else ['small']
        tags = list(dict.fromkeys(tags))
        new_obj = _Obj(display_name=name, description=desc, object_tags=set(tags))
        # Explicit for clarity; default is None
        try:
            new_obj.owner_id = None  # type: ignore[attr-defined]
        except Exception:
            pass

    try:
        room.objects[new_obj.uuid] = new_obj
        save_world(world, state_path, debounced=True)
    except Exception:
        pass

    how = f"from template '{template_key}'" if used_template and template_key else ""
    emits.append({'type': 'system', 'content': f"Created object '{new_obj.display_name}' {how} in room {rid}."})
    return True, None, emits, broadcasts


def list_templates(world) -> list[str]:
    try:
        return sorted(list((getattr(world, 'object_templates', {}) or {}).keys()))
    except Exception:
        return []


def view_template(world, key: str) -> tuple[bool, str | None, str | None]:
    """Return (ok, err, json_text) for the template keyed by 'key'."""
    obj = (getattr(world, 'object_templates', {}) or {}).get(key)
    if not obj:
        return False, f"Template '{key}' not found.", None
    try:
        import json
        raw = json.dumps(obj.to_dict(), ensure_ascii=False, indent=2)
    except Exception:
        raw = str(obj.to_dict())
    return True, None, raw


def delete_template(world, state_path: str, key: str) -> tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Delete an object template.
    
    Returns: (handled, error, emits, broadcasts)
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    store = getattr(world, 'object_templates', {})
    if key not in store:
        return True, f"Template '{key}' not found.", emits, broadcasts
    try:
        del store[key]
        save_world(world, state_path, debounced=True)
        emits.append({'type': 'system', 'content': f"Deleted template '{key}'."})
    except Exception as e:
        return True, f"Failed to delete template: {e}", emits, broadcasts
    return True, None, emits, broadcasts

def list_objects(world, sid: str, args: list[str]) -> tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """List objects in the current or specified room.
    
    Syntax: /object list [room_id]
    """
    emits: List[dict] = []
    
    room_input = args[0] if args else "here"
    rok, rerr, rid = _resolve_room_id_fuzzy(world, sid, room_input)
    if not rok or not rid:
        return True, (rerr or 'Room not found.'), emits, []
        
    room = world.rooms.get(rid)
    if not room:
        return True, 'Room not found.', emits, []
        
    lines = [f"[b]Objects in {rid}:[/b]"]
    if not room.objects:
        lines.append("No objects found.")
    else:
        for oid, obj in room.objects.items():
            lines.append(f"- {obj.display_name} (UUID: {oid})")
            
    emits.append({'type': 'system', 'content': "\n".join(lines)})
    return True, None, emits, []


def delete_object_instance(world, state_path: str, args: list[str]) -> tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Delete a concrete object instance from a room.
    
    Syntax: /object delete <room> | <object_name_or_uuid>
    """
    emits: List[dict] = []
    
    try:
        joined = " ".join(args)
        p_room, p_target = _pipe_parts(joined, expected=2)
    except Exception:
        return True, 'Usage: /object delete <room> | <object_name_or_uuid>', emits, []
        
    room_input = _strip_quotes(p_room)
    target = _strip_quotes(p_target)
    
    rok, rerr, rid = _resolve_room_id_fuzzy(world, None, room_input) # Sid optional if room explicit
    if not rok or not rid:
        return True, (rerr or 'Room not found.'), emits, []
        
    room = world.rooms.get(rid)
    if not room:
        return True, 'Room not found.', emits, []
        
    # Resolve target: UUID first, then name
    target_uuid = None
    if target in room.objects:
        target_uuid = target
    else:
        # Fuzzy match by name
        candidates = [uid for uid, o in room.objects.items() if o.display_name.lower() == target.lower()]
        if not candidates:
            candidates = [uid for uid, o in room.objects.items() if target.lower() in o.display_name.lower()]
        
        if len(candidates) == 1:
            target_uuid = candidates[0]
        elif len(candidates) > 1:
            return True, f"Multiple objects match '{target}'. Use UUID.", emits, []
            
    if not target_uuid:
        return True, f"Object '{target}' not found in {rid}.", emits, []
        
    del room.objects[target_uuid]
    save_world(world, state_path, debounced=True)
    emits.append({'type': 'system', 'content': f"Object deleted from {rid}."})
    return True, None, emits, []
