---
description: Add a new NPC GOAP action to TinyMUD
---

# Add NPC Action Workflow

## Overview

NPC actions are executed during the world tick. Actions are defined in `server/game_loop.py` and planned by the GOAP system in `server/goap_state_manager.py`.

## Steps

### 1. Define the action executor

Add a new function in `server/game_loop.py`:

```python
def _npc_exec_my_action(npc_name: str, room_id: str, target: str) -> bool:
    """Execute my custom action.
    
    Returns True if successful, False otherwise.
    """
    ctx = get_context()
    world = ctx.world
    
    # Get NPC sheet
    sheet = world.npc_sheets.get(npc_name)
    if not sheet:
        return False
    
    # Execute action logic
    # ...
    
    # Broadcast to room
    ctx.broadcast_to_room(room_id, {
        'type': 'system',
        'content': f'[i]{npc_name} performs my action on {target}.[/i]'
    })
    
    return True
```

### 2. Add to action dispatcher

Find the action execution switch in `server/server.py` (in `_world_tick`) and add:

```python
elif action_type == 'my_action':
    success = game_loop._npc_exec_my_action(npc_name, room_id, params.get('target'))
```

### 3. Define GOAP action

Add the action to `server/goap_state_manager.py`:

```python
# In _get_available_actions or similar
actions.append({
    'action': 'my_action',
    'target': target_name,
    'precondition': lambda s: s.get('has_item', False),
    'effect': lambda s: {**s, 'goal_achieved': True},
    'cost': 2,
})
```

### 4. Add tests

```python
def test_npc_exec_my_action():
    # Create test world with NPC
    world = create_test_world()
    add_test_npc(world, 'TestNPC', 'room_1')
    
    # Execute action
    result = game_loop._npc_exec_my_action('TestNPC', 'room_1', 'target')
    
    assert result == True
```

// turbo

### 5. Run tests

```bash
cd server && python -m pytest -v -k "npc"
```

## Common Action Patterns

| Pattern | Use Case | Example |
|---------|----------|---------|
| Get object | NPC picks up item | `_npc_exec_get_object` |
| Consume | NPC eats/drinks | `_npc_exec_consume_object` |
| Move | NPC travels | `_npc_exec_move_through` |
| Social | NPC talks | `_npc_exec_say`, `_npc_exec_emote` |
| Combat | NPC attacks | Use `combat_service.attack` |
