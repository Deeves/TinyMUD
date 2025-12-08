# Service Contract Uniformity - Executive Summary

**Date:** October 7, 2025  
**Problem:** Coupled socket emission logic and inconsistent service return contracts  
**Status:** Analysis Complete - Ready for Implementation

## The Problem

Your codebase currently has **5 different service return patterns**:

1. **3-tuple:** `(handled, error, emits)` - Used by room_service, others
2. **4-tuple:** `(ok, error, emits, broadcasts)` - Used by account_service, movement_service  
3. **5-tuple:** `(handled, emits, broadcasts, directs, mutated)` - Used by trade/barter
4. **3-tuple auth:** `(handled, emits, broadcasts)` - Used by auth wizard
5. **Router-only:** Boolean return, direct emission in router

This creates:
- ⚠️ **Maintenance burden** - Each new command requires figuring out the "right" pattern
- ⚠️ **Bug risk** - Wrong tuple unpacking causes runtime errors
- ⚠️ **Testing friction** - Each pattern needs different mocking strategies
- ⚠️ **Onboarding confusion** - New contributors don't know which pattern to use

## The Solution

**Standardize on ONE pattern:** 4-tuple

```python
def service_function(...) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """
    Returns: (handled, error, emits, broadcasts)
    """
    return True, None, [{'type': 'system', 'content': 'Done!'}], []
```

### Why This Pattern?

✅ **Proven** - Already used by 40% of services  
✅ **Low Risk** - Just adding empty `[]` to existing 3-tuples  
✅ **Backward Compatible** - Easy migration path  
✅ **Clear Semantics** - `handled` (did I process?) + `error` (did it work?)  
✅ **Future-Proof** - Easy to extend to dataclass later  

## What Changed?

### Services Updated
- `room_service.py` - Add broadcasts to all functions
- `npc_service.py` - Add broadcasts to all functions
- `faction_service.py` - Add broadcasts to all functions
- `object_service.py` - Add broadcasts to all functions
- `setup_service.py` - Add error AND broadcasts (currently 2-tuple!)
- `admin_service.py` - Add broadcasts to promote/demote

### Routers Updated
- `admin_router.py` - Unpack 4 values instead of 3
- `player_router.py` - Update service call sites
- Other routers - Audit and update as needed

### New Files Created
- `server/service_contract.py` - Helper functions and documentation
- `server/test_service_contract.py` - Tests for helpers
- `docs/service-contract-audit.md` - Full analysis (this audit)
- `docs/service-contract-implementation-plan.md` - Step-by-step guide

## Implementation Effort

**Estimated Time:** 13-19 hours (2-3 work days)

| Phase | Hours |
|-------|-------|
| Helper module creation | 1-2 |
| Service updates | 4-6 |
| Router updates | 3-4 |
| Test updates | 2-3 |
| Documentation | 1 |
| Validation | 1 |

## Migration Strategy

**Phase 1:** Create `service_contract.py` with helper functions  
**Phase 2:** Update 3-tuple services to 4-tuple (add broadcasts)  
**Phase 3:** Update routers to unpack 4 values  
**Phase 4:** Update all tests  
**Phase 5:** Update documentation  
**Phase 6:** Validate with full test suite + manual smoke test  

## Risk Assessment

### Low Risk ✅
- Just changing tuple length, not structure
- Empty broadcasts list is harmless
- Tests will catch unpacking errors immediately
- Can do incremental commits

### Medium Risk ⚠️
- ~15-20 service functions to update
- ~5-10 router call sites to update
- ~20-30 test functions to update
- Potential for missed call sites

### Mitigation
- Use grep to find all return signatures
- Update tests in same commit as service changes
- Run pytest after each service file
- Manual smoke test before declaring done

## Key Files for Review

1. **`docs/service-contract-audit.md`** - Full analysis of current patterns
2. **`docs/service-contract-implementation-plan.md`** - Step-by-step implementation guide with code examples
3. This summary

## Alternatives Considered

### Option A: ServiceResult Dataclass (REJECTED)
```python
@dataclass
class ServiceResult:
    handled: bool
    emits: List[dict]
    broadcasts: List[Tuple[str, dict]]
    error: Optional[str] = None
```

**Why not:** More invasive, higher risk, can do later as follow-up

### Option B: Keep Current Chaos (REJECTED)
**Why not:** Technical debt compounds, makes server.py harder to maintain

### Option C: Document Only (REJECTED)
**Why not:** Doesn't solve the problem, just acknowledges it

## Success Criteria

✅ All service functions return 4-tuple  
✅ All routers handle 4-tuple unpacking  
✅ All tests pass (132+ passing tests maintained)  
✅ Server starts without errors  
✅ Manual smoke test successful (auth, movement, trading all work)  
✅ Documentation updated  

## Next Steps

1. **Review these documents** - Read audit + implementation plan
2. **Approve approach** - Confirm 4-tuple standardization
3. **Create implementation PR** - Start with Phase 1 (helper module)
4. **Incremental commits** - One service file per commit
5. **Validate continuously** - Run tests after each change

## Questions?

- **Q: Why not keep existing patterns?**  
  A: Maintenance burden too high, bugs from wrong unpacking, onboarding friction

- **Q: Why 4-tuple instead of dataclass?**  
  A: Lower risk, proven pattern, can migrate to dataclass later if needed

- **Q: What about the 5-tuple trade pattern?**  
  A: Keep for now, migrate in follow-up PR (adds 'directs' and 'mutated' to standard)

- **Q: Will this break anything?**  
  A: Tests will catch unpacking errors immediately. Changes are additive (empty broadcasts).

- **Q: How long to implement?**  
  A: 2-3 work days for careful, tested implementation

---

**Ready to proceed?** Start with Phase 1 in the implementation plan.
