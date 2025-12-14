# Daily System: Manages Time, Roles, and Contracts
import time
import logging
import uuid
import random
from typing import List, Optional

from world import World
from role_model import FactionRole
from mission_model import Mission, MissionStatus, ObtainItemObjective, Objective, VisitRoomObjective
import ambition_service

# Constants
DAY_LENGTH_TICKS = 24  # 24 ticks = 1 game day (at 60s/tick = 24 minutes)

# Default Hourly Descriptions (0-23)
HOURLY_DESCRIPTIONS = {
    0: "The moon hangs high in the midnight sky.",
    1: "A deep stillness settles over the world in the witching hour.",
    2: "The stars shine brightly in the pitch-black sky.",
    3: "A faint chill permeates the air before dawn.",
    4: "The horizon begins to pale with the promise of day.",
    5: "The birds begin to stir as the sky turns grey.",
    6: "The first light of dawn breaks over the horizon.",
    7: "The morning sun casts long shadows across the land.",
    8: "The world is fully awake and bustling with morning energy.",
    9: "The sun climbs higher, warming the earth.",
    10: "The day is bright and the sky is a clear azure.",
    11: "The sun approaches its zenith, casting short shadows.",
    12: "The sun hangs directly overhead in the noon sky.",
    13: "The afternoon sun beats down with intensity.",
    14: "The heat of the day persists in the early afternoon.",
    15: "The sun begins its slow descent towards the west.",
    16: "Golden hour approaches as the light softens.",
    17: "Long shadows return as evening draws near.",
    18: "The sun touches the horizon, painting the sky in orange and red.",
    19: "Twilight falls, blurring the lines between day and night.",
    20: "The last traces of daylight fade into the west.",
    21: "Darkness claims the sky, and the stars emerge.",
    22: "The night deepens, wrapping the world in shadow.",
    23: "The world is quiet under the starlit canopy."
}

def get_game_time_string(world: World) -> str:
    """Return a prose description of the current time of day."""
    if not hasattr(world, 'game_time_ticks'):
        return ""
    
    # Calculate hour (assuming 1 tick = 1 hour for simplicity in this prose mapping, 
    # though valid ticks might be faster. The constant DAY_LENGTH_TICKS is 24, so 1 tick = 1 hour is correct.)
    hour = world.game_time_ticks % DAY_LENGTH_TICKS
    
    # Check if world has custom overrides (persisted time descriptions)
    # Use a safe attribute access or default to global constant
    descriptions = getattr(world, 'time_descriptions', HOURLY_DESCRIPTIONS)
    
    # Fallback to default if key missing in custom dict
    desc = descriptions.get(hour, HOURLY_DESCRIPTIONS.get(hour, "Time passes."))
    
    return f"\n\nIt is currently {hour}:00. {desc}"


def process_daily_cycle(world: World, broadcast_func=None):
    """Called every tick to check if a new day has dawned."""
    
    # 1. Increment Game Time
    if not hasattr(world, 'game_time_ticks'):
        world.game_time_ticks = 0
    
    world.game_time_ticks += 1
    
    # 2. Check for New Day
    if world.game_time_ticks % DAY_LENGTH_TICKS == 0:
        _start_new_day(world, broadcast_func)

def _start_new_day(world: World, broadcast_func=None):
    """Perform end-of-day calculations and start new day."""
    msg = f"[Daily System] A new day dawns! (Tick {world.game_time_ticks})"
    print(msg)
    if broadcast_func:
        broadcast_func({'type': 'system', 'content': f"[b]A new day has dawned![/b] (Day {world.game_time_ticks // DAY_LENGTH_TICKS})"})
    
    # 3. Evaluate Yesterday's Contracts & Generate Today's
    # Iterate all factions
    for faction in world.factions.values():
        # Iterate all members with roles
        for member_id, role_id in faction.member_roles.items():
            role = faction.roles.get(role_id)
            if not role:
                continue
                
            # A) Resolve previous contracts for this member
            _resolve_outstanding_contracts(world, member_id, faction.faction_id, broadcast_func)
            
            # B) Generate new contract
            _assign_daily_contract(world, faction, member_id, role, broadcast_func)
            
    # 4. Epiphany Cycle (Self-Actualization)
    print(f"[Daily System] Running Epiphany Cycle for {len(world.npc_sheets)} NPCs...")
    for npc_name in world.npc_sheets:
        try:
            ambition_service.evaluate_epiphany(world, npc_name)
        except Exception as e:
            print(f"[Daily System] Error in Epiphany for {npc_name}: {e}")

    world.daily_update_timestamp = time.time()

def _resolve_outstanding_contracts(world: World, member_id: str, faction_id: str, broadcast_func=None):
    """Check for active daily missions from this faction and fail them if expired."""
    # Find active missions assigned to this member from this faction
    # Use O(1) index if available, else fallback
    if hasattr(world, 'missions_by_assignee'):
        mission_uuids = world.missions_by_assignee.get(member_id, set())
        # Copy to list to avoid runtime error if we modify index during iteration (though remove logic usually handles this safely)
        for mid in list(mission_uuids):
            mission = world.missions.get(mid)
            if (mission and 
                mission.faction_id == faction_id and 
                mission.status == MissionStatus.ACTIVE):
                
                print(f"[Daily System] Member {member_id} failed mission {mission.uuid}")
                mission.status = MissionStatus.FAILED
                
                # Apply Consequence
                _apply_failure_consequence(world, member_id, faction_id, mission, broadcast_func)
    else:
        # Fallback linear scan
        if not hasattr(world, 'missions'):
             world.missions = {}
        for mission in world.missions.values():
            if (mission.assignee_id == member_id and 
                mission.faction_id == faction_id and 
                mission.status == MissionStatus.ACTIVE):
                
                print(f"[Daily System] Member {member_id} failed mission {mission.uuid}")
                mission.status = MissionStatus.FAILED
                _apply_failure_consequence(world, member_id, faction_id, mission, broadcast_func)

def _apply_failure_consequence(world: World, member_id: str, faction_id: str, mission: Mission, broadcast_func=None):
    """Punish the slacker."""
    faction = world.factions.get(faction_id)
    if not faction: return
    
    # 1. Rep Loss (Simple implementation)
    sheet = None
    player_sid = None
    
    # Resolve sheet
    if member_id in world.users:
        user = world.users[member_id]
        sheet = user.sheet
        # Find active session for broadcast
        for sid, p in world.players.items():
            if p.sheet and p.sheet.display_name == user.display_name:
                player_sid = sid
                break
    else:
        # NPC
        sheet = world.npc_sheets.get(member_id) # maybe it's a name?
        if not sheet:
            # Try UUID lookup
            # Optimized reverse lookup
            if hasattr(world, 'npc_ids_reverse'):
                name = world.npc_ids_reverse.get(member_id)
                if name:
                    sheet = world.npc_sheets.get(name)
            else:
                # Fallback linear
                for name, uuid in world.npc_ids.items():
                    if uuid == member_id:
                        sheet = world.npc_sheets.get(name)
                        break
    
    if sheet:
        # Deduct status
        old_status = sheet.social_status
        sheet.social_status = max(0, sheet.social_status - 5)
        
        # Add a negative memory
        sheet.memories.append({
            'type': 'contract_failed',
            'faction': faction.name,
            'mission': mission.title,
            'timestamp': time.time()
        })
        
        # Messaging
        if player_sid and broadcast_func:
            pass # messaging logic
            print(f"Player {sheet.display_name} notified of failure.")

def _assign_daily_contract(world: World, faction, member_id: str, role: FactionRole, broadcast_func=None):
    """Create a new mission based on the role."""
    
    mission = Mission(
        title=f"Daily Duty: {role.name}",
        description=f"Standard daily quota for {role.name}. {role.description}",
        issuer_id=faction.faction_id, # Faction itself issues it
        assignee_id=member_id,
        faction_id=faction.faction_id,
        status=MissionStatus.ACTIVE,
        deadline=time.time() + (DAY_LENGTH_TICKS * 60) # Approx deadlines
    )
    
    # Configure Objectives based on Role Type
    config = role.contract_config
    if role.contract_type == "resource_contribution":
        # e.g., "Obtain 5 Stone"
        target_item_name = config.get("resource_tag", "stone") # Using tag or name
        count = config.get("amount", 3)
        
        # We assume target_id is a tag or name for generic obtain
        obj = ObtainItemObjective(
            description=f"Obtain {count} {target_item_name}",
            target_id=target_item_name, 
            target_count=count
        )
        mission.objectives.append(obj)
        
    elif role.contract_type == "patrol":
        # Visit a random room
        target_room_id = None
        target_room_name = "Unknown Location"
        
        if world.rooms:
            # Pick any room (for MVP)
            # Ideal: Pick a room in faction territory or connected area
            # Just random for now
            rid = random.choice(list(world.rooms.keys()))
            target_room_id = rid
            target_room = world.rooms[rid]
            # Try to get a nice name? Room doesn't have a 'name' field, just description and id.
            # ID is often not human readable. 
            # We can use First line of description or ID if simple.
            # actually we can just say "Patrol designated area" and give ID in debug.
            # or try to extract a name mechanism if one existed.
            target_room_name = target_room.id # Usually user-friendly handle
            
        obj = VisitRoomObjective(
            description=f"Patrol {target_room_name}",
            target_id=target_room_id,
            target_count=1
        )
        mission.objectives.append(obj)
        
    # Rewards
    mission.reward_faction_rep = config.get("reward_rep", 5)
    mission.reward_currency = config.get("reward_currency", 10)
    
    # Save to world
    if not hasattr(world, 'missions'):
        world.missions = {}
    world.missions[mission.uuid] = mission
    
    # Update Index
    if hasattr(world, 'missions_by_assignee'):
        if member_id not in world.missions_by_assignee:
            world.missions_by_assignee[member_id] = set()
        world.missions_by_assignee[member_id].add(mission.uuid)
    
    print(f"[Daily System] Assigned {mission.title} to {member_id}")
