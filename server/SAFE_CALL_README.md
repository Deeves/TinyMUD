# Safe Exception Handling with safe_call()

This project uses a structured approach to exception handling through the `safe_utils.py` module, which provides better debugging capabilities than bare `except Exception: pass` blocks.

## Problem Solved

Previously, the codebase had many patterns like this:

```python
try:
    risky_operation()
except Exception:
    pass  # Silent failure - no debugging info!
```

These patterns hide errors completely, making debugging difficult when issues occur.

## Solution: safe_call()

The `safe_call()` helper logs the first occurrence of each exception type per function, then silently handles subsequent occurrences of the same exception type. This provides debugging information without log spam.

## Usage Examples

### Basic Replacement

```python
# Before
try:
    socketio.emit(MESSAGE_OUT, payload, to=psid)
except Exception:
    pass

# After  
safe_call(socketio.emit, MESSAGE_OUT, payload, to=psid)
```

### With Default Return Values

```python
# Before
try:
    return config_reader(key)
except Exception:
    pass
return default_value

# After
return safe_call_with_default(config_reader, default_value, key)
```

### Complex Logic Refactoring

```python
# Before
try:
    for rid, room in world.rooms.items():
        if npc_name in (room.npcs or set()):
            return rid
except Exception:
    pass
return None

# After
def _find_room():
    for rid, room in world.rooms.items():
        if npc_name in (room.npcs or set()):
            return rid
    return None

return safe_call(_find_room) or None
```

### Method Decorator

```python
class GameEntity:
    @safe_decorator(default=[])
    def get_inventory(self) -> list[str]:
        return list(self.inventory)  # May raise AttributeError
```

## Benefits

1. **Better Debugging**: First occurrence of each error type is logged with context
2. **No Log Spam**: Subsequent identical errors are silently handled  
3. **Graceful Degradation**: Functions still return None/default on failure
4. **Zero Breaking Changes**: Drop-in replacement for existing patterns
5. **Testing Friendly**: `reset_seen_exceptions()` for clean test state

## Integration Status

Key areas where `safe_call()` has been integrated:

- `broadcast_to_room()` - Network emission failures
- `_setup_logging()` - Configuration failures  
- `_npc_find_room_for()` - World state iteration failures

Additional bare `except Exception: pass` patterns throughout the codebase can be gradually migrated to use `safe_call()` for improved debugging capabilities.
