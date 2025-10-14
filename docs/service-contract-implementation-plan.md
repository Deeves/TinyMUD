# Service Contract Uniformity - Implementation Plan

**Status:** Ready for Implementation  
**Date:** October 7, 2025  
**Related:** `service-contract-audit.md`

## Executive Summary

We will standardize all service layer return contracts to a uniform 4-tuple pattern:
```python
(handled: bool, error: str | None, emits: List[dict], broadcasts: List[Tuple[str, dict]])
```

This eliminates confusion, reduces bugs, and makes testing easier while staying conservative (no dataclasses, minimal risk).

## Why This Approach

1. **Lowest Risk:** Just changing tuple length, not structure
2. **Backward Compatible:** Easy to add empty `[]` for broadcasts
3. **Already Proven:** 40% of services already use this pattern
4. **Test-Friendly:** Clear success/error semantics
5. **Future-Proof:** Easy to extend to dataclass later if needed

## Phase 1: Create Helper Module (1-2 hours)

Create `server/service_contract.py`:

```python
"""Service layer contract definitions and helpers.

All service functions in TinyMUD should return a 4-tuple:
    (handled: bool, error: str | None, emits: List[dict], broadcasts: List[Tuple[str, dict]])

Where:
    - handled: True if this service recognized and processed the request
    - error: None on success, error message string on failure (still handled=True)
    - emits: List of message payloads to send to the acting player
    - broadcasts: List of (room_id, payload) tuples to broadcast to rooms

Example success:
    return True, None, [{'type': 'system', 'content': 'Done!'}], []

Example error:
    return True, 'Invalid input.', [], []

Example with broadcast:
    emits = [{'type': 'system', 'content': 'You created a room.'}]
    broadcasts = [(room_id, {'type': 'system', 'content': 'Someone created a room!'})]
    return True, None, emits, broadcasts
"""

from __future__ import annotations
from typing import List, Tuple, Optional

# Type alias for clarity
ServiceReturn = Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]


def success(emits: List[dict], broadcasts: List[Tuple[str, dict]] = None) -> ServiceReturn:
    """Helper to return a successful service result."""
    return True, None, emits, broadcasts or []


def error(message: str) -> ServiceReturn:
    """Helper to return a service error result."""
    return True, message, [], []


def not_handled() -> ServiceReturn:
    """Helper to return 'this service did not handle this request'."""
    return False, None, [], []


def emit_router_helper(
    ctx,  # CommandContext
    sid: str | None,
    emit_fn,  # EmitFn
    service_result: ServiceReturn,
) -> None:
    """Helper to emit service results following the standard pattern.
    
    Usage in routers:
        handled, err, emits, broadcasts = some_service(...)
        if not handled:
            return False
        emit_router_helper(ctx, sid, emit, (handled, err, emits, broadcasts))
        return True
    """
    handled, error_msg, emits, broadcasts = service_result
    
    MESSAGE_OUT = ctx.message_out
    
    # Emit error if present
    if error_msg:
        emit_fn(MESSAGE_OUT, {'type': 'error', 'content': error_msg})
        return
    
    # Emit all messages to acting player
    for payload in emits:
        emit_fn(MESSAGE_OUT, payload)
    
    # Broadcast to rooms
    for room_id, payload in broadcasts:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
```

**Test:** Create `server/test_service_contract.py`:

```python
"""Tests for service contract helpers."""

from service_contract import success, error, not_handled, emit_router_helper


def test_success_helper():
    """Test success() constructs valid tuple."""
    result = success([{'type': 'system', 'content': 'OK'}])
    assert result == (True, None, [{'type': 'system', 'content': 'OK'}], [])


def test_error_helper():
    """Test error() constructs valid tuple."""
    result = error('Something went wrong')
    assert result == (True, 'Something went wrong', [], [])


def test_not_handled_helper():
    """Test not_handled() constructs valid tuple."""
    result = not_handled()
    assert result == (False, None, [], [])


def test_success_with_broadcasts():
    """Test success() with broadcasts."""
    emits = [{'type': 'system', 'content': 'You did it'}]
    broadcasts = [('room1', {'type': 'system', 'content': 'They did it'})]
    result = success(emits, broadcasts)
    assert result == (True, None, emits, broadcasts)
```

## Phase 2: Standardize 3-Tuple Services (4-6 hours)

### 2.1 Update `room_service.py`

**Before:**
```python
def handle_room_command(...) -> Tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    # ... logic ...
    return True, None, emits
```

**After:**
```python
def handle_room_command(...) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    # ... logic ...
    return True, None, emits, broadcasts
```

**Changes Required:**
- Add `List[Tuple[str, dict]]` to return type
- Add `broadcasts: List[Tuple[str, dict]] = []` at top of each function
- Change all `return True, None, emits` to `return True, None, emits, broadcasts`
- Change all `return True, 'error msg', emits` to `return True, 'error msg', emits, broadcasts`
- **Optionally:** Add broadcasts where it makes sense (e.g., room creation announcement)

**Estimated:** 15 functions × 5min = 75 minutes

### 2.2 Update `faction_service.py`, `npc_service.py`, `object_service.py`

Same pattern as above. Check each service file:

```bash
# Find all services with 3-tuple returns
grep -n "-> Tuple\[bool, str | None, List\[dict\]\]" server/*_service.py
```

**Estimated:** 10 functions × 5min = 50 minutes

### 2.3 Update `setup_service.py`

This one currently returns `(bool, List[dict])` - need to add error AND broadcasts:

**Before:**
```python
def handle_setup_input(...) -> Tuple[bool, List[dict]]:
    emits = []
    # ... logic ...
    return True, emits
```

**After:**
```python
def handle_setup_input(...) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    emits = []
    broadcasts = []
    # ... logic ...
    return True, None, emits, broadcasts
```

**Estimated:** 5 functions × 10min = 50 minutes

## Phase 3: Update Routers (3-4 hours)

### 3.1 Update `admin_router.py`

**Before:**
```python
handled, err, emits2 = ctx.handle_room_command(world, ctx.state_path, args, sid)
if handled:
    if err:
        _emit_error(emit, MESSAGE_OUT, err)
    else:
        for payload in emits2:
            emit(MESSAGE_OUT, payload)
    return True
```

**After:**
```python
handled, err, emits2, broadcasts2 = ctx.handle_room_command(world, ctx.state_path, args, sid)
if handled:
    if err:
        _emit_error(emit, MESSAGE_OUT, err)
    else:
        for payload in emits2:
            emit(MESSAGE_OUT, payload)
        for room_id, payload in broadcasts2:
            ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
    return True
```

**Estimated:** 5 call sites × 10min = 50 minutes

### 3.2 Update Other Routers

Check each router for service calls:

```python
# interaction_router.py - Already handles broadcasts ✅
# movement_router.py - Already uses 4-tuple ✅
# dialogue_router.py - Check for service calls
# player_router.py - Check for service calls
```

**Estimated:** 3 routers × 20min = 60 minutes

## Phase 4: Update `server.py` Wrapper Functions (1-2 hours)

Several legacy helper functions in `server.py` need updating:

### 4.1 Update `_auth_handle` Wrapper

**Before:**
```python
def _auth_handle(...):
    # Calls auth_wizard_service.handle_interactive_auth
    # Which returns (handled, emits, broadcasts) - 3-tuple variant
    return handled, emits2, broadcasts2
```

**After:**
Keep wrapper but document that it's the "old" 3-tuple auth variant for backward compat.

**Estimated:** 15 minutes

### 4.2 Update CommandContext methods

Some CommandContext methods are thin wrappers around services:

```python
# In command_context.py
def handle_room_command(self, world, state_path, args, sid):
    from room_service import handle_room_command
    return handle_room_command(world, state_path, args, sid)
```

These will automatically return the new 4-tuple once services are updated. ✅

**Estimated:** 0 minutes (automatic)

## Phase 5: Update Tests (2-3 hours)

### 5.1 Update Service Unit Tests

**Pattern:**

```python
# Before:
handled, err, emits = room_service.handle_room_command(...)
assert handled
assert err is None

# After:
handled, err, emits, broadcasts = room_service.handle_room_command(...)
assert handled
assert err is None
assert isinstance(broadcasts, list)
```

**Files to update:**
- `test_auth_wizard_service.py` (may need special handling)
- `test_setup_service.py` ✓
- `test_interaction_service.py` ✓ (already 4-tuple)
- Any tests importing service functions directly

**Estimated:** 20 test functions × 5min = 100 minutes

### 5.2 Update Integration Tests

Check `service_tests.py` and other integration tests:

```bash
grep -n "handled, err, emits" server/test_*.py
```

**Estimated:** 30 minutes

## Phase 6: Documentation Updates (1 hour)

### 6.1 Update `docs/architecture.md`

Add section:

```markdown
### Service Layer Contract

All service modules follow a uniform return contract:

\`\`\`python
def service_function(...) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """
    Returns: (handled, error, emits, broadcasts)
        handled: True if this service recognized the request
        error: None on success, error message on failure
        emits: Messages to send to the acting player
        broadcasts: (room_id, payload) tuples for room announcements
    """
    emits = []
    broadcasts = []
    # ... logic ...
    return True, None, emits, broadcasts
\`\`\`

See `service_contract.py` for helper functions.
```

### 6.2 Update `CODING_STANDARDS.md`

Add requirement:

```markdown
### Service Layer Functions

All service layer functions MUST return the standard 4-tuple:

\`\`\`python
(handled: bool, error: str | None, emits: List[dict], broadcasts: List[Tuple[str, dict]])
\`\`\`

Use helpers from `service_contract.py`:
- `success(emits, broadcasts)` for successful operations
- `error(message)` for error returns
- `not_handled()` for unrecognized commands
```

### 6.3 Update `.github/copilot-instructions.md`

Update service contract examples to show 4-tuple consistently.

**Estimated:** 60 minutes total

## Phase 7: Validation & Cleanup (1 hour)

### 7.1 Run Full Test Suite

```bash
pytest -q server
```

### 7.2 Type Check (if using mypy)

```bash
mypy server/*.py
```

### 7.3 Smoke Test Server Startup

```bash
python server/server.py
# Should print AI status and start normally
```

### 7.4 Manual Integration Test

1. Start server
2. Connect with Godot client
3. Test commands:
   - `/auth create` - should work
   - `/room create` - should work
   - Movement commands - should work
   - Trade/barter - should work

**Estimated:** 60 minutes

## Total Time Estimate

| Phase | Time |
|-------|------|
| 1. Helper Module | 1-2 hours |
| 2. Service Updates | 4-6 hours |
| 3. Router Updates | 3-4 hours |
| 4. server.py Wrappers | 1-2 hours |
| 5. Test Updates | 2-3 hours |
| 6. Documentation | 1 hour |
| 7. Validation | 1 hour |
| **Total** | **13-19 hours** |

Realistically: **2-3 work days** for one developer working carefully.

## Risk Mitigation

### Risk: Breaking Existing Tests
**Mitigation:** Update tests incrementally in same commits as service changes. Run `pytest` after each service file.

### Risk: Missed Service Functions
**Mitigation:** Use grep to find all functions returning tuples:
```bash
grep -rn "-> Tuple\[" server/*_service.py
```

### Risk: Circular Import Issues
**Mitigation:** `service_contract.py` has no imports from other server modules. Safe to import anywhere.

### Risk: Forgetting Broadcasts
**Mitigation:** Even if broadcasts list is empty, it's harmless. We can add meaningful broadcasts in follow-up PRs.

## Success Criteria

- [ ] All service functions return 4-tuple
- [ ] All routers handle 4-tuple unpacking
- [ ] All tests pass (132+ passing)
- [ ] Server starts without errors
- [ ] Manual smoke test successful
- [ ] Documentation updated
- [ ] No new type errors (if using mypy)

## Post-Migration Improvements (Future PRs)

Once this is complete, we can:

1. **Add Meaningful Broadcasts** - Go back and add room announcements where appropriate
2. **Consolidate Emit Logic** - Use `emit_router_helper()` more widely
3. **ServiceResult Dataclass** - If team wants more type safety, migrate to dataclass
4. **Direct Messages** - Extend to 5-tuple pattern for trade/barter-like features
5. **Mutation Tracking** - Add optional `mutated` flag if needed

## Migration Checklist

### Services (Add 4th element: broadcasts)
- [ ] `room_service.py` - handle_room_command and all subfunctions
- [ ] `npc_service.py` - handle_npc_command and all subfunctions
- [ ] `faction_service.py` - handle_faction_command and all subfunctions
- [ ] `object_service.py` - All public functions
- [ ] `setup_service.py` - handle_setup_input (currently 2-tuple!)
- [ ] `admin_service.py` - promote_user, demote_user (already 3-tuple, add broadcasts)

### Routers (Update unpacking)
- [ ] `admin_router.py` - Multiple service calls (~5 sites)
- [ ] `player_router.py` - Check for service calls
- [ ] `dialogue_router.py` - Check for service calls
- [ ] `auth_router.py` - Uses 4-tuple already ✅

### Tests (Update assertions)
- [ ] `test_setup_service.py`
- [ ] `test_faction_service_offline.py`
- [ ] `resolver_tests.py` (if it calls services)
- [ ] `object_tests.py`
- [ ] Any integration tests in `service_tests.py`

### Documentation
- [ ] `docs/architecture.md` - Add service contract section
- [ ] `CODING_STANDARDS.md` - Add service layer requirements
- [ ] `.github/copilot-instructions.md` - Update examples
- [ ] `server/service_contract.py` - Create with docstrings

---

**Ready to start?** Begin with Phase 1 (helper module) and work through incrementally.
