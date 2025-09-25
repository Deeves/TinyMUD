from __future__ import annotations

"""Unit tests for dialogue commands: say, say to, tell, whisper.

We test server-side behavior by importing server.py and monkeypatching:
- server.emit: capture per-sid emissions
- server.socketio.emit: capture targeted emissions (room broadcasts, whispers)
- server.get_sid: return a controllable sid for the current call

The tests construct a tiny world with two players in one room and a couple
of NPCs present. We force AI to offline fallback (model=None) and pin random
rolls where needed to make behavior deterministic.
"""

import types
from typing import Dict, List, Tuple

import pytest


@pytest.fixture()
def server_ctx(monkeypatch):
    # Import the server module once per test context
    import server as srv

    # Replace the world with a fresh instance (avoid persisted state or startup side-effects)
    from world import World, Room
    srv.world = World()
    # No AI calls in tests; ensure offline fallback path
    srv.model = None

    # Minimal world: one room with two players and two NPCs
    room = Room(id="start", description="Start room")
    room.npcs.update({"Innkeeper", "Gate Guard"})
    srv.world.rooms["start"] = room
    srv.world.start_room_id = "start"
    # Add players
    srv.world.add_player("sidA", name="Alice", room_id="start")
    srv.world.add_player("sidB", name="Bob", room_id="start")

    # Captured outputs
    sent_by_sid: Dict[str, List[dict]] = {"sidA": [], "sidB": []}
    targeted: Dict[str, List[dict]] = {"sidA": [], "sidB": []}

    # Current sid controller
    current_sid = {"sid": "sidA"}

    def fake_get_sid():
        return current_sid["sid"]

    def fake_emit(event_name: str, payload=None, **kwargs):
        # server.emit('message', payload) is how handlers send to current sid
        # We only care about 'message' payloads here
        if event_name == "message" and payload is not None:
            sid = current_sid["sid"]
            sent_by_sid.setdefault(sid, []).append(payload)

    class FakeSocketIO:
        def emit(self, event_name: str, payload=None, to: str | None = None, **kwargs):
            # server.socketio.emit('message', payload, to=<sid>) is used for broadcasts and whispers
            if event_name == "message" and payload is not None and to is not None:
                targeted.setdefault(to, []).append(payload)

    # Patch emit/socketio and get_sid
    monkeypatch.setattr(srv, "emit", fake_emit, raising=True)
    monkeypatch.setattr(srv, "socketio", FakeSocketIO(), raising=True)
    monkeypatch.setattr(srv, "get_sid", fake_get_sid, raising=True)

    # Make dice rolls deterministic when needed (return 100 -> no random NPC chime-ins)
    class Roll:
        def __init__(self, total: int):
            self.total = total
            self.expression = "d%"

    monkeypatch.setattr(srv, "dice_roll", lambda expr: Roll(100), raising=True)

    # Expose helpers to switch the current caller sid and to drive the handler
    def send_as(sid: str, text: str):
        current_sid["sid"] = sid
        srv.handle_message({"content": text})

    return types.SimpleNamespace(
        srv=srv,
        send_as=send_as,
        sent_by_sid=sent_by_sid,
        targeted=targeted,
    )


def _names(payloads: List[dict]) -> List[str]:
    out: List[str] = []
    for p in payloads:
        if isinstance(p, dict) and "name" in p and p.get("name") is not None:
            out.append(str(p.get("name")))
    return out


def test_say_broadcast_to_room(server_ctx):
    # Alice says something; Bob should receive a player message via room broadcast.
    server_ctx.send_as("sidA", "say Hello room")
    b_msgs = server_ctx.targeted.get("sidB", [])
    assert b_msgs, "Bob should receive at least one message"
    last = b_msgs[-1]
    assert last.get("type") == "player"
    assert last.get("name") == "Alice"
    assert last.get("content") == "Hello room"
    # Sender (Alice) should not get a local echo for say
    assert all(m.get("type") != "player" or m.get("content") != "Hello room" for m in server_ctx.sent_by_sid.get("sidA", []))


def test_quoted_text_becomes_say(server_ctx):
    # Quoted text should be treated exactly like a say message
    server_ctx.send_as("sidA", '"Hello room"')
    b_msgs = server_ctx.targeted.get("sidB", [])
    assert b_msgs, "Bob should receive at least one message from quoted say"
    last = b_msgs[-1]
    assert last.get("type") == "player"
    assert last.get("name") == "Alice"
    assert last.get("content") == "Hello room"
    # No local echo to Alice
    assert not any(m.get("type") == "player" and m.get("content") == "Hello room" for m in server_ctx.sent_by_sid.get("sidA", []))


def test_say_to_targets_triggers_npc_replies(server_ctx):
    # Targeted say should trigger NPC replies regardless of random chance.
    server_ctx.send_as("sidA", "say to Innkeeper and Gate Guard: Greetings")
    # Bob hears Alice speak
    room_msgs = [m for m in server_ctx.targeted.get("sidB", []) if m.get("type") == "player" and m.get("name") == "Alice"]
    assert room_msgs and room_msgs[-1].get("content") == "Greetings"
    # Alice receives NPC replies locally
    npc_local = [m for m in server_ctx.sent_by_sid.get("sidA", []) if m.get("type") == "npc"]
    assert len(npc_local) >= 2, f"Expected at least 2 NPC replies, got {len(npc_local)}"
    npc_names = set(_names(npc_local))
    assert {"Innkeeper", "Gate Guard"}.issubset(npc_names)
    # Bob also hears the NPC replies via broadcast
    npc_broadcast = [m for m in server_ctx.targeted.get("sidB", []) if m.get("type") == "npc"]
    assert len(npc_broadcast) >= 2


def test_tell_player_broadcasts_only(server_ctx):
    # Tell to a player: room hears it; no private direct message is sent beyond the broadcast
    server_ctx.send_as("sidA", "tell Bob Hello there")
    # Room broadcast to Bob
    b_msgs = [m for m in server_ctx.targeted.get("sidB", []) if m.get("type") == "player" and m.get("name") == "Alice"]
    assert b_msgs and b_msgs[-1].get("content") == "Hello there"
    # No system whisper-like confirmations to Alice for tell
    assert not any(m.get("type") == "system" and "You whisper to" in m.get("content", "") for m in server_ctx.sent_by_sid.get("sidA", []))


def test_tell_npc_broadcasts_and_npc_replies(server_ctx):
    server_ctx.send_as("sidA", "tell Innkeeper How fares the inn?")
    # Bob hears Alice speak
    b_msgs = [m for m in server_ctx.targeted.get("sidB", []) if m.get("type") == "player" and m.get("name") == "Alice"]
    assert b_msgs and b_msgs[-1].get("content") == "How fares the inn?"
    # Alice gets an NPC reply locally
    npc_local = [m for m in server_ctx.sent_by_sid.get("sidA", []) if m.get("type") == "npc"]
    assert npc_local, "Expected an NPC reply to tell"


def test_whisper_player_is_private(server_ctx):
    server_ctx.send_as("sidA", "whisper Bob psst, a secret")
    # Sender gets confirmation
    a_sys = [m for m in server_ctx.sent_by_sid.get("sidA", []) if m.get("type") == "system" and m.get("content", "").startswith("You whisper to Bob:")]
    assert a_sys, "Sender should receive a whisper confirmation"
    # Receiver gets a private message targeted to their sid
    b_priv = [m for m in server_ctx.targeted.get("sidB", []) if m.get("type") == "system" and "whispers to you" in m.get("content", "")]
    assert b_priv, "Receiver should get a private whisper"
    # No room broadcast for whispers
    # We approximate this by ensuring Bob didn't receive an ordinary player-type message from Alice for this action
    assert not any(m.get("type") == "player" and m.get("name") == "Alice" and "psst, a secret" in m.get("content", "") for m in server_ctx.targeted.get("sidB", []))


def test_whisper_npc_is_private_to_sender(server_ctx):
    server_ctx.send_as("sidA", "whisper Innkeeper hush now")
    # Sender gets confirmation line and a private NPC reply
    a_msgs = server_ctx.sent_by_sid.get("sidA", [])
    assert any(m.get("type") == "system" and m.get("content", "").startswith("You whisper to Innkeeper:") for m in a_msgs)
    assert any(m.get("type") == "npc" for m in a_msgs), "Expected a private NPC reply"
    # Bob should not receive any messages from this action
    b_msgs = server_ctx.targeted.get("sidB", [])
    # Filter messages that would be caused by this action: no player or npc messages with this content should appear
    assert not any((m.get("type") in ("player", "npc")) and ("hush now" in m.get("content", "")) for m in b_msgs)


def test_gesture_broadcast_and_sender_view(server_ctx):
    # Alice performs a gesture; she should see a second-person italic line
    # and Bob should see a third-person italic broadcast with conjugated verb.
    server_ctx.send_as("sidA", "gesture wave")
    # Sender view
    a_msgs = server_ctx.sent_by_sid.get("sidA", [])
    assert any(m.get("type") == "system" and m.get("content") == "[i]You wave[/i]" for m in a_msgs)
    # Bob's broadcast
    b_msgs = server_ctx.targeted.get("sidB", [])
    assert any(m.get("type") == "system" and m.get("content") == "[i]Alice waves[/i]" for m in b_msgs)


def test_targeted_gesture_to_player(server_ctx):
    # Alice gestures to Bob; both see appropriate lines, no NPC involvement
    server_ctx.send_as("sidA", "gesture a bow to Bob")
    # Sender sees second-person
    a_msgs = server_ctx.sent_by_sid.get("sidA", [])
    assert any(m.get("type") == "system" and m.get("content") == "[i]You bow to Bob[/i]" for m in a_msgs)
    # Bob sees third-person with conjugated verb
    b_msgs = server_ctx.targeted.get("sidB", [])
    assert any(m.get("type") == "system" and m.get("content") == "[i]Alice bows to Bob[/i]" for m in b_msgs)


def test_targeted_gesture_to_npc_triggers_reply(server_ctx):
    # Alice gestures to Innkeeper; NPC should reply (offline fallback ok)
    server_ctx.send_as("sidA", "gesture a bow to Innkeeper")
    # Sender second-person line
    a_msgs = server_ctx.sent_by_sid.get("sidA", [])
    assert any(m.get("type") == "system" and "[i]You bow to Innkeeper[/i]" == m.get("content") for m in a_msgs)
    # Room sees third-person line
    b_msgs = server_ctx.targeted.get("sidB", [])
    assert any(m.get("type") == "system" and "[i]Alice bows to Innkeeper[/i]" == m.get("content") for m in b_msgs)
    # NPC reply should appear locally to Alice
    assert any(m.get("type") == "npc" for m in a_msgs), "Expected NPC to react to the gesture"


def test_invalid_payload_shape_emits_error(monkeypatch):
    # Import fresh server; ensure model disabled
    import importlib
    srv = importlib.import_module('server')
    setattr(srv, 'model', None)

    # Capture emits to the implicit current sid
    captured = []
    def fake_emit(event_name: str, payload=None, **kwargs):
        if event_name == "message" and payload is not None:
            captured.append(payload)
    monkeypatch.setattr(srv, "emit", fake_emit, raising=True)
    # get_sid isn't used for invalid shape path, but keep it defined
    monkeypatch.setattr(srv, "get_sid", lambda: "sidZ", raising=True)

    # Send bad payloads
    srv.handle_message(None)
    srv.handle_message({})
    srv.handle_message({"wrong": "field"})

    # We should have at least one error emission
    assert any(p.get('type') == 'error' and 'Invalid payload' in p.get('content','') for p in captured)
