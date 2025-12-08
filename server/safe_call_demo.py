#!/usr/bin/env python3
"""
Demonstration script showing safe_call migration patterns.

This script shows how to migrate existing bare 'except Exception: pass' patterns
to use safe_call for better debugging while maintaining graceful failure behavior.
"""

from safe_utils import safe_call, safe_call_with_default, safe_decorator

# Example 1: Simple function call migration
def demo_simple_migration():
    """Show basic migration from try/except to safe_call."""
    print("=== Simple Migration Pattern ===")
    
    # Simulated risky function
    def risky_network_call(url: str) -> str:
        if "bad" in url:
            raise ConnectionError(f"Cannot connect to {url}")
        return f"Connected to {url}"
    
    # OLD PATTERN (hides all errors)
    def old_way(url: str) -> str | None:
        try:
            return risky_network_call(url)
        except Exception:
            pass  # Silent failure - no debugging info!
        return None
    
    # NEW PATTERN (logs first occurrence of each error type)
    def new_way(url: str) -> str | None:
        return safe_call(risky_network_call, url)
    
    # Test both approaches
    print("Old way results:")
    print(f"  good.com: {old_way('good.com')}")
    print(f"  bad.com: {old_way('bad.com')}")  # Silent failure
    print(f"  bad2.com: {old_way('bad2.com')}")  # Silent failure
    
    print("\nNew way results (check logs for first error):")
    print(f"  good.com: {new_way('good.com')}")
    print(f"  bad.com: {new_way('bad.com')}")  # Logs ConnectionError once
    print(f"  bad2.com: {new_way('bad2.com')}")  # Silent (already logged)


# Example 2: Migration with default values
def demo_default_value_migration():
    """Show migration when you need a specific default value."""
    print("\n=== Default Value Migration Pattern ===")
    
    # Simulated config reader
    def read_config(key: str) -> int:
        configs = {"timeout": 30, "retries": 3}
        if key not in configs:
            raise KeyError(f"Config key '{key}' not found")
        return configs[key]
    
    # OLD PATTERN
    def old_get_config(key: str, default: int = 0) -> int:
        try:
            return read_config(key)
        except Exception:
            pass
        return default
    
    # NEW PATTERN
    def new_get_config(key: str, default: int = 0) -> int:
        return safe_call_with_default(read_config, default, key)
    
    # Test both approaches
    print("Old way results:")
    print(f"  timeout: {old_get_config('timeout', 60)}")
    print(f"  missing: {old_get_config('missing', 60)}")
    
    print("\nNew way results:")
    print(f"  timeout: {new_get_config('timeout', 60)}")
    print(f"  missing: {new_get_config('missing', 60)}")


# Example 3: Decorator pattern for methods
def demo_decorator_migration():
    """Show how to use safe_decorator for class methods."""
    print("\n=== Decorator Migration Pattern ===")
    
    class GameEntity:
        def __init__(self, name: str, has_inventory: bool = True):
            self.name = name
            if has_inventory:
                self.inventory = ["sword", "potion"]
            # Note: some entities might not have inventory attribute
        
        # OLD PATTERN - method that might fail
        def get_inventory_old(self) -> list[str]:
            try:
                return list(self.inventory)  # May raise AttributeError
            except Exception:
                pass
            return []
        
        # NEW PATTERN - using decorator
        @safe_decorator(default=[])
        def get_inventory_new(self) -> list[str]:
            return list(self.inventory)  # May raise AttributeError
    
    # Test with entities that have and don't have inventory
    player = GameEntity("Player", has_inventory=True)
    npc = GameEntity("NPC", has_inventory=False)
    
    print("Old way results:")
    print(f"  Player inventory: {player.get_inventory_old()}")
    print(f"  NPC inventory: {npc.get_inventory_old()}")  # Silent failure
    
    print("\nNew way results:")
    print(f"  Player inventory: {player.get_inventory_new()}")
    print(f"  NPC inventory: {npc.get_inventory_new()}")  # Logs AttributeError


# Example 4: Complex refactoring pattern
def demo_complex_migration():
    """Show how to refactor complex try/except blocks."""
    print("\n=== Complex Migration Pattern ===")
    
    # Simulated world data
    world_rooms = {
        "tavern": {"npcs": {"Innkeeper", "Bard"}},
        "forest": {"npcs": {"Druid"}},
        "broken": None  # Simulates corrupted data
    }
    
    # OLD PATTERN - complex logic in try/except
    def find_npc_room_old(npc_name: str) -> str | None:
        try:
            for room_id, room_data in world_rooms.items():
                if room_data and npc_name in room_data.get("npcs", set()):
                    return room_id
        except Exception:
            pass  # Any error in the loop silently ignored
        return None
    
    # NEW PATTERN - extract logic and use safe_call
    def find_npc_room_new(npc_name: str) -> str | None:
        def _search_rooms():
            for room_id, room_data in world_rooms.items():
                if room_data and npc_name in room_data.get("npcs", set()):
                    return room_id
            return None
        
        return safe_call(_search_rooms) or None
    
    print("Old way results:")
    print(f"  Innkeeper: {find_npc_room_old('Innkeeper')}")
    print(f"  Missing: {find_npc_room_old('Wizard')}")
    
    print("\nNew way results:")
    print(f"  Innkeeper: {find_npc_room_new('Innkeeper')}")
    print(f"  Missing: {find_npc_room_new('Wizard')}")


if __name__ == "__main__":
    import logging
    
    # Configure logging to see safe_call messages
    logging.basicConfig(
        level=logging.WARNING,
        format='[%(levelname)s] %(name)s: %(message)s'
    )
    
    print("Safe Call Migration Demonstration")
    print("=" * 50)
    print("This demo shows how to replace 'except Exception: pass'")
    print("with safe_call for better debugging.\n")
    
    demo_simple_migration()
    demo_default_value_migration() 
    demo_decorator_migration()
    demo_complex_migration()
    
    print("\n" + "=" * 50)
    print("Summary:")
    print("- safe_call() logs first occurrence of each exception type")
    print("- safe_call_with_default() allows custom return values")
    print("- @safe_decorator() works for methods that shouldn't fail")
    print("- Extract complex logic into inner functions for safe_call()")
    print("- Check server logs for exception information!")