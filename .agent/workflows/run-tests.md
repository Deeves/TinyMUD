---
description: Run the full test suite for TinyMUD
---

# Run Tests Workflow

## Quick Run (all tests, minimal output)

// turbo

1. Run pytest with quiet output:

```bash
cd server && python -m pytest -q
```

## Verbose Run (detailed output)

// turbo
2. Run pytest with verbose output:

```bash
cd server && python -m pytest -v --tb=short
```

## Run Specific Test File

3. Run a single test file:

```bash
cd server && python -m pytest test_<filename>.py -v
```

## Run Tests Matching Pattern

4. Run tests matching a keyword:

```bash
cd server && python -m pytest -k "<pattern>" -v
```

## Run with Coverage

5. Run tests with coverage report:

```bash
cd server && python -m pytest --cov=. --cov-report=term-missing
```

## Skip Slow Tests

6. Run only fast tests:

```bash
cd server && python -m pytest -m "not slow" -v
```
