# Service Contract Quick Reference

**Standard Pattern (Use This!):**

```python
from typing import List, Tuple, Optional

def my_service_function(
    world,
    sid: str,
    # ... other params
) -> Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]:
    """Short description of what this service does.
    
    Returns: (handled, error, emits, broadcasts)
        - handled: True if we processed the request
        - error: None on success, error message on failure  
        - emits: Messages to send to acting player
        - broadcasts: (room_id, payload) for room announcements
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    
    # Early error return
    if not_valid:
        return True, "Validation error message.", emits, broadcasts
    
    # Do work
    emits.append({'type': 'system', 'content': 'Operation successful!'})
    
    # Optional: Announce to room
    player = world.players.get(sid)
    if player:
        room_id = player.room_id
        broadcasts.append((room_id, {
            'type': 'system',
            'content': f"[i]{player.sheet.display_name} did something.[/i]"
        }))
    
    # Success return
    return True, None, emits, broadcasts
```

---

## Router Pattern (Use This!)

```python
def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    if cmd != 'mycommand':
        return False  # Not our command
    
    MESSAGE_OUT = ctx.message_out
    
    # Call service
    handled, err, emits, broadcasts = my_service_function(
        ctx.world,
        sid,
        # ... other args
    )
    
    # Handle result
    if not handled:
        return False
    
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
        return True
    
    # Emit to acting player
    for payload in emits:
        emit(MESSAGE_OUT, payload)
    
    # Broadcast to rooms
    for room_id, payload in broadcasts:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
    
    return True
```

---

## Common Patterns

### Success with no broadcast:
```python
return True, None, [{'type': 'system', 'content': 'Done!'}], []
```

### Error (still handled):
```python
return True, "Something went wrong.", [], []
```

### Not handled (pass to next router):
```python
return False, None, [], []
```

### Success with room announcement:
```python
emits = [{'type': 'system', 'content': 'You created a room.'}]
broadcasts = [(room_id, {'type': 'system', 'content': 'A room was created.'})]
return True, None, emits, broadcasts
```

---

## Using Helper Functions

```python
from service_contract import success, error, not_handled

# Success:
return success([{'type': 'system', 'content': 'Done!'}])

# Success with broadcast:
return success(
    [{'type': 'system', 'content': 'You did it.'}],
    [(room_id, {'type': 'system', 'content': 'They did it.'})]
)

# Error:
return error("Invalid input.")

# Not handled:
return not_handled()
```

---

## Message Payload Types

```python
# System message (gray/white in UI)
{'type': 'system', 'content': 'Text here'}

# Error message (red in UI)  
{'type': 'error', 'content': 'Error text'}

# Player message (blue in UI)
{'type': 'player', 'content': 'What they said', 'name': 'PlayerName'}

# NPC message (green in UI)
{'type': 'npc', 'content': 'What NPC said', 'name': 'NPCName'}
```

---

## BBCode Formatting

```python
# Bold
'[b]Bold text[/b]'

# Italic (use for atmospheric/action descriptions)
'[i]The door creaks open...[/i]'

# Color
'[color=red]Red text[/color]'

# Common pattern for room announcements:
f"[i]{player_name} performs an action.[/i]"
```

---

## When to Broadcast

✅ **DO broadcast:**
- Player enters/leaves room
- Player creates visible object
- Player performs action others would notice
- NPC moves or speaks

❌ **DON'T broadcast:**
- Private whispers
- Inventory checks  
- Looking at objects
- System notifications

---

## Testing Pattern

```python
def test_my_service():
    # Setup
    world = World()
    sid = 'test_sid'
    
    # Call service
    handled, err, emits, broadcasts = my_service_function(world, sid, args)
    
    # Assert
    assert handled
    assert err is None  # or assert err == "expected error"
    assert len(emits) == 1
    assert emits[0]['type'] == 'system'
    assert emits[0]['content'] == 'Expected text'
    assert len(broadcasts) == 0  # or check broadcast content
```

---

## Common Mistakes

❌ **Wrong:** Returning 3-tuple
```python
return True, None, emits  # Missing broadcasts!
```

✅ **Right:** Always 4-tuple
```python
return True, None, emits, broadcasts
```

---

❌ **Wrong:** Forgetting to check handled
```python
handled, err, emits, broadcasts = service(...)
# Emit regardless - BAD!
for p in emits:
    emit(MESSAGE_OUT, p)
```

✅ **Right:** Check handled first
```python
handled, err, emits, broadcasts = service(...)
if not handled:
    return False
# Now safe to emit
```

---

❌ **Wrong:** Raising exceptions from service
```python
def my_service(...):
    if error:
        raise ValueError("Bad input")  # DON'T!
```

✅ **Right:** Return error string
```python
def my_service(...):
    if error:
        return True, "Bad input", [], []
```

---

## Where to Get Help

- **Full audit:** `docs/service-contract-audit.md`
- **Implementation plan:** `docs/service-contract-implementation-plan.md`
- **Examples:** Look at `account_service.py` or `movement_service.py`
- **Helpers:** Import from `service_contract.py`

---

**Remember:** When in doubt, copy the pattern from `account_service.py` - it's the canonical example.
