"""
Demo script showing the enhanced NPC behavior system (Priority 1).

This script demonstrates how NPCs with different personality traits
make different autonomous decisions based on their enhanced needs.
"""

import sys
import os

sys.path.append(os.path.dirname(__file__))

from world import World, Room, CharacterSheet, Object
from autonomous_npc_service import evaluate_npc_autonomy


def create_demo_scenario():
    """Create a test scenario with different NPC personalities."""
    world = World()
    
    # Create a room with some valuable objects and food
    room = Room(id="tavern", description="A bustling tavern")
    
    # Add some objects of interest
    gold_ring = Object(display_name="Gold Ring", description="A shiny gold ring", value=50)
    bread = Object(display_name="Bread", description="Fresh bread")
    bread.satiation_value = 30
    
    apple = Object(display_name="Apple", description="A red apple")
    apple.satiation_value = 20
    
    room.objects = {
        "ring1": gold_ring,
        "bread1": bread,
        "apple1": apple
    }
    
    world.rooms["tavern"] = room
    
    return world, room


def create_test_npcs():
    """Create NPCs with different personality profiles."""
    npcs = {}
    
    # The Thief - low responsibility, high wealth desire
    thief = CharacterSheet("Sneaky Pete")
    thief.responsibility = 20  # Very low morals
    thief.wealth_desire = 90.0  # Loves money
    thief.confidence = 70  # Bold enough to act
    thief.currency = 2  # Poor
    thief.hunger = 80.0  # Not desperately hungry
    npcs["thief"] = thief
    
    # The Paladin - high responsibility, low aggression
    paladin = CharacterSheet("Sir Noble")
    paladin.responsibility = 90  # Very moral
    paladin.wealth_desire = 30.0  # Not materialistic
    paladin.confidence = 80  # Confident but moral
    paladin.aggression = 20  # Peaceful
    paladin.currency = 50  # Well-off
    paladin.hunger = 85.0  # Not hungry
    npcs["paladin"] = paladin
    
    # The Scholar - high curiosity, moderate confidence
    scholar = CharacterSheet("Wise Sage")
    scholar.curiosity = 85  # Very curious
    scholar.confidence = 60  # Moderately confident
    scholar.responsibility = 70  # Generally moral
    scholar.wealth_desire = 40.0  # Not greedy
    scholar.hunger = 90.0  # Well-fed
    npcs["scholar"] = scholar
    
    # The Coward - low confidence, high safety need
    coward = CharacterSheet("Timid Tom")
    coward.confidence = 25  # Very timid
    coward.safety = 30.0  # Feels unsafe
    coward.aggression = 10  # Very passive
    coward.responsibility = 60  # Generally good
    coward.hunger = 75.0  # Okay on food
    npcs["coward"] = coward
    
    # The Starving Criminal - low responsibility, desperate hunger
    criminal = CharacterSheet("Desperate Dan")
    criminal.responsibility = 15  # Very low morals
    criminal.hunger = 15.0  # Starving!
    criminal.wealth_desire = 60.0  # Wants money
    criminal.confidence = 40  # Desperate enough to act
    criminal.currency = 0  # Broke
    npcs["criminal"] = criminal
    
    return npcs


def run_demo():
    """Run the demonstration."""
    print("=== Enhanced NPC Behavior Demo (Priority 1) ===\n")
    
    world, room = create_demo_scenario()
    npcs = create_test_npcs()
    
    # Add NPCs to world
    for npc_name, sheet in npcs.items():
        world.npc_sheets[sheet.display_name] = sheet
        room.npcs.add(sheet.display_name)
    
    print("Scenario: A tavern with a Gold Ring (value: 50), Bread, and Apple\n")
    
    for npc_type, sheet in npcs.items():
        print(f"--- {sheet.display_name} ({npc_type.title()}) ---")
        print(f"Personality: Responsibility={sheet.responsibility}, Confidence={sheet.confidence}")
        print(f"             Curiosity={sheet.curiosity}, Aggression={sheet.aggression}")
        print(f"Needs: Hunger={sheet.hunger}, Safety={sheet.safety}")
        print(f"       Wealth Desire={sheet.wealth_desire}, Currency={sheet.currency}")
        print()
        
        # Evaluate what this NPC wants to do
        actions = evaluate_npc_autonomy(world, sheet.display_name, "tavern")
        
        if actions:
            print("Autonomous behaviors this NPC is considering:")
            for i, action in enumerate(actions[:3], 1):  # Show top 3
                print(f"  {i}. {action.get('description', 'No description')} (Priority: {action.get('priority', 0)})")
                print(f"     Tool: {action['tool']}, Args: {action['args']}")
        else:
            print("This NPC sees no reason to act autonomously.")
        
        print("\n" + "="*60 + "\n")


def show_personality_effects():
    """Show how personality traits affect decision-making."""
    print("=== Personality Trait Effects ===\n")
    
    scenarios = [
        {
            "title": "Low Responsibility + High Wealth Desire + Valuable Object Present",
            "effect": "NPC likely to steal if opportunity exists and few witnesses"
        },
        {
            "title": "High Responsibility + Criminal Activity Detected", 
            "effect": "NPC will report crimes or intervene to maintain order"
        },
        {
            "title": "High Curiosity + Unexplored Objects",
            "effect": "NPC will investigate unknown objects before other actions"
        },
        {
            "title": "Low Confidence + Conflict Present",
            "effect": "NPC will flee rather than engage in confrontation"
        },
        {
            "title": "High Aggression + Resource Competition",
            "effect": "NPC may challenge competitors aggressively"
        },
        {
            "title": "Low Safety + Threats Present",
            "effect": "NPC will prioritize escape over all other needs"
        }
    ]
    
    for scenario in scenarios:
        print(f"• {scenario['title']}")
        print(f"  Result: {scenario['effect']}\n")


if __name__ == "__main__":
    run_demo()
    show_personality_effects()
    
    print("\nThis demonstrates Priority 1: Enhanced NPC Needs & Behaviors")
    print("NPCs now make decisions based on personality traits like Oblivion's Radiant AI!")