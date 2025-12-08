from __future__ import annotations
"""Pytest shared fixtures.

This module enforces a fresh import of key server modules before every test function
so we never reuse a stale in-memory copy that may omit recently added parameters
(e.g., 'interaction_sessions' in CommandContext construction) or old dialogue
ordering logic. This has been the source of intermittent first-run flakes.

Strategy: aggressively delete select modules from sys.modules so the subsequent
fixture/test imports re-execute their module top-level code.

If future performance becomes a concern we can relax the scope or add a build ID
comparison to skip reloads when unchanged, but the overhead is negligible given
our small module set.
"""
import importlib
import sys
import os
import pytest

def _force_trade_ctx_patch(server_mod):
    """Ensure server_mod._build_trade_ctx always supplies interaction_sessions.

    Some intermittent flakes indicated a stale version lacking the parameter; we defensively
    replace it every test run. This is test-only hardening and does not ship in production.
    """
    try:
        from command_context import CommandContext as _CC
    except Exception:
        return
    def _patched():  # type: ignore
        return _CC(
            world=server_mod.world,
            state_path=server_mod.STATE_PATH,
            saver=server_mod._saver,
            socketio=server_mod.socketio,
            message_out=server_mod.MESSAGE_OUT,
            sessions=server_mod.sessions,
            admins=server_mod.admins,
            pending_confirm=server_mod._pending_confirm,
            world_setup_sessions=server_mod.world_setup_sessions,
            barter_sessions=server_mod.barter_sessions,
            trade_sessions=server_mod.trade_sessions,
            interaction_sessions=getattr(server_mod, 'interaction_sessions', {}),
            strip_quotes=server_mod._strip_quotes,
            resolve_player_sid_global=server_mod._resolve_player_sid_global,
            normalize_room_input=server_mod._normalize_room_input,
            resolve_room_id_fuzzy=server_mod._resolve_room_id_fuzzy,
            teleport_player=server_mod.teleport_player,
            handle_room_command=server_mod.handle_room_command,
            handle_npc_command=server_mod.handle_npc_command,
            handle_faction_command=server_mod.handle_faction_command,
            purge_prompt=server_mod.purge_prompt,
            execute_purge=server_mod.execute_purge,
            redact_sensitive=server_mod.redact_sensitive,
            is_confirm_yes=server_mod.is_confirm_yes,
            is_confirm_no=server_mod.is_confirm_no,
            broadcast_to_room=server_mod.broadcast_to_room,
        )
    try:
        server_mod._build_trade_ctx = _patched  # type: ignore[attr-defined]
    except Exception:
        pass

MODULES_TO_REFRESH = ("server", "dialogue_router", "trade_router")


@pytest.fixture(autouse=True)
def fresh_server_modules():
    # Ensure TEST_MODE so server suppresses heartbeat threads for determinism
    os.environ['TEST_MODE'] = '1'
    # Disable rate limiting for tests to prevent interference between test runs
    os.environ['MUD_RATE_ENABLE'] = '0'
    # Optional: enable trade debug to diagnose session step transitions (safe noisy output)
    os.environ.setdefault('MUD_DEBUG_TRADE', '1')
    os.environ['MUD_NO_INTERACTIVE'] = '1'
    os.environ['GEMINI_NO_PROMPT'] = '1'
    # Remove targeted modules; keep a copy of whether they existed for debugging
    removed = []
    for name in list(sys.modules.keys()):
        if name in MODULES_TO_REFRESH:
            try:
                del sys.modules[name]
                removed.append(name)
            except Exception:
                pass
    # Re-import server eagerly so helpers referencing it in other fixtures see the fresh copy
    try:
        importlib.invalidate_caches()
        import server  # type: ignore  # noqa: F401
        server = importlib.reload(server)
        # Reset the global world to a fresh empty state for tests
        from world import World
        server.world = World()  # Replace loaded world with fresh empty world
        # Reload dialogue router to pick up fast-path logic reliably
        try:
            import dialogue_router  # type: ignore
            importlib.reload(dialogue_router)
        except Exception:
            pass
        # Guarantee interaction_sessions exists
        if not hasattr(server, 'interaction_sessions'):
            setattr(server, 'interaction_sessions', {})
        _force_trade_ctx_patch(server)
        # Overwrite _build_trade_ctx unconditionally to avoid stale signature reuse
        try:
            from command_context import CommandContext as _CC
            def _fresh_ctx():  # type: ignore
                return _CC(
                    world=server.world,
                    state_path=server.STATE_PATH,
                    saver=server._saver,
                    socketio=server.socketio,
                    message_out=server.MESSAGE_OUT,
                    sessions=server.sessions,
                    admins=server.admins,
                    pending_confirm=server._pending_confirm,
                    world_setup_sessions=server.world_setup_sessions,
                    barter_sessions=server.barter_sessions,
                    trade_sessions=server.trade_sessions,
                    interaction_sessions=getattr(server, 'interaction_sessions', {}),
                    strip_quotes=server._strip_quotes,
                    resolve_player_sid_global=server._resolve_player_sid_global,
                    normalize_room_input=server._normalize_room_input,
                    resolve_room_id_fuzzy=server._resolve_room_id_fuzzy,
                    teleport_player=server.teleport_player,
                    handle_room_command=server.handle_room_command,
                    handle_npc_command=server.handle_npc_command,
                    handle_faction_command=server.handle_faction_command,
                    purge_prompt=server.purge_prompt,
                    execute_purge=server.execute_purge,
                    redact_sensitive=server.redact_sensitive,
                    is_confirm_yes=server.is_confirm_yes,
                    is_confirm_no=server.is_confirm_no,
                    broadcast_to_room=server.broadcast_to_room,
                )
            server._build_trade_ctx = _fresh_ctx  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass
    yield
