"""Scenario test for object templates and room objects.

Run with:
  python server/object_tests.py

This exercises:
- Creating two rooms ('start' and 'bar')
- Linking them with an admin door command (reciprocal door pair)
- Player traversing through the door to the bar
- Admin creating a 'tiki bar' object template (immovable)
- Placing an instance of that object in the bar
- Player using look (world.describe_room_for) to see Objects listed
"""

from __future__ import annotations

import os
import tempfile

from world import World, Room, Object
from account_service import create_account_and_login
from room_service import handle_room_command
from movement_service import move_through_door


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_object_scenario(state_path: str) -> None:
    # Fresh world with two rooms
    w = World()
    w.rooms['start'] = Room(id='start', description='The starting room.')
    w.rooms['bar'] = Room(id='bar', description='A cozy bar with bamboo decor.')
    # Ensure new accounts spawn in 'start'
    w.start_room_id = 'start'

    # Create admin (first user becomes admin) and a normal player
    sessions: dict[str, str] = {}
    admins: set[str] = set()
    sid_admin = 'sid_admin'
    okA, errA, emitsA, broadcastsA = create_account_and_login(
        w, sid_admin, 'Alice', 'pw', 'Admin of the realm', sessions, admins, state_path
    )
    assert_true(okA and not errA, f"admin creation failed: {errA}")

    # Link rooms with a named door using admin room command (creates reciprocal link)
    handled, err, emits = handle_room_command(w, state_path, ['adddoor', 'start|oak door|bar'], sid_admin)
    assert_true(handled and err is None, f"adddoor failed: {err}")
    assert_true(w.rooms['start'].doors.get('oak door') == 'bar', 'forward door missing')
    # Reciprocal back-link should exist in bar (name may be 'oak door' or a variant if collision)
    assert_true(any(trg == 'start' for trg in w.rooms['bar'].doors.values()), 'back-link door missing in bar')

    # Create a regular player and place them in start
    sid_player = 'sid_player'
    okP, errP, emitsP, broadcastsP = create_account_and_login(
        w, sid_player, 'Bob', 'pw2', 'A thirsty patron', sessions, admins, state_path
    )
    assert_true(okP and not errP, f"player creation failed: {errP}")
    assert_true(w.players[sid_player].room_id == 'start', 'player should spawn in start')

    # Player traverses through the door to the bar
    okM, errM, _emitsM, _broadcastsM = move_through_door(w, sid_player, 'oak door')
    assert_true(okM and not errM, f"move through door failed: {errM}")
    assert_true(w.players[sid_player].room_id == 'bar', 'player should arrive in bar')

    # Admin creates a 'tiki bar' object template with an immovable tag
    # (Simulate admin tools by populating world.object_templates)
    tiki_template = Object(display_name='Tiki Bar', description='A festive bamboo tiki bar.', object_tags={'Immovable'})
    w.object_templates['tiki_bar'] = tiki_template

    # Instantiate the object from the template and place in the bar
    # Clone via dict round-trip to simulate template usage
    tiki_obj = Object.from_dict(tiki_template.to_dict())
    # Ensure a fresh UUID for the placed instance
    import uuid as _uuid
    tiki_obj.uuid = str(_uuid.uuid4())
    # Place in room objects
    w.rooms['bar'].objects[tiki_obj.uuid] = tiki_obj

    # Player uses look; verify objects are listed
    desc = w.describe_room_for(sid_player)
    assert_true('Objects:' in desc, 'look output missing Objects section')
    assert_true('Tiki Bar' in desc, "look output should include 'Tiki Bar'")


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmpfile = os.path.join(d, 'world_state.json')
        test_object_scenario(tmpfile)
    print('Object scenario test: PASS')


if __name__ == '__main__':
    main()
