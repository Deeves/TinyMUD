# TinyMUD – AI agent working notes# TinyMUD – AI agent working notes# TinyMUD – AI agent working n## Server patterns you must follow## Common workflows (PowerShell)



Use this as the "you're new here but need to be productive fast" guide. - **Setup venv**: Use `.venv/Scripts/python.exe` after activation. VS Code tasks prefer this path.



Use this as the "you're new here but need to be productive fast" guide. - Install deps: `python -m pip install -r .\requirements.txt` (run from repo root).

## Architecture in 7 bullets

- Client: Godot 4 (GDScript). Main scene `ChatUI.tscn` with `src/chat_ui.gd`; minimal Socket.IO v4 client in `src/socket_io_client.gd` built on `WebSocketPeer`.- **Run server**: Use VS Code task "Run server to verify startup print" or `python server\server.py` (prints AI status on startup).

- Server: Python Flask‑SocketIO in `server/server.py` (prefers eventlet). Command handling delegated to router modules (`server/*_router.py`) which use service helpers (`server/*_service.py`).

- Transport: Socket.IO (EIO v4) over ws. Client emits `message_to_server`; server emits `message`.- **Run tests**: Use VS Code task "Run pytest server" or `pytest -q server` (from repo root).

- AI: Optional Google Gemini via `google-generativeai`. Dual models: lightweight chat + stronger GOAP planner. If no key, server sends offline fallbacks.

- GOAP NPCs: NPCs plan actions to satisfy needs (hunger, thirst, sleep, socialization) using AI when players present, offline planner otherwise. Toggle via `world.advanced_goap_enabled`.## Architecture in 7 bullets- Optional key: `$env:GEMINI_API_KEY = "..."` (or `GOOGLE_API_KEY`).

- Persistence: Single JSON file `server/world_state.json` via `World.save_to_file`/`load_from_file`. Backfills missing UUIDs/fields for compatibility.

- Tests: Pytest unit tests for services in `server/test_*.py`. MockAI framework for deterministic AI testing without API keys.- Client: Godot 4 (GDScript). Main scene `ChatUI.tscn` with `src/chat_ui.gd`; minimal Socket.IO v4 client in `src/socket_io_client.gd` built on `WebSocketPeer`.- **Reset world**: `python server\server.py --purge --yes` deletes `world_state.json` and exits.Router → Service → Emit pattern**: Commands flow through `*_router.py` modules that call `*_service.py` helpers. Services return `(handled/ok, err, emits[, broadcasts])` tuples. Routers handle emission in `server.py`.



## Message contracts (don't break these)- Server: Python Flask‑SocketIO in `server/server.py` (prefers eventlet). Command handling delegated to router modules (`server/*_router.py`) which use service helpers (`server/*_service.py`).  - Example contracts:

- Client → Server event: `message_to_server` with `{ "content": string }`.

- Server → Client event: `message` with `{ "type": "system"|"player"|"npc"|"error", "content": string, "name"?: string }`.- Transport: Socket.IO (EIO v4) over ws. Client emits `message_to_server`; server emits `message`.    - `account_service.create_account_and_login(...) -> (ok, err, emits, broadcasts)`

- Chat UI expects BBCode-friendly text; types colorize output. Keep keys and casing stable.

- AI: Optional Google Gemini via `google-generativeai`. Dual models: lightweight chat + stronger GOAP planner. If no key, server sends offline fallbacks.    - `room_service.handle_room_command(...) -> (handled, err, emits)`

## Server patterns you must follow

- **Router → Service → Emit pattern**: Commands flow through `*_router.py` modules that call `*_service.py` helpers. Services return `(handled/ok, err, emits[, broadcasts])` tuples. Routers handle emission in `server.py`.- GOAP NPCs: NPCs plan actions to satisfy needs (hunger, thirst, sleep, socialization) using AI when players present, offline planner otherwise. Toggle via `world.advanced_goap_enabled`.- **CommandContext**: Pass `CommandContext` to routers with shared state (`world`, `sessions`, `admins`, `message_out`, etc.) instead of individual parameters.

  - Example contracts:

    - `account_service.create_account_and_login(...) -> (ok, err, emits, broadcasts)`- Persistence: Single JSON file `server/world_state.json` via `World.save_to_file`/`load_from_file`. Backfills missing UUIDs/fields for compatibility.- **Safe execution**: Replace bare `except Exception: pass` with `safe_call()` from `safe_utils.py`. Logs first occurrence of each exception type while maintaining graceful fallback.

    - `room_service.handle_room_command(...) -> (handled, err, emits)`

- **CommandContext**: Pass `CommandContext` to routers with shared state (`world`, `sessions`, `admins`, `message_out`, etc.) instead of individual parameters.- Tests: Pytest unit tests for services in `server/test_*.py`. MockAI framework for deterministic AI testing without API keys.- **Input parsing**: Normalize user input via helpers from `id_parse_utils` (e.g., `_strip_quotes`, `_parse_pipe_parts`, fuzzy resolvers). Accept `'here'` for room arguments.

- **Safe execution**: Replace bare `except Exception: pass` with `safe_call()` from `safe_utils.py`. Logs first occurrence of each exception type while maintaining graceful fallback.

- **Input parsing**: Normalize user input via helpers from `id_parse_utils` (e.g., `_strip_quotes`, `_parse_pipe_parts`, fuzzy resolvers). Accept `'here'` for room arguments.- After mutating world state, attempt to persist: `world.save_to_file(STATE_PATH)` (best‑effort; swallow errors).

- After mutating world state, attempt to persist: `world.save_to_file(STATE_PATH)` (best‑effort; swallow errors).

- Use `broadcast_to_room(room_id, payload, exclude_sid=sid)` to echo to others; use `emit('message', payload)` for the sender.## Message contracts (don't break these)- Use `broadcast_to_room(room_id, payload, exclude_sid=sid)` to echo to others; use `emit('message', payload)` for the sender.

- Admin gating: check `sid in admins` before admin commands. First created user is auto‑admin.

- Client → Server event: `message_to_server` with `{ "content": string }`.- Admin gating: check `sid in admins` before admin commands. First created user is auto‑admin.se this as the "you're new here but need to be productive fast" guide. 

## Critical architectural constraints

- **File size limit**: `server.py` MUST stay under 1,500 lines. Currently at 3,006 lines - URGENT refactoring needed.- Server → Client event: `message` with `{ "type": "system"|"player"|"npc"|"error", "content": string, "name"?: string }`.

- **Comment density**: Files should be ~70% code, ~30% comments. Explain "why" not "what" with enthusiastic teaching voice.

- **Extract large subsystems**: NPC GOAP system (`_npc_*` functions) should be extracted to `npc_service.py` or similar modules.- Chat UI expects BBCode-friendly text; types colorize output. Keep keys and casing stable.



## World model and linking## Architecture in 7 bullets

- `World` holds `rooms`, `players`, `users`, `npc_sheets`, `npc_ids`, `relationships`, `object_templates`, and GOAP settings.

- **NPCs have needs**: Each NPC has `hunger`, `thirst`, `sleep`, `socialization` values (0‑100) and a `needs_last_updated` timestamp. NPCs plan actions to satisfy needs using AI or offline heuristics.## Server patterns you must follow- Client: Godot 4 (GDScript). Main scene `ChatUI.tscn` with `src/chat_ui.gd`; minimal Socket.IO v4 client in `src/socket_io_client.gd` built on `WebSocketPeer`.

- **Objects system**: Rich `Object` model with `tags`, `material_tag`, `owner_id`, `crafting_recipe`, and travel linking (`link_target_room_id`). Doors/stairs are objects with `{"Immovable", "Travel Point"}` tags.

- When renaming rooms or adding doors/stairs, update reciprocal links and ensure `door_ids`/`stairs_*_id` and corresponding `objects` exist.- **Router → Service → Emit pattern**: Commands flow through `*_router.py` modules that call `*_service.py` helpers. Services return `(handled/ok, err, emits[, broadcasts])` tuples. Routers handle emission in `server.py`.- Server: Python Flask‑SocketIO in `server/server.py` (prefers eventlet). Command handling delegated to router modules (`server/*_router.py`) which use service helpers (`server/*_service.py`).



## AI integration  - Example contracts:- Transport: Socket.IO (EIO v4) over ws. Client emits `message_to_server`; server emits `message`.

- **Dual AI models**: Chat model (`chat_model`) for roleplay + planning model (`plan_model`) for GOAP. Both optional; graceful fallbacks exist.

- **MockAI testing**: Use `mock_ai.py` framework for deterministic tests. Import `MockAIModel`, `create_npc_generation_mock`, `create_goap_planning_mock` from `mock_ai_examples.py`.    - `account_service.create_account_and_login(...) -> (ok, err, emits, broadcasts)`- AI: Optional Google Gemini via `google-generativeai`. Dual models: lightweight chat + stronger GOAP planner. If no key, server sends offline fallbacks.

- **GOAP planning**: NPCs use AI JSON generation for action sequences when `world.advanced_goap_enabled=True` and players present. Otherwise offline heuristics.

- Safety level per‑world (`world.safety_level`): `G | PG-13 | R | OFF`. Always include offline fallback for AI-disabled scenarios.    - `room_service.handle_room_command(...) -> (handled, err, emits)`- GOAP NPCs: NPCs plan actions to satisfy needs (hunger, thirst, sleep, socialization) using AI when players present, offline planner otherwise. Toggle via `world.advanced_goap_enabled`.



## Comments- **CommandContext**: Pass `CommandContext` to routers with shared state (`world`, `sessions`, `admins`, `message_out`, etc.) instead of individual parameters.- Persistence: Single JSON file `server/world_state.json` via `World.save_to_file`/`load_from_file`. Backfills missing UUIDs/fields for compatibility.

- A file containing code should be roughly 70% code and 30% comments as a rule of thumb.

- Use comments to explain the "why" behind complex logic, not just the "what".- **Safe execution**: Replace bare `except Exception: pass` with `safe_call()` from `safe_utils.py`. Logs first occurrence of each exception type while maintaining graceful fallback.- Tests: Pytest unit tests for services in `server/test_*.py`. MockAI framework for deterministic AI testing without API keys.AI agent working notes

- Write comments with an authorial style, tone, and voice of a proud and excited programmer explaining how every piece of the program works to a novice programmer that wants to contribute to the codebase but isn't confident with how and where to start.

- **Input parsing**: Normalize user input via helpers from `id_parse_utils` (e.g., `_strip_quotes`, `_parse_pipe_parts`, fuzzy resolvers). Accept `'here'` for room arguments.

## Common workflows (PowerShell)

- **Setup venv**: Use `.venv/Scripts/python.exe` after activation. VS Code tasks prefer this path.- After mutating world state, attempt to persist: `world.save_to_file(STATE_PATH)` (best‑effort; swallow errors).Use this as the “you’re new here but need to be productive fast” guide. 

- Install deps: `python -m pip install -r .\requirements.txt` (run from repo root).

- **Run server**: Use VS Code task "Run server to verify startup print" or `python server\server.py` (prints AI status on startup).- Use `broadcast_to_room(room_id, payload, exclude_sid=sid)` to echo to others; use `emit('message', payload)` for the sender.

- **Run tests**: Use VS Code task "Run pytest server" or `pytest -q server` (from repo root).

- Optional key: `$env:GEMINI_API_KEY = "..."` (or `GOOGLE_API_KEY`).- Admin gating: check `sid in admins` before admin commands. First created user is auto‑admin.

- **Reset world**: `python server\server.py --purge --yes` deletes `world_state.json` and exits.

## Architecture in 6 bullets

## Adding commands (tiny example)

- **New router pattern**: Create `my_feature_router.py` with `try_handle(ctx, sid, cmd, args, raw, emit)` that returns `bool`. Register in `server.py`'s router list.## World model and linking- Client: Godot 4 (GDScript). Main scene `ChatUI.tscn` with `src/chat_ui.gd`; minimal Socket.IO v4 client in `src/socket_io_client.gd` built on `WebSocketPeer`.

- **Service contract**: Services return `(handled/ok, err, emits[, broadcasts])` tuples. In router, emit each payload and handle broadcasts.

- **Testing**: Write pytest using `CommandContext` and mock objects. See `test_*_service.py` for patterns.- `World` holds `rooms`, `players`, `users`, `npc_sheets`, `npc_ids`, `relationships`, `object_templates`, and GOAP settings.- Server: Python Flask‑SocketIO in `server/server.py` (prefers eventlet). Small, testable helpers live in `server/*_service.py` and pure data model in `server/world.py`.

- Save world if you mutated it; use `safe_call()` around saves.

- **NPCs have needs**: Each NPC has `hunger`, `thirst`, `sleep`, `socialization` values (0‑100) and a `needs_last_updated` timestamp. NPCs plan actions to satisfy needs using AI or offline heuristics.- Transport: Socket.IO (EIO v4) over ws. Client emits `message_to_server`; server emits `message`.

## Client expectations

- Don't change event names or JSON shape. `src/chat_ui.gd` renders based on `type` and optional `name`.- **Objects system**: Rich `Object` model with `tags`, `material_tag`, `owner_id`, `crafting_recipe`, and travel linking (`link_target_room_id`). Doors/stairs are objects with `{"Immovable", "Travel Point"}` tags.- AI: Optional Google Gemini via `google-generativeai`. If no key, server sends a friendly offline fallback.

- The minimal Socket.IO client assumes EIO v4 and default namespace (`/`). Avoid server changes that require namespaces/acks.

- When renaming rooms or adding doors/stairs, update reciprocal links and ensure `door_ids`/`stairs_*_id` and corresponding `objects` exist.- Persistence: Single JSON file `server/world_state.json` via `World.save_to_file`/`load_from_file`. Backfills missing UUIDs/fields for compatibility.

## Pitfalls and invariants

- Never block the server thread; prefer eventlet (installed via requirements) to avoid Werkzeug WS quirks.- Tests: Pytest unit tests for wizards/services in `server/test_*.py`.

- Keep fuzzy resolvers tolerant but deterministic (exact CI > unique prefix > unique substring). Return helpful suggestions on misses.

- On any world mutation, ensure related UUID maps and linked objects are maintained (doors/stairs/objects).## AI integration



Key files: `server/server.py`, `server/world.py`, `server/*_service.py`, `src/chat_ui.gd`, `src/socket_io_client.gd`, `README.md`, `docs/architecture.md`.- **Dual AI models**: Chat model (`chat_model`) for roleplay + planning model (`plan_model`) for GOAP. Both optional; graceful fallbacks exist.## Message contracts (don’t break these)

- **MockAI testing**: Use `mock_ai.py` framework for deterministic tests. Import `MockAIModel`, `create_npc_generation_mock`, `create_goap_planning_mock` from `mock_ai_examples.py`.- Client → Server event: `message_to_server` with `{ "content": string }`.

- **GOAP planning**: NPCs use AI JSON generation for action sequences when `world.advanced_goap_enabled=True` and players present. Otherwise offline heuristics.- Server → Client event: `message` with `{ "type": "system"|"player"|"npc"|"error", "content": string, "name"?: string }`.

- Safety level per‑world (`world.safety_level`): `G | PG-13 | R | OFF`. Always include offline fallback for AI-disabled scenarios.- Chat UI expects BBCode-friendly text; types colorize output. Keep keys and casing stable.



## Comments## Server patterns you must follow

- A file containing code should be roughly 70% code and 30% comments as a rule of thumb.- Most “features” are extracted into pure service modules that return payloads; socket emission happens in `server.py`.

- Use comments to explain the "why" behind complex logic, not just the "what".  - Example contracts:

- Write comments with an authorial style, tone, and voice of a proud and excited programmer explaining how every piece of the program works to a novice programmer that wants to contribute to the codebase but isn't confident with how and where to start.    - `account_service.create_account_and_login(...) -> (ok, err, emits, broadcasts)`

    - `room_service.handle_room_command(...) -> (handled, err, emits)`

## Common workflows (PowerShell)- Normalize and parse user input via helpers from `id_parse_utils` (e.g., `_strip_quotes`, `_parse_pipe_parts`, fuzzy resolvers). Accept `'here'` for room arguments.

- **Setup venv**: Use `.venv/Scripts/python.exe` after activation. VS Code tasks prefer this path.- After mutating world state, attempt to persist: `world.save_to_file(STATE_PATH)` (best‑effort; swallow errors).

- Install deps: `python -m pip install -r .\requirements.txt` (run from repo root).- Use `broadcast_to_room(room_id, payload, exclude_sid=sid)` to echo to others; use `emit('message', payload)` for the sender.

- **Run server**: Use VS Code task "Run server to verify startup print" or `python server\server.py` (prints AI status on startup).- Admin gating: check `sid in admins` before admin commands. First created user is auto‑admin.

- **Run tests**: Use VS Code task "Run pytest server" or `pytest -q server` (from repo root).

- Optional key: `$env:GEMINI_API_KEY = "..."` (or `GOOGLE_API_KEY`).## World model and linking

- **Reset world**: `python server\server.py --purge --yes` deletes `world_state.json` and exits.- `World` holds `rooms`, `players`, `users`, `npc_sheets`, `npc_ids`, `relationships`, `object_templates`, and GOAP settings.

- **NPCs have needs**: Each NPC has `hunger`, `thirst`, `sleep`, `socialization` values (0‑100) and a `needs_last_updated` timestamp. NPCs plan actions to satisfy needs using AI or offline heuristics.

## Adding commands (tiny example)- **Objects system**: Rich `Object` model with `tags`, `material_tag`, `owner_id`, `crafting_recipe`, and travel linking (`link_target_room_id`). Doors/stairs are objects with `{"Immovable", "Travel Point"}` tags.

- **New router pattern**: Create `my_feature_router.py` with `try_handle(ctx, sid, cmd, args, raw, emit)` that returns `bool`. Register in `server.py`'s router list.- When renaming rooms or adding doors/stairs, update reciprocal links and ensure `door_ids`/`stairs_*_id` and corresponding `objects` exist.

- **Service contract**: Services return `(handled/ok, err, emits[, broadcasts])` tuples. In router, emit each payload and handle broadcasts.

- **Testing**: Write pytest using `CommandContext` and mock objects. See `test_*_service.py` for patterns.## AI integration

- Save world if you mutated it; use `safe_call()` around saves.- **Dual AI models**: Chat model (`chat_model`) for roleplay + planning model (`plan_model`) for GOAP. Both optional; graceful fallbacks exist.

- **MockAI testing**: Use `mock_ai.py` framework for deterministic tests. Import `MockAIModel`, `create_npc_generation_mock`, `create_goap_planning_mock` from `mock_ai_examples.py`.

## Client expectations- **GOAP planning**: NPCs use AI JSON generation for action sequences when `world.advanced_goap_enabled=True` and players present. Otherwise offline heuristics.

- Don't change event names or JSON shape. `src/chat_ui.gd` renders based on `type` and optional `name`.- Safety level per‑world (`world.safety_level`): `G | PG-13 | R | OFF`. Always include offline fallback for AI-disabled scenarios.

- The minimal Socket.IO client assumes EIO v4 and default namespace (`/`). Avoid server changes that require namespaces/acks.

## Comments

## Pitfalls and invariants- A file containing code should be roughly 70% code and 30% comments as a rule of thumb.

- Never block the server thread; prefer eventlet (installed via requirements) to avoid Werkzeug WS quirks.- Use comments to explain the "why" behind complex logic, not just the "what".

- Keep fuzzy resolvers tolerant but deterministic (exact CI > unique prefix > unique substring). Return helpful suggestions on misses.- Write comments with an authorial style, tone, and voice of a proud and excited programmer explaining how every piece of the program works to a novice programmer that wants to contribute to the codebase but isn't confident with how and where to start.

- On any world mutation, ensure related UUID maps and linked objects are maintained (doors/stairs/objects).

## Common workflows (PowerShell)

Key files: `server/server.py`, `server/world.py`, `server/*_service.py`, `src/chat_ui.gd`, `src/socket_io_client.gd`, `README.md`, `docs/architecture.md`.- Install deps: `python -m pip install -r .\requirements.txt` (run from repo root or `server\..` accordingly).
- Run server locally: `python server\server.py` (prints “Gemini API configured successfully.” when key is valid).
- Optional key: `$env:GEMINI_API_KEY = "..."` (or `GOOGLE_API_KEY`).
- Run tests (from repo root): `pytest -q server`.

## Adding commands (tiny example)
- **New router pattern**: Create `my_feature_router.py` with `try_handle(ctx, sid, cmd, args, raw, emit)` that returns `bool`. Register in `server.py`'s router list.
- **Service contract**: Services return `(handled/ok, err, emits[, broadcasts])` tuples. In router, emit each payload and handle broadcasts.
- **Testing**: Write pytest using `CommandContext` and mock objects. See `test_*_service.py` for patterns.
- Save world if you mutated it; use `safe_call()` around saves.

## Client expectations
- Don’t change event names or JSON shape. `src/chat_ui.gd` renders based on `type` and optional `name`.
- The minimal Socket.IO client assumes EIO v4 and default namespace (`/`). Avoid server changes that require namespaces/acks.

## Pitfalls and invariants
- Never block the server thread; prefer eventlet (installed via requirements) to avoid Werkzeug WS quirks.
- Keep fuzzy resolvers tolerant but deterministic (exact CI > unique prefix > unique substring). Return helpful suggestions on misses.
- On any world mutation, ensure related UUID maps and linked objects are maintained (doors/stairs/objects).

Key files: `server/server.py`, `server/world.py`, `server/*_service.py`, `src/chat_ui.gd`, `src/socket_io_client.gd`, `README.md`, `docs/architecture.md`.
