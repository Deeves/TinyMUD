from __future__ import annotations

"""
auth_wizard_service.py — Login, registration, and character creation flows.

Philosophy:
- Tiny state machine per user (keyed by SID) stored in auth_sessions.
- Stateless functions that return messages to emit; sockets live elsewhere.
- Be kind to new contributors: tiny steps, clear messages, defensive checks.
"""

from typing import Dict, List, Tuple
from account_service import create_account_and_login, login_existing


def begin_login(auth_sessions: Dict[str, dict], sid: str) -> List[dict]:
    """Start the login flow for a user."""
    auth_sessions[sid] = {"mode": "login", "step": "name", "temp": {}}
    return [{'type': 'system', 'content': 'Login selected. Enter your display name:'}]


def begin_register(auth_sessions: Dict[str, dict], sid: str) -> List[dict]:
    """Start the registration flow for a new user."""
    auth_sessions[sid] = {"mode": "create", "step": "name", "temp": {}}
    return [{'type': 'system', 'content': 'Creation selected. Choose a display name (2-32 chars):'}]


def begin_choose(auth_sessions: Dict[str, dict], sid: str) -> List[dict]:
    """Initialize an interactive auth session with a 'choose' prompt."""
    auth_sessions[sid] = {"mode": None, "step": "choose", "temp": {}}
    return [{'type': 'system', 'content': 'Type "create" to forge a new character or "login" to sign in.'}]


def handle_interactive_auth(
    world,
    sid: str,
    text: str,
    sessions: Dict[str, str],
    admins: set[str],
    state_path: str,
    auth_sessions: Dict[str, dict],
) -> Tuple[bool, List[dict], List[Tuple[str, dict]]]:
    """Advance the interactive auth (create/login) wizard.

    Returns (handled, emits, broadcasts). handled=False if no auth handling occurred.
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    # Ensure a session container exists
    if sid not in auth_sessions:
        auth_sessions[sid] = {"mode": None, "step": "choose", "temp": {}}
    sess = auth_sessions[sid]
    step = sess.get('step')
    mode = sess.get('mode')
    text_lower = (text or '').strip().lower()

    # Choose step: decide between login/create
    if step == 'choose':
        if text_lower in ("login", "l"):
            sess['mode'] = 'login'
            sess['step'] = 'name'
            emits.append({'type': 'system', 'content': 'Login selected. Enter your display name:'})
            return True, emits, broadcasts
        if text_lower in ("create", "c"):
            sess['mode'] = 'create'
            sess['step'] = 'name'
            emits.append({'type': 'system', 'content': 'Creation selected. Choose a display name (2-32 chars):'})
            return True, emits, broadcasts
        emits.append({'type': 'system', 'content': 'Type "create" to forge a new character or "login" to sign in.'})
        return True, emits, broadcasts

    # Common cancel/back handling
    if text_lower in ("cancel", "back"):
        sess['mode'] = None
        sess['step'] = 'choose'
        sess['temp'] = {}
        emits.append({'type': 'system', 'content': 'Cancelled. Type "create" or "login" to continue.'})
        return True, emits, broadcasts

    # Name step
    if step == 'name':
        name = (text or '').strip()
        if len(name) < 2 or len(name) > 32:
            emits.append({'type': 'error', 'content': 'Name must be between 2 and 32 characters. Try again or type cancel.'})
            return True, emits, broadcasts
        sess['temp']['name'] = name
        sess['step'] = 'password'
        emits.append({'type': 'system', 'content': 'Enter password:'})
        return True, emits, broadcasts

    # Password step
    if step == 'password':
        pwd = (text or '').strip()
        # Keep this permissive to match legacy tests that use 'pw'
        if len(pwd) < 2:
            emits.append({'type': 'error', 'content': 'Password too short (min 2). Try again or type cancel.'})
            return True, emits, broadcasts
        sess['temp']['password'] = pwd
        if mode == 'create':
            sess['step'] = 'description'
            emits.append({'type': 'system', 'content': 'Enter a short character description (max 300 chars):'})
            return True, emits, broadcasts
        # login path completes here
        name = sess['temp'].get('name', '')
        ok, err, emits2, broadcasts2 = login_existing(world, sid, name, pwd, sessions, admins)
        if not ok:
            emits.append({'type': 'error', 'content': err or 'Login failed.'})
            return True, emits, broadcasts
        # Clear auth flow
        auth_sessions.pop(sid, None)
        emits.extend(emits2)
        broadcasts.extend(broadcasts2)
        return True, emits, broadcasts

    # Description step (create only)
    if step == 'description':
        desc = (text or '').strip()
        if len(desc) > 300:
            emits.append({'type': 'error', 'content': 'Description too long (max 300). Try again or type cancel.'})
            return True, emits, broadcasts
        name = sess['temp'].get('name', '')
        pwd = sess['temp'].get('password', '')
        if world.get_user_by_display_name(name):
            emits.append({'type': 'error', 'content': 'That display name is already taken. Type back to choose another.'})
            return True, emits, broadcasts
        ok, err, emits2, broadcasts2 = create_account_and_login(world, sid, name, pwd, desc, sessions, admins, state_path)
        if not ok:
            emits.append({'type': 'error', 'content': err or 'Failed to create user.'})
            return True, emits, broadcasts
        auth_sessions.pop(sid, None)
        emits.extend(emits2)
        broadcasts.extend(broadcasts2)
        return True, emits, broadcasts

    # Unknown step: do not handle
    return False, emits, broadcasts


def handle_login_input(world, sid: str, text: str, auth_sessions: Dict[str, dict]) -> Tuple[bool, List[dict]]:
    """Back-compat shim: not used in current server; kept for potential reuse."""
    return False, []


def handle_register_input(world, sid: str, text: str, auth_sessions: Dict[str, dict]) -> Tuple[bool, List[dict]]:
    """Back-compat shim: not used in current server; kept for potential reuse."""
    return False, []
