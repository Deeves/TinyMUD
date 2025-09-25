from __future__ import annotations

"""
setup_service.py — World setup wizard (admin-only) extracted from the socket layer.

What this does, in plain words:
- Guides the first admin through naming their world, describing it, choosing a
  comfort/safety level, creating a starting room, and optionally adding a first
  NPC — all as a friendly interactive flow.

Design goals:
- Keep everything pure: return lists of messages to emit, never touch sockets.
- Store transient state in a provided world_setup_sessions dict keyed by SID.
- Make contributors comfortable: tiny functions, clear steps, gentle validation.
"""

from typing import Dict, List, Tuple
import re

from world import Room, CharacterSheet
from persistence_utils import save_world


def begin_setup(world_setup_sessions: Dict[str, dict], sid: str) -> List[dict]:
    """Initialize the setup state and return the first prompt to the admin."""
    world_setup_sessions[sid] = {"step": "world_name", "temp": {}}
    return [
        {'type': 'system', 'content': "Let's set up your world! What's the name of this world?"}
    ]


def handle_setup_input(world, state_path: str, sid: str, player_message: str, world_setup_sessions: Dict[str, dict]) -> Tuple[bool, List[dict]]:
    """Advance the setup wizard given the latest input.

    Contract:
    - Inputs: world, path to state file, sid, raw player_message, sessions dict
    - Output: (handled, emits)
      • handled=True means the message was consumed by the wizard (caller should return)
      • emits: list of payloads to send back to the admin
    """
    emits: List[dict] = []
    if sid not in world_setup_sessions:
        return False, emits

    sess = world_setup_sessions.get(sid, {"step": "world_name", "temp": {}})
    step = sess.get("step")
    temp = sess.get("temp", {})
    text_raw = player_message or ""
    text_lower = text_raw.strip().lower()

    # Universal controls
    if text_lower in ("cancel", "back"):
        world_setup_sessions.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Setup cancelled. Use /setup to restart if needed.'})
        return True, emits

    # Step: world name
    if step == 'world_name':
        name = text_raw.strip()
        if len(name) < 2 or len(name) > 64:
            emits.append({'type': 'error', 'content': 'World name must be 2-64 characters.'})
            return True, emits
        world.world_name = name
        sess['step'] = 'world_description'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Describe the world in 1-3 sentences:'})
        return True, emits

    # Step: world description
    if step == 'world_description':
        desc = text_raw.strip()
        if len(desc) < 10:
            emits.append({'type': 'error', 'content': 'Please add a bit more detail (>= 10 chars).'})
            return True, emits
        world.world_description = desc
        sess['step'] = 'world_conflict'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Describe the main conflict of this world:'})
        return True, emits

    # Step: world conflict
    if step == 'world_conflict':
        conflict = text_raw.strip()
        if len(conflict) < 5:
            emits.append({'type': 'error', 'content': 'Please provide a short conflict summary (>= 5 chars).'})
            return True, emits
        world.world_conflict = conflict
        # Ask for roleplay comfort/safety setting next
        sess['step'] = 'safety_level'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            "What type of roleplay are you and your group comfortable with?\n"
            "Choose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], [b]Low (R)[/b], or [b]Safety Filters Off[/b].\n"
            "You can type: G, PG-13, R, or OFF."
        )})
        return True, emits

    # Step: safety level
    if step == 'safety_level':
        level_raw = text_raw.strip().upper()
        if level_raw in ("HIGH", "G", "ALL-AGES"):
            level = 'G'
        elif level_raw in ("MEDIUM", "PG13", "PG-13", "PG_13", "PG"):
            level = 'PG-13'
        elif level_raw in ("LOW", "R"):
            level = 'R'
        elif level_raw in ("OFF", "NONE", "NO FILTERS", "SAFETY FILTERS OFF"):
            level = 'OFF'
        else:
            emits.append({'type': 'error', 'content': 'Please answer with G, PG-13, R, or OFF.'})
            return True, emits
        try:
            world.safety_level = level
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'room_id'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Create the starting room. Enter a room id (letters, numbers, underscores), e.g., town_square:'})
        return True, emits

    # Step: room id
    if step == 'room_id':
        rid = re.sub(r"[^A-Za-z0-9_]+", "_", text_raw.strip())
        if not rid:
            emits.append({'type': 'error', 'content': 'Room id cannot be empty.'})
            return True, emits
        if rid in world.rooms:
            emits.append({'type': 'error', 'content': f"Room id '{rid}' already exists. Choose another."})
            return True, emits
        temp['room_id'] = rid
        sess['temp'] = temp
        sess['step'] = 'room_desc'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Enter a description for the starting room:'})
        return True, emits

    # Step: room description (creates room and moves player there if present)
    if step == 'room_desc':
        rdesc = text_raw.strip()
        rid = temp.get('room_id')
        if not rid:
            emits.append({'type': 'error', 'content': 'Internal error: missing room id.'})
            return True, emits
        world.rooms[rid] = Room(id=rid, description=rdesc)
        world.start_room_id = rid
        # Move current player there if logged in
        if sid in world.players:
            try:
                world.move_player(sid, rid)
            except Exception:
                pass
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'npc_name'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Create an NPC for this room. Enter an NPC name (or type "skip"):'})
        return True, emits

    # Step: npc name (or skip)
    if step == 'npc_name':
        npc_name = text_raw.strip()
        if npc_name.lower() in ('skip', 'none'):
            world.setup_complete = True
            try:
                save_world(world, state_path, debounced=True)
            except Exception:
                pass
            world_setup_sessions.pop(sid, None)
            emits.append({'type': 'system', 'content': 'World setup complete! Others will now see your world description and conflict on login.'})
            # Show look
            emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
            return True, emits
        temp['npc_name'] = npc_name
        sess['temp'] = temp
        sess['step'] = 'npc_desc'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': f'Enter a short description for {npc_name}:'})
        return True, emits

    # Step: npc description (finalizes NPC and completes setup)
    if step == 'npc_desc':
        npc_desc = text_raw.strip()
        rid = temp.get('room_id')
        npc_name = temp.get('npc_name')
        room = world.rooms.get(rid)
        if room and npc_name:
            room.npcs.add(npc_name)
            sheet = world.npc_sheets.get(npc_name)
            if sheet is None:
                sheet = CharacterSheet(display_name=npc_name, description=npc_desc)
                world.npc_sheets[npc_name] = sheet
            else:
                sheet.description = npc_desc
            try:
                world.get_or_create_npc_id(npc_name)
            except Exception:
                pass
            try:
                world.save_to_file(state_path)
            except Exception:
                pass
        world.setup_complete = True
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        world_setup_sessions.pop(sid, None)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added. World setup complete!"})
        emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
        return True, emits

    # Unknown step — be gentle and reset
    world_setup_sessions.pop(sid, None)
    emits.append({'type': 'error', 'content': 'Setup session lost. Use /setup to start again.'})
    return True, emits
