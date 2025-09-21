from __future__ import annotations

"""
interaction_service.py — Player-facing object interaction flow.

Contract:
- begin_interaction(world, sid, room, object_name, sessions) -> (ok: bool, err: str|None, emits: list[dict])
- handle_interaction_input(world, sid, text, sessions) -> (handled: bool, emits: list[dict])

This service is intentionally tiny and side-effect free (no socket calls here).
It lists possible interactions based on an Object's tags and guides the player
through choosing one. For now, choosing an interaction simply acknowledges the
choice; "Step Away" cancels the flow cleanly.

We derive interactions from tags in a conservative way. Unknown tags just don't
add actions. "Step Away" is always available so players can cancel.
"""

from typing import Tuple, List, Dict, Any
import random
from dice_utils import roll as dice_roll
from movement_service import move_through_door


# Map object tags -> human actions (labels). Keep these short and friendly.
_TAG_TO_ACTIONS: dict[str, list[str]] = {
    # Mobility / world geometry
    "Travel Point": ["Move Through"],
    # Carrying / equipment
    "one-hand": ["Pick Up"],
    "two-hand": ["Pick Up"],
    "weapon": ["Wield"],
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


def _actions_for_object(obj) -> list[str]:
    actions: list[str] = []
    try:
        tags = set(getattr(obj, 'object_tags', []) or [])
        for t in tags:
            tstr = str(t)
            if tstr in _TAG_TO_ACTIONS:
                actions.extend(_TAG_TO_ACTIONS[tstr])
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


def begin_interaction(world, sid: str, room, object_name: str, sessions: Dict[str, dict]) -> tuple[bool, str | None, list[dict]]:
    if not sid or sid not in world.players:
        return False, 'Please authenticate first.', []
    if not room:
        return False, 'You are nowhere.', []
    from look_service import resolve_object_in_room  # local import to avoid cycles at module import time
    obj, suggestions = resolve_object_in_room(room, object_name)
    if obj is None:
        if suggestions:
            return False, "Did you mean: " + ", ".join(suggestions) + "?", []
        return False, f"You don't see '{object_name}' here.", []

    actions = _actions_for_object(obj)
    # Stash session state
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
    return True, None, emits


def handle_interaction_input(world, sid: str, text: str, sessions: Dict[str, dict]) -> tuple[bool, list[dict], list[tuple[str, dict]]]:
    """Handle a follow-up input while in the interaction session.

    Returned handled=False if no active session; otherwise True with resulting emits.
    """
    sess = sessions.get(sid)
    if not sess:
        return False, [], []
    step = sess.get('step')
    if step != 'choose':
        # Unknown state: fail-safe cancel
        sessions.pop(sid, None)
        return True, [{'type': 'system', 'content': 'Interaction cancelled.'}], []

    raw = (text or '').strip()
    low = raw.lower()
    name = sess.get('obj_name') or 'object'
    broadcasts: list[tuple[str, dict]] = []
    actions: list[str] = list(sess.get('actions') or [])

    # Friendly cancel words
    if low in ('cancel', 'back', 'exit', 'quit', 'step away'):
        sessions.pop(sid, None)
        return True, [{'type': 'system', 'content': f'You step away from {name}.'}], []

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
        return True, [
            {'type': 'system', 'content': "I didn't catch that. Please pick one of the options (number or name)."},
            {'type': 'system', 'content': msg},
        ], []

    # Always allow cancelling via Step Away
    if chosen.lower() == 'step away':
        sessions.pop(sid, None)
        return True, [{'type': 'system', 'content': f'You step away from {name}.'}], []

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
                obj = it; obj_loc = 'hand'; hand_index = i; break
        if not obj:
            for i in range(2, 6):
                it = inv.slots[i]
                if it and getattr(it, 'uuid', None) == obj_uuid:
                    obj = it; obj_loc = 'small'; stow_index = i; break
        if not obj:
            for i in range(6, 8):
                it = inv.slots[i]
                if it and getattr(it, 'uuid', None) == obj_uuid:
                    obj = it; obj_loc = 'large'; stow_large_index = i; break

    if chosen.lower() == 'move through':
        # Delegate to movement service using the object's display name
        if not obj:
            # If missing, try by stored name
            target_name = name
        else:
            target_name = getattr(obj, 'display_name', name)
        ok, err, emits_m, broadcasts_m = move_through_door(world, sid, target_name)
        sessions.pop(sid, None)
        if not ok:
            return True, [{'type': 'error', 'content': err or 'You cannot go that way.'}], []
        return True, emits_m, broadcasts_m

    def _place_in_hand(o) -> tuple[bool, str | None, int | None]:
        # Prefer right hand (1), then left hand (0)
        if inv is None:
            return False, 'No inventory available.', None
        if inv.slots[1] is None:
            inv.slots[1] = o
            # Remove 'stowed' if present
            try:
                getattr(o, 'object_tags', set()).discard('stowed')
            except Exception:
                pass
            return True, None, 1
        if inv.slots[0] is None:
            inv.slots[0] = o
            try:
                getattr(o, 'object_tags', set()).discard('stowed')
            except Exception:
                pass
            return True, None, 0
        return False, 'Your hands are full.', None

    def _place_stowed(o) -> tuple[bool, str | None]:
        if inv is None:
            return False, 'No inventory available.'
        tags = set(getattr(o, 'object_tags', []) or [])
        # two-hand items go to large, one-hand to small
        if 'two-hand' in tags:
            for i in range(6, 8):
                if inv.slots[i] is None:
                    inv.slots[i] = o
                    try:
                        getattr(o, 'object_tags', set()).add('stowed')
                    except Exception:
                        pass
                    return True, None
            return False, 'No large slot available to stow it.'
        # default one-hand
        for i in range(2, 6):
            if inv.slots[i] is None:
                inv.slots[i] = o
                try:
                    getattr(o, 'object_tags', set()).add('stowed')
                except Exception:
                    pass
                return True, None
        return False, 'No small slot available to stow it.'

    if chosen.lower() == 'pick up':
        if not player or not room:
            sessions.pop(sid, None)
            return True, [{'type': 'error', 'content': 'You are nowhere.'}], []
        if not obj and obj_uuid:
            # Perhaps someone else took it
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'The {name} is no longer here.'}], []
        if obj is None:
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'The {name} is no longer here.'}], []
        # Don't allow picking up immovable/travel points
        try:
            tags = set(getattr(obj, 'object_tags', []) or [])
        except Exception:
            tags = set()
        if 'Immovable' in tags or 'Travel Point' in tags:
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'The {name} cannot be picked up.'}], []
        # Default policy: stow into appropriate slot; if none, try hands
        # Remove from room first
        try:
            if obj is not None:
                room.objects.pop(obj.uuid, None)
        except Exception:
            pass
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
                return True, [{'type': 'error', 'content': errp or errh or 'No space to pick that up.'}], []
        sessions.pop(sid, None)
        return True, [{'type': 'system', 'content': f'You pick up the {name}.'}], []

    if chosen.lower() == 'wield':
        if not player or not room:
            sessions.pop(sid, None)
            return True, [{'type': 'error', 'content': 'You are nowhere.'}], []
        # If in room, take it; if stowed, move it; if already in hand, just confirm
        source = obj_loc or ('room' if obj_uuid and obj_uuid in (room.objects or {}) else None)
        if source == 'room' or source is None:
            if not obj and obj_uuid:
                sessions.pop(sid, None)
                return True, [{'type': 'system', 'content': f'The {name} is no longer here.'}], []
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
                return True, [{'type': 'error', 'content': errh or 'Your hands are full.'}], []
            hand_name = 'right hand' if which == 1 else 'left hand'
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'You wield the {name} in your {hand_name}.'}], []
        if source in ('small', 'large'):
            if inv is None:
                sessions.pop(sid, None)
                return True, [{'type': 'error', 'content': 'No inventory available.'}], []
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
                return True, [{'type': 'error', 'content': errh or 'Your hands are full.'}], []
            hand_name = 'right hand' if which == 1 else 'left hand'
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'You wield the {name} in your {hand_name}.'}], []
        if source == 'hand':
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'You are already holding the {name}.'}], []

    if chosen.lower() in ('eat', 'drink'):
        if not player or not room:
            sessions.pop(sid, None)
            return True, [{'type': 'error', 'content': 'You are nowhere.'}], []
        # Remove source (room or inventory) and spawn deconstruct outputs into room
        removed = False
        if inv is None:
            sessions.pop(sid, None)
            return True, [{'type': 'error', 'content': 'No inventory available.'}], []
        if obj_loc == 'hand' and hand_index is not None:
            inv.slots[hand_index] = None; removed = True
        elif obj_loc == 'small' and stow_index is not None:
            inv.slots[stow_index] = None; removed = True
        elif obj_loc == 'large' and stow_large_index is not None:
            inv.slots[stow_large_index] = None; removed = True
        elif room and obj and obj.uuid in (room.objects or {}):
            try:
                room.objects.pop(obj.uuid, None)
                removed = True
            except Exception:
                removed = False
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
                    clone = _Obj.from_dict(base.to_dict()) if hasattr(base, 'to_dict') else _Obj.from_dict(base)
                    room.objects[clone.uuid] = clone
                    created_names.append(getattr(clone, 'display_name', 'Object'))
                except Exception:
                    continue
        sessions.pop(sid, None)
        line = 'drink' if chosen.lower() == 'drink' else 'eat'
        msg = f'You {line} the {name}.'
        if created_names:
            msg += " You now have: " + ", ".join(created_names) + "."
        return True, [{'type': 'system', 'content': msg}], []

    if chosen.lower() == 'open':
        # Container inventory listing
        if not obj:
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'The {name} is no longer here.'}], []
        tags = set(getattr(obj, 'object_tags', []) or [])
        if 'Container' not in tags:
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f"The {name} can't be opened."}], []
        if not getattr(obj, 'container_searched', False):
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f"You should search the {name} before opening it."}], []
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
        return True, [{'type': 'system', 'content': content}], []

    if chosen.lower() == 'search':
        if not obj:
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f'The {name} is no longer here.'}], []
        tags = set(getattr(obj, 'object_tags', []) or [])
        if 'Container' not in tags:
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f"You find nothing noteworthy."}], []
        if getattr(obj, 'container_searched', False):
            sessions.pop(sid, None)
            return True, [{'type': 'system', 'content': f"You've already searched the {name}."}], []
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
                        if llh and getattr(llh, 'display_name', '').strip().lower() == (getattr(obj, 'display_name', '').strip().lower()):
                            matches.append(tmpl)
                    except Exception:
                        continue
                if matches:
                    base = random.choice(matches)
                    spawned = _Obj.from_dict(base.to_dict()) if hasattr(base, 'to_dict') else _Obj.from_dict(base)
                    # Place into appropriate container slot
                    tags2 = set(getattr(spawned, 'object_tags', []) or [])
                    placed = False
                    if 'two-hand' in tags2:
                        for i in range(0, 2):
                            if getattr(obj, 'container_large_slots', [None, None])[i] is None:
                                obj.container_large_slots[i] = spawned
                                placed = True; break
                    else:
                        for i in range(0, 2):
                            if getattr(obj, 'container_small_slots', [None, None])[i] is None:
                                obj.container_small_slots[i] = spawned
                                placed = True; break
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
        return True, [{'type': 'system', 'content': msg}], []

    # Default acknowledgement
    sessions.pop(sid, None)
    return True, [{'type': 'system', 'content': f"You attempt to {chosen.lower()} the {name}."}], []
