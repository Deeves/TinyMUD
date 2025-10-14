"""Service layer contract definitions and helpers.

All service functions in TinyMUD should return a 4-tuple:
    (handled: bool, error: str | None, emits: List[dict], broadcasts: List[Tuple[str, dict]])

Where:
    - handled: True if this service recognized and processed the request
    - error: None on success, error message string on failure (still handled=True)
    - emits: List of message payloads to send to the acting player
    - broadcasts: List of (room_id, payload) tuples to broadcast to rooms

Example success:
    return True, None, [{'type': 'system', 'content': 'Done!'}], []

Example error:
    return True, 'Invalid input.', [], []

Example with broadcast:
    emits = [{'type': 'system', 'content': 'You created a room.'}]
    broadcasts = [(room_id, {'type': 'system', 'content': 'Someone created a room!'})]
    return True, None, emits, broadcasts

Why This Contract?
------------------
Uniform contracts across all services make the codebase easier to maintain,
test, and extend. The 4-tuple pattern provides clear separation between:
  1. Command routing (handled)
  2. Operation success/failure (error)
  3. Private feedback (emits to acting player)
  4. Public announcements (broadcasts to room occupants)

This pattern is already proven in account_service, movement_service, and
admin_service. We're standardizing all other services to match.
"""

from __future__ import annotations

from typing import List, Tuple, Optional

# Type alias for clarity and reusability
ServiceReturn = Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]


def success(emits: List[dict], broadcasts: List[Tuple[str, dict]] | None = None) -> ServiceReturn:
    """Helper to return a successful service result.
    
    Args:
        emits: List of message payloads to send to the acting player
        broadcasts: Optional list of (room_id, payload) tuples for room announcements
    
    Returns:
        Standard 4-tuple: (True, None, emits, broadcasts)
    
    Example:
        return success([{'type': 'system', 'content': 'Room created!'}])
    """
    return True, None, emits, broadcasts or []


def error(message: str) -> ServiceReturn:
    """Helper to return a service error result.
    
    Args:
        message: User-friendly error message
    
    Returns:
        Standard 4-tuple: (True, error_message, [], [])
    
    Note:
        Even errors return handled=True because the service recognized the command.
        The error is in the second position for easy checking: if err: ...
    
    Example:
        return error("Invalid room name.")
    """
    return True, message, [], []


def not_handled() -> ServiceReturn:
    """Helper to return 'this service did not handle this request'.
    
    Returns:
        Standard 4-tuple: (False, None, [], [])
    
    Use this when a service doesn't recognize the command/subcommand.
    The router can then try the next service in the chain.
    
    Example:
        if sub not in ('create', 'delete', 'list'):
            return not_handled()
    """
    return False, None, [], []


def emit_service_result(
    ctx,  # CommandContext - avoid circular import by not type hinting
    sid: str | None,
    emit_fn,  # EmitFn - avoid circular import
    service_result: ServiceReturn,
) -> None:
    """Helper to emit service results following the standard pattern.
    
    This consolidates the common emission logic used in routers. After calling
    a service, pass the result to this helper to handle all emission and
    broadcasting automatically.
    
    Args:
        ctx: CommandContext with broadcast_to_room and message_out
        sid: Session ID of the acting player (for broadcast exclusion)
        emit_fn: The emit function (typically the 'emit' parameter in try_handle)
        service_result: The 4-tuple returned by a service function
    
    Example usage in a router:
        handled, err, emits, broadcasts = some_service(...)
        if not handled:
            return False
        emit_service_result(ctx, sid, emit, (handled, err, emits, broadcasts))
        return True
    
    The helper will:
      1. Emit error message if present
      2. Emit all messages to the acting player
      3. Broadcast messages to rooms (excluding acting player)
    """
    handled, error_msg, emits, broadcasts = service_result
    
    MESSAGE_OUT = ctx.message_out
    
    # Emit error if present (takes precedence over emits)
    if error_msg:
        emit_fn(MESSAGE_OUT, {'type': 'error', 'content': error_msg})
        return
    
    # Emit all messages to acting player
    for payload in emits:
        emit_fn(MESSAGE_OUT, payload)
    
    # Broadcast to rooms (excluding the acting player)
    for room_id, payload in broadcasts:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
