"""Account-related operations for the AI MUD server.

This module contains pure functions that operate on the world and session state
to perform account creation and login. They do not import Flask/SocketIO; instead
they return a list of messages to emit to the current client and broadcasts for
other players in the same room. The caller (server.py) is responsible for sending.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from concurrency_utils import atomic_many
from persistence_utils import save_world
from rate_limiter import check_rate_limit, OperationType


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
    
    # Rate limiting: prevent account creation spam and brute force attempts
    if not check_rate_limit(sid, OperationType.MODERATE, "account_creation"):
        return (False, 'You are creating accounts too quickly. '
                       'Please wait before creating another account.', emits, broadcasts)

    try:
        # Protect creation + session/admin updates as one atomic step
        with atomic_many(['world', 'sessions', 'admins']):
            # First user becomes admin by default. In Creative Mode, everyone is admin.
            grant_admin = (
                (len(world.users) == 0)
                or bool(getattr(world, 'debug_creative_mode', False))
            )
            user = world.create_user(display_name, password, description, is_admin=grant_admin)
            # Place into the world
            player = world.add_player(sid, sheet=user.sheet)
            sessions[sid] = user.user_id
            if user.is_admin:
                admins.add(sid)
        # Persist after atomic section (best-effort, debounced)
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            # Best-effort persistence
            pass
    except Exception as e:
        return False, f"Failed to create user: {e}", emits, broadcasts

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
    broadcasts.append((
        player.room_id,
        {
            'type': 'system',
            'content': f"{player.sheet.display_name} enters.",
        },
    ))
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
    
    # Rate limiting: prevent brute force login attempts
    if not check_rate_limit(sid, OperationType.MODERATE, "login_attempt"):
        return (False, 'You are attempting to login too frequently. '
                       'Please wait before trying again.', emits, broadcasts)

    # Validate credentials outside of mutation lock
    user = world.get_user_by_display_name(display_name)
    if not user or user.password != password:
        return False, 'Invalid name or password.', emits, broadcasts

    # Determine spawn room: prefer user's home bed if it exists; else start_room
    spawn_room_id = None
    info_msgs: List[str] = []
    try:
        bed_uuid = getattr(user, 'home_bed_uuid', None)
        if bed_uuid:
            # Find the room containing that bed object
            for rid, room in (world.rooms or {}).items():
                if bed_uuid in (room.objects or {}):
                    spawn_room_id = rid
                    break
            if not spawn_room_id:
                # Bed no longer exists
                info_msgs.append(
                    "Your bed was destroyed while you were gone. "
                    "You wake up in the start room."
                )
                # Clear the home bed and persist best-effort
                try:
                    user.home_bed_uuid = None
                    save_world(world, getattr(world, 'STATE_PATH', None) or '')
                except Exception:
                    pass
    except Exception:
        pass
    with atomic_many(['world', 'sessions', 'admins']):
        player = world.add_player(sid, sheet=user.sheet, room_id=spawn_room_id)
        sessions[sid] = user.user_id
        # In Creative Mode, ensure the user is an admin (persist change best-effort)
        if getattr(world, 'debug_creative_mode', False) and not getattr(user, 'is_admin', False):
            try:
                user.is_admin = True
            except Exception:
                pass
        if user.is_admin or getattr(world, 'debug_creative_mode', False):
            admins.add(sid)

    emits.append({'type': 'system', 'content': f'Welcome back, {user.display_name}.'})
    for m in info_msgs:
        emits.append({'type': 'system', 'content': m})
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
    broadcasts.append((
        player.room_id,
        {
            'type': 'system',
            'content': f"{player.sheet.display_name} enters.",
        },
    ))
    return True, None, emits, broadcasts
