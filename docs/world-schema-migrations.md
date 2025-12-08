# World Schema Migration System

This document describes the migration system implemented to replace ad-hoc backfill logic with a clean, versioned schema evolution system.

## Overview

The migration system provides:
- **Sequential versioning** starting from version 1
- **Automatic migration** of old world files to current schema
- **Idempotent migrations** that can be safely re-run
- **Comprehensive testing** with full coverage of migration scenarios
- **Graceful error handling** with fallback to raw data loading

## Architecture

### Core Components

1. **`BaseMigration`** - Abstract base class for all migrations
2. **`MigrationRegistry`** - Auto-discovers and runs migrations in order
3. **Individual Migration Classes** - Handle specific schema changes
4. **World Integration** - Transparent migration during world loading

### Migration Files

- `server/world_migrations.py` - Migration framework and all migration classes
- `server/test_world_migrations.py` - Comprehensive test suite
- `server/world.py` - Updated World class with migration integration

## Available Migrations

### Migration 001: Add World Version
- **Purpose**: Bootstrap migration that adds `world_version` field
- **Effect**: Enables version tracking for all future migrations
- **Data Changes**: Adds `world_version: 1` to world data

### Migration 002: Consolidate Needs System  
- **Purpose**: Replace ad-hoc needs system backfill with proper migration
- **Effect**: Ensures all NPCs and player characters have needs fields
- **Data Changes**: 
  - Adds `hunger`, `thirst`, `socialization`, `sleep` with defaults (100.0)
  - Adds `sleeping_ticks_remaining`, `sleeping_bed_uuid`, `action_points`, `plan_queue`
  - Handles type conversion and malformed data gracefully

### Migration 003: Consolidate UUIDs
- **Purpose**: Replace UUID backfill logic with proper migration
- **Effect**: Ensures all entities have stable UUIDs
- **Data Changes**:
  - Generates `uuid` for rooms, objects, and templates
  - Creates `door_ids` mapping for all doors
  - Generates `stairs_up_id` and `stairs_down_id` when needed
  - Creates `npc_ids` mapping for all NPCs

### Migration 004: Ensure Travel Objects
- **Purpose**: Create Object instances for doors and stairs
- **Effect**: Uniform travel point representation
- **Data Changes**:
  - Creates Object entries for all doors with proper tags and links
  - Creates Object entries for stairs (up/down) when present
  - Updates existing objects to have correct travel point tags

## Usage

### Automatic Migration (Normal Use)
```python
# Migrations are applied automatically during world loading
world = World.load_from_file("world_state.json")
# Old files are migrated transparently to current schema
```

### Manual Migration (Development/Testing)
```python
from world_migrations import migration_registry

# Check if migration is needed
if migration_registry.needs_migration(data):
    # Apply migrations
    migrated_data = migration_registry.migrate(data)

# List available migrations
migrations = migration_registry.list_migrations()
for m in migrations:
    print(f"Version {m['version']}: {m['description']}")
```

## Adding New Migrations

1. Create a new migration class inheriting from `BaseMigration`
2. Implement required properties and methods:
   ```python
   class Migration005_YourFeature(BaseMigration):
       @property
       def version(self) -> int:
           return 5
       
       @property
       def description(self) -> str:
           return "Description of what this migration does"
       
       def migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
           # Implement migration logic here
           data = dict(data)  # Always copy input
           # ... apply changes ...
           data["world_version"] = self.version
           return data
   ```

3. Add comprehensive tests in `test_world_migrations.py`
4. The migration will be auto-discovered by the registry

## Migration Principles

### Safety
- **Always copy input data** - Never mutate the input dictionary
- **Handle malformed data** - Use safe type conversion with defaults
- **Graceful degradation** - Migration failures don't crash the server
- **Backwards compatibility** - Never remove data, only add or transform

### Idempotency  
- Migrations can be run multiple times safely
- Check for existing data before adding fields
- Use `setdefault()` for new fields with defaults

### Testing
- Test each migration individually with various data scenarios
- Test full migration chains from version 0 to latest
- Test error conditions and malformed data handling
- Test integration with World loading/saving

## Schema Evolution Strategy

### Before This System
- Ad-hoc backfill logic scattered throughout `from_dict` methods
- No version tracking or migration history
- Difficult to test and maintain
- Risk of data corruption from untested backfill logic

### After This System  
- Clean, versioned schema evolution
- Centralized migration logic with comprehensive testing
- Clear migration history and documentation
- Safe, tested upgrades for all schema changes

### Future Additions
When adding new fields or changing data structures:

1. **Create a migration** rather than adding backfill logic
2. **Test thoroughly** with various data scenarios
3. **Document the change** in the migration's description
4. **Update tests** to cover the new schema version

This approach ensures the codebase remains maintainable and reduces the risk of data corruption during schema evolution.

## Removed Backfill Logic

The following ad-hoc backfill logic has been replaced with proper migrations:

- **CharacterSheet.from_dict()**: Needs system defaults (now Migration 002)
- **Room.from_dict()**: Door ID and stairs ID generation (now Migration 003)
- **Room.from_dict()**: Travel point object creation (now Migration 004)  
- **World.from_dict()**: NPC ID generation (now Migration 003)

Runtime backfill logic in `server.py` for live game state remains for defensive programming but is separate from data loading migrations.