import pytest
from world import World
from faction_service import handle_faction_command

def test_factiongen_creates_ranks():
    world = World()
    # Ensure clean state
    existing = world.get_faction_by_name("The Iron Vanguard")
    if existing:
        world.remove_faction(existing.faction_id)

    # Run factiongen
    # We rely on the fact that without an API key, it falls back to offline default
    # which we updated to include ranks.
    handled, err, emits, broadcasts = handle_faction_command(world, "test_state.json", None, ["factiongen"])
    
    assert handled
    assert err is None
    
    # Verify faction exists
    faction = world.get_faction_by_name("The Iron Vanguard")
    assert faction is not None
    
    # Verify ranks exist
    assert "Recruit" in faction.ranks
    assert faction.ranks["Recruit"] == 1
    assert "Captain" in faction.ranks
    assert faction.ranks["Captain"] == 5
    
    # Verify NPC ranks
    # We need to find the NPC IDs. The offline graph defines "Quartermaster" with rank "Captain".
    quartermaster_id = world.get_or_create_npc_id("Quartermaster")
    assert faction.is_npc_member(quartermaster_id)
    assert faction.get_member_rank(quartermaster_id) == "Captain"
    
    scout_id = world.get_or_create_npc_id("Scout Rafe")
    assert faction.is_npc_member(scout_id)
    assert faction.get_member_rank(scout_id) == "Recruit"

if __name__ == "__main__":
    test_factiongen_creates_ranks()
