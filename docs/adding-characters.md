# Add or Customize AI/NPCs

There are two kinds of “characters” here:

1) Visible names in a room (character list): these are strings in `Room.npcs` in `server/world.py`.
2) The talking AI persona: configured in `server/server.py`.

## Visible character names

In `server/world.py`, rooms can include a set of names:

```python
self.rooms["start"] = Room(
    id="start",
    description="…",
    npcs={"The Wizard", "Old Guard"}
)
```

These names appear under “NPCs here:” when players `look`.

## The AI persona (who talks back)

In `server/server.py`, the server builds a `prompt` and emits a chat message with a `name` field.

Change the `name` if you want a different speaker label:

```python
emit('message', {
    'type': 'npc',
    'name': 'The Wizard',  # change me
    'content': ai_response.text
})
```

Tweak the `prompt` to change the voice/tone:

```python
prompt = (
    "You are a wise, slightly mysterious wizard in a fantasy MUD. "
    f"A player says to you: '{player_message}'. How do you respond? "
    "Ensure your response is concise and formatted with BBCode where helpful."
)
```

Example: switch to a grumpy guard persona:

```python
prompt = (
    "You are a gruff town guard who distrusts strangers. Keep answers short. "
    f"Player: '{player_message}'. Reply in a brusque tone."
)
```

## No API key? No problem.

If no Gemini key is set, the server sends a friendly built‑in reply. You can adjust that fallback string in `server/server.py` too.
