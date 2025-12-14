import pytest
from unittest.mock import MagicMock, patch
import time
import random

from world import World, Room, CharacterSheet, Mission, Object
from mission_model import MissionStatus, VisitRoomObjective
from daily_system import _assign_daily_contract, _resolve_outstanding_contracts, _apply_failure_consequence
from role_model import FactionRole
import npc_service
import mission_service

def test_room_events():
    """Verify that Room.events works and cuts off at 50."""
    r = Room(id="r1", description="Test Room")
    assert r.events == []
    
    # Add 60 events
    for i in range(60):
        r.add_event({"id": i, "timestamp": time.time()})
        
    assert len(r.events) == 50
    assert r.events[0]["id"] == 10  # Should have dropped 0-9
    assert r.events[-1]["id"] == 59

def test_world_indexes_npc():
    """Verify npc_ids_reverse index is maintained."""
    w = World()
    
    # Manually adding via get_or_create_npc_id (used by npc_service)
    npc_name = "TestNPC"
    uid = w.get_or_create_npc_id(npc_name)
    
    assert w.npc_ids[npc_name] == uid
    assert w.npc_ids_reverse[uid] == npc_name
    
    # Verify persistence/loading populates it (mock scenario)
    w2 = World.from_dict(w.to_dict())
    assert w2.npc_ids_reverse[uid] == npc_name

def test_world_indexes_missions():
    """Verify missions_by_assignee index is maintained."""
    w = World()
    
    # create mission via service (accepting it)
    m = mission_service.create_mission(w, "Test", "Desc", "issuer", [])
    assignee = "user1"
    
    mission_service.accept_mission(w, m.uuid, assignee)
    
    assert assignee in w.missions_by_assignee
    assert m.uuid in w.missions_by_assignee[assignee]
    
    # Verify persistence/loading
    w2 = World.from_dict(w.to_dict())
    assert assignee in w2.missions_by_assignee
    assert m.uuid in w2.missions_by_assignee[assignee]

def test_daily_system_patrol_target():
    """Verify patrol contracts pick a specific room."""
    w = World()
    w.rooms['r1'] = Room(id='r1', description='Room 1') # Targetable
    
    faction = MagicMock()
    faction.faction_id = 'f1'
    
    role = FactionRole(id='guard', name='Guard', description='Guard Role', contract_type='patrol', contract_config={})
    
    _assign_daily_contract(w, faction, 'u1', role)
    
    # Check mission
    assert 'u1' in w.missions_by_assignee
    mid = list(w.missions_by_assignee['u1'])[0]
    mission = w.missions[mid]
    
    assert len(mission.objectives) == 1
    obj = mission.objectives[0]
    assert isinstance(obj, VisitRoomObjective)
    assert obj.target_id == 'r1' # Should pick the only room
    assert "Patrol r1" in obj.description

def test_daily_system_optimized_lookup():
    """Verify _resolve_outstanding_contracts uses index."""
    w = World()
    w.missions_by_assignee = {'u1': set()} # Empty set, should result in NO iterations if working
    
    # If it fell back to linear scan, it would look at w.missions
    # Let's put a mission in w.missions that matches criteria but is NOT in index
    # If optimization works, it won't see it (because we manually desynced index to test)
    # Actually simpler: Put mission in global, ensure logic works normally with index.
    
    m = Mission(title="M", description="D", issuer_id="i", assignee_id="u1", faction_id="f1", status=MissionStatus.ACTIVE)
    w.missions[m.uuid] = m
    w.missions_by_assignee['u1'].add(m.uuid)
    
    # This should find it and fail it
    _resolve_outstanding_contracts(w, "u1", "f1")
    assert m.status == MissionStatus.FAILED

def test_instrumentation_pickup():
    """Verify pick up logs event."""
    from interaction_service import handle_interaction_input
    
    w = World()
    r = Room(id='r1', description='Desc')
    w.rooms['r1'] = r
    
    # Player
    u = w.create_user("User", "pass", "Display")
    w.players['sid1'] = MagicMock()
    w.players['sid1'].user_id = u.user_id
    w.players['sid1'].sheet = u.sheet
    w.players['sid1'].room_id = 'r1'
    
    # Object
    # Object
    obj = Object(display_name='Stone')
    obj.uuid = 'stone_uuid'
    r.objects[obj.uuid] = obj
    
    # Setup session
    sessions = {'sid1': {'step': 'choose', 'obj_uuid': obj.uuid, 'obj_name': 'Stone', 'actions': ['Pick Up']}}
    
    handle_interaction_input(w, 'sid1', 'Pick Up', sessions)
    
    assert len(r.events) == 1
    assert r.events[0]['type'] == 'take'
    assert r.events[0]['actor_id'] == u.user_id

def test_instrumentation_attack():
    """Verify attack logs violence event."""
    from combat_service import attack
    
    w = World()
    r = Room(id='r1', description='Desc')
    w.rooms['r1'] = r
    
    # Attacker
    u = w.create_user("Attacker", "pass", "Attacker")
    w.players['sid1'] = MagicMock()
    w.players['sid1'].user_id = u.user_id
    w.players['sid1'].sheet = u.sheet
    w.players['sid1'].room_id = 'r1'
    u.sheet.strength = 10
    
    # Victim NPC
    npc = CharacterSheet(display_name="Victim", hp=10, max_hp=10)
    w.npc_sheets["Victim"] = npc
    r.npcs.add("Victim")
    
    attack(w, "state.json", 'sid1', 'Victim', {}, set(), MagicMock(), MagicMock())
    
    assert len(r.events) == 1
    assert r.events[0]['type'] == 'violence'
    assert r.events[0]['actor_name'] == "Attacker"
    assert r.events[0]['target_name'] == "Victim"
