"""
Test suite for GOAP state manager - ensuring planner integrity and cleanup.

This test suite validates that the GOAP state management system properly handles
state transitions, cleanup operations, and integrity validation. It ensures that
NPCs don't get stuck with partially corrupted planner state when advanced GOAP
is toggled or when worlds are reloaded.

Test categories:
    - NPC state validation (plan queues, needs, action points)
    - GOAP mode transitions (advanced AI ↔ offline heuristics)
    - Cache cleanup (rate limiting, planner artifacts)
    - World reload integrity (ensuring clean slate)
    - Error recovery (corrupted state repair)
"""

import pytest
from unittest.mock import patch

# Import the modules we're testing
from goap_state_manager import (
    validate_npc_planner_state,
    clean_npc_planner_state,
    reset_goap_mode_safely,
    cleanup_planner_caches,
    audit_world_planner_integrity,
    on_world_reload_cleanup
)
from world import World, CharacterSheet


class TestNPCStateValidation:
    """Test validation of individual NPC planner states."""
    
    def test_validate_empty_world(self):
        """Test validation with empty or None world."""
        is_valid, issues = validate_npc_planner_state(None)
        assert not is_valid
        assert "World or NPC sheets missing" in issues
        
        world = World()
        world.npc_sheets = {}
        is_valid, issues = validate_npc_planner_state(world)
        assert is_valid
        assert len(issues) == 0
    
    def test_validate_healthy_npc_state(self):
        """Test validation of a properly configured NPC."""
        world = World()
        
        # Create a healthy NPC
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = [
            {"tool": "eat", "args": {"target": "apple"}},
            {"tool": "sleep", "args": {"duration": 8}}
        ]
        npc.hunger = 75.0
        npc.thirst = 80.0
        npc.socialization = 90.0
        npc.sleep = 65.0
        npc.action_points = 3
        npc.sleeping_ticks_remaining = 0
        npc.sleeping_bed_uuid = None
        
        world.npc_sheets = {"TestNPC": npc}
        
        is_valid, issues = validate_npc_planner_state(world)
        assert is_valid, f"Validation failed: {issues}"
        assert len(issues) == 0
    
    def test_validate_corrupted_plan_queue(self):
        """Test detection of corrupted plan queue structures."""
        world = World()
        npc = CharacterSheet("TestNPC")
        
        # Test various corruption patterns
        corruption_tests = [
            # Plan queue is not a list
            {"plan_queue": "invalid", "expected_issue": "invalid plan_queue type"},
            
            # Action is not a dict
            {"plan_queue": ["invalid_action"], "expected_issue": "is not a dict"},
            
            # Action missing tool key
            {"plan_queue": [{"args": {}}], "expected_issue": "missing 'tool' key"},
            
            # Tool is not a string
            {"plan_queue": [{"tool": 123, "args": {}}], "expected_issue": "tool is not string"},
            
            # Args is not a dict
            {"plan_queue": [{"tool": "eat", "args": "invalid"}],
             "expected_issue": "args is not dict"}
        ]
        
        for test_case in corruption_tests:
            npc.plan_queue = test_case["plan_queue"]
            world.npc_sheets = {"TestNPC": npc}
            
            is_valid, issues = validate_npc_planner_state(world)
            assert not is_valid, f"Should have detected corruption: {test_case}"
            
            found_expected = any(test_case["expected_issue"] in issue for issue in issues)
            expected_msg = test_case['expected_issue']
            assert found_expected, f"Expected issue '{expected_msg}' not found in: {issues}"
    
    def test_validate_needs_out_of_range(self):
        """Test detection of needs values outside valid ranges."""
        world = World()
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = []
        
        # Test needs out of range
        invalid_needs_tests = [
            {"hunger": -10.0, "expected": "hunger out of range"},
            {"thirst": 150.0, "expected": "thirst out of range"},
            {"socialization": "invalid", "expected": "socialization is not numeric"},
            {"sleep": None, "expected": "sleep is not numeric"}
        ]
        
        for test_case in invalid_needs_tests:
            # Reset to valid values
            npc.hunger = 50.0
            npc.thirst = 50.0
            npc.socialization = 50.0
            npc.sleep = 50.0
            
            # Apply the test corruption
            for need_name, value in test_case.items():
                if need_name != "expected":
                    setattr(npc, need_name, value)
            
            world.npc_sheets = {"TestNPC": npc}
            
            is_valid, issues = validate_npc_planner_state(world)
            assert not is_valid, f"Should detect invalid need: {test_case}"
            
            found_expected = any(test_case["expected"] in issue for issue in issues)
            assert found_expected, f"Expected '{test_case['expected']}' in issues: {issues}"
    
    def test_validate_sleep_state_inconsistency(self):
        """Test detection of inconsistent sleep states."""
        world = World()
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = []
        npc.hunger = npc.thirst = npc.socialization = npc.sleep = 50.0
        
        # Test: sleeping but no bed
        npc.sleeping_ticks_remaining = 100
        npc.sleeping_bed_uuid = None
        world.npc_sheets = {"TestNPC": npc}
        
        is_valid, issues = validate_npc_planner_state(world)
        assert not is_valid
        assert any("is sleeping but has no bed UUID" in issue for issue in issues)
        
        # Test: has bed but not sleeping
        npc.sleeping_ticks_remaining = 0
        npc.sleeping_bed_uuid = "some-bed-uuid"
        
        is_valid, issues = validate_npc_planner_state(world)
        assert not is_valid
        assert any("has bed UUID but is not sleeping" in issue for issue in issues)


class TestNPCStateCleanup:
    """Test NPC state cleanup and repair functions."""
    
    def test_clean_empty_world(self):
        """Test cleanup with empty world."""
        world = World()
        world.npc_sheets = {}
        
        npcs_cleaned, actions = clean_npc_planner_state(world)
        assert npcs_cleaned == 0
        assert len(actions) == 0
    
    def test_clean_healthy_npc_no_changes(self):
        """Test that healthy NPCs are left unchanged."""
        world = World()
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = [{"tool": "eat", "args": {"target": "apple"}}]
        npc.hunger = 75.0
        npc.thirst = 80.0
        npc.socialization = 90.0
        npc.sleep = 65.0
        npc.action_points = 3
        
        world.npc_sheets = {"TestNPC": npc}
        
        # Clean without forcing resets
        npcs_cleaned, actions = clean_npc_planner_state(world, reset_plans=False,
                                                        reset_needs=False)
        
        assert npcs_cleaned == 0  # No issues to clean
        assert len(actions) == 0
        assert npc.plan_queue == [{"tool": "eat", "args": {"target": "apple"}}]
        assert npc.hunger == 75.0
    
    def test_force_reset_plans(self):
        """Test forced plan queue reset."""
        world = World()
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = [{"tool": "eat", "args": {"target": "apple"}}]
        
        world.npc_sheets = {"TestNPC": npc}
        
        # Force reset plans
        npcs_cleaned, actions = clean_npc_planner_state(world, reset_plans=True, reset_needs=False)
        
        assert npcs_cleaned == 1
        assert npc.plan_queue == []
        assert any("Reset plan queue for NPC 'TestNPC'" in action for action in actions)
    
    def test_force_reset_needs(self):
        """Test forced needs reset."""
        world = World()
        npc = CharacterSheet("TestNPC")
        npc.hunger = 25.0
        npc.thirst = 30.0
        npc.socialization = 40.0
        npc.sleep = 20.0
        
        world.npc_sheets = {"TestNPC": npc}
        
        # Force reset needs
        npcs_cleaned, actions = clean_npc_planner_state(world, reset_plans=False, reset_needs=True)
        
        assert npcs_cleaned == 1
        assert npc.hunger == 100.0
        assert npc.thirst == 100.0
        assert npc.socialization == 100.0
        assert npc.sleep == 100.0
        assert any("Reset needs for NPC 'TestNPC'" in action for action in actions)
    
    def test_clean_corrupted_plan_queue(self):
        """Test cleanup of corrupted plan queues."""
        world = World()
        npc = CharacterSheet("TestNPC")
        
        # Mix valid and invalid actions
        npc.plan_queue = [
            {"tool": "eat", "args": {"target": "apple"}},  # Valid
            "invalid_action",  # Invalid
            {"tool": "sleep"},  # Valid (missing args is okay)
            {"args": {"target": "water"}},  # Invalid (missing tool)
            {"tool": 123, "args": {}}  # Invalid (tool not string)
        ]
        
        world.npc_sheets = {"TestNPC": npc}
        
        npcs_cleaned, actions = clean_npc_planner_state(world, reset_plans=False)
        
        assert npcs_cleaned == 1
        assert len(npc.plan_queue) == 2  # Only valid actions remain
        assert npc.plan_queue[0] == {"tool": "eat", "args": {"target": "apple"}}
        assert npc.plan_queue[1] == {"tool": "sleep"}
        assert any("Cleaned invalid actions" in action for action in actions)
    
    def test_clamp_needs_to_valid_ranges(self):
        """Test clamping of needs values to valid ranges."""
        world = World()
        npc = CharacterSheet("TestNPC")
        
        # Set invalid need values
        npc.hunger = -25.0  # Below 0
        npc.thirst = 150.0  # Above 100
        npc.socialization = "invalid"  # Wrong type
        npc.sleep = 75.0  # Valid
        
        world.npc_sheets = {"TestNPC": npc}
        
        npcs_cleaned, actions = clean_npc_planner_state(world, reset_plans=False,
                                                        reset_needs=False)
        
        assert npcs_cleaned == 1
        assert npc.hunger == 0.0  # Clamped to minimum
        assert npc.thirst == 100.0  # Clamped to maximum
        assert npc.socialization == 100.0  # Reset due to invalid type
        assert npc.sleep == 75.0  # Unchanged
        assert any("Clamped need values" in action for action in actions)
    
    def test_fix_sleep_state_inconsistencies(self):
        """Test fixing inconsistent sleep states."""
        world = World()
        
        # Test case 1: Sleeping without bed
        npc1 = CharacterSheet("TestNPC")
        npc1.sleeping_ticks_remaining = 100
        npc1.sleeping_bed_uuid = None
        
        # Test case 2: Has bed but not sleeping
        npc2 = CharacterSheet("TestNPC")
        npc2.sleeping_ticks_remaining = 0
        npc2.sleeping_bed_uuid = "some-bed-uuid"
        
        world.npc_sheets = {"NPC1": npc1, "NPC2": npc2}
        
        npcs_cleaned, actions = clean_npc_planner_state(world, reset_plans=False)
        
        assert npcs_cleaned == 2
        
        # NPC1 should stop sleeping
        assert npc1.sleeping_ticks_remaining == 0
        assert any("Stopped invalid sleep state for NPC 'NPC1'" in action for action in actions)
        
        # NPC2 should have bed reference cleared
        assert npc2.sleeping_bed_uuid is None
        assert any("Cleared orphaned bed reference for NPC 'NPC2'" in action for action in actions)


class TestGOAPModeTransitions:
    """Test safe transitions between GOAP modes."""
    
    def test_mode_no_change_validation_only(self):
        """Test when mode doesn't change but validation is needed."""
        world = World()
        world.advanced_goap_enabled = True
        
        # Add NPC with valid state
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = [{"tool": "eat", "args": {"target": "apple"}}]
        world.npc_sheets = {"TestNPC": npc}
        
        success, actions = reset_goap_mode_safely(world, True)  # Same mode
        
        assert success
        assert any("GOAP mode already set to True" in action for action in actions)
        # Plan should remain unchanged since it's valid
        assert npc.plan_queue == [{"tool": "eat", "args": {"target": "apple"}}]
    
    def test_mode_change_clears_plans(self):
        """Test that changing modes clears all plan queues."""
        world = World()
        world.advanced_goap_enabled = False
        
        # Add NPCs with existing plans
        npc1 = CharacterSheet("TestNPC")
        npc1.plan_queue = [{"tool": "eat", "args": {}}]

        npc2 = CharacterSheet("TestNPC")
        npc2.plan_queue = [{"tool": "sleep", "args": {}}, {"tool": "drink", "args": {}}]
        
        world.npc_sheets = {"NPC1": npc1, "NPC2": npc2}
        
        success, actions = reset_goap_mode_safely(world, True)  # Change to advanced
        
        assert success
        assert world.advanced_goap_enabled is True
        
        # All plan queues should be cleared
        assert npc1.plan_queue == []
        assert npc2.plan_queue == []
        
        # Should see clear actions for both NPCs
        assert any("Cleared plan queue for NPC 'NPC1'" in action for action in actions)
        assert any("Cleared plan queue for NPC 'NPC2'" in action for action in actions)
        assert any("advanced AI GOAP" in action for action in actions)
    
    def test_mode_change_to_offline_planning(self):
        """Test switching from advanced to offline planning."""
        world = World()
        world.advanced_goap_enabled = True

        npc = CharacterSheet("TestNPC")
        npc.plan_queue = [{"tool": "complex_ai_action", "args": {"reasoning": "advanced"}}]
        world.npc_sheets = {"TestNPC": npc}
        
        success, actions = reset_goap_mode_safely(world, False)  # Change to offline
        
        assert success
        assert world.advanced_goap_enabled is False
        assert npc.plan_queue == []  # Plan cleared during transition
        assert any("offline heuristic planning" in action for action in actions)
    
    def test_mode_change_with_corrupted_state_cleanup(self):
        """Test mode change when NPCs have corrupted state that needs cleanup."""
        world = World()
        world.advanced_goap_enabled = False

        npc = CharacterSheet("TestNPC")
        npc.plan_queue = ["invalid_action", {"tool": "eat"}]  # Mixed valid/invalid
        npc.hunger = -50.0  # Invalid need value
        
        world.npc_sheets = {"TestNPC": npc}
        
        success, actions = reset_goap_mode_safely(world, True)
        
        assert success
        assert world.advanced_goap_enabled is True
        assert npc.plan_queue == []  # Cleared during mode transition
        assert npc.hunger == 0.0  # Fixed during cleanup
        
        # Should see both transition and cleanup actions
        assert any("advanced AI GOAP" in action for action in actions)
        assert any("Cleaned up residual state" in action for action in actions)


class TestCacheCleanup:
    """Test cleanup of planner-related caches."""
    
    @patch('rate_limiter.cleanup_rate_limiter')
    @patch('rate_limiter.cleanup_npc_planning_rate_limits')
    def test_cache_cleanup_general_fallback(self, mock_cleanup_npc, mock_cleanup):
        """Test general cache cleanup when introspection fails."""
        # Make NPC cleanup fail to trigger fallback
        mock_cleanup_npc.side_effect = Exception("NPC cleanup failed")
        mock_cleanup.return_value = None
        
        caches_cleaned, actions = cleanup_planner_caches()
        
        assert caches_cleaned >= 1  # At least the general cleanup
        assert any("general rate limiter cleanup" in action for action in actions)
        mock_cleanup.assert_called_once()
    
    @patch('rate_limiter.cleanup_npc_planning_rate_limits')
    def test_cache_cleanup_specific_keys(self, mock_cleanup_npc):
        """Test cleanup of specific NPC planning keys."""
        # Mock that some NPC planning keys were cleaned
        mock_cleanup_npc.return_value = 3
        
        caches_cleaned, actions = cleanup_planner_caches()
        
        # Should have cleaned up found keys
        assert caches_cleaned == 3
        assert any("Cleaned 3 NPC planning rate limits" in action for action in actions)
        mock_cleanup_npc.assert_called_once()


class TestWorldAudit:
    """Test comprehensive world audit functionality."""
    
    def test_audit_empty_world(self):
        """Test auditing an empty world."""
        world = World()
        world.npc_sheets = {}
        world.advanced_goap_enabled = False
        
        audit = audit_world_planner_integrity(world)
        
        assert audit["total_npcs"] == 0
        assert audit["npcs_with_plans"] == 0
        assert audit["npcs_with_invalid_plans"] == 0
        assert audit["npcs_sleeping"] == 0
        assert audit["npcs_with_invalid_needs"] == 0
        assert audit["is_valid"] is True
        assert audit["health_score"] == 100.0  # Perfect health for empty world
    
    def test_audit_healthy_world(self):
        """Test auditing a world with healthy NPCs."""
        world = World()
        world.advanced_goap_enabled = True
        
        # Add healthy NPCs
        for i in range(3):
            npc_name = f"NPC_{i}"
            npc = CharacterSheet(npc_name)
            npc.plan_queue = [{"tool": "eat", "args": {"target": f"food_{i}"}}]
            npc.hunger = 50.0 + i * 10
            npc.thirst = 60.0 + i * 5
            npc.socialization = 70.0 + i * 3
            npc.sleep = 80.0 + i * 2
            npc.action_points = i + 1
            world.npc_sheets[npc_name] = npc
        
        audit = audit_world_planner_integrity(world)
        
        assert audit["total_npcs"] == 3
        assert audit["npcs_with_plans"] == 3
        assert audit["npcs_with_invalid_plans"] == 0
        assert audit["npcs_with_invalid_needs"] == 0
        assert audit["is_valid"] is True
        assert audit["health_score"] >= 95.0  # Should be very healthy
        
        # Check individual NPC details
        for i in range(3):
            npc_detail = audit["npc_details"][f"NPC_{i}"]
            assert npc_detail["has_plan"] is True
            assert npc_detail["plan_length"] == 1
            assert npc_detail["needs_valid"] is True
            assert npc_detail["plan_valid"] is True
    
    def test_audit_problematic_world(self):
        """Test auditing a world with various problems."""
        world = World()
        world.advanced_goap_enabled = False
        
        # NPC with invalid plan
        npc1 = CharacterSheet("TestNPC")
        npc1.plan_queue = ["invalid_action"]
        npc1.hunger = npc1.thirst = npc1.socialization = npc1.sleep = 50.0
        
        # NPC with invalid needs
        npc2 = CharacterSheet("TestNPC")
        npc2.plan_queue = []
        npc2.hunger = -25.0  # Invalid
        npc2.thirst = 150.0  # Invalid
        npc2.socialization = 50.0
        npc2.sleep = 50.0
        
        # NPC with sleep inconsistency
        npc3 = CharacterSheet("TestNPC")
        npc3.plan_queue = []
        npc3.hunger = npc3.thirst = npc3.socialization = npc3.sleep = 50.0
        npc3.sleeping_ticks_remaining = 100
        npc3.sleeping_bed_uuid = None  # Inconsistent
        
        world.npc_sheets = {"NPC1": npc1, "NPC2": npc2, "NPC3": npc3}
        
        audit = audit_world_planner_integrity(world)
        
        assert audit["total_npcs"] == 3
        assert audit["npcs_with_invalid_plans"] == 1  # NPC1
        assert audit["npcs_with_invalid_needs"] == 1  # NPC2
        assert audit["is_valid"] is False  # Should detect problems
        assert audit["health_score"] < 50.0  # Should be unhealthy
        assert len(audit["validation_issues"]) > 0


class TestWorldReloadCleanup:
    """Test the comprehensive world reload cleanup process."""
    
    @patch('goap_state_manager.cleanup_planner_caches')
    def test_world_reload_full_process(self, mock_cache_cleanup):
        """Test the complete world reload cleanup process."""
        # Mock cache cleanup
        mock_cache_cleanup.return_value = (2, ["Cleaned cache A", "Cleaned cache B"])
        
        world = World()
        world.advanced_goap_enabled = True
        
        # Add NPC with some issues that need cleanup
        npc = CharacterSheet("TestNPC")
        npc.plan_queue = [{"tool": "eat", "args": {}}]  # Valid plan
        npc.hunger = -10.0  # Invalid need (will be clamped)
        npc.thirst = 150.0  # Invalid need (will be clamped)
        npc.socialization = 50.0
        npc.sleep = 50.0
        
        world.npc_sheets = {"TestNPC": npc}
        
        actions = on_world_reload_cleanup(world)
        
        # Should have performed all cleanup steps
        assert len(actions) > 0
        
        # Cache cleanup should have been called
        mock_cache_cleanup.assert_called_once()
        
        # Should see cache cleanup actions
        assert any("Cleaned cache" in action for action in actions)
        
        # NPC needs should be fixed
        assert 0.0 <= npc.hunger <= 100.0
        assert 0.0 <= npc.thirst <= 100.0
        
        # Should see completion message with health score
        completion_actions = [action for action in actions if "Health score" in action]
        assert len(completion_actions) == 1
    
    @patch('goap_state_manager.cleanup_planner_caches')  
    def test_world_reload_with_errors(self, mock_cache_cleanup):
        """Test world reload cleanup when errors occur."""
        # Make cache cleanup raise an exception
        mock_cache_cleanup.side_effect = Exception("Cache cleanup failed")
        
        world = World()
        world.npc_sheets = {}
        
        actions = on_world_reload_cleanup(world)
        
        # Should handle the error gracefully
        assert any("Cleanup error" in action for action in actions)
        
        # But still complete what it can
        assert any("Health score" in action for action in actions)


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
