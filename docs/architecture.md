# Architecture and Code Tour

TinyMUD is a thought experiment in revisiting the concept of a minimalistic, extensible, and modular [MUD (Multi-User Dungeon)](https://en.wikipedia.org/wiki/Multi-user_dungeon) server and client, utilizing cutting edge software. It is designed to be lightweight and easy to extend, allowing developers to create their own game worlds and mechanics.

## Features

- Crafting spots: Any Object can advertise a crafting action by adding an object tag of the form `craft spot:<template_key>`. When players interact with the object, a "Craft <Template Display Name>" action appears. Choosing it spawns a fresh instance of the referenced template into the room. If the template key is missing, an error is shown. This aligns with the service pattern—interactions are handled in `interaction_service.py`.

## Object tags and behaviors

Object tags are simple strings that drive interactions and inventory rules. Tags are case-sensitive unless otherwise noted. Here are the canonical tags supported right now and what they do:

- Size and carrying
  - `small`: The item is small. Players can Pick Up the item. By default it stows into a small inventory slot (indices 2–5); if those are full, it falls back to a free hand (1 then 0). Containers also have small slots for storing small items.
  - `large`: The item is large. Players can Pick Up the item. By default it stows into a large inventory slot (indices 6–7); if those are full, it falls back to a free hand (1 then 0). Containers also have large slots for large items.

- Mobility and world navigation
  - `Travel Point`: Adds the “Move Through” interaction. When selected, the movement service attempts to traverse a door or stair linked to this object. These are typically paired with `Immovable` and created automatically for doors/stairs so they persist across saves.
  - `Immovable`: Marks an object that cannot be picked up. Often used with `Travel Point` and `Container` props embedded in rooms.

- Containers
  - `Container`: Enables “Open” and “Search” interactions. Containers have two small and two large internal slots. Behavior:
    - Search: First search has a chance to spawn loot from templates that hint they belong here (via a template’s `loot_location_hint.display_name` matching the container’s display name). Subsequent searches are blocked (“already searched”).
    - Open: Requires that the container has been searched at least once; then shows contents, grouped as Small and Large.

- Affordances and use actions
  - `weapon`: Adds the “Wield” interaction. Wielding moves the object into a hand (right hand prefers index 1, then left hand index 0) and clears the runtime `stowed` marker if present.
  - `Edible: N`: Adds “Eat (+N)” and allows consuming the item, then spawns any `deconstruct_recipe` outputs into the room. N must be an integer; the `Edible` key is matched case-insensitively when parsing the number. If an item carries an `Edible` key without a number, the system will show an error when trying to eat it—use the numeric form.
  - `Drinkable: N`: Adds “Drink (+N)” and allows consuming the item, analogously to `Edible: N`. Again, the numeric suffix is required for use.
  - `cutting damage`: Adds a “Cut” interaction today with no special behavior beyond an acknowledgement; it’s a placeholder for future combat or tool effects.

- Dynamic crafting spots
  - `craft spot:<template_key>`: Dynamically adds a Craft action for the given template. If the template exists in `world.object_templates`, selecting the action spawns a fresh instance of that template into the current room. If the template defines a `crafting_recipe` (list of component Objects by display name), the player must have those components in inventory; components are consumed by display-name counts (case-insensitive). Missing templates or components yield helpful error messages.

- Runtime marker (not for authoring)
  - `stowed`: Applied automatically when items are placed into stow slots (small/large). It’s removed when an item is moved to a hand. Authors generally shouldn’t set this tag manually.

Inventory layout reference (indexes):

- 0: Left hand
- 1: Right hand
- 2–5: Small stow slots
- 6–7: Large stow slots

Authoring tips:

- Use only `small` or `large` for size; these are the canonical size tags.
- For world geometry (doors/stairs), prefer the room/door helpers; they ensure reciprocal links and add `Immovable` + `Travel Point` objects with stable UUIDs.
- For food/drink, prefer the numeric forms `Edible: N` and `Drinkable: N` so the actions are both listed and usable.

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

## Configuration and Constants

TinyMUD centralizes its configuration in `server/constants.py` to reduce magic strings and make the codebase more maintainable. This file contains:

**Socket.IO Protocol Constants:**
- `MESSAGE_IN` = 'message_to_server' (client → server event)  
- `MESSAGE_OUT` = 'message' (server → client event)

**Message Type Constants:**
- `MSG_TYPE_SYSTEM`, `MSG_TYPE_PLAYER`, `MSG_TYPE_NPC`, `MSG_TYPE_ERROR`
- Used by the client to apply different colors and formatting

**Command Parsing Constants:**
- `COMMAND_PREFIX` = '/' (for slash commands like /help, /auth)
- `ROOM_BUILD_PREFIX` = '+' (for room creation like +room, +door)

**Environment Variables and Defaults:**
- `ENV_GEMINI_API_KEY`, `ENV_GOOGLE_API_KEY` for AI configuration
- `DEFAULT_MAX_MESSAGE_LENGTH`, `DEFAULT_SAFETY_LEVEL`, etc.

**Helper Functions:**
- `get_message_payload()` creates standardized Socket.IO message structures
- `is_slash_command()`, `validate_world_name()`, etc. for input validation

This approach makes it easy to adjust protocol details, message limits, and other configuration without hunting through multiple files. New contributors can quickly understand the system's communication patterns by examining the constants file.

## Glossary (terminology)

- Room name (user input): Human-friendly string admins/players type in commands. We fuzzy-resolve these (exact, case-insensitive exact, unique prefix, unique substring) to a concrete room id.
- Room id (internal): Stable identifier string used as the key in `world.rooms` and persisted in `world_state.json`. Doors and stairs store target room ids.
- Door name: Human-facing label for a connector inside a room (e.g., "oak door", "north door"). Each door name maps to a target room id and also has a stable `door_id` UUID for persistence.
- Stairs: Optional up/down connectors; each direction stores a target room id and has its own stable UUID.
- Player display name: Human-friendly name shown in chat. Players are addressed by display name in commands, resolved fuzzily.
- Player SID: Ephemeral socket connection id for the current session.
- Player/User id: Stable UUID stored on the server; not typed by users.
- NPC name: Human-facing name used in chat and commands; internally each NPC also has a stable UUID (`npc_ids`).
