"""World schema migration system.

Provides automatic upgrading of world state files from older schema versions
to the current version. Each migration class handles one version increment.
"""

import uuid
import copy
from typing import Dict, Any, List


class MigrationError(Exception):
    """Raised when a migration fails."""
    pass


class BaseMigration:
    """Base class for all migrations."""
    version = 0
    description = "Base Migration"

    def migrate(self, data: dict) -> dict:
        """Apply this migration. Should return a NEW dict, not mutate input."""
        return copy.deepcopy(data)


class Migration001_AddWorldVersion(BaseMigration):
    """Bootstrap migration that adds version tracking to world data."""
    version = 1
    description = "Add world_version field"

    def migrate(self, data: dict) -> dict:
        result = copy.deepcopy(data)
        if "world_version" not in result:
            result["world_version"] = 1
        return result


class Migration002_ConsolidateNeedsSystem(BaseMigration):
    """Backfill needs fields (hunger, thirst, etc.) on character sheets."""
    version = 2
    description = "Consolidate needs system"

    # Default values for needs fields
    NEEDS_DEFAULTS: Dict[str, Any] = {
        "hunger": 100.0,
        "thirst": 100.0,
        "socialization": 100.0,
        "sleep": 100.0,
        "sleeping_ticks_remaining": 0,
        "sleeping_bed_uuid": None,
        "action_points": 0,
        "plan_queue": [],
    }

    def _safe_float(self, value: Any, default: float) -> float:
        """Convert value to float safely, returning default on failure."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _safe_int(self, value: Any, default: int) -> int:
        """Convert value to int safely, returning default on failure."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _backfill_sheet(self, sheet: dict) -> dict:
        """Backfill needs fields on a character sheet."""
        for key, default in self.NEEDS_DEFAULTS.items():
            if key not in sheet or sheet[key] is None:
                sheet[key] = default
            elif isinstance(default, float):
                sheet[key] = self._safe_float(sheet[key], default)
            elif isinstance(default, int):
                sheet[key] = self._safe_int(sheet[key], default)
            elif isinstance(default, list) and not isinstance(sheet[key], list):
                sheet[key] = default
        return sheet

    def migrate(self, data: dict) -> dict:
        result = copy.deepcopy(data)

        # Backfill NPC sheets
        npc_sheets = result.get("npc_sheets", {})
        if isinstance(npc_sheets, dict):
            for npc_name, sheet in npc_sheets.items():
                if isinstance(sheet, dict):
                    npc_sheets[npc_name] = self._backfill_sheet(sheet)

        # Backfill user character sheets
        users = result.get("users", {})
        if isinstance(users, dict):
            for user_id, user_data in users.items():
                if isinstance(user_data, dict) and "sheet" in user_data:
                    sheet = user_data.get("sheet")
                    if isinstance(sheet, dict):
                        user_data["sheet"] = self._backfill_sheet(sheet)

        return result


class Migration003_ConsolidateUUIDs(BaseMigration):
    """Generate missing UUIDs for rooms, doors, stairs, and NPCs."""
    version = 3
    description = "Consolidate UUIDs"

    def migrate(self, data: dict) -> dict:
        result = copy.deepcopy(data)

        # Ensure npc_ids exists
        if "npc_ids" not in result:
            result["npc_ids"] = {}

        # Process rooms
        rooms = result.get("rooms", {})
        if isinstance(rooms, dict):
            for room_id, room in rooms.items():
                if not isinstance(room, dict):
                    continue

                # Generate room UUID if missing
                if "uuid" not in room or not room["uuid"]:
                    room["uuid"] = str(uuid.uuid4())

                # Generate door_ids for any doors without them
                doors = room.get("doors", {})
                if isinstance(doors, dict):
                    if "door_ids" not in room:
                        room["door_ids"] = {}
                    for door_name in doors:
                        if door_name not in room["door_ids"]:
                            room["door_ids"][door_name] = str(uuid.uuid4())

                # Generate stair UUIDs if stairs exist but no UUID
                if room.get("stairs_up_to") and not room.get("stairs_up_id"):
                    room["stairs_up_id"] = str(uuid.uuid4())
                if room.get("stairs_down_to") and not room.get("stairs_down_id"):
                    room["stairs_down_id"] = str(uuid.uuid4())

                # Ensure objects dict exists
                if "objects" not in room:
                    room["objects"] = {}

                # Collect NPC names from this room
                npcs = room.get("npcs", [])
                if isinstance(npcs, (list, set)):
                    for npc_name in npcs:
                        if npc_name not in result["npc_ids"]:
                            result["npc_ids"][npc_name] = str(uuid.uuid4())

        # Generate IDs for NPCs in npc_sheets not yet in npc_ids
        npc_sheets = result.get("npc_sheets", {})
        if isinstance(npc_sheets, dict):
            for npc_name in npc_sheets:
                if npc_name not in result["npc_ids"]:
                    result["npc_ids"][npc_name] = str(uuid.uuid4())

        return result


class Migration004_EnsureTravelObjects(BaseMigration):
    """Create or update travel point objects for doors and stairs."""
    version = 4
    description = "Ensure travel objects"

    def _ensure_travel_object(
        self,
        objects: dict,
        obj_uuid: str,
        display_name: str,
        target_room_id: str
    ) -> None:
        """Create or update a travel object in the objects dict."""
        required_tags = {"Travel Point", "Immovable"}

        if obj_uuid in objects:
            # Update existing object
            obj = objects[obj_uuid]
            existing_tags = set(obj.get("object_tag", []))
            obj["object_tag"] = list(existing_tags | required_tags)
            if "link_target_room_id" not in obj:
                obj["link_target_room_id"] = target_room_id
        else:
            # Create new travel object
            objects[obj_uuid] = {
                "uuid": obj_uuid,
                "display_name": display_name,
                "description": f"A passage leading to {target_room_id}.",
                "object_tag": list(required_tags),
                "link_target_room_id": target_room_id,
            }

    def migrate(self, data: dict) -> dict:
        result = copy.deepcopy(data)

        rooms = result.get("rooms", {})
        if not isinstance(rooms, dict):
            return result

        for room_id, room in rooms.items():
            if not isinstance(room, dict):
                continue

            # Ensure objects dict exists
            if "objects" not in room:
                room["objects"] = {}
            objects = room["objects"]

            # Create/update door objects
            doors = room.get("doors", {})
            door_ids = room.get("door_ids", {})
            if isinstance(doors, dict) and isinstance(door_ids, dict):
                for door_name, target_room in doors.items():
                    if door_name in door_ids:
                        door_uuid = door_ids[door_name]
                        self._ensure_travel_object(
                            objects, door_uuid, door_name, target_room
                        )

            # Create/update stairs up object
            stairs_up_to = room.get("stairs_up_to")
            stairs_up_id = room.get("stairs_up_id")
            if stairs_up_to and stairs_up_id:
                self._ensure_travel_object(
                    objects, stairs_up_id, "stairs up", stairs_up_to
                )

            # Create/update stairs down object
            stairs_down_to = room.get("stairs_down_to")
            stairs_down_id = room.get("stairs_down_id")
            if stairs_down_to and stairs_down_id:
                self._ensure_travel_object(
                    objects, stairs_down_id, "stairs down", stairs_down_to
                )

        return result


class MigrationRegistry:
    """Registry that discovers and runs migrations in order."""

    def __init__(self) -> None:
        self.migrations: List[BaseMigration] = [
            Migration001_AddWorldVersion(),
            Migration002_ConsolidateNeedsSystem(),
            Migration003_ConsolidateUUIDs(),
            Migration004_EnsureTravelObjects(),
        ]

    def list_migrations(self) -> List[Dict[str, Any]]:
        """List all registered migrations."""
        return [
            {"version": m.version, "description": m.description}
            for m in self.migrations
        ]

    def get_current_version(self, data: dict) -> int:
        """Get the schema version of the given world data."""
        return data.get("world_version", 0)

    def get_latest_version(self) -> int:
        """Get the latest schema version supported."""
        return max(m.version for m in self.migrations) if self.migrations else 0

    def needs_migration(self, data: dict) -> bool:
        """Check if the data needs migration."""
        return self.get_current_version(data) < self.get_latest_version()

    def get_migration_plan(self, data: dict) -> List[int]:
        """Get the list of migration versions that will be applied."""
        current = self.get_current_version(data)
        return [m.version for m in self.migrations if m.version > current]

    def migrate(self, data: dict) -> dict:
        """Apply all pending migrations to the data."""
        current = self.get_current_version(data)

        # If already at latest, return as-is
        if current >= self.get_latest_version():
            return data

        result = copy.deepcopy(data)

        for migration in self.migrations:
            if migration.version > current:
                print(f"Applying migration {migration.version}: {migration.description}")
                result = migration.migrate(result)
                result["world_version"] = migration.version

        return result


# Global singleton registry
migration_registry = MigrationRegistry()
