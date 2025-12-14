import pytest
import sys
import os

# Ensure server directory is in path for direct imports
sys.path.append(os.path.dirname(__file__))

from world import World, Player, CharacterSheet, Room
import combat_service

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

@pytest.fixture
def basic_world():
    w = World()
    # Create room
    room = Room(id="r1", description="Test room")
    w.rooms[room.id] = room
    # Create players
    attacker_sheet = CharacterSheet(display_name="Attacker", strength=12, hp=10, max_hp=10)
    defender_sheet = CharacterSheet(display_name="Defender", strength=8, hp=5, max_hp=5)
    attacker = Player(sid="A", room_id=room.id, sheet=attacker_sheet)
    defender = Player(sid="B", room_id=room.id, sheet=defender_sheet)
    w.players[attacker.sid] = attacker
    w.players[defender.sid] = defender
    room.players.add(attacker.sid)
    room.players.add(defender.sid)
    return w

def test_attack_damage_and_death(basic_world, tmp_path):
    w = basic_world
    broadcaster = DummyBroadcaster()
    emitter = DummyEmitter()
    handled, err, emits, broadcasts = combat_service.attack(
        w, str(tmp_path / "world.json"), "A", "Defender", {}, set(), broadcaster, emitter
    )
    assert handled
    assert err is None
    # Defender should have reduced HP
    assert w.players["B"].sheet.hp < 5
    # Repeat until death
    while not w.players["B"].sheet.is_dead:
        combat_service.attack(w, str(tmp_path / "world.json"), "A", "Defender", {}, set(), broadcaster, emitter)
    assert w.players["B"].sheet.hp == 0
    assert w.players["B"].sheet.is_dead

def test_attack_npc_yield(tmp_path):
    w = World()
    room = Room(id="arena", description="Arena")
    w.rooms[room.id] = room
    attacker_sheet = CharacterSheet(display_name="Hero", strength=12, hp=10, max_hp=10)
    npc_sheet = CharacterSheet(display_name="Goblin", strength=6, hp=3, max_hp=10, morale=10, confidence=0, aggression=60)
    attacker = Player(sid="H", room_id=room.id, sheet=attacker_sheet)
    w.players[attacker.sid] = attacker
    room.players.add(attacker.sid)
    # Register NPC
    w.npc_sheets["Goblin"] = npc_sheet
    room.npcs.add("Goblin")
    broadcaster = DummyBroadcaster()
    emitter = DummyEmitter()
    # Attack may cause yield due to low HP/morale
    combat_service.attack(w, str(tmp_path / "world.json"), "H", "Goblin", {}, set(), broadcaster, emitter)
    assert npc_sheet.hp <= 3
    # Either dead or yielded
    assert npc_sheet.is_dead or npc_sheet.yielded

def test_attack_with_weapon_and_armor():
    """Test attack damage calculation with weapon and armor modifiers."""
    from combat_service import attack
    from world import World, CharacterSheet, Object, Room, Player, Inventory
    # Setup world, rooms, players
    world = World()
    room1 = Room(id="room1", description="Room1")
    room2 = Room(id="room2", description="Room2")
    world.rooms["room1"] = room1
    world.rooms["room2"] = room2
    # Weapon and armor objects
    sword = Object(display_name="Sword", weapon_damage=5, uuid="w1")
    shield = Object(display_name="Shield", armor_defense=3, uuid="a1")
    # Attacker setup with weapon in inventory
    attacker_inv = Inventory()
    attacker_inv.slots[0] = sword  # Put sword in left hand
    attacker_sheet = CharacterSheet(display_name="Attacker", strength=10, inventory=attacker_inv, equipped_weapon="w1")
    attacker = Player(sid="sid1", room_id="room1", sheet=attacker_sheet)
    # Target setup with armor in inventory
    target_inv = Inventory()
    target_inv.slots[0] = shield  # Put shield in left hand
    target_sheet = CharacterSheet(display_name="Target", hp=20, max_hp=20, inventory=target_inv, equipped_armor="a1")
    target = Player(sid="sid2", room_id="room1", sheet=target_sheet)
    world.players["sid1"] = attacker
    world.players["sid2"] = target
    room1.players.add("sid1")
    room1.players.add("sid2")
    # Dummy context
    emits, broadcasts = [], []
    def dummy_emit(ev, payload):
        emits.append(payload)
    def dummy_broadcast(room_id, payload, exclude_sid=None):
        broadcasts.append(payload)
    # Attack
    handled, err, out_emits, out_broadcasts = attack(world, "", "sid1", "Target", {}, set(), dummy_broadcast, dummy_emit)
    # Damage should be (strength//2 + weapon_damage - armor_defense) = (5+5-3) = 7
    assert target_sheet.hp == 13, f"Expected HP 13, got {target_sheet.hp}"
    assert any("for 7 damage" in e["content"] for e in out_emits), "Damage message missing"

def test_flee_command():
    """Test flee command moves player to adjacent room."""
    from combat_service import flee
    from world import World, CharacterSheet, Object, Room, Player, Inventory
    # Setup world, rooms, player
    world = World()
    room1 = Room(id="room1", description="Room1")
    room2 = Room(id="room2", description="Room2")
    # Add a door object linking to room2
    door = Object(display_name="Door", link_target_room_id="room2", uuid="d1", object_tags={"Travel Point", "Immovable"})
    room1.objects["d1"] = door
    world.rooms["room1"] = room1
    world.rooms["room2"] = room2
    sheet = CharacterSheet(display_name="FleePlayer", hp=10, max_hp=10, inventory=Inventory())
    player = Player(sid="sid1", room_id="room1", sheet=sheet)
    world.players["sid1"] = player
    room1.players.add("sid1")
    emits, broadcasts = [], []
    def dummy_emit(ev, payload):
        emits.append(payload)
    def dummy_broadcast(room_id, payload, exclude_sid=None):
        broadcasts.append(payload)
    # Flee
    handled, err, out_emits, out_broadcasts = flee(world, "", "sid1", {}, set(), dummy_broadcast, dummy_emit)
    assert player.room_id == "room2", f"Expected room2, got {player.room_id}"
    assert any("flee to room2" in e["content"] for e in out_emits), "Flee message missing"

