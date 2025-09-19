# Contributing Guide (Beginner‑friendly)

Thanks for your interest in improving this tiny AI MUD! This project is intentionally small and welcoming for first contributions.

## What can I add?

- New locations (Rooms) with atmospheric descriptions
- New visible NPC names in rooms
- Adjust the AI NPC’s personality and name
- Improve messages or UI copy

## Project layout

- Godot client (GDScript): `ChatUI.tscn`, `src/chat_ui.gd`, `src/socket_io_client.gd`, `OptionsMenu.tscn`, `src/options_menu.gd`
- Python server: `server/server.py` (websocket + AI), `server/world.py` (in‑memory Rooms/Players)

## Workflow

1) Fork this repo and create a new branch from `main`.
2) Make your change in small steps. Test locally:
   - Run the Python server: `cd server && python server.py`
   - Run the Godot scene: open `ChatUI.tscn` in Godot and press Play
3) Keep messages consistent with the client’s expectations:
   - Server emits `message` events shaped like `{ type, content, name? }`
4) Commit with a clear message:
   - Example: "Add ‘tavern’ room with bartender NPC"
5) Open a Pull Request and describe what you changed. Screenshots welcome!

## Code style (lightweight)

- Python: keep functions short and add docstrings/comments for beginners
- GDScript: add a one‑line header comment at the top saying what the script does
- Avoid clever one‑liners—prefer clarity

## Where to add content

- New locations: edit `server/world.py` (see docs/adding-locations.md)
- New NPC names: add to a room’s `npcs` set in `world.py`
- AI persona: edit the `prompt` (and `name`) in `server/server.py`

Thanks again. Have fun and keep PRs small—small PRs get merged faster.
