import time
import uuid
import random
from typing import List, Tuple, Optional, Dict, Any

from mission_model import (
    Mission, MissionStatus, Objective, 
    KillObjective, ObtainItemObjective, VisitRoomObjective
)
from world import World, CharacterSheet, Object

# Constants
MISSION_OFFER_TIMEOUT = 300  # 5 minutes

def create_mission(
    world: World,
    title: str,
    description: str,
    issuer_id: str,
    objectives: List[Objective],
    rewards: Dict[str, Any] = None,
    deadline_seconds: Optional[int] = None,
    min_faction_rank: Optional[str] = None,
    faction_id: Optional[str] = None
) -> Mission:
    """Factory to create and register a new mission."""
    rewards = rewards or {}
    
    deadline = None
    if deadline_seconds:
        deadline = time.time() + deadline_seconds

    mission = Mission(
        title=title,
        description=description,
        issuer_id=issuer_id,
        objectives=objectives,
        reward_currency=rewards.get('currency', 0),
        reward_xp=rewards.get('xp', 0),
        reward_items=rewards.get('items', []),
        reward_faction_id=rewards.get('faction_id'),
        reward_faction_rep=rewards.get('faction_rep', 0),
        deadline=deadline,
        min_faction_rank=min_faction_rank,
        faction_id=faction_id,
        status=MissionStatus.PENDING
    )
    
    world.missions[mission.uuid] = mission
    return mission

def offer_mission(world: World, mission_id: str, target_sid: str) -> Tuple[bool, str | None, List[dict]]:
    """Offer a mission to a player (by SID)."""
    mission = world.missions.get(mission_id)
    if not mission:
        return False, "Mission not found.", []
    
    if mission.status != MissionStatus.PENDING:
        return False, f"Mission is currently {mission.status.value}.", []

    player = world.players.get(target_sid)
    if not player:
        return False, "Target player not found.", []

    # Construct the offer message
    reward_text = []
    if mission.reward_currency:
        reward_text.append(f"{mission.reward_currency} coins")
    if mission.reward_xp:
        reward_text.append(f"{mission.reward_xp} XP")
    if mission.reward_faction_rep and mission.reward_faction_id:
        fname = "Faction"
        f = world.factions.get(mission.reward_faction_id)
        if f:
            fname = f.name
        reward_text.append(f"{mission.reward_faction_rep} rep with {fname}")
    
    r_str = ", ".join(reward_text) if reward_text else "Gratitude"

    emits = [
        {
            'type': 'system',
            'content': f"\n[b]MISSION OFFERED: {mission.title}[/b]\n"
                       f"{mission.description}\n"
                       f"[b]Rewards:[/b] {r_str}\n"
                       f"Type [color=#00FF00]/mission accept {mission.uuid}[/color] to accept.\n"
        }
    ]
    
    return True, None, emits

def accept_mission(world: World, mission_id: str, assignee_id: str) -> Tuple[bool, str | None, List[dict]]:
    """Transition mission to ACTIVE and assign to assignee (User ID or NPC ID)."""
    mission = world.missions.get(mission_id)
    if not mission:
        return False, "Mission not found.", []
    
    if mission.status != MissionStatus.PENDING:
        return False, f"Mission is already {mission.status.value}.", []
        
    mission.status = MissionStatus.ACTIVE
    mission.assignee_id = assignee_id
    
    emits = [
        {
            'type': 'system',
            'content': f"You have accepted the mission: [b]{mission.title}[/b]. Check /mission detail {mission.uuid} for objectives."
        }
    ]
    return True, None, emits

def update_objective_progress(world: World, mission: Mission, objective_index: int, amount: int = 1) -> bool:
    """Update progress on a specific objective."""
    if mission.status != MissionStatus.ACTIVE:
        return False
        
    if 0 <= objective_index < len(mission.objectives):
        obj = mission.objectives[objective_index]
        if not obj.completed:
            obj.current_count += amount
            if obj.current_count >= obj.target_count:
                obj.current_count = obj.target_count
                obj.completed = True
                # Check if all completed
                if all(o.completed for o in mission.objectives):
                    complete_mission(world, mission)
            return True
    return False

def complete_mission(world: World, mission: Mission):
    """Handle mission completion logic (rewards)."""
    mission.status = MissionStatus.COMPLETED
    # Note: Actual reward distribution usually happens when the player 'turns in' the mission
    # or immediately upon completion depending on design.
    # For now, we just mark it completed. The controller/router should handle giving rewards.

def process_tick(world: World) -> List[str]:
    """Check deadlines. Returns list of failed mission UUIDs."""
    failed_ids = []
    now = time.time()
    
    for mission in list(world.missions.values()):
        if mission.status == MissionStatus.ACTIVE:
            if mission.deadline and now > mission.deadline:
                mission.status = MissionStatus.FAILED
                failed_ids.append(mission.uuid)
                
    return failed_ids

def generate_dynamic_mission(world: World, issuer_npc_name: str, target_player_level: int = 1) -> Optional[Mission]:
    """Generate a simple procedural mission from an NPC."""
    issuer_id = world.get_or_create_npc_id(issuer_npc_name)
    
    # Simple template: Fetch Item
    # 1. Pick a random item template
    if not world.object_templates:
        return None
        
    target_item_key = random.choice(list(world.object_templates.keys()))
    target_template = world.object_templates[target_item_key]
    
    title = f"Retrieve {target_template.display_name}"
    desc = f"I need a {target_template.display_name} for my work. Can you find one for me?"
    
    obj = ObtainItemObjective(
        description=f"Obtain 1 {target_template.display_name}",
        target_id=target_item_key, # Using template key as target ID for now
        target_count=1
    )
    
    rewards = {
        'currency': random.randint(10, 50) * target_player_level,
        'xp': 100 * target_player_level
    }
    
    return create_mission(
        world=world,
        title=title,
        description=desc,
        issuer_id=issuer_id,
        objectives=[obj],
        rewards=rewards,
        deadline_seconds=3600 # 1 hour
    )

def generate_faction_mission(world: World, faction_id: str, target_player_level: int = 1) -> Optional[Mission]:
    """Generate a mission for a specific faction."""
    faction = world.factions.get(faction_id)
    if not faction:
        return None
        
    # Fallback: Fetch supplies for the faction
    if not world.object_templates:
        return None
        
    target_item_key = random.choice(list(world.object_templates.keys()))
    target_template = world.object_templates[target_item_key]
    
    title = f"Supplies for {faction.name}"
    desc = f"We need {target_template.display_name} to support our operations. Bring one to us."
    
    obj = ObtainItemObjective(
        description=f"Obtain 1 {target_template.display_name}",
        target_id=target_item_key,
        target_count=1
    )
    
    rewards = {
        'currency': random.randint(20, 100) * target_player_level,
        'xp': 150 * target_player_level,
        'faction_id': faction_id,
        'faction_rep': 10
    }
    
    # Issuer? Maybe the faction leader?
    issuer_id = faction.leader_player_id or "system"
    
    return create_mission(
        world=world,
        title=title,
        description=desc,
        issuer_id=issuer_id,
        objectives=[obj],
        rewards=rewards,
        deadline_seconds=7200, # 2 hours
        faction_id=faction_id
    )

def handle_mission_admin_command(world: World, args: List[str]) -> Tuple[bool, str | None, List[dict]]:
    """Handle admin subcommands for missions."""
    if not args:
        return False, "Usage: /mission <listall|delete|create|setstatus> ...", []

    sub = args[0].lower()
    sub_args = args[1:]
    emits = []

    if sub == 'listall':
        lines = ["[b]All World Missions:[/b]"]
        if not world.missions:
            lines.append("No missions found.")
        else:
            for m in world.missions.values():
                lines.append(f"- [{m.status.value.upper()}] {m.title} (ID: {m.uuid})")
        emits.append({'type': 'system', 'content': "\n".join(lines)})
        return True, None, emits

    if sub == 'delete':
        if not sub_args:
            return True, "Usage: /mission delete <mission_uuid>", []
        mid = sub_args[0]
        if mid in world.missions:
            del world.missions[mid]
            emits.append({'type': 'system', 'content': f"Mission {mid} deleted."})
        else:
            return True, "Mission not found.", []
        return True, None, emits

    if sub == 'create':
        # /mission create <title> | <description>
        parts = " ".join(sub_args).split("|")
        if len(parts) < 2:
            return True, "Usage: /mission create <title> | <description>", []
        
        title = parts[0].strip()
        desc = parts[1].strip()
        
        # Create a dummy objective so it's valid
        obj = Objective(description="Manual Objective", type="generic", target_count=1)
        
        mission = create_mission(
            world=world,
            title=title,
            description=desc,
            issuer_id="admin",
            objectives=[obj]
        )
        emits.append({'type': 'system', 'content': f"Mission created. ID: {mission.uuid}"})
        return True, None, emits

    if sub == 'setstatus':
        # /mission setstatus <uuid> | <status>
        parts = " ".join(sub_args).split("|")
        if len(parts) < 2:
            return True, "Usage: /mission setstatus <uuid> | <status>", []
            
        mid = parts[0].strip()
        status_str = parts[1].strip().lower()
        
        mission = world.missions.get(mid)
        if not mission:
            return True, "Mission not found.", []
            
        try:
            # Map simplified status strings if needed, or rely on enum
            # Enum values are 'pending', 'active', 'completed', 'failed', 'expired'
            new_status = MissionStatus(status_str)
            mission.status = new_status
            emits.append({'type': 'system', 'content': f"Mission {mid} status set to {new_status.value}."})
        except ValueError:
            valid = [s.value for s in MissionStatus]
            return True, f"Invalid status. Valid: {', '.join(valid)}", []
            
        return True, None, emits

    return False, None, []
