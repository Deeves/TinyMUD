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
"""

from typing import List, Tuple

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


def create_object(world, state_path: str, sid: str | None, args: list[str]) -> tuple[bool, str | None, List[dict]]:
    """Create a concrete Object instance in a room, optionally from a template.

    Syntax: /object createobject <room> | <display name> | <description> | <tags csv OR template_key>
    Returns: (handled, error, emits)
    """
    emits: List[dict] = []
    try:
        joined = " ".join(args)
        p_room, p_name, p_desc, p_third = _pipe_parts(joined, expected=4)
    except Exception:
        return True, 'Usage: /object createobject <room> | <display name> | <description> | <tags or template_key>', emits

    name = _strip_quotes(p_name or "").strip()
    desc = _strip_quotes(p_desc or "").strip()
    third = (p_third or "").strip()
    if not name:
        return True, 'Display name required.', emits

    room_input = _strip_quotes(p_room or "").strip()
    rok, rerr, rid = _resolve_room_id_fuzzy(world, sid, room_input or 'here')
    if not rok or not rid:
        return True, (rerr or 'Room not found.'), emits
    room = world.rooms.get(rid)
    if not room:
        return True, 'Room not found.', emits

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
            return True, f"Template '{third}' not found.", emits
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
        used_template = True
    else:
        tags = [t.strip() for t in third.split(',') if t.strip()] if third else ['one-hand']
        tags = list(dict.fromkeys(tags))
        new_obj = _Obj(display_name=name, description=desc, object_tags=set(tags))

    try:
        room.objects[new_obj.uuid] = new_obj
        world.save_to_file(state_path)
    except Exception:
        pass

    how = f"from template '{template_key}'" if used_template and template_key else ""
    emits.append({'type': 'system', 'content': f"Created object '{new_obj.display_name}' {how} in room {rid}."})
    return True, None, emits


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


def delete_template(world, state_path: str, key: str) -> tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    store = getattr(world, 'object_templates', {})
    if key not in store:
        return True, f"Template '{key}' not found.", emits
    try:
        del store[key]
        world.save_to_file(state_path)
        emits.append({'type': 'system', 'content': f"Deleted template '{key}'."})
    except Exception as e:
        return True, f"Failed to delete template: {e}", emits
    return True, None, emits
