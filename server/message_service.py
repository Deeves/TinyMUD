"""Message formatting and broadcast service.

This module centralizes message broadcasting and formatting logic
to keep server.py clean and enable reuse across services.
"""
from __future__ import annotations

from typing import Any

from safe_utils import safe_call


# Message event types
MESSAGE_IN = 'message_to_server'
MESSAGE_OUT = 'message'


class MessageContext:
    """Context object holding messaging dependencies."""
    
    def __init__(
        self,
        world: Any,
        socketio: Any,
    ):
        self.world = world
        self.socketio = socketio


# Global context
_ctx: MessageContext | None = None


def init_message_service(ctx: MessageContext) -> None:
    """Initialize the message service with a context object."""
    global _ctx
    _ctx = ctx


def get_context() -> MessageContext:
    """Get the current message service context."""
    if _ctx is None:
        raise RuntimeError("Message service not initialized. Call init_message_service() first.")
    return _ctx


def broadcast_to_room(room_id: str, payload: dict, exclude_sid: str | None = None) -> None:
    """Broadcast a payload to all players in a room, optionally excluding one.
    
    Args:
        room_id: The room ID to broadcast to
        payload: The message payload dict
        exclude_sid: Optional session ID to exclude from broadcast
    """
    ctx = get_context()
    
    def _broadcast():
        room = ctx.world.rooms.get(room_id)
        if not room:
            return
        sids = getattr(room, 'players', set()) or set()
        for sid in list(sids):
            if sid == exclude_sid:
                continue
            try:
                ctx.socketio.emit(MESSAGE_OUT, payload, to=sid)
            except Exception:
                pass
    
    safe_call(_broadcast)


def emit_to_player(sid: str, event: str, payload: dict) -> None:
    """Emit a message to a specific player.
    
    Args:
        sid: The player's session ID
        event: The event name (usually MESSAGE_OUT)
        payload: The message payload dict
    """
    ctx = get_context()
    safe_call(ctx.socketio.emit, event, payload, to=sid)


def broadcast_all(payload: dict) -> None:
    """Broadcast a message to all connected players.
    
    Args:
        payload: The message payload dict
    """
    ctx = get_context()
    safe_call(ctx.socketio.emit, MESSAGE_OUT, payload)


def format_system_message(content: str) -> dict:
    """Format a system message payload.
    
    Args:
        content: The message content
        
    Returns:
        A formatted message payload dict
    """
    return {'type': 'system', 'content': content}


def format_npc_message(npc_name: str, content: str) -> dict:
    """Format an NPC speech message payload.
    
    Args:
        npc_name: The NPC's display name
        content: The speech content
        
    Returns:
        A formatted message payload dict
    """
    return {'type': 'npc', 'name': npc_name, 'content': content}


def format_player_message(player_name: str, content: str) -> dict:
    """Format a player speech message payload.
    
    Args:
        player_name: The player's display name
        content: The speech content
        
    Returns:
        A formatted message payload dict
    """
    return {'type': 'player', 'name': player_name, 'content': content}


def format_emote(actor_name: str, action: str) -> dict:
    """Format an emote message payload.
    
    Args:
        actor_name: The actor's display name
        action: The emote action text
        
    Returns:
        A formatted message payload dict with italicized content
    """
    return {'type': 'system', 'content': f"[i]{actor_name} {action}[/i]"}


# Exported functions
__all__ = [
    'MESSAGE_IN',
    'MESSAGE_OUT',
    'MessageContext',
    'init_message_service',
    'get_context',
    'broadcast_to_room',
    'emit_to_player',
    'broadcast_all',
    'format_system_message',
    'format_npc_message',
    'format_player_message',
    'format_emote',
]
