"""Tests for world.validate() method.

This module validates that the World.validate() method correctly detects
various types of data integrity and referential integrity issues.
"""

from __future__ import annotations

import uuid

import pytest

from world import World, Room, Player, User, Object, CharacterSheet, Inventory


def test_empty_world_validates_clean():
    """An empty world should have no validation errors."""
    w = World()
    errors = w.validate()
    assert errors == []


def test_simple_valid_world_passes_validation():
    """A basic world with rooms, players, and NPCs should validate cleanly."""
    w = World()
    
    # Add a room with a simple door
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = str(uuid.uuid4())
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add a player
    w.add_player("sid123", "TestPlayer", "room1")
    
    # Add an NPC with sheet
    w.npc_sheets["Guard"] = CharacterSheet(display_name="Guard")
    w.npc_ids["Guard"] = str(uuid.uuid4())  # Ensure NPC has ID mapping
    room1.npcs.add("Guard")
    
    # Add a user account
    user = w.create_user("Alice", "password123", "A brave adventurer")
    
    errors = w.validate()
    assert errors == []


def test_duplicate_uuid_detected():
    """Validation should detect duplicate UUIDs across different entities."""
    w = World()
    
    duplicate_uuid = str(uuid.uuid4())
    
    # Create rooms with same UUID
    room1 = Room(id="room1", description="First room")
    room1.uuid = duplicate_uuid
    room2 = Room(id="room2", description="Second room") 
    room2.uuid = duplicate_uuid
    
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    errors = w.validate()
    assert any("Duplicate UUID" in err and duplicate_uuid in err for err in errors)


def test_invalid_uuid_format_detected():
    """Validation should detect invalid UUID formats."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    room.uuid = "not-a-valid-uuid"
    w.rooms["room1"] = room
    
    errors = w.validate()
    assert any("Invalid UUID format" in err for err in errors)


def test_door_to_nonexistent_room_detected():
    """Validation should detect doors pointing to non-existent rooms."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    room.doors["north"] = "nonexistent_room"
    w.rooms["room1"] = room
    
    errors = w.validate()
    assert any("door 'north' points to non-existent room: nonexistent_room" in err for err in errors)


def test_stairs_to_nonexistent_room_detected():
    """Validation should detect stairs pointing to non-existent rooms."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    room.stairs_up_to = "nonexistent_upper_room"
    room.stairs_down_to = "nonexistent_lower_room"
    w.rooms["room1"] = room
    
    errors = w.validate()
    assert any("stairs_up_to points to non-existent room: nonexistent_upper_room" in err for err in errors)
    assert any("stairs_down_to points to non-existent room: nonexistent_lower_room" in err for err in errors)


def test_travel_point_invalid_link_detected():
    """Validation should detect travel point objects with invalid room links."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    door_obj = Object(
        display_name="Magic Portal",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="nonexistent_room"
    )
    room.objects[door_obj.uuid] = door_obj
    w.rooms["room1"] = room
    
    errors = w.validate()
    assert any("travel point 'Magic Portal' links to non-existent room: nonexistent_room" in err for err in errors)


def test_player_in_nonexistent_room_detected():
    """Validation should detect players in non-existent rooms."""
    w = World()
    
    player = Player(sid="sid123", room_id="nonexistent_room", sheet=CharacterSheet(display_name="TestPlayer"))
    w.players["sid123"] = player
    
    errors = w.validate()
    assert any("Player 'sid123' in non-existent room: nonexistent_room" in err for err in errors)


def test_player_not_in_room_players_set_detected():
    """Validation should detect when a player isn't registered in their room's players set."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    w.rooms["room1"] = room
    
    # Create player but don't add to room's players set
    player = Player(sid="sid123", room_id="room1", sheet=CharacterSheet(display_name="TestPlayer"))
    w.players["sid123"] = player
    # Intentionally don't add sid to room.players
    
    errors = w.validate()
    assert any("Player 'sid123' not registered in room 'room1' players set" in err for err in errors)


def test_inventory_constraint_violation_detected():
    """Validation should detect inventory constraint violations."""
    w = World()
    
    # Create a player with invalid inventory
    player_sheet = CharacterSheet(display_name="TestPlayer")
    # Put a large item in a small slot (constraint violation)
    large_item = Object(display_name="Huge Boulder", object_tags={"large"})
    player_sheet.inventory.slots[2] = large_item  # slot 2 is small-only
    
    player = Player(sid="sid123", room_id="__void__", sheet=player_sheet)
    w.players["sid123"] = player
    
    errors = w.validate()
    assert any("inventory slot 2 violates constraints" in err and "Huge Boulder" in err for err in errors)


def test_npc_without_sheet_detected():
    """Validation should detect NPCs referenced in rooms without sheets."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    room.npcs.add("MissingNPC")
    w.rooms["room1"] = room
    # Intentionally don't add NPC sheet
    
    errors = w.validate()
    assert any("Room 'room1' references NPC 'MissingNPC' but no sheet exists" in err for err in errors)


def test_npc_missing_id_mapping_detected():
    """Validation should detect NPCs without ID mappings."""
    w = World()
    
    w.npc_sheets["Guard"] = CharacterSheet(display_name="Guard")
    # Intentionally don't add to npc_ids mapping
    
    errors = w.validate()
    assert any("NPC 'Guard' missing from npc_ids mapping" in err for err in errors)


def test_duplicate_user_display_name_detected():
    """Validation should detect duplicate user display names."""
    w = World()
    
    user1 = User(user_id=str(uuid.uuid4()), display_name="Alice", password="pass1")
    user2 = User(user_id=str(uuid.uuid4()), display_name="alice", password="pass2")  # Same name, different case
    
    w.users[user1.user_id] = user1
    w.users[user2.user_id] = user2
    
    errors = w.validate()
    assert any("Duplicate user display name: alice" in err for err in errors)


def test_user_key_mismatch_detected():
    """Validation should detect user account key mismatches."""
    w = World()
    
    user = User(user_id=str(uuid.uuid4()), display_name="Alice", password="pass1")
    wrong_key = str(uuid.uuid4())
    w.users[wrong_key] = user  # Key doesn't match user.user_id
    
    errors = w.validate()
    assert any("User account key mismatch" in err for err in errors)


def test_room_object_key_mismatch_detected():
    """Validation should detect room object key mismatches."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    obj = Object(display_name="Test Object")
    wrong_key = str(uuid.uuid4())
    room.objects[wrong_key] = obj  # Key doesn't match obj.uuid
    w.rooms["room1"] = room
    
    errors = w.validate()
    assert any("Room 'room1' object key mismatch" in err for err in errors)


def test_invalid_start_room_detected():
    """Validation should detect invalid start room configuration."""
    w = World()
    
    w.start_room_id = "nonexistent_start_room"
    
    errors = w.validate()
    assert any("World start_room_id points to non-existent room: nonexistent_start_room" in err for err in errors)


def test_invalid_relationship_entity_ids_detected():
    """Validation should detect invalid entity IDs in relationships graph."""
    w = World()
    
    w.relationships = {
        "not-a-uuid": {"target1": "friendship"},
        str(uuid.uuid4()): {"not-a-uuid-either": "rivalry"}
    }
    
    errors = w.validate()
    assert any("Invalid entity_id in relationships: not-a-uuid" in err for err in errors)
    assert any("Invalid target entity_id in relationships" in err and "not-a-uuid-either" in err for err in errors)


def test_validation_after_world_mutations():
    """Test validation on a world after various mutations."""
    w = World()
    
    # Start with a valid world
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1 
    w.rooms["room2"] = room2
    
    # Should be clean initially
    errors = w.validate()
    assert errors == []
    
    # Add a door (mutation)
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = str(uuid.uuid4())
    
    # Should still be clean
    errors = w.validate()
    assert errors == []
    
    # Break it by pointing door to invalid room (mutation)
    room1.doors["south"] = "invalid_room"
    
    # Should detect the error
    errors = w.validate()
    assert any("door 'south' points to non-existent room: invalid_room" in err for err in errors)
    
    # Fix it (mutation)
    del room1.doors["south"]
    
    # Should be clean again
    errors = w.validate()
    assert errors == []


if __name__ == "__main__":
    pytest.main([__file__])