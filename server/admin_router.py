from __future__ import annotations

"""Admin (and closely related) slash command handling.

Migrated commands:
  /kick, /teleport, /bring, /purge, /worldstate, /safety, /setup,
  /room <...>, /npc <...>, /faction <...>, /object <...>

Behavior is intentionally preserved to keep existing tests green.
Future improvements (after full modular carve‑out):
  - Dedicated unit tests per handler.
  - Central registry + help text auto-generation.
  - Metrics / tracing decorators.
"""

from typing import Any
import json

from command_context import CommandContext, EmitFn
from persistence_utils import save_world


def _emit_error(emit: EmitFn, message_out: str, text: str) -> None:
    emit(message_out, {'type': 'error', 'content': text})


def _emit_system(emit: EmitFn, message_out: str, text: str) -> None:
    emit(message_out, {'type': 'system', 'content': text})


def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    if not cmd:
        return False
    admin_cmds = {
        'kick', 'teleport', 'bring', 'purge', 'worldstate', 'safety', 'setup',
        'room', 'npc', 'faction', 'object'
    }
    if cmd not in admin_cmds:
        return False

    if cmd in admin_cmds and (sid is None or sid not in ctx.admins):
        _emit_error(emit, ctx.message_out, 'Admin command. Admin rights required.')
        return True

    world = ctx.world
    MESSAGE_OUT = ctx.message_out

    # /kick
    if cmd == 'kick':
        if not args:
            _emit_error(emit, MESSAGE_OUT, 'Usage: /kick <playerName>')
            return True
        target_name = ctx.strip_quotes(" ".join(args))
        okp, perr, target_sid, _resolved_name = ctx.resolve_player_sid_global(world, target_name)
        if not okp or target_sid is None:
            _emit_error(emit, MESSAGE_OUT, perr or f"Player '{target_name}' not found.")
            return True
        if target_sid == sid:
            _emit_error(emit, MESSAGE_OUT, 'You cannot kick yourself.')
            return True
        from flask_socketio import disconnect
        try:
            disconnect(target_sid, namespace="/")
            _emit_system(emit, MESSAGE_OUT, f"Kicked '{target_name}'.")
        except Exception as e:  # pragma: no cover
            _emit_error(emit, MESSAGE_OUT, f"Failed to kick '{target_name}': {e}")
        return True

    # /teleport
    if cmd == 'teleport':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        if not args:
            _emit_error(emit, MESSAGE_OUT, 'Usage: /teleport <room_id>  or  /teleport <playerName> | <room_id>')
            return True
        target_sid = sid
        target_room = None
        joined_args = " ".join(args)
        if '|' in joined_args:
            try:
                player_name, target_room = [ctx.strip_quotes(p.strip()) for p in joined_args.split('|', 1)]
            except Exception:
                _emit_error(emit, MESSAGE_OUT, 'Usage: /teleport <playerName> | <room_id>')
                return True
            okp, perr, tsid, _pname = ctx.resolve_player_sid_global(world, player_name)
            if not okp or not tsid:
                _emit_error(emit, MESSAGE_OUT, perr or f"Player '{player_name}' not found.")
                return True
            target_sid = tsid
        else:
            target_room = ctx.strip_quotes(joined_args.strip())
        if not target_room:
            _emit_error(emit, MESSAGE_OUT, 'Target room id required.')
            return True
        rok, rerr, resolved = ctx.resolve_room_id_fuzzy(sid, target_room)
        if not rok or not resolved:
            _emit_error(emit, MESSAGE_OUT, rerr or 'Room not found.')
            return True
        ok, err, emits2, broadcasts2 = ctx.teleport_player(world, target_sid, resolved)
        if not ok:
            _emit_error(emit, MESSAGE_OUT, err or 'Teleport failed.')
            return True
        for payload in emits2:
            try:
                if target_sid == sid:
                    emit(MESSAGE_OUT, payload)
                else:
                    ctx.socketio.emit(MESSAGE_OUT, payload, to=target_sid)
            except Exception:  # pragma: no cover
                pass
        for room_id, payload in broadcasts2:
            ctx.broadcast_to_room(room_id, payload, target_sid)
        if target_sid != sid:
            _emit_system(emit, MESSAGE_OUT, 'Teleport complete.')
        return True

    # /bring
    if cmd == 'bring':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        if not args:
            _emit_error(emit, MESSAGE_OUT, 'Usage: /bring <playerName>')
            return True
        player_name = ctx.strip_quotes(" ".join(args).split('|', 1)[0].strip())
        okp, perr, tsid, _pname = ctx.resolve_player_sid_global(world, player_name)
        if not okp or not tsid:
            _emit_error(emit, MESSAGE_OUT, perr or f"Player '{player_name}' not found.")
            return True
        okh, erh, here_room = ctx.normalize_room_input(sid, 'here')
        if not okh or not here_room:
            _emit_error(emit, MESSAGE_OUT, erh or 'You are nowhere.')
            return True
        ok, err, emits2, broadcasts2 = ctx.teleport_player(world, tsid, here_room)
        if not ok:
            _emit_error(emit, MESSAGE_OUT, err or 'Bring failed.')
            return True
        for payload in emits2:
            try:
                ctx.socketio.emit(MESSAGE_OUT, payload, to=tsid)
            except Exception:  # pragma: no cover
                pass
        for room_id, payload in broadcasts2:
            ctx.broadcast_to_room(room_id, payload, tsid)
        _emit_system(emit, MESSAGE_OUT, 'Bring complete.')
        return True

    # /purge
    if cmd == 'purge':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        ctx.pending_confirm[sid] = 'purge'
        emit(MESSAGE_OUT, ctx.purge_prompt())
        return True

    # /worldstate
    if cmd == 'worldstate':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        try:
            with open(ctx.state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            sanitized = ctx.redact_sensitive(data)
            raw_json = json.dumps(sanitized, ensure_ascii=False, indent=2)
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"[b]world_state.json[/b]\n{raw_json}"})
        except FileNotFoundError:
            _emit_error(emit, MESSAGE_OUT, 'world_state.json not found.')
        except Exception as e:  # pragma: no cover
            _emit_error(emit, MESSAGE_OUT, f'Failed to read world_state.json: {e}')
        return True

    # /safety
    if cmd == 'safety':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        if not args:
            cur = getattr(world, 'safety_level', 'G')
            _emit_system(emit, MESSAGE_OUT, f"Current safety level: [b]{cur}[/b]\nUsage: /safety <G|PG-13|R|OFF>")
            return True
        raw_level = " ".join(args).strip().upper()
        if raw_level in ("HIGH", "G", "ALL-AGES"):
            level = 'G'
        elif raw_level in ("MEDIUM", "PG13", "PG-13", "PG_13", "PG"):
            level = 'PG-13'
        elif raw_level in ("LOW", "R"):
            level = 'R'
        elif raw_level in ("OFF", "NONE", "NO FILTERS", "DISABLE", "DISABLED", "SAFETY FILTERS OFF"):
            level = 'OFF'
        else:
            _emit_error(emit, MESSAGE_OUT, 'Invalid safety level. Use one of: G, PG-13, R, OFF.')
            return True
        try:
            world.safety_level = level  # type: ignore[attr-defined]
            save_world(world, ctx.state_path, debounced=True)
        except Exception:  # pragma: no cover
            pass
        _emit_system(emit, MESSAGE_OUT, f"Safety level set to [b]{level}[/b]. This applies to future AI replies.")
        return True

    # /setup
    if cmd == 'setup':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        if getattr(world, 'setup_complete', False):
            _emit_system(emit, MESSAGE_OUT, 'Setup is already complete. Use /purge to reset the world if you want to run setup again.')
            return True
        from setup_service import begin_setup as _setup_begin  # type: ignore
        # For now reuse world_setup_sessions dict if present; else allocate ephemeral
        sessions = getattr(world, 'world_setup_sessions', {})
        for p in _setup_begin(sessions, sid):
            emit(MESSAGE_OUT, p)
        return True

    # /object
    if cmd == 'object':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        if not args:
            _emit_system(emit, MESSAGE_OUT, 'Usage: /object <createtemplateobject | createobject <room> | <name> | <desc> | <tags or template_key> | listtemplates | viewtemplate <key> | deletetemplate <key>>')
            return True
        sub = args[0].lower()
        from object_service import (
            create_object as _obj_create,
            list_templates as _obj_list_templates,
            view_template as _obj_view_template,
            delete_template as _obj_delete_template,
        )  # type: ignore
        if sub == 'createobject':
            if sid not in world.players:
                _emit_error(emit, MESSAGE_OUT, 'Please authenticate first to create objects.')
                return True
            handled, err, emits3 = _obj_create(world, ctx.state_path, sid, args[1:])
            if err:
                _emit_error(emit, MESSAGE_OUT, err)
                return True
            for payload in emits3:
                emit(MESSAGE_OUT, payload)
            return True
        if sub == 'createtemplateobject':
            if not hasattr(world, 'object_template_sessions'):
                world.object_template_sessions = {}  # type: ignore[attr-defined]
            world.object_template_sessions[sid] = {"step": "template_key", "temp": {}}  # type: ignore[attr-defined]
            _emit_system(emit, MESSAGE_OUT, 'Creating a new Object template. Type cancel to abort at any time.')
            _emit_system(emit, MESSAGE_OUT, 'Enter a unique template key (letters, numbers, underscores), e.g., sword_bronze:')
            return True
        if sub == 'listtemplates':
            templates = _obj_list_templates(world)
            _emit_system(emit, MESSAGE_OUT, 'No object templates saved.' if not templates else 'Object templates: ' + ", ".join(templates))
            return True
        if sub == 'viewtemplate':
            if len(args) < 2:
                _emit_error(emit, MESSAGE_OUT, 'Usage: /object viewtemplate <key>')
                return True
            key = args[1]
            okv, ev, raw_t = _obj_view_template(world, key)
            if not okv:
                _emit_error(emit, MESSAGE_OUT, ev or 'Template not found.')
                return True
            _emit_system(emit, MESSAGE_OUT, f"[b]{key}[/b]\n{raw_t}")
            return True
        if sub == 'deletetemplate':
            if len(args) < 2:
                _emit_error(emit, MESSAGE_OUT, 'Usage: /object deletetemplate <key>')
                return True
            key = args[1]
            handled, err2, emitsD = _obj_delete_template(world, ctx.state_path, key)
            if err2:
                _emit_error(emit, MESSAGE_OUT, err2)
                return True
            for payload in emitsD:
                emit(MESSAGE_OUT, payload)
            return True
        _emit_error(emit, MESSAGE_OUT, 'Unknown /object subcommand. Use createobject, createtemplateobject, listtemplates, viewtemplate, or deletetemplate.')
        return True

    # /room
    if cmd == 'room':
        handled, err, emits2 = ctx.handle_room_command(world, ctx.state_path, args, sid)
        if err:
            _emit_error(emit, MESSAGE_OUT, err)
            return True
        for payload in emits2:
            emit(MESSAGE_OUT, payload)
        return True if handled else False

    # /faction
    if cmd == 'faction':
        if sid is None:
            _emit_error(emit, MESSAGE_OUT, 'Not connected.')
            return True
        if sid not in ctx.admins:
            _emit_error(emit, MESSAGE_OUT, 'Admin command. Admin rights required.')
            return True
        handled, err, emits2 = ctx.handle_faction_command(world, ctx.state_path, sid, args)
        if err:
            _emit_error(emit, MESSAGE_OUT, err)
            return True
        for payload in emits2:
            emit(MESSAGE_OUT, payload)
        return True if handled else False

    # /npc
    if cmd == 'npc':
        handled, err, emits2 = ctx.handle_npc_command(world, ctx.state_path, sid, args)
        if err:
            _emit_error(emit, MESSAGE_OUT, err)
            return True
        for payload in emits2:
            emit(MESSAGE_OUT, payload)
        return True if handled else False

    return False
