# Persistence Strategy Refactoring

**Date**: October 2025  
**Branch**: GOAP-AI  
**Status**: ✅ Complete

## Problem

Inconsistent persistence strategy across the codebase:
- Mixed use of direct `world.save_to_file(state_path)` calls
- Some services using `save_world(..., debounced=True)` from `persistence_utils`
- No centralized enforcement of the persistence contract
- Difficult to track and audit save operations
- Hard to mock in tests

### Examples of Inconsistency

**Before:**
```python
# setup_service.py - mostly good, but one direct call at line 430
save_world(world, state_path, debounced=True)  # ✅
world.save_to_file(state_path)                  # ❌ Inconsistent

# server.py - direct calls everywhere
world.save_to_file(STATE_PATH)                  # ❌
safe_call(world.save_to_file, STATE_PATH)       # ❌

# player_router.py, admin_router.py, etc - direct calls
world.save_to_file(STATE_PATH)                  # ❌

# room_service.py - defensive fallback logic
try:
    from persistence_utils import save_world as _save
except Exception:
    _save = None
if _save is not None:
    _save(world, state_path, debounced=True)
else:
    world.save_to_file(state_path)              # ❌ Fallback to direct call
```

## Solution

Created a **centralized persistence façade** in `persistence_utils.py` that:
1. Provides a single, mandatory API for all world state persistence
2. Supports both debounced (default) and immediate saves
3. Tracks statistics for monitoring and debugging
4. Makes testing easier with a single mock point
5. Documents the architectural contract clearly

### Enhanced `persistence_utils.py`

```python
"""
🎯 KEY CONTRACT: This module is the ONLY authorized way to persist world state.
   All services, routers, and handlers MUST use save_world() instead of calling
   world.save_to_file() directly.
"""

# Public API
save_world(world, state_path, debounced=True)  # Standard save
flush_all_saves()                              # Force flush on shutdown
get_save_stats()                               # Monitoring/debugging

# Only place in codebase that calls world.save_to_file()
def _save_world_immediate(world, state_path):
    world.save_to_file(state_path)
```

## Changes Made

### Files Modified

1. **`persistence_utils.py`** - Enhanced with:
   - Comprehensive module docstring explaining the contract
   - Detailed function docstrings with usage patterns
   - Statistics tracking (`_stats` dict)
   - `flush_all_saves()` for shutdown handling
   - `get_save_stats()` for monitoring
   - Clear documentation that this is the ONLY place `world.save_to_file()` should be called

2. **`setup_service.py`** - Fixed inconsistent direct call:
   ```python
   # Before: world.save_to_file(state_path)
   # After:
   save_world(world, state_path, debounced=False)
   ```

3. **`server.py`** - Refactored all save operations:
   - Added import: `from persistence_utils import save_world, flush_all_saves`
   - Updated `_save_world()` to use `save_world()` and `flush_all_saves()`
   - Replaced all `world.save_to_file()` calls with `save_world()`
   - Replaced all `safe_call(world.save_to_file, ...)` with `save_world()`

4. **`player_router.py`** - Migrated to façade:
   - Added import: `from persistence_utils import save_world`
   - Updated `/rename` and `/describe` commands to use `save_world()`

5. **`admin_router.py`** - Migrated to façade:
   - Added import: `from persistence_utils import save_world`
   - Updated `/safety` command to use `save_world()`

6. **`admin_service.py`** - Migrated to façade:
   - Added import: `from persistence_utils import save_world`
   - Updated `execute_purge()` to use immediate save
   - Simplified `_save_silent()` helper

7. **`room_service.py`** - Simplified save helper:
   - Removed defensive fallback logic
   - `_save_silent()` now always uses `save_world()`

8. **`npc_service.py`** - Simplified save helper:
   - Removed defensive fallback logic
   - Helper now always uses `save_world()`

9. **`faction_service.py`** - Migrated to façade:
   - Added import: `from persistence_utils import save_world`
   - Updated faction generation to use `save_world()`

10. **`interaction_router.py`** - Migrated to façade:
    - Added import: `from persistence_utils import save_world`
    - Updated interaction flow to use immediate save
    - Updated docstring to reflect new approach

### Tests Added

Created `test_persistence_facade.py` with comprehensive tests:
- ✅ `test_immediate_save` - Verifies immediate writes
- ✅ `test_debounced_save` - Verifies debouncing coalesces writes
- ✅ `test_flush_all_saves` - Verifies forced flush
- ✅ `test_save_stats_tracking` - Verifies statistics tracking
- ✅ `test_error_handling` - Verifies best-effort behavior
- ✅ `test_multiple_paths` - Verifies separate DebouncedSaver per path
- ✅ `test_integration_with_world_mutations` - Verifies real-world usage

## Verification

### Test Results
```
139 passed in 4.33s
```

All existing tests pass + 7 new persistence façade tests.

### Code Audit

Verified NO direct `world.save_to_file()` calls remain outside the façade:
```bash
$ grep -r "world.save_to_file" server/*.py
```

Only matches found:
- `persistence_utils.py` - The ONE authorized location (line 111)
- Comments and docstrings explaining the contract
- `debounced_saver.py` - Historical docstring reference

## Usage Patterns

### Standard Pattern (Debounced)
```python
from persistence_utils import save_world

# After any world mutation (wizards, room edits, etc.)
save_world(world, state_path, debounced=True)
```

### Critical Pattern (Immediate)
```python
# For auth, logout, admin commands that must persist before continuing
save_world(world, state_path, debounced=False)
```

### CommandContext Pattern (Preferred in Routers)
```python
from persistence_utils import save_world

def try_handle(ctx: CommandContext, ...):
    # Mutate world
    world.some_field = new_value
    
    # Save using context
    save_world(ctx.world, ctx.state_path, debounced=True)
```

### Shutdown Pattern
```python
from persistence_utils import flush_all_saves

def on_shutdown():
    flush_all_saves()  # Force all pending saves
```

## Benefits

1. **Consistency** - Single, well-documented API for all saves
2. **Debuggability** - Stats tracking and centralized logging point
3. **Testability** - Mock one module instead of many call sites
4. **Performance** - Proper debouncing prevents I/O storms
5. **Maintainability** - Future enhancements (compression, backups, remote sync) in one place
6. **Safety** - Contract enforcement prevents accidental direct calls

## Future Enhancements

Potential additions to the façade (no code changes needed elsewhere):

- [ ] Automatic backup rotation before overwrites
- [ ] Compression (gzip) for large world states
- [ ] Remote persistence (S3, GCS, etc.) alongside local
- [ ] Metrics export (Prometheus, StatsD)
- [ ] Save validation (schema checks before write)
- [ ] Audit logging of all save operations

## Contract

**✅ DO:**
- Use `save_world(world, state_path, debounced=True)` for all saves
- Use `flush_all_saves()` on shutdown
- Use `debounced=False` only for critical operations (auth, logout)

**❌ DON'T:**
- Call `world.save_to_file()` directly anywhere except `persistence_utils.py:_save_world_immediate()`
- Create new save helper functions that bypass the façade
- Use `safe_call(world.save_to_file, ...)` instead of `save_world()`

## Migration Checklist

For future features that need persistence:

- [ ] Import `save_world` from `persistence_utils`
- [ ] Call `save_world(world, state_path, debounced=True)` after mutations
- [ ] Use `debounced=False` only if the operation MUST persist before continuing
- [ ] Never call `world.save_to_file()` directly
- [ ] Add tests that verify persistence happens

## References

- `server/persistence_utils.py` - The persistence façade
- `server/debounced_saver.py` - Underlying debouncing mechanism
- `server/test_persistence_facade.py` - Comprehensive test suite
- `.github/copilot-instructions.md` - Updated with new patterns
