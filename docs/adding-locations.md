# Add a New Location (Room)

You can add new places for players to visit by creating Rooms in `server/world.py`.

A Room has:
- `id`: a short unique string (e.g., `"tavern"`)
- `description`: a short paragraph players see when they `look`
- `npcs`: optional set of visible NPC names (strings)

## 1) Open `server/world.py`

Find `World.ensure_default_room` for a good example.

## 2) Add a new Room

Add your room to `self.rooms` (usually in a new helper method or right after the default room is created). For example:

```python
self.rooms["tavern"] = Room(
    id="tavern",
    description=(
        "You enter a warm tavern. Lanterns sway gently and the smell of bread fills the air."
    ),
    npcs={"Bartender", "Quiet Bard"},
)
```

That’s it—your room exists in the world!

## 3) Move a player into the room (optional)

Right now, everyone spawns in the `start` room. To move someone, add a command in `server/server.py`:

```python
# inside handle_message, after we compute text_lower
if text_lower == "go tavern":
    world.move_player(sid, "tavern")
    emit('message', { 'type': 'system', 'content': world.describe_room_for(sid) })
    return
```

Now typing `go tavern` will move the player and describe the new room.

## Tips

- Keep descriptions short (1–3 lines) so they fit nicely in the chat window.
- Use present tense and sensory hints (sight, sound, smell) to set the mood.
- NPC names in `npcs` are just strings; adding them makes them “listed” in the room.
