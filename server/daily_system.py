# Daily System: Manages Time, Roles, and Contracts
import time
import logging
import uuid
from typing import List, Optional

from world import World
from role_model import FactionRole
from world import World
from role_model import FactionRole
from mission_model import Mission, MissionStatus, ObtainItemObjective, Objective
import ambition_service

# Constants
DAY_LENGTH_TICKS = 24  # 24 ticks = 1 game day (at 60s/tick = 24 minutes)

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
    # Note: efficient lookup would require an index, doing linear scan for MVP
    if not hasattr(world, 'missions'):
         world.missions = {}

    for mission in world.missions.values():
        if (mission.assignee_id == member_id and 
            mission.faction_id == faction_id and 
            mission.status == MissionStatus.ACTIVE):
            
            # It's a new day, so any active daily mission is now FAILED
            # (Assuming daily missions must be done same day. 
            #  Could check 'deadline' field too, but simpler logic: New Day = Deadline passed)
            
            print(f"[Daily System] Member {member_id} failed mission {mission.uuid}")
            mission.status = MissionStatus.FAILED
            
            # Apply Consequence: Rep Loss / Chew Out
            _apply_failure_consequence(world, member_id, faction_id, mission, broadcast_func)

def _apply_failure_consequence(world: World, member_id: str, faction_id: str, mission: Mission, broadcast_func=None):
    """Punish the slacker."""
    faction = world.factions.get(faction_id)
    if not faction: return
    
    # 1. Rep Loss (Simple implementation)
    # Using social_status as proxy for standing since Faction doesn't track per-member rep numerically yet
    # Also look for the player/NPC to deduct
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
        sheet = world.npc_sheets.get(member_id) # member_id might be npc name or uuid?
        # Faction system currently uses npc_id (UUID). Need to resolve to sheet.
        # But npc_sheets is by Name. 
        # Ideally we map UUID -> Name. world.npc_ids maps Name -> UUID.
        # Reverse lookup for MVP:
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
        fail_msg = f"You failed to complete '{mission.title}' for {faction.name}. Your standing has decreased."
        if player_sid:
            # Send specific message to player
            if broadcast_func:
                # We can hack a directed message via broadcast_func if it supports 'to' 
                # or just rely on the implementation. 
                # If broadcast_func is generic broadcast_to_all, this spams everyone.
                # Better: daily_system creates a notification event we can pick up? 
                # For MVP, just print to console or use broadcast if generic.
                pass 
                # Actually, can't easily send private message without `emit` access here.
                # Just log for now.
                print(f"Player {sheet.display_name} notified of failure.")
        elif sheet:
            # NPC Grumble?
            pass

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
        # Visit a room
        # For MVP, generic "Visit HQ"
        obj = Objective(description="Report for duty", type="visit", target_count=1)
        mission.objectives.append(obj)
        
    # Rewards
    mission.reward_faction_rep = config.get("reward_rep", 5)
    mission.reward_currency = config.get("reward_currency", 10)
    
    # Save to world
    if not hasattr(world, 'missions'):
        world.missions = {}
    world.missions[mission.uuid] = mission
    
    print(f"[Daily System] Assigned {mission.title} to {member_id}")
