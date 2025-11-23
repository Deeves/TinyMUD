import pytest
from unittest.mock import MagicMock, patch
from npc_service import handle_npc_command
from world import World, CharacterSheet, Room

@pytest.fixture
def mock_world():
    w = MagicMock(spec=World)
    w.rooms = {}
    w.npc_sheets = {}
    w.players = {}
    w.users = {}
    w.relationships = {}
    w.world_name = "Test World"
    w.world_description = "A test world."
    w.safety_level = "PG-13"
    
    # Mock get_or_create_npc_id to just return the name as ID for simplicity
    w.get_or_create_npc_id.side_effect = lambda name: name
    return w

def test_npc_setattr(mock_world):
    # Setup
    npc_name = "Bob"
    sheet = CharacterSheet(display_name=npc_name)
    mock_world.npc_sheets[npc_name] = sheet
    
    # Command: /npc setattr "Bob" | strength | 15
    handled, err, emits, broadcasts = handle_npc_command(
        mock_world, "state.json", "admin_sid", 
        ["setattr", "Bob", "|", "strength", "|", "15"]
    )
    
    assert handled is True
    assert err is None
    assert sheet.strength == 15
    assert "Set Bob's strength to 15" in emits[0]['content']

def test_npc_setaspect(mock_world):
    # Setup
    npc_name = "Alice"
    sheet = CharacterSheet(display_name=npc_name)
    mock_world.npc_sheets[npc_name] = sheet
    
    # Command: /npc setaspect "Alice" | high_concept | "Space Pirate"
    handled, err, emits, broadcasts = handle_npc_command(
        mock_world, "state.json", "admin_sid", 
        ["setaspect", "Alice", "|", "high_concept", "|", "Space Pirate"]
    )
    
    assert handled is True
    assert err is None
    assert sheet.high_concept == "Space Pirate"
    assert "Set Alice's high_concept to 'Space Pirate'" in emits[0]['content']

def test_npc_setmatrix(mock_world):
    # Setup
    npc_name = "Charlie"
    sheet = CharacterSheet(display_name=npc_name)
    mock_world.npc_sheets[npc_name] = sheet
    
    # Command: /npc setmatrix "Charlie" | auth_egal | 5
    handled, err, emits, broadcasts = handle_npc_command(
        mock_world, "state.json", "admin_sid", 
        ["setmatrix", "Charlie", "|", "auth_egal", "|", "5"]
    )
    
    assert handled is True
    assert err is None
    assert sheet.auth_egal == 5
    assert "Set Charlie's auth_egal to 5" in emits[0]['content']

def test_npc_sheet(mock_world):
    # Setup
    npc_name = "Dave"
    sheet = CharacterSheet(display_name=npc_name, strength=12, high_concept="Warrior")
    mock_world.npc_sheets[npc_name] = sheet
    
    # Command: /npc sheet "Dave"
    handled, err, emits, broadcasts = handle_npc_command(
        mock_world, "state.json", "admin_sid", 
        ["sheet", "Dave"]
    )
    
    assert handled is True
    assert err is None
    content = emits[0]['content']
    print(f"DEBUG CONTENT: {content}")
    assert "Dave" in content
    assert "[b]ST:[/b] 12" in content
    assert "[b]High Concept:[/b] Warrior" in content

@patch('npc_service._get_gemini_model')
@patch('npc_service._generate_nexus_profile')
def test_npc_generate(mock_gen_profile, mock_get_model, mock_world):
    # Setup
    mock_model = MagicMock()
    mock_get_model.return_value = mock_model
    
    # Mock profile return
    mock_gen_profile.return_value = {
        "high_concept": "Generated Hero",
        "trouble": "Secret Past",
        "background": "Soldier",
        "focus": "Combat",
        "strength": 14,
        "dexterity": 12,
        "intelligence": 10,
        "health": 11,
        "psychosocial_matrix": {
            "auth_egal": 2,
            "cons_lib": -1
        }
    }
    
    # Mock room resolution
    room = MagicMock(spec=Room)
    room.id = "room1"
    room.npcs = set()
    mock_world.rooms = {"room1": room}
    
    # Mock player location
    player = MagicMock()
    player.room_id = "room1"
    mock_world.players = {"admin_sid": player}
    
    # Command: /npc generate "here" | "NewGuy" | "A cool guy"
    handled, err, emits, broadcasts = handle_npc_command(
        mock_world, "state.json", "admin_sid", 
        ["generate", "here", "|", "NewGuy", "|", "A cool guy"]
    )
    
    assert handled is True
    assert err is None
    
    # Verify NPC created
    assert "NewGuy" in mock_world.npc_sheets
    sheet = mock_world.npc_sheets["NewGuy"]
    assert sheet.high_concept == "Generated Hero"
    assert sheet.strength == 14
    assert sheet.auth_egal == 2
    assert "NewGuy" in room.npcs
