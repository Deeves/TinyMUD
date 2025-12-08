"""Tests for admin world crafting commands.

Validates CRUD operations for rooms, NPCs, objects, and missions
through the admin command interface.
"""

import pytest
from unittest.mock import MagicMock, patch
from world import World, Room, CharacterSheet, Object, Faction
from admin_router import try_handle
from command_context import CommandContext
from mission_model import Mission, MissionStatus


def extract_emit_content(mock_emit):
    """Extract the 'content' field from the last emit call.
    
    Handles both 2-arg (event, payload) and 1-arg (payload) emit signatures.
    """
    if not mock_emit.called:
        return ""
    last_call = mock_emit.call_args
    args = last_call[0]
    payload = {}
    if len(args) == 2:
        payload = args[1]
    elif len(args) == 1:
        payload = args[0]
    
    if isinstance(payload, dict):
        return payload.get('content', '')
    return str(payload)

@pytest.fixture
def test_world():
    w = World()
    # Setup basic world
    w.rooms['r1'] = Room(id='r1', description='Room 1')
    w.rooms['r2'] = Room(id='r2', description='Room 2')
    w.start_room_id = 'r1'
    
    # Setup Admin User
    u = w.create_user('admin', 'pass', 'Admin User')
    u.is_admin = True
    w.players['sid_admin'] = MagicMock()
    w.players['sid_admin'].user_id = u.user_id
    w.players['sid_admin'].room_id = 'r1' # Admin in room 1
    
    # Setup Admin session
    return w, 'sid_admin', u.user_id

@pytest.fixture
def mock_ctx(test_world):
    world, sid, uid = test_world
    
    # helper mocks
    noop = MagicMock()
    
    ctx = CommandContext(
        world=world,
        state_path='test_state.json',
        saver=MagicMock(),
        socketio=MagicMock(),
        message_out='out',
        sessions={'sid_admin': uid},
        admins={'sid_admin'},
        pending_confirm={},
        world_setup_sessions={},
        barter_sessions={},
        trade_sessions={},
        interaction_sessions={},
        strip_quotes=lambda s: s.strip('"\' '),
        resolve_player_sid_global=MagicMock(return_value=(True, None, sid, 'Admin')),
        normalize_room_input=MagicMock(return_value=(True, None, 'r1')),
        resolve_room_id_fuzzy=MagicMock(return_value=(True, None, 'r1')),
        teleport_player=MagicMock(),
        handle_room_command=MagicMock(wraps=lambda w, p, a, s: __import__('room_service').handle_room_command(w, p, a, s)),
        handle_npc_command=MagicMock(wraps=lambda w, p, s, a: __import__('npc_service').handle_npc_command(w, p, s, a)),
        handle_faction_command=MagicMock(),
        purge_prompt=MagicMock(),
        execute_purge=MagicMock(),
        redact_sensitive=MagicMock(),
        is_confirm_yes=MagicMock(return_value=False),
        is_confirm_no=MagicMock(return_value=False),
        broadcast_to_room=MagicMock()
    )
    return ctx

def test_room_commands(mock_ctx):
    """Test room create, list, and delete commands."""
    world, sid, _ = mock_ctx.world, 'sid_admin', None
    emit = MagicMock()
    
    # Patch at the source for consistency across modules
    with patch('persistence_utils.save_world') as mock_save, \
         patch('rate_limiter.check_rate_limit', return_value=True):
        
        # 1. Create Room
        try_handle(mock_ctx, sid, 'room', ['create', 'r3', 'Room 3'], 'raw', emit)
        assert 'r3' in world.rooms
        assert world.rooms['r3'].description == 'Room 3'
        
        # 2. List Rooms
        try_handle(mock_ctx, sid, 'room', ['list'], 'raw', emit)
        assert extract_emit_content(emit).find('r3') != -1
        
        # 3. Delete Room
        try_handle(mock_ctx, sid, 'room', ['delete', 'r3'], 'raw', emit)
        assert 'r3' not in world.rooms

def test_npc_commands(mock_ctx):
    """Test NPC add, list, and delete commands."""
    world, sid, _ = mock_ctx.world, 'sid_admin', None
    emit = MagicMock()
    
    with patch('persistence_utils.save_world') as mock_save, \
         patch('rate_limiter.check_rate_limit', return_value=True):
        
        # 1. Add NPC
        try_handle(mock_ctx, sid, 'npc', ['add', 'r1', '|', 'Bob', '|', 'Desc'], 'raw', emit)
        assert 'Bob' in world.npc_sheets
        assert 'Bob' in world.rooms['r1'].npcs
        
        # 2. List NPCs
        try_handle(mock_ctx, sid, 'npc', ['list'], 'raw', emit)
        assert extract_emit_content(emit).find('Bob') != -1
        
        # 3. Delete NPC (Global)
        try_handle(mock_ctx, sid, 'npc', ['delete', 'Bob'], 'raw', emit)
        assert 'Bob' not in world.npc_sheets
        assert 'Bob' not in world.rooms['r1'].npcs

def test_object_commands(mock_ctx):
    """Test object create, list, and delete commands."""
    world, sid, _ = mock_ctx.world, 'sid_admin', None
    emit = MagicMock()
    
    with patch('persistence_utils.save_world') as mock_save, \
         patch('rate_limiter.check_rate_limit', return_value=True):
        
        # 1. Create Object
        # syntax: /object createobject <room> | <name> | <desc> | <tags>
        try_handle(mock_ctx, sid, 'object', ['createobject', 'r1', '|', 'Sword', '|', 'Sharp', '|', 'weapon'], 'raw', emit)
        
        # Find uuid
        r1 = world.rooms['r1']
        assert len(r1.objects) == 1
        oid = list(r1.objects.keys())[0]
        obj = r1.objects[oid]
        assert obj.display_name == 'Sword'
        
        # 2. List Objects
        try_handle(mock_ctx, sid, 'object', ['list', 'r1'], 'raw', emit)
        content = extract_emit_content(emit)
        assert 'Sword' in content
        
        # 3. Delete Object
        # Syntax: /object delete <room> | <name_or_uuid>
        try_handle(mock_ctx, sid, 'object', ['delete', 'r1', '|', 'Sword'], 'raw', emit)
        assert len(r1.objects) == 0

def test_mission_commands(mock_ctx):
    """Test mission create, list, setstatus, and delete commands."""
    from mission_router import try_handle as mission_handle
    world, sid, _ = mock_ctx.world, 'sid_admin', None
    emit = MagicMock()
    
    # 1. Create Mission (Admin)
    args = ['create', 'Quest 1', '|', 'Do stuff']
    mission_handle(mock_ctx, sid, 'mission', args, 'raw', emit)
    
    assert len(world.missions) == 1
    mid = list(world.missions.keys())[0]
    assert world.missions[mid].title == 'Quest 1'
    
    # 2. List Missions
    mission_handle(mock_ctx, sid, 'mission', ['listall'], 'raw', emit)
    assert extract_emit_content(emit).find('Quest 1') != -1
    
    # 3. Set Status
    mission_handle(mock_ctx, sid, 'mission', ['setstatus', mid, '|', 'completed'], 'raw', emit)
    assert world.missions[mid].status == MissionStatus.COMPLETED
    
    # 4. Delete Mission
    mission_handle(mock_ctx, sid, 'mission', ['delete', mid], 'raw', emit)
    assert len(world.missions) == 0

