# Service Contract Audit & Uniformity Analysis

**Date:** October 7, 2025  
**Purpose:** High-impact structural refactoring to ensure long-term codebase health

## Problem Statement

The current router/service architecture has **inconsistent return contracts** that leak formatting responsibilities into `server.py`. This creates:
- Maintenance burden in the 3,000+ line `server.py`
- Cognitive overhead when adding new features
- Risk of bugs from mismatched tuple unpacking
- Difficulty testing service layers in isolation

## Current Service Contract Patterns

### Pattern 1: Three-Tuple (handled, error, emits)
**Used by:** `room_service.py`, most service functions

```python
def handle_room_command(...) -> Tuple[bool, str | None, List[dict]]:
    return (handled, error, emits)
```

**Characteristics:**
- ✅ Simple, clear error handling
- ✅ Direct emission pattern
- ❌ No broadcast support built-in
- ❌ Router must manually handle room broadcasts

**Usage in server.py:**
```python
handled, err, emits2 = ctx.handle_room_command(world, ctx.state_path, args, sid)
if handled:
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
    else:
        for payload in emits2:
            emit(MESSAGE_OUT, payload)
```

### Pattern 2: Four-Tuple (ok/success, error, emits, broadcasts)
**Used by:** `account_service.py`, `movement_service.py`, `admin_service.py`

```python
def create_account_and_login(...) -> Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]:
    return (success, error, emits, broadcasts)
```

**Characteristics:**
- ✅ Built-in broadcast support
- ✅ Clean separation of sender vs room messages
- ✅ Easier to handle room-wide announcements
- ❌ More complex unpacking
- ❌ Sometimes 'ok' means different things than 'handled'

**Usage in server.py:**
```python
ok, err, emits2, broadcasts2 = create_account_and_login(world, sid, ...)
if not ok:
    emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Failed.'})
    return True
for p in emits2:
    emit(MESSAGE_OUT, p)
for room_id, payload in broadcasts2:
    ctx.broadcast_to_room(room_id, payload, sid)
```

### Pattern 3: Five-Tuple (handled, emits, broadcasts, directs, mutated)
**Used by:** `trade_router._trade_handle`, `_barter_handle`

```python
def _trade_handle(...) -> tuple[bool, list[dict], list[tuple[str, dict]], list[tuple[str, dict]], bool]:
    return (handled, emits, broadcasts, directs, mutated)
```

**Characteristics:**
- ✅ Most comprehensive: supports direct messages to specific sids
- ✅ Explicit mutation tracking for persistence
- ✅ No error string (errors are just emits with type='error')
- ❌ Most complex unpacking
- ❌ 'mutated' flag is implicit contract for save_world calls

**Usage in server.py:**
```python
handled, emits, broadcasts, directs, mutated = trade_router._trade_handle(ctx, world, sid, text)
for payload in emits:
    emit(MESSAGE_OUT, payload)
for room_id, payload in broadcasts:
    ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
for target_sid, payload in directs:
    socketio.emit(MESSAGE_OUT, payload, to=target_sid)
if mutated:
    save_world(world, STATE_PATH)
```

### Pattern 4: Three-Tuple Auth Variant (handled, emits, broadcasts)
**Used by:** `auth_wizard_service.handle_interactive_auth`

```python
def handle_interactive_auth(...) -> Tuple[bool, List[dict], List[Tuple[str, dict]]]:
    return (handled, emits, broadcasts)
```

**Characteristics:**
- ✅ No error string (errors in emits)
- ✅ Built-in broadcast support
- ❌ No explicit ok/err separation
- ❌ Different from other 3-tuple patterns

### Pattern 5: Router Direct Emission (Boolean return only)
**Used by:** All `*_router.py` modules with `try_handle()` or `try_handle_flow()`

```python
def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    # Router calls service, then emits directly
    ok, err, emits, broadcasts = some_service(...)
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
    for p in emits:
        emit(MESSAGE_OUT, p)
    for room_id, payload in broadcasts:
        ctx.broadcast_to_room(room_id, payload, sid)
    return True  # Just indicate "I handled this command"
```

**Characteristics:**
- ✅ Clean router/service separation
- ✅ Router owns emission logic
- ✅ Simple boolean contract for command routing
- ❌ Emission logic duplicated in each router
- ❌ Testing harder (need to mock emit function)

## Identified Inconsistencies

### 1. Error Handling Divergence
- **Pattern 1 & 2:** Explicit error string as second return value
- **Pattern 3, 4, 5:** Errors embedded in emits list with `type: 'error'`

**Problem:** Callers must know which pattern to use. Some routers check `if err:` and emit separately, others trust the emits list.

### 2. Success vs Handled Semantics
- **Pattern 1:** Returns `handled` (did I recognize this command?)
- **Pattern 2:** Returns `ok/success` (did the operation succeed?)
- **Pattern 3 & 4:** Returns `handled` (was message consumed?)

**Problem:** Same position, different meaning. Pattern 2 returns `False` on failure but still handled the command.

### 3. Broadcast Tuple Inconsistency
- **Most patterns:** `List[Tuple[str, dict]]` where first element is `room_id`
- **Some services:** Don't support broadcasts at all, router must construct them

**Problem:** When adding room broadcast to a 3-tuple service, must change contract everywhere.

### 4. Direct Messages (Pattern 3 only)
- Only trade/barter flows support `directs: List[Tuple[str, dict]]` for targeted messages
- Other services construct these ad-hoc or rely on router logic

**Problem:** No standard way to send direct messages to non-acting players.

### 5. Mutation Tracking
- **Pattern 3:** Explicit `mutated: bool` flag
- **Others:** Implicit - service callers "know" to save after certain operations
- **Some routers:** Use `ctx.mark_world_dirty()` debounced pattern

**Problem:** Easy to forget to persist, or persist too often.

## Formatting Responsibilities Leaking to server.py

### Issue A: BBCode Formatting
Many services return plain text, relying on server.py or routers to wrap with BBCode tags:

```python
# In service:
emits.append({'type': 'system', 'content': f"Room '{room_id}' created."})

# In server.py (hypothetical leak):
content = f"[b]{room_name}[/b] created."  # Formatting decision in wrong layer
```

**Audit Result:** Most services already format BBCode correctly. ✅ No major leak here.

### Issue B: Message Type Selection
Some routers conditionally set `type: 'error'` vs `type: 'system'` based on service return:

```python
# auth_router.py
ok, err, emits2, broadcasts2 = create_account_and_login(...)
if not ok:
    emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Failed.'})
    return True
for p in emits2:
    emit(MESSAGE_OUT, p)
```

**Analysis:** This is intentional layering - service returns semantic result, router chooses presentation. ✅ Not a leak, but inconsistent with Pattern 3/4 where service controls message types.

### Issue C: Broadcast Construction
Several routers manually construct broadcast payloads after service returns:

```python
# Example from old server.py admin code:
handled, err, emits = some_room_operation(...)
# Router must know to broadcast:
broadcasts.append((room_id, {'type': 'system', 'content': f"Admin performed action."}))
```

**Problem:** Service knows the operation succeeded but can't tell other room occupants. Router must duplicate business logic to construct correct broadcast message.

### Issue D: Player Name Resolution
Some services expect resolved player names, others accept raw input:

```python
# Inconsistency:
# Service A: Expects ctx to resolve player name before call
# Service B: Does its own fuzzy resolution internally
```

**Problem:** Resolution logic sometimes in router, sometimes in service, sometimes in server.py helper functions.

## Recommended Uniform Contract

### Proposed Standard: ServiceResult Dataclass

```python
@dataclass
class ServiceResult:
    """Uniform return contract for all service layer functions.
    
    Fields:
        handled: Did this service recognize/process the request?
        emits: Messages to send to the acting player/client
        broadcasts: Messages to send to room occupants (room_id, payload)
        directs: Messages to send to specific other players (sid, payload)
        mutated: Did this operation change world state requiring persistence?
        error: Optional error message for logging/debugging (not user-facing)
    
    User-facing errors should be in emits with type='error'.
    The error field is for internal logging and should not be displayed to users.
    """
    handled: bool = True
    emits: List[dict] = field(default_factory=list)
    broadcasts: List[Tuple[str, dict]] = field(default_factory=list)
    directs: List[Tuple[str, dict]] = field(default_factory=list)
    mutated: bool = False
    error: Optional[str] = None  # Internal only, for logging
    
    @property
    def ok(self) -> bool:
        """Convenience: operation succeeded if handled and no error."""
        return self.handled and self.error is None
```

### Migration Strategy

**Phase 1: Create ServiceResult class + adapter helpers** (Non-breaking)
- Add `service_result.py` with dataclass definition
- Add backward-compat tuple unpacking helpers
- Update documentation

**Phase 2: Migrate high-traffic services** (One at a time, with tests)
- Start with `account_service.py` (already 4-tuple)
- Then `room_service.py` (most admin operations)
- Then `movement_service.py`

**Phase 3: Update routers to unified emission pattern**
- Create `emit_service_result(result: ServiceResult, ctx, sid, emit)` helper
- Refactor each router's try_handle to use helper

**Phase 4: Remove legacy shim functions from server.py**
- Once all tests pass with new contracts
- Remove old `_trade_handle`, `_barter_handle` wrappers

## Alternative: Keep Current Patterns but Document

If full migration is too risky, at minimum:

1. **Document each pattern clearly** in service module docstrings
2. **Add type hints everywhere** (already mostly done ✅)
3. **Create router template** showing correct unpacking for each pattern
4. **Standardize error handling:** Services EITHER return error string OR put errors in emits, never both
5. **Require all new services** to use Pattern 2 (4-tuple) as the "standard"

## Impact Assessment

### Current Technical Debt Cost
- **Cognitive load:** ~15min per new command to figure out correct contract
- **Bug risk:** Medium - 2-3 bugs per year from wrong tuple unpacking
- **Test complexity:** High - must mock emission differently per pattern
- **Onboarding friction:** High - new contributors confused by patterns

### Migration Cost (ServiceResult approach)
- **Implementation time:** ~40-60 hours across all services
- **Testing time:** ~20 hours (each service has unit tests to update)
- **Risk:** Medium (tuple unpacking failures if done wrong)
- **Benefit:** High - uniform contract, better testability, easier future features

### Migration Cost (Standardize on Pattern 2)
- **Implementation time:** ~20-30 hours (fewer services to change)
- **Testing time:** ~10 hours
- **Risk:** Low (just changing tuple length, not structure)
- **Benefit:** Medium - still some pattern divergence, but manageable

## Recommendation

**Preferred: Hybrid Approach**

1. **Short term (This week):** Standardize existing 3-tuples → 4-tuples
   - Change `room_service` and other 3-tuple services to Pattern 2
   - Add empty broadcasts list where needed
   - Update routers to unpack 4 values

2. **Medium term (Next sprint):** Create ServiceResult for new code
   - Introduce dataclass without breaking existing code
   - All NEW services use ServiceResult
   - Create compat layer: `ServiceResult.from_tuple()` and `.to_tuple()`

3. **Long term (Next quarter):** Migrate existing services to ServiceResult
   - One service per PR, with full test coverage
   - Update routers incrementally
   - Remove tuple contracts once all migrated

**Alternative if low risk appetite:** Document and standardize on Pattern 2 only.

## Action Items

- [ ] Create `service_result.py` with dataclass definition
- [ ] Audit all services and document their current contract in module docstrings  
- [ ] Create router emission helper to reduce duplication
- [ ] Write migration guide for contributors
- [ ] Update CODING_STANDARDS.md with canonical service contract
- [ ] Add contract validation in test fixtures
- [ ] Create "service contract" section in architecture.md

## Files Requiring Changes (Pattern 2 standardization)

### Services (3-tuple → 4-tuple)
- `room_service.py` - All functions
- `look_service.py` - If exists
- `faction_service.py` - Check return signatures
- `npc_service.py` - Check return signatures
- `object_service.py` - Check return signatures
- `setup_service.py` - Wizard functions (currently 2-tuple)

### Routers (Update unpacking)
- `admin_router.py` - Multiple service calls
- `player_router.py` - Update for new signatures
- All other routers using 3-tuple services

### Tests (Update assertions)
- `test_*_service.py` - All service unit tests
- `service_tests.py` - Integration tests
- Any test importing service functions directly

### Documentation
- `docs/architecture.md` - Update Router→Service→Emit pattern section
- `CODING_STANDARDS.md` - Add service contract requirements
- `.github/copilot-instructions.md` - Update contract examples

---

**Next Step:** Discuss with team and choose migration strategy. Then create implementation PR with Phase 1 changes.
