"""Account-related operations for the AI MUD server.

This module contains pure functions that operate on the world and session state
to perform account creation and login. They do not import Flask/SocketIO; instead
they return a list of messages to emit to the current client and broadcasts for
other players in the same room. The caller (server.py) is responsible for sending.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def create_account_and_login(
    world,
    sid: str,
    display_name: str,
    password: str,
    description: str,
    sessions: Dict[str, str],
    admins: set[str],
    state_path: str,
) -> Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]:
    """Create a new user and immediately log them in as a player.

    Returns: (success, error, emits, broadcasts)
    - emits: list of payloads to emit back to the caller's client
    - broadcasts: list of (room_id, payload) to broadcast to others in the room
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    try:
        # First user becomes admin by default
        grant_admin = (len(world.users) == 0)
        user = world.create_user(display_name, password, description, is_admin=grant_admin)
        try:
            world.save_to_file(state_path)
        except Exception:
            # Best-effort persistence
            pass
    except Exception as e:
        return False, f"Failed to create user: {e}", emits, broadcasts

    # Place into the world
    player = world.add_player(sid, sheet=user.sheet)
    sessions[sid] = user.user_id
    if user.is_admin:
        admins.add(sid)

    emits.append({'type': 'system', 'content': f'{user.display_name} arrives.'})
    # Greet with world context if configured
    try:
        if getattr(world, 'setup_complete', False):
            wname = getattr(world, 'world_name', None)
            wdesc = getattr(world, 'world_description', None)
            wconf = getattr(world, 'world_conflict', None)
            if wname:
                emits.append({'type': 'system', 'content': f"[b]World:[/b] {wname}"})
            if wdesc:
                emits.append({'type': 'system', 'content': wdesc})
            if wconf:
                emits.append({'type': 'system', 'content': wconf})
    except Exception:
        pass
    emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
    # Announce arrival to others
    broadcasts.append((player.room_id, {'type': 'system', 'content': f"{player.sheet.display_name} enters."}))
    return True, None, emits, broadcasts


def login_existing(
    world,
    sid: str,
    display_name: str,
    password: str,
    sessions: Dict[str, str],
    admins: set[str],
) -> Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]:
    """Log an existing user in and place them as a player in the world.

    Returns: (success, error, emits, broadcasts)
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    user = world.get_user_by_display_name(display_name)
    if not user or user.password != password:
        return False, 'Invalid name or password.', emits, broadcasts

    player = world.add_player(sid, sheet=user.sheet)
    sessions[sid] = user.user_id
    if user.is_admin:
        admins.add(sid)

    emits.append({'type': 'system', 'content': f'Welcome back, {user.display_name}.'})
    # Greet with world context if configured
    try:
        if getattr(world, 'setup_complete', False):
            wname = getattr(world, 'world_name', None)
            wdesc = getattr(world, 'world_description', None)
            wconf = getattr(world, 'world_conflict', None)
            if wname:
                emits.append({'type': 'system', 'content': f"[b]World:[/b] {wname}"})
            if wdesc:
                emits.append({'type': 'system', 'content': wdesc})
            if wconf:
                emits.append({'type': 'system', 'content': wconf})
    except Exception:
        pass
    emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
    broadcasts.append((player.room_id, {'type': 'system', 'content': f"{player.sheet.display_name} enters."}))
    return True, None, emits, broadcasts
