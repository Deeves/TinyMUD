from __future__ import annotations

"""
interaction_service.py — Player-facing object interaction flow.

Service Contract:
    All public functions return 4-tuple: (handled, error, emits, broadcasts)
    - handled: bool - whether the command was recognized
    - error: str | None - error message if any
    - emits: List[dict] - messages to send to the acting player
    - broadcasts: List[Tuple[str, dict]] - (room_id, message) pairs for room broadcasts

This service is intentionally tiny and side-effect free (no socket calls here).
It lists possible interactions based on an Object's tags and guides the player
through choosing one. For now, choosing an interaction simply acknowledges the
choice; "Step Away" cancels the flow cleanly.

We derive interactions from tags in a conservative way. Unknown tags just don't
add actions. "Step Away" is always available so players can cancel.
"""

from typing import Dict, Any
from concurrency_utils import atomic
import random
from dice_utils import roll as dice_roll
from movement_service import move_through_door
from rate_limiter import check_rate_limit, OperationType


# Map object tags -> human actions (labels). Keep these short and friendly.
_TAG_TO_ACTIONS: dict[str, list[str]] = {
    # Mobility / world geometry
    "Travel Point": ["Move Through"],
    # Carrying / equipment
    "small": ["Pick Up"],
    "large": ["Pick Up"],
    "weapon": ["Wield"],
    # Resting
    # The 'bed' tag enables a direct Sleep interaction for players (with ownership check)
    "bed": ["Sleep"],
    # Common affordances (optional future use)
    "Edible": ["Eat"],
    "Drinkable": ["Drink"],
    "Container": ["Open", "Search"],
    "cutting damage": ["Cut"],
}


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: dict[str, bool] = {}
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen[it] = True
            out.append(it)
    return out


def _actions_for_object(world, obj) -> list[str]:
    """Return available actions for an object, including dynamic ones.

    In addition to static tag→action mappings, this inspects tags for
    parameterized affordances like 'craft spot:<template_key>' and adds a
    corresponding Craft action when a template is available.
    """
    actions: list[str] = []
    try:
        tags = set(getattr(obj, 'object_tags', []) or [])
        # 1) Static tag-based actions (exact tag matches only)
        for t in list(tags):
            tstr = str(t)
            if tstr in _TAG_TO_ACTIONS:
                actions.extend(_TAG_TO_ACTIONS[tstr])

    # 2) Numeric-aware nutrition tags: 'Edible: N' and 'Drinkable: N'
        def _parse_tag_val(ts: set[str], key: str) -> int | None:
            keyl = key.lower()
            for x in ts:
                s = str(x)
                parts = s.split(':', 1)
                if len(parts) != 2:
                    continue
                if parts[0].strip().lower() == keyl:
                    r = parts[1].strip()
                    if r.startswith('+'):
                        r = r[1:]
                    if r.lstrip('-').isdigit():
                        try:
                            return int(r)
                        except Exception:
                            return None
            return None
        has_edible = any(str(t).split(':', 1)[0].strip().lower() == 'edible' for t in tags)
        has_drink = any(str(t).split(':', 1)[0].strip().lower() == 'drinkable' for t in tags)
        val_e = _parse_tag_val(tags, 'Edible') if has_edible else None
        val_d = _parse_tag_val(tags, 'Drinkable') if has_drink else None
    # If numeric provided, replace plain label with formatted one; if missing,
    # remove the action entirely
        if has_edible:
            # Remove any prior Eat variants
            actions = [a for a in actions if not (a == 'Eat' or a.lower().startswith('eat (+'))]
            if val_e is not None:
                actions.append(f"Eat (+{val_e})")
        if has_drink:
            actions = [
                a for a in actions
                if not (a == 'Drink' or a.lower().startswith('drink (+'))
            ]
            if val_d is not None:
                actions.append(f"Drink (+{val_d})")

        # 3) Dynamic: craft spot:<template_key>
        store = getattr(world, 'object_templates', {}) or {}
        for t in list(tags):
            try:
                tstr = str(t)
            except Exception:
                continue
            low = tstr.strip().lower()
            if low.startswith('craft spot:'):
                key_raw = tstr.split(':', 1)[1].strip()
                if not key_raw:
                    continue
                key_match = None
                if key_raw in store:
                    key_match = key_raw
                else:
                    for k in store.keys():
                        if k.lower() == key_raw.lower():
                            key_match = k
                            break
                # Prefer the template's display name when known; else show the key
                label_name = key_raw
                try:
                    if key_match and store.get(key_match):
                        label_name = (
                            getattr(store[key_match], 'display_name', key_match)
                            or key_match
                        )
                except Exception:
                    label_name = key_raw
                actions.append(f"Craft {label_name}")
    except Exception:
        pass
    # Always allow cancelling
    actions = _unique_preserve_order(actions)
    actions.append("Step Away")
    return actions


def _format_choices(title: str, actions: list[str]) -> str:
    # Render a compact numbered list; allow players to reply with a number or name
    lines: list[str] = [f"[b]{title}[/b]"]
    for idx, act in enumerate(actions, start=1):
        lines.append(f"{idx}. {act}")
    lines.append("What do you wish to do?")
    return "\n".join(lines)


def begin_interaction(
    world,
    sid: str,
    room,
    object_name: str,
    sessions: Dict[str, dict],
) -> tuple[bool, str | None, list[dict], list[tuple[str, dict]]]:
    """Begin an interaction with an object.
    
    Returns: (handled, error, emits, broadcasts)
    """
    broadcasts: list[tuple[str, dict]] = []
    if not sid or sid not in world.players:
        return False, 'Please authenticate first.', [], broadcasts
    if not room:
        return False, 'You are nowhere.', [], broadcasts
    # Local import to avoid cycles at module import time
    from look_service import resolve_object_in_room
    obj, suggestions = resolve_object_in_room(room, object_name)
    if obj is None:
        if suggestions:
            return False, "Did you mean: " + ", ".join(suggestions) + "?", [], broadcasts
        return False, f"You don't see '{object_name}' here.", [], broadcasts

    actions = _actions_for_object(world, obj)
    # Stash session state
    with atomic('interaction_sessions'):
        sessions[sid] = {
            'step': 'choose',
            'obj_uuid': getattr(obj, 'uuid', None),
            'obj_name': getattr(obj, 'display_name', 'object'),
            'actions': actions,
        }
    # Build emits
    title = f"Interactions for {getattr(obj, 'display_name', 'object')}"
    emits = [
        {'type': 'system', 'content': _format_choices(title, actions)}
    ]
    return True, None, emits, broadcasts


def handle_interaction_input(
    world,
    sid: str,
    text: str,
    sessions: Dict[str, dict],
) -> tuple[bool, str | None, list[dict], list[tuple[str, dict]]]:
    """Handle a follow-up input while in the interaction session.

    Returns: (handled, error, emits, broadcasts)
    """
    sess = sessions.get(sid)
    if not sess:
        return False, None, [], []
    step = sess.get('step')
    if step != 'choose':
        # Unknown state: fail-safe cancel
        with atomic('interaction_sessions'):
            sessions.pop(sid, None)
        return True, None, [{'type': 'system', 'content': 'Interaction cancelled.'}], []

    raw = (text or '').strip()
    low = raw.lower()
    name = sess.get('obj_name') or 'object'
    broadcasts: list[tuple[str, dict]] = []
    actions: list[str] = list(sess.get('actions') or [])

    # Friendly cancel words
    if low in ('cancel', 'back', 'exit', 'quit', 'step away'):
        with atomic('interaction_sessions'):
            sessions.pop(sid, None)
        return True, None, [{'type': 'system', 'content': f'You step away from {name}.'}], []

    chosen: str | None = None
    # Allow numeric selection 1..N
    try:
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(actions):
                chosen = actions[idx - 1]
    except Exception:
        pass
    # Or label/prefix match
    if chosen is None and raw:
        # exact case-insensitive match first
        for act in actions:
            if act.lower() == low:
                chosen = act
                break
        if chosen is None:
            # unique prefix
            matches = [a for a in actions if a.lower().startswith(low)]
            if len(matches) == 1:
                chosen = matches[0]

    if chosen is None:
        # Reprint menu
        title = f"Interactions for {name}"
        msg = _format_choices(title, actions)
        return True, None, [
            {
                'type': 'system',
                'content': (
                    "I didn't catch that. Please pick one of the options "
                    "(number or name)."
                ),
            },
            {'type': 'system', 'content': msg},
        ], []

    # Always allow cancelling via Step Away
    if chosen.lower() == 'step away':
        with atomic('interaction_sessions'):
            sessions.pop(sid, None)
        return True, None, [{'type': 'system', 'content': f'You step away from {name}.'}], []

    # Locate the object by uuid in the current room or player's inventory
    player = world.players.get(sid)
    room = world.rooms.get(player.room_id) if player else None
    obj = None
    obj_uuid = sess.get('obj_uuid')
    if room and obj_uuid and getattr(room, 'objects', None):
        obj = room.objects.get(obj_uuid)
    # Search hands and stowed inventory if not in room
    inv = player.sheet.inventory if player else None
    obj_loc = None  # 'room' | 'hand' | 'small' | 'large'
    hand_index = None
    stow_index = None
    stow_large_index = None
    if (not obj) and inv:
        # hands 0,1 then small 2..5, large 6..7
        for i in range(0, 2):
            it = inv.slots[i]
            if it and getattr(it, 'uuid', None) == obj_uuid:
                obj = it
                obj_loc = 'hand'
                hand_index = i
                break
        if not obj:
            for i in range(2, 6):
                it = inv.slots[i]
                if it and getattr(it, 'uuid', None) == obj_uuid:
                    obj = it
                    obj_loc = 'small'
                    stow_index = i
                    break
        if not obj:
            for i in range(6, 8):
                it = inv.slots[i]
                if it and getattr(it, 'uuid', None) == obj_uuid:
                    obj = it
                    obj_loc = 'large'
                    stow_large_index = i
                    break

    # Helper: simple clamp to keep needs within 0..100
    def _clamp_need(v: float | int | None) -> float:
        try:
            return max(0.0, min(100.0, float(v or 0.0)))
        except Exception:
            return 0.0

    if chosen.lower() == 'move through':
        # Delegate to movement service using the object's display name
        if not obj:
            # If missing, try by stored name
            target_name = name
        else:
            target_name = getattr(obj, 'display_name', name)
        ok, err, emits_m, broadcasts_m = move_through_door(world, sid, target_name)
        with atomic('interaction_sessions'):
            sessions.pop(sid, None)
        if not ok:
            return True, None, [{'type': 'error', 'content': err or 'You cannot go that way.'}], []
        return True, None, emits_m, broadcasts_m

    # Craft action(s): derived from 'craft spot:<template_key>' tags
    if chosen.lower().startswith('craft'):
        # Rate limiting: protect against crafting spam
        if not check_rate_limit(sid, OperationType.MODERATE, "crafting"):
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'error',
                'content': 'You are crafting too quickly. Please wait before crafting again.',
            }], []
        
        # Recompute dynamic mapping in case actions list was truncated by UI
        target_key: str | None = None
        try:
            tags = set(getattr(obj, 'object_tags', []) or []) if obj else set()
        except Exception:
            tags = set()
        store = getattr(world, 'object_templates', {}) or {}
        # Build candidates [(label, key)]
        candidates: list[tuple[str, str]] = []
        for t in list(tags):
            tstr = str(t)
            if tstr.lower().startswith('craft spot:'):
                key_raw = tstr.split(':', 1)[1].strip()
                if not key_raw:
                    continue
                key_match = None
                if key_raw in store:
                    key_match = key_raw
                else:
                    for k in store.keys():
                        if k.lower() == key_raw.lower():
                            key_match = k
                            break
                label_name = key_raw
                if key_match and store.get(key_match):
                    try:
                        label_name = (
                            getattr(store[key_match], 'display_name', key_match)
                            or key_match
                        )
                    except Exception:
                        label_name = key_match
                candidates.append((f"Craft {label_name}", key_match or key_raw))
        # Resolve which candidate the user picked
        if len(candidates) == 1 and chosen.lower() == 'craft':
            target_key = candidates[0][1]
        else:
            low = chosen.lower()
            for lbl, key in candidates:
                if lbl.lower() == low or lbl.lower().startswith(low):
                    target_key = key
                    break
        if not target_key:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'error',
                'content': (
                    'This crafting spot is misconfigured or offers nothing to craft.'
                )
            }], []
        # Locate template and spawn a fresh instance into the current room
        tmpl = (
            store.get(target_key)
            or next(
                (store[k] for k in store.keys() if k.lower() == target_key.lower()),
                None,
            )
        )
        if not tmpl:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'error',
                'content': (
                    f"Crafting failed: template '{target_key}' not found."
                ),
            }], []
        try:
            # If the template specifies a crafting_recipe, require the player to have
            # each listed component in their inventory (match by display_name, case-insensitive).
            # The station (craft spot) itself is not a component; only
            # crafting_recipe items.
            # If any component is missing, report what's needed and abort.
            try:
                required = [
                    getattr(o, 'display_name', None)
                    for o in (getattr(tmpl, 'crafting_recipe', []) or [])
                ]
                required = [str(n).strip() for n in required if n and str(n).strip()]
            except Exception:
                required = []
            if required:
                # Gather inventory names across all slots
                inv_names: list[str] = []
                if inv is not None:
                    for it in (inv.slots or []):
                        if it and getattr(it, 'display_name', None):
                            inv_names.append(str(getattr(it, 'display_name')).strip())
                # Count and compare case-insensitively
                from collections import Counter
                req_counts = Counter([n.lower() for n in required])
                have_counts = Counter([n.lower() for n in inv_names])
                missing_list: list[str] = []
                for nm, cnt in req_counts.items():
                    if have_counts.get(nm, 0) < cnt:
                        # Use original-cased name for message when available
                        # Find an example casing from required list
                        example = next((r for r in required if r.lower() == nm), nm)
                        deficit = cnt - have_counts.get(nm, 0)
                        if deficit == 1:
                            missing_list.append(example)
                        else:
                            missing_list.append(f"{deficit}x {example}")
                if missing_list:
                    with atomic('interaction_sessions'):
                        sessions.pop(sid, None)
                    return True, None, [{
                        'type': 'error',
                        'content': (
                            'You lack the required components to craft this: '
                            + ", ".join(missing_list)
                        ),
                    }], []
                # Consume components: remove the needed number of items from inventory slots.
                # Strategy: scan slots left-to-right and null out matching items
                # until counts satisfied.
                if inv is not None:
                    to_remove = dict(req_counts)
                    for idx in range(0, len(inv.slots)):
                        if all(v <= 0 for v in to_remove.values()):
                            break
                        it = inv.slots[idx]
                        if not it or not getattr(it, 'display_name', None):
                            continue
                        nm = str(getattr(it, 'display_name')).strip().lower()
                        if to_remove.get(nm, 0) > 0:
                            # Remove this item
                            inv.slots[idx] = None
                            to_remove[nm] -= 1
                    # Safety check: if for some reason we couldn't remove all, abort
                    if any(v > 0 for v in to_remove.values()):
                        with atomic('interaction_sessions'):
                            sessions.pop(sid, None)
                        return True, None, [{
                            'type': 'error',
                            'content': (
                                'Crafting failed: inventory changed and components '
                                'are no longer available.'
                            ),
                        }], []
            from world import Object as _Obj
            made = (
                _Obj.from_dict(tmpl.to_dict())
                if hasattr(tmpl, 'to_dict')
                else _Obj.from_dict(tmpl)
            )
            # Place in room (simple initial rule: spawns into the world at the spot)
            if room is None:
                # Fallback if room missing
                with atomic('interaction_sessions'):
                    sessions.pop(sid, None)
                return True, None, [{'type': 'error', 'content': 'You are nowhere.'}], []
            room.objects[made.uuid] = made
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': (
                    f"You craft a {getattr(made, 'display_name', 'mystery item')}."
                ),
            }], []
        except Exception as e:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': f'Crafting failed: {e}'}], []

    def _place_in_hand(o) -> tuple[bool, str | None, int | None]:
        # Enhanced version with duplicate UUID checking and safer placement
        if inv is None:
            return False, 'No inventory available.', None
        
        # Check for duplicate UUID in inventory before placing
        for idx, existing_obj in enumerate(inv.slots):
            if existing_obj and existing_obj.uuid == o.uuid:
                return False, f'Object already exists in slot {idx}.', None
        
        # Prefer right hand (1), then left hand (0) with validation
        for slot_idx in [1, 0]:
            if inv.slots[slot_idx] is None and inv.can_place(slot_idx, o):
                inv.slots[slot_idx] = o
                # Remove 'stowed' tag if present
                try:
                    getattr(o, 'object_tags', set()).discard('stowed')
                except Exception:
                    pass
                return True, None, slot_idx
        
        return False, 'Your hands are full or object cannot be held.', None

    def _place_stowed(o) -> tuple[bool, str | None]:
        if inv is None:
            return False, 'No inventory available.'
            
        # Enhanced version with duplicate UUID checking and validation
        # Check for duplicate UUID in inventory before placing
        for idx, existing_obj in enumerate(inv.slots):
            if existing_obj and existing_obj.uuid == o.uuid:
                return False, f'Object already exists in slot {idx}.'
        
        tags = set(getattr(o, 'object_tags', []) or [])
        # large items go to large slots (6-7), small to small slots (2-5)
        if 'large' in tags:
            for i in range(6, 8):
                if inv.slots[i] is None and inv.can_place(i, o):
                    inv.slots[i] = o
                    try:
                        getattr(o, 'object_tags', set()).add('stowed')
                    except Exception:
                        pass
                    return True, None
            return False, 'No large slot available to stow it.'
        
        # default small items
        for i in range(2, 6):
            if inv.slots[i] is None and inv.can_place(i, o):
                inv.slots[i] = o
                try:
                    getattr(o, 'object_tags', set()).add('stowed')
                except Exception:
                    pass
                return True, None
        return False, 'No small slot available to stow it.'

    if chosen.lower() == 'pick up':
        if not player or not room:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'You are nowhere.'}], []
        if not obj and obj_uuid:
            # Perhaps someone else took it
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'The {name} is no longer here.',
            }], []
        if obj is None:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'The {name} is no longer here.',
            }], []
        # Don't allow picking up immovable/travel points
        try:
            tags = set(getattr(obj, 'object_tags', []) or [])
        except Exception:
            tags = set()
        if 'Immovable' in tags or 'Travel Point' in tags:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'The {name} cannot be picked up.',
            }], []
        # Default policy: stow into appropriate slot; if none, try hands
        # Remove from room first
        try:
            if obj is not None:
                room.objects.pop(obj.uuid, None)
        except Exception:
            pass
            
        # Attempt to place object in inventory with enhanced validation
        okp, errp = _place_stowed(obj)
        if not okp:
            okh, errh, _idx = _place_in_hand(obj)
            if not okh:
                # Put back in room if failed
                try:
                    if obj is not None:
                        room.objects[obj.uuid] = obj
                except Exception:
                    pass
                sessions.pop(sid, None)
                return True, None, [{
                    'type': 'error',
                    'content': (errp or errh or 'No space to pick that up.'),
                }], []
        
        # Object successfully picked up - transfer ownership atomically
        if obj and player:
            try:
                # Transfer ownership to the picking player
                obj.owner_id = player.user_id  # type: ignore[attr-defined]
            except Exception:
                # If ownership transfer fails, continue anyway (non-critical)
                pass
        
        sessions.pop(sid, None)
        return True, None, [{'type': 'system', 'content': f'You pick up the {name}.'}], []

    if chosen.lower() == 'wield':
        if not player or not room:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'You are nowhere.'}], []
        # If in room, take it; if stowed, move it; if already in hand, just confirm
        source = obj_loc or ('room' if obj_uuid and obj_uuid in (room.objects or {}) else None)
        if source == 'room' or source is None:
            if not obj and obj_uuid:
                sessions.pop(sid, None)
                return True, None, [{
                    'type': 'system',
                    'content': f'The {name} is no longer here.',
                }], []
            # Remove from room and place in hand
            try:
                if obj is not None:
                    room.objects.pop(obj.uuid, None)
            except Exception:
                pass
            okh, errh, which = _place_in_hand(obj)
            if not okh:
                # put back
                try:
                    if obj is not None:
                        room.objects[obj.uuid] = obj
                except Exception:
                    pass
                sessions.pop(sid, None)
                return True, None, [{
                    'type': 'error',
                    'content': errh or 'Your hands are full.',
                }], []
            
            # Transfer ownership when wielding from room
            if obj and player:
                try:
                    obj.owner_id = player.user_id  # type: ignore[attr-defined]
                except Exception:
                    pass
                    
            hand_name = 'right hand' if which == 1 else 'left hand'
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'You wield the {name} in your {hand_name}.',
            }], []
        if source in ('small', 'large'):
            if inv is None:
                sessions.pop(sid, None)
                return True, None, [{'type': 'error', 'content': 'No inventory available.'}], []
            # Move from stowed to a hand
            # Remove from slot
            if source == 'small' and stow_index is not None:
                inv.slots[stow_index] = None
            if source == 'large' and stow_large_index is not None:
                inv.slots[stow_large_index] = None
            okh, errh, which = _place_in_hand(obj)
            if not okh:
                # put back into the same stow slot on failure
                if source == 'small' and stow_index is not None:
                    inv.slots[stow_index] = obj
                if source == 'large' and stow_large_index is not None:
                    inv.slots[stow_large_index] = obj
                sessions.pop(sid, None)
                return True, None, [{
                    'type': 'error',
                    'content': errh or 'Your hands are full.',
                }], []
            hand_name = 'right hand' if which == 1 else 'left hand'
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'You wield the {name} in your {hand_name}.',
            }], []
        if source == 'hand':
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'You are already holding the {name}.',
            }], []

    # Sleep interaction on a bed (must be owned by the player)
    if chosen.lower() == 'sleep':
        if not player:
            sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'Please authenticate first.'}], []
        room = world.rooms.get(player.room_id) if player else None
        if not room:
            sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'You are nowhere.'}], []
        if not obj and obj_uuid:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'The {name} is no longer here.',
            }], []
        # Verify the target is a bed by tag (case-insensitive)
        try:
            tags_now = {str(t).strip().lower() for t in (getattr(obj, 'object_tags', []) or [])}
        except Exception:
            tags_now = set()
        if 'bed' not in tags_now:
            sessions.pop(sid, None)
            return True, None, [{'type': 'system', 'content': "You can't sleep on that."}], []
        # Resolve acting user id by matching the player's sheet to a user record
        actor_uid = None
        try:
            for uid, user in (getattr(world, 'users', {}) or {}).items():
                if getattr(user, 'sheet', None) is player.sheet:
                    actor_uid = uid
                    break
        except Exception:
            actor_uid = None
        if not actor_uid:
            sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'Session error.'}], []
        # Ownership check: player must own the bed
        owner = getattr(obj, 'owner_id', None)
        if owner != actor_uid:
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': 'You can only sleep in a bed you own.',
            }], []
        # Restore a chunk of sleep and set home bed
        try:
            cur = getattr(player.sheet, 'sleep', 100.0) or 0.0
            # Use the same default refill amount as server's constant (10.0)
            # to avoid importing server.py
            player.sheet.sleep = _clamp_need(cur + 10.0)
        except Exception:
            pass
        try:
            user = (getattr(world, 'users', {}) or {}).get(actor_uid)
            if user is not None:
                user.home_bed_uuid = getattr(obj, 'uuid', None)
        except Exception:
            pass
        # Build emits/broadcasts; server will persist after handling
        broadcasts.append((
            player.room_id,
            {
                'type': 'system',
                'content': (
                    f"[i]{player.sheet.display_name} takes a quick rest on their bed.[/i]"
                ),
            },
        ))
        with atomic('interaction_sessions'):
            sessions.pop(sid, None)
        return True, None, [{
            'type': 'system',
            'content': 'Your data was saved. You feel well rested.',
        }], broadcasts

    if (
        chosen.lower() == 'eat'
        or chosen.lower().startswith('eat (')
        or chosen.lower() == 'drink'
        or chosen.lower().startswith('drink (')
    ):
        if not player or not room:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'You are nowhere.'}], []
        # Enforce numeric tag presence before consuming when the tag exists
        tags_now = set(getattr(obj, 'object_tags', []) or []) if obj else set()

        def _parse_tag_val2(ts: set[str], key: str) -> int | None:
            keyl = key.lower()
            for x in ts:
                s = str(x)
                parts = s.split(':', 1)
                if len(parts) != 2:
                    continue
                if parts[0].strip().lower() == keyl:
                    r = parts[1].strip()
                    if r.startswith('+'):
                        r = r[1:]
                    if r.lstrip('-').isdigit():
                        try:
                            return int(r)
                        except Exception:
                            return None
            return None
        need_key = 'Drinkable' if chosen.lower().startswith('drink') else 'Edible'
        has_key = any(
            str(t).split(':', 1)[0].strip().lower() == need_key.lower()
            for t in tags_now
        )
        if has_key and _parse_tag_val2(tags_now, need_key) is None:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{
                'type': 'error',
                'content': (
                    f"This item requires a numeric '{need_key}: N' tag to be used."
                ),
            }], []
        # Remove source (room or inventory) and spawn deconstruct outputs into room
        if inv is None:
            with atomic('interaction_sessions'):
                sessions.pop(sid, None)
            return True, None, [{'type': 'error', 'content': 'No inventory available.'}], []
        if obj_loc == 'hand' and hand_index is not None:
            inv.slots[hand_index] = None
        elif obj_loc == 'small' and stow_index is not None:
            inv.slots[stow_index] = None
        elif obj_loc == 'large' and stow_large_index is not None:
            inv.slots[stow_large_index] = None
        elif room and obj and obj.uuid in (room.objects or {}):
            try:
                room.objects.pop(obj.uuid, None)
            except Exception:
                pass
        # Spawn outputs
        created_names: list[str] = []
        try:
            outputs = list(getattr(obj, 'deconstruct_recipe', []) or [])
        except Exception:
            outputs = []
        if outputs:
            for base in outputs:
                try:
                    # Clone via to_dict/from_dict to ensure new UUID
                    from world import Object as _Obj
                    if hasattr(base, 'to_dict'):
                        clone = _Obj.from_dict(base.to_dict())
                    else:
                        clone = _Obj.from_dict(base)
                    room.objects[clone.uuid] = clone
                    created_names.append(getattr(clone, 'display_name', 'Object'))
                except Exception:
                    continue
        with atomic('interaction_sessions'):
            sessions.pop(sid, None)
        line = 'drink' if chosen.lower().startswith('drink') else 'eat'
        msg = f'You {line} the {name}.'
        if created_names:
            msg += " You now have: " + ", ".join(created_names) + "."
        return True, None, [{'type': 'system', 'content': msg}], []

    if chosen.lower() == 'open':
        # Container inventory listing
        if not obj:
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'The {name} is no longer here.',
            }], []
        tags = set(getattr(obj, 'object_tags', []) or [])
        if 'Container' not in tags:
            sessions.pop(sid, None)
            return True, None, [{'type': 'system', 'content': f"The {name} can't be opened."}], []
        if not getattr(obj, 'container_searched', False):
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f"You should search the {name} before opening it.",
            }], []
        # Mark opened and print contents
        try:
            obj.container_opened = True
        except Exception:
            pass

        def _names(lst):
            return [getattr(o, 'display_name', 'Unnamed') for o in lst if o]
        small = _names(getattr(obj, 'container_small_slots', []) or [])
        large = _names(getattr(obj, 'container_large_slots', []) or [])
        if not small and not large:
            content = f"You open the {name}. It's empty."
        else:
            bits = []
            if small:
                bits.append("Small: " + ", ".join(small))
            if large:
                bits.append("Large: " + ", ".join(large))
            content = f"You open the {name}. Inside: " + "; ".join(bits)
        sessions.pop(sid, None)
        return True, None, [{'type': 'system', 'content': content}], []

    if chosen.lower() == 'search':
        if not obj:
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f'The {name} is no longer here.',
            }], []
        tags = set(getattr(obj, 'object_tags', []) or [])
        if 'Container' not in tags:
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': "You find nothing noteworthy.",
            }], []
        if getattr(obj, 'container_searched', False):
            sessions.pop(sid, None)
            return True, None, [{
                'type': 'system',
                'content': f"You've already searched the {name}.",
            }], []
        # Mark searched
        try:
            obj.container_searched = True
        except Exception:
            pass
        # Low chance to spawn an item whose loot_location_hint references this container
        # Decide chance by 20% on d%
        try:
            pct = dice_roll('d%').total
        except Exception:
            pct = random.randint(1, 100)
        spawned = None
        if pct <= 20:
            try:
                from world import Object as _Obj
                matches: list[Any] = []
                for tmpl in (getattr(world, 'object_templates', {}) or {}).values():
                    try:
                        llh = getattr(tmpl, 'loot_location_hint', None)
                        obj_name = getattr(obj, 'display_name', '').strip().lower()
                        loot_name = getattr(llh, 'display_name', '').strip().lower()
                        if llh and loot_name == obj_name:
                            matches.append(tmpl)
                    except Exception:
                        continue
                if matches:
                    base = random.choice(matches)
                    if hasattr(base, 'to_dict'):
                        spawned = _Obj.from_dict(base.to_dict())
                    else:
                        spawned = _Obj.from_dict(base)
                    # Place into appropriate container slot
                    tags2 = set(getattr(spawned, 'object_tags', []) or [])
                    placed = False
                    if 'large' in tags2:
                        for i in range(0, 2):
                            slots = getattr(obj, 'container_large_slots', [None, None])
                            if slots[i] is None:
                                obj.container_large_slots[i] = spawned
                                placed = True
                                break
                    else:
                        for i in range(0, 2):
                            slots = getattr(obj, 'container_small_slots', [None, None])
                            if slots[i] is None:
                                obj.container_small_slots[i] = spawned
                                placed = True
                                break
                    if not placed:
                        spawned = None  # no space; discard spawn silently
            except Exception:
                spawned = None
        msg = f"You search the {name}."
        if spawned:
            msg += f" You find a {getattr(spawned, 'display_name', 'mystery item')}!"
        else:
            msg += " You don't find anything of value."
        sessions.pop(sid, None)
        return True, None, [{'type': 'system', 'content': msg}], []

    # Default acknowledgement
    with atomic('interaction_sessions'):
        sessions.pop(sid, None)
    return True, None, [{
        'type': 'system',
        'content': f"You attempt to {chosen.lower()} the {name}.",
    }], []
