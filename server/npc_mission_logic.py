from typing import Tuple
from mission_model import Mission, KillObjective, ObtainItemObjective, VisitRoomObjective
from world import World, CharacterSheet

def evaluate_mission_offer(
    world: World, 
    npc_sheet: CharacterSheet, 
    mission: Mission, 
    issuer_id: str
) -> Tuple[bool, str]:
    """
    Decide if an NPC accepts a mission offer.
    Returns (accepted, reason_message).
    """
    
    # 1. Calculate Perceived Reward Value
    # Base value: 1 coin = 1 point. 1 XP = 0.1 point.
    reward_score = mission.reward_currency + (mission.reward_xp * 0.1)
    
    # Faction Rep value
    if mission.reward_faction_id:
        # If NPC is in that faction, rep is valuable.
        # We need to check NPC factions.
        # For now, assume generic value of 2 points per rep.
        reward_score += mission.reward_faction_rep * 2.0

    # Adjust for Greed (Wealth Desire)
    # wealth_desire 0-100. 50 is neutral.
    # If greed is high, they value rewards more.
    greed_factor = (npc_sheet.wealth_desire / 50.0)
    perceived_reward = reward_score * greed_factor

    # 2. Calculate Perceived Risk/Effort
    base_risk = 0
    for obj in mission.objectives:
        if isinstance(obj, KillObjective):
            base_risk += 50
        elif isinstance(obj, VisitRoomObjective):
            base_risk += 20
        elif isinstance(obj, ObtainItemObjective):
            base_risk += 10
        else:
            base_risk += 10
            
    # Adjust risk by Aggression (for combat) and Confidence
    # High aggression lowers combat risk perception.
    # High confidence lowers general risk perception.
    
    aggression_mod = (100 - npc_sheet.aggression) / 100.0 # 0.0 to 1.0 (High agg -> low mod)
    confidence_mod = (100 - npc_sheet.confidence) / 100.0 # 0.0 to 1.0 (High conf -> low mod)
    
    perceived_risk = base_risk * ((aggression_mod + confidence_mod) / 2.0)
    
    # 3. Relationship Factor
    # issuer_id might be a user_id. We need to check relationships.
    # relationships is dict[entity_id] -> score
    rel_score = npc_sheet.relationships.get(issuer_id, 0)
    
    # 4. Final Score
    # Score = Reward + (Rel * 2) - Risk
    final_score = perceived_reward + (rel_score * 2.0) - perceived_risk
    
    # Threshold
    # Base threshold 20.
    threshold = 20.0
    
    if final_score >= threshold:
        return True, "I accept your terms."
    else:
        # Generate rejection reason based on what was low
        if perceived_risk > perceived_reward:
            return False, "Too dangerous for that pay."
        elif rel_score < -20:
            return False, "I don't work for people like you."
        else:
            return False, "I'm not interested."
