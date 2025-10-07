from __future__ import annotations

from world import World, Room, Object, CharacterSheet, Player
import uuid as _uuid
import server as srv  # Central conftest fixture will reload & patch this each test


def _reset_world() -> World:
    # Reinitialize mutable global world + session dicts for isolation
    srv.world = World()  # type: ignore[attr-defined]
    srv.barter_sessions.clear()  # type: ignore[attr-defined]
    srv.trade_sessions.clear()  # type: ignore[attr-defined]
    # Provide a fresh interaction session mapping if missing
    if not hasattr(srv, 'interaction_sessions'):
        setattr(srv, 'interaction_sessions', {})  # type: ignore[attr-defined]
    else:
        try:
            srv.interaction_sessions.clear()  # type: ignore[attr-defined]
        except Exception:
            pass
    return srv.world  # type: ignore[union-attr]


def test_trade_flow_player_buys_from_npc():
    world = _reset_world()
    room = Room(id="market", description="A busy marketplace.")
    world.rooms[room.id] = room

    buyer_sheet = CharacterSheet(display_name="Buyer")
    buyer_sheet.currency = 50
    buyer = Player(sid="sid-buyer", room_id=room.id, sheet=buyer_sheet)
    world.players[buyer.sid] = buyer
    room.players.add(buyer.sid)

    npc_name = "Vendor"
    npc_sheet = CharacterSheet(display_name=npc_name)
    npc_sheet.currency = 0
    item = Object(display_name="Shiny Ring")
    if not getattr(item, 'uuid', None):  # ensure uuid present for trade lookup
        item.uuid = str(_uuid.uuid4())  # type: ignore[attr-defined]
    slot = srv._find_inventory_slot(npc_sheet.inventory, item)
    assert slot is not None
    npc_sheet.inventory.place(slot, item)
    world.npc_sheets[npc_name] = npc_sheet
    world.npc_ids[npc_name] = str(__import__('uuid').uuid4())  # Ensure NPC has ID mapping
    room.npcs.add(npc_name)

    ok, err, _ = srv._trade_begin(
        world,
        buyer.sid,
        target_kind='npc',
        target_display=npc_sheet.display_name,
        room_id=room.id,
        target_name=npc_name,
    )
    assert ok and err is None

    handled, emits, _, _, mutated = srv._trade_handle(world, buyer.sid, "Shiny Ring", srv.trade_sessions)
    assert handled and not mutated
    # Accept either prompt progression or retry text depending on router matching rules
    if not any('coin' in p['content'] for p in emits):
        # Should not report target lacks item unless test data misconfigured
        assert not any("doesn't appear to have" in p['content'] for p in emits), f"Unexpected missing item message: {[p['content'] for p in emits]}"

    handled, _, _, _, mutated = srv._trade_handle(world, buyer.sid, "15", srv.trade_sessions)
    assert handled and mutated

    assert buyer_sheet.currency == 35
    assert npc_sheet.currency == 15
    assert any(obj and obj.display_name == "Shiny Ring" for obj in srv._inventory_slots(buyer_sheet.inventory))
    assert not any(obj and obj.display_name == "Shiny Ring" for obj in srv._inventory_slots(npc_sheet.inventory))
    
    # Validate world integrity after trade mutations
    validation_errors = world.validate()
    assert validation_errors == [], f"World validation failed after trade: {validation_errors}"


def test_trade_requires_sufficient_funds():
    world = _reset_world()
    room = Room(id="bazaar", description="")
    world.rooms[room.id] = room

    buyer_sheet = CharacterSheet(display_name="Buyer")
    buyer_sheet.currency = 5
    buyer = Player(sid="sid-low", room_id=room.id, sheet=buyer_sheet)
    world.players[buyer.sid] = buyer
    room.players.add(buyer.sid)

    npc_name = "Vendor"
    npc_sheet = CharacterSheet(display_name=npc_name)
    item = Object(display_name="Lantern")
    if not getattr(item, 'uuid', None):
        item.uuid = str(_uuid.uuid4())  # type: ignore[attr-defined]
    slot = srv._find_inventory_slot(npc_sheet.inventory, item)
    assert slot is not None
    npc_sheet.inventory.place(slot, item)
    world.npc_sheets[npc_name] = npc_sheet
    world.npc_ids[npc_name] = str(__import__('uuid').uuid4())  # Ensure NPC has ID mapping
    room.npcs.add(npc_name)

    ok, err, _ = srv._trade_begin(
        world,
        buyer.sid,
        target_kind='npc',
        target_display=npc_sheet.display_name,
        room_id=room.id,
        target_name=npc_name,
    )
    assert ok and err is None

    handled, emits, _, _, mutated = srv._trade_handle(world, buyer.sid, "Lantern", srv.trade_sessions)
    assert handled and not mutated
    if not any('coin' in p['content'] for p in emits):
        assert not any("doesn't appear to have" in p['content'] for p in emits), f"Unexpected missing item message: {[p['content'] for p in emits]}"

    handled, emits, _, _, mutated = srv._trade_handle(world, buyer.sid, "10", srv.trade_sessions)
    assert handled and not mutated
    # Should still be waiting for price input; some flows may re-ask for desired item
    assert srv.trade_sessions[buyer.sid]['step'] in ('enter_price', 'choose_desired')
    assert any('coin' in payload['content'] for payload in emits)
    assert buyer_sheet.currency == 5
    assert any(obj and obj.display_name == "Lantern" for obj in srv._inventory_slots(npc_sheet.inventory))


def test_npc_trade_action_moves_item_and_currency():
    world = _reset_world()
    room = Room(id="square", description="")
    world.rooms[room.id] = room

    npc_name = "Merchant"
    npc_sheet = CharacterSheet(display_name=npc_name)
    npc_sheet.currency = 40
    world.npc_sheets[npc_name] = npc_sheet
    world.npc_ids[npc_name] = str(__import__('uuid').uuid4())  # Ensure NPC has ID mapping
    room.npcs.add(npc_name)

    player_sheet = CharacterSheet(display_name="Traveler")
    player_sheet.currency = 0
    item = Object(display_name="Map")
    if not getattr(item, 'uuid', None):
        item.uuid = str(_uuid.uuid4())  # type: ignore[attr-defined]
    slot = srv._find_inventory_slot(player_sheet.inventory, item)
    assert slot is not None
    player_sheet.inventory.place(slot, item)
    player = Player(sid="sid-player", room_id=room.id, sheet=player_sheet)
    world.players[player.sid] = player
    room.players.add(player.sid)

    # Execute trade tool
    item_uuid = next(obj.uuid for obj in srv._inventory_slots(player_sheet.inventory) if obj)
    srv._npc_execute_action(npc_name, room.id, {
        'tool': 'trade',
        'args': {
            'target_name': player_sheet.display_name,
            'object_uuid': item_uuid,
            'price': 20,
        }
    })

    assert npc_sheet.currency == 20
    assert player_sheet.currency == 20
    assert any(obj and obj.display_name == "Map" for obj in srv._inventory_slots(npc_sheet.inventory))
    assert not any(obj and obj.display_name == "Map" for obj in srv._inventory_slots(player_sheet.inventory))
    
    # Validate world integrity after NPC trade action
    validation_errors = world.validate()
    assert validation_errors == [], f"World validation failed after NPC trade: {validation_errors}"