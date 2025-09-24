# Architecture and Code Tour

TinyMUD is a thought experiment in revisiting the concept of a minimalistic, extensible, and modular [MUD (Multi-User Dungeon)](https://en.wikipedia.org/wiki/Multi-user_dungeon) server and client, utilizing cutting edge software. It is designed to be lightweight and easy to extend, allowing developers to create their own game worlds and mechanics.

## Features

- Crafting spots: Any Object can advertise a crafting action by adding an object tag of the form `craft spot:<template_key>`. When players interact with the object, a "Craft <Template Display Name>" action appears. Choosing it spawns a fresh instance of the referenced template into the room. If the template key is missing, an error is shown. This aligns with the service pattern—interactions are handled in `interaction_service.py`.

## Big picture

- Godot (client) shows a chat window and sends your text to the server.
- Python (server) receives text, handles login/commands, and may ask an AI (Gemini) to speak as an NPC.
- The server sends messages back for the client to display.

```
You type → Godot sends { content: "..." } → Python decides: auth? command? AI? →
→ Python emits { type, content, name? } → Godot formats and shows it.
```

## Repos and files

- Godot client (GDScript)
  - `ChatUI.tscn` — scene with a RichTextLabel and LineEdit
  - `src/chat_ui.gd` — UI logic and message formatting
  - `src/socket_io_client.gd` — tiny Socket.IO v4 client over WebSocketPeer
  - `OptionsMenu.tscn`, `src/options_menu.gd` — adjust text size and background color
- Python server
  - `server/server.py` — Flask‑SocketIO events, command handling, optional Gemini call
  - `server/world.py` — very small world model: Rooms, Players, Users, NPC sheets

## Data shapes

- Client → Server: event `message_to_server` with a JSON object: `{ "content": string }`
- Server → Client: event `message` with a JSON object:
  - `{ "type": "system" | "player" | "npc" | "error", "content": string, "name"?: string }

## Login and accounts

Two ways to authenticate:

1) Guided flow (type `create` or `login` after connecting). The server prompts for name, password, and (for create) description.
2) One‑line commands:
   - `/auth create <name> | <password> | <description>`
   - `/auth login <name> | <password>`

The first account ever created becomes an admin automatically. Admins can kick users, manage rooms, and manage NPCs.

## Commands (server side)

- Player convenience:
  - `/rename <new name>` — change display name
  - `/describe <text>` — update character description
  - `/sheet` — show your character sheet
  - `look` (or `l`) — describe your current room

- Admin:
  - `/kick <playerName>` — disconnect a player
  - `/purge` — reset and wipe persisted world_state.json (asks for Y/N)
  - `/room create <id> | <description>`
  - `/room setdesc <id> | <description>`
  - `/npc add <room name> <npc name...>`
  - `/npc remove <room name> <npc name...>`
  - `/npc setdesc <npc name> | <description>`
  - `/auth promote <name>` / `/auth demote <name>` / `/auth list_admins`

## World model (server/world.py)

- `Room`: `id` (string key), `uuid` (stable UUID), `description`, `players` (set of live connection sids), `npcs` (set of names)
  - Doors: `doors` (name -> room id) plus `door_ids` (name -> UUID)
  - Stairs: `stairs_up_to`/`stairs_down_to` (room ids) plus `stairs_up_id`/`stairs_down_id` (UUIDs)
- `Player`: `sid` (socket id), `id` (stable UUID), `room_id`, `sheet`
- `CharacterSheet`: `display_name`, `description`, `inventory`
- `User`: persisted accounts with `user_id` (UUID), `display_name`, `password`, `is_admin`, and a `sheet`
- `World`: `rooms`, `players`, `users`, `npc_sheets`, and `npc_ids` (name -> UUID)
- Persistence: `World.save_to_file` and `.load_from_file` write/read `world_state.json`. When loading older saves, any missing UUIDs are backfilled automatically.

## Adding features safely

1) Keep payload shapes stable (`{ type, content, name? }`).
2) Prefer small, incremental changes.
3) Add short comments where logic might confuse a beginner.
4) Test locally: run `python server.py`, then run Godot and try your feature.

## Where the AI fits

If a Gemini API key is configured, the server builds a prompt using both the player’s and NPC’s character sheets and asks Gemini to reply. Without a key, a friendly fallback reply is sent so the game remains playable offline.

## Glossary (terminology)

- Room name (user input): Human-friendly string admins/players type in commands. We fuzzy-resolve these (exact, case-insensitive exact, unique prefix, unique substring) to a concrete room id.
- Room id (internal): Stable identifier string used as the key in `world.rooms` and persisted in `world_state.json`. Doors and stairs store target room ids.
- Door name: Human-facing label for a connector inside a room (e.g., "oak door", "north door"). Each door name maps to a target room id and also has a stable `door_id` UUID for persistence.
- Stairs: Optional up/down connectors; each direction stores a target room id and has its own stable UUID.
- Player display name: Human-friendly name shown in chat. Players are addressed by display name in commands, resolved fuzzily.
- Player SID: Ephemeral socket connection id for the current session.
- Player/User id: Stable UUID stored on the server; not typed by users.
- NPC name: Human-facing name used in chat and commands; internally each NPC also has a stable UUID (`npc_ids`).
