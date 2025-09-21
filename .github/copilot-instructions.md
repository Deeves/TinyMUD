# TinyMUD – AI agent working notes

Use this as the “you’re new here but need to be productive fast” guide. 


## Architecture in 6 bullets
- Client: Godot 4 (GDScript). Main scene `ChatUI.tscn` with `src/chat_ui.gd`; minimal Socket.IO v4 client in `src/socket_io_client.gd` built on `WebSocketPeer`.
- Server: Python Flask‑SocketIO in `server/server.py` (prefers eventlet). Small, testable helpers live in `server/*_service.py` and pure data model in `server/world.py`.
- Transport: Socket.IO (EIO v4) over ws. Client emits `message_to_server`; server emits `message`.
- AI: Optional Google Gemini via `google-generativeai`. If no key, server sends a friendly offline fallback.
- Persistence: Single JSON file `server/world_state.json` via `World.save_to_file`/`load_from_file`. Backfills missing UUIDs/fields for compatibility.
- Tests: Pytest unit tests for wizards/services in `server/test_*.py`.

## Message contracts (don’t break these)
- Client → Server event: `message_to_server` with `{ "content": string }`.
- Server → Client event: `message` with `{ "type": "system"|"player"|"npc"|"error", "content": string, "name"?: string }`.
- Chat UI expects BBCode-friendly text; types colorize output. Keep keys and casing stable.

## Server patterns you must follow
- Most “features” are extracted into pure service modules that return payloads; socket emission happens in `server.py`.
  - Example contracts:
    - `account_service.create_account_and_login(...) -> (ok, err, emits, broadcasts)`
    - `room_service.handle_room_command(...) -> (handled, err, emits)`
- Normalize and parse user input via helpers from `id_parse_utils` (e.g., `_strip_quotes`, `_parse_pipe_parts`, fuzzy resolvers). Accept `'here'` for room arguments.
- After mutating world state, attempt to persist: `world.save_to_file(STATE_PATH)` (best‑effort; swallow errors).
- Use `broadcast_to_room(room_id, payload, exclude_sid=sid)` to echo to others; use `emit('message', payload)` for the sender.
- Admin gating: check `sid in admins` before admin commands. First created user is auto‑admin.

## World model and linking
- `World` holds `rooms`, `players`, `users`, `npc_sheets`, `npc_ids`, `relationships`, and `object_templates`.
- Rooms keep stable UUIDs for rooms/doors/stairs plus `objects` where doors/stairs are persisted as `Object` with tags `{ "Immovable", "Travel Point" }`.
- When renaming rooms or adding doors/stairs, update reciprocal links and ensure `door_ids`/`stairs_*_id` and corresponding `objects` exist.

## AI integration
- `server.py` builds a prompt from: world meta, player sheet, NPC sheet, and relationship context; then calls Gemini.
- Safety level is set per‑world (`world.safety_level`): `G | PG-13 | R | OFF`. Map to SDK `safety_settings` if available. Always keep an offline fallback.

## Comments
- A file containing code should be roughly 70% code and 30% comments as a rule of thumb.
- Use comments to explain the "why" behind complex logic, not just the "what".
- Write comments with an authorial style, tone, and voice of a proud and excited programmer explaining how every piece of the program works to a novice programmer that wants to contribute to the codebase but isn't confident with how and where to start.

## Common workflows (PowerShell)
- Install deps: `python -m pip install -r .\requirements.txt` (run from repo root or `server\..` accordingly).
- Run server locally: `python server\server.py` (prints “Gemini API configured successfully.” when key is valid).
- Optional key: `$env:GEMINI_API_KEY = "..."` (or `GOOGLE_API_KEY`).
- Run tests (from repo root): `pytest -q server`.

## Adding commands (tiny example)
- For a new admin command, parse in `handle_command` then delegate to a service function:
  - Service returns `handled/ok, err, emits[, broadcasts]`.
  - In `server.py`, loop `emit('message', p)` and `broadcast_to_room(...)` as appropriate.
  - Save world if you mutated it; keep try/except around saves.

## Client expectations
- Don’t change event names or JSON shape. `src/chat_ui.gd` renders based on `type` and optional `name`.
- The minimal Socket.IO client assumes EIO v4 and default namespace (`/`). Avoid server changes that require namespaces/acks.

## Pitfalls and invariants
- Never block the server thread; prefer eventlet (installed via requirements) to avoid Werkzeug WS quirks.
- Keep fuzzy resolvers tolerant but deterministic (exact CI > unique prefix > unique substring). Return helpful suggestions on misses.
- On any world mutation, ensure related UUID maps and linked objects are maintained (doors/stairs/objects).

Key files: `server/server.py`, `server/world.py`, `server/*_service.py`, `src/chat_ui.gd`, `src/socket_io_client.gd`, `README.md`, `docs/architecture.md`.
