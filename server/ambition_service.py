import random
from typing import List, Dict, Optional
from world import World, CharacterSheet, Object
from ambition_model import Ambition, Milestone

# Constants
MASLOW_GATE_THRESHOLD = 30.0 # Needs must be above this to pursue ambitions

def check_maslow_gate(sheet: CharacterSheet) -> bool:
    """
    Returns True if the NPC's basic needs are met sufficiently to pursue self-actualization.
    """
    if sheet.hunger < MASLOW_GATE_THRESHOLD:
        return False
    if sheet.thirst < MASLOW_GATE_THRESHOLD:
        return False
    if sheet.safety < MASLOW_GATE_THRESHOLD:
        return False
    if sheet.sleep < MASLOW_GATE_THRESHOLD:
        return False
    return True

def generate_ambition(sheet: CharacterSheet) -> Ambition:
    """
    Generate a suitable ambition based on NPC traits.
    """
    # Simple logic based on highest traits
    if sheet.wealth_desire > 70:
        return _create_wealth_ambition(sheet)
    elif sheet.aggression > 60:
        return _create_warlord_ambition(sheet)
    elif sheet.curiosity > 60:
        return _create_explorer_ambition(sheet)
    elif sheet.social_status > 60:
        return _create_political_ambition(sheet)
    else:
        # Default fallback
        return _create_peacekeeper_ambition(sheet)

def _create_wealth_ambition(sheet: CharacterSheet) -> Ambition:
    return Ambition(
        name="Merchant Tycoon",
        description="I want to amass a fortune.",
        milestones=[
            Milestone("Earn first 100 gold", "currency", 100),
            Milestone("Earn 500 gold", "currency", 500),
            Milestone("Earn 1000 gold", "currency", 1000)
        ]
    )

def _create_warlord_ambition(sheet: CharacterSheet) -> Ambition:
    return Ambition(
        name="Warlord",
        description="I want to prove my strength in combat.",
        milestones=[
            Milestone("Win a duel", "stat_combat_wins", 1),
            Milestone("Defeat 3 enemies", "stat_combat_wins", 3),
            Milestone("Become a Faction Guard", "role", "Guard")
        ]
    )

def _create_explorer_ambition(sheet: CharacterSheet) -> Ambition:
    return Ambition(
        name="Master Explorer",
        description="I want to see the world.",
        milestones=[
            Milestone("Visit 5 different rooms", "stat_rooms_visited", 5),
            Milestone("Find a rare artifact", "item_tag", "rare"),
            Milestone("Visit 10 different rooms", "stat_rooms_visited", 10)
        ]
    )

def _create_political_ambition(sheet: CharacterSheet) -> Ambition:
    return Ambition(
        name="High Society",
        description="I want to be respected by everyone.",
        milestones=[
            Milestone("Make 3 friends", "stat_friends_made", 3),
            Milestone("Host a party", "action", "host_party"),
            Milestone("Become Faction Leader", "role", "Leader")
        ]
    )

def _create_peacekeeper_ambition(sheet: CharacterSheet) -> Ambition:
    return Ambition(
        name="Peacekeeper",
        description="I want to ensure safety for my community.",
        milestones=[
            Milestone("Patrol 3 times", "stat_patrols", 3),
            Milestone("Stop a crime", "stat_crimes_stopped", 1),
            Milestone("Be thanked by a player", "stat_thanks_received", 1)
        ]
    )

def evaluate_epiphany(world: World, npc_name: str):
    """
    Run the Epiphany Cycle: Check life satisfaction and progress ambition.
    """
    sheet = world.npc_sheets.get(npc_name)
    if not sheet:
        return

    # 1. Check Maslow Gate
    if not check_maslow_gate(sheet):
        # Too stressed to think about dreams
        return

    # 2. Assign Ambition if missing
    if not sheet.ambition:
        sheet.ambition = generate_ambition(sheet)
        # Log/Notify could happen here
        return
    
    # 3. Check Progress
    milestone = sheet.ambition.get_current_milestone()
    if not milestone:
        # Completed all milestones!
        return

def check_milestone_progress(world: World, sheet: CharacterSheet, milestone: Milestone) -> bool:
    """
    Check if a specific milestone has been completed based on its target type and value.
    """
    if milestone.completed:
        return True

    # 1. Currency
    if milestone.target_type == 'currency':
        if sheet.currency >= milestone.target_value:
            return True

    # 2. Stats (Generic stat lookup in sheet.stats or similar)
    elif milestone.target_type.startswith('stat_'):
        stat_name = milestone.target_type  # e.g., 'stat_combat_wins'
        # Assume character sheet has a stats dict for tracking lifetime accumulators
        if not hasattr(sheet, 'lifetime_stats'):
            sheet.lifetime_stats = {}
        
        current_val = sheet.lifetime_stats.get(stat_name, 0)
        # Handle string target values if legacy, but usually stats are ints
        try:
            target_val = int(milestone.target_value)
            if current_val >= target_val:
                return True
        except (ValueError, TypeError):
            pass

    # 3. Item Tags (Checking inventory)
    elif milestone.target_type == 'item_tag':
        required_tag = str(milestone.target_value).lower()
        # Scan inventory
        for item in sheet.inventory.slots:
            if item:
                # Check tags
                tags = [t.lower() for t in getattr(item, 'object_tags', [])]
                if required_tag in tags:
                    return True

    # 4. Role (Faction Rank/Role)
    elif milestone.target_type == 'role':
        required_role = str(milestone.target_value).lower()
        # Check faction membership and rank
        if sheet.faction_id:
            faction = world.factions.get(sheet.faction_id)
            if faction:
                # Check explicit role assignment
                # (Assuming faction.member_roles maps npc_id -> role_id)
                member_role_id = faction.member_roles.get(world.get_or_create_npc_id(sheet.display_name))
                if member_role_id:
                    role_obj = faction.roles.get(member_role_id)
                    if role_obj and role_obj.name.lower() == required_role:
                        return True
                
                # Also check Rank (legacy simple string rank)
                member_rank = faction.get_member_rank(world.get_or_create_npc_id(sheet.display_name))
                if member_rank and member_rank.lower() == required_role:
                    return True
                    
    # 5. Actions (Checked via history/memories)
    elif milestone.target_type == 'action':
        required_action = str(milestone.target_value)
        # Check memories for performed action
        # Memory format: {'type': 'action_performed', 'action_name': 'host_party', ...}
        for mem in sheet.memories:
            if mem.get('type') == 'action_performed' and mem.get('action_name') == required_action:
                return True

    return False

def evaluate_epiphany(world: World, npc_name: str):
    """
    Run the Epiphany Cycle: Check life satisfaction and progress ambition.
    """
    sheet = world.npc_sheets.get(npc_name)
    if not sheet:
        return

    # 1. Check Maslow Gate
    if not check_maslow_gate(sheet):
        # Too stressed to think about dreams
        return

    # 2. Assign Ambition if missing
    if not sheet.ambition:
        sheet.ambition = generate_ambition(sheet)
        # Log/Notify could happen here
        return
    
    # 3. Check Progress on Current Milestone
    milestone = sheet.ambition.get_current_milestone()
    if not milestone:
        # Completed all milestones! 
        # Ideally, generate a NEW ambition (Prestige Class?)
        # For now, just return
        return

    if check_milestone_progress(world, sheet, milestone):
        print(f"[Ambition] {npc_name} completed milestone: {milestone.description}")
        sheet.ambition.advance_milestone()
        # Could grant XP or happiness boost here
        sheet.socialization = min(100, sheet.socialization + 20)
        sheet.confidence = min(100, sheet.confidence + 10)

def get_ambition_actions(world: World, npc_name: str) -> List[Dict]:
    """
    Generate GOAP actions relevant to the current ambition milestone.
    """
    sheet = world.npc_sheets.get(npc_name)
    if not sheet or not sheet.ambition:
        return []

    if not check_maslow_gate(sheet):
        return []

    actions = []
    milestone = sheet.ambition.get_current_milestone()
    if not milestone:
        return []

    # Inject high-priority actions based on milestone
    if milestone.target_type == 'currency':
        # Prioritize working or trading
        actions.append({
            'tool': 'work_job', # Hypothetical general tool
            'args': {'reason': 'earn_money_for_ambition'},
            'priority': 85, # High priority, but below immediate threats (90+)
            'description': f"{npc_name} works to earn gold for their ambition."
        })
    elif milestone.target_type == 'stat_combat_wins':
         # Look for sparring partners
         actions.append({
            'tool': 'find_sparring_partner',
            'args': {},
            'priority': 80,
            'description': f"{npc_name} looks for a fight to prove their strength."
         })
    
    return actions
