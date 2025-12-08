# Mission System Implementation Plan

## 1. Data Model (`server/mission_model.py`)
- [ ] Define `MissionStatus` (Enum).
- [ ] Define `Mission` class (uuid, title, desc, issuer, assignee, rewards, deadline, objectives).
- [ ] Define `Objective` base class and subclasses (`KillObjective`, `ObtainItemObjective`, `VisitRoomObjective`).
- [ ] Add `missions` dictionary to `World` class in `server/world.py`.

## 2. Service Logic (`server/mission_service.py`)
- [ ] `create_mission(...)`: Factory for new missions.
- [ ] `offer_mission(world, mission, target_sid/name)`: Handles the negotiation phase.
- [ ] `accept_mission(world, mission_id, assignee_sid/name)`: Transitions to ACTIVE.
- [ ] `check_objectives(world, mission)`: Evaluates progress.
- [ ] `process_tick(world)`: Checks deadlines and auto-fails expired missions.
- [ ] `generate_dynamic_mission(world, issuer_npc, target_player)`: Creates procedural missions.

## 3. NPC AI Integration (`server/npc_mission_logic.py`)
- [ ] `evaluate_mission_offer(npc, mission, issuer)`: Returns (bool, reason).
    - Logic: `(Reward + Relationship + Alignment) - (Risk + Effort) > Threshold`.
    - Traits: `Responsibility` (reliability), `Greed` (reward sensitivity), `Aggression` (combat preference).
- [ ] `generate_npc_mission_offer`: NPC proactively offering missions.

## 4. Commands & Routing (`server/mission_router.py`)
- [ ] `/mission list`: View active/pending missions.
- [ ] `/mission detail <id>`: View objectives/rewards.
- [ ] `/mission create ...`: (Admin/Advanced) Manual creation.
- [ ] `/mission offer <target> <id>`: Offer a created mission.
- [ ] `/mission accept <id>`: Accept an offer.

## 5. Integration
- [ ] Hook into `server.py` main loop for `process_tick`.
- [ ] Hook into `server.py` command handler.
- [ ] Add persistence to `World.to_dict`/`from_dict`.

## 6. Faction Integration
- [ ] Add `faction_min_rank` to Mission.
- [ ] Faction-based objective generation (e.g., "Sabotage rival faction").
