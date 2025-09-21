# TinyMUD Code Standards (Summary)

This project follows the TinyMUD Coding Guidelines (see project docs). Key points:

- Keep control flow simple; prefer guard clauses.
- All loops bounded (no while true in gameplay/request paths).
- Predictable resources: load/static init early; avoid heavy I/O in hot paths.
- Small, focused functions (target < 50 LOC logic per function).
- Assert preconditions/postconditions generously during development.
- Restrict scope; avoid globals; underscore-private members respected.
- Always check return values and handle error cases.
- Use static typing rigorously:
  - Python: full type hints (mypy strict), 4-space indent, 99-char lines.
  - GDScript: typed variables and functions, tab indent, 100-char guide.
- Avoid train-wreck chains; respect Law of Demeter.
- Lint clean, run clean: mypy/flake8 clean; Godot editor with no warnings.
-  Comments should be written with an authorial style, tone, and voice of a proud and excited programmer explaining how every piece of the program works to a novice programmer that wants to contribute to the codebase but isn't confident with how to start.

Tooling in this repo:
- .editorconfig enforces Python (4 spaces) and GDScript (tabs).
- .flake8 sets max line length 99; .ini for mypy strict checks.
- Python quick tests: `python server/service_tests.py` and `python server/resolver_tests.py`.
