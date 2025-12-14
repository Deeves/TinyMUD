"""Game loop and world tick functionality.

This module contains the world heartbeat logic including:
- NPC needs decay and action point regeneration
- NPC action execution (move, get, consume, emote, say, etc.)
- GOAP planning and plan execution
- Heartbeat thread management
"""
from __future__ import annotations

import os
import time
import random
from typing import Any, Callable, cast

from safe_utils import safe_call, safe_call_with_default
from id_parse_utils import fuzzy_resolve, resolve_door_name
from world import World, CharacterSheet, Room
import daily_system
import mission_service
from combat_service import attack


# --- Configuration from environment ---
def _env_int(name: str, default: int) -> int:
    try:
        val = os.getenv(name)
        if val is None:
            return default
        return int(str(val).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        val = os.getenv(name)
        if val is None:
            return default
        return float(str(val).strip())
    except Exception:
        return default


TICK_SECONDS = _env_int('MUD_TICK_SECONDS', 60)
AP_MAX = _env_int('MUD_AP_MAX', 3)
NEED_DROP_PER_TICK = _env_float('MUD_NEED_DROP', 1.0)
NEED_THRESHOLD = _env_float('MUD_NEED_THRESHOLD', 25.0)
SOCIAL_DROP_PER_TICK = _env_float('MUD_SOCIAL_DROP', 0.5)
SOCIAL_REFILL_ON_CHAT = _env_float('MUD_SOCIAL_REFILL', 10.0)
SOCIAL_SIM_REFILL_TICK = _env_float('MUD_SOCIAL_SIM_TICK', 5.0)
SOCIAL_REFILL_EMOTE = _env_float('MUD_SOCIAL_REFILL_EMOTE', 15.0)
SLEEP_DROP_PER_TICK = _env_float('MUD_SLEEP_DROP', 0.75)
SLEEP_REFILL_PER_TICK = _env_float('MUD_SLEEP_REFILL', 10.0)
SLEEP_TICKS_DEFAULT = _env_int('MUD_SLEEP_TICKS', 3)


def _clamp_need(v: float) -> float:
    """Clamp a need value to [0, 100]."""
    try:
        return max(0.0, min(100.0, float(v)))
    except Exception:
        return 0.0


def _parse_tag_value(tags: set[str] | list[str] | None, key: str) -> int | None:
    """Return the integer suffix from a tag like 'Edible: 20' or 'Drinkable: 15'."""
    if not tags:
        return None
    return safe_call_with_default(lambda: _parse_tag_value_inner(tags, key), None)


def _parse_tag_value_inner(tags, key: str) -> int | None:
    """Helper function for _parse_tag_value with actual parsing logic."""
    key_low = key.strip().lower()
    for t in list(tags):
        s = safe_call_with_default(lambda: str(t), "")
        if not s:
            continue
        parts = s.split(':', 1)
        if len(parts) != 2:
            continue
        left, right = parts[0].strip().lower(), parts[1].strip()
        if left == key_low and right:
            r = right
            if r.startswith('+'):
                r = r[1:]
            if r.lstrip('-').isdigit():
                return safe_call_with_default(lambda: int(r), None)
    return None


def _nutrition_from_tags_or_fields(obj) -> tuple[int, int]:
    """Return (satiation, hydration) preferring tag-driven values over legacy fields."""
    tags = safe_call_with_default(lambda: set(getattr(obj, 'object_tags', []) or []), set())
    sv_tag = _parse_tag_value(tags, 'Edible')
    hv_tag = _parse_tag_value(tags, 'Drinkable')
    has_edible_key = any(str(t).split(':', 1)[0].strip().lower() == 'edible' for t in tags)
    has_drink_key = any(str(t).split(':', 1)[0].strip().lower() == 'drinkable' for t in tags)

    sv_field = int(getattr(obj, 'satiation_value', 0) or 0)
    hv_field = int(getattr(obj, 'hydration_value', 0) or 0)

    if has_edible_key or has_drink_key:
        sv = sv_tag if sv_tag is not None else 0
        hv = hv_tag if hv_tag is not None else 0
    else:
        sv = sv_field
        hv = hv_field
    return int(sv or 0), int(hv or 0)


class GameLoopContext:
    """Context object holding references needed by game loop functions.
    
    This avoids passing many parameters to each function and makes the
    code easier to test with mock contexts.
    """
    def __init__(
        self,
        world: World,
        state_path: str,
        socketio: Any,
        broadcast_to_room: Callable,
        save_debounce: Callable,
        sessions: dict,
        admins: set,
        plan_model: Any = None,
    ):
        self.world = world
        self.state_path = state_path
        self.socketio = socketio
        self.broadcast_to_room = broadcast_to_room
        self.save_debounce = save_debounce
        self.sessions = sessions
        self.admins = admins
        self.plan_model = plan_model


# Global context - set by server.py during initialization
_ctx: GameLoopContext | None = None


def init_game_loop(ctx: GameLoopContext) -> None:
    """Initialize the game loop with a context object."""
    global _ctx
    _ctx = ctx


def get_context() -> GameLoopContext:
    """Get the current game loop context."""
    if _ctx is None:
        raise RuntimeError("Game loop not initialized. Call init_game_loop() first.")
    return _ctx


def update_broadcast_to_room(broadcast_fn) -> None:
    """Update the broadcast_to_room function in the context.
    
    This is primarily for test compatibility - tests that patch server.broadcast_to_room
    can call this to update the game_loop context's reference as well.
    """
    if _ctx is not None:
        _ctx.broadcast_to_room = broadcast_fn


# --- NPC Helper Functions ---

def _npc_find_room_for(npc_name: str) -> str | None:
    """Search rooms where this NPC is present."""
    ctx = get_context()
    def _find_room():
        for rid, room in ctx.world.rooms.items():
            if npc_name in (room.npcs or set()):
                return rid
        return None
    return safe_call(_find_room) or None


def _ensure_npc_sheet(npc_name: str) -> CharacterSheet:
    """Ensure an NPC has a CharacterSheet in world.npc_sheets."""
    ctx = get_context()
    if npc_name not in ctx.world.npc_sheets:
        ctx.world.npc_sheets[npc_name] = CharacterSheet(
            display_name=npc_name,
            description=f"A character named {npc_name}."
        )
    return ctx.world.npc_sheets[npc_name]


def _npc_gain_socialization(npc_name: str, amount: float) -> None:
    """Increase an NPC's socialization meter, clamped to [0,100]."""
    try:
        sheet = _ensure_npc_sheet(npc_name)
        current = getattr(sheet, 'socialization', 100.0) or 100.0
        sheet.socialization = _clamp_need(current + amount)
    except Exception:
        pass


def _find_inventory_slot(inv, obj) -> int | None:
    """Find a compatible inventory slot for an object."""
    if inv is None:
        return None
    try:
        tags = set(getattr(obj, 'object_tags', []) or [])
        is_large = any(str(t).strip().lower() == 'large' for t in tags)
        slots = getattr(inv, 'slots', [])
        # Large items go in slots 0-1 (hands), small in 2-7
        if is_large:
            for i in range(min(2, len(slots))):
                if slots[i] is None:
                    return i
        else:
            for i in range(2, len(slots)):
                if i < len(slots) and slots[i] is None:
                    return i
            # Fall back to hands if small slots are full
            for i in range(min(2, len(slots))):
                if slots[i] is None:
                    return i
    except Exception:
        pass
    return None


# --- NPC Action Execution Functions ---

def _npc_exec_get_object(npc_name: str, room_id: str, object_name: str) -> tuple[bool, str]:
    """Pick up an object from the room into the NPC's inventory."""
    ctx = get_context()
    room = ctx.world.rooms.get(room_id)
    sheet = _ensure_npc_sheet(npc_name)
    if not room:
        return False, "room not found"
    
    candidates = list((room.objects or {}).values())
    
    def _score(o, q):
        n = getattr(o, 'display_name', '') or ''
        nl = n.lower()
        ql = q.lower()
        if nl == ql:
            return 3
        if nl.startswith(ql):
            return 2
        if ql in nl:
            return 1
        return 0
    
    best = None
    best_s = 0
    for o in candidates:
        s = _score(o, object_name)
        if s > best_s:
            best, best_s = o, s
    
    if best is None:
        def _is_nutritious(o):
            sv, hv = _nutrition_from_tags_or_fields(o)
            return (sv > 0) or (hv > 0)
        best = next((o for o in candidates if _is_nutritious(o)), None)
    
    if best is None:
        return False, "object not found"
    
    slot = _find_inventory_slot(sheet.inventory, best)
    if slot is None:
        return False, "no free slot"
    
    safe_call(room.objects.pop, best.uuid, None)
    ok = sheet.inventory.place(slot, best)
    if not ok:
        room.objects[best.uuid] = best
        return False, "cannot carry"
    
    ctx.broadcast_to_room(room_id, {
        'type': 'system',
        'content': f"[i]{npc_name} picks up the {best.display_name}[/i]"
    })
    return True, best.uuid


def _npc_exec_consume_object(npc_name: str, room_id: str, object_uuid: str) -> tuple[bool, str]:
    """Consume an object in inventory, applying satiation/hydration and removing it."""
    ctx = get_context()
    sheet = _ensure_npc_sheet(npc_name)
    inv = sheet.inventory
    idx = None
    obj = None
    for i, it in enumerate(inv.slots):
        if it and getattr(it, 'uuid', None) == object_uuid:
            idx = i
            obj = it
            break
    if idx is None or obj is None:
        return False, "object not in inventory"
    
    sv, hv = _nutrition_from_tags_or_fields(obj)
    sheet.hunger = _clamp_need(sheet.hunger + float(sv))
    sheet.thirst = _clamp_need(sheet.thirst + float(hv))
    safe_call(inv.remove, idx)
    
    which = []
    if sv:
        which.append('eats')
    if hv and not sv:
        which.append('drinks')
    action_word = 'consumes' if not which else which[0]
    ctx.broadcast_to_room(room_id, {
        'type': 'system',
        'content': f"[i]{npc_name} {action_word} the {getattr(obj, 'display_name', 'item')}[/i]"
    })
    return True, "ok"


def _npc_exec_do_nothing(npc_name: str, room_id: str) -> tuple[bool, str]:
    """NPC pauses to think."""
    ctx = get_context()
    ctx.broadcast_to_room(room_id, {'type': 'system', 'content': f"[i]{npc_name} pauses to think.[/i]"})
    return True, "ok"


def _npc_exec_emote(npc_name: str, room_id: str, message: str | None = None) -> tuple[bool, str]:
    """Perform a lightweight emote to the room and refill socialization."""
    ctx = get_context()
    text = safe_call_with_default(
        lambda: message.strip() if isinstance(message, str) else "", 
        ""
    )
    content = f"[i]{npc_name} {text}[/i]" if text else f"[i]{npc_name} looks around, humming softly.[/i]"
    ctx.broadcast_to_room(room_id, {'type': 'system', 'content': content})
    safe_call(_npc_gain_socialization, npc_name, SOCIAL_REFILL_EMOTE)
    return True, "ok"


def _npc_exec_say(npc_name: str, room_id: str, message: str) -> tuple[bool, str]:
    """NPC says something to the room."""
    ctx = get_context()
    if not message:
        return False, "nothing to say"
    ctx.broadcast_to_room(room_id, {
        'type': 'npc',
        'name': npc_name,
        'content': message
    })
    safe_call(_npc_gain_socialization, npc_name, SOCIAL_REFILL_ON_CHAT)
    return True, "ok"


def _npc_exec_drop(npc_name: str, room_id: str, object_uuid: str) -> tuple[bool, str]:
    """NPC drops an object from inventory into the room."""
    ctx = get_context()
    sheet = _ensure_npc_sheet(npc_name)
    room = ctx.world.rooms.get(room_id)
    if not room:
        return False, "room not found"
    
    inv = sheet.inventory
    idx = None
    obj = None
    for i, it in enumerate(inv.slots):
        if it and getattr(it, 'uuid', None) == object_uuid:
            idx = i
            obj = it
            break
    
    if idx is None or obj is None:
        return False, "object not in inventory"
    
    safe_call(inv.remove, idx)
    room.objects[obj.uuid] = obj
    
    ctx.broadcast_to_room(room_id, {
        'type': 'system',
        'content': f"[i]{npc_name} drops the {getattr(obj, 'display_name', 'item')}.[/i]"
    })
    return True, "ok"


def _npc_exec_look(npc_name: str, room_id: str, target_name: str) -> tuple[bool, str]:
    """NPC examines a target object."""
    ctx = get_context()
    ctx.broadcast_to_room(room_id, {
        'type': 'system',
        'content': f"[i]{npc_name} examines the {target_name}.[/i]"
    })
    
    sheet = _ensure_npc_sheet(npc_name)
    room = ctx.world.rooms.get(room_id)
    
    if room:
        target_obj = None
        for obj in (room.objects or {}).values():
            if getattr(obj, 'display_name', '') == target_name:
                target_obj = obj
                break
        
        if target_obj:
            setattr(target_obj, 'investigated_by_' + npc_name, True)
            try:
                from autonomous_npc_service import add_memory
                add_memory(sheet, 'investigated_object', {
                    'object_name': target_name,
                    'room_id': room_id
                })
            except ImportError:
                pass
    
    return True, "ok"


def _npc_exec_move_through(npc_name: str, room_id: str, name_in: str) -> tuple[bool, str]:
    """NPC moves through a door or travel point to an adjacent room."""
    ctx = get_context()
    room = ctx.world.rooms.get(room_id)
    if not room:
        return False, "room not found"
    
    # Trim leading articles
    low = name_in.lower()
    for art in ("the ", "a ", "an "):
        if low.startswith(art):
            name_in = name_in[len(art):].strip()
            break
    
    # Auto-pick if only one exit
    if not name_in:
        candidates: list[str] = []
        room_doors = safe_call_with_default(lambda: getattr(room, 'doors', {}) or {}, {})
        candidates.extend(list(room_doors.keys()))
        room_objects = safe_call_with_default(lambda: getattr(room, 'objects', {}) or {}, {})
        for _oid, obj in room_objects.items():
            tags = safe_call_with_default(lambda: set(getattr(obj, 'object_tags', []) or []), set())
            if 'Travel Point' in tags:
                dn = safe_call_with_default(lambda: (getattr(obj, 'display_name', None) or '').strip(), '')
                if dn:
                    candidates.append(dn)
        uniq = sorted(set(candidates))
        if len(uniq) == 1:
            name_in = uniq[0]
        else:
            name_in = ''
    
    target_room_id: str | None = None
    resolved_label = name_in
    
    if name_in:
        # Try named doors first
        ok_d, _err_d, resolved_door = resolve_door_name(room, name_in)
        if ok_d and resolved_door:
            resolved_label = resolved_door
            target_room_id = (room.doors or {}).get(resolved_door)
        else:
            # Try Travel Point objects
            tp_name_to_ids: dict[str, list[str]] = {}
            try:
                for oid, obj in (getattr(room, 'objects', {}) or {}).items():
                    try:
                        tags = set(getattr(obj, 'object_tags', []) or [])
                    except Exception:
                        tags = set()
                    if 'Travel Point' in tags:
                        dn = (getattr(obj, 'display_name', None) or '').strip()
                        if dn:
                            tp_name_to_ids.setdefault(dn, []).append(oid)
            except Exception:
                tp_name_to_ids = {}
            
            tp_names = list(tp_name_to_ids.keys())
            if tp_names:
                ok_tp, _err_tp, resolved_tp = fuzzy_resolve(name_in, tp_names)
                if ok_tp and resolved_tp:
                    resolved_label = resolved_tp
                    oid = tp_name_to_ids[resolved_tp][0]
                    obj = room.objects.get(oid)
                    target_room_id = getattr(obj, 'link_target_room_id', None)
    
    if not target_room_id or target_room_id not in ctx.world.rooms:
        return False, "target not found"
    
    # Enforce door locks
    permitted = True
    try:
        locks = getattr(room, 'door_locks', {}) or {}
        if resolved_label in locks:
            policy = locks.get(resolved_label)
            if not isinstance(policy, dict):
                permitted = False
            else:
                actor_id = ctx.world.get_or_create_npc_id(npc_name)
                allow_ids = set((policy.get('allow_ids') or []))
                rel_rules = policy.get('allow_rel') or []
                
                if not allow_ids and not rel_rules:
                    permitted = False
                else:
                    permitted = actor_id in allow_ids
                    if not permitted:
                        relationships = getattr(ctx.world, 'relationships', {}) or {}
                        for rule in rel_rules:
                            try:
                                rtype = str(rule.get('type') or '').strip()
                                to_id = rule.get('to')
                            except Exception:
                                rtype = ''
                                to_id = None
                            if rtype and to_id and relationships.get(actor_id, {}).get(to_id) == rtype:
                                if to_id not in getattr(ctx.world, 'users', {}):
                                    continue
                                permitted = True
                                break
    except Exception:
        permitted = False
    
    if not permitted:
        safe_call(ctx.broadcast_to_room, room_id, {
            'type': 'system',
            'content': f"[i]{npc_name} tries the {resolved_label}, but it's locked.[/i]"
        })
        return False, "locked"
    
    # Perform the move
    safe_call(ctx.broadcast_to_room, room_id, {
        'type': 'system',
        'content': f"{npc_name} leaves through the {resolved_label}."
    })
    
    try:
        def _update_npc_presence():
            if room and npc_name in (room.npcs or set()):
                room.npcs.discard(npc_name)
            if target_room_id in ctx.world.rooms:
                ctx.world.rooms[target_room_id].npcs.add(npc_name)
        safe_call(_update_npc_presence)
        safe_call(ctx.broadcast_to_room, target_room_id, {
            'type': 'system',
            'content': f"{npc_name} enters."
        })
        return True, "ok"
    except Exception:
        return False, "error"


def _npc_grumble_failure(npc_name: str, room_id: str, action: dict, reason: str) -> None:
    """Announce why an NPC failed to perform an action."""
    ctx = get_context()
    tool = action.get('tool', 'act')
    
    explanation = f"I cannot {tool} because {reason}!"
    
    if reason == "locked":
        explanation = "This door is locked!"
    elif reason == "room not found":
        explanation = "I don't know where I am going!"
    elif reason == "object not found":
        target = action.get('args', {}).get('object_name', 'it')
        explanation = f"I cannot find the {target}!"
    elif reason == "cannot carry":
        explanation = "I am carrying too much!"
    elif reason == "target not found":
        target = action.get('args', {}).get('target', 'them')
        explanation = f"I cannot find {target}!"
    
    ctx.broadcast_to_room(room_id, {
        'type': 'system',
        'content': f"[i]{npc_name} grumbles loudly: \"{explanation}\"[/i]"
    })


# Note: Additional NPC execution functions (barter, trade, attack, sleep, etc.)
# and the main _npc_execute_action dispatcher remain in server.py for now
# due to their complex dependencies. They can be migrated incrementally.


def _npc_offline_plan(npc_name: str, room: Room, sheet: CharacterSheet) -> list[dict]:
    """Enhanced GOAP: considers personality traits and extended needs.
    Returns a list of actions: [{tool, args}...]
    """
    ctx = get_context()
    plan: list[dict] = []
    
    def find_inv(predicate) -> object | None:
        for it in sheet.inventory.slots:
            if it and predicate(it):
                return it
        return None
    
    # Priority 1: Safety concerns
    safety = getattr(sheet, 'safety', 100.0)
    if safety < 30:
        if hasattr(room, 'doors') and room.doors:
            exit_name = list(room.doors.keys())[0]
            plan.append({'tool': 'move_through', 'args': {'name': exit_name}})
            return plan
    
    # Priority 2: Basic survival needs
    responsibility = getattr(sheet, 'responsibility', 50)
    
    if sheet.hunger < NEED_THRESHOLD:
        inv_food = find_inv(lambda o: _nutrition_from_tags_or_fields(o)[0] > 0)
        if inv_food:
            plan.append({'tool': 'consume_object', 'args': {'object_uuid': getattr(inv_food, 'uuid', '')}})
        else:
            food = next((o for o in (room.objects or {}).values() if _nutrition_from_tags_or_fields(o)[0] > 0), None)
            if food:
                plan.append({'tool': 'get_object', 'args': {'object_name': getattr(food, 'display_name', '')}})
                plan.append({'tool': 'consume_object', 'args': {'object_uuid': getattr(food, 'uuid', '')}})
    
    if sheet.thirst < NEED_THRESHOLD:
        inv_drink = find_inv(lambda o: _nutrition_from_tags_or_fields(o)[1] > 0)
        if inv_drink:
            plan.append({'tool': 'consume_object', 'args': {'object_uuid': getattr(inv_drink, 'uuid', '')}})
        else:
            water = next((o for o in (room.objects or {}).values() if _nutrition_from_tags_or_fields(o)[1] > 0), None)
            if water:
                plan.append({'tool': 'get_object', 'args': {'object_name': getattr(water, 'display_name', '')}})
                plan.append({'tool': 'consume_object', 'args': {'object_uuid': getattr(water, 'uuid', '')}})
    
    # Priority 3: Curiosity-driven exploration
    curiosity = getattr(sheet, 'curiosity', 50)
    confidence = getattr(sheet, 'confidence', 50)
    if curiosity > 60 and confidence > 40 and not plan:
        for obj in (room.objects or {}).values():
            if not hasattr(obj, 'investigated_by_' + npc_name):
                plan.append({'tool': 'look', 'args': {'target': getattr(obj, 'display_name', '')}})
                break
    
    # Priority 4: Social needs
    socialization = safe_call_with_default(lambda: getattr(sheet, 'socialization', 100.0), 100.0)
    if socialization < NEED_THRESHOLD:
        aggression = getattr(sheet, 'aggression', 30)
        if aggression > 60:
            plan.append({'tool': 'emote', 'args': {'message': 'glares around the room assertively.'}})
        else:
            plan.append({'tool': 'emote', 'args': {'message': 'hums a tune to themself.'}})
    
    # Priority 5: Sleep needs
    sleep_val = safe_call_with_default(lambda: getattr(sheet, 'sleep', 100.0), 100.0)
    if sleep_val < NEED_THRESHOLD:
        npc_id = safe_call_with_default(lambda: ctx.world.get_or_create_npc_id(npc_name), "")
        if npc_id:
            _npc_add_sleep_plan_safe(plan, npc_id, room)
    
    # Priority 6: Wealth desire
    wealth_desire = getattr(sheet, 'wealth_desire', 50.0)
    if wealth_desire > 60 and getattr(sheet, 'currency', 0) < 20 and not plan:
        for obj in (room.objects or {}).values():
            obj_value = getattr(obj, 'value', 0)
            if obj_value > 10:
                if responsibility > 60:
                    plan.append({'tool': 'emote', 'args': {'message': f'looks thoughtfully at the {getattr(obj, "display_name", "item")}.'}})
                elif responsibility < 40:
                    plan.append({'tool': 'get_object', 'args': {'object_name': getattr(obj, 'display_name', '')}})
                break
    
    if not plan:
        plan.append({'tool': 'do_nothing', 'args': {}})
    
    return plan


def _npc_add_sleep_plan_safe(plan: list, npc_id: str, room) -> None:
    """Helper function to safely find beds and add sleep plan items."""
    owned_bed = None
    unowned_bed = None
    room_objects = safe_call_with_default(lambda: room.objects or {}, {})
    
    for o in room_objects.values():
        tags = safe_call_with_default(lambda: set(getattr(o, 'object_tags', []) or []), set())
        is_bed = any(safe_call_with_default(lambda: str(t).strip().lower() == 'bed', False) for t in tags)
        if is_bed:
            owner = safe_call_with_default(lambda: getattr(o, 'owner_id', None), None)
            if owner == npc_id and owned_bed is None:
                owned_bed = o
            if (owner is None) and unowned_bed is None:
                unowned_bed = o
    
    if owned_bed is not None:
        bed_uuid = safe_call_with_default(lambda: getattr(owned_bed, 'uuid', ''), '')
        if bed_uuid:
            plan.append({'tool': 'sleep', 'args': {'bed_uuid': bed_uuid}})
    elif unowned_bed is not None:
        bed_uuid = safe_call_with_default(lambda: getattr(unowned_bed, 'uuid', ''), '')
        if bed_uuid:
            plan.append({'tool': 'claim', 'args': {'object_uuid': bed_uuid}})
            plan.append({'tool': 'sleep', 'args': {'bed_uuid': bed_uuid}})


# Exported functions that server.py will use
__all__ = [
    'GameLoopContext',
    'init_game_loop',
    'get_context',
    '_clamp_need',
    '_parse_tag_value',
    '_nutrition_from_tags_or_fields',
    '_npc_find_room_for',
    '_ensure_npc_sheet',
    '_npc_gain_socialization',
    '_find_inventory_slot',
    '_npc_exec_get_object',
    '_npc_exec_consume_object',
    '_npc_exec_do_nothing',
    '_npc_exec_emote',
    '_npc_exec_say',
    '_npc_exec_drop',
    '_npc_exec_look',
    '_npc_exec_move_through',
    '_npc_grumble_failure',
    '_npc_offline_plan',
    '_npc_add_sleep_plan_safe',
    'TICK_SECONDS',
    'AP_MAX',
    'NEED_DROP_PER_TICK',
    'NEED_THRESHOLD',
    'SOCIAL_DROP_PER_TICK',
    'SOCIAL_REFILL_ON_CHAT',
    'SOCIAL_SIM_REFILL_TICK',
    'SOCIAL_REFILL_EMOTE',
    'SLEEP_DROP_PER_TICK',
    'SLEEP_REFILL_PER_TICK',
    'SLEEP_TICKS_DEFAULT',
]
