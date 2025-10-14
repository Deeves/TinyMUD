"""
GOAP Planner State Management and Data Integrity Utilities.

This module addresses data integrity concerns around GOAP planner side effects,
ensuring that NPC intent state remains consistent when advanced GOAP is toggled
and that planner caching structures are properly reset on world reload.

Mission briefing:
    The GOAP system can leave NPCs in partially mutated states when switching
    between AI planning and offline planning modes. This module provides
    utilities to ensure clean state transitions and proper cleanup of any
    residual planning artifacts.

Key concerns addressed:
    - Plan queue corruption when switching GOAP modes
    - Rate limiter state persistence across world reloads
    - Orphaned planner artifacts in NPC state
    - Inconsistent need degradation between GOAP modes
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple
from world import World, CharacterSheet

logger = logging.getLogger(__name__)


def validate_npc_planner_state(world: World) -> Tuple[bool, List[str]]:
    """
    Validate NPC planner state for consistency and integrity.
    
    Returns:
        (is_valid, list_of_issues)
        
    Checks performed:
        - Plan queue contains only valid actions
        - Need values are within valid ranges
        - No orphaned planner artifacts
        - Sleep state consistency
    """
    issues: List[str] = []
    
    if not world or not hasattr(world, 'npc_sheets'):
        issues.append("World or NPC sheets missing")
        return False, issues
    
    # Validate each NPC's planner state
    for npc_name, sheet in world.npc_sheets.items():
        if not isinstance(sheet, CharacterSheet):
            issues.append(f"NPC '{npc_name}' has invalid sheet type: {type(sheet)}")
            continue
            
        # Validate plan queue structure
        plan_queue = getattr(sheet, 'plan_queue', [])
        if not isinstance(plan_queue, list):
            issues.append(f"NPC '{npc_name}' has invalid plan_queue type: {type(plan_queue)}")
            continue
            
        # Validate each action in plan queue
        for i, action in enumerate(plan_queue):
            if not isinstance(action, dict):
                issues.append(f"NPC '{npc_name}' plan_queue[{i}] is not a dict: {type(action)}")
                continue
            
            if 'tool' not in action:
                issues.append(f"NPC '{npc_name}' plan_queue[{i}] missing 'tool' key")
                continue
                
            tool = action.get('tool')
            if not isinstance(tool, str):
                issues.append(f"NPC '{npc_name}' plan_queue[{i}] tool is not string: {type(tool)}")
                continue
                
            args = action.get('args', {})
            if not isinstance(args, dict):
                issues.append(f"NPC '{npc_name}' plan_queue[{i}] args is not dict: {type(args)}")
        
        # Validate need values are in proper ranges (0-100)
        needs_to_check = ['hunger', 'thirst', 'socialization', 'sleep']
        for need in needs_to_check:
            value = getattr(sheet, need, 100.0)
            if not isinstance(value, (int, float)):
                issues.append(f"NPC '{npc_name}' {need} is not numeric: {type(value)}")
                continue
            if value < 0 or value > 100:
                issues.append(f"NPC '{npc_name}' {need} out of range (0-100): {value}")
        
        # Validate action points
        action_points = getattr(sheet, 'action_points', 0)
        if not isinstance(action_points, int):
            issues.append(f"NPC '{npc_name}' action_points is not int: {type(action_points)}")
        elif action_points < 0:
            issues.append(f"NPC '{npc_name}' action_points is negative: {action_points}")
        
        # Validate sleep state consistency
        sleeping_ticks = getattr(sheet, 'sleeping_ticks_remaining', 0)
        sleeping_bed = getattr(sheet, 'sleeping_bed_uuid', None)
        
        if sleeping_ticks > 0 and not sleeping_bed:
            issues.append(f"NPC '{npc_name}' is sleeping but has no bed UUID")
        elif sleeping_ticks <= 0 and sleeping_bed:
            issues.append(f"NPC '{npc_name}' has bed UUID but is not sleeping")
    
    is_valid = len(issues) == 0
    return is_valid, issues


def clean_npc_planner_state(world: World, reset_plans: bool = True,
                            reset_needs: bool = False) -> Tuple[int, List[str]]:
    """
    Clean up NPC planner state to ensure consistency.
    
    Args:
        world: World instance to clean
        reset_plans: Whether to clear all plan queues
        reset_needs: Whether to reset needs to default values
        
    Returns:
        (num_npcs_cleaned, list_of_actions_taken)
    """
    actions_taken: List[str] = []
    npcs_cleaned = 0
    
    if not world or not hasattr(world, 'npc_sheets'):
        return 0, actions_taken
    
    for npc_name, sheet in world.npc_sheets.items():
        npc_had_issues = False
        
        # Clean plan queue if requested or if it's malformed
        plan_queue = getattr(sheet, 'plan_queue', [])
        if reset_plans or not isinstance(plan_queue, list):
            sheet.plan_queue = []
            actions_taken.append(f"Reset plan queue for NPC '{npc_name}'")
            npc_had_issues = True
        else:
            # Validate and clean individual actions
            cleaned_plan = []
            for action in plan_queue:
                if (isinstance(action, dict) and 
                    'tool' in action and 
                    isinstance(action['tool'], str) and
                    isinstance(action.get('args', {}), dict)):
                    cleaned_plan.append(action)
                else:
                    npc_had_issues = True
            
            if len(cleaned_plan) != len(plan_queue):
                sheet.plan_queue = cleaned_plan
                actions_taken.append(f"Cleaned invalid actions from '{npc_name}' plan queue")
                npc_had_issues = True
        
        # Reset needs if requested
        if reset_needs:
            sheet.hunger = 100.0
            sheet.thirst = 100.0
            sheet.socialization = 100.0
            sheet.sleep = 100.0
            actions_taken.append(f"Reset needs for NPC '{npc_name}'")
            npc_had_issues = True
        else:
            # Clamp existing needs to valid ranges
            needs_clamped = False
            for need_name in ['hunger', 'thirst', 'socialization', 'sleep']:
                current_value = getattr(sheet, need_name, 100.0)
                if not isinstance(current_value, (int, float)):
                    setattr(sheet, need_name, 100.0)
                    needs_clamped = True
                else:
                    clamped_value = max(0.0, min(100.0, float(current_value)))
                    if clamped_value != current_value:
                        setattr(sheet, need_name, clamped_value)
                        needs_clamped = True
            
            if needs_clamped:
                actions_taken.append(f"Clamped need values for NPC '{npc_name}'")
                npc_had_issues = True
        
        # Clean action points
        action_points = getattr(sheet, 'action_points', 0)
        if not isinstance(action_points, int) or action_points < 0:
            sheet.action_points = 0
            actions_taken.append(f"Reset action points for NPC '{npc_name}'")
            npc_had_issues = True
        
        # Clean sleep state
        sleeping_ticks = getattr(sheet, 'sleeping_ticks_remaining', 0)
        sleeping_bed = getattr(sheet, 'sleeping_bed_uuid', None)
        
        if sleeping_ticks > 0 and not sleeping_bed:
            # Sleeping without a bed - stop sleeping
            sheet.sleeping_ticks_remaining = 0
            actions_taken.append(f"Stopped invalid sleep state for NPC '{npc_name}'")
            npc_had_issues = True
        elif sleeping_ticks <= 0 and sleeping_bed:
            # Has bed but not sleeping - clear bed reference
            sheet.sleeping_bed_uuid = None
            actions_taken.append(f"Cleared orphaned bed reference for NPC '{npc_name}'")
            npc_had_issues = True
        
        if npc_had_issues:
            npcs_cleaned += 1
    
    return npcs_cleaned, actions_taken


def reset_goap_mode_safely(world: World, new_advanced_goap_enabled: bool) -> Tuple[bool, List[str]]:
    """
    Safely transition between GOAP modes, ensuring no partial state corruption.
    
    Args:
        world: World instance to modify
        new_advanced_goap_enabled: Target GOAP mode
        
    Returns:
        (success, list_of_actions_taken)
    """
    actions_taken: List[str] = []
    
    if not world:
        return False, ["World is None"]
    
    current_mode = getattr(world, 'advanced_goap_enabled', False)
    
    # If no change needed, validate current state
    if current_mode == new_advanced_goap_enabled:
        is_valid, issues = validate_npc_planner_state(world)
        if not is_valid:
            # Clean up issues even if mode isn't changing
            npcs_cleaned, cleanup_actions = clean_npc_planner_state(world, reset_plans=True)
            actions_taken.extend(cleanup_actions)
            actions_taken.append(f"Cleaned up {npcs_cleaned} NPCs due to validation issues")
        
        actions_taken.append(f"GOAP mode already set to {new_advanced_goap_enabled}")
        return True, actions_taken
    
    # Mode is changing - ensure clean transition
    try:
        # Step 1: Clear all plan queues to prevent stale actions
        for npc_name, sheet in world.npc_sheets.items():
            if hasattr(sheet, 'plan_queue') and sheet.plan_queue:
                sheet.plan_queue = []
                actions_taken.append(f"Cleared plan queue for NPC '{npc_name}' during mode switch")
        
        # Step 2: Update the mode
        world.advanced_goap_enabled = new_advanced_goap_enabled
        mode_name = "advanced AI GOAP" if new_advanced_goap_enabled else "offline heuristic planning"
        actions_taken.append(f"Switched GOAP mode to: {mode_name}")
        
        # Step 3: Clean up any remaining inconsistencies
        npcs_cleaned, cleanup_actions = clean_npc_planner_state(world, reset_plans=False)
        actions_taken.extend(cleanup_actions)
        
        if npcs_cleaned > 0:
            actions_taken.append(f"Cleaned up residual state for {npcs_cleaned} NPCs")
        
        # Step 4: Validate final state
        is_valid, issues = validate_npc_planner_state(world)
        if not is_valid:
            actions_taken.append(f"Warning: {len(issues)} validation issues remain after cleanup")
            for issue in issues[:5]:  # Limit logged issues
                actions_taken.append(f"  - {issue}")
        
        return True, actions_taken
        
    except Exception as e:
        logger.error(f"Failed to safely reset GOAP mode: {e}")
        actions_taken.append(f"Error during GOAP mode reset: {e}")
        return False, actions_taken


def cleanup_planner_caches() -> Tuple[int, List[str]]:
    """
    Clean up any planner-related caches and rate limiting state.
    
    This should be called on world reload to ensure fresh state.
    
    Returns:
        (num_caches_cleaned, list_of_actions_taken)
    """
    actions_taken: List[str] = []
    caches_cleaned = 0
    
    try:
        # Clean up rate limiter state for NPC planning operations
        from rate_limiter import cleanup_npc_planning_rate_limits
        
        try:
            cleaned_count = cleanup_npc_planning_rate_limits()
            if cleaned_count > 0:
                actions_taken.append(f"Cleaned {cleaned_count} NPC planning rate limits")
                caches_cleaned += cleaned_count
            else:
                actions_taken.append("No NPC planning rate limits to clean")
                
        except Exception as e:
            actions_taken.append(f"NPC rate limit cleanup failed: {e}")
            
            # Fallback to general cleanup
            try:
                from rate_limiter import cleanup_rate_limiter
                cleanup_rate_limiter()
                actions_taken.append("Performed fallback general rate limiter cleanup")
                caches_cleaned += 1
            except Exception:
                pass  # Best effort
        
        # Note: We don't clean AI model caches as they're typically stateless
        # and recreated on each use. The rate limiter is the main persistent cache.
        
        actions_taken.append(f"Cleaned {caches_cleaned} planner cache structures")
        return caches_cleaned, actions_taken
        
    except Exception as e:
        logger.error(f"Failed to cleanup planner caches: {e}")
        actions_taken.append(f"Error during cache cleanup: {e}")
        return caches_cleaned, actions_taken


def audit_world_planner_integrity(world: World) -> Dict[str, any]:
    """
    Comprehensive audit of world planner state for debugging and monitoring.
    
    Returns:
        Dictionary with audit results and statistics
    """
    if not world:
        return {"error": "World is None"}
    
    audit_results = {
        "timestamp": __import__('time').time(),
        "advanced_goap_enabled": getattr(world, 'advanced_goap_enabled', False),
        "total_npcs": len(getattr(world, 'npc_sheets', {})),
        "npcs_with_plans": 0,
        "npcs_with_invalid_plans": 0,
        "npcs_sleeping": 0,
        "npcs_with_invalid_needs": 0,
        "validation_issues": [],
        "npc_details": {}
    }
    
    try:
        # Validate overall state
        is_valid, issues = validate_npc_planner_state(world)
        audit_results["validation_issues"] = issues
        audit_results["is_valid"] = is_valid
        
        # Collect NPC statistics
        for npc_name, sheet in world.npc_sheets.items():
            npc_stats = {
                "has_plan": bool(getattr(sheet, 'plan_queue', [])),
                "plan_length": len(getattr(sheet, 'plan_queue', [])),
                "action_points": getattr(sheet, 'action_points', 0),
                "is_sleeping": getattr(sheet, 'sleeping_ticks_remaining', 0) > 0,
                "needs": {
                    "hunger": getattr(sheet, 'hunger', 100.0),
                    "thirst": getattr(sheet, 'thirst', 100.0),
                    "socialization": getattr(sheet, 'socialization', 100.0),
                    "sleep": getattr(sheet, 'sleep', 100.0)
                },
                "needs_valid": True
            }
            
            # Check for various conditions
            if npc_stats["has_plan"]:
                audit_results["npcs_with_plans"] += 1
                
            if npc_stats["is_sleeping"]:
                audit_results["npcs_sleeping"] += 1
            
            # Validate needs ranges
            for need_name, need_value in npc_stats["needs"].items():
                if not isinstance(need_value, (int, float)) or need_value < 0 or need_value > 100:
                    npc_stats["needs_valid"] = False
                    audit_results["npcs_with_invalid_needs"] += 1
                    break
            
            # Check plan validity
            plan_queue = getattr(sheet, 'plan_queue', [])
            invalid_plan = False
            if plan_queue:
                for action in plan_queue:
                    if not isinstance(action, dict) or 'tool' not in action:
                        invalid_plan = True
                        break
            
            if invalid_plan:
                audit_results["npcs_with_invalid_plans"] += 1
                npc_stats["plan_valid"] = False
            else:
                npc_stats["plan_valid"] = True
            
            audit_results["npc_details"][npc_name] = npc_stats
        
        # Calculate health score (0-100)
        total_checks = audit_results["total_npcs"] * 3  # plans + needs + sleep consistency
        failed_checks = (audit_results["npcs_with_invalid_plans"] +
                         audit_results["npcs_with_invalid_needs"] +
                         len(audit_results["validation_issues"]))
        
        if total_checks > 0:
            audit_results["health_score"] = max(0, 100 - (failed_checks * 100 / total_checks))
        else:
            audit_results["health_score"] = 100
            
    except Exception as e:
        audit_results["audit_error"] = str(e)
        audit_results["health_score"] = 0
    
    return audit_results


def on_world_reload_cleanup(world: World) -> List[str]:
    """
    Perform all necessary cleanup when world is reloaded from file.
    
    This is the main entry point for ensuring planner integrity after world reload.
    
    Returns:
        List of actions taken during cleanup
    """
    all_actions = []
    
    try:
        # Step 1: Clean up external caches
        caches_cleaned, cache_actions = cleanup_planner_caches()
        all_actions.extend(cache_actions)
        
        # Step 2: Validate and clean NPC state
        npcs_cleaned, npc_actions = clean_npc_planner_state(world, reset_plans=False)
        all_actions.extend(npc_actions)
        
        # Step 3: Ensure GOAP mode is consistently applied
        current_mode = getattr(world, 'advanced_goap_enabled', False)
        mode_success, mode_actions = reset_goap_mode_safely(world, current_mode)
        all_actions.extend(mode_actions)
        
        # Step 4: Final validation
        audit = audit_world_planner_integrity(world)
        health_score = audit.get('health_score', 0)
        
        all_actions.append(f"World reload cleanup completed - Health score: {health_score:.1f}%")
        
        if health_score < 90:
            all_actions.append(f"Warning: {len(audit.get('validation_issues', []))} integrity issues remain")
    
    except Exception as e:
        logger.error(f"Error during world reload cleanup: {e}")
        all_actions.append(f"Cleanup error: {e}")
    
    return all_actions