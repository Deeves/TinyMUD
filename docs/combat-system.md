# Combat System Overview

This document introduces the initial combat implementation (Attack verb, morale, permadeath).

## Core Concepts
- **Attack Verb**: Players (and future NPC AI) use `/attack <target>` to deal damage. Damage = `max(1, strength // 2)` as an early placeholder.
- **Hit Points**: Existing `hp` / `max_hp` fields on `CharacterSheet` are used. `hp` reaching 0 sets `is_dead = True` (permadeath for players).
- **Permadeath**: A dead player cannot execute most commands (only `/help`, `/who`, `/look`). They must create a new character.
- **Morale**: New `morale` (0-100). Lower values and low HP increase chance an NPC yields.
- **Yielding**: NPCs may set `yielded = True` when morale conditions fail. Yielded NPCs stop fighting; attacks against them still succeed but they won't retaliate.
- **Death Flag**: `is_dead` persists in save data. For NPCs we keep the sheet for historical reference but remove the name from the room's `npcs` set.

## New Fields (CharacterSheet)
- `morale: int = 50`
- `yielded: bool = False`
- `is_dead: bool = False`

## Migration
`Migration005_CombatStats` backfills missing combat fields in older saves with defaults.

## Router / Service Pattern
- `/attack` routed via `combat_router.py` → `combat_service.attack(...)`.
- Service returns `(handled, err, emits, broadcasts)`.
- Router emits attacker messages and broadcasts to the current room.

## Morale / Yield Logic
Trigger after a successful hit on an NPC:
1. If `hp <= 30% max_hp` OR morale roll fails.
2. Morale roll = `rand(1,100) + morale + confidence - aggression`.
3. If (low HP) OR (roll < 50) ⇒ set `yielded = True` and broadcast surrender.

## Weapon and Armor Modifiers
- **Weapon Damage**: If a player or NPC has an equipped weapon (`equipped_weapon` field), its `weapon_damage` value is added to base damage.
- **Armor Defense**: If a target has equipped armor (`equipped_armor` field), its `armor_defense` value reduces incoming damage (minimum 1).
- **Calculation**: Damage = `max(1, strength // 2 + weapon_damage - armor_defense)`.
- **Object Fields**: Weapon objects use `weapon_damage` and `weapon_type`; armor uses `armor_defense` and `armor_type`.

## Flee Command
- **Usage**: `/flee` allows a player or NPC to escape combat by moving to a random adjacent room (via doors, stairs, or travel objects).
- **Restrictions**: Cannot flee if dead or yielded.
- **Implementation**: Flee command is routed via `combat_router.py` → `combat_service.flee(...)`. Player is moved to a linked room and notified.

## Extensibility Hooks
Future improvements could include:
- Weapon items adding damage modifiers.
- Armor / resistances reducing incoming damage.
- Status effects (bleeding, stunned) tracked on sheet.
- Structured morale system factoring recent events and faction support.
- NPC AI to choose targets or flee when yielded.

## Command Gating
In `server.py` inside `handle_command`, dead players are barred from most commands to enforce permadeath philosophy.

## Testing
`test_combat_attack.py` covers:
- Attack reduces HP and causes death.
- NPC may yield or die based on low HP/morale.
- Weapon and armor effects on damage calculation.
- Flee command moves player to adjacent room and sends appropriate messages.

## Safety & Robustness
- World save wrapped with `safe_call` in combat_service.
- Fuzzy target resolution prevents ambiguous target selection and returns helpful errors.

---

"Fight bravely, or flee wisely—your fate is in your hands."