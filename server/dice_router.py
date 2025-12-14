from __future__ import annotations

"""Dice Roll Router.

Handles the 'roll' command for dice rolling.
Extracted from server.py handle_message to reduce file size.
"""

from typing import Dict, Any, Callable

from command_context import CommandContext

MESSAGE_OUT = 'message'


def try_handle_flow(
    ctx: CommandContext,
    sid: str | None,
    player_message: str,
    text_lower: str,
    emit: Callable[[str, Dict[str, Any]], None],
) -> bool:
    """Handle dice roll command if applicable.
    
    Returns True if the message was handled, False otherwise.
    """
    if not (text_lower == "roll" or text_lower.startswith("roll ")):
        return False

    # Import dice utilities
    try:
        from dice_utils import dice_roll, DiceError
    except ImportError:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Dice rolling not available.'})
        return True

    if sid not in ctx.world.players:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first to roll dice.'})
        return True

    raw = player_message.strip()
    # Remove leading keyword
    arg = raw[4:].strip() if len(raw) > 4 else ""
    if not arg:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: roll <dice expression> [| Private]'})
        return True

    # Support optional "| Private" suffix (case-insensitive)
    priv = False
    if '|' in arg:
        left, right = arg.split('|', 1)
        expr = left.strip()
        if right.strip().lower() == 'private':
            priv = True
    else:
        expr = arg

    try:
        result = dice_roll(expr)
    except DiceError as e:
        emit(MESSAGE_OUT, {'type': 'error', 'content': f'Dice error: {e}'})
        return True

    # Compose result text
    res_text = f"{result.expression} = {result.total}"
    player_obj = ctx.world.players.get(sid)
    pname = player_obj.sheet.display_name if player_obj else 'Someone'

    if priv:
        emit(MESSAGE_OUT, {'type': 'system', 'content': f"You secretly pull out the sacred geometric stones from your pocket and roll {res_text}."})
        return True

    # Public roll: tell roller and broadcast to room
    emit(MESSAGE_OUT, {'type': 'system', 'content': f"You pull out the sacred geometric stones from your pocket and roll {res_text}."})
    if player_obj:
        ctx.broadcast_to_room(player_obj.room_id, {
            'type': 'system',
            'content': f"{pname} pulls out the sacred geometric stones from their pocket and rolls {res_text}."
        }, exclude_sid=sid)
    return True
