"""
Focused inventory integrity tests for object ownership and data consistency.

These tests directly exercise the inventory system and our new utility functions
to ensure data integrity without complex interaction mocking.
"""

from __future__ import annotations

import uuid
from world import World, Room, Object, Inventory
from account_service import create_account_and_login
from inventory_utils import (
    validate_inventory_integrity,
    find_object_in_inventory,
    find_objects_by_name,
    transfer_object_ownership,
    remove_object_safely,
    place_object_safely,
    compact_inventory_references,
    get_inventory_summary
)


def test_inventory_integrity_validation():
    """Test that inventory validation catches common integrity issues."""
    inv = Inventory()
    
    # Test valid empty inventory
    is_valid, errors = validate_inventory_integrity(inv)
    assert is_valid, f"Empty inventory should be valid, got errors: {errors}"
    
    # Test inventory with valid objects
    small_obj = Object(display_name="Small Item", object_tags={'small'})
    large_obj = Object(display_name="Large Item", object_tags={'large'})
    
    inv.slots[2] = small_obj  # Small slot
    inv.slots[6] = large_obj  # Large slot
    
    is_valid, errors = validate_inventory_integrity(inv)
    assert is_valid, f"Valid inventory should pass validation, got errors: {errors}"
    
    # Test constraint violation
    inv.slots[3] = large_obj  # Large object in small slot - should be caught
    is_valid, errors = validate_inventory_integrity(inv)
    assert not is_valid, "Should detect constraint violation"
    assert any("violates constraints" in error for error in errors), \
           f"Should report constraint violation: {errors}"
    
    # Test duplicate UUID detection
    inv.slots[3] = small_obj  # Reset to valid
    duplicate_obj = Object(display_name="Duplicate", object_tags={'small'})
    duplicate_obj.uuid = small_obj.uuid  # Same UUID as slot 2
    inv.slots[4] = duplicate_obj
    
    is_valid, errors = validate_inventory_integrity(inv)
    assert not is_valid, "Should detect duplicate UUID"
    assert any("Duplicate UUID" in error for error in errors), \
           f"Should report duplicate UUID: {errors}"


def test_find_object_functions():
    """Test object finding utilities."""
    inv = Inventory()
    
    # Add some test objects
    obj1 = Object(display_name="Magic Sword", object_tags={'large'})
    obj2 = Object(display_name="Health Potion", object_tags={'small'})
    obj3 = Object(display_name="Health Potion", object_tags={'small'})  # Duplicate name
    
    inv.slots[0] = obj1  # Hand
    inv.slots[2] = obj2  # Small slot
    inv.slots[3] = obj3  # Another small slot
    
    # Test find by UUID
    result = find_object_in_inventory(inv, obj1.uuid)
    assert result is not None, "Should find object by UUID"
    slot_idx, found_obj = result
    assert slot_idx == 0, "Should find object in correct slot"
    assert found_obj == obj1, "Should return correct object"
    
    # Test find non-existent UUID
    fake_uuid = str(uuid.uuid4())
    result = find_object_in_inventory(inv, fake_uuid)
    assert result is None, "Should not find non-existent object"
    
    # Test find by name
    matches = find_objects_by_name(inv, "Health Potion")
    assert len(matches) == 2, "Should find both health potions"
    assert all(obj.display_name == "Health Potion" for _, obj in matches), \
           "All matches should have correct name"
    
    # Test case sensitivity
    matches_case = find_objects_by_name(inv, "health potion", case_sensitive=False)
    assert len(matches_case) == 2, "Should find matches case-insensitively"
    
    matches_case_strict = find_objects_by_name(inv, "health potion", case_sensitive=True)
    assert len(matches_case_strict) == 0, "Should not find matches with strict case"


def test_ownership_transfer():
    """Test atomic ownership transfer functionality."""
    obj = Object(display_name="Test Item", object_tags={'small'})
    obj.owner_id = "original_owner"
    
    # Test successful transfer
    success, error = transfer_object_ownership(obj, "new_owner")
    assert success, f"Ownership transfer should succeed: {error}"
    assert obj.owner_id == "new_owner", "Object should have new owner"
    
    # Test transfer to None (unowned)
    success, error = transfer_object_ownership(obj, None, validate_owner_exists=False)
    assert success, f"Transfer to None should succeed: {error}"
    assert obj.owner_id is None, "Object should be unowned"
    
    # Test invalid owner format
    success, error = transfer_object_ownership(obj, "", validate_owner_exists=True)
    assert not success, "Should reject empty owner ID"
    assert "Invalid owner ID format" in error, f"Should report format error: {error}"


def test_safe_inventory_operations():
    """Test safe inventory placement and removal operations."""
    inv = Inventory()
    
    # Test safe placement
    obj = Object(display_name="Test Item", object_tags={'small'})
    
    # Valid placement
    success, error = place_object_safely(inv, 2, obj)
    assert success, f"Valid placement should succeed: {error}"
    assert inv.slots[2] == obj, "Object should be placed in slot"
    
    # Test placement in occupied slot
    obj2 = Object(display_name="Another Item", object_tags={'small'})
    success, error = place_object_safely(inv, 2, obj2)
    assert not success, "Should reject placement in occupied slot"
    assert "already occupied" in error, f"Should report occupied slot: {error}"
    
    # Test duplicate UUID prevention
    obj_dup = Object(display_name="Duplicate UUID", object_tags={'small'})
    obj_dup.uuid = obj.uuid
    success, error = place_object_safely(inv, 3, obj_dup)
    assert not success, "Should reject duplicate UUID"
    assert "already exists" in error, f"Should report duplicate UUID: {error}"
    
    # Test safe removal
    success, removed, error = remove_object_safely(inv, 2)
    assert success, f"Valid removal should succeed: {error}"
    assert removed == obj, "Should return removed object"
    assert inv.slots[2] is None, "Slot should be empty after removal"
    
    # Test removal from empty slot
    success, removed, error = remove_object_safely(inv, 2)
    assert success, f"Removal from empty slot should succeed: {error}"
    assert removed is None, "Should return None for empty slot"


def test_inventory_compaction_and_cleanup():
    """Test inventory reference cleanup and compaction utilities."""
    # Test with malformed inventory
    inv = Inventory()
    inv.slots = [None] * 6  # Too few slots
    
    fixes, descriptions = compact_inventory_references(inv)
    assert fixes > 0, "Should apply fixes to malformed inventory"
    assert len(inv.slots) == 8, "Should ensure exactly 8 slots"
    assert "Adjusted inventory slots" in " ".join(descriptions), "Should report slot adjustment"
    
    # Test with malformed objects
    inv = Inventory()
    bad_obj = Object(display_name="Test")
    delattr(bad_obj, 'uuid')  # Remove required attribute
    inv.slots[2] = bad_obj
    
    fixes, descriptions = compact_inventory_references(inv)
    assert fixes > 0, "Should fix malformed objects"
    assert inv.slots[2] is None, "Should remove malformed object"
    assert "Removed malformed object" in " ".join(descriptions), "Should report object removal"


def test_inventory_summary_reporting():
    """Test inventory summary and debugging utilities."""
    inv = Inventory()
    
    # Empty inventory summary
    summary = get_inventory_summary(inv)
    assert summary['is_valid'], "Empty inventory should be valid"
    assert summary['total_objects'] == 0, "Should report zero objects"
    assert summary['empty_slots'] == 8, "Should report all slots empty"
    
    # Populated inventory summary
    hand_obj = Object(display_name="Sword", object_tags={'large'})
    small_obj = Object(display_name="Potion", object_tags={'small'})
    large_obj = Object(display_name="Shield", object_tags={'large'})
    
    inv.slots[0] = hand_obj  # Hand slot
    inv.slots[2] = small_obj  # Small slot
    inv.slots[6] = large_obj  # Large slot
    
    summary = get_inventory_summary(inv)
    assert summary['is_valid'], "Valid inventory should be valid"
    assert summary['total_objects'] == 3, "Should count all objects"
    assert summary['hand_objects'] == 1, "Should count hand objects"
    assert summary['small_objects'] == 1, "Should count small objects"
    assert summary['large_objects'] == 1, "Should count large objects"
    assert summary['empty_slots'] == 5, "Should count empty slots"


def test_constraint_enforcement():
    """Test that inventory constraints are properly enforced."""
    inv = Inventory()
    
    # Create test objects with different properties
    small_obj = Object(display_name="Small Item", object_tags={'small'})
    large_obj = Object(display_name="Large Item", object_tags={'large'})
    both_tagged = Object(display_name="Conflicted", object_tags={'small', 'large'})
    immovable_obj = Object(display_name="Pillar", object_tags={'Immovable'})
    travel_obj = Object(display_name="Door", object_tags={'Travel Point'})
    
    # Test hand slots (0-1) accept movable objects
    assert inv.can_place(0, small_obj), "Hand should accept small objects"
    assert inv.can_place(1, large_obj), "Hand should accept large objects"
    assert not inv.can_place(0, immovable_obj), "Hand should reject immovable objects"
    assert not inv.can_place(1, travel_obj), "Hand should reject travel objects"
    
    # Test small slots (2-5) only accept small, not large
    assert inv.can_place(2, small_obj), "Small slot should accept small objects"
    assert not inv.can_place(3, large_obj), "Small slot should reject large objects"
    assert not inv.can_place(4, both_tagged), "Small slot should reject dual-tagged objects"
    
    # Test large slots (6-7) only accept large objects
    assert inv.can_place(6, large_obj), "Large slot should accept large objects"
    assert not inv.can_place(7, small_obj), "Large slot should reject small objects"
    
    # Test invalid slot indices
    assert not inv.can_place(-1, small_obj), "Should reject negative indices"
    assert not inv.can_place(8, small_obj), "Should reject indices >= 8"


def test_real_world_pickup_scenario():
    """Test a realistic pickup scenario with ownership transfer."""
    # Create a world with a room and player
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create player
    sessions = {}
    admins = set()
    sid = 'player1'
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid, 'TestPlayer', 'pass', 'A test player', sessions, admins, ''
    )
    assert ok and not err, f"Player creation failed: {err}"
    
    player = w.players[sid]
    inv = player.sheet.inventory
    
    # Create an object in the room
    room_obj = Object(display_name="Found Treasure", object_tags={'small'})
    room_obj.owner_id = None  # Initially unowned
    w.rooms['test'].objects[room_obj.uuid] = room_obj
    
    # Simulate picking up the object (manual process for testing)
    # Remove from room
    w.rooms['test'].objects.pop(room_obj.uuid)
    
    # Place in inventory with validation
    success, error = place_object_safely(inv, 2, room_obj)
    assert success, f"Should place object in inventory: {error}"
    
    # Get the user_id from sessions (this is how ownership is tracked)
    user_id = sessions[sid]
    
    # Transfer ownership
    success, error = transfer_object_ownership(room_obj, user_id)
    assert success, f"Should transfer ownership: {error}"
    assert room_obj.owner_id == user_id, "Object should be owned by player"
    
    # Validate final state
    is_valid, errors = validate_inventory_integrity(inv)
    assert is_valid, f"Final inventory should be valid: {errors}"
    
    # Object should not be in room anymore
    assert room_obj.uuid not in w.rooms['test'].objects, "Object should not be in room"
    
    # Object should be in player inventory
    found = find_object_in_inventory(inv, room_obj.uuid)
    assert found is not None, "Object should be in inventory"
    slot_idx, found_obj = found
    assert found_obj == room_obj, "Should find the correct object"
    assert slot_idx == 2, "Should be in the expected slot"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])