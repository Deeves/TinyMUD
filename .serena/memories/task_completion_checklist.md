# Task Completion Checklist

## After Completing Any Task

### 1. Testing
- **Run all tests**: `pytest -q server` from repo root
- **Verify no regressions**: Ensure existing functionality still works
- **Add new tests**: If adding features, include corresponding tests
- **Test edge cases**: Especially for parsing and resolution logic

### 2. Code Quality
- **Check type hints**: Ensure all functions have proper type annotations
- **Review comments**: Maintain ~70% code, ~30% comments ratio
- **Verify patterns**: Follow Router → Service → Emit pattern
- **Check error handling**: Use safe_call() and structured error returns

### 3. Integration Testing
- **Start server**: Verify it starts without errors
- **Test manually**: Connect client and test affected functionality
- **Check AI integration**: If AI features affected, test with/without API key
- **Verify persistence**: Ensure world state saves/loads correctly

### 4. Documentation
- **Update docstrings**: If function signatures or behavior changed
- **Update comments**: Ensure explanatory comments are accurate
- **Check architectural docs**: Update if patterns changed

### 5. File Size Limits
- **server.py**: Must stay under 1,500 lines (currently over limit - needs refactoring)
- **Extract large subsystems**: Move functionality to dedicated service modules

### 6. Determinism and Reliability
- **Fuzzy resolution**: Ensure stable, predictable ordering
- **Test ambiguous cases**: Verify consistent behavior for tie cases
- **Locale independence**: Ensure sorting works consistently across systems