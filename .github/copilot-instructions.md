# TinyMUD – AI Agent Coding Guide

Use this as your "you're new here but need to be productive fast" reference.

## Architecture Overview

**TinyMUD is a modern text-based MUD with AI-powered NPCs.** The system uses a modular Router → Service → Emit pattern designed for incremental refactoring from a monolithic server.

- **Client**: Godot 4 (GDScript) with minimal Socket.IO v4 client (`src/socket_io_client.gd`)
- **Server**: Python Flask-SocketIO (`server/server.py`) delegates to service modules (`server/*_service.py`)  
- **Transport**: Socket.IO (EIO v4) over WebSocket; client emits `message_to_server`, server emits `message`
- **AI**: Optional Google Gemini for NPC chat + GOAP planning with offline fallbacks
- **Persistence**: Single JSON file (`server/world_state.json`) with migration support
- **World Model**: `World` holds `rooms`, `players`, `users`, `npc_sheets`, relationships, object templates

## Critical Development Patterns

### Service Contract (MANDATORY)
All services return 4-tuple: `(handled: bool, error: str|None, emits: List[dict], broadcasts: List[Tuple[str, dict]])`

```python
# Example service signature from account_service.py
def create_account_and_login(world, sid, name, password, description, sessions, admins, state_path):
    return True, None, [{'type': 'system', 'content': 'Account created!'}], []
```

### Router Pattern
Commands flow: Router → Service → Emit. Routers in `server.py` call services, handle emissions.
New routers should accept `CommandContext` to access shared state (`world`, `sessions`, `admins`, etc.).

```python
# Adding new command family
def try_handle_my_feature(ctx: CommandContext, sid: str, cmd: str, args: list[str], raw: str, emit: Callable) -> bool:
    if cmd == 'mycommand':
        ok, err, emits, broadcasts = my_service.handle_command(ctx.world, args)
        # Handle emissions...
        return True  # Command handled
    return False  # Not our command
```

### Input Parsing (CRUCIAL)
Always use `id_parse_utils` helpers for user input:

```python
from id_parse_utils import strip_quotes, parse_pipe_parts, fuzzy_resolve

# Fuzzy resolution: exact → ci-exact → unique prefix → unique substring
ok, err, resolved = fuzzy_resolve("ap", ["apple", "application", "approve"])
# Returns deterministic, stable ordering for ambiguous matches
```

### Safe Execution
Replace bare `except Exception: pass` with `safe_call()` from `safe_utils.py`:

```python
from safe_utils import safe_call
result = safe_call(risky_function, default_value)  # Logs first occurrence
```

## Developer Workflows

- **Run Server**: `python server/server.py` (prints AI status on startup)
- **Run Tests**: `pytest -q server` (runs fast unit tests)
- **Reset World**: `python server/server.py --purge --yes` (deletes `world_state.json`)
- **Linting**: `flake8` (max line length 99), `mypy` (strict)

## Client-Server Contract

- **Client → Server**: `message_to_server` event with `{ "content": string }`
- **Server → Client**: `message` event with `{ "type": "system"|"player"|"npc"|"error", "content": string, "name"?: string }`
- **Formatting**: Client expects BBCode-friendly text. Types determine color.

## Project Conventions

- **File Size**: Keep `server/server.py` under 1,500 lines (refactor to services/routers).
- **Comments**: ~30% comment density. Explain "why" with an enthusiastic, teaching voice.
- **AI Integration**: Dual models (Chat + GOAP). Always provide offline fallbacks.
- **World Mutation**: After mutating `world`, call `world.save_to_file(STATE_PATH)` (best-effort).

## Key Files
- `server/server.py`: Main entry point, socket handlers.
- `server/world.py`: Data model (Room, Player, User, Object).
- `server/*_service.py`: Pure logic modules.
- `server/command_context.py`: Shared state container.
- `src/chat_ui.gd`: Main client logic.
