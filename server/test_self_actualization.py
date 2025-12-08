"""Tests for NPC self-actualization and ambition system.

Validates:
- Maslow's Gate logic (needs must be met before pursuing ambitions)
- Ambition generation based on personality traits
- Milestone progression and completion
- Ambition-driven action generation
"""

import pytest
from world import CharacterSheet, World
import ambition_service
from ambition_model import Ambition


def test_maslow_gate_logic():
    """Maslow's Gate should block ambitions when basic needs are unmet."""
    sheet = CharacterSheet(display_name="TestNPC")
    
    # Defaults are 100, so gate should be open
    assert ambition_service.check_maslow_gate(sheet) == True
    
    # Starving -> Gate Closed
    sheet.hunger = 10
    assert ambition_service.check_maslow_gate(sheet) == False
    
    # Full again but Unsafe -> Gate Closed
    sheet.hunger = 100
    sheet.safety = 10
    assert ambition_service.check_maslow_gate(sheet) == False

def test_ambition_generation():
    sheet = CharacterSheet(display_name="Merchant")
    sheet.wealth_desire = 90
    sheet.aggression = 10
    
    ambition = ambition_service.generate_ambition(sheet)
    assert ambition.name == "Merchant Tycoon"
    assert len(ambition.milestones) == 3
    assert ambition.milestones[0].target_type == "currency"

    sheet2 = CharacterSheet(display_name="General")
    sheet2.wealth_desire = 10
    sheet2.aggression = 90
    
    ambition2 = ambition_service.generate_ambition(sheet2)
    assert ambition2.name == "Warlord"
    assert ambition2.milestones[0].target_type == "stat_combat_wins"

def test_ambition_progression():
    world = World()
    sheet = CharacterSheet(display_name="Richie")
    world.npc_sheets["Richie"] = sheet
    
    # Assign Wealth Ambition
    sheet.ambition = ambition_service._create_wealth_ambition(sheet)
    # Milestone 0: 100 gold
    
    # Start with 0 gold
    sheet.currency = 0
    ambition_service.evaluate_epiphany(world, "Richie")
    assert sheet.ambition.current_milestone_idx == 0
    
    # Give gold
    sheet.currency = 150
    ambition_service.evaluate_epiphany(world, "Richie")
    assert sheet.ambition.current_milestone_idx == 1 # Advanced!
    
    # Check completed
    assert sheet.ambition.milestones[0].completed == True

def test_action_generation():
    world = World()
    sheet = CharacterSheet(display_name="Worker")
    world.npc_sheets["Worker"] = sheet
    sheet.ambition = ambition_service._create_wealth_ambition(sheet)
    
    # Needs met -> Should get ambition actions
    actions = ambition_service.get_ambition_actions(world, "Worker")
    assert len(actions) > 0
    assert actions[0]['tool'] == 'work_job'
    
    # Needs NOT met -> No ambition actions
    sheet.hunger = 5
    actions = ambition_service.get_ambition_actions(world, "Worker")
    assert len(actions) == 0


