from __future__ import annotations

"""Tests for offline nutrition parsing and simple planner behavior.

Covers:
- _nutrition_from_tags_or_fields correctly preferring numeric tags and not
  falling back when a tag key exists without a number.
- _npc_offline_plan chooses get/consume actions for drinkable items when thirst
  is below threshold.
"""

from world import Object as WObject


def _make_obj(name: str, tags: set[str] | None = None, sv: int = 0, hv: int = 0):
  o = WObject(display_name=name, description="", object_tags=set(tags or set()))
  o.satiation_value = sv
  o.hydration_value = hv
  if not getattr(o, 'uuid', None):
    o.uuid = name + "-uuid"
  return o


def test_nutrition_prefers_tags_and_handles_missing_numbers():
    import server as srv
    # Tag numeric beats fields
    o1 = _make_obj("Water Skin", {"Drinkable: 15"}, sv=5, hv=5)
    sv, hv = srv._nutrition_from_tags_or_fields(o1)
    assert (sv, hv) == (0, 15)
    # Tag key without number should force 0 (no fallback to fields)
    o2 = _make_obj("Mysterious Soup", {"Edible"}, sv=20, hv=0)
    sv2, hv2 = srv._nutrition_from_tags_or_fields(o2)
    assert (sv2, hv2) == (0, 0)


def test_offline_plan_prefers_drink_when_thirst_low(monkeypatch):
    import server as srv
    # Build a tiny room with one drinkable object
    from world import Room, CharacterSheet
    room = Room(id="start", description="Start room")
    water = _make_obj("Water Skin", {"Drinkable: 25"})
    room.objects[water.uuid] = water
    sheet = CharacterSheet(display_name="Innkeeper", description="NPC")
    # Make thirst low to trigger drink plan, hunger ok
    sheet.hunger = 80.0
    sheet.thirst = 0.0
    plan = srv._npc_offline_plan("Innkeeper", room, sheet)
    # Expect get_object followed by consume_object referring to the same uuid
    assert len(plan) >= 2
    assert plan[0].get("tool") == "get_object"
    assert plan[1].get("tool") == "consume_object"