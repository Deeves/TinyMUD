"""Tests for new NPC actions: say, drop, look, and autonomous mappings."""

from world import World, Room, Object, CharacterSheet
import server as srv
import pytest

def _fresh_world():
    srv.world = World()
    return srv.world

def test_npc_say():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    w.rooms[r1.id] = r1
    npc = "Talker"
    r1.npcs.add(npc)
    
    # Mock broadcast
    messages = []
    def mock_broadcast(room_id, payload, exclude_sid=None):
        messages.append((room_id, payload))
    
    original_broadcast = srv.broadcast_to_room
    srv.broadcast_to_room = mock_broadcast
    
    try:
        srv._npc_execute_action(npc, r1.id, {"tool": "say", "args": {"message": "Hello world!"}})
        
        assert len(messages) == 1
        assert messages[0][0] == "r1"
        assert messages[0][1]['type'] == 'npc'
        assert messages[0][1]['name'] == npc
        assert messages[0][1]['content'] == "Hello world!"
    finally:
        srv.broadcast_to_room = original_broadcast

def test_npc_drop():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    w.rooms[r1.id] = r1
    npc = "Dropper"
    r1.npcs.add(npc)
    
    sheet = CharacterSheet(npc)
    obj = Object(display_name="Rock", uuid="rock-123")
    sheet.inventory.place(0, obj)
    w.npc_sheets[npc] = sheet
    
    # Mock broadcast
    messages = []
    def mock_broadcast(room_id, payload, exclude_sid=None):
        messages.append((room_id, payload))
    
    original_broadcast = srv.broadcast_to_room
    srv.broadcast_to_room = mock_broadcast
    
    try:
        srv._npc_execute_action(npc, r1.id, {"tool": "drop", "args": {"object_uuid": "rock-123"}})
        
        assert "rock-123" in r1.objects
        assert sheet.inventory.slots[0] is None
        assert len(messages) == 1
        assert "drops the Rock" in messages[0][1]['content']
    finally:
        srv.broadcast_to_room = original_broadcast

def test_npc_look():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    w.rooms[r1.id] = r1
    npc = "Looker"
    r1.npcs.add(npc)
    
    # Mock broadcast
    messages = []
    def mock_broadcast(room_id, payload, exclude_sid=None):
        messages.append((room_id, payload))
    
    original_broadcast = srv.broadcast_to_room
    srv.broadcast_to_room = mock_broadcast
    
    try:
        srv._npc_execute_action(npc, r1.id, {"tool": "look", "args": {"target": "something"}})
        
        assert len(messages) == 1
        assert "examines the something" in messages[0][1]['content']
    finally:
        srv.broadcast_to_room = original_broadcast

def test_autonomous_mappings():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    w.rooms[r1.id] = r1
    npc = "AutoNPC"
    r1.npcs.add(npc)
    
    # Mock broadcast
    messages = []
    def mock_broadcast(room_id, payload, exclude_sid=None):
        messages.append((room_id, payload))
    
    original_broadcast = srv.broadcast_to_room
    srv.broadcast_to_room = mock_broadcast
    
    try:
        # Test boast_achievements -> emote
        srv._npc_execute_action(npc, r1.id, {"tool": "boast_achievements", "args": {"audience": "everyone"}})
        assert "boasts about their achievements" in messages[-1][1]['content']
        
        # Test offer_help -> emote
        srv._npc_execute_action(npc, r1.id, {"tool": "offer_help", "args": {"target": "Player1"}})
        assert "offers to help Player1" in messages[-1][1]['content']
        
        # Test challenge_competitor -> say
        srv._npc_execute_action(npc, r1.id, {"tool": "challenge_competitor", "args": {"target": "Rival"}})
        assert messages[-1][1]['type'] == 'npc'
        assert "challenges Rival" in messages[-1][1]['content']
        
        # Test report_crime -> say
        srv._npc_execute_action(npc, r1.id, {"tool": "report_crime", "args": {"criminal": "Thief"}})
        assert messages[-1][1]['type'] == 'npc'
        assert "witnessed a crime by Thief" in messages[-1][1]['content']
        
        # Test initiate_trade -> emote
        srv._npc_execute_action(npc, r1.id, {"tool": "initiate_trade", "args": {"target": "Merchant"}})
        assert "approaches Merchant to trade" in messages[-1][1]['content']
        
    finally:
        srv.broadcast_to_room = original_broadcast

def test_autonomous_move_mappings():
    w = _fresh_world()
    r1 = Room(id="r1", description="Room 1")
    r2 = Room(id="r2", description="Room 2")
    r1.doors["exit"] = "r2"
    w.rooms[r1.id] = r1
    w.rooms[r2.id] = r2
    npc = "Mover"
    r1.npcs.add(npc)
    
    # Test flee_danger -> move_through
    srv._npc_execute_action(npc, r1.id, {"tool": "flee_danger", "args": {"target_room": "exit"}})
    assert npc in w.rooms["r2"].npcs
    
    # Reset
    w.rooms[r2.id].npcs.remove(npc)
    w.rooms[r1.id].npcs.add(npc)
    
    # Test move_to_safety -> move_through
    srv._npc_execute_action(npc, r1.id, {"tool": "move_to_safety", "args": {"target_room": "exit"}})
    assert npc in w.rooms["r2"].npcs
