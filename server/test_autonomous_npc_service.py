"""
Test the enhanced NPC needs and behaviors system (Priority 1).

This test suite verifies that the new personality traits, enhanced needs,
and autonomous behavior evaluation work correctly.
"""

import pytest
from world import World, Room, CharacterSheet, Object
from autonomous_npc_service import (
    evaluate_npc_autonomy,
    add_memory,
    update_relationship,
    get_personality_modifier
)


class TestEnhancedNPCNeeds:
    """Test the enhanced needs system beyond basic hunger/thirst/sleep/socialization."""
    
    def test_character_sheet_enhanced_fields(self):
        """Test that CharacterSheet includes all new enhanced fields."""
        sheet = CharacterSheet("TestNPC")
        
        # Check enhanced needs exist with correct defaults
        assert sheet.safety == 100.0
        assert sheet.wealth_desire == 50.0
        assert sheet.social_status == 50.0
        
        # Check personality traits exist with correct defaults
        assert sheet.responsibility == 50
        assert sheet.aggression == 30
        assert sheet.confidence == 50
        assert sheet.curiosity == 50
        
        # Check memory and relationship systems exist
        assert sheet.memories == []
        assert sheet.relationships == {}
    
    def test_character_sheet_serialization(self):
        """Test that enhanced fields are properly saved and loaded."""
        sheet = CharacterSheet("TestNPC")
        
        # Modify some enhanced fields
        sheet.safety = 75.0
        sheet.wealth_desire = 80.0
        sheet.responsibility = 25
        sheet.aggression = 90
        sheet.memories = [{"type": "test", "data": "value"}]
        sheet.relationships = {"player1": 50.0, "npc2": -30.0}
        
        # Serialize and deserialize
        data = sheet.to_dict()
        restored_sheet = CharacterSheet.from_dict(data)
        
        # Verify all enhanced fields are preserved
        assert restored_sheet.safety == 75.0
        assert restored_sheet.wealth_desire == 80.0
        assert restored_sheet.responsibility == 25
        assert restored_sheet.aggression == 90
        assert restored_sheet.memories == [{"type": "test", "data": "value"}]
        assert restored_sheet.relationships == {"player1": 50.0, "npc2": -30.0}


class TestAutonomousBehavior:
    """Test autonomous behavior evaluation based on enhanced needs and personality."""
    
    def test_low_responsibility_theft_behavior(self):
        """Test that NPCs with low responsibility consider theft when poor and opportunity exists."""
        world = World()
        
        # Create a room with valuable objects
        room = Room(id="test_room", description="Test room")
        valuable_obj = Object(display_name="Gold Ring", value=50)
        room.objects = {"ring1": valuable_obj}
        world.rooms["test_room"] = room
        
        # Create NPC with low responsibility and high wealth desire
        sheet = CharacterSheet("ThiefNPC")
        sheet.responsibility = 20  # Very low responsibility
        sheet.wealth_desire = 80.0  # High desire for wealth
        sheet.currency = 5  # Poor
        world.npc_sheets["ThiefNPC"] = sheet
        room.npcs.add("ThiefNPC")
        
        # Evaluate autonomous behavior
        actions = evaluate_npc_autonomy(world, "ThiefNPC", "test_room")
        
        # Should consider theft due to low responsibility + high wealth desire + opportunity
        theft_actions = [a for a in actions if a.get('tool') == 'steal_object']
        assert len(theft_actions) > 0
        assert theft_actions[0]['args']['target'] == "Gold Ring"
        assert theft_actions[0]['priority'] > 50  # Should be high priority
    
    def test_high_responsibility_no_theft(self):
        """Test that NPCs with high responsibility don't consider theft."""
        world = World()
        
        # Create same setup as theft test
        room = Room(id="test_room", description="Test room")
        valuable_obj = Object(display_name="Gold Ring", value=50)
        room.objects = {"ring1": valuable_obj}
        world.rooms["test_room"] = room
        
        # Create NPC with HIGH responsibility despite high wealth desire
        sheet = CharacterSheet("HonestNPC")
        sheet.responsibility = 80  # Very high responsibility
        sheet.wealth_desire = 80.0  # High desire for wealth
        sheet.currency = 5  # Poor (same as thief)
        world.npc_sheets["HonestNPC"] = sheet
        room.npcs.add("HonestNPC")
        
        # Evaluate autonomous behavior
        actions = evaluate_npc_autonomy(world, "HonestNPC", "test_room")
        
        # Should NOT consider theft despite opportunity and desire
        theft_actions = [a for a in actions if a.get('tool') == 'steal_object']
        assert len(theft_actions) == 0
    
    def test_curiosity_drives_exploration(self):
        """Test that NPCs with high curiosity explore new objects and areas."""
        world = World()
        
        # Create room with unexplored objects and exits
        room = Room(id="test_room", description="Test room")
        mysterious_obj = Object(display_name="Strange Artifact")
        room.objects = {"artifact1": mysterious_obj}
        room.doors = {"north_door": "other_room"}
        world.rooms["test_room"] = room
        
        # Create curious NPC
        sheet = CharacterSheet("ExplorerNPC")
        sheet.curiosity = 80  # Very curious
        sheet.confidence = 60  # Confident enough to explore
        world.npc_sheets["ExplorerNPC"] = sheet
        room.npcs.add("ExplorerNPC")
        
        # Evaluate autonomous behavior
        actions = evaluate_npc_autonomy(world, "ExplorerNPC", "test_room")
        
        # Should want to investigate objects and explore areas
        investigate_actions = [a for a in actions if a.get('tool') == 'investigate_object']
        explore_actions = [a for a in actions if a.get('tool') == 'explore_area']
        
        assert len(investigate_actions) > 0
        assert investigate_actions[0]['args']['target'] == "Strange Artifact"
        assert len(explore_actions) > 0
    
    def test_low_curiosity_no_exploration(self):
        """Test that NPCs with low curiosity don't explore much."""
        world = World()
        
        # Same setup as curious NPC test
        room = Room(id="test_room", description="Test room")
        mysterious_obj = Object(display_name="Strange Artifact")
        room.objects = {"artifact1": mysterious_obj}
        room.doors = {"north_door": "other_room"}
        world.rooms["test_room"] = room
        
        # Create incurious NPC
        sheet = CharacterSheet("BoringNPC")
        sheet.curiosity = 20  # Very low curiosity
        sheet.confidence = 60  # Still confident, but not curious
        world.npc_sheets["BoringNPC"] = sheet
        room.npcs.add("BoringNPC")
        
        # Evaluate autonomous behavior
        actions = evaluate_npc_autonomy(world, "BoringNPC", "test_room")
        
        # Should NOT want to investigate or explore
        investigate_actions = [a for a in actions if a.get('tool') == 'investigate_object']
        explore_actions = [a for a in actions if a.get('tool') == 'explore_area']
        
        assert len(investigate_actions) == 0
        assert len(explore_actions) == 0


class TestMemorySystem:
    """Test the NPC memory and relationship system."""
    
    def test_add_memory(self):
        """Test adding memories to an NPC."""
        sheet = CharacterSheet("TestNPC")
        
        # Add a memory
        add_memory(sheet, "conversation", {
            "participant": "PlayerName",
            "topic": "weather",
            "location": "tavern"
        })
        
        assert len(sheet.memories) == 1
        memory = sheet.memories[0]
        assert memory['type'] == "conversation"
        assert memory['participant'] == "PlayerName"
        assert memory['topic'] == "weather"
        assert 'timestamp' in memory
    
    def test_memory_limit(self):
        """Test that memory system limits total memories."""
        sheet = CharacterSheet("TestNPC")
        
        # Add more memories than the limit
        for i in range(55):  # Default limit is 50
            add_memory(sheet, "test", {"number": i})
        
        # Should only keep the most recent 50
        assert len(sheet.memories) == 50
        assert sheet.memories[0]['number'] == 5  # Should have removed first 5
        assert sheet.memories[-1]['number'] == 54  # Should have kept the last one
    
    def test_relationship_updates(self):
        """Test updating relationship scores."""
        sheet = CharacterSheet("TestNPC")
        
        # Start with neutral relationship
        assert sheet.relationships.get("player1", 0.0) == 0.0
        
        # Positive interaction
        update_relationship(sheet, "player1", 25.0)
        assert sheet.relationships["player1"] == 25.0
        
        # Another positive interaction
        update_relationship(sheet, "player1", 30.0)
        assert sheet.relationships["player1"] == 55.0
        
        # Negative interaction
        update_relationship(sheet, "player1", -20.0)
        assert sheet.relationships["player1"] == 35.0
        
        # Test bounds (should cap at -100 to +100)
        update_relationship(sheet, "player1", 100.0)
        assert sheet.relationships["player1"] == 100.0  # Should cap at 100
        
        update_relationship(sheet, "player1", -250.0)
        assert sheet.relationships["player1"] == -100.0  # Should cap at -100


class TestPersonalityModifiers:
    """Test personality trait modifiers for decision-making."""
    
    def test_personality_modifiers(self):
        """Test that personality traits generate correct modifiers."""
        sheet = CharacterSheet("TestNPC")
        
        # Test default (50) should give 0.0 modifier
        assert get_personality_modifier(sheet, 'responsibility') == 0.0
        
        # Test extremes
        sheet.responsibility = 0
        assert get_personality_modifier(sheet, 'responsibility') == -1.0
        
        sheet.responsibility = 100
        assert get_personality_modifier(sheet, 'responsibility') == 1.0
        
        # Test mid-values
        sheet.aggression = 75
        assert get_personality_modifier(sheet, 'aggression') == 0.5
        
        sheet.confidence = 25
        assert get_personality_modifier(sheet, 'confidence') == -0.5


if __name__ == "__main__":
    pytest.main([__file__])