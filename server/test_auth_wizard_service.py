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


def test_create_flow(ctx):
    w, state_path, sessions, admins, auth_sessions = ctx
    sid = 's1'
    # Entry point
    begin_choose(auth_sessions, sid)
    handled, emits, broadcasts = _run(w, sid, 'create', sessions, admins, state_path, auth_sessions)
    assert handled and any('choose a display name' in e.get('content','').lower() for e in emits)
    handled, emits, broadcasts = _run(w, sid, 'Alice', sessions, admins, state_path, auth_sessions)
    assert handled and any('enter password' in e.get('content','').lower() for e in emits)
    handled, emits, broadcasts = _run(w, sid, 'pw', sessions, admins, state_path, auth_sessions)
    assert handled and any('short character description' in e.get('content','').lower() for e in emits)
    handled, emits, broadcasts = _run(w, sid, 'Curious adventurer', sessions, admins, state_path, auth_sessions)
    assert handled
    # Should be logged in now
    assert sid in w.players
    # First user becomes admin
    assert sid in admins
    
    # Validate world integrity after account creation mutations
    validation_errors = w.validate()
    assert validation_errors == [], f"World validation failed after account creation: {validation_errors}"


def test_login_flow(ctx):
    w, state_path, sessions, admins, auth_sessions = ctx
    # Seed an account through the service path
    sid_seed = 'seed'
    begin_choose(auth_sessions, sid_seed)
    _run(w, sid_seed, 'create', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'Alice', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'pw', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'Curious adventurer', sessions, admins, state_path, auth_sessions)
    # New sid logs in
    auth_sessions.clear()
    sid2 = 's2'
    begin_choose(auth_sessions, sid2)
    handled, emits, broadcasts = _run(w, sid2, 'login', sessions, admins, state_path, auth_sessions)
    assert handled and any('display name' in e.get('content','').lower() for e in emits)
    handled, emits, broadcasts = _run(w, sid2, 'Alice', sessions, admins, state_path, auth_sessions)
    assert handled and any('enter password' in e.get('content','').lower() for e in emits)
    handled, emits, broadcasts = _run(w, sid2, 'pw', sessions, admins, state_path, auth_sessions)
    assert handled
    assert sid2 in w.players


def test_choose_list_users(ctx):
    w, state_path, sessions, admins, auth_sessions = ctx
    sid = 's_list'
    # Initially no users
    begin_choose(auth_sessions, sid)
    handled, emits, _ = _run(w, sid, 'list', sessions, admins, state_path, auth_sessions)
    assert handled
    joined = "\n".join([e.get('content','') for e in emits])
    assert 'No characters exist' in joined
    # Create two users via create flow (seed through wizard for realism)
    sid_seed = 'seedA'
    begin_choose(auth_sessions, sid_seed)
    _run(w, sid_seed, 'create', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'Ada', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'pw', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed, 'Adventurer A', sessions, admins, state_path, auth_sessions)
    # Second
    sid_seed2 = 'seedB'
    begin_choose(auth_sessions, sid_seed2)
    _run(w, sid_seed2, 'create', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed2, 'Bob', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed2, 'pw', sessions, admins, state_path, auth_sessions)
    _run(w, sid_seed2, 'Adventurer B', sessions, admins, state_path, auth_sessions)
    # Back to list on original sid; should see both names, order not critical but sorted in impl
    auth_sessions.pop(sid, None)
    begin_choose(auth_sessions, sid)
    handled, emits, _ = _run(w, sid, 'list', sessions, admins, state_path, auth_sessions)
    assert handled
    text = "\n".join(e.get('content','') for e in emits)
    assert 'Existing characters:' in text
    assert 'Ada' in text and 'Bob' in text
