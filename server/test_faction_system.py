"""Tests for the faction system in TinyMUD.

This test suite verifies that the faction data structure and related
functionality work correctly according to the game's architectural patterns.
"""

import pytest
import uuid
from world import World, Faction


def test_faction_creation_and_basic_properties():
    """Test creating a faction with basic properties."""
    faction_id = str(uuid.uuid4())
    faction = Faction(
        faction_id=faction_id,
        name="The Order of Light",
        description="A righteous faction dedicated to justice"
    )
    
    assert faction.faction_id == faction_id
    assert faction.name == "The Order of Light"
    assert faction.description == "A righteous faction dedicated to justice"
    assert faction.member_player_ids == []
    assert faction.member_npc_ids == []
    assert faction.ally_faction_ids == []
    assert faction.rival_faction_ids == []
    assert faction.get_total_members() == 0


def test_faction_member_management():
    """Test adding and removing members from factions."""
    faction = Faction(str(uuid.uuid4()), "Test Faction")
    
    player_id = str(uuid.uuid4())
    npc_id = str(uuid.uuid4())
    
    # Test adding members
    assert faction.add_member_player(player_id) is True
    assert faction.add_member_npc(npc_id) is True
    assert faction.get_total_members() == 2
    
    # Test duplicate addition returns False
    assert faction.add_member_player(player_id) is False
    assert faction.add_member_npc(npc_id) is False
    assert faction.get_total_members() == 2
    
    # Test membership queries
    assert faction.is_player_member(player_id) is True
    assert faction.is_npc_member(npc_id) is True
    
    # Test removing members
    assert faction.remove_member_player(player_id) is True
    assert faction.remove_member_npc(npc_id) is True
    assert faction.get_total_members() == 0
    
    # Test removing non-members returns False
    assert faction.remove_member_player(player_id) is False
    assert faction.remove_member_npc(npc_id) is False


def test_faction_relationship_management():
    """Test adding and removing ally/rival relationships."""
    faction = Faction(str(uuid.uuid4()), "Test Faction")
    
    ally_id = str(uuid.uuid4())
    rival_id = str(uuid.uuid4())
    
    # Test adding relationships
    assert faction.add_ally(ally_id) is True
    assert faction.add_rival(rival_id) is True
    
    # Test duplicate addition returns False
    assert faction.add_ally(ally_id) is False
    assert faction.add_rival(rival_id) is False
    
    # Test relationship queries
    assert faction.is_ally(ally_id) is True
    assert faction.is_rival(rival_id) is True
    
    # Test removing relationships
    assert faction.remove_ally(ally_id) is True
    assert faction.remove_rival(rival_id) is True
    
    # Test removing non-relationships returns False
    assert faction.remove_ally(ally_id) is False
    assert faction.remove_rival(rival_id) is False


def test_faction_serialization():
    """Test faction to_dict and from_dict methods."""
    original = Faction(
        faction_id=str(uuid.uuid4()),
        name="Serialization Test",
        description="Testing serialization",
        member_player_ids=[str(uuid.uuid4())],
        member_npc_ids=[str(uuid.uuid4())],
        ally_faction_ids=[str(uuid.uuid4())],
        rival_faction_ids=[str(uuid.uuid4())]
    )
    original.created_timestamp = 1234567890.0
    original.leader_player_id = str(uuid.uuid4())
    
    # Serialize to dict
    data = original.to_dict()
    
    # Deserialize back
    restored = Faction.from_dict(data)
    
    # Verify all fields match
    assert restored.faction_id == original.faction_id
    assert restored.name == original.name
    assert restored.description == original.description
    assert restored.member_player_ids == original.member_player_ids
    assert restored.member_npc_ids == original.member_npc_ids
    assert restored.ally_faction_ids == original.ally_faction_ids
    assert restored.rival_faction_ids == original.rival_faction_ids
    assert restored.created_timestamp == original.created_timestamp
    assert restored.leader_player_id == original.leader_player_id


def test_world_faction_integration():
    """Test faction integration with World class."""
    world = World()
    
    # Test creating a faction through world
    faction = world.create_faction("Test Guild", "A test guild for testing")
    
    assert faction.name == "Test Guild"
    assert faction.description == "A test guild for testing"
    assert faction.faction_id in world.factions
    assert world.factions[faction.faction_id] == faction
    assert faction.created_timestamp is not None
    
    # Test duplicate name prevention
    with pytest.raises(ValueError, match="already exists"):
        world.create_faction("Test Guild", "Another guild")
    
    # Test case-insensitive name check
    with pytest.raises(ValueError, match="already exists"):
        world.create_faction("test guild", "Another guild")


def test_world_faction_lookup():
    """Test faction lookup methods."""
    world = World()
    
    # Create test faction
    faction = world.create_faction("Lookup Test", "For lookup testing")
    
    # Test name-based lookup
    found = world.get_faction_by_name("Lookup Test")
    assert found == faction
    
    # Test case-insensitive lookup
    found = world.get_faction_by_name("lookup test")
    assert found == faction
    
    # Test non-existent faction
    found = world.get_faction_by_name("Non-existent")
    assert found is None


def test_world_player_faction_membership():
    """Test player faction membership tracking."""
    world = World()
    
    # Create test user and faction
    user = world.create_user("TestPlayer", "password", "A test player")
    faction = world.create_faction("Player Faction", "For testing player membership")
    
    # Add player to faction
    faction.add_member_player(user.user_id)
    
    # Test membership lookup
    player_factions = world.get_player_factions(user.user_id)
    assert len(player_factions) == 1
    assert player_factions[0] == faction
    
    # Test non-member
    other_user = world.create_user("OtherPlayer", "password", "Another player")
    other_factions = world.get_player_factions(other_user.user_id)
    assert len(other_factions) == 0


def test_world_npc_faction_membership():
    """Test NPC faction membership tracking."""
    world = World()
    
    # Create test NPC and faction
    npc_name = "TestNPC"
    npc_id = world.get_or_create_npc_id(npc_name)
    faction = world.create_faction("NPC Faction", "For testing NPC membership")
    
    # Add NPC to faction
    faction.add_member_npc(npc_id)
    
    # Test membership lookup
    npc_factions = world.get_npc_factions(npc_id)
    assert len(npc_factions) == 1
    assert npc_factions[0] == faction
    
    # Test non-member
    other_npc_id = world.get_or_create_npc_id("OtherNPC")
    other_factions = world.get_npc_factions(other_npc_id)
    assert len(other_factions) == 0


def test_faction_removal_with_cleanup():
    """Test that removing a faction cleans up references."""
    world = World()
    
    # Create test factions
    faction1 = world.create_faction("Faction One", "First faction")
    faction2 = world.create_faction("Faction Two", "Second faction")
    
    # Set up relationships
    faction1.add_ally(faction2.faction_id)
    faction2.add_rival(faction1.faction_id)
    
    # Remove faction1
    assert world.remove_faction(faction1.faction_id) is True
    
    # Verify faction is gone
    assert faction1.faction_id not in world.factions
    
    # Verify references cleaned up
    assert faction1.faction_id not in faction2.ally_faction_ids
    assert faction1.faction_id not in faction2.rival_faction_ids


def test_faction_validation():
    """Test faction integrity validation."""
    world = World()
    
    # Create test data
    user = world.create_user("TestUser", "password", "A test user")
    npc_id = world.get_or_create_npc_id("TestNPC")
    faction1 = world.create_faction("Valid Faction", "A valid faction")
    faction2 = world.create_faction("Another Faction", "Another faction")
    
    # Add valid relationships
    faction1.add_member_player(user.user_id)
    faction1.add_member_npc(npc_id)
    faction1.add_ally(faction2.faction_id)
    faction1.leader_player_id = user.user_id
    
    # Validation should pass
    errors = world.validate_faction_integrity()
    assert len(errors) == 0
    
    # Add invalid player reference
    faction1.member_player_ids.append("invalid-player-id")
    errors = world.validate_faction_integrity()
    assert len(errors) == 1
    assert "non-existent player" in errors[0]
    
    # Clean up for next test
    faction1.member_player_ids.remove("invalid-player-id")
    
    # Add invalid NPC reference
    faction1.member_npc_ids.append("invalid-npc-id")
    errors = world.validate_faction_integrity()
    assert len(errors) == 1
    assert "non-existent NPC" in errors[0]
    
    # Clean up for next test
    faction1.member_npc_ids.remove("invalid-npc-id")
    
    # Add invalid ally reference
    faction1.ally_faction_ids.append("invalid-faction-id")
    errors = world.validate_faction_integrity()
    assert len(errors) == 1
    assert "non-existent ally" in errors[0]
    
    # Clean up for next test
    faction1.ally_faction_ids.remove("invalid-faction-id")
    
    # Add self as ally (invalid)
    faction1.ally_faction_ids.append(faction1.faction_id)
    errors = world.validate_faction_integrity()
    assert len(errors) == 1
    assert "lists itself as an ally" in errors[0]
    
    # Clean up for next test
    faction1.ally_faction_ids.remove(faction1.faction_id)
    
    # Add conflicting ally/rival relationship
    faction1.rival_faction_ids.append(faction2.faction_id)
    errors = world.validate_faction_integrity()
    assert len(errors) == 1
    assert "both ally and rival" in errors[0]
    
    # Clean up for next test
    faction1.rival_faction_ids.remove(faction2.faction_id)
    
    # Invalid leader (not a member)
    faction1.leader_player_id = "some-other-user"
    errors = world.validate_faction_integrity()
    assert len(errors) == 1  # Non-existent user (can't check membership)
    assert any("non-existent leader" in error for error in errors)
    
    # Test leader who exists but is not a member
    other_user = world.create_user("OtherUser", "password", "Another user")
    faction1.leader_player_id = other_user.user_id
    errors = world.validate_faction_integrity()
    assert len(errors) == 1  # Leader exists but is not a member
    assert any("leader is not a member" in error for error in errors)


def test_world_faction_persistence():
    """Test that factions are properly saved and loaded."""
    world = World()
    
    # Create test data
    user = world.create_user("TestUser", "password", "Test description")
    npc_id = world.get_or_create_npc_id("TestNPC")
    
    faction1 = world.create_faction("Persistent Faction", "Will be saved")
    faction1.add_member_player(user.user_id)
    faction1.add_member_npc(npc_id)
    faction1.leader_player_id = user.user_id
    
    faction2 = world.create_faction("Allied Faction", "An ally")
    faction1.add_ally(faction2.faction_id)
    faction2.add_rival(faction1.faction_id)
    
    # Serialize and deserialize
    data = world.to_dict()
    restored_world = World.from_dict(data)
    
    # Verify factions were preserved
    assert len(restored_world.factions) == 2
    
    restored_faction1 = restored_world.get_faction_by_name("Persistent Faction")
    assert restored_faction1 is not None
    assert restored_faction1.description == "Will be saved"
    assert user.user_id in restored_faction1.member_player_ids
    assert npc_id in restored_faction1.member_npc_ids
    assert restored_faction1.leader_player_id == user.user_id
    
    restored_faction2 = restored_world.get_faction_by_name("Allied Faction")
    assert restored_faction2 is not None
    assert restored_faction2.faction_id in restored_faction1.ally_faction_ids
    assert restored_faction1.faction_id in restored_faction2.rival_faction_ids


def test_world_validation_includes_factions():
    """Test that world validation includes faction validation."""
    world = World()
    
    # Create a faction with invalid references
    faction = world.create_faction("Bad Faction", "Has invalid references")
    faction.member_player_ids.append("invalid-player-id")
    faction.ally_faction_ids.append("invalid-faction-id")
    
    # Run world validation
    errors = world.validate()
    
    # Should include faction-related errors
    faction_errors = [error for error in errors if "Faction" in error or "faction" in error]
    assert len(faction_errors) >= 2  # At least the two we added
    assert any("non-existent player" in error for error in faction_errors)
    assert any("non-existent ally" in error for error in faction_errors)


if __name__ == "__main__":
    pytest.main([__file__])