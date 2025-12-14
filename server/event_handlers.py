"""Socket.IO event handlers for WebSocket connections.

This module contains the event handlers for Socket.IO connections:
- connect: Initial client connection and welcome
- disconnect: Client disconnection and cleanup

The main message handler (handle_message) and command handler (handle_command)
remain in server.py due to their extensive dependencies.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Set

from safe_utils import safe_call, safe_call_with_default
from concurrency_utils import atomic_many


class EventHandlerContext:
    """Context object holding dependencies for event handlers."""
    
    def __init__(
        self,
        world: Any,
        socketio: Any,
        emit: Callable,
        get_sid: Callable,
        broadcast_to_room: Callable,
        sessions: Dict[str, str],
        admins: Set[str],
        auth_sessions: Dict[str, dict],
        barter_sessions: Dict[str, dict],
        trade_sessions: Dict[str, dict],
        interaction_sessions: Dict[str, dict],
        ascii_art: str | None = None,
        message_out: str = 'message',
        env_str: Callable = lambda name, default: default,
    ):
        self.world = world
        self.socketio = socketio
        self.emit = emit
        self.get_sid = get_sid
        self.broadcast_to_room = broadcast_to_room
        self.sessions = sessions
        self.admins = admins
        self.auth_sessions = auth_sessions
        self.barter_sessions = barter_sessions
        self.trade_sessions = trade_sessions
        self.interaction_sessions = interaction_sessions
        self.ascii_art = ascii_art
        self.message_out = message_out
        self.env_str = env_str


# Global context
_ctx: EventHandlerContext | None = None


def init_event_handlers(ctx: EventHandlerContext) -> None:
    """Initialize the event handlers module with a context object."""
    global _ctx
    _ctx = ctx


def get_context() -> EventHandlerContext:
    """Get the current event handler context."""
    if _ctx is None:
        raise RuntimeError("Event handlers not initialized. Call init_event_handlers() first.")
    return _ctx


def create_connect_handler() -> Callable:
    """Create the connect event handler.
    
    Returns a function that can be registered as a Socket.IO event handler.
    """
    def handle_connect():
        """Called automatically when a new player connects."""
        ctx = get_context()
        print('Client connected!')
        sid = ctx.get_sid()
        
        # Show ASCII art banner if available
        if ctx.ascii_art:
            safe_call(ctx.emit, ctx.message_out, {
                'type': 'system', 
                'content': ctx.ascii_art
            })
        
        # Welcome banner with world name if set up
        try:
            welcome_text = 'Welcome, traveler.'
            if getattr(ctx.world, 'setup_complete', False):
                nm = getattr(ctx.world, 'world_name', None)
                if isinstance(nm, str) and nm.strip():
                    nm_clean = nm.strip()
                    welcome_text = f"Welcome to {nm_clean}, Traveler."
                    ctx.emit(ctx.message_out, {'type': 'system', 'content': welcome_text})
                    
                    # Immersive introduction
                    try:
                        desc = getattr(ctx.world, 'world_description', None)
                        conflict = getattr(ctx.world, 'world_conflict', None)
                        parts = [f"You arrive in [b]{nm_clean}[/b]."]
                        if isinstance(desc, str) and desc.strip():
                            parts.append(desc.strip())
                        if isinstance(conflict, str) and conflict.strip():
                            parts.append(f"Yet all is not well: {conflict.strip()}")
                        if len(parts) > 1:
                            paragraph = " ".join(parts)
                            ctx.emit(ctx.message_out, {
                                'type': 'system', 
                                'content': f"[i]{paragraph}[/i]"
                            })
                    except Exception:
                        pass
                else:
                    ctx.emit(ctx.message_out, {'type': 'system', 'content': welcome_text})
            else:
                ctx.emit(ctx.message_out, {'type': 'system', 'content': welcome_text})
        except Exception:
            ctx.emit(ctx.message_out, {'type': 'system', 'content': 'Welcome, traveler.'})
        
        # Auth prompt
        ctx.emit(ctx.message_out, {
            'type': 'system',
            'content': 'Type "create" to forge a new character, "login" to sign in, or "list" to see existing characters. You can also use /auth commands if you prefer.'
        })
        
        # Config for client
        try:
            max_len = int(ctx.env_str('MUD_MAX_MESSAGE_LEN', '1000'))
            ctx.emit(ctx.message_out, {
                'type': 'system', 
                'content': f'[config] MAX_MESSAGE_LEN={max_len}'
            })
        except Exception:
            pass
    
    return handle_connect


def create_disconnect_handler() -> Callable:
    """Create the disconnect event handler.
    
    Returns a function that can be registered as a Socket.IO event handler.
    """
    def handle_disconnect():
        """Called automatically when a player disconnects."""
        ctx = get_context()
        print('Client disconnected!')
        
        try:
            sid = ctx.get_sid()
            if sid:
                # Announce departure
                try:
                    player_obj = ctx.world.players.get(sid)
                    if player_obj:
                        ctx.broadcast_to_room(player_obj.room_id, {
                            'type': 'system',
                            'content': f"{player_obj.sheet.display_name} leaves."
                        }, exclude_sid=sid)
                except Exception:
                    pass
                
                # Clean up session state
                with atomic_many([
                    'sessions', 'admins', 'auth_sessions', 'barter_sessions',
                    'trade_sessions', 'interaction_sessions', 'setup_sessions'
                ]):
                    if sid in ctx.admins:
                        ctx.admins.discard(sid)
                    ctx.sessions.pop(sid, None)
                    safe_call(ctx.auth_sessions.pop, sid, None)
                    safe_call(ctx.barter_sessions.pop, sid, None)
                    safe_call(ctx.trade_sessions.pop, sid, None)
                    safe_call(ctx.interaction_sessions.pop, sid, None)
                
                ctx.world.remove_player(sid)
        except Exception:
            pass
    
    return handle_disconnect


def register_handlers(socketio: Any, message_in: str = 'message_to_server') -> None:
    """Register connect and disconnect handlers on the socketio instance.
    
    Note: The main message handler should still be registered in server.py
    as it has too many dependencies to extract cleanly.
    
    Args:
        socketio: The Flask-SocketIO instance
        message_in: The event name for incoming messages (unused here, for reference)
    """
    ctx = get_context()
    
    # Register handlers
    socketio.on_event('connect', create_connect_handler())
    socketio.on_event('disconnect', create_disconnect_handler())


# Exported functions
__all__ = [
    'EventHandlerContext',
    'init_event_handlers',
    'get_context',
    'create_connect_handler',
    'create_disconnect_handler',
    'register_handlers',
]
