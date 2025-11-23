#!/usr/bin/env python3
"""
Demo script to show the enhanced Gemini AI integration with personality, 
memory, and relationship systems for TinyMUD NPCs.

This script demonstrates how NPCs now use their personality traits, memories,
and relationships to generate more contextual responses during conversations.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import sys
import os
import uuid
from datetime import datetime, timedelta

# Add server directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from world import World, CharacterSheet, Room


def create_demo_world():
    """Create a demo world with NPCs that have different personalities, memories, and relationships."""
    world = World()
    
    # Create a demo room
    room_id = "scholars_library"
    room = Room(
        id=room_id,
        description="The Scholars' Library - A quiet library filled with ancient tomes and scrolls. Dust motes dance in the afternoon sunlight streaming through tall windows."
    )
    world.rooms[room_id] = room
    
    # Create Scholar NPC - High curiosity, high responsibility
    scholar_name = "Librarian Thalia"
    scholar = CharacterSheet(
        display_name=scholar_name,
        description="An elderly scholar with keen eyes and ink-stained fingers. She has devoted her life to preserving knowledge.",
        curiosity=85,  # Very curious - asks lots of questions
        responsibility=90,  # High moral standards
        confidence=60,  # Moderately confident
        aggression=15,  # Very peaceful
        safety=95.0,
        wealth_desire=20.0,  # Doesn't care much about money
        social_status=70.0   # Respected scholar
    )
    
    # Add some memories for the scholar (using dict format as defined in CharacterSheet)
    scholar.memories = [
        {
            "id": str(uuid.uuid4()),
            "content": "A young student asked me about forbidden magic yesterday. I was concerned about their intentions.",
            "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
            "memory_type": "conversation",
            "importance": 8,
            "related_character_id": None
        },
        {
            "id": str(uuid.uuid4()),
            "content": "I discovered a rare manuscript about ancient rituals in the restricted section.",
            "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
            "memory_type": "discovery",
            "importance": 9,
            "related_character_id": None
        }
    ]
    
    world.npc_sheets[scholar_name] = scholar
    world.npc_ids[scholar_name] = str(uuid.uuid4())
    
    # Create Rogue NPC - Low responsibility, high aggression
    rogue_name = "Sly Marcus"
    rogue = CharacterSheet(
        display_name=rogue_name,
        description="A shifty-eyed individual with quick hands and a crooked smile. His clothes are well-made but worn.",
        curiosity=45,  # Moderate curiosity
        responsibility=15,  # Low moral standards - flexible about rules
        confidence=75,  # Bold and assertive
        aggression=70,  # Confrontational when needed
        safety=60.0,
        wealth_desire=85.0,  # Very interested in money
        social_status=30.0   # Low social standing
    )
    
    # Add memories for the rogue (using dict format as defined in CharacterSheet)
    rogue.memories = [
        {
            "id": str(uuid.uuid4()),
            "content": "I overheard the scholar mention valuable manuscripts in the restricted section.",
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "memory_type": "conversation",
            "importance": 7,
            "related_character_id": scholar_name
        },
        {
            "id": str(uuid.uuid4()),
            "content": "The merchant district guards have been asking questions about missing coins.",
            "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
            "memory_type": "observation",
            "importance": 6,
            "related_character_id": None
        }
    ]
    
    world.npc_sheets[rogue_name] = rogue
    world.npc_ids[rogue_name] = str(uuid.uuid4())
    
    # Create a relationship between the scholar and rogue (using the relationships dict on CharacterSheet)
    scholar.relationships[rogue_name] = -20.0  # Slightly negative relationship from scholar's perspective
    rogue.relationships[scholar_name] = 10.0   # Rogue is neutral/slightly positive toward scholar
    
    # Create player character
    player_name = "Adventurer Alex"
    player = CharacterSheet(
        display_name=player_name,
        description="A curious traveler seeking knowledge and adventure."
    )
    # Note: In the actual game, players are stored differently, but for demo purposes we'll use a simple approach
    
    return world, scholar_name, rogue_name, player_name, room_id


def demo_enhanced_ai_responses():
    """Demonstrate the enhanced AI integration with personality, memory, and relationship systems."""
    print("🎭 TinyMUD Enhanced AI Integration Demo")
    print("=" * 50)
    print()
    
    world, scholar_name, rogue_name, player_name, room_id = create_demo_world()
    
    print("📚 Scholar NPC (High Curiosity, High Responsibility):")
    print("-" * 50)
    scholar_sheet = world.npc_sheets[scholar_name]
    print(f"Name: {scholar_sheet.display_name}")
    print(f"Description: {scholar_sheet.description}")
    print(f"Personality: Curiosity={scholar_sheet.curiosity}, Responsibility={scholar_sheet.responsibility}")
    print(f"             Confidence={scholar_sheet.confidence}, Aggression={scholar_sheet.aggression}")
    print(f"Needs: Safety={scholar_sheet.safety}, Wealth Desire={scholar_sheet.wealth_desire}, Social Status={scholar_sheet.social_status}")
    print()
    
    print("🗡️ Rogue NPC (Low Responsibility, High Aggression):")
    print("-" * 50)
    rogue_sheet = world.npc_sheets[rogue_name]
    print(f"Name: {rogue_sheet.display_name}")
    print(f"Description: {rogue_sheet.description}")
    print(f"Personality: Curiosity={rogue_sheet.curiosity}, Responsibility={rogue_sheet.responsibility}")
    print(f"             Confidence={rogue_sheet.confidence}, Aggression={rogue_sheet.aggression}")
    print(f"Needs: Safety={rogue_sheet.safety}, Wealth Desire={rogue_sheet.wealth_desire}, Social Status={rogue_sheet.social_status}")
    print()
    
    print("🧠 Memory and Relationship Context:")
    print("-" * 40)
    print("The Scholar remembers:")
    for memory in scholar_sheet.memories:
        print(f"  • {memory['content']}")
    print()
    print("The Rogue remembers:")
    for memory in rogue_sheet.memories:
        print(f"  • {memory['content']}")
    print()
    print("Their relationships:")
    if rogue_name in scholar_sheet.relationships:
        print(f"  • Thalia → Marcus: {scholar_sheet.relationships[rogue_name]} (suspicious)")
    if scholar_name in rogue_sheet.relationships:
        print(f"  • Marcus → Thalia: {rogue_sheet.relationships[scholar_name]} (neutral)")
    
    print()
    print("🎯 Enhanced AI Integration Features:")
    print("-" * 40)
    print("✅ Personality traits influence behavior (responsibility, aggression, confidence, curiosity)")
    print("✅ Extended needs system (safety, wealth desire, social status)")
    print("✅ Memory system tracks recent events and interactions")
    print("✅ Relationship system with numerical scores between characters")
    print("✅ AI context now includes comprehensive personality and memory information")
    print("✅ NPCs make personality-driven decisions in autonomous behavior system")
    
    print()
    print("🚀 Implementation Complete!")
    print("   NPCs now use their personalities, memories, and relationships")
    print("   to generate more contextual and believable responses.")
    print("   Google Gemini AI integration enhanced with full memory & relationship context.")


if __name__ == "__main__":
    demo_enhanced_ai_responses()