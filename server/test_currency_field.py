from __future__ import annotations

from world import World, CharacterSheet


def test_currency_persists_for_users_and_npcs(tmp_path):
    w = World()
    user = w.create_user("Alice", "pw", "desc")
    user.sheet.currency = 123

    npc_name = "Merchant"
    npc_sheet = CharacterSheet(display_name=npc_name, description="Shrewd trader")
    npc_sheet.currency = 77
    w.npc_sheets[npc_name] = npc_sheet

    path = tmp_path / "world_state.json"
    w.save_to_file(str(path))

    reloaded = World.load_from_file(str(path))
    restored_user = reloaded.get_user_by_display_name("Alice")
    assert restored_user is not None
    assert restored_user.sheet.currency == 123
    assert reloaded.npc_sheets[npc_name].currency == 77


def test_currency_defaults_to_zero_for_legacy_data():
    legacy_data = {
        "display_name": "Legacy",
        "description": "An adventurer from an older save.",
        "inventory": {},
    }
    sheet = CharacterSheet.from_dict(legacy_data)
    assert sheet.currency == 0
