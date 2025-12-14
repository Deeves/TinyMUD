import uuid

class MigrationError(Exception):
    pass

class BaseMigration:
    version = 0
    description = "Base Migration"
    
    def migrate(self, data: dict) -> dict:
        return data

class Migration001_AddWorldVersion(BaseMigration):
    version = 1
    description = "Add world_version field"
    
    def migrate(self, data: dict) -> dict:
        if "world_version" not in data:
            data["world_version"] = 1
        return data

class Migration002_ConsolidateNeedsSystem(BaseMigration):
    version = 2
    description = "Consolidate needs system"
    def migrate(self, data: dict) -> dict:
        return data

class Migration003_ConsolidateUUIDs(BaseMigration):
    version = 3
    description = "Consolidate UUIDs"
    def migrate(self, data: dict) -> dict:
        return data

class Migration004_EnsureTravelObjects(BaseMigration):
    version = 4
    description = "Ensure travel objects"
    def migrate(self, data: dict) -> dict:
        return data

class MigrationRegistry:
    def __init__(self):
        self.migrations = [
            Migration001_AddWorldVersion(),
            Migration002_ConsolidateNeedsSystem(),
            Migration003_ConsolidateUUIDs(),
            Migration004_EnsureTravelObjects()
        ]
        
    def list_migrations(self):
        return [{"version": m.version, "description": m.description} for m in self.migrations]
        
    def get_current_version(self, data: dict) -> int:
        return data.get("world_version", 0)
        
    def get_latest_version(self) -> int:
        return 4
        
    def needs_migration(self, data: dict) -> bool:
        current = self.get_current_version(data)
        return current < self.get_latest_version()
        
    def migrate(self, data: dict) -> dict:
        current = self.get_current_version(data)
        latest = self.get_latest_version()
        
        for m in self.migrations:
            if m.version > current:
                print(f"Applying migration {m.version}: {m.description}")
                data = m.migrate(data)
                data["world_version"] = m.version
                
        return data
        
    def get_migration_plan(self, data: dict):
        current = self.get_current_version(data)
        return [m.version for m in self.migrations if m.version > current]

migration_registry = MigrationRegistry()
