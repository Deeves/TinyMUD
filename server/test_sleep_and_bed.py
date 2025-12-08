from __future__ import annotations

"""Tests for Sleep need and 'bed' object tag.

Covers:
- Offline planner queues a sleep action when sleep < NEED_THRESHOLD and an owned bed is present.
- Executing sleep enters a sleeping state that refills sleep over ticks.
"""

import types


def _mk_bed(world, name: str, owner_npc: str, room):
    from world import Object as WObject
    bed = WObject(display_name=name, description="A cozy bed.", object_tags={"bed"})
    bed.owner_id = world.get_or_create_npc_id(owner_npc)
    if not getattr(bed, 'uuid', None):
        bed.uuid = name + "-uuid"
    room.objects[bed.uuid] = bed
    return bed


def test_offline_plan_sleep_when_tired(monkeypatch):
    import server as srv
    from world import Room, CharacterSheet, World
    # Use fresh world to avoid stale state from other tests
    srv.world = World()
    # Build a tiny world context
    r = Room(id="inn", description="A quiet inn room")
    # Place NPC into the room in the global world
    npc_name = "Sleeper"
    srv.world.rooms[r.id] = r
    r.npcs.add(npc_name)
    sheet = srv._ensure_npc_sheet(npc_name)
    # Make the NPC tired
    setattr(sheet, 'sleep', float(srv.NEED_THRESHOLD) - 1.0)
    # Add an owned bed
    bed = _mk_bed(srv.world, "Simple Bed", npc_name, r)
    # Plan
    plan = srv._npc_offline_plan(npc_name, r, sheet)
    assert any(step.get('tool') == 'sleep' for step in plan), "Planner should schedule sleep when tired and a bed is owned."


def test_sleep_action_sets_sleeping_state(monkeypatch):
    import server as srv
    from world import Room, World
    # Use fresh world to avoid stale state from other tests
    srv.world = World()
    r = Room(id="inn2", description="Another room")
    srv.world.rooms[r.id] = r
    npc = "Dreamer"
    r.npcs.add(npc)
    sheet = srv._ensure_npc_sheet(npc)
    setattr(sheet, 'sleep', 10.0)
    bed = _mk_bed(srv.world, "Dreamer's Bed", npc, r)
    # Ensure NPC ID mapping exists for validation
    if npc not in srv.world.npc_ids:
        srv.world.npc_ids[npc] = str(__import__('uuid').uuid4())
    # Execute sleep action
    srv._npc_execute_action(npc, r.id, {'tool': 'sleep', 'args': {'bed_uuid': bed.uuid}})
    assert getattr(sheet, 'sleeping_ticks_remaining', 0) > 0
    assert getattr(sheet, 'sleeping_bed_uuid', None) == bed.uuid
    
    # Validate world integrity after sleep action mutations
    validation_errors = srv.world.validate()
    assert validation_errors == [], f"World validation failed after sleep action: {validation_errors}"
