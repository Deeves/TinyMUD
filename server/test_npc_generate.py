"""Tests for /npc generate command (both contextual and explicit modes).

These tests verify:
1. Contextual generation (no arguments) - generates NPC for current room
2. Explicit generation (with arguments) - generates NPC with specified details
3. Proper allocation of advantages, disadvantages, and quirks
4. Psychosocial matrix values are clamped to valid ranges
5. AI fallback handling when no API key is available
"""

from __future__ import annotations

import os
import tempfile

from world import World, Room, CharacterSheet, Player
from npc_service import handle_npc_command
from mock_ai import MockAIModel


def test_generate_contextual_mode():
    """Test contextual NPC generation in player's current room."""
    # Mock the AI model
    import npc_service as ns
    
    class FakeResp:
        def __init__(self, text):
            self.text = text
    
    class FakeModel:
        def generate_content(self, prompt, safety_settings=None):
            # Return a complete Nexus profile
            return FakeResp('''{
                "name": "Gareth the Smith",
                "description": "A burly blacksmith with soot-stained hands and a friendly demeanor.",
                "high_concept": "Master of the Forge",
                "trouble": "Too Trusting of Strangers",
                "background": "Craftsman",
                "focus": "Armorer",
                "strength": 14,
                "dexterity": 10,
                "intelligence": 11,
                "health": 13,
                "advantages": [{"name": "Fit", "cost": 5}, {"name": "Craftsman (Blacksmith)", "cost": 10}],
                "disadvantages": [{"name": "Truthfulness", "cost": -5}],
                "quirks": ["Hums while working", "Prefers ale to wine"],
                "psychosocial_matrix": {
                    "sexuality_hom_het": 5,
                    "physical_presentation_mas_fem": -8,
                    "social_presentation_mas_fem": -5,
                    "auth_egal": -3,
                    "cons_lib": 2,
                    "spirit_mat": 4,
                    "ego_alt": -2,
                    "hed_asc": 3,
                    "nih_mor": -4,
                    "rat_rom": 1,
                    "ske_abso": 0
                }
            }''')
    
    orig_get = getattr(ns, '_get_gemini_model', None)
    ns._get_gemini_model = lambda: FakeModel()
    
    try:
        with tempfile.TemporaryDirectory() as d:
            tmpfile = os.path.join(d, 'world_state.json')
            w = World()
            w.world_name = "Ironforge Vale"
            w.world_description = "A medieval kingdom centered around mining and smithing."
            
            # Create a room with context
            w.rooms['smithy'] = Room(id='smithy', description='A hot, noisy workshop filled with the clang of hammers on anvils.')
            
            # Create a player in the smithy
            sid = 'test_sid'
            sheet = CharacterSheet(display_name='TestPlayer', description='A test player')
            player = Player(sid=sid, sheet=sheet, room_id='smithy')
            w.players[sid] = player
            
            # Execute contextual generation (no arguments)
            handled, err, emits, broadcasts = handle_npc_command(w, tmpfile, sid, ['generate'])
            
            assert handled, "Command should be handled"
            assert err is None, f"Should not error: {err}"
            assert len(emits) >= 2, "Should emit progress and completion messages"
            
            # Verify NPC was created
            assert 'Gareth the Smith' in w.npc_sheets, "NPC should be created"
            sheet = w.npc_sheets['Gareth the Smith']
            
            # Verify Nexus profile
            assert sheet.high_concept == "Master of the Forge"
            assert sheet.trouble == "Too Trusting of Strangers"
            assert sheet.strength == 14
            assert sheet.dexterity == 10
            assert sheet.intelligence == 11
            assert sheet.health == 13
            
            # Verify advantages and disadvantages
            assert len(sheet.advantages) == 2
            assert sheet.advantages[0]['name'] == 'Fit'
            assert len(sheet.disadvantages) == 1
            assert len(sheet.quirks) == 2
            
            # Verify psychosocial matrix
            assert sheet.physical_presentation_mas_fem == -8
            assert sheet.auth_egal == -3
            
            # Verify NPC is in the room
            assert 'Gareth the Smith' in w.rooms['smithy'].npcs
            
    finally:
        if orig_get:
            ns._get_gemini_model = orig_get


def test_generate_explicit_mode():
    """Test explicit NPC generation with specified details."""
    import npc_service as ns
    
    class FakeResp:
        def __init__(self, text):
            self.text = text
    
    class FakeModel:
        def generate_content(self, prompt, safety_settings=None):
            return FakeResp('''{
                "high_concept": "Cunning Merchant Prince",
                "trouble": "Debts to the Wrong People",
                "background": "Noble",
                "focus": "Dilettante",
                "strength": 9,
                "dexterity": 11,
                "intelligence": 14,
                "health": 10,
                "advantages": [{"name": "Charisma", "cost": 5}, {"name": "Wealth", "cost": 20}],
                "disadvantages": [{"name": "Greed", "cost": -15}],
                "quirks": ["Always wears purple", "Obsessed with exotic spices", "Speaks in metaphors"],
                "psychosocial_matrix": {
                    "sexuality_hom_het": 0,
                    "physical_presentation_mas_fem": 2,
                    "social_presentation_mas_fem": 5,
                    "auth_egal": 7,
                    "cons_lib": -6,
                    "spirit_mat": -8,
                    "ego_alt": 9,
                    "hed_asc": 8,
                    "nih_mor": 3,
                    "rat_rom": -5,
                    "ske_abso": 4
                }
            }''')
    
    orig_get = getattr(ns, '_get_gemini_model', None)
    ns._get_gemini_model = lambda: FakeModel()
    
    try:
        with tempfile.TemporaryDirectory() as d:
            tmpfile = os.path.join(d, 'world_state.json')
            w = World()
            w.world_name = "Trading Kingdoms"
            w.world_description = "A network of merchant states competing for trade routes."
            
            w.rooms['bazaar'] = Room(id='bazaar', description='A bustling marketplace filled with colorful stalls.')
            
            # Execute explicit generation
            handled, err, emits, broadcasts = handle_npc_command(
                w, tmpfile, None, 
                ['generate', 'bazaar|Lord Vespin|A wealthy merchant with a taste for luxury']
            )
            
            assert handled, "Command should be handled"
            assert err is None, f"Should not error: {err}"
            
            # Verify NPC
            assert 'Lord Vespin' in w.npc_sheets
            sheet = w.npc_sheets['Lord Vespin']
            assert sheet.description == 'A wealthy merchant with a taste for luxury'
            assert sheet.intelligence == 14
            assert len(sheet.advantages) == 2
            assert sheet.advantages[1]['cost'] == 20
            
            # Verify quirks are limited to 5
            assert len(sheet.quirks) <= 5
            
    finally:
        if orig_get:
            ns._get_gemini_model = orig_get


def test_generate_advantage_allocation():
    """Test that advantages are properly allocated with max 40 points."""
    import npc_service as ns
    
    class FakeResp:
        def __init__(self, text):
            self.text = text
    
    class FakeModel:
        def generate_content(self, prompt, safety_settings=None):
            # Return advantages totaling over 40 points
            return FakeResp('''{
                "high_concept": "Superhuman Warrior",
                "trouble": "Too Many Enemies",
                "background": "Soldier",
                "focus": "Warrior",
                "strength": 15,
                "dexterity": 14,
                "intelligence": 10,
                "health": 14,
                "advantages": [
                    {"name": "Combat Reflexes", "cost": 15},
                    {"name": "Extra HP", "cost": 10},
                    {"name": "High Pain Threshold", "cost": 10},
                    {"name": "Weapon Master", "cost": 20}
                ],
                "disadvantages": [{"name": "Bloodlust", "cost": -10}],
                "quirks": ["Polishes weapons obsessively"],
                "psychosocial_matrix": {
                    "sexuality_hom_het": 3,
                    "physical_presentation_mas_fem": -9,
                    "social_presentation_mas_fem": -7,
                    "auth_egal": 5,
                    "cons_lib": 4,
                    "spirit_mat": 2,
                    "ego_alt": 3,
                    "hed_asc": 1,
                    "nih_mor": -2,
                    "rat_rom": 0,
                    "ske_abso": 6
                }
            }''')
    
    orig_get = getattr(ns, '_get_gemini_model', None)
    ns._get_gemini_model = lambda: FakeModel()
    
    try:
        with tempfile.TemporaryDirectory() as d:
            tmpfile = os.path.join(d, 'world_state.json')
            w = World()
            w.rooms['arena'] = Room(id='arena', description='A gladiatorial arena.')
            
            handled, err, emits, broadcasts = handle_npc_command(
                w, tmpfile, None, 
                ['generate', 'arena|Maximus|A legendary gladiator']
            )
            
            assert handled and err is None
            sheet = w.npc_sheets['Maximus']
            
            # Calculate total advantage points
            total_adv = sum(adv.get('cost', 0) for adv in sheet.advantages)
            assert total_adv <= 40, f"Advantages should total ≤40 points, got {total_adv}"
            
            # Should only include advantages up to 40 point limit
            # Combat Reflexes (15) + Extra HP (10) + High Pain Threshold (10) = 35 ≤ 40
            # Weapon Master (20) would push to 55, so should be excluded
            assert len(sheet.advantages) == 3, "Should include only first 3 advantages"
            
    finally:
        if orig_get:
            ns._get_gemini_model = orig_get


def test_generate_psychosocial_clamping():
    """Test that psychosocial matrix values are clamped to -10 to 10."""
    import npc_service as ns
    
    class FakeResp:
        def __init__(self, text):
            self.text = text
    
    class FakeModel:
        def generate_content(self, prompt, safety_settings=None):
            # Return out-of-range values
            return FakeResp('''{
                "high_concept": "Extremist",
                "trouble": "No Middle Ground",
                "background": "Radical",
                "focus": "Zealot",
                "strength": 10,
                "dexterity": 10,
                "intelligence": 10,
                "health": 10,
                "advantages": [],
                "disadvantages": [],
                "quirks": [],
                "psychosocial_matrix": {
                    "sexuality_hom_het": 25,
                    "physical_presentation_mas_fem": -15,
                    "social_presentation_mas_fem": 50,
                    "auth_egal": -100,
                    "cons_lib": 12,
                    "spirit_mat": -11,
                    "ego_alt": 10,
                    "hed_asc": -10,
                    "nih_mor": 9,
                    "rat_rom": -8,
                    "ske_abso": 0
                }
            }''')
    
    orig_get = getattr(ns, '_get_gemini_model', None)
    ns._get_gemini_model = lambda: FakeModel()
    
    try:
        with tempfile.TemporaryDirectory() as d:
            tmpfile = os.path.join(d, 'world_state.json')
            w = World()
            w.rooms['temple'] = Room(id='temple', description='A sacred place of worship.')
            
            handled, err, emits, broadcasts = handle_npc_command(
                w, tmpfile, None, 
                ['generate', 'temple|Zealot|A radical believer']
            )
            
            assert handled and err is None
            sheet = w.npc_sheets['Zealot']
            
            # Verify all matrix values are clamped
            assert -10 <= sheet.sexuality_hom_het <= 10, f"sexuality_hom_het not clamped: {sheet.sexuality_hom_het}"
            assert -10 <= sheet.physical_presentation_mas_fem <= 10
            assert -10 <= sheet.social_presentation_mas_fem <= 10
            assert -10 <= sheet.auth_egal <= 10, f"auth_egal not clamped: {sheet.auth_egal}"
            assert -10 <= sheet.cons_lib <= 10
            assert -10 <= sheet.spirit_mat <= 10
            
    finally:
        if orig_get:
            ns._get_gemini_model = orig_get


def test_generate_no_api_key():
    """Test graceful handling when no API key is available."""
    import npc_service as ns
    
    orig_get = getattr(ns, '_get_gemini_model', None)
    ns._get_gemini_model = lambda: None  # Simulate no API key
    
    try:
        with tempfile.TemporaryDirectory() as d:
            tmpfile = os.path.join(d, 'world_state.json')
            w = World()
            w.rooms['tavern'] = Room(id='tavern', description='A cozy tavern.')
            
            # Create player for contextual mode
            sid = 'test_sid'
            sheet = CharacterSheet(display_name='TestPlayer', description='Test')
            player = Player(sid=sid, sheet=sheet, room_id='tavern')
            w.players[sid] = player
            
            # Test contextual mode
            handled, err, emits, broadcasts = handle_npc_command(w, tmpfile, sid, ['generate'])
            assert handled
            assert err is not None
            assert 'not available' in err.lower()
            
            # Test explicit mode
            handled, err, emits, broadcasts = handle_npc_command(
                w, tmpfile, None, 
                ['generate', 'tavern|Bartender|A friendly bartender']
            )
            assert handled
            assert err is not None
            assert 'not available' in err.lower()
            
    finally:
        if orig_get:
            ns._get_gemini_model = orig_get


if __name__ == '__main__':
    test_generate_contextual_mode()
    print("✓ test_generate_contextual_mode")
    
    test_generate_explicit_mode()
    print("✓ test_generate_explicit_mode")
    
    test_generate_advantage_allocation()
    print("✓ test_generate_advantage_allocation")
    
    test_generate_psychosocial_clamping()
    print("✓ test_generate_psychosocial_clamping")
    
    test_generate_no_api_key()
    print("✓ test_generate_no_api_key")
    
    print("\nAll /npc generate tests passed!")
