"""Combat service implementing the Attack verb and morale/death handling.

Service contract: functions return (handled: bool, err: str|None, emits: List[dict], broadcasts: List[Tuple[str, dict]])

High-level rules:
- Players and NPCs can /attack <target>
- Damage = max(1, attacker.strength // 2) (basic placeholder; can expand later with weapons)
- When target hp <= 0 -> is_dead True, hp clamped to 0, broadcast death message. Player permadeath: future actions gated.
- Morale check: When an NPC takes damage and hp <= 30% max_hp OR random morale roll fails -> yields (yielded True) and announces surrender.
- Yielded NPCs should not attack further (router will gate).
"""
from __future__ import annotations
import random
import time
from typing import List, Tuple, Optional

from safe_utils import safe_call
from id_parse_utils import fuzzy_resolve
from service_contract import ServiceReturn
from world import World, CharacterSheet

MESSAGE_OUT = "message"

def attack(world: World, state_path: str, attacker_sid: str, target_token: str, sessions: dict, admins: set, broadcast_to_room, emit, attacker_npc_name: str = None, room_id: str = None) -> ServiceReturn:
    """Resolve an attack command with weapon and armor modifiers.

    attacker_sid: player sid initiating attack (None if NPC).
    target_token: raw target identifier (display name or NPC name)
    broadcast_to_room: callable(room_id, payload, exclude_sid=None)
    emit: callable(event, payload)
    attacker_npc_name: optional name of NPC attacker.
    room_id: optional room_id (required if attacker is NPC).
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    if attacker_npc_name:
        sheet = world.npc_sheets.get(attacker_npc_name)
        if not sheet:
            return True, "Attacker NPC not found.", emits, broadcasts
        attacker_name = attacker_npc_name
        if not room_id:
            return True, "Room ID required for NPC attack.", emits, broadcasts
        current_room_id = room_id
    else:
        player = world.players.get(attacker_sid)
        if not player:
            return True, "Authenticate first.", emits, broadcasts
        sheet = player.sheet
        attacker_name = sheet.display_name
        current_room_id = player.room_id

    if sheet.is_dead:
        return True, "You are dead and cannot act. Create a new character.", emits, broadcasts
    if sheet.yielded:
        return True, "You have yielded; you cannot attack unless you regain morale.", emits, broadcasts

    room = world.rooms.get(current_room_id)
    if not room:
        return True, "Room not found.", emits, broadcasts

    # Build target candidate lists (players in room except attacker, NPCs in room)
    player_targets = []
    for sid, p in world.players.items():
        if p.room_id == current_room_id and sid != attacker_sid and not p.sheet.is_dead:
            player_targets.append(p.sheet.display_name)
    npc_targets = [n for n in room.npcs if n in world.npc_sheets]

    candidates = player_targets + npc_targets
    if not candidates:
        return True, "No valid targets here.", emits, broadcasts

    ok, err, resolved = fuzzy_resolve(target_token, candidates)
    if not ok:
        return True, err or "Target not found.", emits, broadcasts
    target_name = resolved

    # Determine if target is player or NPC
    target_player_sid: Optional[str] = None
    for sid, p in world.players.items():
        if p.room_id == current_room_id and p.sheet.display_name.lower() == target_name.lower():
            target_player_sid = sid
            break

    if target_player_sid:
        target_sheet = world.players[target_player_sid].sheet
        target_kind = "player"
    else:
        target_sheet = world.npc_sheets.get(target_name)
        target_kind = "npc"

    if not isinstance(target_sheet, CharacterSheet):
        return True, "Target lacks a sheet.", emits, broadcasts
    if target_sheet.is_dead:
        return True, f"{target_sheet.display_name} is already dead.", emits, broadcasts
    if target_sheet.yielded:
        return True, f"{target_sheet.display_name} has yielded and is not fighting.", emits, broadcasts

    # --- Weapon and Armor Modifiers ---
    # Get attacker's weapon
    weapon_obj = None
    if sheet.equipped_weapon:
        for obj in sheet.inventory.objects:
            if getattr(obj, 'uuid', None) == sheet.equipped_weapon:
                weapon_obj = obj
                break
    weapon_damage = getattr(weapon_obj, 'weapon_damage', None) if weapon_obj else None
    base_damage = max(1, sheet.strength // 2)
    dmg = base_damage + (weapon_damage if weapon_damage is not None else 0)

    # Get target's armor
    armor_obj = None
    if target_sheet.equipped_armor:
        for obj in target_sheet.inventory.objects:
            if getattr(obj, 'uuid', None) == target_sheet.equipped_armor:
                armor_obj = obj
                break
    armor_defense = getattr(armor_obj, 'armor_defense', None) if armor_obj else None
    dmg = max(1, dmg - (armor_defense if armor_defense is not None else 0))

    pre_hp = target_sheet.hp
    target_sheet.hp = max(0, target_sheet.hp - dmg)

    # Build combat message
    if not attacker_npc_name:
        emits.append({"type": "system", "content": f"You attack {target_sheet.display_name} for {dmg} damage (HP {pre_hp}->{target_sheet.hp})."})
    broadcasts.append((MESSAGE_OUT, {"type": "system", "content": f"{attacker_name} attacks {target_sheet.display_name} for {dmg} damage."}))

    # Log event to room
    if room:
        room.add_event({
            'type': 'violence',
            'actor_name': attacker_name,
            'target_name': target_sheet.display_name,
            'damage': dmg,
            'timestamp': time.time()
        })

    # Death check
    if target_sheet.hp <= 0:
        target_sheet.is_dead = True
        death_msg = f"{target_sheet.display_name} dies! Permadeath." if target_kind == "player" else f"{target_sheet.display_name} is slain."
        broadcasts.append((MESSAGE_OUT, {"type": "system", "content": death_msg}))
        emits.append({"type": "system", "content": death_msg})
        # If NPC, remove from room presence (keep sheet for history)
        if target_kind == "npc" and target_sheet.display_name in room.npcs:
            room.npcs.discard(target_sheet.display_name)
    else:
        # Morale yield check for NPC only
        if target_kind == "npc":
            # Trigger conditions: low HP or morale roll failure
            low_hp = target_sheet.hp <= max(1, int(target_sheet.max_hp * 0.3))
            morale_roll = random.randint(1, 100) + target_sheet.morale + target_sheet.confidence - target_sheet.aggression
            if low_hp or morale_roll < 50:  # simple threshold heuristic
                target_sheet.yielded = True
                yield_msg = f"{target_sheet.display_name} yields! They will not continue fighting."
                broadcasts.append((MESSAGE_OUT, {"type": "system", "content": yield_msg}))
                emits.append({"type": "system", "content": yield_msg})

    # Persist world (best effort)
    safe_call(world.save_to_file, None, state_path)

    return True, None, emits, broadcasts

def flee(world: World, state_path: str, sid: str, sessions: dict, admins: set, broadcast_to_room, emit) -> ServiceReturn:
    """Allow a player or NPC to flee to a random adjacent room if not dead/yielded."""
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []

    player = world.players.get(sid)
    if not player:
        return True, "Authenticate first.", emits, broadcasts
    sheet = player.sheet
    if sheet.is_dead:
        return True, "You are dead and cannot act. Create a new character.", emits, broadcasts
    if sheet.yielded:
        return True, "You have yielded and cannot flee.", emits, broadcasts

    room = world.rooms.get(player.room_id)
    if not room:
        return True, "Room not found.", emits, broadcasts

    # Find adjacent rooms via doors/stairs/links
    adjacent_ids = set()
    for obj in room.objects:
        if getattr(obj, 'link_target_room_id', None):
            adjacent_ids.add(obj.link_target_room_id)
    if not adjacent_ids:
        return True, "No exits to flee through!", emits, broadcasts

    import random
    dest_id = random.choice(list(adjacent_ids))
    if dest_id not in world.rooms:
        return True, "Destination room not found.", emits, broadcasts

    # Move player
    old_room_id = player.room_id
    player.room_id = dest_id
    emits.append({"type": "system", "content": f"You flee to {world.rooms[dest_id].display_name}."})
    broadcasts.append((MESSAGE_OUT, {"type": "system", "content": f"{sheet.display_name} flees from combat!"}))

    # Persist world
    safe_call(world.save_to_file, None, state_path)
    return True, None, emits, broadcasts

def npc_autonomous_attack(world: World, state_path: str, npc_name: str, room_id: str, broadcast_to_room, emit) -> None:
    """NPC AI: If hostile NPCs from rival factions are present, insult and attack."""
    npc_sheet = world.npc_sheets.get(npc_name)
    if not npc_sheet or npc_sheet.is_dead or npc_sheet.yielded:
        return
    room = world.rooms.get(room_id)
    if not room:
        return
    # Get this NPC's faction
    npc_faction_id = getattr(npc_sheet, 'faction_id', None)
    if not npc_faction_id or npc_faction_id not in world.factions:
        return
    npc_faction = world.factions[npc_faction_id]
    # Find rival NPCs in room
    for other_npc_name in room.npcs:
        if other_npc_name == npc_name:
            continue
        other_sheet = world.npc_sheets.get(other_npc_name)
        if not other_sheet or other_sheet.is_dead or other_sheet.yielded:
            continue
        other_faction_id = getattr(other_sheet, 'faction_id', None)
        if not other_faction_id or other_faction_id not in world.factions:
            continue
        other_faction = world.factions[other_faction_id]
        # Check if factions are rivals
        if npc_faction.is_rival(other_faction_id):
            # Insult
            insult_msg = f"{npc_name} insults {other_npc_name}: 'Your faction is a disgrace!'"
            broadcast_to_room(room_id, {"type": "npc", "content": insult_msg, "name": npc_name})
            # Attack
            # NPC attacks other NPC
            attack(world, state_path, None, other_npc_name, {}, set(), broadcast_to_room, emit, attacker_npc_name=npc_name, room_id=room_id)
            # Other NPC may retaliate (optional: could add logic for counterattack)
            break
