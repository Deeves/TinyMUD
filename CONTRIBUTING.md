# Contributing Guide (Beginner‑friendly)

Thanks for your interest in improving TinyMUD! This project is intentionally small and welcoming for first contributions.

## What Can I Contribute?

**Easy (great first issues):**
- Fix typos or improve messages/UI copy
- Add comments to confusing code

**Medium:**
- Adjust the AI NPC's personality and prompts
- Add new object templates (food, weapons, furniture)
- Improve test coverage

**Advanced:**
- New game mechanics (see `docs/architecture.md`)
- NPC behavior improvements (see `docs/goap-ai.md`)
- Combat system tweaks (see `docs/combat-system.md`)

## Project Layout

```
TinyMUD/
├── src/                    # Godot client (GDScript)
│   ├── chat_ui.gd          # Main chat interface
│   └── socket_io_client.gd # WebSocket client
├── server/                 # Python server
│   ├── server.py           # Main entry, Socket.IO events
│   ├── world.py            # World model (Rooms, Players, NPCs)
│   ├── *_service.py        # Feature services (combat, movement, etc.)
│   └── *_router.py         # Command routing
└── docs/                   # Documentation you're reading now!
```

## Development Workflow

1. **Fork** this repo and create a new branch from `main`
2. **Set up locally:**
   ```powershell
   cd server
   python -m pip install -r ../requirements.txt
   python server.py
   ```
3. **Run Godot:** Open `project.godot` and press Play on `ChatUI.tscn`
4. **Make changes** in small steps — test after each change
5. **Commit** with clear messages: `"Add tavern room with bartender NPC"`
6. **Open a Pull Request** describing what you changed. Screenshots welcome!

## Code Style (Keep It Simple)

- **Python:** Short functions with docstrings. Use type hints. See `CODING_STANDARDS.md`.
- **GDScript:** Header comment explaining what the script does.
- **Both:** Prefer clarity over cleverness. Write for beginners to read.

## Where to Add Content

| What | Where | Guide |
|------|-------|-------|
| New rooms | `server/world.py` or `/room create` in-game | `docs/adding-locations.md` |
| New NPCs | `/npc add` in-game or `world.py` | `docs/adding-characters.md` |
| Object templates | `/object createtemplateobject` in-game | `docs/architecture.md` |
| AI personality | `server/server.py` (prompt strings) | `docs/adding-characters.md` |

## Testing Your Changes

```powershell
cd server
python -m pytest -v        # Run all tests
python service_tests.py    # Quick service tests
```

## Getting Help

- Check `docs/` for architecture and feature docs
- Look at existing code for patterns to follow
- Open an issue if you're stuck — we're friendly!

Thanks again. Have fun and **keep PRs small** — small PRs get merged faster.
