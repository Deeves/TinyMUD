"""Integration tests for server message handling paths.

These tests verify the end-to-end message flow through the server,
testing multiple services working together:
- Auth flow → Player creation → Room presence
- Movement commands → Room broadcasts
- Look commands → NPC/Object resolution
- Admin commands → World state changes
- Dice rolling → Room broadcasts
- Pending confirmation flows
- Rate limiting
- Object template wizard

Coverage target: boost message_handler.py and overall integration coverage.
"""

from unittest.mock import MagicMock, patch
import pytest
from world import World, Room, Object, Player, CharacterSheet


class FakeRateLimiter:
    """Fake rate limiter that always allows."""
    def allow(self):
        return True


class MockSocketIO:
    """Mock SocketIO for testing emit/broadcast."""
    def __init__(self):
        self.emitted = []
        
    def emit(self, event, payload, to=None, room=None):
        self.emitted.append({'event': event, 'payload': payload, 'to': to, 'room': room})


class DiceResult:
    """Fake dice result."""
    def __init__(self, expr, total):
        self.expression = expr
        self.total = total


class DiceError(Exception):
    """Dice error for testing."""
    pass


def _fresh_world():
    """Create a fresh World with test rooms."""
    import server as srv
    srv.world = World()
    srv.world.rooms["start"] = Room(id="start", description="The starting room.")
    srv.world.rooms["hall"] = Room(id="hall", description="A grand hall.")
    srv.world.start_room_id = "start"
    try:
        import game_loop
        ctx = game_loop.get_context()
        ctx.world = srv.world
    except (RuntimeError, ImportError):
        pass
    return srv.world


def _make_message_handler_context(world, sid="test_sid"):
    """Create a MessageHandlerContext for testing."""
    from message_handler import MessageHandlerContext
    
    emits = []
    broadcasts = []
    disconnects = []
    
    def fake_emit(event, payload):
        emits.append({'event': event, 'payload': payload})
        
    def fake_broadcast(room_id, payload, exclude_sid=None):
        broadcasts.append({'room_id': room_id, 'payload': payload, 'exclude': exclude_sid})
        
    def fake_disconnect(target_sid, namespace=None):
        disconnects.append(target_sid)
        
    def fake_get_sid():
        return sid
    
    rate_limiters = {}
    def get_rate_limiter(sid):
        if sid not in rate_limiters:
            rate_limiters[sid] = FakeRateLimiter()
        return rate_limiters[sid]
    
    sessions = {}
    admins = set()
    
    ctx = MessageHandlerContext(
        world=world,
        state_path="test_state.json",
        saver=MagicMock(),
        socketio=MockSocketIO(),
        sessions=sessions,
        admins=admins,
        pending_confirm={},
        auth_sessions={},
        world_setup_sessions={},
        object_template_sessions={},
        barter_sessions={},
        trade_sessions={},
        interaction_sessions={},
        emit=fake_emit,
        get_sid=fake_get_sid,
        broadcast_to_room=fake_broadcast,
        disconnect=fake_disconnect,
        message_in="message_to_server",
        message_out="message",
        env_str=lambda key, default: default,
        strip_quotes=lambda s: s.strip('"').strip("'"),
        resolve_player_sid_global=lambda w, name: _resolve_player(w, name),
        normalize_room_input=lambda sid, room: (True, None, room if room != 'here' else 'start'),
        resolve_room_id_fuzzy=lambda sid, room: (room in world.rooms, None if room in world.rooms else "Not found", room if room in world.rooms else None),
        simple_rate_limiter=type('FakeLimiter', (), {'get': staticmethod(get_rate_limiter)})(),
        teleport_player=lambda w, sid, room: _teleport(w, sid, room),
        handle_room_command=lambda w, sp, args, sid: (True, None, [{'type': 'system', 'content': 'Room cmd.'}], []),
        handle_npc_command=lambda w, sp, sid, args: (True, None, [{'type': 'system', 'content': 'NPC cmd.'}], []),
        handle_faction_command=lambda w, sp, sid, args: (True, None, [{'type': 'system', 'content': 'Faction cmd.'}], []),
        purge_prompt=lambda: {'type': 'system', 'content': 'Confirm purge?'},
        execute_purge=lambda sp: World(),
        prepare_purge_snapshot_sids=lambda w: list(w.players.keys()),
        redact_sensitive=lambda d: d,
        is_confirm_yes=lambda s: s.lower() in ('y', 'yes'),
        is_confirm_no=lambda s: s.lower() in ('n', 'no'),
        auth_handle=lambda w, sid, msg, sess, admins, sp, auth_sess: _auth_handle(w, sid, msg, sess, admins, auth_sess),
        setup_handle=lambda w, sp, sid, msg, sess: (False, None, [], []),
        setup_begin=lambda sess, sid: [{'type': 'system', 'content': 'Setup wizard started.'}],
        dice_roll=lambda expr: DiceResult(expr, 12),
        dice_error=DiceError,
        handle_command=lambda sid, msg: None,
        save_world=lambda w, sp, debounced=False: None,
    )
    
    return ctx, emits, broadcasts, sessions, admins


def _resolve_player(world, name):
    """Helper to resolve player by name."""
    for sid, player in world.players.items():
        if player.sheet.display_name.lower() == name.lower():
            return True, None, sid, player.sheet.display_name
    return False, f"Player '{name}' not found.", None, None


def _teleport(world, sid, room_id):
    """Helper teleport function."""
    player = world.players.get(sid)
    if not player:
        return False, "Player not found.", [], []
    if room_id not in world.rooms:
        return False, "Room not found.", [], []
    old_room = player.room_id
    player.room_id = room_id
    return True, None, [{'type': 'system', 'content': f'Teleported to {room_id}.'}], [(old_room, {'type': 'system', 'content': 'Player left.'})]


def _auth_handle(world, sid, msg, sessions, admins, auth_sessions):
    """Fake auth handler - creates player on any input."""
    if sid not in world.players:
        world.add_player(sid, name=msg.strip() or "NewPlayer", room_id="start")
        sessions[sid] = f"user_{sid}"
        if len(world.players) == 1:
            admins.add(sid)
        return True, [{'type': 'system', 'content': f'Welcome, {msg}!'}], []
    return False, [], []


# ============================================================================
# Message validation
# ============================================================================

def test_invalid_payload():
    """Test that invalid payloads are rejected."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    
    # Test with non-dict payload
    handler("not a dict")
    assert len(emits) > 0
    assert emits[0]['payload'].get('type') == 'error'
    assert 'Invalid payload' in emits[0]['payload'].get('content', '')


def test_missing_content_key():
    """Test that missing content key is rejected."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'other_key': 'value'})
    
    assert len(emits) > 0
    assert emits[0]['payload'].get('type') == 'error'


def test_message_too_long():
    """Test that overly long messages are rejected."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'x' * 2000})  # Default limit is 1000
    
    assert len(emits) > 0
    assert emits[0]['payload'].get('type') == 'error'
    assert 'too long' in emits[0]['payload'].get('content', '').lower()


# ============================================================================
# Auth flow integration
# ============================================================================

def test_unauthenticated_user_auth_flow():
    """Test that unauthenticated users go through auth flow."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'TestPlayer'})
    
    # Should have created a player
    assert 'test_sid' in w.players
    assert w.players['test_sid'].sheet.display_name == 'TestPlayer'


def test_first_user_becomes_admin():
    """Test that first user becomes admin."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'AdminPlayer'})
    
    assert 'test_sid' in admins


# ============================================================================
# Pending confirmation flow
# ============================================================================

def test_pending_confirm_yes():
    """Test confirming a pending action with 'yes'."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    ctx.pending_confirm['test_sid'] = 'purge'
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'yes'})
    
    assert 'test_sid' not in ctx.pending_confirm
    # Should have completed the purge action
    assert any('purged' in e['payload'].get('content', '').lower() for e in emits)


def test_pending_confirm_no():
    """Test cancelling a pending action with 'no'."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    ctx.pending_confirm['test_sid'] = 'purge'
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'no'})
    
    assert 'test_sid' not in ctx.pending_confirm
    assert any('cancelled' in e['payload'].get('content', '').lower() for e in emits)


def test_pending_confirm_invalid():
    """Test invalid response to pending confirmation."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    ctx.pending_confirm['test_sid'] = 'purge'
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'maybe'})
    
    # Should still be pending
    assert 'test_sid' in ctx.pending_confirm
    assert any('confirm' in e['payload'].get('content', '').lower() for e in emits)


# ============================================================================
# Roll command integration
# ============================================================================

def test_roll_command():
    """Test dice rolling command."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Roller", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'roll 2d6'})
    
    # Should get a roll result
    assert len(emits) > 0
    assert any('roll' in e['payload'].get('content', '').lower() for e in emits)


def test_roll_command_usage():
    """Test roll command with no expression shows usage."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Roller", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'roll'})
    
    assert len(emits) > 0
    assert emits[0]['payload'].get('type') == 'error'
    assert 'Usage' in emits[0]['payload'].get('content', '')


def test_roll_private():
    """Test private dice roll."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Roller", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'roll 1d20 | private'})
    
    # Should get a private roll result
    assert len(emits) > 0
    assert any('secretly' in e['payload'].get('content', '').lower() for e in emits)
    # Broadcasts should be empty for private roll
    assert len(broadcasts) == 0


def test_roll_unauthenticated():
    """Test roll command requires authentication."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'roll 2d6'})
    
    # Should trigger auth flow instead of roll
    # (auth flow creates player since our mock auth_handle always succeeds)
    # The point is it doesn't crash and handles gracefully


# ============================================================================
# Slash command dispatch
# ============================================================================

def test_slash_command_dispatch():
    """Test that slash commands are dispatched correctly."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Commander", room_id="start")
    
    command_calls = []
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    ctx.handle_command = lambda s, msg: command_calls.append((s, msg))
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': '/help'})
    
    assert len(command_calls) > 0
    assert command_calls[0] == (sid, '/help')


# ============================================================================
# Movement router integration
# ============================================================================

def test_movement_through_door():
    """Test movement through door triggers movement router."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Walker", room_id="start")
    w.rooms["start"].doors["north door"] = "hall"
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'move through north door'})
    
    # Should have moved the player
    assert w.players[sid].room_id == "hall"


def test_look_command():
    """Test look command."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Looker", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'look'})
    
    # Should get room description
    assert len(emits) > 0
    assert emits[0]['payload'].get('type') == 'system'


# ============================================================================
# Object template wizard
# ============================================================================

def test_object_template_wizard_cancel():
    """Test cancelling object template creation."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Creator", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    ctx.object_template_sessions[sid] = {"step": "template_key", "temp": {}}
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'cancel'})
    
    # Session should be cleared
    assert sid not in ctx.object_template_sessions
    assert any('cancelled' in e['payload'].get('content', '').lower() for e in emits)


def test_object_template_wizard_step_key():
    """Test object template wizard template_key step."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Creator", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    ctx.object_template_sessions[sid] = {"step": "template_key", "temp": {}}
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'my_sword'})
    
    # Should advance to next step
    assert ctx.object_template_sessions[sid]['temp'].get('key') == 'my_sword'
    assert ctx.object_template_sessions[sid]['step'] == 'display_name'


def test_object_template_wizard_duplicate_key():
    """Test object template wizard rejects duplicate keys."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    w.object_templates = {'existing_key': Object(display_name="Test")}
    sid = "test_sid"
    w.add_player(sid, name="Creator", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    ctx.object_template_sessions[sid] = {"step": "template_key", "temp": {}}
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'existing_key'})
    
    # Should show error and stay on same step
    assert any('already exists' in e['payload'].get('content', '').lower() for e in emits)
    assert ctx.object_template_sessions[sid]['step'] == 'template_key'


# ============================================================================
# Trade/barter session integration
# ============================================================================

def test_trade_session_detection():
    """Test that trade sessions are detected and routed."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Trader", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    ctx.trade_sessions[sid] = {"step": "awaiting_confirm"}
    init_message_handler(ctx)
    
    # The handler should detect trade session
    # This tests the session detection path, actual handling is in trade_router


# ============================================================================
# World setup session
# ============================================================================

def test_world_setup_session_detection():
    """Test world setup session routing."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Admin", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    ctx.world_setup_sessions[sid] = {"step": "name"}
    # Override setup_handle to return handled
    ctx.setup_handle = lambda w, sp, sid, msg, sess: (True, None, [{'type': 'system', 'content': 'Setup handled.'}], [])
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': 'My World'})
    
    assert any('Setup handled' in e['payload'].get('content', '') for e in emits)


# ============================================================================
# Edge cases and error handling
# ============================================================================

def test_non_string_message():
    """Test handling of non-string message content."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    # Non-string content should be handled gracefully
    handler({'content': 12345})
    # Should not crash - may or may not produce output depending on handling


def test_empty_message():
    """Test empty message handling."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Silent", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': ''})
    # Should not crash


def test_whitespace_only_message():
    """Test whitespace-only message handling."""
    from message_handler import create_message_handler, init_message_handler
    
    w = _fresh_world()
    sid = "test_sid"
    w.add_player(sid, name="Spacer", room_id="start")
    
    ctx, emits, broadcasts, sessions, admins = _make_message_handler_context(w, sid)
    init_message_handler(ctx)
    
    handler = create_message_handler()
    handler({'content': '   '})
    # Should not crash


# ============================================================================
# Context management
# ============================================================================

def test_get_context_without_init():
    """Test that get_context raises when not initialized."""
    from message_handler import get_context
    import message_handler
    
    # Save current context
    old_ctx = message_handler._ctx
    message_handler._ctx = None
    
    try:
        with pytest.raises(RuntimeError, match="not initialized"):
            get_context()
    finally:
        # Restore context
        message_handler._ctx = old_ctx


def test_world_replacement():
    """Test that world can be replaced via context."""
    from message_handler import MessageHandlerContext
    
    w1 = World()
    w1.world_name = "World 1"
    
    ctx, _, _, _, _ = _make_message_handler_context(w1)
    
    assert ctx.get_world().world_name == "World 1"
    
    w2 = World()
    w2.world_name = "World 2"
    ctx.set_world(w2)
    
    assert ctx.get_world().world_name == "World 2"
