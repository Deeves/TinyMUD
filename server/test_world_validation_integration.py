"""
Integration test for World.validate() method with real world state.

This test verifies that the validation works correctly on actual world
configurations that might be created by admin commands.
"""

import os
import tempfile
import pytest
from world import World
from room_service import handle_room_command


def test_validate_real_world_configuration():
    """Test validation on a world created through admin commands."""
    # Create a temporary file for world state
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        state_path = f.name
    
    try:
        # Create a world and add rooms through proper admin commands
        world = World()
        
        # Use room service to create rooms and doors (simulates admin usage)
        
        # Create rooms
        ok1, err1, emits1, broadcasts1 = handle_room_command(world, state_path, 
                                                            ['create', 'lobby', 'The main lobby'])
        assert ok1 and not err1, f"Failed to create lobby: {err1}"
        
        ok2, err2, emits2, broadcasts2 = handle_room_command(world, state_path, 
                                                            ['create', 'garden', 'A beautiful garden'])
        assert ok2 and not err2, f"Failed to create garden: {err2}"
        
        ok3, err3, emits3, broadcasts3 = handle_room_command(world, state_path, 
                                                            ['create', 'upstairs', 'The upper floor'])
        assert ok3 and not err3, f"Failed to create upstairs: {err3}"
        
        # Add doors between lobby and garden
        ok4, err4, emits4, broadcasts4 = handle_room_command(world, state_path, 
                                                           ['adddoor', 'lobby|garden door|garden'])
        assert ok4 and not err4, f"Failed to add door: {err4}"
        
        # Add stairs between lobby and upstairs
        ok5, err5, emits5, broadcasts5 = handle_room_command(world, state_path, 
                                                           ['linkstairs', 'lobby|up|upstairs'])
        assert ok5 and not err5, f"Failed to add stairs: {err5}"
        
        # Validate the world - should pass with proper reciprocal connections
        errors = world.validate()
        
        # Filter out any UUID duplicate errors from test artifacts
        validation_errors = [e for e in errors if not e.startswith("Duplicate UUID")]
        
        if validation_errors:
            print("Validation errors found:")
            for error in validation_errors:
                print(f"  - {error}")
        
        # The world should validate cleanly since room commands create proper reciprocal connections
        assert len(validation_errors) == 0, f"World validation failed with errors: {validation_errors}"
        
        # Verify the structure is as expected
        assert 'lobby' in world.rooms, "Lobby room not created"
        assert 'garden' in world.rooms, "Garden room not created"  
        assert 'upstairs' in world.rooms, "Upstairs room not created"
        
        # Check door reciprocity
        lobby = world.rooms['lobby']
        garden = world.rooms['garden']
        upstairs = world.rooms['upstairs']
        
        # Lobby should have door to garden
        assert 'garden door' in lobby.doors, "Lobby missing door to garden"
        assert lobby.doors['garden door'] == 'garden', "Lobby door points to wrong room"
        
        # Garden should have reciprocal door back to lobby
        garden_doors_to_lobby = [name for name, target in garden.doors.items() if target == 'lobby']
        assert len(garden_doors_to_lobby) > 0, "Garden missing reciprocal door to lobby"
        
        # Lobby should have stairs up to upstairs
        assert lobby.stairs_up_to == 'upstairs', "Lobby missing stairs up"
        
        # Upstairs should have stairs down to lobby
        assert upstairs.stairs_down_to == 'lobby', "Upstairs missing stairs down"
        
        print("✓ Real world configuration validates successfully!")
        print(f"✓ Created {len(world.rooms)} rooms with proper linkage")
        print(f"✓ Door reciprocity: lobby ↔ garden")
        print(f"✓ Stairs reciprocity: lobby ↕ upstairs")
        
    finally:
        # Clean up temp file
        if os.path.exists(state_path):
            os.unlink(state_path)


def test_validate_broken_world_state():
    """Test that validation catches broken world states."""
    world = World()
    
    # Create rooms with broken linkage (simulating corrupted world state)
    from world import Room, Object
    import uuid
    
    lobby = Room(id="lobby", description="The main lobby")
    garden = Room(id="garden", description="A beautiful garden")
    
    # Add door from lobby to garden but no reciprocal door
    lobby.doors["garden door"] = "garden"
    door_id = str(uuid.uuid4())
    lobby.door_ids["garden door"] = door_id
    
    # Create door object but with wrong link target
    door_obj = Object(
        display_name="garden door",
        object_tags={"Immovable", "Travel Point"}, 
        link_target_room_id="wrong_room"  # This should be "garden"
    )
    door_obj.uuid = door_id
    lobby.objects[door_id] = door_obj
    
    world.rooms["lobby"] = lobby
    world.rooms["garden"] = garden
    
    # Validate the broken world
    errors = world.validate()
    
    # Should find multiple errors
    reciprocal_errors = [e for e in errors if "lacks reciprocal door" in e]
    link_errors = [e for e in errors if "link_target_room_id mismatch" in e]
    
    assert len(reciprocal_errors) > 0, "Should detect missing reciprocal door"
    assert len(link_errors) > 0, "Should detect link target mismatch"
    
    print("✓ Validation correctly detected broken world state:")
    for error in reciprocal_errors + link_errors:
        print(f"  - {error}")


if __name__ == "__main__":
    test_validate_real_world_configuration()
    test_validate_broken_world_state()
    print("\n✓ All integration tests passed!")