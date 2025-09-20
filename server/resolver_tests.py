"""Unit tests for id_parse_utils resolvers.

Run with:
  python server/resolver_tests.py

These are lightweight asserts that exercise parsing and fuzzy resolution behavior.
"""

from __future__ import annotations

from typing import List

from id_parse_utils import (
    strip_quotes,
    parse_pipe_parts,
    fuzzy_resolve,
    resolve_room_id,
    resolve_player_sid_global,
    resolve_player_sid_in_room,
    resolve_npcs_in_room,
    resolve_door_name,
)
from world import World, Room, CharacterSheet


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_strip_quotes() -> None:
    assert_true(strip_quotes("'Main Hall'") == "Main Hall", "single quotes not stripped")
    assert_true(strip_quotes('"Main Hall"') == "Main Hall", "double quotes not stripped")
    assert_true(strip_quotes(" Main Hall ") == "Main Hall", "whitespace not trimmed")
    # Inner quotes are preserved; we only strip the outer quotes
    assert_true(strip_quotes("'A 'tricky' name'") == "A 'tricky' name", "inner quotes handling")


def test_parse_pipe_parts() -> None:
    parts = parse_pipe_parts("'A' | 'B' | C ", expected=3)
    assert_true(parts == ["A", "B", "C"], f"pipe parts unexpected: {parts}")
    parts2 = parse_pipe_parts("one | two | three | four", expected=3)
    assert_true(parts2 == ["one", "two", "three | four"], f"excess parts join failed: {parts2}")
    parts3 = parse_pipe_parts("one", expected=2)
    assert_true(parts3 == ["one", ""], f"padding missing parts failed: {parts3}")


def test_fuzzy_resolve() -> None:
    items = ["alpha", "alpine", "Beta", "gamma"]
    ok, err, val = fuzzy_resolve("alpha", items)
    assert_true(ok and val == "alpha", f"exact match failed: {(ok, val)}")
    ok2, err2, val2 = fuzzy_resolve("BETA", items)
    assert_true(ok2 and val2 == "Beta", f"ci-exact failed: {(ok2, val2)}")
    ok3, err3, val3 = fuzzy_resolve("gam", items)
    assert_true(ok3 and val3 == "gamma", f"unique prefix failed: {(ok3, val3)}")
    ok4, err4, val4 = fuzzy_resolve("lpi", items)
    assert_true(ok4 and val4 == "alpine", f"unique substring failed: {(ok4, val4)}")
    ok5, err5, val5 = fuzzy_resolve("al", items)
    assert_true((not ok5) and err5 and "Ambiguous" in err5, f"ambiguity not reported: {(ok5, err5, val5)}")
    ok6, err6, val6 = fuzzy_resolve("zeta", items)
    assert_true((not ok6) and err6 is not None, f"not found should produce an error: {(ok6, err6)}")


def test_room_resolver() -> None:
    w = World()
    w.rooms["Main Hall"] = Room(id="Main Hall", description="A")
    w.rooms["Market Square"] = Room(id="Market Square", description="B")
    ok, err, rid = resolve_room_id(w, "'market'")
    assert_true(ok and rid == "Market Square", f"room prefix resolve failed: {(ok, rid, err)}")
    ok2, err2, rid2 = resolve_room_id(w, "hall")
    assert_true(ok2 and rid2 == "Main Hall", f"room substring resolve failed: {(ok2, rid2, err2)}")
    ok3, err3, rid3 = resolve_room_id(w, "nope")
    assert_true((not ok3) and err3 is not None, "missing room should not resolve")


def _mk_player(world: World, sid: str, name: str, room_id: str) -> None:
    sheet = CharacterSheet(display_name=name, description=f"{name} desc")
    world.rooms.setdefault(room_id, Room(id=room_id, description=""))
    world.add_player(sid, name=name, room_id=room_id, sheet=sheet)


def test_player_resolvers() -> None:
    w = World()
    w.rooms["R1"] = Room(id="R1", description="")
    w.rooms["R2"] = Room(id="R2", description="")
    _mk_player(w, "sid1", "Alice", "R1")
    _mk_player(w, "sid2", "Alfred", "R1")
    _mk_player(w, "sid3", "Bob", "R2")
    # global resolver
    ok, err, sid, name = resolve_player_sid_global(w, "'ali'")
    assert_true(ok and sid in ("sid1", "sid2"), f"global player fuzzy resolve unexpected: {(ok, sid, name, err)}")
    # in-room unique
    r1 = w.rooms["R1"]
    ok2, err2, sid2, name2 = resolve_player_sid_in_room(w, r1, "Alfr")
    assert_true(ok2 and sid2 == "sid2" and name2 == "Alfred", f"in-room unique prefix failed: {(ok2, sid2, name2)}")
    # in-room not found
    ok3, err3, sid3, name3 = resolve_player_sid_in_room(w, r1, "Charlie")
    assert_true((not ok3) and sid3 is None and name3 is None, "in-room unknown should fail")


def test_npc_and_door_resolvers() -> None:
    w = World()
    rm = Room(id="Dungeon", description="")
    rm.npcs.update({"Gate Guard", "Innkeeper"})
    rm.doors["oak door"] = "Cell"
    w.rooms[rm.id] = rm
    okn_list = resolve_npcs_in_room(rm, ["guard", "Inn"])  # prefix/substring
    assert_true(set(okn_list) == {"Gate Guard", "Innkeeper"}, f"npc fuzzy list failed: {okn_list}")
    okd, derr, dname = resolve_door_name(rm, "'oak'")
    assert_true(okd and dname == "oak door", f"door fuzzy resolve failed: {(okd, dname, derr)}")


def main() -> None:
    test_strip_quotes()
    test_parse_pipe_parts()
    test_fuzzy_resolve()
    test_room_resolver()
    test_player_resolvers()
    test_npc_and_door_resolvers()
    print("Resolver tests: PASS")


if __name__ == '__main__':
    main()
