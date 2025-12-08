import pytest
import time
from world import World, Faction, CharacterSheet
from role_model import FactionRole
from daily_system import process_daily_cycle, DAY_LENGTH_TICKS
from mission_model import MissionStatus

def test_faction_role_management():
    """Test adding/assigning roles in a faction."""
    faction = Faction("f1", "Test Faction")
    
    # 1. Add Role
    role = FactionRole(id="miner", name="Miner", description="Dig stuff")
    faction.add_role(role)
    assert "miner" in faction.roles
    assert faction.roles["miner"].name == "Miner"
    
    # 2. Assign Role
    member_id = "user123"
    faction.member_player_ids.append(member_id)
    assert faction.assign_role(member_id, "miner") is True
    assert faction.member_roles[member_id] == "miner"
    
    # 3. Get Role
    assigned = faction.get_member_role(member_id)
    assert assigned is not None
    assert assigned.id == "miner"
    
    # 4. Revoke Role
    assert faction.revoke_role(member_id) is True
    assert member_id not in faction.member_roles
    
    # 5. Remove Role definition
    faction.assign_role(member_id, "miner")
    assert faction.remove_role("miner") is True
    assert "miner" not in faction.roles
    assert member_id not in faction.member_roles # Should be auto-revoked

def test_daily_cycle_integrtion():
    """Test the daily cycle triggers mission generation."""
    world = World()
    
    # Setup Faction and Member
    faction = world.create_faction("Mining Co")
    member_id = "u1"
    # Create fake user/sheet so verification doesn't crash if it checks them
    world.create_user("MinerBob", "pass", "desc") 
    # Hack: force u1 as the id for simplicity or retrieve it
    u1 = world.get_user_by_display_name("MinerBob")
    member_id = u1.user_id
    
    faction.add_member_player(member_id)
    
    # Setup Role
    role = FactionRole(
        id="miner_role",
        name="Miner",
        description="Dig 5 stone",
        contract_type="resource_contribution",
        contract_config={"resource_tag": "stone", "amount": 5}
    )
    faction.add_role(role)
    faction.assign_role(member_id, "miner_role")
    
    # Run cycle - Day 1 Start
    # world.game_time_ticks starts at 0. 
    # process_daily_cycle increments then checks % DAY_LENGTH == 0
    # So we need to run it DAY_LENGTH times to hit the trigger?
    # Actually if DAY_LENGTH is 24, 24 % 24 == 0. So 24 calls.
    
    for _ in range(DAY_LENGTH_TICKS):
        process_daily_cycle(world)
        
    # Check if mission generated
    assert len(world.missions) == 1
    mission = list(world.missions.values())[0]
    assert mission.assignee_id == member_id
    assert mission.status == MissionStatus.ACTIVE
    assert "stone" in mission.objectives[0].description.lower()
    
    # Run cycle - Day 2 Start (Failure check)
    # Advance another full day
    # The mission is still ACTIVE. New day should mark it FAILED.
    
    old_uuid = mission.uuid
    
    for _ in range(DAY_LENGTH_TICKS):
        process_daily_cycle(world)
        
    assert world.missions[old_uuid].status == MissionStatus.FAILED
    
    # And a NEW mission should be assigned
    active_missions = [m for m in world.missions.values() if m.status == MissionStatus.ACTIVE]
    assert len(active_missions) == 1
    new_mission = active_missions[0]
    assert new_mission.uuid != old_uuid
    assert new_mission.assignee_id == member_id
