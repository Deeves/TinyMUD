import pytest
from world import World, Room, Player
from daily_system import get_game_time_string, HOURLY_DESCRIPTIONS
from command_context import CommandContext
from admin_router import try_handle

class MockEmit:
    def __init__(self):
        self.messages = []
    
    def __call__(self, event, payload, **kwargs):
        self.messages.append((event, payload))

class MockContext:
    def __init__(self, world):
        self.world = world
        self.state_path = "test_worldstate.json"
        self.message_out = "message"
        self.admins = set()

def test_room_tags_persistence():
    """Test that room tags and ownership are persisted correctly."""
    world = World()
    # Create room with tags
    r = Room(id="room1", description="A test room.")
    r.tags = ["external", "ownable"]
    r.owner_id = "faction_123"
    
    d = r.to_dict()
    assert d["tags"] == ["external", "ownable"]
    assert d["owner_id"] == "faction_123"
    
    # Reload
    r2 = Room.from_dict(d)
    assert r2.tags == ["external", "ownable"]
    assert r2.owner_id == "faction_123"

def test_external_room_time_display():
    """Test that [external] rooms display the time."""
    world = World()
    world.game_time_ticks = 0 # Midnight
    
    # Non-external room
    r1 = Room(id="r1", description="Inside.")
    desc1 = r1.describe(world)
    assert "The moon hangs high" not in desc1
    
    # External room
    r2 = Room(id="r2", description="Outside.")
    r2.tags = ["external"]
    desc2 = r2.describe(world)
    assert "Outside." in desc2
    assert "It is currently 0:00." in desc2
    assert HOURLY_DESCRIPTIONS[0] in desc2

def test_admin_set_time_desc():
    """Test /settimedesc command."""
    world = World()
    world.game_time_ticks = 5
    
    # Setup context
    ctx = MockContext(world)
    sid = "admin_sid"
    ctx.admins.add(sid)
    emit = MockEmit()
    
    # Set time description
    # /settimedesc 5 New Dawn Description
    try_handle(ctx, sid, "settimedesc", ["5", "New", "Dawn", "Description"], "/settimedesc 5 New Dawn Description", emit)
    
    assert world.time_descriptions[5] == "New Dawn Description"
    
    # Verify persistence check (in-memory)
    # Check description retrieval
    time_str = get_game_time_string(world)
    assert "New Dawn Description" in time_str
    
    # Verify persistence round-trip
    wd = world.to_dict()
    assert wd["time_descriptions"]["5"] == "New Dawn Description"
    
    w2 = World.from_dict(wd)
    assert w2.time_descriptions[5] == "New Dawn Description"

def test_daily_system_defaults():
    world = World()
    world.game_time_ticks = 12
    s = get_game_time_string(world)
    assert "12:00" in s
    assert HOURLY_DESCRIPTIONS[12] in s
