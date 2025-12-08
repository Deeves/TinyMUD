# Gemini-assisted GOAP for NPCs

This document explains how TinyMUD’s NPC behavior works using a lightweight GOAP-style planner with optional Gemini assistance. If Gemini isn’t configured, an offline planner ensures NPCs still act sensibly.

At a glance:
- NPCs have needs (hunger, thirst, socialization, sleep) and limited action points per tick.
- On each world heartbeat, NPCs degrade needs, regenerate action points, plan if needed, and execute one action per AP.
- Planning prefers an AI JSON plan (Gemini 2.5 Pro) when players are present; otherwise uses a deterministic offline planner.
- NPC dialogue still uses a lightweight chat model (Gemini Flash) and is independent of the planner.
- The setup wizard now asks whether to enable the advanced GOAP AI; choosing "no" keeps NPCs on the offline planner only.


## When is the planner used?

The server runs a heartbeat loop when enabled via environment:
- MUD_TICK_ENABLE=1 — enable the world heartbeat
- MUD_TICK_SECONDS — seconds between ticks (default 60)

On each tick, for each NPC in each room:
1) Needs drip down (hunger, thirst, socialization, sleep)
2) If sleeping, sleep refills; otherwise sleep slowly drains
3) Action Points (AP) regenerate to a cap (default AP_MAX=3)
4) If any need is below NEED_THRESHOLD and there’s no current plan, the NPC “thinks”
5) Execute up to AP actions from the plan queue, spending one AP per action

Room presence gate: if a room has no connected players, we skip Gemini entirely and use the offline planner even if an API key is present. This keeps background activity cheap and predictable.


## Needs model and NPC sheet fields

CharacterSheet (for NPCs) carries these planning-relevant fields:
- hunger: float (0–100; higher is better)
- thirst: float (0–100)
- socialization: float (0–100)
- sleep: float (0–100)
- action_points: int — regenerated each tick up to AP_MAX
- plan_queue: list[dict] — queue of actions produced by plan
- sleeping_ticks_remaining: int — remaining ticks to stay asleep
- sleeping_bed_uuid: str|None — bed object the NPC is sleeping on

Environment tunables (defaults in server/server.py):
- MUD_TICK_SECONDS (default 60)
- MUD_AP_MAX (default 3)
- MUD_NEED_DROP (default 1.0 per tick for hunger/thirst)
- MUD_SOCIAL_DROP (default 0.5 per tick)
- MUD_SOCIAL_REFILL (default +10 on conversation)
- MUD_SOCIAL_SIM_TICK (default +5 per tick when alone)
- MUD_SLEEP_DROP (default 0.75 per tick)
- MUD_SLEEP_REFILL (default +10 per tick while sleeping)
- MUD_SLEEP_TICKS (default 3 ticks for a sleep action)


## Nutrition and object tagging

NPCs determine food and drink via object tags or legacy fields:
- Preferred: tags "Edible: N" and "Drinkable: N" on room objects and inventory items.
- Legacy fallback: satiation_value/hydration_value fields on objects when no nutrition tags exist.

The object template wizard automatically adds Edible/Drinkable tags when you provide numeric values. Doors/stairs and other immovable travel points are not carriable (they include tags {Immovable, Travel Point}).


## The tool/action contract (plan outputs)

Plans are arrays of JSON actions with this shape:
- { "tool": "get_object", "args": { "object_name": string } }
- { "tool": "consume_object", "args": { "object_uuid": string } }
- { "tool": "emote", "args": { "message"?: string } }
- { "tool": "claim", "args": { "object_uuid": string } }
- { "tool": "unclaim", "args": { "object_uuid": string } }
- { "tool": "sleep", "args": { "bed_uuid"?: string } }
- { "tool": "do_nothing", "args": {} }
- { "tool": "move_through", "args": { "name": string } }

Execution semantics:
- Each executed action spends 1 AP, even on failure (prevents thrashing).
- get_object picks an object in the current room by name via exact/prefix/substr.
- consume_object consumes an item from inventory and applies satiation/hydration.
- emote performs a light room emote and restores a bit of socialization without using AI.
- claim/unclaim toggles object ownership (used for beds).
- sleep requires a bed you own in the room; if absent, claim an unowned bed first.
- do_nothing produces a small “thinks” beat.
- move_through moves via a named door or any Travel Point object (e.g., "oak door", "stairs up"). It accepts "name" with optional articles like "the".


## Offline planner behavior

When the offline planner runs (no players in room or no plan model):
- If hunger < NEED_THRESHOLD: prefer consuming edible in inventory; else get edible from room then consume.
- If thirst < NEED_THRESHOLD: same logic for drinks.
- If socialization < NEED_THRESHOLD: emote a small message to self.
- If sleep < NEED_THRESHOLD: sleep in an owned bed if present; else claim an unowned bed then sleep.
- If nothing to do: do_nothing.

The offline planner builds short plans (1–4 actions) and is deterministic and cheap.


## Gemini-assisted planning

When a player is in the room and a plan model is configured, the server prompts Gemini 2.5 Pro to return ONLY JSON (no prose). The prompt bundles:
- A compact system description with the tool list and rules
- NPC need levels
- Room objects with names, UUIDs, tags, and normalized nutrition values
- Inventory items similarly normalized

The model must return a JSON array of up to 4 actions using the tool contract above. The server parses, sanitizes, and pushes the plan into the NPC’s plan_queue. On any parse/error, it falls back to the offline planner.

Models in use (when API configured):
- plan_model: gemini-2.5-pro — for planning JSON
- model: gemini-flash-lite-latest — for conversational NPC replies (say/tell/whisper)


## Safety levels and moderation

Admins can set a per-world safety level with /safety:
- /safety G | PG-13 | R | OFF

server/ai_utils.py maps the world’s safety_level to Gemini safety_settings. If the SDK is missing or the enums aren’t available, safety is omitted. The setting applies to both dialogue replies and planner prompts.


## Socialization: chat and emotes

- Every NPC reply (say/tell/whisper) increases the NPC’s socialization by MUD_SOCIAL_REFILL.
- When no players are present in a room, NPCs passively regain socialization per tick (MUD_SOCIAL_SIM_TICK).
- The emote tool refills socialization a bit without any AI calls.


## Sleep: ownership and recovery

- Sleep restores the sleep meter while consuming sleep ticks.
- NPCs must own the bed they sleep in; claim an unowned bed first.
- Beds are recognized by an object tag equal to "bed" (case-insensitive match of the tag value).


## Debugging and observability

- The server logs AI responses and heartbeat start (“World heartbeat started.”).
- Admins inspecting an NPC with look get a needs overlay: Hunger, Thirst, Social, Sleep, AP, and current plan length.
- If the planner returns invalid JSON, the server prints a parse error and falls back to the offline plan.


## How to enable locally (PowerShell)

Minimal setup:

```powershell
# From repo root
cd server
python -m pip install -r ..\requirements.txt

# Optional but recommended for AI
$env:GEMINI_API_KEY = "YOUR_API_KEY"

# Enable heartbeat and shorten tick for testing
$env:MUD_TICK_ENABLE = "1"
$env:MUD_TICK_SECONDS = "10"

# Start server
python server.py
```

If you see a warning about eventlet not installed, install requirements again; eventlet provides a production-capable WebSocket server that avoids Werkzeug quirks.


## Extending the planner (advanced)

Adding a new tool requires:
1) Implementing its execution in server/server.py (_npc_execute_action)
2) Teaching the offline planner when to use it
3) Updating the planner system prompt to document the new tool and its args shape
4) Keeping the plan queue small (1–4 steps) and actions idempotent or safely fail-fast

Always maintain message contracts and world invariants (see .github/copilot-instructions.md and docs/architecture.md). After mutating the world, save with world.save_to_file(STATE_PATH) best-effort.
