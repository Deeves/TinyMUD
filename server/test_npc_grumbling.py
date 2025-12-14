import pytest
import server
import game_loop
from world import World, Room, CharacterSheet


def _sync_context_for_test(world, broadcast_fn):
    """Sync game_loop context with test mocks."""
    try:
        ctx = game_loop.get_context()
        ctx.world = world
        ctx.broadcast_to_room = broadcast_fn
    except RuntimeError:
        pass


def test_npc_grumble_on_missing_item(monkeypatch):
    """Test that an NPC grumbles when trying to pick up a missing object."""
    world = World()
    room = Room(id='r1', description='A test room')
    world.rooms['r1'] = room
    
    npc_name = 'Grumbler'
    sheet = CharacterSheet(display_name=npc_name)
    sheet.plan_queue = [{'tool': 'get_object', 'args': {'object_name': 'NonExistentItem'}}]
    sheet.action_points = 1
    world.npc_sheets[npc_name] = sheet
    room.npcs.add(npc_name)
    
    # Mock broadcast_to_room to capture output
    broadcasts = []
    def mock_broadcast(room_id, payload, exclude_sid=None):
        broadcasts.append(payload)
    
    monkeypatch.setattr(server, 'world', world)
    monkeypatch.setattr(server, 'broadcast_to_room', mock_broadcast)
    _sync_context_for_test(world, mock_broadcast)
    
    # Simulate one tick of action execution logic
    # We can't easily call _world_tick because it's an infinite loop, 
    # so we'll simulate the relevant part manually or extract a helper if needed.
    # But wait, we modified _world_tick directly. 
    # Let's import the modified server module and just call a simplified version of the logic 
    # OR we can expose a helper.
    # The clean way is to trust that _world_tick calls _npc_execute_action which calls grumble.
    # So let's test that logic flow by calling _npc_execute_action and asserting grumble is called?
    # No, we modified the CALLER of _npc_execute_action.
    
    # We will simulate the loop body for this NPC
    action = sheet.plan_queue.pop(0)
    ok, reason = server._npc_execute_action(npc_name, 'r1', action)
    if not ok:
        server._npc_grumble_failure(npc_name, 'r1', action, reason)
        
    # Assertions
    assert len(broadcasts) > 0
    message = broadcasts[-1]['content']
    assert "grumbles loudly" in message
    assert "cannot find the NonExistentItem" in message

def test_npc_grumble_on_locked_door(monkeypatch):
    """Test that an NPC grumbles when trying to locked door."""
    world = World()
    room = Room(id='r1', description='A test room')
    room.doors = {'Locked Door': 'r2'}
    room.door_locks = {'Locked Door': {'allow_ids': []}} # Locked to everyone
    world.rooms['r1'] = room
    world.rooms['r2'] = Room(id='r2', description='Destination')
    
    npc_name = 'Grumbler'
    sheet = CharacterSheet(display_name=npc_name)
    # Ensure stable ID for lock check
    world.npc_sheets[npc_name] = sheet
    world.get_or_create_npc_id(npc_name)
    
    sheet.plan_queue = [{'tool': 'move_through', 'args': {'name': 'Locked Door'}}]
    room.npcs.add(npc_name)
    
    broadcasts = []
    def mock_broadcast(room_id, payload, exclude_sid=None):
        broadcasts.append(payload)
        
    monkeypatch.setattr(server, 'world', world)
    monkeypatch.setattr(server, 'broadcast_to_room', mock_broadcast)
    _sync_context_for_test(world, mock_broadcast)
    
    # Simulate execution
    action = sheet.plan_queue.pop(0)
    # Note: We need to make sure _npc_execute_action uses the mocked world?
    # server.world IS the global world we patched.
    ok, reason = server._npc_execute_action(npc_name, 'r1', action)
    if not ok:
        server._npc_grumble_failure(npc_name, 'r1', action, reason)
    
    # Assertions
    # Depending on implementation, it might broadcast "triest the door" THEN grumble
    found_grumble = False
    for b in broadcasts:
        if "grumbles loudly" in b.get('content', ''):
            found_grumble = True
            assert "locked" in b['content']
            
    assert found_grumble
