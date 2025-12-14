from __future__ import annotations

"""Object Template Wizard Router.

Handles the interactive object template creation wizard flow.
Extracted from server.py handle_message to reduce file size.
"""

import re
import json
from typing import Dict, Any, Callable

MESSAGE_OUT = 'message'


def _is_skip(s: str) -> bool:
    """Check if input should be treated as a skip."""
    sl = (s or "").strip().lower()
    return sl == "" or sl in ("skip", "none", "-")


def _parse_recipe_input(s: str) -> list:
    """Parse recipe input from JSON or comma-separated names."""
    if _is_skip(s):
        return []
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            out = []
            for el in parsed:
                if isinstance(el, dict):
                    out.append(el)
                elif isinstance(el, (str, int)):
                    out.append({"display_name": str(el)})
            return out
        if isinstance(parsed, dict):
            return [parsed]
        return [{"display_name": str(parsed)}]
    except Exception:
        names = [p.strip() for p in s.split(',') if p.strip()]
        return [{"display_name": n} for n in names]


def try_handle_flow(
    world: Any,
    state_path: str,
    sid: str | None,
    player_message: str,
    object_template_sessions: Dict[str, dict],
    emit: Callable[[str, Dict[str, Any]], None],
) -> bool:
    """Handle object template wizard flow if active.
    
    Returns True if the message was handled, False otherwise.
    """
    if not sid or sid not in object_template_sessions:
        return False

    from typing import cast
    from persistence_utils import save_world

    sid_str = cast(str, sid)
    sess = object_template_sessions.get(sid_str, {"step": "template_key", "temp": {}})
    step = sess.get("step")
    temp = sess.get("temp", {})
    text_stripped = player_message.strip()
    text_lower = text_stripped.lower()

    def _echo_raw(s: str) -> None:
        """Show user's raw entry as a plain system line."""
        if s and not _is_skip(s):
            emit(MESSAGE_OUT, {'type': 'system', 'content': s})

    def _ask_next(current: str) -> None:
        """Update step and prompt for next input."""
        sess['step'] = current
        object_template_sessions[sid_str] = sess
        prompts = {
            'template_key': "Enter a unique template key (letters, numbers, underscores), e.g., sword_bronze:",
            'display_name': "Enter display name (required), e.g., Bronze Sword:",
            'description': "Enter a short description (required):",
            'object_tags': "Enter comma-separated tags (optional; default: small). Examples: weapon,cutting damage,small:",
            'material_tag': "Enter material tag (optional), e.g., bronze (Enter to skip or type 'skip'):",
            'value': "Enter value in coins (optional integer; Enter to skip or type 'skip'):",
            'satiation_value': "Enter hunger satiation value (optional int; Enter to skip), e.g., 25 for food:",
            'hydration_value': "Enter thirst hydration value (optional int; Enter to skip), e.g., 25 for drink:",
            'durability': "Enter durability (optional integer; Enter to skip or type 'skip'):",
            'quality': "Enter quality (optional), e.g., average (Enter to skip or type 'skip'):",
            'loot_location_hint': "Enter loot location hint as JSON object or a plain name (optional). Examples: {\"display_name\": \"Old Chest\"} or Old Chest. Enter to skip:",
            'crafting_recipe': "Enter crafting recipe as JSON array of objects or comma-separated names (optional). Examples: [{\"display_name\":\"Bronze Ingot\"}],Hammer or Enter to skip (or type 'skip'):",
            'deconstruct_recipe': "Enter deconstruct recipe as JSON array of objects or comma-separated names (optional). Enter to skip (or type 'skip'):",
            'confirm': "Type 'save' to save this template, or 'cancel' to abort.",
        }
        emit(MESSAGE_OUT, {'type': 'system', 'content': prompts.get(current, '...')})

    # Allow cancel
    if text_lower in ("cancel",):
        object_template_sessions.pop(sid_str, None)
        emit(MESSAGE_OUT, {'type': 'system', 'content': 'Object template creation cancelled.'})
        return True

    # Step handlers
    if step == 'template_key':
        key = re.sub(r"[^A-Za-z0-9_]+", "_", text_stripped)
        if not key:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Template key cannot be empty.'})
            return True
        if key in getattr(world, 'object_templates', {}):
            emit(MESSAGE_OUT, {'type': 'error', 'content': f"Template key '{key}' already exists. Choose another."})
            return True
        temp['key'] = key
        sess['temp'] = temp
        _ask_next('display_name')
        return True

    if step == 'display_name':
        name = text_stripped
        if len(name) < 1:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Display name is required.'})
            return True
        temp['display_name'] = name
        sess['temp'] = temp
        _ask_next('description')
        return True

    if step == 'description':
        if not text_stripped or _is_skip(text_stripped):
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Description is required.'})
            _ask_next('description')
            return True
        temp['description'] = text_stripped
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('object_tags')
        return True

    if step == 'object_tags':
        if not _is_skip(text_stripped):
            tags = [t.strip() for t in text_stripped.split(',') if t.strip()]
        else:
            tags = ['small']
        temp['object_tags'] = list(dict.fromkeys(tags))
        sess['temp'] = temp
        _ask_next('material_tag')
        return True

    if step == 'material_tag':
        temp['material_tag'] = None if _is_skip(text_stripped) else text_stripped
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('value')
        return True

    if step == 'value':
        if _is_skip(text_stripped):
            temp['value'] = None
        else:
            try:
                temp['value'] = int(text_stripped)
            except Exception:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        sess['temp'] = temp
        _ask_next('satiation_value')
        return True

    if step == 'satiation_value':
        if _is_skip(text_stripped):
            temp['satiation_value'] = None
        else:
            try:
                temp['satiation_value'] = int(text_stripped)
            except Exception:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        sess['temp'] = temp
        _ask_next('hydration_value')
        return True

    if step == 'hydration_value':
        if _is_skip(text_stripped):
            temp['hydration_value'] = None
        else:
            try:
                temp['hydration_value'] = int(text_stripped)
            except Exception:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        sess['temp'] = temp
        _ask_next('durability')
        return True

    if step == 'durability':
        if _is_skip(text_stripped):
            temp['durability'] = None
        else:
            try:
                temp['durability'] = int(text_stripped)
            except Exception:
                emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('quality')
        return True

    if step == 'quality':
        temp['quality'] = None if _is_skip(text_stripped) else text_stripped
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('loot_location_hint')
        return True

    # Back-compat: if a session somehow has this old step, auto-skip
    if step == 'link_to_object_uuid':
        temp['link_to_object_uuid'] = None
        sess['temp'] = temp
        _ask_next('loot_location_hint')
        return True

    if step == 'loot_location_hint':
        if _is_skip(text_stripped):
            temp['loot_location_hint'] = None
        else:
            odata = None
            try:
                parsed = json.loads(text_stripped)
                if isinstance(parsed, dict):
                    odata = parsed
                else:
                    odata = {"display_name": str(parsed)}
            except Exception:
                odata = {"display_name": text_stripped}
            temp['loot_location_hint'] = odata
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('crafting_recipe')
        return True

    if step == 'crafting_recipe':
        temp['crafting_recipe'] = _parse_recipe_input(text_stripped)
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('deconstruct_recipe')
        return True

    if step == 'deconstruct_recipe':
        temp['deconstruct_recipe'] = _parse_recipe_input(text_stripped)
        _echo_raw(text_stripped)
        sess['temp'] = temp
        # Show summary then confirm
        try:
            preview = {
                'display_name': temp.get('display_name'),
                'description': temp.get('description', ''),
                'object_tags': temp.get('object_tags', ['small']),
                'material_tag': temp.get('material_tag'),
                'value': temp.get('value'),
                'satiation_value': temp.get('satiation_value'),
                'hydration_value': temp.get('hydration_value'),
                'durability': temp.get('durability'),
                'quality': temp.get('quality'),
                'loot_location_hint': temp.get('loot_location_hint'),
                'crafting_recipe': temp.get('crafting_recipe', []),
                'deconstruct_recipe': temp.get('deconstruct_recipe', []),
            }
            raw = json.dumps(preview, ensure_ascii=False, indent=2)
        except Exception:
            raw = '(error building preview)'
        emit(MESSAGE_OUT, {'type': 'system', 'content': f"Preview of template object:\n{raw}"})
        _ask_next('confirm')
        return True

    if step == 'confirm':
        if text_lower not in ('save', 'y', 'yes'):
            emit(MESSAGE_OUT, {'type': 'system', 'content': "Not saved. Type 'save' to save or 'cancel' to abort."})
            return True
        # Build Object from collected data
        try:
            from world import Object as _Obj
            key = temp.get('key')
            if not key:
                raise ValueError('Missing template key')
            # Build nested items
            llh_dict = temp.get('loot_location_hint')
            crafting_list = temp.get('crafting_recipe', [])
            decon_list = temp.get('deconstruct_recipe', [])
            llh_obj = _Obj.from_dict(llh_dict) if llh_dict else None
            craft_objs = [_Obj.from_dict(o) for o in crafting_list]
            decon_objs = [_Obj.from_dict(o) for o in decon_list]
            # Convert numeric nutrition values into explicit tags
            tags_final = list(dict.fromkeys(temp.get('object_tags', ['small'])))
            try:
                if temp.get('satiation_value') is not None:
                    tags_final.append(f"Edible: {int(temp['satiation_value'])}")
                if temp.get('hydration_value') is not None:
                    tags_final.append(f"Drinkable: {int(temp['hydration_value'])}")
            except Exception:
                pass
            obj = _Obj(
                display_name=temp.get('display_name'),
                description=temp.get('description', ''),
                object_tags=set(tags_final),
                material_tag=temp.get('material_tag'),
                value=temp.get('value'),
                satiation_value=temp.get('satiation_value'),
                hydration_value=temp.get('hydration_value'),
                loot_location_hint=llh_obj,
                durability=temp.get('durability'),
                quality=temp.get('quality'),
                crafting_recipe=craft_objs,
                deconstruct_recipe=decon_objs,
                link_target_room_id=temp.get('link_target_room_id'),
                link_to_object_uuid=temp.get('link_to_object_uuid'),
            )
            # Save into world templates
            if not hasattr(world, 'object_templates'):
                world.object_templates = {}
            world.object_templates[key] = obj
            try:
                save_world(world, state_path, debounced=True)
            except Exception:
                pass
            object_template_sessions.pop(sid_str, None)
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"Saved object template '{key}'."})
            return True
        except Exception as e:
            emit(MESSAGE_OUT, {'type': 'error', 'content': f'Failed to save template: {e}'})
            return True

    # If step is unknown, prompt the first step
    _ask_next('template_key')
    return True
