"""Tests for NPC planner tool 'move_through' to travel between rooms.

Covers:
- Moving through a named door
- Moving through a Travel Point object
- Denial due to door lock policy
- Auto-pick when exactly one travel option exists and name omitted
"""

from world import World, Room, Object
import server as srv
import game_loop


def _fresh_world():
    srv.world = World()
    # Sync game_loop context with test world
    try:
        ctx = game_loop.get_context()
        ctx.world = srv.world
    except RuntimeError:
        pass
    return srv.world


def test_npc_move_through_named_door_success():
    w = _fresh_world()
    # Rooms
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    # Link via named door
    r1.doors["oak door"] = "r2"
    w.rooms[r1.id] = r1
    w.rooms[r2.id] = r2
    # NPC present in r1
    npc = "Innkeeper"
    r1.npcs.add(npc)

    # Execute move via planner tool
    srv._npc_execute_action(npc, r1.id, {"tool": "move_through", "args": {"name": "oak door"}})

    assert npc not in w.rooms["r1"].npcs, "NPC should have left the origin room"
    assert npc in w.rooms["r2"].npcs, "NPC should have arrived in the target room"


def test_npc_move_through_travel_point_object_success():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    w.rooms[r1.id] = r1
    w.rooms[r2.id] = r2
    # Add a Travel Point object named Portal
    portal = Object(display_name="Portal", description="A shimmering gate.", object_tags={"Immovable", "Travel Point"}, link_target_room_id="r2")
    r1.objects[portal.uuid] = portal
    # NPC in r1
    npc = "Wanderer"
    r1.npcs.add(npc)

    # Execute move by object name (case-insensitive / fuzzy is supported but we pass exact)
    srv._npc_execute_action(npc, r1.id, {"tool": "move_through", "args": {"name": "portal"}})

    assert npc not in w.rooms["r1"].npcs, "NPC should have left the origin room via the travel point"
    assert npc in w.rooms["r2"].npcs, "NPC should have arrived in the target room via the travel point"


def test_npc_move_through_locked_denied():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    r1.doors["oak door"] = "r2"
    # Door lock denying all (no allow_ids, no allow_rel)
    r1.door_locks["oak door"] = {"allow_ids": [], "allow_rel": []}
    w.rooms[r1.id] = r1
    w.rooms[r2.id] = r2
    npc = "Guard"
    r1.npcs.add(npc)

    # Attempt to move through locked door
    srv._npc_execute_action(npc, r1.id, {"tool": "move_through", "args": {"name": "oak door"}})

    assert npc in w.rooms["r1"].npcs, "Locked door should prevent NPC from leaving"
    assert npc not in w.rooms["r2"].npcs, "NPC should not appear in the target room when denied"


def test_npc_move_through_autopick_single_option():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    # Only one travel candidate (a door)
    r1.doors["north gate"] = "r2"
    w.rooms[r1.id] = r1
    w.rooms[r2.id] = r2
    npc = "Ranger"
    r1.npcs.add(npc)

    # Omit name; tool should auto-pick the only option
    srv._npc_execute_action(npc, r1.id, {"tool": "move_through", "args": {}})

    assert npc not in w.rooms["r1"].npcs, "NPC should auto-pick the sole travel option and leave"
    assert npc in w.rooms["r2"].npcs, "NPC should arrive in the destination room"
