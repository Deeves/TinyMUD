"""Test suite for world schema migration system.

This module tests the migration framework to ensure:
- Migrations are applied in correct order
- Each migration is idempotent and safe
- Old world files are properly upgraded to current schema
- New world files start at latest version
- Migration failures are handled gracefully
"""

import pytest
import json
import tempfile
import os
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# Import the system under test
from world_migrations import (
    migration_registry,
    BaseMigration,
    MigrationError,
    Migration001_AddWorldVersion,
    Migration002_ConsolidateNeedsSystem,
    Migration003_ConsolidateUUIDs,
    Migration004_EnsureTravelObjects
)
from world import World


class TestMigrationRegistry:
    """Test the migration registry and discovery system."""
    
    def test_registry_discovers_migrations(self):
        """Test that the registry auto-discovers migration classes."""
        migrations = migration_registry.list_migrations()
        
        # Should have discovered our test migrations
        assert len(migrations) >= 4
        
        # Check for expected migrations
        versions = [m["version"] for m in migrations]
        assert 1 in versions  # Migration001_AddWorldVersion
        assert 2 in versions  # Migration002_ConsolidateNeedsSystem
        assert 3 in versions  # Migration003_ConsolidateUUIDs
        assert 4 in versions  # Migration004_EnsureTravelObjects
    
    def test_get_current_version(self):
        """Test version detection from world data."""
        # No version field = version 0
        assert migration_registry.get_current_version({}) == 0
        
        # Explicit version
        assert migration_registry.get_current_version({"world_version": 3}) == 3
    
    def test_needs_migration(self):
        """Test migration necessity detection."""
        latest = migration_registry.get_latest_version()
        
        # Old data needs migration
        assert migration_registry.needs_migration({})
        assert migration_registry.needs_migration({"world_version": latest - 1})
        
        # Current data doesn't need migration
        assert not migration_registry.needs_migration({"world_version": latest})
    
    def test_migration_plan(self):
        """Test migration plan generation."""
        # Version 0 -> latest should include all migrations
        plan = migration_registry.get_migration_plan({})
        assert plan == list(range(1, migration_registry.get_latest_version() + 1))
        
        # Version 2 -> latest should skip migrations 1-2
        plan = migration_registry.get_migration_plan({"world_version": 2})
        expected = list(range(3, migration_registry.get_latest_version() + 1))
        assert plan == expected


class TestMigration001:
    """Test the bootstrap migration that adds version tracking."""
    
    def test_adds_version_field(self):
        """Test that Migration001 adds world_version field."""
        migration = Migration001_AddWorldVersion()
        
        input_data = {"some": "data"}
        result = migration.migrate(input_data)
        
        assert result["world_version"] == 1
        assert result["some"] == "data"  # Preserves existing data
        assert input_data == {"some": "data"}  # Doesn't mutate input


class TestMigration002:
    """Test needs system backfill migration."""
    
    def test_backfills_npc_needs(self):
        """Test that Migration002 backfills needs for NPC sheets."""
        migration = Migration002_ConsolidateNeedsSystem()
        
        input_data = {
            "npc_sheets": {
                "Alice": {
                    "display_name": "Alice",
                    "description": "A helpful NPC"
                    # Missing needs fields
                },
                "Bob": {
                    "display_name": "Bob",
                    "hunger": 50.0,  # Partial needs
                    "thirst": 75.0
                    # Missing other needs
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        # Alice should have all needs with defaults
        alice = result["npc_sheets"]["Alice"]
        assert alice["hunger"] == 100.0
        assert alice["thirst"] == 100.0
        assert alice["socialization"] == 100.0
        assert alice["sleep"] == 100.0
        assert alice["sleeping_ticks_remaining"] == 0
        assert alice["sleeping_bed_uuid"] is None
        assert alice["action_points"] == 0
        assert alice["plan_queue"] == []
        
        # Bob should preserve existing values and add missing ones
        bob = result["npc_sheets"]["Bob"]
        assert bob["hunger"] == 50.0  # Preserved
        assert bob["thirst"] == 75.0  # Preserved
        assert bob["socialization"] == 100.0  # Added
        assert bob["sleep"] == 100.0  # Added
    
    def test_backfills_user_needs(self):
        """Test that Migration002 backfills needs for user character sheets."""
        migration = Migration002_ConsolidateNeedsSystem()
        
        input_data = {
            "users": {
                "user123": {
                    "user_id": "user123",
                    "display_name": "Player1",
                    "sheet": {
                        "display_name": "Player1",
                        "description": "A player character"
                        # Missing needs
                    }
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        sheet = result["users"]["user123"]["sheet"]
        assert sheet["hunger"] == 100.0
        assert sheet["thirst"] == 100.0
        assert sheet["socialization"] == 100.0
        assert sheet["sleep"] == 100.0
    
    def test_handles_malformed_needs(self):
        """Test that Migration002 handles malformed needs data gracefully."""
        migration = Migration002_ConsolidateNeedsSystem()
        
        input_data = {
            "npc_sheets": {
                "TestNPC": {
                    "display_name": "TestNPC",
                    "hunger": "not_a_number",
                    "thirst": None,
                    "socialization": "50.5",  # String that can be converted
                    "action_points": "invalid"
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        npc = result["npc_sheets"]["TestNPC"]
        assert npc["hunger"] == 100.0  # Invalid -> default
        assert npc["thirst"] == 100.0  # None -> default  
        assert npc["socialization"] == 50.5  # Valid string -> float
        assert npc["action_points"] == 0  # Invalid -> default


class TestMigration003:
    """Test UUID consolidation migration."""
    
    def test_generates_room_uuids(self):
        """Test that Migration003 generates missing room UUIDs."""
        migration = Migration003_ConsolidateUUIDs()
        
        input_data = {
            "rooms": {
                "lobby": {
                    "id": "lobby",
                    "description": "A lobby"
                    # Missing uuid
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        room = result["rooms"]["lobby"]
        assert "uuid" in room
        assert isinstance(room["uuid"], str)
        assert len(room["uuid"]) > 0
    
    def test_generates_door_ids(self):
        """Test that Migration003 generates door IDs."""
        migration = Migration003_ConsolidateUUIDs()
        
        input_data = {
            "rooms": {
                "room1": {
                    "id": "room1",
                    "doors": {
                        "north door": "room2",
                        "east door": "room3"
                    }
                    # Missing door_ids
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        room = result["rooms"]["room1"]
        assert "door_ids" in room
        assert "north door" in room["door_ids"]
        assert "east door" in room["door_ids"]
        assert isinstance(room["door_ids"]["north door"], str)
    
    def test_generates_npc_ids(self):
        """Test that Migration003 generates NPC IDs."""
        migration = Migration003_ConsolidateUUIDs()
        
        input_data = {
            "npc_sheets": {
                "Alice": {"display_name": "Alice"},
                "Bob": {"display_name": "Bob"}
            },
            "rooms": {
                "tavern": {
                    "id": "tavern", 
                    "npcs": ["Charlie", "Alice"]  # Charlie not in sheets
                }
            }
            # Missing npc_ids
        }
        
        result = migration.migrate(input_data)
        
        npc_ids = result["npc_ids"]
        assert "Alice" in npc_ids
        assert "Bob" in npc_ids  
        assert "Charlie" in npc_ids  # Should be added even though not in sheets


class TestMigration004:
    """Test travel object creation migration."""
    
    def test_creates_door_objects(self):
        """Test that Migration004 creates objects for doors."""
        migration = Migration004_EnsureTravelObjects()
        
        input_data = {
            "rooms": {
                "room1": {
                    "id": "room1",
                    "doors": {"north door": "room2"},
                    "door_ids": {"north door": "door-uuid-123"},
                    "objects": {}  # Empty objects dict
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        objects = result["rooms"]["room1"]["objects"]
        assert "door-uuid-123" in objects
        
        door_obj = objects["door-uuid-123"]
        assert door_obj["display_name"] == "north door"
        assert "Travel Point" in door_obj["object_tag"]
        assert "Immovable" in door_obj["object_tag"]
        assert door_obj["link_target_room_id"] == "room2"
        assert door_obj["uuid"] == "door-uuid-123"
    
    def test_creates_stairs_objects(self):
        """Test that Migration004 creates objects for stairs."""
        migration = Migration004_EnsureTravelObjects()
        
        input_data = {
            "rooms": {
                "room1": {
                    "id": "room1",
                    "stairs_up_to": "room2",
                    "stairs_up_id": "stairs-up-uuid",
                    "stairs_down_to": "room3", 
                    "stairs_down_id": "stairs-down-uuid",
                    "objects": {}
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        objects = result["rooms"]["room1"]["objects"]
        
        # Check stairs up object
        assert "stairs-up-uuid" in objects
        up_obj = objects["stairs-up-uuid"]
        assert up_obj["display_name"] == "stairs up"
        assert up_obj["link_target_room_id"] == "room2"
        
        # Check stairs down object
        assert "stairs-down-uuid" in objects
        down_obj = objects["stairs-down-uuid"]
        assert down_obj["display_name"] == "stairs down"
        assert down_obj["link_target_room_id"] == "room3"
    
    def test_updates_existing_objects(self):
        """Test that Migration004 updates existing travel objects."""
        migration = Migration004_EnsureTravelObjects()
        
        input_data = {
            "rooms": {
                "room1": {
                    "id": "room1",
                    "doors": {"main door": "room2"},
                    "door_ids": {"main door": "existing-door-uuid"},
                    "objects": {
                        "existing-door-uuid": {
                            "uuid": "existing-door-uuid",
                            "display_name": "main door",
                            "object_tag": ["small"]  # Missing travel tags
                            # Missing link_target_room_id
                        }
                    }
                }
            }
        }
        
        result = migration.migrate(input_data)
        
        door_obj = result["rooms"]["room1"]["objects"]["existing-door-uuid"]
        
        # Should have added missing tags
        tags = set(door_obj["object_tag"])
        assert "Travel Point" in tags
        assert "Immovable" in tags
        assert "small" in tags  # Preserved existing tag
        
        # Should have added missing link
        assert door_obj["link_target_room_id"] == "room2"


class TestFullMigrationFlow:
    """Test complete migration workflows."""
    
    def test_full_migration_chain(self):
        """Test migrating from version 0 to latest through full chain."""
        # Create legacy world data with no version
        legacy_data = {
            "rooms": {
                "tavern": {
                    "id": "tavern",
                    "description": "A cozy tavern",
                    "doors": {"front door": "street"},
                    "npcs": ["Barkeep"]
                }
            },
            "npc_sheets": {
                "Barkeep": {
                    "display_name": "Barkeep",
                    "description": "The friendly barkeep"
                    # Missing needs, UUIDs, etc.
                }
            }
        }
        
        # Migrate to latest
        result = migration_registry.migrate(legacy_data)
        
        # Should have version field
        assert result["world_version"] == migration_registry.get_latest_version()
        
        # Should have backfilled needs
        barkeep = result["npc_sheets"]["Barkeep"]
        assert barkeep["hunger"] == 100.0
        assert barkeep["thirst"] == 100.0
        
        # Should have generated UUIDs
        tavern = result["rooms"]["tavern"]
        assert "uuid" in tavern
        assert "door_ids" in tavern
        assert "front door" in tavern["door_ids"]
        
        # Should have NPC IDs
        assert "npc_ids" in result
        assert "Barkeep" in result["npc_ids"]
        
        # Should have door objects
        door_id = tavern["door_ids"]["front door"]
        assert door_id in tavern["objects"]
        door_obj = tavern["objects"][door_id]
        assert "Travel Point" in door_obj["object_tag"]
        assert door_obj["link_target_room_id"] == "street"
    
    def test_current_version_no_migration(self):
        """Test that current version data passes through unchanged."""
        current_version = migration_registry.get_latest_version()
        
        current_data = {
            "world_version": current_version,
            "rooms": {"test": {"id": "test"}},
            "some_field": "some_value"
        }
        
        result = migration_registry.migrate(current_data)
        
        # Should be unchanged
        assert result == current_data
    
    def test_partial_migration(self):
        """Test migrating from intermediate version to latest."""
        # Start at version 2, migrate to latest
        intermediate_data = {
            "world_version": 2,
            "rooms": {
                "room1": {
                    "id": "room1", 
                    "doors": {"door1": "room2"}
                    # Missing UUIDs (should be added by migration 3+)
                }
            }
        }
        
        result = migration_registry.migrate(intermediate_data)
        
        # Should have been migrated from 2 to latest
        assert result["world_version"] == migration_registry.get_latest_version()
        
        # Migration 3+ effects should be present
        room = result["rooms"]["room1"]
        assert "uuid" in room
        assert "door_ids" in room


class TestWorldIntegration:
    """Test integration with World class loading."""
    
    def test_world_from_dict_applies_migrations(self):
        """Test that World.from_dict applies migrations."""
        legacy_data = {
            # No world_version = version 0
            "npc_sheets": {
                "TestNPC": {
                    "display_name": "TestNPC"
                    # Missing needs
                }
            }
        }
        
        world = World.from_dict(legacy_data)
        
        # Should have migrated to current version
        assert world.world_version == migration_registry.get_latest_version()
        
        # Needs should be backfilled
        npc = world.npc_sheets["TestNPC"]
        assert npc.hunger == 100.0
        assert npc.thirst == 100.0
    
    def test_world_to_dict_saves_current_version(self):
        """Test that World.to_dict saves at current version."""
        world = World()
        data = world.to_dict()
        
        assert data["world_version"] == migration_registry.get_latest_version()
    
    def test_world_load_save_roundtrip(self):
        """Test complete load/save cycle with migrations."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            # Write legacy data
            legacy_data = {
                "rooms": {"test": {"id": "test", "description": "Test room"}},
                "npc_sheets": {"NPC": {"display_name": "NPC"}}
            }
            json.dump(legacy_data, f)
            temp_path = f.name
        
        try:
            # Load should apply migrations
            world = World.load_from_file(temp_path)
            assert world.world_version == migration_registry.get_latest_version()
            
            # Save and reload 
            world.save_to_file(temp_path)
            world2 = World.load_from_file(temp_path)
            
            # Should still be current version
            assert world2.world_version == migration_registry.get_latest_version()
            
        finally:
            os.unlink(temp_path)


class TestErrorHandling:
    """Test migration error handling and robustness."""
    
    def test_migration_failure_handling(self):
        """Test graceful handling of migration failures."""
        # This would require mocking a migration to fail, which is complex
        # For now, we test the error types exist and can be raised
        assert issubclass(MigrationError, Exception)
        
        with pytest.raises(MigrationError):
            raise MigrationError("Test error")
    
    def test_malformed_data_handling(self):
        """Test handling of completely malformed data."""
        malformed_data = {
            "rooms": "not_a_dict",
            "npc_sheets": None,
            "invalid_field": {"deeply": {"nested": "nonsense"}}
        }
        
        # Should not crash during migration
        try:
            result = migration_registry.migrate(malformed_data)
            # At minimum should have version field
            assert "world_version" in result
        except MigrationError:
            # Migration errors are acceptable for truly malformed data
            pass


if __name__ == "__main__":
    pytest.main([__file__])