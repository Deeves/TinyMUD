from __future__ import annotations

import os
from typing import List, Tuple

import pytest

from world import World
from auth_wizard_service import handle_interactive_auth, begin_choose


@pytest.fixture()
def ctx(tmp_path):
    w = World()
    state_path = os.fspath(tmp_path / 'world_state.json')
    sessions: dict[str, str] = {}
    admins: set[str] = set()
    auth_sessions: dict[str, dict] = {}
    return w, state_path, sessions, admins, auth_sessions


def _run(world, sid, text, sessions, admins, state_path, auth_sessions):
    return handle_interactive_auth(world, sid, text, sessions, admins, state_path, auth_sessions)


def test_login_retry_after_invalid_password(ctx):
    w, state_path, sessions, admins, auth_sessions = ctx
    # Seed an account via interactive create flow
    sid_seed = 'seed'
    begin_choose(auth_sessions, sid_seed)
    _run(w, sid_seed, 'create', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'Alice', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'pw', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'Curious adventurer', sessions, admins, state_path, auth_sessions)

    # New session attempts login with wrong password first
    sid2 = 's2'
    begin_choose(auth_sessions, sid2)
    handled, emits, broadcasts = _run(w, sid2, 'login', sessions, admins, state_path, auth_sessions)
    assert handled
    handled, emits, broadcasts = _run(w, sid2, 'Alice', sessions, admins, state_path, auth_sessions)
    assert handled
    # Wrong password
    handled, emits, broadcasts = _run(w, sid2, 'wrong', sessions, admins, state_path, auth_sessions)
    assert handled
    # Expect an error followed by a re-prompt to enter password again
    contents = [e.get('content','').lower() for e in emits]
    assert any('invalid name or password' in t for t in contents)
    assert any('enter password:' in t for t in contents)
    # Still not logged in
    assert sid2 not in w.players

    # Now enter the correct password and succeed
    handled, emits, broadcasts = _run(w, sid2, 'pw', sessions, admins, state_path, auth_sessions)
    assert handled
    assert sid2 in w.players
