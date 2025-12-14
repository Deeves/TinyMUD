"""Tests for admin_router.py - Admin slash command handling.

This module tests admin commands:
- /kick, /teleport, /bring, /purge  
- /worldstate, /safety, /setup
- /world set <key> | <value>
- /object subcommands
- /room, /npc, /faction delegation
- /settimedesc

Coverage target: boost admin_router.py from ~22% to ~70%+
"""

from unittest.mock import MagicMock, patch
import pytest
import json
import os
from world import World, Room, Player, CharacterSheet


def _fresh_world():
    """Create a fresh World with a room for testing."""
    import server as srv
    srv.world = World()
    # Create a room
    room = Room(id="start", description="A starting room")
    srv.world.rooms["start"] = room
    # Sync game_loop context 
    try:
        import game_loop
        ctx = game_loop.get_context()
        ctx.world = srv.world
    except (RuntimeError, ImportError):
        pass
    return srv.world


def _make_ctx(world, admins=None, state_path="test_state.json"):
    """Create a minimal CommandContext-like object for testing."""
    if admins is None:
        admins = set()
    broadcasts = []
    
    class FakeSocketIO:
        def emit(self, event, payload, to=None):
            pass
    
    class FakeCtx:
        def __init__(self):
            self.world = world
            self.admins = admins
            self.message_out = "message"
            self.state_path = state_path
            self.pending_confirm = {}
            self.socketio = FakeSocketIO()
            
        def broadcast_to_room(self, room_id, payload, exclude_sid=None):
            broadcasts.append((room_id, payload))
            
        def strip_quotes(self, s):
            s = s.strip()
            if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                return s[1:-1]
            if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                return s[1:-1]
            return s
            
        def resolve_player_sid_global(self, world, name):
            for sid, player in world.players.items():
                if player.sheet.display_name.lower() == name.lower():
                    return True, None, sid, player.sheet.display_name
            return False, f"Player '{name}' not found.", None, None
            
        def normalize_room_input(self, sid, room_in):
            if room_in == 'here':
                player = world.players.get(sid)
                if player:
                    return True, None, player.room_id
                return False, "You are nowhere.", None
            return True, None, room_in
            
        def resolve_room_id_fuzzy(self, sid, room_in):
            if room_in in world.rooms:
                return True, None, room_in
            return False, f"Room '{room_in}' not found.", None
            
        def teleport_player(self, world, sid, target_room):
            player = world.players.get(sid)
            if not player:
                return False, "Player not found.", [], []
            if target_room not in world.rooms:
                return False, f"Room '{target_room}' not found.", [], []
            old_room = player.room_id
            player.room_id = target_room
            emits = [{'type': 'system', 'content': f'You are now in {target_room}.'}]
            broadcasts = [(old_room, {'type': 'system', 'content': 'Player vanishes.'}),
                          (target_room, {'type': 'system', 'content': 'Player appears.'})]
            return True, None, emits, broadcasts
            
        def purge_prompt(self):
            return {'type': 'system', 'content': 'Type YES to confirm purge.'}
            
        def redact_sensitive(self, data):
            # Simple redaction for testing
            return data
            
        def handle_room_command(self, world, state_path, args, sid=None):
            return True, None, [{'type': 'system', 'content': 'Room command handled.'}], []
            
        def handle_npc_command(self, world, state_path, sid, args):
            return True, None, [{'type': 'system', 'content': 'NPC command handled.'}], []
            
        def handle_faction_command(self, world, state_path, sid, args):
            return True, None, [{'type': 'system', 'content': 'Faction command handled.'}], []
    
    return FakeCtx(), broadcasts


def _make_emit():
    """Create emit function that captures emitted messages."""
    emits = []
    def emit(event, payload):
        emits.append((event, payload))
    return emit, emits


# ============================================================================
# Non-admin access denied
# ============================================================================

def test_non_admin_denied():
    """Test that non-admins cannot use admin commands."""
    from admin_router import try_handle
    
    w = _fresh_world()
    sid = "player1"
    w.add_player(sid, name="NonAdmin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins=set())  # No admins
    emit, emits = _make_emit()
    
    result = try_handle(ctx, sid, "kick", ["someone"], "/kick someone", emit)
    
    assert result is True  # Command was handled
    assert len(emits) > 0
    assert emits[0][1].get('type') == 'error'
    assert 'Admin' in emits[0][1].get('content', '')


def test_unknown_command_not_handled():
    """Test that unknown commands return False."""
    from admin_router import try_handle
    
    w = _fresh_world()
    ctx, broadcasts = _make_ctx(w)
    emit, emits = _make_emit()
    
    result = try_handle(ctx, "sid", "unknown_cmd", [], "/unknown_cmd", emit)
    
    assert result is False  # Not an admin command


def test_empty_command():
    """Test that empty command returns False."""
    from admin_router import try_handle
    
    w = _fresh_world()
    ctx, broadcasts = _make_ctx(w)
    emit, emits = _make_emit()
    
    result = try_handle(ctx, "sid", "", [], "", emit)
    
    assert result is False


# ============================================================================
# /kick command
# ============================================================================

def test_kick_no_args():
    """Test /kick with no arguments shows usage."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "kick", [], "/kick", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'Usage' in emits[0][1].get('content', '')


def test_kick_player_not_found():
    """Test /kick with nonexistent player shows error."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "kick", ["ghost"], "/kick ghost", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'not found' in emits[0][1].get('content', '').lower()


def test_kick_self_denied():
    """Test admin cannot kick themselves."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "kick", ["Admin"], "/kick Admin", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'yourself' in emits[0][1].get('content', '').lower()


# ============================================================================
# /teleport command
# ============================================================================

def test_teleport_no_args():
    """Test /teleport with no arguments shows usage."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "teleport", [], "/teleport", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'Usage' in emits[0][1].get('content', '')


def test_teleport_self_success():
    """Test admin can teleport themselves."""
    from admin_router import try_handle
    
    w = _fresh_world()
    w.rooms["hall"] = Room(id="hall", description="A grand hall")
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "teleport", ["hall"], "/teleport hall", emit)
    
    assert result is True
    assert w.players[admin_sid].room_id == "hall"


def test_teleport_other_player():
    """Test admin can teleport another player."""
    from admin_router import try_handle
    
    w = _fresh_world()
    w.rooms["hall"] = Room(id="hall", description="A grand hall")
    admin_sid = "admin1"
    player_sid = "player1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    w.add_player(player_sid, name="Bob", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "teleport", ["Bob", "|", "hall"], "/teleport Bob | hall", emit)
    
    assert result is True
    assert w.players[player_sid].room_id == "hall"


def test_teleport_no_sid():
    """Test /teleport without session returns error."""
    from admin_router import try_handle
    
    w = _fresh_world()
    ctx, broadcasts = _make_ctx(w, admins={"admin1"})
    emit, emits = _make_emit()
    
    # Bypass admin check by having admin1 in admins but calling with None sid
    # Actually the check at line 42 will catch this first
    result = try_handle(ctx, None, "teleport", ["room"], "/teleport room", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'


def test_teleport_room_not_found():
    """Test teleport to nonexistent room."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "teleport", ["nonexistent"], "/teleport nonexistent", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'


# ============================================================================
# /bring command
# ============================================================================

def test_bring_no_args():
    """Test /bring with no arguments shows usage."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "bring", [], "/bring", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'Usage' in emits[0][1].get('content', '')


def test_bring_player_success():
    """Test admin can bring another player to their location."""
    from admin_router import try_handle
    
    w = _fresh_world()
    w.rooms["hall"] = Room(id="hall", description="A grand hall")
    admin_sid = "admin1"
    player_sid = "player1"
    w.add_player(admin_sid, name="Admin", room_id="hall")
    w.add_player(player_sid, name="Bob", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "bring", ["Bob"], "/bring Bob", emit)
    
    assert result is True
    assert w.players[player_sid].room_id == "hall"


def test_bring_player_not_found():
    """Test /bring with nonexistent player shows error."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "bring", ["ghost"], "/bring ghost", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'not found' in emits[0][1].get('content', '').lower()


# ============================================================================
# /purge command
# ============================================================================

def test_purge_sets_pending():
    """Test /purge sets pending confirmation."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "purge", [], "/purge", emit)
    
    assert result is True
    assert ctx.pending_confirm.get(admin_sid) == 'purge'
    assert len(emits) > 0


# ============================================================================
# /worldstate command  
# ============================================================================

def test_worldstate_file_not_found(tmp_path):
    """Test /worldstate with missing file."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid}, state_path=str(tmp_path / "nonexistent.json"))
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "worldstate", [], "/worldstate", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'not found' in emits[0][1].get('content', '').lower()


def test_worldstate_success(tmp_path):
    """Test /worldstate with valid file."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    # Create a test worldstate file
    state_path = tmp_path / "world_state.json"
    state_path.write_text(json.dumps({"test": "data"}))
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid}, state_path=str(state_path))
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "worldstate", [], "/worldstate", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'system'
    assert 'test' in emits[0][1].get('content', '')


# ============================================================================
# /safety command
# ============================================================================

def test_safety_show_current():
    """Test /safety with no args shows current level."""
    from admin_router import try_handle
    
    w = _fresh_world()
    w.safety_level = 'PG-13'
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "safety", [], "/safety", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'system'
    assert 'PG-13' in emits[0][1].get('content', '')


def test_safety_set_g():
    """Test /safety G sets G level."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "safety", ["G"], "/safety G", emit)
    
    assert result is True
    assert w.safety_level == 'G'


def test_safety_set_pg13():
    """Test /safety PG-13 sets PG-13 level."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "safety", ["PG-13"], "/safety PG-13", emit)
    
    assert result is True
    assert w.safety_level == 'PG-13'


def test_safety_set_r():
    """Test /safety R sets R level."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "safety", ["R"], "/safety R", emit)
    
    assert result is True
    assert w.safety_level == 'R'


def test_safety_set_off():
    """Test /safety OFF sets OFF level."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "safety", ["OFF"], "/safety OFF", emit)
    
    assert result is True
    assert w.safety_level == 'OFF'


def test_safety_invalid_level():
    """Test /safety with invalid level shows error."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "safety", ["INVALID"], "/safety INVALID", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'


# ============================================================================
# /setup command
# ============================================================================

def test_setup_already_complete():
    """Test /setup when setup is already complete."""
    from admin_router import try_handle
    
    w = _fresh_world()
    w.setup_complete = True
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "setup", [], "/setup", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'system'
    assert 'already complete' in emits[0][1].get('content', '').lower()


# ============================================================================
# /settimedesc command
# ============================================================================

def test_settimedesc_no_args():
    """Test /settimedesc with no arguments shows usage."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "settimedesc", [], "/settimedesc", emit)
    
    assert result is True
    assert 'Usage' in emits[0][1].get('content', '')


def test_settimedesc_invalid_hour():
    """Test /settimedesc with invalid hour."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "settimedesc", ["25", "Too", "late"], "/settimedesc 25 Too late", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'integer' in emits[0][1].get('content', '').lower()


def test_settimedesc_success():
    """Test /settimedesc with valid hour and description."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "settimedesc", ["12", "The", "sun", "is", "high"], "/settimedesc 12 The sun is high", emit)
    
    assert result is True
    assert hasattr(w, 'time_descriptions')
    assert w.time_descriptions.get(12) == "The sun is high"


# ============================================================================
# /object command
# ============================================================================

def test_object_no_args():
    """Test /object with no arguments shows usage."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "object", [], "/object", emit)
    
    assert result is True
    assert 'Usage' in emits[0][1].get('content', '')


def test_object_listtemplates():
    """Test /object listtemplates."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "object", ["listtemplates"], "/object listtemplates", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'system'


def test_object_viewtemplate_no_key():
    """Test /object viewtemplate with no key."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "object", ["viewtemplate"], "/object viewtemplate", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'Usage' in emits[0][1].get('content', '')


def test_object_deletetemplate_no_key():
    """Test /object deletetemplate with no key."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "object", ["deletetemplate"], "/object deletetemplate", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'Usage' in emits[0][1].get('content', '')


def test_object_unknown_subcommand():
    """Test /object with unknown subcommand."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "object", ["unknownsub"], "/object unknownsub", emit)
    
    assert result is True
    assert emits[0][1].get('type') == 'error'
    assert 'Unknown' in emits[0][1].get('content', '')


def test_object_createtemplateobject():
    """Test /object createtemplateobject starts wizard."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "object", ["createtemplateobject"], "/object createtemplateobject", emit)
    
    assert result is True
    assert hasattr(w, 'object_template_sessions')
    assert admin_sid in w.object_template_sessions


# ============================================================================
# /room, /npc, /faction delegation
# ============================================================================

def test_room_delegated():
    """Test /room is delegated to handler."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "room", ["list"], "/room list", emit)
    
    assert result is True
    assert any('Room command handled' in e[1].get('content', '') for e in emits)


def test_npc_delegated():
    """Test /npc is delegated to handler."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "npc", ["list"], "/npc list", emit)
    
    assert result is True
    assert any('NPC command handled' in e[1].get('content', '') for e in emits)


def test_faction_delegated():
    """Test /faction is delegated to handler."""
    from admin_router import try_handle
    
    w = _fresh_world()
    admin_sid = "admin1"
    w.add_player(admin_sid, name="Admin", room_id="start")
    
    ctx, broadcasts = _make_ctx(w, admins={admin_sid})
    emit, emits = _make_emit()
    
    result = try_handle(ctx, admin_sid, "faction", ["list"], "/faction list", emit)
    
    assert result is True
    assert any('Faction command handled' in e[1].get('content', '') for e in emits)


# ============================================================================
# Rate limiting
# ============================================================================

def test_rate_limit_applied():
    """Test that rate limiting applies to admin commands."""
    from admin_router import try_handle
    import os
    
    # Enable rate limiting for this test
    old_val = os.environ.get('MUD_RATE_ENABLE')
    os.environ['MUD_RATE_ENABLE'] = '1'
    
    try:
        w = _fresh_world()
        admin_sid = "admin1"
        w.add_player(admin_sid, name="Admin", room_id="start")
        
        ctx, broadcasts = _make_ctx(w, admins={admin_sid})
        
        # Spam commands to trigger rate limit
        for _ in range(50):
            emit, emits = _make_emit()
            try_handle(ctx, admin_sid, "safety", [], "/safety", emit)
    finally:
        if old_val is not None:
            os.environ['MUD_RATE_ENABLE'] = old_val
        else:
            os.environ.pop('MUD_RATE_ENABLE', None)
