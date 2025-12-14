---
description: Run test coverage report for TinyMUD
---

# Coverage Workflow

## Quick Coverage (terminal summary)

// turbo

1. Run tests with coverage summary:

```bash
python -m pytest server --cov -q
```

## Detailed Coverage Report

// turbo
2. Generate HTML coverage report:

```bash
python -m pytest server --cov --cov-report=html
```

Then open `htmlcov/index.html` in your browser for a detailed breakdown.

## Coverage with Missing Lines

3. Show which lines are not covered:

```bash
python -m pytest server --cov --cov-report=term-missing
```

## Coverage for Specific Module

4. Check coverage for a single file:

```bash
python -m pytest server --cov=server/combat_service.py --cov-report=term-missing
```

## Coverage Thresholds

5. Fail if coverage drops below threshold:

```bash
python -m pytest server --cov --cov-fail-under=40
```

## Current Coverage Summary

| Module | Coverage | Notes |
|--------|----------|-------|
| Overall | ~43% | Working baseline |
| Core services | Higher | Well tested |
| Server.py | Lower | Complex, many branches |

## Files to Focus On

Priority modules that could benefit from more tests:

- `server.py` - Main handler logic
- `game_loop.py` - NPC action execution
- `goap_state_manager.py` - AI planning
