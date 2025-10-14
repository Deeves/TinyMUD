"""Data integrity tests for relationship-based door permissions.

This module contains negative tests to ensure data integrity and robustness
around relationship-based door traversal rules, particularly focusing on:
- Revoked relationships after caching
- Corrupted or malformed relationship data
- Missing users referenced in permissions
- Race conditions and edge cases

Run with:
  python -m pytest server/test_relationship_door_integrity.py -v

These tests help ensure the system gracefully handles data corruption,
user deletions, and relationship changes without compromising security.
"""

import tempfile
from world import World, Room
from account_service import create_account_and_login
from movement_service import move_through_door
from room_service import handle_room_command


def create_tmpfile():
    """Helper to create a temporary file for world persistence tests."""
    fd, path = tempfile.mkstemp(suffix='.json')
    import os
    os.close(fd)
    return path


def setup_world_with_locked_door():
    """Set up a world with two users and a relationship-locked door.

    Returns:
        tuple: (world, alice_sid, bob_sid, tmpfile_path, alice_uid, bob_uid)
    """
    tmpfile = create_tmpfile()
    w = World()

    # Create rooms and door
    w.rooms['start'] = Room(id='start', description='Start Room')
    w.rooms['hall'] = Room(id='hall', description='Hall')
    w.rooms['start'].doors['oak door'] = 'hall'
    w.start_room_id = 'start'

    # Create two users
    sessions = {}
    admins = set()

    alice_sid = 'alice_sid'
    ok1, err1, _, _ = create_account_and_login(
        w, alice_sid, 'Alice', 'pw1', 'Alice desc', sessions, admins, tmpfile)
    assert ok1 and not err1, f"Failed to create Alice: {err1}"

    bob_sid = 'bob_sid'
    ok2, err2, _, _ = create_account_and_login(
        w, bob_sid, 'Bob', 'pw2', 'Bob desc', sessions, admins, tmpfile)
    assert ok2 and not err2, f"Failed to create Bob: {err2}"

    # Get user IDs for relationship setup
    alice_uid = next(
        uid for uid, u in w.users.items() if u.display_name == 'Alice')
    bob_uid = next(
        uid for uid, u in w.users.items() if u.display_name == 'Bob')

    return w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid


class TestRevokedRelationships:
    """Tests for scenarios where relationships are revoked after door locks are established."""
    
    def test_revoked_relationship_denies_access(self):
        """Test that revoking a relationship immediately prevents door access."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Establish relationship: Bob is Alice's friend
        w.relationships = w.relationships or {}
        w.relationships.setdefault(bob_uid, {})[alice_uid] = 'friend'
        
        # Lock door to require 'friend' relationship with Alice
        handled, err, _, _ = handle_room_command(
            w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        assert handled and not err, f"Failed to lock door: {err}"
        
        # Bob should be able to pass initially
        ok1, err1, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert ok1 and not err1, f"Bob should pass initially: {err1}"
        
        # Move Bob back to start
        w.move_player(bob_sid, 'start')
        
        # Revoke the relationship
        del w.relationships[bob_uid][alice_uid]
        
        # Bob should now be denied access
        ok2, err2, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok2, "Bob should be denied after relationship revoked"
        assert err2 and 'locked' in err2.lower(), f"Expected lock error, got: {err2}"
    
    def test_partial_relationship_cleanup(self):
        """Test behavior when relationships are partially cleaned up."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Set up relationships
        w.relationships = {
            bob_uid: {alice_uid: 'friend'},
            alice_uid: {bob_uid: 'ally'}  # Mutual relationships
        }
        
        # Lock door requiring friend relationship
        handle_room_command(
            w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Clear all of Bob's relationships but leave Alice's intact
        w.relationships[bob_uid] = {}
        
        # Bob should be denied
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()
    
    def test_empty_relationships_dict(self):
        """Test behavior when relationships dict becomes empty."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()

        # Set up relationship and lock
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        _, _, _, _ = handle_room_command(
            w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Clear entire relationships dict
        w.relationships = {}
        
        # Bob should be denied
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()


class TestCorruptedRelationshipData:
    """Tests for handling malformed or corrupted relationship data."""
    
    def test_none_relationships_dict(self):
        """Test behavior when relationships dict is None."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Set up valid relationship and lock
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        handle_room_command(
            w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Corrupt relationships to None
        w.relationships = None
        
        # Should deny access gracefully
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()
    
    def test_malformed_relationship_values(self):
        """Test handling of non-string relationship values."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Lock door first
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Set malformed relationship values
        test_cases = [
            None,           # None value
            42,             # Integer  
            ['friend'],     # List
            {'type': 'friend'},  # Dict
            '',             # Empty string
            '  ',           # Whitespace only
        ]
        
        for bad_value in test_cases:
            w.relationships = {bob_uid: {alice_uid: bad_value}}
            
            ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
            assert not ok, f"Should deny access with malformed value: {bad_value}"
            assert err and 'locked' in err.lower()
    
    def test_non_dict_relationship_structure(self):
        """Test handling when relationship structure is not a dict."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Test various non-dict structures
        bad_structures = [
            'not_a_dict',
            ['list', 'of', 'values'], 
            42,
            True,
        ]
        
        for bad_struct in bad_structures:
            w.relationships = {bob_uid: bad_struct}
            
            ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
            assert not ok, f"Should deny access with bad structure: {type(bad_struct)}"


class TestMissingUserIntegrity:
    """Tests for handling missing or deleted users referenced in permissions."""
    
    def test_deleted_user_in_relationship_target(self):
        """Test behavior when target user in relationship is deleted."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Set up relationship and lock
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Delete Alice's user account but leave relationship intact  
        del w.users[alice_uid]
        
        # Bob should be denied (relationship target doesn't exist)
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()
    
    def test_deleted_user_with_active_relationships(self):
        """Test behavior when user with relationships is deleted."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Set up relationship and lock
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Delete Bob's user account but leave player and relationships
        del w.users[bob_uid]
        
        # Bob should be denied (can't resolve actor_uid)
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()
    
    def test_orphaned_relationship_references(self):
        """Test relationships pointing to non-existent user IDs."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Create relationship to non-existent user
        fake_uid = 'nonexistent_user_id'
        w.relationships = {bob_uid: {fake_uid: 'friend'}}
        
        # Should be denied (no valid relationship to Alice)
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()


class TestDoorLockIntegrity:
    """Tests for door lock data integrity and edge cases."""
    
    def test_corrupted_door_lock_policy(self):
        """Test handling of corrupted door lock policy data."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Set up valid relationship
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        
        # Manually corrupt the door lock policy
        room = w.rooms['start']
        room.door_locks = room.door_locks or {}
        
        # Test various corrupted policy structures
        corrupted_policies = [
            None,                           # None policy
            'not_a_dict',                  # Non-dict policy
            {'allow_rel': 'not_a_list'},   # Non-list allow_rel
            {'allow_rel': [None]},         # None rule in list
            {'allow_rel': [{'type': None, 'to': alice_uid}]},  # None type
            {'allow_rel': [{'type': 'friend', 'to': None}]},   # None target
            {'allow_rel': [{'type': '', 'to': alice_uid}]},    # Empty type
        ]
        
        for policy in corrupted_policies:
            room.door_locks['oak door'] = policy
            
            ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
            assert not ok, f"Should deny access with corrupted policy: {policy}"
            assert err and 'locked' in err.lower()
    
    def test_missing_door_lock_keys(self):
        """Test behavior when door lock policy is missing expected keys."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        room = w.rooms['start']
        room.door_locks = {'oak door': {}}  # Empty policy
        
        # Should deny access (no allow_ids or allow_rel)
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()
    
    def test_door_locks_attribute_missing(self):
        """Test behavior when door_locks attribute doesn't exist on room."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Remove door_locks attribute entirely
        room = w.rooms['start'] 
        if hasattr(room, 'door_locks'):
            delattr(room, 'door_locks')
        
        # Should allow access (no locks configured)
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert ok and not err, "Should allow access when no door_locks exist"


class TestActorResolutionEdgeCases:
    """Tests for edge cases in actor UID resolution during permission checking."""
    
    def test_player_without_user_reference(self):
        """Test behavior when player exists but has no matching user.""" 
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Set up lock requiring relationship
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # Break the player->user sheet reference
        bob_player = w.players[bob_sid]
        bob_player.sheet = None  # Remove sheet reference
        
        # Should deny access (can't resolve actor_uid)
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        assert not ok and err and 'locked' in err.lower()
    
    def test_multiple_users_same_sheet(self):
        """Test behavior when multiple users share the same sheet object."""
        w, alice_sid, bob_sid, tmpfile, alice_uid, bob_uid = setup_world_with_locked_door()
        
        # Create a third user with the same sheet as Bob (edge case)
        charlie_uid = 'charlie_uid'
        bob_user = w.users[bob_uid]
        w.users[charlie_uid] = bob_user  # Same user object
        
        # Set up relationship and lock
        w.relationships = {bob_uid: {alice_uid: 'friend'}}
        handle_room_command(w, tmpfile,
            ['lockdoor', 'oak door|relationship: friend with Alice'], alice_sid)
        
        # The first matching user should be used for actor_uid
        ok, err, _, _ = move_through_door(w, bob_sid, 'oak door')
        # Should work if the first match has the valid relationship
        # (Implementation detail - depends on dict iteration order)


def test_comprehensive_relationship_scenarios():
    """Integration test covering multiple integrity scenarios together."""
    tmpfile = create_tmpfile()
    w = World()
    
    # Set up world with multiple rooms and users
    w.rooms['lobby'] = Room(id='lobby', description='Lobby')
    w.rooms['vip'] = Room(id='vip', description='VIP Room')  
    w.rooms['admin'] = Room(id='admin', description='Admin Room')
    w.rooms['lobby'].doors['vip door'] = 'vip'
    w.rooms['lobby'].doors['admin door'] = 'admin'
    w.start_room_id = 'lobby'
    
    # Create multiple users with complex relationships
    sessions = {}
    admins = set()
    
    users_data = [
        ('alice_sid', 'Alice', 'Admin user'),
        ('bob_sid', 'Bob', 'Regular user'), 
        ('charlie_sid', 'Charlie', 'VIP user'),
        ('dave_sid', 'Dave', 'Guest user'),
    ]
    
    user_sids = {}
    user_uids = {}
    
    for sid, name, desc in users_data:
        ok, err, _, _ = create_account_and_login(w, sid, name, 'pw', desc, sessions, admins, tmpfile)
        assert ok and not err, f"Failed to create {name}: {err}"
        
        user_sids[name] = sid
        user_uids[name] = next(uid for uid, u in w.users.items() if u.display_name == name)
    
    # Set up complex relationship network
    w.relationships = {
        user_uids['Bob']: {user_uids['Alice']: 'friend'},
        user_uids['Charlie']: {user_uids['Alice']: 'vip_member'},
        user_uids['Dave']: {user_uids['Bob']: 'acquaintance'},
        user_uids['Alice']: {user_uids['Charlie']: 'admin_trust'},
    }
    
    # Lock VIP door to require vip_member relationship with Alice
    handle_room_command(w, tmpfile,
        ['lockdoor', 'vip door|relationship: vip_member with Alice'], user_sids['Alice'])
    
    # Lock admin door to require admin_trust from Alice
    handle_room_command(w, tmpfile, 
        ['lockdoor', 'admin door|relationship: admin_trust from Alice'], user_sids['Alice'])
    
    # Test various scenarios:
    
    # 1. Charlie should access VIP (has vip_member -> Alice)
    ok, err, _, _ = move_through_door(w, user_sids['Charlie'], 'vip door')
    assert ok and not err, f"Charlie should access VIP: {err}"
    
    # 2. Bob should not access VIP (has friend, not vip_member)
    ok, err, _, _ = move_through_door(w, user_sids['Bob'], 'vip door')
    assert not ok and err and 'locked' in err.lower()
    
    # 3. Revoke Charlie's VIP status
    del w.relationships[user_uids['Charlie']][user_uids['Alice']]
    w.move_player(user_sids['Charlie'], 'lobby')  # Move back
    
    # 4. Charlie should now be denied VIP access
    ok, err, _, _ = move_through_door(w, user_sids['Charlie'], 'vip door')
    assert not ok and err and 'locked' in err.lower()
    
    # 5. Delete a user and test orphaned relationships
    del w.users[user_uids['Dave']]
    # Dave's relationships should not affect other users
    
    # Clean up
    import os
    os.unlink(tmpfile)


if __name__ == '__main__':
    # Run basic smoke test
    test_comprehensive_relationship_scenarios()
    print("✓ Basic relationship integrity tests passed")
    
    # Individual test classes would be run via pytest
    print("Run full test suite with: python -m pytest server/test_relationship_door_integrity.py -v")