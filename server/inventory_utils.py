"""
Inventory utilities for enhanced data integrity and robustness.

These utilities provide defensive programming helpers to ensure inventory
operations maintain data consistency and prevent corruption scenarios.

Mission briefing:
    While our slot-based inventory doesn't require compaction (each slot has
    a specific purpose), we still need utilities to validate integrity,
    prevent duplicate UUIDs, and ensure atomic ownership transfers.

Key functions:
    - validate_inventory_integrity: Ensure no duplicate UUIDs, proper constraints
    - find_object_in_inventory: Safely locate objects across all slots
    - transfer_object_ownership: Atomically change ownership with validation
    - compact_object_references: Clean up any dangling references
"""

from __future__ import annotations

from typing import Optional, Tuple, List, Set
from world import Object, Inventory
import logging

logger = logging.getLogger(__name__)


def validate_inventory_integrity(inventory: Inventory) -> Tuple[bool, List[str]]:
    """
    Validate inventory for data integrity issues.
    
    Returns:
        (is_valid, list_of_errors)
        
    Checks performed:
    - No duplicate UUIDs across slots
    - Objects are in appropriate slots based on size constraints
    - No None objects in unexpected places
    - Object tags are consistent with slot placement
    """
    errors: List[str] = []
    
    if not inventory or not hasattr(inventory, 'slots'):
        errors.append("Invalid inventory object")
        return False, errors
    
    # Ensure exactly 8 slots
    if len(inventory.slots) != 8:
        errors.append(f"Inventory should have exactly 8 slots, found {len(inventory.slots)}")
    
    # Track UUIDs to detect duplicates
    seen_uuids: Set[str] = set()
    
    for slot_idx, obj in enumerate(inventory.slots):
        if obj is None:
            continue  # Empty slots are fine
            
        # Check for duplicate UUIDs
        if obj.uuid in seen_uuids:
            errors.append(f"Duplicate UUID {obj.uuid} found in slot {slot_idx}")
        else:
            seen_uuids.add(obj.uuid)
        
        # Validate slot constraints
        if not inventory.can_place(slot_idx, obj):
            obj_tags = getattr(obj, 'object_tags', set()) or set()
            errors.append(
                f"Object '{obj.display_name}' with tags {obj_tags} "
                f"violates constraints for slot {slot_idx}"
            )
    
    is_valid = len(errors) == 0
    return is_valid, errors


def find_object_in_inventory(inventory: Inventory, target_uuid: str) -> Optional[Tuple[int, Object]]:
    """
    Find an object in inventory by UUID.
    
    Returns:
        (slot_index, object) if found, None if not found
        
    This is safer than direct slot access as it validates the object exists
    and returns both the location and the object itself.
    """
    if not inventory or not hasattr(inventory, 'slots'):
        return None
        
    for slot_idx, obj in enumerate(inventory.slots):
        if obj is not None and getattr(obj, 'uuid', None) == target_uuid:
            return (slot_idx, obj)
    
    return None


def find_objects_by_name(inventory: Inventory, name: str,
                         case_sensitive: bool = False) -> List[Tuple[int, Object]]:
    """
    Find all objects in inventory matching a display name.
    
    Returns:
        List of (slot_index, object) tuples for matches
        
    Useful for crafting systems or when multiple items have the same name.
    """
    matches: List[Tuple[int, Object]] = []
    
    if not inventory or not hasattr(inventory, 'slots'):
        return matches
    
    target_name = name if case_sensitive else name.lower()
    
    for slot_idx, obj in enumerate(inventory.slots):
        if obj is None:
            continue
            
        obj_name = getattr(obj, 'display_name', '')
        if not case_sensitive:
            obj_name = obj_name.lower()
            
        if obj_name == target_name:
            matches.append((slot_idx, obj))
    
    return matches


def transfer_object_ownership(obj: Object, new_owner_id: Optional[str],
                              validate_owner_exists: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Atomically transfer object ownership with validation.
    
    Args:
        obj: The object to transfer
        new_owner_id: New owner's UUID (or None for unowned)
        validate_owner_exists: Whether to validate the new owner exists
        
    Returns:
        (success, error_message)
        
    This ensures ownership changes are atomic and logged for debugging.
    """
    if not obj:
        return False, "Cannot transfer ownership of None object"
    
    old_owner = getattr(obj, 'owner_id', None)
    
    # Validate new owner if requested
    if validate_owner_exists and new_owner_id is not None:
        # In a full implementation, this would check against world.users or world.npc_ids
        # For now, we just ensure it's a valid string format
        if not isinstance(new_owner_id, str) or not new_owner_id.strip():
            return False, f"Invalid owner ID format: {new_owner_id}"
    
    # Perform the transfer
    try:
        obj.owner_id = new_owner_id  # type: ignore[attr-defined]
        
        # Log the transfer for debugging
        logger.info(
            f"Object ownership transferred: '{obj.display_name}' ({obj.uuid}) "
            f"from '{old_owner}' to '{new_owner_id}'"
        )
        
        return True, None
        
    except Exception as e:
        logger.error(f"Failed to transfer ownership of {obj.uuid}: {e}")
        return False, f"Ownership transfer failed: {e}"


def remove_object_safely(inventory: Inventory, slot_index: int):
    """
    Safely remove an object from inventory with validation.
    
    Returns:
        (success, removed_object, error_message)
    """
    """
    Safely remove an object from inventory with validation.
    
    Returns:
        (success, removed_object, error_message)
        
    This is more robust than direct slot access as it validates the operation
    and provides clear error reporting.
    """
    if not inventory or not hasattr(inventory, 'slots'):
        return False, None, "Invalid inventory"
        
    if slot_index < 0 or slot_index >= len(inventory.slots):
        return False, None, f"Invalid slot index: {slot_index}"
    
    try:
        removed_obj = inventory.remove(slot_index)
        return True, removed_obj, None
        
    except Exception as e:
        logger.error(f"Failed to remove object from slot {slot_index}: {e}")
        return False, None, f"Removal failed: {e}"


def place_object_safely(inventory: Inventory, slot_index: int, obj: Object):
    """
    Safely place an object in inventory with full validation.
    
    Returns:
        (success, error_message)
        
    Performs comprehensive checks before placement to prevent corruption.
    """
    if not inventory or not hasattr(inventory, 'slots'):
        return False, "Invalid inventory"
        
    if not obj:
        return False, "Cannot place None object"
    
    if slot_index < 0 or slot_index >= len(inventory.slots):
        return False, f"Invalid slot index: {slot_index}"
    
    # Check if slot is already occupied
    if inventory.slots[slot_index] is not None:
        return False, f"Slot {slot_index} is already occupied"
    
    # Validate object can be placed in this slot
    if not inventory.can_place(slot_index, obj):
        obj_tags = getattr(obj, 'object_tags', set()) or set()
        return False, f"Object with tags {obj_tags} cannot be placed in slot {slot_index}"
    
    # Check for duplicate UUID in other slots
    for idx, existing_obj in enumerate(inventory.slots):
        if idx != slot_index and existing_obj and existing_obj.uuid == obj.uuid:
            return False, f"Object UUID {obj.uuid} already exists in slot {idx}"
    
    try:
        success = inventory.place(slot_index, obj)
        if not success:
            return False, "Placement failed for unknown reason"
        return True, None
        
    except Exception as e:
        logger.error(f"Failed to place object in slot {slot_index}: {e}")
        return False, f"Placement failed: {e}"


def compact_inventory_references(inventory: Inventory) -> Tuple[int, List[str]]:
    """
    Clean up any issues with inventory references and report what was fixed.
    
    Returns:
        (num_fixes_applied, list_of_fixes_descriptions)
        
    Note: Our slot-based system doesn't need compaction, but this function
    can clean up other integrity issues like malformed objects or broken references.
    """
    fixes_applied = 0
    fix_descriptions: List[str] = []
    
    if not inventory or not hasattr(inventory, 'slots'):
        return fixes_applied, fix_descriptions
    
    # Ensure slots list has exactly 8 elements
    if len(inventory.slots) != 8:
        old_len = len(inventory.slots)
        if len(inventory.slots) < 8:
            # Pad with None
            inventory.slots.extend([None] * (8 - len(inventory.slots)))
        else:
            # Truncate to 8 (preserve first 8 slots)
            inventory.slots = inventory.slots[:8]
        
        fixes_applied += 1
        fix_descriptions.append(f"Adjusted inventory slots from {old_len} to 8")
    
    # Remove any objects that have lost their essential properties
    for slot_idx, obj in enumerate(inventory.slots):
        if obj is None:
            continue
            
        # Check if object has required properties
        if not hasattr(obj, 'uuid') or not hasattr(obj, 'display_name'):
            inventory.slots[slot_idx] = None
            fixes_applied += 1
            fix_descriptions.append(f"Removed malformed object from slot {slot_idx}")
            continue
        
        # Ensure UUID is valid
        if not obj.uuid or not isinstance(obj.uuid, str):
            inventory.slots[slot_idx] = None
            fixes_applied += 1
            fix_descriptions.append(f"Removed object with invalid UUID from slot {slot_idx}")
            continue
    
    return fixes_applied, fix_descriptions


def get_inventory_summary(inventory: Inventory) -> dict:
    """
    Get a comprehensive summary of inventory state for debugging.
    
    Returns:
        Dictionary with inventory statistics and validation results
    """
    if not inventory:
        return {"error": "Invalid inventory"}
    
    is_valid, errors = validate_inventory_integrity(inventory)
    
    # Count objects by type
    small_objects = 0
    large_objects = 0
    hand_objects = 0
    immovable_objects = 0
    
    object_details = []
    
    for slot_idx, obj in enumerate(inventory.slots):
        if obj is None:
            continue
            
        tags = getattr(obj, 'object_tags', set()) or set()
        
        # Categorize object
        if 'Immovable' in tags or 'Travel Point' in tags:
            immovable_objects += 1
        elif slot_idx in (0, 1):  # Hand slots
            hand_objects += 1
        elif 'large' in tags:
            large_objects += 1
        else:
            small_objects += 1
        
        object_details.append({
            'slot': slot_idx,
            'uuid': obj.uuid,
            'name': obj.display_name,
            'tags': list(tags),
            'owner_id': getattr(obj, 'owner_id', None)
        })
    
    return {
        'is_valid': is_valid,
        'errors': errors,
        'total_objects': len(object_details),
        'empty_slots': len([s for s in inventory.slots if s is None]),
        'small_objects': small_objects,
        'large_objects': large_objects,
        'hand_objects': hand_objects,
        'immovable_objects': immovable_objects,
        'object_details': object_details
    }