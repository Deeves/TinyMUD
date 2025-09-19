"""Admin operations: promote/demote/list, kick lookup, and purge support.

Note: The actual disconnect() must be performed by the caller since it depends
on Flask-SocketIO. This module performs lookups and returns messages to emit.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import os
from world import World


def list_admins(world) -> List[str]:
    try:
        return sorted([u.display_name for u in world.users.values() if u.is_admin])
    except Exception:
        return []


def promote_user(world, sessions: Dict[str, str], admins: set[str], target_name: str, state_path: str) -> Tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    user = world.get_user_by_display_name(target_name)
    if not user:
        return True, f"User '{target_name}' not found.", emits
    if user.is_admin:
        emits.append({'type': 'system', 'content': f"'{user.display_name}' is already an admin."})
        return True, None, emits
    user.is_admin = True
    _save_silent(world, state_path)
    # Grant admin to any connected SIDs for this user
    try:
        for psid, uid in list(sessions.items()):
            if uid == user.user_id:
                admins.add(psid)
    except Exception:
        pass
    emits.append({'type': 'system', 'content': f"Promoted '{user.display_name}' to admin."})
    return True, None, emits


def demote_user(world, sessions: Dict[str, str], admins: set[str], target_name: str, state_path: str) -> Tuple[bool, str | None, List[dict]]:
    emits: List[dict] = []
    user = world.get_user_by_display_name(target_name)
    if not user:
        return True, f"User '{target_name}' not found.", emits
    if not user.is_admin:
        emits.append({'type': 'system', 'content': f"'{user.display_name}' is not an admin."})
        return True, None, emits
    try:
        admin_count = sum(1 for u in world.users.values() if u.is_admin)
    except Exception:
        admin_count = 1
    if admin_count <= 1:
        return True, 'Cannot demote the last remaining admin.', emits
    user.is_admin = False
    _save_silent(world, state_path)
    try:
        for psid, uid in list(sessions.items()):
            if uid == user.user_id:
                admins.discard(psid)
    except Exception:
        pass
    emits.append({'type': 'system', 'content': f"Demoted '{user.display_name}' from admin."})
    return True, None, emits


def find_player_sid_by_name(world, player_name: str) -> Optional[str]:
    for psid, p in world.players.items():
        if p.sheet.display_name.lower() == player_name.lower():
            return psid
    return None


def prepare_purge(world, state_path: str) -> Tuple[bool, str | None]:
    # Nothing to persist yet; server will set pending confirm and handle disconnects
    return True, None


def purge_prompt() -> dict:
    return {'type': 'system', 'content': "Are you sure you want to purge the world? This cannot be undone. Type 'Y' to confirm or 'N' to cancel."}


def is_confirm_yes(text: str) -> bool:
    t = (text or '').strip().lower()
    return t in ('y', 'yes')


def is_confirm_no(text: str) -> bool:
    t = (text or '').strip().lower()
    return t in ('n', 'no')


def prepare_purge_snapshot_sids(world) -> List[str]:
    """Return a snapshot of current connected player SIDs for post-purge disconnects."""
    try:
        return list(world.players.keys())
    except Exception:
        return []


def execute_purge(state_path: str) -> World:
    """Delete persisted world file and return a fresh World with default room persisted."""
    try:
        if os.path.exists(state_path):
            os.remove(state_path)
    except Exception:
        pass
    new_world = World()
    try:
        new_world.save_to_file(state_path)
    except Exception:
        pass
    return new_world


def _save_silent(world, state_path: str) -> None:
    try:
        world.save_to_file(state_path)
    except Exception:
        pass
