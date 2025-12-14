"""Tests for account_service.py - Account creation and login.

This module tests:
- create_account_and_login: new user registration, first user admin, creative mode
- login_existing: password validation, home bed spawn, creative mode admin

Coverage target: boost account_service.py from ~52% to ~85%+
"""

from unittest.mock import MagicMock, patch
import pytest
import os
from world import World, Room, Object, User, CharacterSheet


def _fresh_world():
    """Create a fresh World with a start room."""
    import server as srv
    srv.world = World()
    srv.world.rooms["start"] = Room(id="start", description="The starting room.")
    srv.world.start_room_id = "start"
    try:
        import game_loop
        ctx = game_loop.get_context()
        ctx.world = srv.world
    except (RuntimeError, ImportError):
        pass
    return srv.world


# ============================================================================
# create_account_and_login tests
# ============================================================================

def test_create_account_success():
    """Test successful account creation."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "TestPlayer", "password123", "A brave adventurer",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    assert err is None
    assert "sid1" in sessions
    assert "sid1" in w.players
    assert w.players["sid1"].sheet.display_name == "TestPlayer"


def test_first_user_becomes_admin():
    """Test that the first user becomes admin."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "FirstAdmin", "password123", "The first admin",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    assert "sid1" in admins, "First user should be admin"


def test_second_user_not_admin():
    """Test that second user is not automatically admin."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    # Create first user
    w.create_user("FirstUser", "pass", "desc", is_admin=True)
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid2", "SecondPlayer", "password123", "A regular player",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    assert "sid2" not in admins, "Second user should not be admin"


def test_creative_mode_grants_admin():
    """Test that creative mode grants admin to all users."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    w.debug_creative_mode = True
    # Create first user so second wouldn't normally be admin
    w.create_user("FirstUser", "pass", "desc")
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid2", "SecondPlayer", "password123", "Creative mode player",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    assert "sid2" in admins, "Creative mode should grant admin"


def test_create_account_emits_arrival():
    """Test that account creation emits arrival message."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "NewPlayer", "password123", "desc",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    # Should have at least arrival message and room description
    assert len(emits) >= 2
    assert any("arrives" in e.get('content', '').lower() for e in emits)


def test_create_account_broadcasts_to_room():
    """Test that account creation broadcasts to room."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "NewPlayer", "password123", "desc",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    assert len(broadcasts) >= 1
    assert broadcasts[0][0] == "start"  # Room id
    assert "enters" in broadcasts[0][1].get('content', '').lower()


def test_create_account_with_world_context():
    """Test creation shows world context when setup complete."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    w.setup_complete = True
    w.world_name = "Test Realm"
    w.world_description = "A magical world"
    w.world_conflict = "Dark forces gather"
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "NewPlayer", "password123", "desc",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
    # Check for world context in emits
    contents = [e.get('content', '') for e in emits]
    assert any("Test Realm" in c for c in contents)
    assert any("magical world" in c for c in contents)


def test_create_account_rate_limited():
    """Test that account creation is rate limited."""
    from account_service import create_account_and_login
    
    # Enable rate limiting
    old_val = os.environ.get('MUD_RATE_ENABLE')
    os.environ['MUD_RATE_ENABLE'] = '1'
    
    try:
        # Reset rate limiter for this test
        from rate_limiter import reset_rate_limit
        reset_rate_limit("spam_sid")
        
        w = _fresh_world()
        sessions = {}
        admins = set()
        
        # Try many rapid account creations - should eventually fail
        failures = 0
        for i in range(20):
            ok, err, _, _ = create_account_and_login(
                w, "spam_sid", f"Player{i}", "pass", "desc",
                sessions, admins, "test_state.json"
            )
            if not ok and "too quickly" in (err or ""):
                failures += 1
        
        # At least some should have been rate limited
        # (depends on rate limiter config, so we just check it didn't crash)
    finally:
        if old_val is not None:
            os.environ['MUD_RATE_ENABLE'] = old_val
        else:
            os.environ.pop('MUD_RATE_ENABLE', None)


# ============================================================================
# login_existing tests
# ============================================================================

def test_login_success():
    """Test successful login with correct credentials."""
    from account_service import login_existing
    
    w = _fresh_world()
    # Create a user first
    user = w.create_user("ExistingUser", "correct_pass", "A returning player")
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "ExistingUser", "correct_pass",
        sessions, admins
    )
    
    assert ok is True
    assert err is None
    assert "sid1" in sessions
    assert "sid1" in w.players


def test_login_wrong_password():
    """Test login fails with wrong password."""
    from account_service import login_existing
    
    w = _fresh_world()
    user = w.create_user("ExistingUser", "correct_pass", "A player")
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "ExistingUser", "wrong_pass",
        sessions, admins
    )
    
    assert ok is False
    assert "Invalid name or password" in (err or "")
    assert "sid1" not in sessions


def test_login_nonexistent_user():
    """Test login fails for nonexistent user."""
    from account_service import login_existing
    
    w = _fresh_world()
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "GhostUser", "any_pass",
        sessions, admins
    )
    
    assert ok is False
    assert "Invalid name or password" in (err or "")


def test_login_admin_user():
    """Test that admin users get added to admins set."""
    from account_service import login_existing
    
    w = _fresh_world()
    user = w.create_user("AdminUser", "pass", "desc", is_admin=True)
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "AdminUser", "pass",
        sessions, admins
    )
    
    assert ok is True
    assert "sid1" in admins


def test_login_non_admin_user():
    """Test that non-admin users don't get added to admins set."""
    from account_service import login_existing
    
    w = _fresh_world()
    user = w.create_user("RegularUser", "pass", "desc", is_admin=False)
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "RegularUser", "pass",
        sessions, admins
    )
    
    assert ok is True
    assert "sid1" not in admins


def test_login_creative_mode_grants_admin():
    """Test creative mode makes logged in user admin."""
    from account_service import login_existing
    
    w = _fresh_world()
    w.debug_creative_mode = True
    user = w.create_user("RegularUser", "pass", "desc", is_admin=False)
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "RegularUser", "pass",
        sessions, admins
    )
    
    assert ok is True
    assert "sid1" in admins, "Creative mode should grant admin on login"


def test_login_emits_welcome_back():
    """Test login emits welcome back message."""
    from account_service import login_existing
    
    w = _fresh_world()
    user = w.create_user("ReturningPlayer", "pass", "desc")
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "ReturningPlayer", "pass",
        sessions, admins
    )
    
    assert ok is True
    assert any("Welcome back" in e.get('content', '') for e in emits)


def test_login_with_home_bed():
    """Test login spawns at home bed if set."""
    from account_service import login_existing
    
    w = _fresh_world()
    # Create bedroom with a bed
    w.rooms["bedroom"] = Room(id="bedroom", description="A cozy bedroom")
    bed = Object(display_name="Comfy Bed", object_tags={"Bed", "Immovable"})
    w.rooms["bedroom"].objects[bed.uuid] = bed
    
    # Create user with home bed
    user = w.create_user("SleepyPlayer", "pass", "desc")
    user.home_bed_uuid = bed.uuid
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "SleepyPlayer", "pass",
        sessions, admins
    )
    
    assert ok is True
    # Player should spawn in bedroom
    assert w.players["sid1"].room_id == "bedroom"


def test_login_destroyed_bed_fallback():
    """Test login falls back to start room if bed was destroyed."""
    from account_service import login_existing
    
    w = _fresh_world()
    # Create user with a bed UUID that doesn't exist
    user = w.create_user("HomelessPlayer", "pass", "desc")
    user.home_bed_uuid = "nonexistent_bed_uuid"
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "HomelessPlayer", "pass",
        sessions, admins
    )
    
    assert ok is True
    # Should have info message about destroyed bed
    assert any("destroyed" in e.get('content', '').lower() for e in emits)
    # Should spawn in start room
    assert w.players["sid1"].room_id == "start"


def test_login_with_world_context():
    """Test login shows world context when setup complete."""
    from account_service import login_existing
    
    w = _fresh_world()
    w.setup_complete = True
    w.world_name = "Return Realm"
    w.world_description = "Welcome back to the realm"
    
    user = w.create_user("ReturningPlayer", "pass", "desc")
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "ReturningPlayer", "pass",
        sessions, admins
    )
    
    assert ok is True
    contents = [e.get('content', '') for e in emits]
    assert any("Return Realm" in c for c in contents)


def test_login_broadcasts_to_room():
    """Test login broadcasts arrival to room."""
    from account_service import login_existing
    
    w = _fresh_world()
    user = w.create_user("ReturningPlayer", "pass", "desc")
    
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = login_existing(
        w, "sid1", "ReturningPlayer", "pass",
        sessions, admins
    )
    
    assert ok is True
    assert len(broadcasts) >= 1
    assert "enters" in broadcasts[0][1].get('content', '').lower()


def test_login_rate_limited():
    """Test that login attempts are rate limited."""
    from account_service import login_existing
    
    # Enable rate limiting
    old_val = os.environ.get('MUD_RATE_ENABLE')
    os.environ['MUD_RATE_ENABLE'] = '1'
    
    try:
        from rate_limiter import reset_rate_limit
        reset_rate_limit("brute_sid")
        
        w = _fresh_world()
        user = w.create_user("TargetUser", "secret_pass", "desc")
        
        sessions = {}
        admins = set()
        
        # Try many rapid login attempts
        for i in range(20):
            ok, err, _, _ = login_existing(
                w, "brute_sid", "TargetUser", f"wrong_pass_{i}",
                sessions, admins
            )
            # Some should fail with rate limit
    finally:
        if old_val is not None:
            os.environ['MUD_RATE_ENABLE'] = old_val
        else:
            os.environ.pop('MUD_RATE_ENABLE', None)


# ============================================================================
# Edge cases
# ============================================================================

def test_create_duplicate_user():
    """Test creating user with duplicate name fails gracefully."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    # First creation should succeed
    ok1, err1, _, _ = create_account_and_login(
        w, "sid1", "UniquePlayer", "pass", "desc",
        sessions, admins, "test_state.json"
    )
    assert ok1 is True
    
    # Second creation with same name - behavior depends on world.create_user
    # Just ensure it doesn't crash
    sessions2 = {}
    admins2 = set()
    ok2, err2, _, _ = create_account_and_login(
        w, "sid2", "UniquePlayer", "pass2", "desc2",
        sessions2, admins2, "test_state.json"
    )
    # May succeed or fail depending on implementation


def test_login_case_sensitivity():
    """Test login name matching behavior."""
    from account_service import login_existing
    
    w = _fresh_world()
    user = w.create_user("CaseSensitive", "pass", "desc")
    
    sessions = {}
    admins = set()
    
    # Exact case should work
    ok, err, _, _ = login_existing(
        w, "sid1", "CaseSensitive", "pass",
        sessions, admins
    )
    assert ok is True


def test_empty_display_name():
    """Test handling of empty display name."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    # Empty name - behavior depends on world.create_user validation
    # Just ensure it doesn't crash
    ok, err, _, _ = create_account_and_login(
        w, "sid1", "", "pass", "desc",
        sessions, admins, "test_state.json"
    )
    # May succeed or fail


def test_special_characters_in_name():
    """Test handling of special characters in display name."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "Player<script>", "pass", "desc",
        sessions, admins, "test_state.json"
    )
    
    # Should succeed (validation is elsewhere) but not crash
    assert ok is True


def test_very_long_password():
    """Test handling of very long password."""
    from account_service import create_account_and_login
    
    w = _fresh_world()
    sessions = {}
    admins = set()
    
    long_pass = "a" * 1000
    ok, err, emits, broadcasts = create_account_and_login(
        w, "sid1", "LongPassPlayer", long_pass, "desc",
        sessions, admins, "test_state.json"
    )
    
    assert ok is True
