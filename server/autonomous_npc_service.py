"""
Autonomous NPC Service - Priority 1: Enhanced NPC Needs & Behaviors

This service implements autonomous decision-making for NPCs based on their enhanced
needs system and personality traits, inspired by Oblivion's Radiant AI.

The system works alongside the existing GOAP planner by providing more nuanced
behavioral triggers and personality-driven action selection.
"""

from typing import List, Dict, Optional
from world import World, CharacterSheet, Room
import random


def evaluate_npc_autonomy(world: World, npc_name: str, current_room_id: str) -> List[Dict]:
    """
    Make autonomous decisions for an NPC based on their enhanced needs and personality.
    
    This is the main entry point for Priority 1 autonomous behavior. It evaluates
    an NPC's current state and returns a list of potential autonomous actions they
    might take, ordered by priority.
    
    Args:
        world: The game world
        npc_name: Name of the NPC to evaluate
        current_room_id: ID of the room the NPC is currently in
        
    Returns:
        List of action dictionaries with 'tool', 'args', and 'priority' keys
        Higher priority numbers indicate more urgent actions
    """
    sheet = world.npc_sheets.get(npc_name)
    if not sheet:
        return []
    
    room = world.rooms.get(current_room_id)
    if not room:
        return []
    
    actions = []
    
    # Evaluate enhanced needs (beyond basic hunger/thirst/sleep/socialization)
    actions.extend(_evaluate_safety_needs(world, sheet, npc_name, room))
    actions.extend(_evaluate_wealth_desires(world, sheet, npc_name, room))
    actions.extend(_evaluate_social_status_needs(world, sheet, npc_name, room))
    
    # Evaluate faction combat
    actions.extend(_evaluate_faction_combat(world, sheet, npc_name, room))

    # Evaluate personality-driven behaviors
    actions.extend(_evaluate_responsibility_behaviors(world, sheet, npc_name, room))
    actions.extend(_evaluate_aggression_behaviors(world, sheet, npc_name, room))
    actions.extend(_evaluate_curiosity_behaviors(world, sheet, npc_name, room))
    
    # Sort by priority (higher priority first)
    actions.sort(key=lambda x: x.get('priority', 0), reverse=True)
    
    return actions


def _evaluate_safety_needs(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """Evaluate safety-related autonomous behaviors."""
    actions = []
    
    # If safety is low, NPCs should seek secure areas or avoid threats
    if sheet.safety < 30:
        # High priority: flee from dangerous situations
        if _has_dangerous_players_or_npcs(world, room, npc_name):
            actions.append({
                'tool': 'flee_danger',
                'args': {'reason': 'threat_avoidance'},
                'priority': 90,
                'description': f'{npc_name} seeks safety from perceived threats'
            })
        
        # Medium priority: seek safe areas (rooms with guards, friendly NPCs)
        safe_exits = _find_safe_exits(world, room)
        if safe_exits:
            actions.append({
                'tool': 'move_to_safety',
                'args': {'target_room': random.choice(safe_exits)},
                'priority': 60,
                'description': f'{npc_name} seeks a safer location'
            })
    
    return actions


def _evaluate_wealth_desires(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """Evaluate wealth accumulation behaviors based on personality and needs."""
    actions = []
    
    # NPCs with high wealth desire and low responsibility might steal
    if sheet.wealth_desire > 70 and sheet.responsibility < 40:
        valuable_objects = _find_valuable_objects_in_room(room)
        if valuable_objects and sheet.currency < 50:  # Only if actually poor
            target_obj = max(valuable_objects, key=lambda obj: getattr(obj, 'value', 0))
            actions.append({
                'tool': 'steal_object',
                'args': {'target': target_obj.display_name, 'stealth': True},
                'priority': 50 + (70 - sheet.responsibility),  # Lower responsibility = higher priority
                'description': f'{npc_name} considers taking {target_obj.display_name}'
            })
    
    # NPCs with moderate wealth desire might engage in legitimate trade
    elif sheet.wealth_desire > 50:
        # Look for trading opportunities with players or merchant NPCs
        potential_traders = _find_potential_traders(world, room, npc_name)
        if potential_traders:
            actions.append({
                'tool': 'initiate_trade',
                'args': {'target': potential_traders[0]},
                'priority': 30,
                'description': f'{npc_name} seeks trading opportunities'
            })
    
    return actions


def _evaluate_social_status_needs(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """Evaluate social status and reputation-seeking behaviors."""
    actions = []
    
    if sheet.social_status < 40:
        # Look for ways to improve reputation
        # High confidence NPCs might boast or show off
        if sheet.confidence > 60:
            actions.append({
                'tool': 'boast_achievements',
                'args': {'audience': 'room'},
                'priority': 40,
                'description': f'{npc_name} wants to impress others'
            })
        
        # Look for helping opportunities to build reputation
        players_in_need = _find_players_needing_help(world, room)
        if players_in_need:
            actions.append({
                'tool': 'offer_help',
                'args': {'target': players_in_need[0]},
                'priority': 35,
                'description': f'{npc_name} seeks to build reputation by helping'
            })
    
    return actions


def _evaluate_faction_combat(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """Evaluate faction-based combat triggers."""
    actions = []
    
    # Check if NPC belongs to a faction
    npc_faction_id = getattr(sheet, 'faction_id', None)
    if not npc_faction_id or npc_faction_id not in world.factions:
        return actions
        
    npc_faction = world.factions[npc_faction_id]
    
    # Check for rival NPCs in the room
    for other_npc_name in room.npcs:
        if other_npc_name == npc_name:
            continue
            
        other_sheet = world.npc_sheets.get(other_npc_name)
        if not other_sheet or other_sheet.is_dead or other_sheet.yielded:
            continue
            
        other_faction_id = getattr(other_sheet, 'faction_id', None)
        if not other_faction_id or other_faction_id not in world.factions:
            continue
            
        # Check if factions are rivals
        if npc_faction.is_rival(other_faction_id):
            # Found a rival!
            # High priority to attack
            
            # Insult first
            actions.append({
                'tool': 'emote',
                'args': {'message': f"insults {other_npc_name}: 'Your faction is a disgrace!'"},
                'priority': 96,
                'description': f'{npc_name} insults rival {other_npc_name}'
            })
            
            # Then attack
            actions.append({
                'tool': 'attack',
                'args': {'target': other_npc_name},
                'priority': 95, # Very high priority
                'description': f'{npc_name} attacks rival {other_npc_name}'
            })
            
    return actions


def _evaluate_responsibility_behaviors(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """
    Evaluate behaviors driven by the responsibility trait (moral compass).
    Low responsibility = more likely to break rules, high = law-abiding.
    """
    actions = []
    
    if sheet.responsibility < 30:
        # Low responsibility NPCs might engage in petty crimes
        if _witnesses_present(world, room, npc_name) < 2:  # Avoid acting with too many witnesses
            # Look for minor theft opportunities
            unguarded_items = _find_unguarded_valuable_items(room)
            if unguarded_items:
                actions.append({
                    'tool': 'petty_theft',
                    'args': {'target': unguarded_items[0].display_name},
                    'priority': 30 + (30 - sheet.responsibility),  # Lower responsibility = higher priority
                    'description': f'{npc_name} considers petty theft'
                })
    
    elif sheet.responsibility > 70:
        # High responsibility NPCs might intervene in crimes or help maintain order
        criminal_activity = _detect_criminal_activity(world, room, npc_name)
        if criminal_activity:
            actions.append({
                'tool': 'report_crime',
                'args': {'criminal': criminal_activity['perpetrator'], 'crime': criminal_activity['type']},
                'priority': 60,
                'description': f'{npc_name} feels compelled to report criminal activity'
            })
    
    return actions


def _evaluate_aggression_behaviors(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """Evaluate combat and conflict behaviors based on aggression trait."""
    actions = []
    
    if sheet.aggression > 60:
        # Aggressive NPCs might start conflicts over resources
        competitors = _find_resource_competitors(world, room, npc_name)
        if competitors and sheet.confidence > 40:  # Need some confidence to act on aggression
            actions.append({
                'tool': 'challenge_competitor',
                'args': {'target': competitors[0], 'reason': 'resource_competition'},
                'priority': 45 + (sheet.aggression - 60),
                'description': f'{npc_name} feels aggressive toward competitors'
            })
    
    elif sheet.aggression < 20:
        # Pacifist NPCs might flee from any conflict
        if _conflict_detected_in_room(room):
            actions.append({
                'tool': 'flee_conflict',
                'args': {'destination': 'anywhere_safe'},
                'priority': 70,
                'description': f'{npc_name} avoids conflict'
            })
    
    return actions


def _evaluate_curiosity_behaviors(world: World, sheet: CharacterSheet, npc_name: str, room: Room) -> List[Dict]:
    """Evaluate exploration and investigation behaviors based on curiosity."""
    actions = []
    
    if sheet.curiosity > 60:
        # Curious NPCs might investigate new objects or areas
        unexplored_objects = _find_unexplored_objects(sheet, room)
        if unexplored_objects:
            actions.append({
                'tool': 'investigate_object',
                'args': {'target': unexplored_objects[0].display_name},
                'priority': 25,
                'description': f'{npc_name} is curious about {unexplored_objects[0].display_name}'
            })
        
        # Might also explore new rooms if confident enough
        if sheet.confidence > 40:
            unexplored_exits = _find_unexplored_exits(sheet, room)
            if unexplored_exits:
                actions.append({
                    'tool': 'explore_area',
                    'args': {'direction': unexplored_exits[0]},
                    'priority': 20,
                    'description': f'{npc_name} wants to explore {unexplored_exits[0]}'
                })
    
    return actions


# Helper functions for behavioral evaluation

def _has_dangerous_players_or_npcs(world: World, room: Room, npc_name: str) -> bool:
    """Check if there are threatening entities in the room."""
    # Look for players or NPCs with high aggression or recent hostile actions
    for player_sid in room.players:
        player = world.players.get(player_sid)
        if player and _is_threatening_to_npc(player, npc_name):
            return True
    
    for other_npc in room.npcs:
        if other_npc != npc_name:
            other_sheet = world.npc_sheets.get(other_npc)
            if other_sheet and other_sheet.aggression > 70:
                return True
    
    return False


def _find_safe_exits(world: World, room: Room) -> List[str]:
    """Find exits leading to safer areas (rooms with guards, etc.)."""
    safe_exits = []
    
    # Check doors and stairs for rooms with security
    for door_name, target_room_id in (room.doors or {}).items():
        target_room = world.rooms.get(target_room_id)
        if target_room and _is_safe_room(world, target_room):
            safe_exits.append(door_name)
    
    return safe_exits


def _find_valuable_objects_in_room(room: Room) -> List:
    """Find objects in the room that have significant value."""
    valuable_objects = []
    for obj in (room.objects or {}).values():
        obj_value = getattr(obj, 'value', None)
        if obj_value is not None and obj_value > 10:  # Threshold for "valuable"
            valuable_objects.append(obj)
    return valuable_objects


def _find_potential_traders(world: World, room: Room, npc_name: str) -> List[str]:
    """Find other entities in the room who might be interested in trading."""
    traders = []
    
    # Look for players (always potential traders)
    for player_sid in room.players:
        player = world.players.get(player_sid)
        if player:
            traders.append(player.sheet.display_name)
    
    # Look for merchant NPCs or NPCs with high wealth desire
    for other_npc in room.npcs:
        if other_npc != npc_name:
            other_sheet = world.npc_sheets.get(other_npc)
            if other_sheet and (other_sheet.wealth_desire > 40 or 'merchant' in other_sheet.description.lower()):
                traders.append(other_npc)
    
    return traders


def _find_players_needing_help(world: World, room: Room) -> List[str]:
    """Find players who might need assistance (low health, etc.)."""
    # Simplified - in a full implementation, this would check player status
    players_needing_help = []
    for player_sid in room.players:
        player = world.players.get(player_sid)
        if player:
            # For now, just add all players as potential help recipients
            players_needing_help.append(player.sheet.display_name)
    return players_needing_help


def _witnesses_present(world: World, room: Room, npc_name: str) -> int:
    """Count potential witnesses to criminal activity."""
    witnesses = 0
    witnesses += len(room.players)  # All players are witnesses
    witnesses += len([npc for npc in room.npcs if npc != npc_name])  # Other NPCs
    return witnesses


def _find_unguarded_valuable_items(room: Room) -> List:
    """Find valuable items that aren't being watched."""
    # Simplified - look for valuable objects not owned by anyone present
    unguarded = []
    for obj in (room.objects or {}).values():
        obj_value = getattr(obj, 'value', None)
        if obj_value is not None and obj_value > 5 and not getattr(obj, 'owner_id', None):
            unguarded.append(obj)
    return unguarded


def _detect_criminal_activity(world: World, room: Room, npc_name: str) -> Optional[Dict]:
    """Detect if criminal activity is happening in the room."""
    # This would be expanded to actually detect crimes in progress
    # For now, return None (no crimes detected)
    return None


def _find_resource_competitors(world: World, room: Room, npc_name: str) -> List[str]:
    """Find other entities competing for the same resources."""
    competitors = []
    
    # Look for other NPCs with similar high needs
    sheet = world.npc_sheets.get(npc_name)
    if not sheet:
        return competitors
    
    for other_npc in room.npcs:
        if other_npc != npc_name:
            other_sheet = world.npc_sheets.get(other_npc)
            if other_sheet:
                # Check if they have similar urgent needs
                if (sheet.hunger < 40 and other_sheet.hunger < 40) or \
                   (sheet.thirst < 40 and other_sheet.thirst < 40):
                    competitors.append(other_npc)
    
    return competitors


def _conflict_detected_in_room(room: Room) -> bool:
    """Check if there's ongoing conflict in the room."""
    # This would be expanded to detect actual combat or arguments
    # For now, return False (no conflict detected)
    return False


def _find_unexplored_objects(sheet: CharacterSheet, room: Room) -> List:
    """Find objects the NPC hasn't investigated before."""
    # Check memories to see what objects have been investigated
    investigated_objects = set()
    for memory in sheet.memories:
        if memory.get('type') == 'investigated_object':
            investigated_objects.add(memory.get('object_name'))
    
    unexplored = []
    for obj in (room.objects or {}).values():
        if obj.display_name not in investigated_objects:
            unexplored.append(obj)
    
    return unexplored


def _find_unexplored_exits(sheet: CharacterSheet, room: Room) -> List[str]:
    """Find exits the NPC hasn't explored before."""
    # Check memories for explored areas
    explored_exits = set()
    for memory in sheet.memories:
        if memory.get('type') == 'explored_exit':
            explored_exits.add(memory.get('exit_name'))
    
    unexplored = []
    for door_name in (room.doors or {}).keys():
        if door_name not in explored_exits:
            unexplored.append(door_name)
    
    # Also check stairs
    if room.stairs_up_to and 'stairs_up' not in explored_exits:
        unexplored.append('stairs_up')
    if room.stairs_down_to and 'stairs_down' not in explored_exits:
        unexplored.append('stairs_down')
    
    return unexplored


def _is_threatening_to_npc(player, npc_name: str) -> bool:
    """Determine if a player poses a threat to the NPC."""
    # This would check player behavior, equipment, recent actions, etc.
    # For now, simplified logic
    return False


def _is_safe_room(world: World, room: Room) -> bool:
    """Determine if a room is considered safe."""
    # Look for guards, safe tags, etc.
    for npc_name in room.npcs:
        npc_sheet = world.npc_sheets.get(npc_name)
        if npc_sheet and ('guard' in npc_sheet.description.lower() or npc_sheet.responsibility > 80):
            return True
    return False


def add_memory(sheet: CharacterSheet, memory_type: str, details: Dict, max_memories: int = 50):
    """
    Add a memory to an NPC's memory system.
    
    Args:
        sheet: The NPC's character sheet
        memory_type: Type of memory ('conversation', 'witnessed_event', 'investigated_object', etc.)
        details: Dictionary of memory details
        max_memories: Maximum number of memories to keep (oldest are removed)
    """
    import time
    
    memory = {
        'type': memory_type,
        'timestamp': time.time(),
        **details
    }
    
    sheet.memories.append(memory)
    
    # Keep only the most recent memories
    if len(sheet.memories) > max_memories:
        sheet.memories = sheet.memories[-max_memories:]


def update_relationship(sheet: CharacterSheet, target_id: str, change: float):
    """
    Update relationship score with another entity.
    
    Args:
        sheet: The NPC's character sheet
        target_id: ID of the player or NPC
        change: Change in relationship (-100 to +100)
    """
    current = sheet.relationships.get(target_id, 0.0)
    new_value = max(-100.0, min(100.0, current + change))
    sheet.relationships[target_id] = new_value


def get_personality_modifier(sheet: CharacterSheet, trait: str) -> float:
    """
    Get a modifier based on personality trait for decision-making.
    
    Args:
        sheet: The NPC's character sheet
        trait: Name of the trait ('responsibility', 'aggression', 'confidence', 'curiosity')
        
    Returns:
        Float modifier from -1.0 to +1.0 based on trait value
    """
    trait_value = getattr(sheet, trait, 50)
    # Convert 0-100 scale to -1.0 to +1.0 modifier
    return (trait_value - 50) / 50.0