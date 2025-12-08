#!/usr/bin/env python3
"""
Unit tests for NPC integrity validation functionality.
"""

from world import World, CharacterSheet


def test_npc_integrity_validation_empty_world():
    """Test NPC integrity validation on an empty world."""
    world = World()
    
    errors = world.validate_npc_integrity()
    assert len(errors) == 0, "Empty world should have no NPC integrity errors"


def test_npc_integrity_validation_orphaned_sheet():
    """Test detection of NPC sheet without corresponding ID mapping."""
    world = World()
    
    # Add a sheet without ID mapping (proper structure: name -> sheet)
    world.npc_sheets["Test NPC"] = CharacterSheet(display_name="Test NPC")
    
    errors = world.validate_npc_integrity()
    assert len(errors) == 1
    assert "missing from npc_ids mapping" in errors[0]
    assert "Test NPC" in errors[0]


def test_npc_integrity_validation_orphaned_id():
    """Test detection of NPC ID mapping without corresponding sheet."""
    world = World()
    
    # Add ID mapping without sheet
    world.npc_ids["Orphaned NPC"] = "orphan-uuid-456"
    
    errors = world.validate_npc_integrity()
    assert len(errors) >= 1  # At least missing sheet error
    error_messages = " ".join(errors)
    assert "missing character sheet" in error_messages


def test_npc_integrity_repair_missing_sheet():
    """Test repair of missing character sheet."""
    world = World()
    
    # Add ID mapping without sheet
    world.npc_ids["Test NPC"] = "valid-uuid-format-here"
    
    repairs_count, repair_messages = world.repair_npc_integrity()
    assert repairs_count == 1
    assert len(repair_messages) == 1
    assert "Created missing character sheet" in repair_messages[0]
    assert "Test NPC" in repair_messages[0]
    
    # Verify sheet was created
    assert "Test NPC" in [sheet.display_name for sheet in world.npc_sheets.values()]


def test_npc_integrity_repair_missing_id():
    """Test repair of missing ID mapping."""
    world = World()
    
    # Add sheet without ID mapping (proper structure: name -> sheet)
    world.npc_sheets["Test NPC"] = CharacterSheet(display_name="Test NPC")
    
    repairs_count, repair_messages = world.repair_npc_integrity()
    assert repairs_count == 1
    assert len(repair_messages) == 1
    assert "Created missing ID mapping" in repair_messages[0]
    assert "Test NPC" in repair_messages[0]
    
    # Verify ID mapping was created (maps display_name -> uuid)
    assert "Test NPC" in world.npc_ids


def test_npc_integrity_in_main_validation():
    """Test that NPC integrity validation is included in main World.validate()."""
    world = World()
    
    # Create NPC integrity issues (proper structure)
    world.npc_sheets["Test NPC"] = CharacterSheet(display_name="Test NPC")
    world.npc_ids["Orphaned NPC"] = "invalid-uuid"
    
    # Main validation should include NPC integrity errors
    all_errors = world.validate()
    npc_errors = [e for e in all_errors if 'NPC' in e or 'character' in e.lower()]
    
    assert len(npc_errors) >= 2, "Main validation should include NPC integrity errors"


def test_enhanced_get_or_create_npc_id_validation():
    """Test the enhanced get_or_create_npc_id with proper input validation."""
    world = World()
    
    # Test with valid input
    npc_id1 = world.get_or_create_npc_id("Valid NPC")
    assert npc_id1 is not None
    assert "Valid NPC" in world.npc_ids
    
    # Test with empty string should raise ValueError
    try:
        world.get_or_create_npc_id("")
        assert False, "Should have raised ValueError for empty string"
    except ValueError as e:
        assert "empty or whitespace-only" in str(e)
    
    # Test with None should raise TypeError
    try:
        world.get_or_create_npc_id(None)  # type: ignore
        assert False, "Should have raised TypeError for None"
    except TypeError as e:
        assert "must be a string" in str(e)