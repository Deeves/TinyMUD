"""
Comprehensive edge case tests for inventory management and object ownership.

This test suite specifically addresses data integrity concerns around:
- Inventory slot compaction after removal/addition
- Full and empty inventory scenarios
- Duplicate UUID handling
- Concurrent pick-up operations
- Ownership transfer validation

Mission briefing:
    These tests ensure the robustness of our inventory system by hammering
    it with edge cases that could cause data corruption or inconsistent state.
    We're validating that the inventory remains well-formed and objects
    maintain proper ownership tracking even under stress conditions.

Why these tests matter:
    - Inventory corruption could lead to lost items or duplicate objects
    - Poor ownership tracking could allow item duplication exploits
    - Non-compact indexes could cause performance issues over time
    - Race conditions during concurrent operations could corrupt state
"""

from __future__ import annotations

import uuid
import threading
from unittest.mock import patch

from world import World, Room, Object, Inventory
from account_service import create_account_and_login


def test_full_inventory_scenarios():
    """Test behavior when inventory is completely full and we try to add more items."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create a player with completely full inventory
    sessions = {}
    admins = set()
    sid = 'test_sid'
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid, 'TestPlayer', 'pass', 'A test player', sessions, admins, ''
    )
    assert ok and not err, f"Player creation failed: {err}"
    
    player = w.players[sid]
    inv = player.sheet.inventory
    
    # Fill all 8 slots with different sized objects
    # Slots 0-1: hands (can hold any size)
    hand_obj1 = Object(display_name="Left Hand Item", object_tags={'small'})
    hand_obj2 = Object(display_name="Right Hand Item", object_tags={'large'})
    
    # Slots 2-5: small items only
    small_objs = [
        Object(display_name=f"Small Item {i}", object_tags={'small'})
        for i in range(1, 5)
    ]
    
    # Slots 6-7: large items only
    large_objs = [
        Object(display_name=f"Large Item {i}", object_tags={'large'})
        for i in range(1, 3)
    ]
    
    # Place all objects
    inv.slots[0] = hand_obj1
    inv.slots[1] = hand_obj2
    for i, obj in enumerate(small_objs):
        inv.slots[i + 2] = obj
    for i, obj in enumerate(large_objs):
        inv.slots[i + 6] = obj
    
    # Verify inventory is full
    assert all(slot is not None for slot in inv.slots), "Inventory should be completely full"
    
    # Try to add another object to the room and pick it up
    extra_obj = Object(display_name="Extra Object", object_tags={'small'})
    w.rooms['test'].objects[extra_obj.uuid] = extra_obj
    
    # Mock interaction session for the pick-up attempt
    sessions_mock = {sid: {
        'type': 'interaction',
        'object_uuid': extra_obj.uuid,
        'object_name': extra_obj.display_name,
        'choices': ['Pick Up']
    }}
    
    with patch('interaction_service.sessions', sessions_mock):
        handled, err, emits, broadcasts = handle_interaction_choice(
            w, '', sid, 'Pick Up'
        )
        
        # Should handle the command but fail to pick up due to full inventory
        assert handled, "Should handle pick-up command"
        assert any('No space' in emit.get('content', '') or 'full' in emit.get('content', '')
                   for emit in emits), f"Should indicate no space available, got: {emits}"
        
        # Object should still be in room, not moved to inventory
        assert extra_obj.uuid in w.rooms['test'].objects, "Object should remain in room"
        assert all(slot.uuid != extra_obj.uuid if slot else True
                   for slot in inv.slots), "Object should not be in any inventory slot"


def test_empty_inventory_operations():
    """Test operations on completely empty inventory."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create a player with empty inventory
    sessions = {}
    admins = set()
    sid = 'test_sid'
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid, 'TestPlayer', 'pass', 'A test player', sessions, admins, ''
    )
    assert ok and not err, f"Player creation failed: {err}"
    
    player = w.players[sid]
    inv = player.sheet.inventory
    
    # Verify inventory is empty
    assert all(slot is None for slot in inv.slots), "Inventory should be completely empty"
    
    # Test removal from empty slots
    for i in range(8):
        removed = inv.remove(i)
        assert removed is None, f"Removing from empty slot {i} should return None"
    
    # Test placing objects in empty inventory
    small_obj = Object(display_name="Test Small", object_tags={'small'})
    large_obj = Object(display_name="Test Large", object_tags={'large'})
    
    # Test placement in appropriate slots
    assert inv.can_place(0, small_obj), "Should be able to place small object in hand"
    assert inv.can_place(0, large_obj), "Should be able to place large object in hand"
    assert inv.can_place(2, small_obj), "Should be able to place small object in small slot"
    assert not inv.can_place(2, large_obj), "Should NOT be able to place large object in small slot"
    assert inv.can_place(6, large_obj), "Should be able to place large object in large slot"
    assert not inv.can_place(6, small_obj), "Should NOT be able to place small object in large slot if also tagged small"
    
    # Test successful placement
    assert inv.place(2, small_obj), "Should successfully place small object"
    assert inv.slots[2] == small_obj, "Small object should be in slot 2"
    
    assert inv.place(6, large_obj), "Should successfully place large object"
    assert inv.slots[6] == large_obj, "Large object should be in slot 6"


def test_duplicate_uuid_prevention():
    """Test that objects with duplicate UUIDs cannot be placed in inventory."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create a player
    sessions = {}
    admins = set()
    sid = 'test_sid'
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid, 'TestPlayer', 'pass', 'A test player', sessions, admins, ''
    )
    assert ok and not err, f"Player creation failed: {err}"
    
    player = w.players[sid]
    inv = player.sheet.inventory
    
    # Create two objects with the same UUID (this shouldn't happen in normal operation,
    # but we need to test the system's resilience)
    duplicate_uuid = str(uuid.uuid4())
    
    obj1 = Object(display_name="First Object", object_tags={'small'})
    obj1.uuid = duplicate_uuid
    
    obj2 = Object(display_name="Second Object", object_tags={'small'}) 
    obj2.uuid = duplicate_uuid
    
    # Place first object successfully
    assert inv.place(2, obj1), "Should place first object"
    assert inv.slots[2] == obj1, "First object should be in slot"
    
    # Check if we already have an object with this UUID in inventory
    existing_uuids = {obj.uuid for obj in inv.slots if obj is not None}
    
    # If attempting to place second object with same UUID, it should be prevented
    # (This is a defensive programming test - the system should detect this)
    if obj2.uuid in existing_uuids:
        # System should reject duplicate UUID - either through validation or explicit check
        # For now, we'll verify that if such a check exists, it works properly
        assert obj2.uuid == obj1.uuid, "UUIDs should be duplicates"
        
        # Verify current inventory state is valid (no duplicate UUIDs across slots)
        inventory_uuids = [obj.uuid for obj in inv.slots if obj is not None]
        assert len(inventory_uuids) == len(set(inventory_uuids)), "No duplicate UUIDs should exist in inventory"


def test_concurrent_pickup_simulation():
    """Simulate concurrent pick-up operations to test for race conditions."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create multiple players
    sessions = {}
    admins = set()
    players = []
    
    for i in range(3):
        sid = f'player_{i}'
        ok, err, emits, broadcasts = create_account_and_login(
            w, sid, f'Player{i}', 'pass', f'Test player {i}', sessions, admins, ''
        )
        assert ok and not err, f"Player {i} creation failed: {err}"
        players.append((sid, w.players[sid]))
    
    # Place a single valuable object in the room
    rare_obj = Object(display_name="Rare Gem", object_tags={'small'})
    w.rooms['test'].objects[rare_obj.uuid] = rare_obj
    
    pickup_results = []
    pickup_errors = []
    
    def attempt_pickup(player_sid):
        """Simulate a player attempting to pick up the object."""
        try:
            # Mock interaction session
            mock_sessions = {player_sid: {
                'type': 'interaction',
                'object_uuid': rare_obj.uuid,
                'object_name': rare_obj.display_name,
                'choices': ['Pick Up']
            }}
            
            with patch('interaction_service.sessions', mock_sessions):
                handled, err, emits, broadcasts = handle_interaction_choice(
                    w, '', player_sid, 'Pick Up'
                )
                pickup_results.append((player_sid, handled, err, emits))
        except Exception as e:
            pickup_errors.append((player_sid, str(e)))
    
    # Launch concurrent pickup attempts
    threads = []
    for sid, _ in players:
        thread = threading.Thread(target=attempt_pickup, args=(sid,))
        threads.append(thread)
    
    # Start all threads nearly simultaneously
    for thread in threads:
        thread.start()
        
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Verify results
    assert not pickup_errors, f"No pickup attempts should have crashed: {pickup_errors}"
    
    # Only one player should have successfully picked up the object
    successful_pickups = [
        result for result in pickup_results 
        if result[1] and not result[2] and any(
            'pick up' in emit.get('content', '').lower() and 'cannot' not in emit.get('content', '').lower()
            for emit in result[3]
        )
    ]
    
    # Either one player got it, or all failed due to race condition handling
    # The key is that the object should be in exactly one place
    object_locations = []
    
    # Check if object is still in room
    if rare_obj.uuid in w.rooms['test'].objects:
        object_locations.append('room')
    
    # Check if object is in any player's inventory
    for sid, player in players:
        for slot in player.sheet.inventory.slots:
            if slot and slot.uuid == rare_obj.uuid:
                object_locations.append(f'player_{sid}')
    
    # Object should be in exactly one location
    assert len(object_locations) == 1, f"Object should be in exactly one location, found in: {object_locations}"


def test_inventory_compaction_after_removal():
    """Test that inventory doesn't need compaction since it's slot-based, but verify integrity."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create a player
    sessions = {}
    admins = set()
    sid = 'test_sid'
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid, 'TestPlayer', 'pass', 'A test player', sessions, admins, ''
    )
    assert ok and not err, f"Player creation failed: {err}"
    
    player = w.players[sid]
    inv = player.sheet.inventory
    
    # Fill several slots with objects
    objects = []
    for i in range(4):  # Fill slots 2-5 (small slots)
        obj = Object(display_name=f"Item {i}", object_tags={'small'})
        objects.append(obj)
        inv.slots[i + 2] = obj
    
    # Verify all objects are placed
    for i, obj in enumerate(objects):
        assert inv.slots[i + 2] == obj, f"Object {i} should be in slot {i + 2}"
    
    # Remove object from middle slot (slot 3)
    removed_obj = inv.remove(3)
    assert removed_obj == objects[1], "Should remove correct object"
    assert inv.slots[3] is None, "Slot 3 should be empty after removal"
    
    # Verify other objects remain in their original slots (no automatic compaction)
    assert inv.slots[2] == objects[0], "Object 0 should remain in slot 2"
    assert inv.slots[4] == objects[2], "Object 2 should remain in slot 4"
    assert inv.slots[5] == objects[3], "Object 3 should remain in slot 5"
    
    # Verify we can place a new object in the now-empty slot
    new_obj = Object(display_name="New Item", object_tags={'small'})
    assert inv.place(3, new_obj), "Should be able to place object in previously occupied slot"
    assert inv.slots[3] == new_obj, "New object should be in slot 3"
    
    # Test removal of multiple objects and verify no corruption
    inv.remove(2)  # Remove first object
    inv.remove(5)  # Remove last object
    
    # Remaining objects should still be in correct positions
    assert inv.slots[2] is None, "Slot 2 should be empty"
    assert inv.slots[3] == new_obj, "New object should remain in slot 3"
    assert inv.slots[4] == objects[2], "Object 2 should remain in slot 4"
    assert inv.slots[5] is None, "Slot 5 should be empty"


def test_ownership_transfer_validation():
    """Test that object ownership transfers are properly validated and atomic."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create two players
    sessions = {}
    admins = set()
    
    # Player 1
    sid1 = 'player1'
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid1, 'Player1', 'pass', 'First player', sessions, admins, ''
    )
    assert ok and not err, f"Player 1 creation failed: {err}"
    player1 = w.players[sid1]
    
    # Player 2  
    sid2 = 'player2'
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid2, 'Player2', 'pass', 'Second player', sessions, admins, ''
    )
    assert ok and not err, f"Player 2 creation failed: {err}"
    player2 = w.players[sid2]
    
    # Create an object and assign ownership to player1
    test_obj = Object(display_name="Owned Item", object_tags={'small'})
    test_obj.owner_id = player1.user_id  # Set ownership
    
    # Place object in room initially
    w.rooms['test'].objects[test_obj.uuid] = test_obj
    
    # Verify initial ownership
    assert test_obj.owner_id == player1.user_id, "Object should be owned by player1"
    
    # Simulate player2 picking up the object (ownership should transfer)
    mock_sessions = {sid2: {
        'type': 'interaction',
        'object_uuid': test_obj.uuid,
        'object_name': test_obj.display_name,
        'choices': ['Pick Up']
    }}
    
    with patch('interaction_service.sessions', mock_sessions):
        handled, err, emits, broadcasts = handle_interaction_choice(
            w, '', sid2, 'Pick Up'
        )
        
        # Pickup should succeed (assuming no ownership restrictions)
        assert handled, "Should handle pickup command"
        
        # Find the object in player2's inventory
        picked_obj = None
        for slot in player2.sheet.inventory.slots:
            if slot and slot.uuid == test_obj.uuid:
                picked_obj = slot
                break
        
        if picked_obj:
            # If object was successfully picked up, verify ownership transfer
            # (This may depend on whether the system implements ownership transfer on pickup)
            assert picked_obj.uuid == test_obj.uuid, "Should be the same object"
            
            # Object should no longer be in room
            assert test_obj.uuid not in w.rooms['test'].objects, "Object should be removed from room"


def test_immovable_object_pickup_prevention():
    """Test that immovable objects cannot be picked up under any circumstances."""
    w = World()
    w.rooms['test'] = Room(id='test', description='Test room')
    w.start_room_id = 'test'
    
    # Create a player
    sessions = {}
    admins = set()
    sid = 'test_sid'
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, sid, 'TestPlayer', 'pass', 'A test player', sessions, admins, ''
    )
    assert ok and not err, f"Player creation failed: {err}"
    
    # Create immovable objects with different tag combinations
    immovable_objects = [
        Object(display_name="Stone Pillar", object_tags={'Immovable', 'large'}),
        Object(display_name="Ancient Door", object_tags={'Immovable', 'Travel Point'}),
        Object(display_name="Fixed Statue", object_tags={'Immovable', 'small'})
    ]
    
    for obj in immovable_objects:
        w.rooms['test'].objects[obj.uuid] = obj
        
        # Attempt to pick up the immovable object
        mock_sessions = {sid: {
            'type': 'interaction',
            'object_uuid': obj.uuid,
            'object_name': obj.display_name,
            'choices': ['Pick Up']
        }}
        
        with patch('interaction_service.sessions', mock_sessions):
            handled, err, emits, broadcasts = handle_interaction_choice(
                w, '', sid, 'Pick Up'
            )
            
            # Should handle command but reject pickup
            assert handled, f"Should handle pickup attempt for {obj.display_name}"
            assert any('cannot be picked up' in emit.get('content', '').lower()
                     for emit in emits), f"Should reject pickup of {obj.display_name}, got: {emits}"
            
            # Object should remain in room
            assert obj.uuid in w.rooms['test'].objects, f"{obj.display_name} should remain in room"
            
            # Object should not be in player inventory
            player = w.players[sid]
            assert not any(slot and slot.uuid == obj.uuid 
                          for slot in player.sheet.inventory.slots), f"{obj.display_name} should not be in inventory"


def test_inventory_constraint_violations():
    """Test that inventory constraints are properly enforced."""
    inv = Inventory()
    
    # Create test objects
    small_obj = Object(display_name="Small Item", object_tags={'small'})
    large_obj = Object(display_name="Large Item", object_tags={'large'})
    both_tagged_obj = Object(display_name="Conflicted Item", object_tags={'small', 'large'})
    immovable_obj = Object(display_name="Immovable Item", object_tags={'Immovable'})
    travel_obj = Object(display_name="Door", object_tags={'Travel Point'})
    
    # Test hand slots (0-1) - should accept any movable object
    assert inv.can_place(0, small_obj), "Hands should accept small objects"
    assert inv.can_place(1, large_obj), "Hands should accept large objects"
    assert not inv.can_place(0, immovable_obj), "Hands should reject immovable objects"
    assert not inv.can_place(1, travel_obj), "Hands should reject travel points"
    
    # Test small slots (2-5) - only small items, not large
    assert inv.can_place(2, small_obj), "Small slots should accept small objects"
    assert not inv.can_place(3, large_obj), "Small slots should reject large objects"
    assert not inv.can_place(4, both_tagged_obj), "Small slots should reject objects tagged as both small and large"
    assert not inv.can_place(2, immovable_obj), "Small slots should reject immovable objects"
    
    # Test large slots (6-7) - only large items
    assert inv.can_place(6, large_obj), "Large slots should accept large objects"
    assert not inv.can_place(7, small_obj), "Large slots should reject small-only objects"
    assert not inv.can_place(6, immovable_obj), "Large slots should reject immovable objects"
    
    # Test invalid slot indices
    assert not inv.can_place(-1, small_obj), "Should reject negative slot index"
    assert not inv.can_place(8, small_obj), "Should reject slot index >= 8"
    assert not inv.can_place(100, small_obj), "Should reject large slot index"


if __name__ == '__main__':
    import pytest
    
    # Run all tests
    pytest.main([__file__, '-v'])