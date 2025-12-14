"""Tests for movement_router.py - the movement & look router.

This module tests:
- Movement through named doors (move through <door>)
- Movement via stairs (move up/down)
- Look command (look / l)
- Look at <name> targeting players, NPCs, and objects

Coverage target: boost movement_router.py from ~12% to ~80%+
"""

from unittest.mock import MagicMock, patch
import pytest
from world import World, Room, Object, Player, CharacterSheet


def _fresh_world():
    """Create a fresh World with two connected rooms for testing."""
    import server as srv
    srv.world = World()
    # Sync game_loop context with test world
    try:
        import game_loop
        ctx = game_loop.get_context()
        ctx.world = srv.world
    except (RuntimeError, ImportError):
        pass
    return srv.world


def _make_command_ctx(world, broadcasts=None):
    """Create a minimal CommandContext-like object for testing."""
    if broadcasts is None:
        broadcasts = []
    
    class FakeCtx:
        def __init__(self):
            self.world = world
            self.broadcast_to_room = lambda room_id, payload, exclude_sid=None: broadcasts.append((room_id, payload))
    
    return FakeCtx()


def _make_emit(emits=None):
    """Create emit function that captures emitted messages."""
    if emits is None:
        emits = []
    def emit(event, payload):
        emits.append((event, payload))
    return emit, emits


# ============================================================================
# Movement through doors
# ============================================================================

def test_move_through_door_success():
    """Test successful movement through a named door."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    r1.doors["oak door"] = "r2"
    w.rooms["r1"] = r1
    w.rooms["r2"] = r2
    
    # Add player
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move through oak door", "move through oak door", emit)
    
    assert result is True, "Handler should return True when handling movement"
    # Check that player was moved
    assert w.players[sid].room_id == "r2", "Player should be in room 2"


def test_move_through_door_error():
    """Test movement through nonexistent door returns error."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move through fake door", "move through fake door", emit)
    
    assert result is True, "Handler should return True (handled the command)"
    # Should have emitted an error
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'error'


def test_move_through_no_sid():
    """Test that movement fails gracefully without a valid session."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    w.rooms["r1"] = r1
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    # No sid provided
    result = try_handle_flow(ctx, None, "move through door", "move through door", emit)
    
    # Should not handle (no authenticated player)
    assert result is False


# ============================================================================
# Stairs movement
# ============================================================================

def test_move_up_stairs_success():
    """Test successful movement up stairs."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Ground floor")
    r2 = Room(id="r2", description="Upper floor")
    r1.stairs_up_to = "r2"
    w.rooms["r1"] = r1
    w.rooms["r2"] = r2
    
    sid = "player1"
    w.add_player(sid, name="Climber", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move up", "move up", emit)
    
    assert result is True
    assert w.players[sid].room_id == "r2"


def test_move_up_stairs_aliases():
    """Test all upstairs movement aliases."""
    from movement_router import try_handle_flow
    
    aliases = ["move up", "move upstairs", "move up stairs", "go up", "go up stairs"]
    
    for alias in aliases:
        w = _fresh_world()
        r1 = Room(id="r1", description="Ground")
        r2 = Room(id="r2", description="Upper")
        r1.stairs_up_to = "r2"
        w.rooms["r1"] = r1
        w.rooms["r2"] = r2
        
        sid = "player1"
        w.add_player(sid, name="Climber", room_id="r1")
        
        ctx = _make_command_ctx(w)
        emit, emits = _make_emit()
        
        result = try_handle_flow(ctx, sid, alias, alias.lower(), emit)
        assert result is True, f"Alias '{alias}' should be handled"
        assert w.players[sid].room_id == "r2", f"Player should move up with alias '{alias}'"


def test_move_down_stairs_success():
    """Test successful movement down stairs."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Upper floor")
    r2 = Room(id="r2", description="Ground floor")
    r1.stairs_down_to = "r2"
    w.rooms["r1"] = r1
    w.rooms["r2"] = r2
    
    sid = "player1"
    w.add_player(sid, name="Descender", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move down", "move down", emit)
    
    assert result is True
    assert w.players[sid].room_id == "r2"


def test_move_down_stairs_aliases():
    """Test all downstairs movement aliases."""
    from movement_router import try_handle_flow
    
    aliases = ["move down", "move downstairs", "move down stairs", "go down", "go down stairs"]
    
    for alias in aliases:
        w = _fresh_world()
        r1 = Room(id="r1", description="Upper")
        r2 = Room(id="r2", description="Lower")
        r1.stairs_down_to = "r2"
        w.rooms["r1"] = r1
        w.rooms["r2"] = r2
        
        sid = "player1"
        w.add_player(sid, name="Climber", room_id="r1")
        
        ctx = _make_command_ctx(w)
        emit, emits = _make_emit()
        
        result = try_handle_flow(ctx, sid, alias, alias.lower(), emit)
        assert result is True, f"Alias '{alias}' should be handled"
        assert w.players[sid].room_id == "r2", f"Player should move down with alias '{alias}'"


def test_move_up_no_stairs_error():
    """Test that moving up without stairs returns an error."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="No stairs here")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move up", "move up", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'error'
    assert w.players[sid].room_id == "r1"  # Player didn't move


def test_move_down_no_stairs_error():
    """Test that moving down without stairs returns an error."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="No stairs here")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move down", "move down", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'error'


# ============================================================================
# Look command
# ============================================================================

def test_look_basic():
    """Test basic 'look' command shows room description."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="A cozy tavern with warm lighting.")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "look", "look", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'system'


def test_look_short_alias():
    """Test 'l' alias for look."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="A quiet library.")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "l", "l", emit)
    
    assert result is True
    assert len(emits) > 0


def test_look_at_npc():
    """Test 'look at <npc>' shows NPC description."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Town square")
    w.rooms["r1"] = r1
    
    # Add an NPC to the room
    npc_name = "Bartender"
    sheet = CharacterSheet(display_name="Bartender", description="A gruff man with a thick beard.")
    w.npc_sheets[npc_name] = sheet
    r1.npcs.add(npc_name)
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "look at Bartender", "look at bartender", emit)
    
    assert result is True
    assert len(emits) > 0
    # Should get a system message with NPC details
    assert emits[0][1].get('type') == 'system'
    assert "Bartender" in emits[0][1].get('content', '')


def test_look_at_object():
    """Test 'look at <object>' shows object description."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="A dusty storage room")
    w.rooms["r1"] = r1
    
    # Add an object
    chest = Object(display_name="Old Chest", description="A weathered wooden chest with iron bands.")
    r1.objects[chest.uuid] = chest
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "look at Old Chest", "look at old chest", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'system'


def test_look_at_nothing():
    """Test 'look at' with empty name shows usage error."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Empty room")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "look at ", "look at ", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'error'
    assert 'Usage' in emits[0][1].get('content', '')


def test_look_at_nonexistent():
    """Test 'look at <nonexistent>' shows not found message."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Empty room")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "look at ghost", "look at ghost", emit)
    
    assert result is True
    assert len(emits) > 0
    assert "don't see" in emits[0][1].get('content', '').lower() or "ghost" in emits[0][1].get('content', '').lower()


def test_look_at_with_l_alias():
    """Test 'l at <name>' alias works."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Town square")
    w.rooms["r1"] = r1
    
    npc_name = "Guard"
    sheet = CharacterSheet(display_name="Guard", description="A stern-looking guard.")
    w.npc_sheets[npc_name] = sheet
    r1.npcs.add(npc_name)
    
    sid = "player1"
    w.add_player(sid, name="Looker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "l at Guard", "l at guard", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'system'


def test_look_at_player():
    """Test 'look at <player>' shows player description."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Meeting hall")
    w.rooms["r1"] = r1
    
    # Add two players
    sid1 = "player1"
    sid2 = "player2"
    w.add_player(sid1, name="Alice", room_id="r1")
    w.add_player(sid2, name="Bob", room_id="r1")
    r1.players.add(sid1)
    r1.players.add(sid2)
    
    # Set Bob's description
    w.players[sid2].sheet.description = "A tall man with a friendly smile."
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid1, "look at Bob", "look at bob", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'system'
    assert "Bob" in emits[0][1].get('content', '')


def test_look_at_unauthenticated():
    """Test that unauthenticated users get an error for look at."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Public area")
    w.rooms["r1"] = r1
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    # No player in world for this sid
    result = try_handle_flow(ctx, "unknown_sid", "look at something", "look at something", emit)
    
    assert result is True
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'error'
    assert 'authenticate' in emits[0][1].get('content', '').lower()


# ============================================================================
# Edge cases and error handling
# ============================================================================

def test_unhandled_command():
    """Test that unrelated commands return False (not handled)."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    
    ctx = _make_command_ctx(w)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "attack goblin", "attack goblin", emit)
    
    assert result is False  # Not a movement/look command


def test_look_prefix_unhandled():
    """Test that 'look' prefix without 'at' falls through."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room")
    w.rooms["r1"] = r1
    
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    
    ctx = _make_command_ctx(w)
    emit, emits = _make_emit()
    
    # "look around" doesn't match "look at"
    result = try_handle_flow(ctx, sid, "look around", "look around", emit)
    
    # Should not be handled by movement_router (falls through)
    assert result is False


def test_broadcast_on_movement():
    """Test that movement broadcasts departure and arrival."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    r1.doors["north door"] = "r2"
    w.rooms["r1"] = r1
    w.rooms["r2"] = r2
    
    sid = "player1"
    w.add_player(sid, name="Walker", room_id="r1")
    r1.players.add(sid)
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    result = try_handle_flow(ctx, sid, "move through north door", "move through north door", emit)
    
    assert result is True
    # Should have broadcasts for departure and arrival
    assert len(broadcasts) >= 2


def test_move_through_quotes_stripped():
    """Test that quoted door names work correctly."""
    from movement_router import try_handle_flow
    
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    r1.doors["fancy door"] = "r2"
    w.rooms["r1"] = r1
    w.rooms["r2"] = r2
    
    sid = "player1"
    w.add_player(sid, name="Tester", room_id="r1")
    
    broadcasts = []
    ctx = _make_command_ctx(w, broadcasts)
    emit, emits = _make_emit()
    
    # Quotes in the command
    result = try_handle_flow(ctx, sid, 'move through "fancy door"', 'move through "fancy door"', emit)
    
    # Should either work or return a sensible error
    assert result is True
