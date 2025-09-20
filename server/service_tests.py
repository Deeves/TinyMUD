"""Tiny, self-contained tests for service modules.

Run with:
  python server/service_tests.py

These are not full unit tests, just smoke checks for signatures and basic flows.
"""

from __future__ import annotations

import os
import tempfile

from world import World
from account_service import create_account_and_login, login_existing
from movement_service import move_through_door, move_stairs, teleport_player
from admin_service import (
    list_admins,
    promote_user,
    demote_user,
    find_player_sid_by_name,
    prepare_purge_snapshot_sids,
    execute_purge,
)
from dialogue_utils import parse_say, split_targets
from room_service import handle_room_command
from security_utils import redact_sensitive


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_accounts_and_admins(tmpfile):
    w = World()
    sessions = {}
    admins = set()
    sid = 'sid1'
    ok, err, emits, broadcasts = create_account_and_login(w, sid, 'Alice', 'pw', 'desc', sessions, admins, tmpfile)
    assert_true(ok and not err, f"create failed: {err}")
    assert_true('sid1' in sessions and sessions['sid1'], 'sid not mapped to user')
    names = list_admins(w)
    assert_true('Alice' in names, 'first user should be admin')
    # Attempt demote should fail for last remaining admin
    ok, err, emits2 = demote_user(w, sessions, admins, 'Alice', tmpfile)
    assert_true(err is not None and 'last remaining admin' in err, 'demote should fail for single admin')
    # Create Bob, promote Bob to admin, then demote Alice should succeed
    sid2 = 'sid2'
    ok, err, emitsB, broadcastsB = create_account_and_login(w, sid2, 'Bob', 'pw2', 'desc2', sessions, admins, tmpfile)
    assert_true(ok and not err, f"create Bob failed: {err}")
    ok, err, emitsP = promote_user(w, sessions, admins, 'Bob', tmpfile)
    assert_true(ok and not err, f"promote Bob failed: {err}")
    ok, err, emitsD = demote_user(w, sessions, admins, 'Alice', tmpfile)
    assert_true(ok and not err, f"demote Alice failed: {err}")


def test_movement(tmpfile):
    from world import Room
    w = World()
    # Create two rooms and a door
    w.rooms['start'] = Room(id='start', description='Start')
    w.rooms['hall'] = Room(id='hall', description='Hall')
    w.rooms['start'].doors['oak door'] = 'hall'
    sid = 'sid2'
    w.add_player(sid, name='Bob', room_id='start')
    ok, err, emits, broadcasts = move_through_door(w, sid, 'oak door')
    assert_true(ok, f"move through failed: {err}")
    ok, err, emits, broadcasts = move_stairs(w, sid, 'up')
    assert_true(not ok, 'should not move up when no stairs')


def test_purge(tmpfile):
    w = World()
    # Simulate a connected player (even without rooms)
    w.add_player('sidA', name='A')
    sids = prepare_purge_snapshot_sids(w)
    assert_true('sidA' in sids, 'snapshot should include sidA')
    neww = execute_purge(tmpfile)
    assert_true(len(neww.rooms) == 0, 'new world should be blank after purge')


def test_teleport(tmpfile):
    from world import Room
    w = World()
    # Rooms
    w.rooms['start'] = Room(id='start', description='Start')
    w.rooms['hall'] = Room(id='hall', description='Hall')
    sid = 'sidT'
    w.add_player(sid, name='Tel', room_id='start')
    ok, err, emits, broadcasts = teleport_player(w, sid, 'hall')
    assert_true(ok and not err, f"teleport failed: {err}")
    assert_true(w.players[sid].room_id == 'hall', 'player should be in hall after teleport')
    ok2, err2, emits2, broadcasts2 = teleport_player(w, sid, 'missing')
    assert_true(not ok2 and err2 is not None, 'teleport to missing room should fail')


def test_room_adddoor_suggestions(tmpfile):
    from world import Room
    w = World()
    # Create rooms with various starting letters
    w.rooms['alpha'] = Room(id='alpha', description='A')
    w.rooms['attic'] = Room(id='attic', description='B')
    w.rooms['beta'] = Room(id='beta', description='B')
    # 1) Adddoor to missing source with suggestions (should suggest alpha, attic for 'a...')
    handled, err, emits = handle_room_command(w, tmpfile, ['adddoor', 'amber|oak door|beta'])
    assert_true(handled and err is not None, 'expected error for missing room')
    e1 = err or ""
    assert_true('Did you mean' in e1 and 'alpha' in e1 and 'attic' in e1, 'suggestions missing expected ids')
    # 2) Missing source with no matching first letter should have no suggestion suffix
    handled2, err2, emits2 = handle_room_command(w, tmpfile, ['adddoor', 'zoo|oak door|beta'])
    assert_true(handled2 and err2 is not None, 'expected error for missing room (zoo)')
    e2 = err2 or ""
    assert_true('Did you mean' not in e2, 'should not include suggestions when none match')
    # 3) Valid adddoor path works
    handled3, err3, emits3 = handle_room_command(w, tmpfile, ['adddoor', 'alpha|oak door|beta'])
    assert_true(handled3 and err3 is None, f'unexpected error on valid adddoor: {err3}')
    assert_true(w.rooms['alpha'].doors.get('oak door') == 'beta', 'door not set correctly')
    # Reciprocal door should also be created in beta pointing back to alpha
    assert_true(any(rid == 'alpha' for rid in w.rooms['beta'].doors.values()), 'reciprocal door not created in target room')

    # 4) Adding a door to an unknown target should keep one-way and inform via emits
    handled4, err4, emits4 = handle_room_command(w, tmpfile, ['adddoor', 'alpha|mystery door|gamma'])
    assert_true(handled4 and err4 is None, 'adddoor to missing target should be handled without fatal error')
    assert_true(w.rooms['alpha'].doors.get('mystery door') == 'gamma', 'one-way door to missing target not stored')


def main():
    with tempfile.TemporaryDirectory() as d:
        tmpfile = os.path.join(d, 'world_state.json')
        test_accounts_and_admins(tmpfile)
        test_movement(tmpfile)
        test_purge(tmpfile)
        test_room_adddoor_suggestions(tmpfile)
        test_teleport(tmpfile)
        # Redaction test: ensure passwords get masked in nested structures
        sample = {
            "users": {
                "uid1": {"display_name": "Alice", "password": "secret", "sheet": {"display_name": "Alice"}},
                "uid2": {"display_name": "Bob", "password_hash": "abcd1234"},
            },
            "rooms": [],
        }
        red = redact_sensitive(sample)
        assert_true(red["users"]["uid1"]["password"] == "***REDACTED***", "password not redacted")
        assert_true(red["users"]["uid2"]["password_hash"] == "***REDACTED***", "password_hash not redacted")
        # Parser tests
        # 1) Plain say
        is_say, targets, msg = parse_say('say Hello world')
        assert_true(is_say and targets is None and msg == 'Hello world', 'plain say failed')

        # 2) say to single with quotes (parser only; NPC existence not required)
        is_say, targets, msg = parse_say('say to The Wizard "What is this place?"')
        assert_true(is_say and targets == ['The Wizard'] and msg == 'What is this place?', 'say to quoted failed')

        # 3) say to multiple with colon and and
        is_say, targets, msg = parse_say('say to Innkeeper and Gate Guard: We seek passage.')
        assert_true(is_say and targets == ['Innkeeper', 'Gate Guard'] and msg == 'We seek passage.', 'say to colon+and failed')

        # 4) say to multiple with commas and --
        is_say, targets, msg = parse_say('say to Innkeeper, Gate Guard, and Thief -- Open the gate!')
        assert_true(is_say and targets == ['Innkeeper', 'Gate Guard', 'Thief'] and msg == 'Open the gate!', 'say to commas+-- failed')

        # 5) split_targets edge trimming and dedupe
        split = split_targets(' Innkeeper ,  Innkeeper and  Gate Guard ')
        assert_true(split == ['Innkeeper', 'Gate Guard'], 'split_targets dedupe/trim failed')
    print('Service tests: PASS')


if __name__ == '__main__':
    main()
