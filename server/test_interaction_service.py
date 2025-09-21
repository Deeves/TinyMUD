from __future__ import annotations

import pytest

from world import World, Room, Object, CharacterSheet
import interaction_service as isvc
from interaction_service import begin_interaction, handle_interaction_input


def _setup_world_with_player_and_room():
    w = World()
    r = Room(id="start", description="A plain room.")
    w.rooms[r.id] = r
    w.start_room_id = r.id
    sid = "sid-123"
    sheet = CharacterSheet(display_name="Tester")
    w.add_player(sid, sheet.display_name, r.id, sheet)
    return w, sid, r


def test_begin_interaction_lists_actions_for_travel_point():
    w, sid, room = _setup_world_with_player_and_room()
    # Add a door-like object
    door = Object(display_name="Oak Door", description="A sturdy door.", object_tags={"Immovable", "Travel Point"})
    room.objects[door.uuid] = door
    sessions = {}

    ok, err, emits = begin_interaction(w, sid, room, "oak", sessions)
    assert ok and err is None
    assert emits and isinstance(emits[0], dict)
    text = emits[0]['content']
    assert "Interactions for Oak Door" in text
    assert "Move Through" in text
    assert "Step Away" in text
    assert "What do you wish to do?" in text
    # Session should be created
    assert sid in sessions


def test_cancel_interaction_via_number():
    w, sid, room = _setup_world_with_player_and_room()
    obj = Object(display_name="Oak Door", object_tags={"Immovable", "Travel Point"})
    room.objects[obj.uuid] = obj
    sessions = {}

    ok, err, emits = begin_interaction(w, sid, room, "oak", sessions)
    assert ok and err is None and sid in sessions
    # Actions order for travel point: ["Move Through", "Step Away"] => 2 cancels
    handled, emits2, _b = handle_interaction_input(w, sid, "2", sessions)
    assert handled
    assert any("step away" in e.get('content', '').lower() for e in emits2)
    assert sid not in sessions


def test_actions_for_carryable_weapon():
    w, sid, room = _setup_world_with_player_and_room()
    obj = Object(display_name="Bronze Sword", object_tags={"one-hand", "weapon"})
    room.objects[obj.uuid] = obj
    sessions = {}

    ok, err, emits = begin_interaction(w, sid, room, "sword", sessions)
    assert ok and err is None
    text = emits[0]['content']
    # Should list both Pick Up and Wield (order not essential)
    assert "Pick Up" in text
    assert "Wield" in text
    assert "Step Away" in text


def test_pickup_stow_one_hand_adds_stowed():
    w, sid, room = _setup_world_with_player_and_room()
    obj = Object(display_name="Dagger", object_tags={"one-hand"})
    room.objects[obj.uuid] = obj
    sessions = {}

    ok, err, emits = begin_interaction(w, sid, room, "dagger", sessions)
    assert ok and err is None and sid in sessions
    handled, emits2, _b = handle_interaction_input(w, sid, "pick up", sessions)
    assert handled
    # Expect placed in a small slot with 'stowed'
    inv = w.players[sid].sheet.inventory
    found = None
    for i in range(2, 6):
        if inv.slots[i] is obj:
            found = i
            break
    assert found is not None
    assert 'stowed' in (obj.object_tags or set())
    assert obj.uuid not in room.objects


def test_pickup_fallback_to_hands_when_no_small_slots():
    w, sid, room = _setup_world_with_player_and_room()
    # Fill small slots
    inv = w.players[sid].sheet.inventory
    for i in range(2, 6):
        inv.slots[i] = Object(display_name=f"Pebble{i}", object_tags={"one-hand"})
    # Hands empty
    obj = Object(display_name="Shortsword", object_tags={"one-hand", "weapon"})
    room.objects[obj.uuid] = obj
    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "shortsword", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "pick up", sessions)
    assert handled
    # Should be in right hand (1), and not stowed
    assert inv.slots[1] is obj
    assert 'stowed' not in (obj.object_tags or set())


def test_pickup_no_space():
    w, sid, room = _setup_world_with_player_and_room()
    inv = w.players[sid].sheet.inventory
    # Fill hands and small slots
    inv.slots[0] = Object(display_name="RockL", object_tags={"one-hand"})
    inv.slots[1] = Object(display_name="RockR", object_tags={"one-hand"})
    for i in range(2, 6):
        inv.slots[i] = Object(display_name=f"Pebble{i}", object_tags={"one-hand"})
    obj = Object(display_name="Apple", object_tags={"one-hand", "Edible"})
    room.objects[obj.uuid] = obj
    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "apple", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "pick up", sessions)
    assert handled
    # Expect an error and object still in room
    assert any(e.get('type') == 'error' for e in emits2)
    assert obj.uuid in room.objects


def test_wield_from_room_moves_to_hand():
    w, sid, room = _setup_world_with_player_and_room()
    obj = Object(display_name="Bronze Sword", object_tags={"one-hand", "weapon"})
    room.objects[obj.uuid] = obj
    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "bronze", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "wield", sessions)
    assert handled
    inv = w.players[sid].sheet.inventory
    assert inv.slots[1] is obj or inv.slots[0] is obj
    assert obj.uuid not in room.objects


def test_wield_from_stowed_moves_to_hand_and_removes_stowed():
    w, sid, room = _setup_world_with_player_and_room()
    inv = w.players[sid].sheet.inventory
    obj = Object(display_name="Club", object_tags={"one-hand", "weapon", "stowed"})
    inv.slots[2] = obj
    sessions = {sid: {"step": "choose", "obj_uuid": obj.uuid, "obj_name": obj.display_name, "actions": ["Wield", "Step Away"]}}
    handled, emits2, _b = handle_interaction_input(w, sid, "wield", sessions)
    assert handled
    assert (inv.slots[1] is obj) or (inv.slots[0] is obj)
    assert 'stowed' not in (obj.object_tags or set())
    assert inv.slots[2] is None


def test_wield_when_already_in_hand():
    w, sid, room = _setup_world_with_player_and_room()
    inv = w.players[sid].sheet.inventory
    obj = Object(display_name="Knife", object_tags={"one-hand", "weapon"})
    inv.slots[0] = obj
    sessions = {sid: {"step": "choose", "obj_uuid": obj.uuid, "obj_name": obj.display_name, "actions": ["Wield", "Step Away"]}}
    handled, emits2, _b = handle_interaction_input(w, sid, "wield", sessions)
    assert handled
    assert any("already holding" in e.get('content', '').lower() for e in emits2)


def test_eat_spawns_outputs():
    w, sid, room = _setup_world_with_player_and_room()
    core = Object(display_name="Core")
    food = Object(display_name="Apple", object_tags={"one-hand", "Edible"}, deconstruct_recipe=[core])
    room.objects[food.uuid] = food
    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "apple", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "eat", sessions)
    assert handled
    assert food.uuid not in room.objects
    # Core spawned
    names = [o.display_name for o in room.objects.values()]
    assert "Core" in names


def test_drink_spawns_outputs():
    w, sid, room = _setup_world_with_player_and_room()
    empty = Object(display_name="Empty Bottle")
    drink = Object(display_name="Potion", object_tags={"one-hand", "Drinkable"}, deconstruct_recipe=[empty])
    room.objects[drink.uuid] = drink
    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "potion", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "drink", sessions)
    assert handled
    assert drink.uuid not in room.objects
    names = [o.display_name for o in room.objects.values()]
    assert "Empty Bottle" in names


def test_container_open_requires_search():
    w, sid, room = _setup_world_with_player_and_room()
    chest = Object(display_name="Old Chest", object_tags={"Container", "Immovable"})
    room.objects[chest.uuid] = chest
    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "chest", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "open", sessions)
    assert handled
    assert any("search" in e.get('content', '').lower() for e in emits2)


def test_container_search_spawns_loot_once_and_open_lists_contents(monkeypatch):
    w, sid, room = _setup_world_with_player_and_room()
    chest = Object(display_name="Old Chest", object_tags={"Container", "Immovable"})
    room.objects[chest.uuid] = chest
    # Add a template that hints it spawns in this container
    loot = Object(display_name="Gold Coin")
    loot.loot_location_hint = Object(display_name="Old Chest")
    w.object_templates["coin"] = loot
    # Force dice to succeed (<= 20)
    class _R:
        def __init__(self, total): self.total = total
    monkeypatch.setattr(isvc, 'dice_roll', lambda expr: _R(1))

    sessions = {}
    ok, err, _ = begin_interaction(w, sid, room, "chest", sessions)
    assert ok
    handled, emits2, _b = handle_interaction_input(w, sid, "search", sessions)
    assert handled
    assert chest.container_searched is True
    # Should have spawned in a small slot if available
    small_has = any(bool(o) and o.display_name == "Gold Coin" for o in chest.container_small_slots)
    large_has = any(bool(o) and o.display_name == "Gold Coin" for o in chest.container_large_slots)
    assert small_has or large_has
    # Now open and verify list shows contents
    ok2, err2, _ = begin_interaction(w, sid, room, "chest", {})
    assert ok2
    handled2, emits3, _b2 = handle_interaction_input(w, sid, "open", {sid: {"step": "choose", "obj_uuid": chest.uuid, "obj_name": chest.display_name, "actions": ["Open", "Step Away"]}})
    assert handled2
    combined = "\n".join(e.get('content', '') for e in emits3)
    assert "Inside:" in combined or "It's empty" not in combined


def test_container_second_search_is_blocked(monkeypatch):
    w, sid, room = _setup_world_with_player_and_room()
    chest = Object(display_name="Old Chest", object_tags={"Container", "Immovable"})
    room.objects[chest.uuid] = chest
    loot = Object(display_name="Gold Coin")
    loot.loot_location_hint = Object(display_name="Old Chest")
    w.object_templates["coin"] = loot
    class _R:  # always succeed the first time
        def __init__(self, total): self.total = total
    monkeypatch.setattr(isvc, 'dice_roll', lambda expr: _R(1))
    # First search spawns loot
    ok, err, _ = begin_interaction(w, sid, room, "chest", {})
    assert ok
    handled, emits1, _b = handle_interaction_input(w, sid, "search", {sid: {"step": "choose", "obj_uuid": chest.uuid, "obj_name": chest.display_name, "actions": ["Search", "Step Away"]}})
    assert handled
    count_after_first = sum(1 for o in list(chest.container_small_slots) + list(chest.container_large_slots) if o)
    assert count_after_first >= 1
    # Second search should not spawn more and should say already searched
    ok2, err2, _ = begin_interaction(w, sid, room, "chest", {})
    assert ok2
    handled2, emits2, _b2 = handle_interaction_input(w, sid, "search", {sid: {"step": "choose", "obj_uuid": chest.uuid, "obj_name": chest.display_name, "actions": ["Search", "Step Away"]}})
    assert handled2
    assert any("already searched" in e.get('content', '').lower() for e in emits2)
    count_after_second = sum(1 for o in list(chest.container_small_slots) + list(chest.container_large_slots) if o)
    assert count_after_second == count_after_first

