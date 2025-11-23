"""Tests for world.validate() method.

This module validates that the World.validate() method correctly detects
various types of data integrity and referential integrity issues.
"""

from __future__ import annotations

import uuid

import pytest

from world import World, Room, Player, User, Object, CharacterSheet


def test_empty_world_validates_clean():
    """An empty world should have no validation errors."""
    w = World()
    errors = w.validate()
    assert errors == []


def test_simple_valid_world_passes_validation():
    """A basic world with rooms, players, and NPCs should validate cleanly."""
    w = World()
    
    # Add rooms with properly set up reciprocal doors
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Create door objects first, then set up doors with their UUIDs
    door1_obj = Object(
        display_name="north door",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="room2"
    )
    door2_obj = Object(
        display_name="south door",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="room1"
    )
    
    # Use the auto-generated UUIDs from the objects
    door1_id = door1_obj.uuid
    door2_id = door2_obj.uuid

    # Create reciprocal doors with proper objects
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = door1_id
    room2.doors["south"] = "room1"
    room2.door_ids["south"] = door2_id

    # Store the objects using their UUIDs as keys
    room1.objects[door1_id] = door1_obj
    room2.objects[door2_id] = door2_obj    # Add a player
    w.add_player("sid123", "TestPlayer", "room1")
    
    # Add an NPC with sheet
    w.npc_sheets["Guard"] = CharacterSheet(display_name="Guard")
    w.npc_ids["Guard"] = str(uuid.uuid4())  # Ensure NPC has ID mapping
    room1.npcs.add("Guard")
    
    # Add a user account
    w.create_user("Alice", "password123", "A brave adventurer")
    
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
    
    # Create door objects first, then set up doors with their UUIDs (mutation)
    door1_obj = Object(
        display_name="north door",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="room2"
    )
    door2_obj = Object(
        display_name="south door",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="room1"
    )
    
    # Use the auto-generated UUIDs from the objects
    door1_id = door1_obj.uuid
    door2_id = door2_obj.uuid
    
    # Add reciprocal doors with proper objects
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = door1_id
    room2.doors["south"] = "room1"
    room2.door_ids["south"] = door2_id
    
    # Store the objects using their UUIDs as keys
    room1.objects[door1_id] = door1_obj
    room2.objects[door2_id] = door2_obj
    
    # Should be clean after proper setup
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


def test_door_without_reciprocal_connection():
    """Validation should detect doors lacking reciprocal connections."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add door from room1 to room2 but no door back
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = str(uuid.uuid4())
    
    errors = w.validate()
    assert any("door 'north' -> 'room2' lacks reciprocal door" in err for err in errors)


def test_door_with_proper_reciprocal_connection():
    """Validation should pass when doors have proper reciprocal connections."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add reciprocal doors
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = str(uuid.uuid4())
    room2.doors["south"] = "room1"
    room2.door_ids["south"] = str(uuid.uuid4())
    
    errors = w.validate()
    reciprocal_errors = [e for e in errors if "lacks reciprocal door" in e]
    assert len(reciprocal_errors) == 0


def test_door_missing_door_id():
    """Validation should detect doors without proper door_ids."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add door without door_id
    room1.doors["north"] = "room2"
    # Intentionally don't set door_ids["north"]
    
    errors = w.validate()
    assert any("door 'north' missing door_id" in err for err in errors)


def test_door_object_missing():
    """Validation should detect missing door objects."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add door with door_id but no matching object
    door_id = str(uuid.uuid4())
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = door_id
    # Intentionally don't create room1.objects[door_id]
    
    errors = w.validate()
    assert any(f"door 'north' has door_id {door_id} but no matching object" in err
               for err in errors)


def test_door_object_missing_travel_point_tag():
    """Validation should detect door objects without Travel Point tag."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Create door with object missing Travel Point tag
    door_id = str(uuid.uuid4())
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = door_id
    
    door_obj = Object(display_name="north door", object_tags={"Immovable"})  # Missing Travel Point
    door_obj.uuid = door_id
    room1.objects[door_id] = door_obj
    
    errors = w.validate()
    assert any("door object 'north' missing 'Travel Point' tag" in err for err in errors)


def test_door_object_link_target_mismatch():
    """Validation should detect door objects with mismatched link targets."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    room3 = Room(id="room3", description="Third room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    w.rooms["room3"] = room3
    
    # Create door to room2 but object links to room3
    door_id = str(uuid.uuid4())
    room1.doors["north"] = "room2"
    room1.door_ids["north"] = door_id
    
    door_obj = Object(
        display_name="north door",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="room3"  # Mismatch: door goes to room2 but object links to room3
    )
    door_obj.uuid = door_id
    room1.objects[door_id] = door_obj
    
    errors = w.validate()
    assert any("link_target_room_id mismatch" in err for err in errors)


def test_stairs_without_reciprocal_connection():
    """Validation should detect stairs lacking reciprocal connections."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add stairs up from room1 to room2 but no stairs down back
    room1.stairs_up_to = "room2"
    # Intentionally don't set room2.stairs_down_to = "room1"
    
    errors = w.validate()
    assert any("stairs_up_to 'room2' lacks reciprocal stairs_down_to" in err for err in errors)


def test_stairs_with_proper_reciprocal_connection():
    """Validation should pass when stairs have proper reciprocal connections."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add reciprocal stairs
    room1.stairs_up_to = "room2"
    room2.stairs_down_to = "room1"
    
    errors = w.validate()
    reciprocal_errors = [e for e in errors if "lacks reciprocal stairs" in e]
    assert len(reciprocal_errors) == 0


def test_stairs_missing_stairs_id():
    """Validation should detect stairs without proper stairs IDs."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add stairs without stairs_up_id
    room1.stairs_up_to = "room2"
    room2.stairs_down_to = "room1"
    # Intentionally don't set stairs_up_id or stairs_down_id
    
    errors = w.validate()
    assert any("has stairs_up_to but missing stairs_up_id" in err for err in errors)
    assert any("has stairs_down_to but missing stairs_down_id" in err for err in errors)


def test_stairs_object_missing():
    """Validation should detect missing stairs objects."""
    w = World()
    
    room1 = Room(id="room1", description="First room")
    room2 = Room(id="room2", description="Second room")
    w.rooms["room1"] = room1
    w.rooms["room2"] = room2
    
    # Add stairs with IDs but no matching objects
    stairs_up_id = str(uuid.uuid4())
    stairs_down_id = str(uuid.uuid4())
    
    room1.stairs_up_to = "room2"
    room1.stairs_up_id = stairs_up_id
    room2.stairs_down_to = "room1"
    room2.stairs_down_id = stairs_down_id
    # Intentionally don't create objects[stairs_up_id] or objects[stairs_down_id]
    
    errors = w.validate()
    assert any(f"stairs_up_id {stairs_up_id} but no matching object" in err for err in errors)
    assert any(f"stairs_down_id {stairs_down_id} but no matching object" in err for err in errors)


def test_travel_point_missing_immovable_tag():
    """Validation should detect travel points without Immovable tag."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    w.rooms["room1"] = room
    
    # Create travel point without Immovable tag
    obj = Object(
        display_name="portal",
        object_tags={"Travel Point"},  # Missing Immovable tag
        link_target_room_id="room2"
    )
    room.objects[obj.uuid] = obj
    
    errors = w.validate()
    assert any("travel point 'portal' missing 'Immovable' tag" in err for err in errors)


def test_travel_point_missing_link_target():
    """Validation should detect travel points without link targets."""
    w = World()
    
    room = Room(id="room1", description="Test room")
    w.rooms["room1"] = room
    
    # Create travel point without link_target_room_id
    obj = Object(
        display_name="broken portal",
        object_tags={"Immovable", "Travel Point"}
        # Missing link_target_room_id
    )
    room.objects[obj.uuid] = obj
    
    errors = w.validate()
    assert any("travel point 'broken portal' missing link_target_room_id" in err for err in errors)


def test_comprehensive_reciprocal_linkage_validation():
    """Test validation of a complex world with proper reciprocal linkage."""
    w = World()
    
    # Create rooms
    lobby = Room(id="lobby", description="Main lobby")
    upstairs = Room(id="upstairs", description="Upper floor") 
    garden = Room(id="garden", description="Garden")
    w.rooms["lobby"] = lobby
    w.rooms["upstairs"] = upstairs
    w.rooms["garden"] = garden
    
    # Set up reciprocal doors: lobby <-> garden
    lobby_door_id = str(uuid.uuid4())
    garden_door_id = str(uuid.uuid4())
    
    lobby.doors["garden door"] = "garden"
    lobby.door_ids["garden door"] = lobby_door_id
    garden.doors["lobby door"] = "lobby"
    garden.door_ids["lobby door"] = garden_door_id
    
    # Create door objects
    lobby_door_obj = Object(
        display_name="garden door",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="garden"
    )
    lobby_door_obj.uuid = lobby_door_id
    lobby.objects[lobby_door_id] = lobby_door_obj
    
    garden_door_obj = Object(
        display_name="lobby door", 
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="lobby"
    )
    garden_door_obj.uuid = garden_door_id
    garden.objects[garden_door_id] = garden_door_obj
    
    # Set up reciprocal stairs: lobby <-> upstairs  
    stairs_up_id = str(uuid.uuid4())
    stairs_down_id = str(uuid.uuid4())
    
    lobby.stairs_up_to = "upstairs"
    lobby.stairs_up_id = stairs_up_id
    upstairs.stairs_down_to = "lobby"
    upstairs.stairs_down_id = stairs_down_id
    
    # Create stairs objects
    stairs_up_obj = Object(
        display_name="stairs up",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="upstairs"
    )
    stairs_up_obj.uuid = stairs_up_id
    lobby.objects[stairs_up_id] = stairs_up_obj
    
    stairs_down_obj = Object(
        display_name="stairs down",
        object_tags={"Immovable", "Travel Point"},
        link_target_room_id="lobby"
    )
    stairs_down_obj.uuid = stairs_down_id
    upstairs.objects[stairs_down_id] = stairs_down_obj
    
    # The comprehensive world should validate with no reciprocal linkage errors
    errors = w.validate()
    reciprocal_errors = [e for e in errors if any(phrase in e for phrase in [
        "lacks reciprocal door", "lacks reciprocal stairs", "missing door_id",
        "but no matching object", "missing 'Travel Point' tag", "link_target_room_id mismatch",
        "missing stairs_up_id", "missing stairs_down_id", "missing 'Immovable' tag",
        "missing link_target_room_id"
    ])]
    assert len(reciprocal_errors) == 0, f"Expected no reciprocal linkage errors, got: {reciprocal_errors}"


if __name__ == "__main__":
    pytest.main([__file__])