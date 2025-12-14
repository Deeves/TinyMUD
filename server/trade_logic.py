"""Trade Logic Utilities.

Core functions for barter and trade operations.
Extracted from server.py to reduce file size.
"""
from __future__ import annotations

from typing import Any
from safe_utils import safe_call


def inventory_slots(inv) -> list:
    """Get the slots list from an inventory object safely."""
    try:
        return list(getattr(inv, 'slots', []) or [])
    except Exception:
        return []


def find_inventory_slot(inv, obj) -> int | None:
    """Find a compatible empty slot for an object in the inventory."""
    try:
        slots = inventory_slots(inv)
        for idx, existing in enumerate(slots):
            if existing is None and inv.can_place(idx, obj):
                return idx
        for idx in range(len(slots)):
            if inv.can_place(idx, obj):
                return idx
    except Exception:
        pass
    return None


def barter_swap(
    actor_inv,
    target_inv,
    actor_offer_uuid: str,
    target_want_uuid: str,
) -> tuple[bool, dict[str, Any] | str]:
    """Swap items between two inventories in a barter transaction.
    
    Returns (success, result) where result is either a dict with 'offered'/'desired' 
    objects or an error message string.
    """
    # Find offered item in actor's inventory
    offered_idx: int | None = None
    offered_obj = None
    for idx, obj in enumerate(inventory_slots(actor_inv)):
        if obj and getattr(obj, 'uuid', None) == actor_offer_uuid:
            offered_idx = idx
            offered_obj = obj
            break
    if offered_idx is None or offered_obj is None:
        return False, 'Your offered item is no longer in your inventory.'

    # Find desired item in target's inventory
    desired_idx: int | None = None
    desired_obj = None
    for idx, obj in enumerate(inventory_slots(target_inv)):
        if obj and getattr(obj, 'uuid', None) == target_want_uuid:
            desired_idx = idx
            desired_obj = obj
            break
    if desired_idx is None or desired_obj is None:
        return False, 'That item is no longer available.'

    # Remove offered item from actor
    try:
        removed_offered = actor_inv.remove(offered_idx)
    except Exception:
        removed_offered = None
    if removed_offered is None:
        return False, 'Unable to pick up your offered item.'
    offered_obj = removed_offered

    # Remove desired item from target
    try:
        removed_desired = target_inv.remove(desired_idx)
    except Exception:
        removed_desired = None
    if removed_desired is None:
        safe_call(actor_inv.place, offered_idx, offered_obj)
        return False, 'Unable to take that item from your trade partner.'
    desired_obj = removed_desired

    # Place desired item into actor inventory
    actor_place_idx = offered_idx
    placed_actor = False
    try:
        placed_actor = actor_inv.place(actor_place_idx, desired_obj)
    except Exception:
        placed_actor = False
    if not placed_actor:
        alt_idx = find_inventory_slot(actor_inv, desired_obj)
        if alt_idx is not None:
            try:
                placed_actor = actor_inv.place(alt_idx, desired_obj)
                if placed_actor:
                    actor_place_idx = alt_idx
            except Exception:
                placed_actor = False
    if not placed_actor:
        safe_call(target_inv.place, desired_idx, desired_obj)
        safe_call(actor_inv.place, offered_idx, offered_obj)
        return False, 'You cannot carry that item.'

    # Place offered item into target inventory
    target_place_idx = desired_idx
    placed_target = False
    try:
        placed_target = target_inv.place(target_place_idx, offered_obj)
    except Exception:
        placed_target = False
    if not placed_target:
        alt_idx = find_inventory_slot(target_inv, offered_obj)
        if alt_idx is not None:
            try:
                placed_target = target_inv.place(alt_idx, offered_obj)
                if placed_target:
                    target_place_idx = alt_idx
            except Exception:
                placed_target = False
    if not placed_target:
        safe_call(actor_inv.remove, actor_place_idx)
        safe_call(actor_inv.place, offered_idx, offered_obj)
        safe_call(target_inv.place, desired_idx, desired_obj)
        return False, 'They cannot carry that item.'

    return True, {'offered': offered_obj, 'desired': desired_obj}


def trade_purchase(
    buyer_sheet,
    seller_sheet,
    seller_inv,
    item_uuid: str,
    price: int,
) -> tuple[bool, dict[str, Any] | str]:
    """Purchase an item from a seller using currency.
    
    Returns (success, result) where result is either a dict with 'item'/'price' 
    or an error message string.
    """
    try:
        price_int = int(price)
    except Exception:
        return False, 'Offer must be a valid whole number of coins.'
    if price_int <= 0:
        return False, 'Offer must be at least 1 coin.'

    buyer_coins = int(getattr(buyer_sheet, 'currency', 0) or 0)
    if buyer_coins < price_int:
        return False, f'You only have {buyer_coins} coin{"s" if buyer_coins != 1 else ""}.'

    # Find item in seller inventory
    desired_idx: int | None = None
    desired_obj = None
    for idx, obj in enumerate(inventory_slots(seller_inv)):
        if obj and getattr(obj, 'uuid', None) == item_uuid:
            desired_idx = idx
            desired_obj = obj
            break
    if desired_idx is None or desired_obj is None:
        return False, 'That item is no longer available.'

    # Check buyer can carry it
    buyer_slot = find_inventory_slot(buyer_sheet.inventory, desired_obj)
    if buyer_slot is None:
        return False, 'You cannot carry that item.'

    # Remove from seller
    try:
        removed = seller_inv.remove(desired_idx)
    except Exception:
        removed = None
    if removed is None:
        return False, 'Unable to take that item right now.'
    desired_obj = removed

    # Place in buyer inventory
    placed = False
    try:
        placed = buyer_sheet.inventory.place(buyer_slot, desired_obj)
    except Exception:
        placed = False
    if not placed:
        try:
            seller_inv.place(desired_idx, desired_obj)
        except Exception:
            pass
        return False, 'You cannot carry that item.'

    # Transfer currency
    buyer_sheet.currency = buyer_coins - price_int
    seller_coins = int(getattr(seller_sheet, 'currency', 0) or 0)
    seller_sheet.currency = seller_coins + price_int

    return True, {'item': desired_obj, 'price': price_int}
