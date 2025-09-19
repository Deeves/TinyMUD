# AI Multi‑User Dungeon (Godot + Python)

A tiny, beginner‑friendly MUD prototype: a Godot 4 client chats with a Python server that can reply as an AI NPC (Gemini) or a friendly offline fallback.

Great first contributions: add new locations (rooms), add NPC names, or tweak the AI persona.

## What’s inside

- Godot 4 client (GDScript)
  - `ChatUI.tscn` + `src/chat_ui.gd` — simple chat window and input box
  - `src/socket_io_client.gd` — tiny Socket.IO v4 client built on WebSocketPeer
  - `OptionsMenu.tscn` + `src/options_menu.gd` — text size and background color
- Python server (Flask‑SocketIO)
  - `server/server.py` — websocket events, AI call (optional), simple commands
  - `server/account_service.py` — account creation/login helpers used by server.py
  - `server/movement_service.py` — character movement helpers (doors/stairs)
  - `server/world.py` — very small world model: Rooms, Players, NPC lists

See also: docs/architecture.md for a gentle code tour and data flow diagrams.

## Prerequisites

- Godot 4.x (open `project.godot`)
- Python 3.10+ (3.11/3.12/3.13 also fine)
- Optional: a Gemini API key (recommended for AI replies)
  - Set either `GEMINI_API_KEY` or `GOOGLE_API_KEY`
  - Copy `.env.example` to `.env` and fill in values if preferred

## Quick start (Windows PowerShell)

1) Install Python deps:

```powershell
cd server
python -m pip install -r ..\requirements.txt
```

2) (Optional) Set your Gemini key for this terminal session:

```powershell
$env:GEMINI_API_KEY = "YOUR_KEY_HERE"
```

3) Run the server locally:

```powershell
python server.py
```

You should see “Gemini API configured successfully.” when the key is valid. Without a key, the server still runs with a friendly offline NPC reply.

4) In Godot, open the project (`project.godot`) and run the `ChatUI.tscn` scene.

- The client connects to `ws://127.0.0.1:5000/socket.io/?EIO=4&transport=websocket`
- On first connect, authenticate:
  - Create: `/auth create <name> | <password> | <description>`
  - Login: `/auth login <name> | <password>`
  - Tip: the first user you create becomes an admin.
- Then try `look` to describe your current room.

Tip: For production or when deploying publicly, set `SECRET_KEY` in the environment. The server will warn if using a dev default.

## How it works (big picture)

- The Godot client sends `message_to_server` with `{ content: "..." }`.
- The Python server receives it and either:
  - Handles auth (`/auth create` and `/auth login`), simple player commands (e.g., `look`) using the `World` model, or
  - Builds an AI prompt and asks Gemini for a reply (if configured).
- The server sends back `message` events. The client formats them into the chat log.

## Contributing (beginner‑friendly)

- Add a location (room): edit `server/world.py` and create a new `Room` entry with an `id`, `description`, and optional `npcs` set. See docs below.
- Add an NPC name: add the NPC’s name to a room’s `npcs` set. It will appear in the room description under “NPCs here: …”.
- Tweak the AI persona: open `server/server.py` and adjust the `prompt` string and the `name` sent back in the `emit('message', ...)` block.
  - Account and movement logic live in `server/account_service.py` and `server/movement_service.py` respectively.

Guides:
- docs/adding-locations.md — add a new room
- docs/adding-characters.md — add or customize AI/NPCs
- docs/deploy-gce.md — deploy the Python server to Google Cloud (e2-micro)

Please also read CONTRIBUTING.md for style and PR tips.

## Licensing and assets

- Code is licensed under the MIT License (see `LICENSE`).
- Verify third‑party asset licenses before publishing. See `ASSETS_LICENSES.md` and replace TODOs with actual sources and licenses, or remove assets if unsure.

## Security

- Never commit secrets. Set environment variables in your shell or `.env` (which is git‑ignored).
- Required/optional env vars: `GEMINI_API_KEY` or `GOOGLE_API_KEY` (optional), `SECRET_KEY` (recommended), `HOST`, `PORT`. See `.env.example`.

### Quick command reference

- Auth:
  - `/auth create <name> | <password> | <description>`
  - `/auth login <name> | <password>`
  - First created account becomes admin automatically
- Basics:
  - `look` or `l` — describe current room
  - `/rename <new name>` — change your display name
  - `/describe <text>` — update your description
  - `/sheet` — show your character sheet
- Admin:
  - `/kick <playerName>` — disconnect a player
  - `/room create <id> | <description>`
  - `/room setdesc <id> | <description>`
  - `/npc add <room_id> <npc name...>` / `/npc remove <room_id> <npc name...>` / `/npc setdesc <npc name> | <description>`
  - `/auth promote <name>` / `/auth demote <name>` / `/auth list_admins`

## Troubleshooting

- Client says “Disconnected.”
  - Ensure the Python server is running on 127.0.0.1:5000
  - Firewalls/VPNs can block localhost websockets — try turning them off temporarily.
- “Malformed message from server.” in chat
  - You may have changed server payload shapes. Keep `{ type, content, name? }`.
- No AI reply
  - Make sure `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is set in the same terminal before `python server.py`.
  - The server prints a helpful message if AI is disabled.
 - Can't use admin commands
   - Only users with `is_admin` true can run admin commands. The first created user becomes admin automatically. You can delete `server/world_state.json` to reset.
 - AssertionError: write() before start_response when a client disconnects
   - This is a Werkzeug limitation when handling WebSocket traffic. We fixed the server to prefer a real WebSocket server (eventlet). Make sure eventlet is installed:
     - In PowerShell:
       - `cd server`
       - `python -m pip install -r ..\requirements.txt`
     - On startup, if you still see the warning “eventlet not installed…”, eventlet did not install correctly.
   - After installing, restart the server; the error should be gone and disconnects will be clean.


Have fun tinkering and keep changes small — it’s easy to break less when you change one thing at a time.
