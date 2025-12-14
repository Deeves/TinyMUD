# Add a New Location (Room)

Create new places for players to explore using in-game commands or code.

## Quick Start: In-Game Commands

Logged in as an admin, use these commands:

```
/room create <id> | <description>
```

Example:
```
/room create tavern | A warm tavern filled with the clang of mugs and the smell of roasted meat. Lanterns sway gently from the rafters.
```

### Connecting Rooms with Doors

```
/room adddoor <door name> | <target room>
```

Example (while standing in the tavern):
```
/room adddoor oak door | town_square
```

This creates a bidirectional door — the target room automatically gets a door back.

### Stairs

```
/room setstairs <up_room> | <down_room>
```

## Room Tags

Rooms can have special tags that modify their behavior:

| Tag | Effect |
|-----|--------|
| `[external]` | Appends time-of-day description (dawn, noon, dusk, etc.) |
| `[internal]` | Standard indoor room |
| `[ownable]` | Can be claimed by factions or players |

## Tips for Good Descriptions

- **Keep it short:** 1-3 sentences work best in the chat window
- **Use present tense:** "You enter..." or "The room is..."
- **Include senses:** Sight, sound, smell make rooms memorable
- **Mention exits:** "A wooden door leads north" helps navigation

## Manual Setup (Advanced)

For programmatic room creation in `server/world.py`:

```python
from world import Room

room = Room(
    id="smithy",
    description="A hot workshop. The forge glows orange, and the rhythmic clang of hammers fills the air.",
    npcs={"Gareth the Smith"},
    doors={"iron door": "marketplace"},
    tags=["internal"]
)
world.rooms["smithy"] = room
```

## Door Locks

Restrict door access by player ID or relationships:

```
/room lockdoor <door> | player:<user_id>
/room lockdoor <door> | relationship:friend with <user_id>
```

## Linking Existing Doors

If you need to manually pair doors between rooms:

```
/room linkdoor <room_a> | <door_a> | <room_b> | <door_b>
```
