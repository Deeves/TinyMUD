from __future__ import annotations
"""Trade & barter command router.

This module extracts /barter and /trade plus their interactive flows from the
monolithic server.py. Text, ordering, and side‑effects are preserved so tests
remain stable. The router exposes two entrypoints:

  try_handle(...)      -> handles the initial /barter or /trade slash command
  try_handle_flow(...) -> advances an in‑progress barter/trade conversation

Both functions return True if they consumed the input.
"""
from typing import cast
import re
import os  # added for debug instrumentation (MUD_DEBUG_TRADE)
from command_context import CommandContext, EmitFn
from world import CharacterSheet, World
from concurrency_utils import atomic_many, atomic

# We reuse inventory + swap/purchase helpers that remain in server.py to avoid
# duplicating logic. Import lazily inside functions to minimize circular risk.


def _barter_begin(
    ctx: CommandContext,
    world: World,
    sid: str,
    *,
    target_kind: str,
    target_display: str,
    room_id: str,
    target_sid: str | None = None,
    target_name: str | None = None
):
    with atomic_many(['barter_sessions', 'trade_sessions']):
        ctx.barter_sessions.pop(sid, None)
        ctx.trade_sessions.pop(sid, None)
        session = {
            'step': 'choose_desired',
            'target_kind': target_kind,
            'target_sid': target_sid,
            'target_name': target_name,
            'target_display': target_display,
            'room_id': room_id,
        }
        ctx.barter_sessions[sid] = session
    emits = [
        {
            'type': 'system',
            'content': f"Beginning barter with {target_display}. Type 'cancel' to abort.",
        },
        {
            'type': 'system',
            'content': f"What item do you want from {target_display}'s inventory?",
        },
    ]
    return True, None, emits


def _barter_handle(ctx: CommandContext, world: World, sid: str, text: str):
    sessions_map = ctx.barter_sessions
    session = sessions_map.get(sid)
    if not session:
        return False, [], [], [], False
    emits: list[dict] = []
    broadcasts: list[tuple[str, dict]] = []
    directs: list[tuple[str, dict]] = []
    mutated = False
    raw = (text or '').strip(); lower = raw.lower()
    if lower in ('cancel', '/cancel'):
        with atomic('barter_sessions'):
            sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Barter cancelled.'})
        return True, emits, broadcasts, directs, False
    player = world.players.get(sid)
    room_id = session.get('room_id'); room = world.rooms.get(room_id) if room_id else None
    if not player or not room_id or not room or player.room_id != room_id:
        sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Barter cancelled because you are no longer in the same room.'})
        return True, emits, broadcasts, directs, False
    target_kind = session.get('target_kind'); target_display = session.get('target_display', 'your trade partner')
    target_inv = None; target_sid = session.get('target_sid')
    if target_kind == 'player':
        target_player = world.players.get(target_sid) if target_sid else None
        if not target_player or target_player.room_id != room_id:
            sessions_map.pop(sid, None)
            emits.append({'type': 'system', 'content': f"{target_display} is no longer here. Barter cancelled."})
            return True, emits, broadcasts, directs, False
        target_inv = target_player.sheet.inventory
    elif target_kind == 'npc':
        target_npc = session.get('target_name')
        if not target_npc or target_npc not in (room.npcs or set()):
            sessions_map.pop(sid, None)
            emits.append({'type': 'system', 'content': f"{target_display} is no longer here. Barter cancelled."})
            return True, emits, broadcasts, directs, False
        from server import _ensure_npc_sheet  # late import
        target_inv = _ensure_npc_sheet(target_npc).inventory
    if target_inv is None:
        sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Barter cancelled (target inventory unavailable).'})
        return True, emits, broadcasts, directs, False
    actor_inv = player.sheet.inventory
    step = session.get('step', 'choose_desired')
    from server import _find_inventory_item_by_name, _barter_swap, _strip_quotes as strip_quotes
    if step == 'choose_desired':
        query = strip_quotes(raw)
        if not query:
            emits.append({'type': 'system', 'content': f"Please name the item you want from {target_display}."})
            return True, emits, broadcasts, directs, False
        obj, _idx, suggestions = _find_inventory_item_by_name(target_inv, query)
        if obj is None:
            emits.append({'type': 'system', 'content': ("Be more specific. Matching items: " + ", ".join(suggestions)) if suggestions else f"{target_display} doesn't appear to have that item."})
            return True, emits, broadcasts, directs, False
        session['desired_uuid'] = str(getattr(obj, 'uuid', '') or '')
        session['desired_name'] = getattr(obj, 'display_name', 'the item')
        session['step'] = 'choose_offer'
        with atomic('barter_sessions'):
            sessions_map[sid] = session
        emits.append({'type': 'system', 'content': f"You set your sights on {session['desired_name']}."})
        emits.append({'type': 'system', 'content': 'What item from your inventory will you offer in exchange?'})
        return True, emits, broadcasts, directs, False
    if step == 'choose_offer':
        desired_uuid = session.get('desired_uuid'); desired_name = session.get('desired_name', 'the item')
        if not desired_uuid:
            session['step'] = 'choose_desired'; sessions_map[sid] = session
            emits.append({'type': 'system', 'content': f"{target_display}'s inventory changed. Please choose again."})
            return True, emits, broadcasts, directs, False
        query = strip_quotes(raw)
        if not query:
            emits.append({'type': 'system', 'content': 'Name the item from your inventory you will offer.'})
            return True, emits, broadcasts, directs, False
        obj, _idx, suggestions = _find_inventory_item_by_name(actor_inv, query)
        if obj is None:
            emits.append({'type': 'system', 'content': ("Be more specific. Matching items: " + ", ".join(suggestions)) if suggestions else "You don't appear to have that item."})
            return True, emits, broadcasts, directs, False
        offer_uuid = str(getattr(obj, 'uuid', '') or '')
        offer_name = getattr(obj, 'display_name', 'item')
        if not offer_uuid:
            emits.append({'type': 'system', 'content': "That item can't be traded right now."})
            return True, emits, broadcasts, directs, False
        ok, result = _barter_swap(actor_inv, target_inv, offer_uuid, desired_uuid)
        if not ok:
            msg = cast(str, result)
            emits.append({'type': 'error', 'content': msg})
            lower_msg = msg.lower()
            if 'no longer available' in lower_msg or 'inventory changed' in lower_msg:
                session['step'] = 'choose_desired'; sessions_map[sid] = session
                emits.append({'type': 'system', 'content': f"It looks like {target_display}'s inventory changed. Which item do you want now?"})
            else:
                emits.append({'type': 'system', 'content': f"What item will you offer in exchange for {desired_name}?"})
            return True, emits, broadcasts, directs, False
        sessions_map.pop(sid, None)
        actor_name = player.sheet.display_name
        emits.append({'type': 'system', 'content': f"You trade your {offer_name} to {target_display} for their {desired_name}."})
        broadcasts.append((room_id, {'type': 'system','content': f"[i]{actor_name} trades their {offer_name} with {target_display}, receiving {desired_name}.[/i]"}))
        if target_kind == 'player' and target_sid:
            directs.append((target_sid, {'type': 'system','content': f"{actor_name} trades their {offer_name} for your {desired_name}."}))
        mutated = True
        return True, emits, broadcasts, directs, mutated
    sessions_map.pop(sid, None)
    emits.append({'type': 'system', 'content': 'Unexpected barter state. Cancelling.'})
    return True, emits, broadcasts, directs, False


def _trade_begin(ctx: CommandContext, world: World, sid: str, *, target_kind: str, target_display: str, room_id: str, target_sid: str | None = None, target_name: str | None = None):
    ctx.trade_sessions.pop(sid, None)
    ctx.barter_sessions.pop(sid, None)
    session = {
        'step': 'choose_desired',
        'target_kind': target_kind,
        'target_sid': target_sid,
        'target_name': target_name,
        'target_display': target_display,
        'room_id': room_id,
    }
    ctx.trade_sessions[sid] = session
    emits = [
        {'type': 'system', 'content': f"Beginning trade with {target_display}. Type 'cancel' to abort."},
        {'type': 'system', 'content': f"What item do you want from {target_display}'s inventory?"},
    ]
    return True, None, emits


def _trade_handle(ctx: CommandContext, world: World, sid: str, text: str):
    sessions_map = ctx.trade_sessions
    session = sessions_map.get(sid)
    if not session:
        return False, [], [], [], False
    emits: list[dict] = []; broadcasts: list[tuple[str, dict]] = []; directs: list[tuple[str, dict]] = []
    mutated = False
    raw = (text or '').strip(); lower = raw.lower()
    if lower in ('cancel', '/cancel'):
        sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Trade cancelled.'})
        return True, emits, broadcasts, directs, False
    player = world.players.get(sid)
    room_id = session.get('room_id'); room = world.rooms.get(room_id) if room_id else None
    if not player or not room_id or not room or player.room_id != room_id:
        sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Trade cancelled because you are no longer in the same room.'})
        return True, emits, broadcasts, directs, False
    target_kind = session.get('target_kind'); target_display = session.get('target_display', 'your trade partner')
    target_sheet: CharacterSheet | None = None
    target_sid = session.get('target_sid')
    if target_kind == 'player':
        target_player = world.players.get(target_sid) if target_sid else None
        if not target_player or target_player.room_id != room_id:
            sessions_map.pop(sid, None)
            emits.append({'type': 'system', 'content': f"{target_display} is no longer here. Trade cancelled."})
            return True, emits, broadcasts, directs, False
        target_sheet = target_player.sheet
    elif target_kind == 'npc':
        target_npc = session.get('target_name')
        if not target_npc or target_npc not in (room.npcs or set()):
            sessions_map.pop(sid, None)
            emits.append({'type': 'system', 'content': f"{target_display} is no longer here. Trade cancelled."})
            return True, emits, broadcasts, directs, False
        from server import _ensure_npc_sheet
        target_sheet = _ensure_npc_sheet(target_npc)
    if target_sheet is None:
        sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Trade cancelled (target unavailable).'})
        return True, emits, broadcasts, directs, False
    step = session.get('step', 'choose_desired')
    from server import _find_inventory_item_by_name, _trade_purchase, _strip_quotes as strip_quotes
    if step == 'choose_desired':
        query = strip_quotes(raw)
        if os.getenv('MUD_DEBUG_TRADE') == '1':  # debug instrumentation
            try:
                from server import _inventory_slots  # late import
                inv_objs = _inventory_slots(target_sheet.inventory)
                inv_names = [getattr(o, 'display_name', None) for o in inv_objs if o]
                print(f"[DEBUG_TRADE] choose_desired sid={sid} query='{query}' inv_names={inv_names}")
            except Exception as e:
                print(f"[DEBUG_TRADE] instrumentation error: {e}")
        if not query:
            emits.append({'type': 'system', 'content': f"Please name the item you want from {target_display}."})
            return True, emits, broadcasts, directs, False
        obj, _idx, suggestions = _find_inventory_item_by_name(target_sheet.inventory, query)
        if obj is None:
            if os.getenv('MUD_DEBUG_TRADE') == '1':
                try:
                    print(f"[DEBUG_TRADE] no match for query='{query}' suggestions={suggestions}")
                except Exception:
                    pass
            emits.append({'type': 'system', 'content': ("Be more specific. Matching items: " + ", ".join(suggestions)) if suggestions else f"{target_display} doesn't appear to have that item."})
            return True, emits, broadcasts, directs, False
        session['desired_uuid'] = str(getattr(obj, 'uuid', '') or '')
        session['desired_name'] = getattr(obj, 'display_name', 'the item')
        session['step'] = 'enter_price'; sessions_map[sid] = session
        if os.getenv('MUD_DEBUG_TRADE') == '1':
            print(f"[DEBUG_TRADE] transition -> enter_price desired_name={session['desired_name']} uuid={session['desired_uuid']}")
        emits.append({'type': 'system', 'content': f"You set your sights on {session['desired_name']}."})
        emits.append({'type': 'system', 'content': f"How many coins will you offer for {session['desired_name']}?"})
        return True, emits, broadcasts, directs, False
    if step == 'enter_price':
        desired_uuid = session.get('desired_uuid'); desired_name = session.get('desired_name', 'the item')
        if not desired_uuid:
            session['step'] = 'choose_desired'; sessions_map[sid] = session
            emits.append({'type': 'system', 'content': f"{target_display}'s inventory changed. Please choose again."})
            return True, emits, broadcasts, directs, False
        match = re.search(r"-?\d+", raw)
        if not match:
            emits.append({'type': 'system', 'content': 'Please enter a whole number of coins.'})
            return True, emits, broadcasts, directs, False
        try: price_val = int(match.group())
        except Exception: price_val = 0
        if price_val <= 0:
            emits.append({'type': 'system', 'content': 'Offer must be at least 1 coin.'})
            return True, emits, broadcasts, directs, False
        actor_coins = int(getattr(player.sheet, 'currency', 0) or 0)
        if actor_coins < price_val:
            emits.append({'type': 'system', 'content': f"You only have {actor_coins} coin{'s' if actor_coins != 1 else ''}."})
            return True, emits, broadcasts, directs, False
        ok, result = _trade_purchase(player.sheet, target_sheet, target_sheet.inventory, desired_uuid, price_val)
        if not ok:
            msg = cast(str, result)
            emits.append({'type': 'error', 'content': msg})
            lower_msg = msg.lower()
            if 'no longer' in lower_msg or 'inventory' in lower_msg:
                session['step'] = 'choose_desired'; sessions_map[sid] = session
                emits.append({'type': 'system', 'content': f"It looks like {target_display}'s inventory changed. Which item do you want now?"})
            else:
                emits.append({'type': 'system', 'content': f"How many coins will you offer for {desired_name}?"})
            return True, emits, broadcasts, directs, False
        payload = cast(dict[str, object], result)
        bought_obj = payload.get('item'); price_raw = payload.get('price', price_val)
        final_price = price_val
        if isinstance(price_raw, (int, float, str)):
            try: final_price = int(price_raw)
            except Exception: final_price = price_val
        item_name = str(getattr(bought_obj, 'display_name', 'item'))
        actor_name = player.sheet.display_name
        sessions_map.pop(sid, None)
        emits.append({'type': 'system', 'content': f"You pay {final_price} coin{'s' if final_price != 1 else ''} to {target_display} for {item_name}."})
        broadcasts.append((room_id, {'type': 'system', 'content': f"[i]{actor_name} pays {final_price} coin{'s' if final_price != 1 else ''} to {target_display}, receiving {item_name}.[/i]"}))
        if target_kind == 'player' and target_sid:
            directs.append((target_sid, {'type': 'system', 'content': f"{actor_name} pays you {final_price} coin{'s' if final_price != 1 else ''} for your {item_name}."}))
        mutated = True
        return True, emits, broadcasts, directs, mutated
    sessions_map.pop(sid, None)
    emits.append({'type': 'system', 'content': 'Unexpected trade state. Cancelling.'})
    return True, emits, broadcasts, directs, False


def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    if cmd not in ('barter', 'trade'):
        return False
    MESSAGE_OUT = ctx.message_out
    world = ctx.world
    if sid is None:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
        return True
    if sid not in world.players:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first with /auth.'})
        return True
    if not args:
        usage = 'Usage: /barter <Player or NPC>' if cmd == 'barter' else 'Usage: /trade <Player or NPC>'
        emit(MESSAGE_OUT, {'type': 'error', 'content': usage})
        return True
    player = world.players.get(sid)
    if not player:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Player not found.'})
        return True
    room = world.rooms.get(player.room_id)
    if not room:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'You are nowhere.'})
        return True
    target_query = ctx.strip_quotes(" ".join(args).strip())
    if not target_query:
        usage = 'Usage: /barter <Player or NPC>' if cmd == 'barter' else 'Usage: /trade <Player or NPC>'
        emit(MESSAGE_OUT, {'type': 'error', 'content': usage})
        return True
    from server import _resolve_player_in_room, _resolve_npcs_in_room, _ensure_npc_sheet, _inventory_has_items
    psid, pname = _resolve_player_in_room(world, room, target_query)
    target_kind = None; target_sid = None; target_name = None; target_display = None; target_sheet: CharacterSheet | None = None; target_inv = None
    if psid and pname:
        if psid == sid:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'You cannot barter with yourself.' if cmd == 'barter' else 'You cannot trade coins with yourself.'})
            return True
        target_player = world.players.get(psid)
        if not target_player:
            emit(MESSAGE_OUT, {'type': 'error', 'content': f"{pname} is not available."})
            return True
        target_kind = 'player'; target_sid = psid; target_display = target_player.sheet.display_name
        target_inv = target_player.sheet.inventory; target_sheet = target_player.sheet
    else:
        npcs = _resolve_npcs_in_room(room, [target_query])
        if npcs:
            target_name = npcs[0]
            target_sheet = _ensure_npc_sheet(target_name)
            target_kind = 'npc'; target_display = target_sheet.display_name
            target_inv = target_sheet.inventory
    if target_kind is None or (cmd == 'barter' and target_inv is None) or (cmd == 'trade' and target_sheet is None):
        emit(MESSAGE_OUT, {'type': 'system', 'content': f"You don't see '{target_query}' here."})
        return True
    if cmd == 'barter':
        if not _inventory_has_items(target_inv):
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"{target_display} has nothing to trade right now."})
            return True
        if not _inventory_has_items(player.sheet.inventory):
            emit(MESSAGE_OUT, {'type': 'system', 'content': 'You have nothing to offer in trade.'})
            return True
        ok, err, start_emits = _barter_begin(ctx, world, sid, target_kind=target_kind, target_display=target_display or target_query, room_id=player.room_id, target_sid=target_sid, target_name=target_name)
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Unable to start barter.'})
            return True
        for p in start_emits: emit(MESSAGE_OUT, p)
        return True
    else:
        if int(getattr(player.sheet, 'currency', 0) or 0) <= 0:
            emit(MESSAGE_OUT, {'type': 'system', 'content': 'You do not have any coins to trade.'})
            return True
        # target_sheet is guaranteed for trade path; enforce not None for type checkers
        if target_sheet is None or not _inventory_has_items(target_sheet.inventory):
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"{target_display} has nothing to trade right now."})
            return True
        ok, err, start_emits = _trade_begin(ctx, world, sid, target_kind=target_kind, target_display=str(target_display), room_id=player.room_id, target_sid=target_sid, target_name=target_name)
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Unable to start trade.'})
            return True
        for p in start_emits: emit(MESSAGE_OUT, p)
        return True


def try_handle_flow(ctx: CommandContext, sid: str | None, text: str, emit: EmitFn) -> bool:
    if sid is None:
        return False
    world = ctx.world; MESSAGE_OUT = ctx.message_out
    progressed = False
    if sid in ctx.barter_sessions:
        handled, emits, broadcasts, directs, mutated = _barter_handle(ctx, world, sid, text)
        if handled:
            progressed = True
            for p in emits: emit(MESSAGE_OUT, p)
            for room_id, payload in broadcasts: ctx.broadcast_to_room(room_id, payload, sid)
            for to_sid, payload in directs: ctx.socketio.emit(MESSAGE_OUT, payload, to=to_sid)
            if mutated: ctx.mark_world_dirty()
    if sid in ctx.trade_sessions:
        handled, emits, broadcasts, directs, mutated = _trade_handle(ctx, world, sid, text)
        if handled:
            progressed = True
            for p in emits: emit(MESSAGE_OUT, p)
            for room_id, payload in broadcasts: ctx.broadcast_to_room(room_id, payload, sid)
            for to_sid, payload in directs: ctx.socketio.emit(MESSAGE_OUT, payload, to=to_sid)
            if mutated: ctx.mark_world_dirty()
    return progressed
