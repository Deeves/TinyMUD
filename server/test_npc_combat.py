import pytest
from world import World, Room, CharacterSheet, Faction
from combat_service import npc_autonomous_attack

class DummyBroadcaster:
    def __init__(self):
        self.messages = []
    def __call__(self, room_id, payload, exclude_sid=None):
        self.messages.append((room_id, payload, exclude_sid))

class DummyEmitter:
    def __init__(self):
        self.messages = []
    def __call__(self, ev, payload):
        self.messages.append((ev, payload))

def test_npc_rival_attack(tmp_path):
    world = World()
    
    # Create factions
    red_faction = Faction(faction_id="red", name="Red Team")
    blue_faction = Faction(faction_id="blue", name="Blue Team")
    
    # Make them rivals
    red_faction.add_rival("blue")
    blue_faction.add_rival("red")
    
    world.factions["red"] = red_faction
    world.factions["blue"] = blue_faction
    
    # Create room
    room = Room(id="arena", description="A dusty arena.")
    world.rooms["arena"] = room
    
    # Create NPCs
    red_guard = CharacterSheet(display_name="RedGuard", strength=10, hp=20, max_hp=20)
    # We need to attach faction_id to the sheet. 
    # CharacterSheet doesn't have faction_id field by default in the dataclass shown earlier, 
    # but the implementation of npc_autonomous_attack uses getattr(npc_sheet, 'faction_id', None).
    # So we can just set it dynamically or if it was added to the class.
    # Looking at previous file reads, CharacterSheet didn't have faction_id explicitly in the dataclass definition 
    # but Python allows dynamic attributes or maybe it was added and I missed it?
    # Wait, the prompt said "Add a faction to have a relationship with another faction."
    # The implementation I wrote uses `getattr(npc_sheet, 'faction_id', None)`.
    # So I should set it on the instance.
    red_guard.faction_id = "red"
    
    blue_guard = CharacterSheet(display_name="BlueGuard", strength=10, hp=20, max_hp=20)
    blue_guard.faction_id = "blue"
    
    world.npc_sheets["RedGuard"] = red_guard
    world.npc_sheets["BlueGuard"] = blue_guard
    
    room.npcs.add("RedGuard")
    room.npcs.add("BlueGuard")
    
    broadcaster = DummyBroadcaster()
    emitter = DummyEmitter()
    
    # Trigger autonomous attack for RedGuard
    npc_autonomous_attack(world, str(tmp_path / "world.json"), "RedGuard", "arena", broadcaster, emitter)
    
    # Verify insult
    insults = [m for m in broadcaster.messages if m[1].get("type") == "npc" and "insults" in m[1].get("content", "")]
    assert len(insults) > 0, "RedGuard should have insulted BlueGuard"
    assert "RedGuard" in insults[0][1]["name"]
    
    # Verify attack (BlueGuard should take damage)
    # Base damage = max(1, strength // 2) = 5
    assert blue_guard.hp < 20, "BlueGuard should have taken damage"
    assert blue_guard.hp == 15

def test_npc_no_attack_same_faction(tmp_path):
    world = World()
    
    # Create faction
    red_faction = Faction(faction_id="red", name="Red Team")
    world.factions["red"] = red_faction
    
    # Create room
    room = Room(id="arena", description="A dusty arena.")
    world.rooms["arena"] = room
    
    # Create NPCs
    red_guard1 = CharacterSheet(display_name="RedGuard1", strength=10, hp=20, max_hp=20)
    red_guard1.faction_id = "red"
    
    red_guard2 = CharacterSheet(display_name="RedGuard2", strength=10, hp=20, max_hp=20)
    red_guard2.faction_id = "red"
    
    world.npc_sheets["RedGuard1"] = red_guard1
    world.npc_sheets["RedGuard2"] = red_guard2
    
    room.npcs.add("RedGuard1")
    room.npcs.add("RedGuard2")
    
    broadcaster = DummyBroadcaster()
    emitter = DummyEmitter()
    
    # Trigger autonomous attack for RedGuard1
    npc_autonomous_attack(world, str(tmp_path / "world.json"), "RedGuard1", "arena", broadcaster, emitter)
    
    # Verify NO insult
    insults = [m for m in broadcaster.messages if m[1].get("type") == "npc" and "insults" in m[1].get("content", "")]
    assert len(insults) == 0, "RedGuard1 should NOT insult RedGuard2"
    
    # Verify NO attack
    assert red_guard2.hp == 20, "RedGuard2 should NOT take damage"
