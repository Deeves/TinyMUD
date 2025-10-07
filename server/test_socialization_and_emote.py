from __future__ import annotations

"""Tests for NPC socialization and emote planner tool.

Covers:
- _npc_offline_plan enqueues an 'emote' action when socialization < NEED_THRESHOLD.
- _npc_exec_emote broadcasts and increases socialization by SOCIAL_REFILL_EMOTE.
"""

def test_offline_plan_emote_when_social_low():
    import server as srv
    from world import Room, CharacterSheet

    room = Room(id="start", description="Start room")
    sheet = CharacterSheet(display_name="Innkeeper", description="NPC")
    # Keep nutrition fine, but drop socialization below threshold
    sheet.hunger = 80.0
    sheet.thirst = 80.0
    # Simulate loneliness: set socialization just below threshold
    setattr(sheet, 'socialization', max(0.0, float(srv.NEED_THRESHOLD) - 1.0))

    plan = srv._npc_offline_plan("Innkeeper", room, sheet)
    assert any((a or {}).get('tool') == 'emote' for a in plan), f"Expected an 'emote' action in plan, got: {plan}"


def test_emote_exec_refills_socialization(monkeypatch):
    import server as srv
    from world import Room, CharacterSheet, World

    # Fresh world and room so broadcast_to_room won't fail on lookups
    srv.world = World()
    rid = "start"
    srv.world.rooms[rid] = Room(id=rid, description="Start room")
    npc_name = "Innkeeper"
    srv.world.rooms[rid].npcs.add(npc_name)

    # Ensure NPC sheet with low socialization
    sheet = CharacterSheet(display_name=npc_name, description="NPC")
    setattr(sheet, 'socialization', 10.0)
    srv.world.npc_sheets[npc_name] = sheet
    srv.world.npc_ids[npc_name] = str(__import__('uuid').uuid4())  # Ensure NPC has ID mapping

    # Capture broadcasts
    captured: list[dict] = []
    def fake_emit(event_name: str, payload=None, to: str | None = None, **kwargs):
        if event_name == "message" and payload is not None and to is not None:
            captured.append(payload)

    class FakeSocketIO:
        def emit(self, event_name: str, payload=None, to: str | None = None, **kwargs):
            fake_emit(event_name, payload, to=to, **kwargs)

    # Patch socketio to harmless fake (broadcast_to_room uses socketio.emit with per-sid targeting)
    monkeypatch.setattr(srv, "socketio", FakeSocketIO(), raising=True)

    before = getattr(sheet, 'socialization', 0.0)
    ok, _ = srv._npc_exec_emote(npc_name, rid, "hums a tune.")
    after = getattr(sheet, 'socialization', 0.0)

    assert ok is True
    assert after > before, f"Socialization should increase after emote (before={before}, after={after})"
    # Optional: ensure we didn't exceed 100
    
    # Validate world integrity after emote mutations
    validation_errors = srv.world.validate()
    assert validation_errors == [], f"World validation failed after emote: {validation_errors}"
    assert after <= 100.0