from __future__ import annotations

import os
from typing import List

import pytest

from world import World
from setup_service import begin_setup, handle_setup_input


@pytest.fixture()
def world_and_state(tmp_path):
    w = World()
    state_path = os.fspath(tmp_path / 'world_state.json')
    return w, state_path


def _drain(emits: List[dict]) -> List[str]:
    return [e.get('content', '') for e in emits]


def test_begin_and_full_setup_flow(world_and_state):
    w, state_path = world_and_state
    sid = 'sid_admin'
    sessions = {}

    # Begin
    first = begin_setup(sessions, sid)
    assert any('set up your world' in c.lower() for c in _drain(first))

    # World name
    handled, emits = handle_setup_input(w, state_path, sid, 'Eldoria', sessions)
    assert handled and any('describe the world' in c.lower() for c in _drain(emits))

    # World description
    handled, emits = handle_setup_input(w, state_path, sid, 'A land of rivers and runes.', sessions)
    assert handled and any('main conflict' in c.lower() for c in _drain(emits))

    # Conflict
    handled, emits = handle_setup_input(w, state_path, sid, 'Warring clans over ancient magic.', sessions)
    assert handled and any('comfortable' in c.lower() for c in _drain(emits))

    # Safety level
    handled, emits = handle_setup_input(w, state_path, sid, 'PG-13', sessions)
    assert handled and any('starting room' in c.lower() for c in _drain(emits))
    assert getattr(w, 'safety_level', None) == 'PG-13'

    # Room id
    handled, emits = handle_setup_input(w, state_path, sid, 'town_square', sessions)
    assert handled and any('description for the starting room' in c.lower() for c in _drain(emits))

    # Room description
    handled, emits = handle_setup_input(w, state_path, sid, 'The bustling heart of the city.', sessions)
    assert handled and any('enter an npc name' in c.lower() for c in _drain(emits))

    # NPC name
    handled, emits = handle_setup_input(w, state_path, sid, 'Town Guard', sessions)
    assert handled and any('short description' in c.lower() for c in _drain(emits))

    # NPC description (finalize)
    handled, emits = handle_setup_input(w, state_path, sid, 'A stalwart guardian of the peace.', sessions)
    assert handled
    out = '\n'.join(_drain(emits))
    assert 'setup complete' in out.lower()
    assert getattr(w, 'setup_complete', False)
    assert 'town_square' in w.rooms
    assert w.start_room_id == 'town_square'
    assert 'Town Guard' in w.npc_sheets


def test_cancel_flow(world_and_state):
    w, state_path = world_and_state
    sid = 'sid_admin'
    sessions = {}
    begin_setup(sessions, sid)
    handled, emits = handle_setup_input(w, state_path, sid, 'cancel', sessions)
    assert handled and any('cancelled' in c.lower() for c in _drain(emits))
