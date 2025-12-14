---
description: Add a new slash command to TinyMUD
---

# Add Command Workflow

## Overview

Slash commands (e.g., `/help`, `/look`, `/attack`) are handled in `server/server.py` in the `handle_command()` function.

## Steps

### 1. Find handle_command function

Open `server/server.py` and search for `def handle_command`.

### 2. Add command handling

Add a new `elif` block for your command. Example:

```python
elif cmd == 'mycommand':
    # Validate arguments
    if not args:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /mycommand <arg>'})
        return
    
    # Get player
    player = world.players.get(sid)
    if not player:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Must be authenticated.'})
        return
    
    # Execute command logic
    result = do_something(player, args[0])
    
    emit(MESSAGE_OUT, {'type': 'system', 'content': f'Result: {result}'})
    return
```

### 3. Update help text

Search for the `/help` command handler and add your command to the help output.

### 4. Add tests

Create or update a test file in `server/`:

```python
def test_mycommand_success():
    # Setup
    world = create_test_world()
    # ... test your command
    assert expected_result
```

// turbo

### 5. Run tests

```bash
cd server && python -m pytest -v -k "mycommand"
```

## Command Categories

| Category | Examples | Notes |
|----------|----------|-------|
| Navigation | `/go`, `/look`, `/enter` | Use movement_router |
| Combat | `/attack`, `/flee` | Use combat_service |
| Social | `/say`, `/tell`, `/whisper` | Use dialogue_router |
| Admin | `/purge`, `/kick`, `/promote` | Check admin status first |
| Items | `/get`, `/drop`, `/use` | Check inventory limits |
