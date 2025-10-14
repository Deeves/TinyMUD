"""World schema migration system for TinyMUD.

This module provides a clean, versioned migration system to replace the ad-hoc backfill
logic scattered throughout World.from_dict and related methods. Each migration is a
discrete, testable unit that transforms data from one schema version to the next.

Design principles:
- Sequential version numbers starting from 1
- Each migration is idempotent and self-contained
- Migrations run in order from current version to latest
- Clear rollback support for development
- Comprehensive logging of migration activity
- Safe defaults for malformed data

Migration workflow:
1. New world files start at the latest version
2. Old world files are migrated step-by-step to current version
3. Each migration documents what schema changes it handles
4. Migration registry auto-discovers migrations by naming convention
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Type
import uuid

# Configure migration-specific logger
migration_logger = logging.getLogger("world_migrations")


class MigrationError(Exception):
    """Raised when a migration cannot be completed safely."""
    pass


class BaseMigration(ABC):
    """Base class for all world schema migrations.
    
    Each migration transforms the world data dictionary from version N to N+1.
    Migrations must be deterministic and handle malformed data gracefully.
    """
    
    @property
    @abstractmethod
    def version(self) -> int:
        """The version this migration upgrades TO (not from)."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this migration does."""
        pass
    
    @abstractmethod
    def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the migration to world data.
        
        Args:
            data: World data dictionary at version (self.version - 1)
            
        Returns:
            World data dictionary at version self.version
            
        Raises:
            MigrationError: If migration cannot be completed safely
        """
        pass
    
    def validate_preconditions(self, data: Dict[str, Any]) -> bool:
        """Override to add migration-specific validation.
        
        Returns:
            True if data is in correct state for this migration
        """
        return True


class Migration001_AddWorldVersion(BaseMigration):
    """Add world_version field to world data.
    
    This is the bootstrap migration that adds version tracking to existing worlds.
    All worlds without a version field are assumed to be "version 0" and need
    to be migrated through all available migrations.
    """
    
    @property
    def version(self) -> int:
        return 1
    
    @property
    def description(self) -> str:
        return "Add world_version field and basic version tracking"
    
    def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Simply add the version field - no schema changes needed yet
        data = dict(data)  # Copy to avoid mutating input
        data["world_version"] = self.version
        migration_logger.info(f"Applied migration {self.version}: {self.description}")
        return data


class Migration002_ConsolidateNeedsSystem(BaseMigration):
    """Consolidate needs system backfill logic into proper migration.
    
    This migration handles backfilling default values for the needs system
    (hunger, thirst, socialization, sleep) that were previously done ad-hoc
    in CharacterSheet.from_dict().
    """
    
    @property
    def version(self) -> int:
        return 2
    
    @property
    def description(self) -> str:
        return "Backfill needs system defaults for character sheets"
    
    def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(data)  # Copy to avoid mutating input
        
        # Helper to safely convert to float with default
        def _safe_float(val: Any, default: float) -> float:
            if val is None:
                return default
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return default
            return default
        
        # Helper to safely convert to int with default  
        def _safe_int(val: Any, default: int) -> int:
            if val is None:
                return default
            if isinstance(val, int):
                return val
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    return default
            return default
        
        # Migrate NPC sheets
        npc_sheets = data.get("npc_sheets", {})
        if isinstance(npc_sheets, dict):
            for npc_name, sheet_data in npc_sheets.items():
                if isinstance(sheet_data, dict):
                    # Add missing needs fields with healthy defaults
                    sheet_data.setdefault("hunger", 100.0)
                    sheet_data.setdefault("thirst", 100.0) 
                    sheet_data.setdefault("socialization", 100.0)
                    sheet_data.setdefault("sleep", 100.0)
                    sheet_data.setdefault("sleeping_ticks_remaining", 0)
                    sheet_data.setdefault("sleeping_bed_uuid", None)
                    sheet_data.setdefault("action_points", 0)
                    sheet_data.setdefault("plan_queue", [])
                    
                    # Ensure proper types
                    sheet_data["hunger"] = _safe_float(sheet_data["hunger"], 100.0)
                    sheet_data["thirst"] = _safe_float(sheet_data["thirst"], 100.0)
                    sheet_data["socialization"] = _safe_float(sheet_data["socialization"], 100.0)
                    sheet_data["sleep"] = _safe_float(sheet_data["sleep"], 100.0)
                    sheet_data["sleeping_ticks_remaining"] = _safe_int(sheet_data["sleeping_ticks_remaining"], 0)
                    sheet_data["action_points"] = _safe_int(sheet_data["action_points"], 0)
        
        # Migrate user character sheets
        users = data.get("users", {})
        if isinstance(users, dict):
            for user_id, user_data in users.items():
                if isinstance(user_data, dict):
                    sheet_data = user_data.get("sheet", {})
                    if isinstance(sheet_data, dict):
                        # Add missing needs fields
                        sheet_data.setdefault("hunger", 100.0)
                        sheet_data.setdefault("thirst", 100.0)
                        sheet_data.setdefault("socialization", 100.0) 
                        sheet_data.setdefault("sleep", 100.0)
                        sheet_data.setdefault("sleeping_ticks_remaining", 0)
                        sheet_data.setdefault("sleeping_bed_uuid", None)
                        sheet_data.setdefault("action_points", 0)
                        sheet_data.setdefault("plan_queue", [])
                        
                        # Ensure proper types
                        sheet_data["hunger"] = _safe_float(sheet_data["hunger"], 100.0)
                        sheet_data["thirst"] = _safe_float(sheet_data["thirst"], 100.0)
                        sheet_data["socialization"] = _safe_float(sheet_data["socialization"], 100.0)
                        sheet_data["sleep"] = _safe_float(sheet_data["sleep"], 100.0)
                        sheet_data["sleeping_ticks_remaining"] = _safe_int(sheet_data["sleeping_ticks_remaining"], 0)
                        sheet_data["action_points"] = _safe_int(sheet_data["action_points"], 0)
        
        data["world_version"] = self.version
        migration_logger.info(f"Applied migration {self.version}: {self.description}")
        return data


class Migration003_ConsolidateUUIDs(BaseMigration):
    """Consolidate UUID backfill logic into proper migration.
    
    This migration handles generating stable UUIDs for entities that were
    previously backfilled ad-hoc in Room.from_dict() and World.from_dict().
    """
    
    @property
    def version(self) -> int:
        return 3
        
    @property 
    def description(self) -> str:
        return "Generate stable UUIDs for rooms, doors, stairs, and NPCs"
    
    def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(data)  # Copy to avoid mutating input
        
        # Generate missing room UUIDs
        rooms = data.get("rooms", {})
        if isinstance(rooms, dict):
            for room_id, room_data in rooms.items():
                if isinstance(room_data, dict):
                    # Ensure room has UUID
                    if "uuid" not in room_data or not room_data["uuid"]:
                        room_data["uuid"] = str(uuid.uuid4())
                    
                    # Ensure door IDs exist for all doors
                    doors = room_data.get("doors", {})
                    door_ids = room_data.setdefault("door_ids", {})
                    for door_name in doors.keys():
                        if door_name not in door_ids:
                            door_ids[door_name] = str(uuid.uuid4())
                    
                    # Ensure stairs IDs exist if stairs are present
                    if room_data.get("stairs_up_to") and not room_data.get("stairs_up_id"):
                        room_data["stairs_up_id"] = str(uuid.uuid4())
                    if room_data.get("stairs_down_to") and not room_data.get("stairs_down_id"):
                        room_data["stairs_down_id"] = str(uuid.uuid4())
        
        # Generate missing NPC IDs
        npc_ids = data.setdefault("npc_ids", {})
        npc_sheets = data.get("npc_sheets", {})
        
        # Ensure all NPCs in sheets have IDs
        if isinstance(npc_sheets, dict):
            for npc_name in npc_sheets.keys():
                if npc_name not in npc_ids:
                    npc_ids[npc_name] = str(uuid.uuid4())
        
        # Ensure all NPCs referenced in rooms have IDs
        if isinstance(rooms, dict):
            for room_data in rooms.values():
                if isinstance(room_data, dict):
                    npcs_in_room = room_data.get("npcs", [])
                    if isinstance(npcs_in_room, list):
                        for npc_name in npcs_in_room:
                            if npc_name not in npc_ids:
                                npc_ids[npc_name] = str(uuid.uuid4())
        
        # Ensure all objects have UUIDs
        if isinstance(rooms, dict):
            for room_data in rooms.values():
                if isinstance(room_data, dict):
                    objects = room_data.get("objects", {})
                    if isinstance(objects, dict):
                        for obj_uuid, obj_data in objects.items():
                            if isinstance(obj_data, dict):
                                if "uuid" not in obj_data or not obj_data["uuid"]:
                                    obj_data["uuid"] = obj_uuid
        
        # Ensure object templates have UUIDs
        templates = data.get("object_templates", {})
        if isinstance(templates, dict):
            for template_data in templates.values():
                if isinstance(template_data, dict):
                    if "uuid" not in template_data or not template_data["uuid"]:
                        template_data["uuid"] = str(uuid.uuid4())
        
        data["world_version"] = self.version
        migration_logger.info(f"Applied migration {self.version}: {self.description}")
        return data


class Migration004_EnsureTravelObjects(BaseMigration):
    """Ensure travel point objects exist for doors and stairs.
    
    This migration creates Object entries for doors and stairs that were
    previously handled only as room metadata, ensuring consistent travel
    point representation.
    """
    
    @property
    def version(self) -> int:
        return 4
    
    @property
    def description(self) -> str:
        return "Create travel point objects for doors and stairs"
    
    def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(data)  # Copy to avoid mutating input
        
        rooms = data.get("rooms", {})
        if isinstance(rooms, dict):
            for room_id, room_data in rooms.items():
                if isinstance(room_data, dict):
                    objects = room_data.setdefault("objects", {})
                    doors = room_data.get("doors", {})
                    door_ids = room_data.get("door_ids", {})
                    
                    # Create door objects
                    for door_name, target_room in doors.items():
                        door_id = door_ids.get(door_name)
                        if door_id and door_id not in objects:
                            objects[door_id] = {
                                "uuid": door_id,
                                "display_name": door_name,
                                "description": f"A doorway named '{door_name}'.",
                                "object_tag": ["Immovable", "Travel Point"],
                                "link_target_room_id": target_room
                            }
                        elif door_id and door_id in objects:
                            # Ensure existing object has proper tags and link
                            obj = objects[door_id]
                            tags = set(obj.get("object_tag", []))
                            tags.update(["Immovable", "Travel Point"])
                            obj["object_tag"] = list(tags)
                            if not obj.get("link_target_room_id"):
                                obj["link_target_room_id"] = target_room
                    
                    # Create stairs objects
                    stairs_up_to = room_data.get("stairs_up_to")
                    stairs_up_id = room_data.get("stairs_up_id")
                    if stairs_up_to and stairs_up_id:
                        if stairs_up_id not in objects:
                            objects[stairs_up_id] = {
                                "uuid": stairs_up_id,
                                "display_name": "stairs up",
                                "description": "A staircase leading up.",
                                "object_tag": ["Immovable", "Travel Point"],
                                "link_target_room_id": stairs_up_to
                            }
                        else:
                            # Ensure existing object has proper configuration
                            obj = objects[stairs_up_id]
                            tags = set(obj.get("object_tag", []))
                            tags.update(["Immovable", "Travel Point"])
                            obj["object_tag"] = list(tags)
                            if not obj.get("link_target_room_id"):
                                obj["link_target_room_id"] = stairs_up_to
                    
                    stairs_down_to = room_data.get("stairs_down_to")
                    stairs_down_id = room_data.get("stairs_down_id")
                    if stairs_down_to and stairs_down_id:
                        if stairs_down_id not in objects:
                            objects[stairs_down_id] = {
                                "uuid": stairs_down_id,
                                "display_name": "stairs down", 
                                "description": "A staircase leading down.",
                                "object_tag": ["Immovable", "Travel Point"],
                                "link_target_room_id": stairs_down_to
                            }
                        else:
                            # Ensure existing object has proper configuration
                            obj = objects[stairs_down_id]
                            tags = set(obj.get("object_tag", []))
                            tags.update(["Immovable", "Travel Point"])
                            obj["object_tag"] = list(tags)
                            if not obj.get("link_target_room_id"):
                                obj["link_target_room_id"] = stairs_down_to
        
        data["world_version"] = self.version
        migration_logger.info(f"Applied migration {self.version}: {self.description}")
        return data


class MigrationRegistry:
    """Registry and runner for world schema migrations.
    
    Auto-discovers migration classes and runs them in version order.
    Provides safe migration with rollback support for development.
    """
    
    def __init__(self):
        self._migrations: Dict[int, Type[BaseMigration]] = {}
        self._discover_migrations()
    
    def _discover_migrations(self) -> None:
        """Auto-discover migration classes in this module."""
        import inspect
        current_module = inspect.getmodule(inspect.currentframe())
        
        for name, obj in inspect.getmembers(current_module):
            if (inspect.isclass(obj) and 
                issubclass(obj, BaseMigration) and 
                obj is not BaseMigration):
                
                # Instantiate to get version number
                try:
                    migration_instance = obj()
                    version = migration_instance.version
                    
                    if version in self._migrations:
                        raise MigrationError(f"Duplicate migration version {version}: {name} and {self._migrations[version].__name__}")
                    
                    self._migrations[version] = obj
                    migration_logger.debug(f"Registered migration {version}: {name}")
                    
                except Exception as e:
                    migration_logger.error(f"Failed to register migration {name}: {e}")
    
    def get_current_version(self, data: Dict[str, Any]) -> int:
        """Get the current schema version from world data."""
        return data.get("world_version", 0)
    
    def get_latest_version(self) -> int:
        """Get the latest available migration version."""
        return max(self._migrations.keys()) if self._migrations else 0
    
    def needs_migration(self, data: Dict[str, Any]) -> bool:
        """Check if world data needs migration."""
        current = self.get_current_version(data)
        latest = self.get_latest_version()
        return current < latest
    
    def get_migration_plan(self, data: Dict[str, Any]) -> List[int]:
        """Get list of migration versions needed to bring data up to date."""
        current = self.get_current_version(data)
        latest = self.get_latest_version()
        
        plan = []
        for version in range(current + 1, latest + 1):
            if version in self._migrations:
                plan.append(version)
            else:
                raise MigrationError(f"Missing migration for version {version}")
        
        return plan
    
    def migrate(self, data: Dict[str, Any], target_version: Optional[int] = None) -> Dict[str, Any]:
        """Migrate world data to target version (or latest if not specified).
        
        Args:
            data: World data dictionary to migrate
            target_version: Version to migrate to, or None for latest
            
        Returns:
            Migrated world data dictionary
            
        Raises:
            MigrationError: If migration fails
        """
        if target_version is None:
            target_version = self.get_latest_version()
        
        current_version = self.get_current_version(data)
        
        if current_version == target_version:
            migration_logger.info(f"World data already at version {target_version}")
            return data
        
        if current_version > target_version:
            raise MigrationError(f"Cannot downgrade from version {current_version} to {target_version}")
        
        migration_logger.info(f"Migrating world data from version {current_version} to {target_version}")
        
        # Apply migrations in sequence
        migrated_data = dict(data)  # Start with a copy
        
        for version in range(current_version + 1, target_version + 1):
            if version not in self._migrations:
                raise MigrationError(f"No migration available for version {version}")
            
            migration_class = self._migrations[version]
            migration = migration_class()
            
            migration_logger.info(f"Applying migration {version}: {migration.description}")
            
            # Validate preconditions
            if not migration.validate_preconditions(migrated_data):
                raise MigrationError(f"Migration {version} preconditions failed")
            
            try:
                migrated_data = migration.migrate(migrated_data)
            except Exception as e:
                migration_logger.error(f"Migration {version} failed: {e}")
                raise MigrationError(f"Migration {version} failed: {e}") from e
            
            # Verify version was updated
            if migrated_data.get("world_version") != version:
                raise MigrationError(f"Migration {version} did not update world_version correctly")
        
        migration_logger.info(f"Migration complete: version {current_version} -> {target_version}")
        return migrated_data
    
    def list_migrations(self) -> List[Dict[str, Any]]:
        """List all available migrations with their descriptions."""
        migrations = []
        for version in sorted(self._migrations.keys()):
            migration_class = self._migrations[version]
            migration = migration_class()
            migrations.append({
                "version": version,
                "description": migration.description,
                "class": migration_class.__name__
            })
        return migrations


# Global migration registry instance
migration_registry = MigrationRegistry()