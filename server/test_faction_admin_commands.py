"""
Test suite for the new faction admin commands.

This module tests the faction management commands that allow admins to create,
modify, and manage faction relationships in TinyMUD. These commands enable
dynamic political gameplay through organized groups of players and NPCs.
"""

import pytest
from world import World
from faction_service import handle_faction_command


class TestFactionAdminCommands:
    """Test the comprehensive faction admin command suite."""

    def setup_method(self):
        """Set up a fresh world for each test with some baseline data."""
        self.world = World()
        self.state_path = "/tmp/test_world.json"
        
        # Create some test users (players)
        self.alice_user = self.world.create_user("Alice", "password123", "A brave warrior")
        self.bob_user = self.world.create_user("Bob", "password456", "A clever mage")
        
        # Create some test NPCs
        from world import CharacterSheet
        self.world.npc_sheets["Guard Captain"] = CharacterSheet("Guard Captain", "A stern military leader")
        self.world.npc_sheets["Merchant"] = CharacterSheet("Merchant", "A traveling trader")
        
        # Ensure NPC IDs exist
        self.guard_id = self.world.get_or_create_npc_id("Guard Captain")
        self.merchant_id = self.world.get_or_create_npc_id("Merchant")

    def test_addfaction_creates_new_faction(self):
        """Test that /faction addfaction creates a new faction properly."""
        args = ["addfaction", "Knights", "|", "Noble warriors of the realm"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Created faction" in emits[0]['content']
        assert "Knights" in emits[0]['content']
        
        # Verify faction was actually created
        faction = self.world.get_faction_by_name("Knights")
        assert faction is not None
        assert faction.name == "Knights"
        assert faction.description == "Noble warriors of the realm"

    def test_addfaction_rejects_duplicate_names(self):
        """Test that creating a faction with an existing name fails."""
        # Create first faction
        self.world.create_faction("Test Faction", "First faction")
        
        # Try to create another with same name
        args = ["addfaction", "Test Faction", "|", "Second faction"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error == "Faction 'Test Faction' already exists."

    def test_removefaction_deletes_faction(self):
        """Test that /faction removefaction removes a faction and cleans up references."""
        # Create test faction
        self.world.create_faction("Doomed Faction", "Will be deleted")
        
        # Remove it
        args = ["removefaction", "Doomed Faction"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Removed faction" in emits[0]['content']
        assert "Doomed Faction" in emits[0]['content']
        
        # Verify faction is gone
        assert self.world.get_faction_by_name("Doomed Faction") is None

    def test_addmember_adds_player_to_faction(self):
        """Test adding a player to a faction."""
        faction = self.world.create_faction("Test Guild", "A testing guild")
        
        args = ["addmember", "Test Guild", "|", "Alice"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Added player" in emits[0]['content']
        assert "Alice" in emits[0]['content']
        
        # Verify player was added
        assert faction.is_player_member(self.alice_user.user_id)

    def test_addmember_adds_npc_to_faction(self):
        """Test adding an NPC to a faction."""
        faction = self.world.create_faction("Guard Unit", "Military organization")
        
        args = ["addmember", "Guard Unit", "|", "Guard Captain"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Added NPC" in emits[0]['content']
        assert "Guard Captain" in emits[0]['content']
        
        # Verify NPC was added
        assert faction.is_npc_member(self.guard_id)

    def test_removemember_removes_player_from_faction(self):
        """Test removing a player from a faction."""
        faction = self.world.create_faction("Test Guild", "A testing guild")
        faction.add_member_player(self.alice_user.user_id)
        
        args = ["removemember", "Test Guild", "|", "Alice"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Removed player" in emits[0]['content']
        assert "Alice" in emits[0]['content']
        
        # Verify player was removed
        assert not faction.is_player_member(self.alice_user.user_id)

    def test_addally_creates_bidirectional_alliance(self):
        """Test creating an alliance between two factions."""
        faction1 = self.world.create_faction("Knights", "Noble warriors")
        faction2 = self.world.create_faction("Mages", "Arcane scholars")
        
        args = ["addally", "Knights", "|", "Mages"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Created alliance" in emits[0]['content']
        assert "Knights" in emits[0]['content']
        assert "Mages" in emits[0]['content']
        
        # Verify bidirectional alliance
        assert faction1.is_ally(faction2.faction_id)
        assert faction2.is_ally(faction1.faction_id)

    def test_addrival_creates_bidirectional_rivalry(self):
        """Test creating a rivalry between two factions."""
        faction1 = self.world.create_faction("Order", "Forces of light")
        faction2 = self.world.create_faction("Chaos", "Forces of darkness")
        
        args = ["addrival", "Order", "|", "Chaos"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Created rivalry" in emits[0]['content']
        assert "Order" in emits[0]['content']
        assert "Chaos" in emits[0]['content']
        
        # Verify bidirectional rivalry
        assert faction1.is_rival(faction2.faction_id)
        assert faction2.is_rival(faction1.faction_id)

    def test_removeally_breaks_alliance(self):
        """Test removing an alliance between factions."""
        faction1 = self.world.create_faction("Former Allies 1", "Description")
        faction2 = self.world.create_faction("Former Allies 2", "Description")
        
        # Create alliance first
        faction1.add_ally(faction2.faction_id)
        faction2.add_ally(faction1.faction_id)
        
        args = ["removeally", "Former Allies 1", "|", "Former Allies 2"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Removed alliance" in emits[0]['content']
        
        # Verify alliance is gone
        assert not faction1.is_ally(faction2.faction_id)
        assert not faction2.is_ally(faction1.faction_id)

    def test_removerival_breaks_rivalry(self):
        """Test removing a rivalry between factions."""
        faction1 = self.world.create_faction("Former Rivals 1", "Description")
        faction2 = self.world.create_faction("Former Rivals 2", "Description")
        
        # Create rivalry first
        faction1.add_rival(faction2.faction_id)
        faction2.add_rival(faction1.faction_id)
        
        args = ["removerival", "Former Rivals 1", "|", "Former Rivals 2"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert len(emits) == 1
        assert "Removed rivalry" in emits[0]['content']
        
        # Verify rivalry is gone
        assert not faction1.is_rival(faction2.faction_id)
        assert not faction2.is_rival(faction1.faction_id)

    def test_fuzzy_faction_resolution(self):
        """Test that faction names are resolved using fuzzy matching."""
        self.world.create_faction("Knights of the Round Table", "Arthurian knights")
        
        # Test partial name matching
        args = ["addmember", "knights", "|", "Alice"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert "Knights of the Round Table" in str(emits[0]['content'])

    def test_fuzzy_entity_resolution(self):
        """Test that player/NPC names are resolved using fuzzy matching."""
        faction = self.world.create_faction("Test Faction", "Description")
        
        # Test partial NPC name matching
        args = ["addmember", "Test Faction", "|", "guard"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is None
        assert "Guard Captain" in emits[0]['content']

    def test_self_relationship_prevention(self):
        """Test that factions cannot be allied or rival with themselves."""
        faction = self.world.create_faction("Self Test", "Testing self-relationships")
        
        # Test self-alliance prevention
        args = ["addally", "Self Test", "|", "Self Test"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error == "A faction cannot be allied with itself."
        
        # Test self-rivalry prevention
        args = ["addrival", "Self Test", "|", "Self Test"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error == "A faction cannot be rival with itself."

    def test_command_without_args_shows_usage(self):
        """Test that calling /faction without arguments shows usage help."""
        args = []
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error is not None
        assert "Usage: /faction" in error
        assert "addfaction" in error
        assert "addmember" in error

    def test_unknown_subcommand_returns_false(self):
        """Test that unknown subcommands return handled=False for proper routing."""
        args = ["unknowncommand", "arg1", "arg2"]
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is False
        assert error is None

    def test_malformed_pipe_syntax_handling(self):
        """Test graceful handling of malformed pipe syntax in commands."""
        args = ["addfaction", "incomplete"]  # Missing pipe and description
        handled, error, emits, broadcasts = handle_faction_command(
            self.world, self.state_path, "test_sid", args
        )
        
        assert handled is True
        assert error == "Usage: /faction addfaction <name> | <description>"


if __name__ == "__main__":
    # Run the tests directly if this file is executed
    pytest.main([__file__, "-v"])