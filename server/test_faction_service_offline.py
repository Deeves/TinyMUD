from __future__ import annotations

import os
from typing import Set

from world import World
from faction_service import handle_faction_command


def test_faction_offline_invariants(monkeypatch, tmp_path):
    # Force offline path (no API key and no model)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    try:
        import faction_service as fs  # type: ignore
        monkeypatch.setattr(fs, '_get_gemini_model', lambda: None, raising=False)
    except Exception:
        pass

    w = World()
    state_file = tmp_path / 'world_state.json'

    # Run the command under test
    handled, err, emits, broadcasts = handle_faction_command(w, str(state_file), None, ['factiongen'])
    assert handled and err is None

    # Collect created room ids
    room_ids: Set[str] = set(w.rooms.keys())
    assert len(room_ids) >= 3  # offline fallback creates 3 rooms

    # Verify food and water exist in at least one of the created rooms
    has_food = False
    has_water = False
    for rid in room_ids:
        r = w.rooms[rid]
        for o in r.objects.values():
            tags = set(getattr(o, 'object_tags', []) or [])
            sv = int(getattr(o, 'satiation_value', 0) or 0)
            hv = int(getattr(o, 'hydration_value', 0) or 0)
            if any(str(t).lower().startswith('edible') for t in tags) or sv > 0:
                has_food = True
            if any(str(t).lower().startswith('drinkable') for t in tags) or hv > 0:
                has_water = True
    assert has_food, 'Expected at least one edible object in generated faction'
    assert has_water, 'Expected at least one drinkable object in generated faction'

    # Verify each NPC placed into a room has an owned bed in that same room
    # Build NPC->room mapping from room.npcs
    npc_rooms: dict[str, str] = {}
    for rid in room_ids:
        for name in w.rooms[rid].npcs:
            npc_rooms[name] = rid
    assert len(npc_rooms) >= 2  # offline fallback creates 3 NPCs

    for name, rid in npc_rooms.items():
        npc_id = w.get_or_create_npc_id(name)
        r = w.rooms[rid]
        bed_found = False
        for o in r.objects.values():
            tags = set(getattr(o, 'object_tags', []) or [])
            owner = getattr(o, 'owner_id', None)
            if any(str(t).strip().lower() == 'bed' for t in tags) and owner == npc_id:
                bed_found = True
                break
        assert bed_found, f"NPC '{name}' should have an owned bed in room '{rid}'"


def test_faction_features_offline(monkeypatch, tmp_path):
    # Force offline path (no API key and no model)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    try:
        import faction_service as fs  # type: ignore
        monkeypatch.setattr(fs, '_get_gemini_model', lambda: None, raising=False)
    except Exception:
        pass

    w = World()
    state_file = tmp_path / 'world_state.json'

    # Run the command under test
    handled, err, emits, broadcasts = handle_faction_command(w, str(state_file), None, ['factiongen'])
    assert handled and err is None

    # Verify faction created
    faction_name = "The Iron Vanguard"
    faction = w.get_faction_by_name(faction_name)
    assert faction is not None
    assert faction.description == "A disciplined group of warriors dedicated to protecting the realm."

    # Verify rooms owned by faction
    room_ids: Set[str] = set(w.rooms.keys())
    assert len(room_ids) >= 3
    for rid in room_ids:
        r = w.rooms[rid]
        assert r.faction_id == faction.faction_id

    # Verify NPCs are members
    npc_rooms: dict[str, str] = {}
    for rid in list(room_ids):
        for name in w.rooms[rid].npcs:
            npc_rooms[name] = rid

    assert len(npc_rooms) >= 3
    for name in npc_rooms:
        npc_id = w.get_or_create_npc_id(name)
        assert faction.is_npc_member(npc_id)

    # Verify beds are owned by faction (in addition to NPC owner)
    for name, rid in npc_rooms.items():
        npc_id = w.get_or_create_npc_id(name)
        r = w.rooms[rid]
        bed_found = False
        for o in r.objects.values():
            tags = set(getattr(o, 'object_tags', []) or [])
            owner = getattr(o, 'owner_id', None)
            f_id = getattr(o, 'faction_id', None)
            if any(str(t).strip().lower() == 'bed' for t in tags) and owner == npc_id:
                assert f_id == faction.faction_id
                bed_found = True
                break
        assert bed_found

    # Verify food/water owned by faction
    for rid in room_ids:
        r = w.rooms[rid]
        for o in r.objects.values():
             tags = set(getattr(o, 'object_tags', []) or [])
             if any(str(t).lower().startswith('edible') for t in tags) or any(str(t).lower().startswith('drinkable') for t in tags):
                 assert o.faction_id == faction.faction_id
