"""Message handler for incoming Socket.IO messages.

This module contains the main message handler that processes all incoming
chat messages, commands, and interactive flows from clients.

The handler is complex due to the many wizard flows (auth, setup, trade, etc.)
and command dispatching it needs to handle.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Set, cast

from safe_utils import safe_call, safe_call_with_default


class MessageHandlerContext:
    """Context object holding all dependencies for message handling."""
    
    def __init__(
        self,
        # Core world state
        world: Any,
        state_path: str,
        saver: Any,
        socketio: Any,
        
        # Session state
        sessions: Dict[str, str],
        admins: Set[str],
        pending_confirm: Dict[str, str],
        auth_sessions: Dict[str, dict],
        world_setup_sessions: Dict[str, dict],
        object_template_sessions: Dict[str, dict],
        barter_sessions: Dict[str, dict],
        trade_sessions: Dict[str, dict],
        interaction_sessions: Dict[str, dict],
        
        # Emit and broadcast
        emit: Callable,
        get_sid: Callable,
        broadcast_to_room: Callable,
        disconnect: Callable,
        
        # Message constants
        message_in: str,
        message_out: str,
        
        # Utility functions
        env_str: Callable,
        strip_quotes: Callable,
        
        # Resolution helpers
        resolve_player_sid_global: Callable,
        normalize_room_input: Callable,
        resolve_room_id_fuzzy: Callable,
        
        # Rate limiter
        simple_rate_limiter: Any,
        
        # Service functions
        teleport_player: Callable,
        handle_room_command: Callable,
        handle_npc_command: Callable,
        handle_faction_command: Callable,
        
        # Admin functions
        purge_prompt: Callable,
        execute_purge: Callable,
        prepare_purge_snapshot_sids: Callable,
        redact_sensitive: Callable,
        is_confirm_yes: Callable,
        is_confirm_no: Callable,
        
        # Auth/setup handlers
        auth_handle: Callable,
        setup_handle: Callable,
        setup_begin: Callable,
        
        # Dice
        dice_roll: Callable,
        dice_error: type,
        
        # Command handler
        handle_command: Callable,
        
        # Save function
        save_world: Callable,
    ):
        self.world = world
        self.state_path = state_path
        self.saver = saver
        self.socketio = socketio
        self.sessions = sessions
        self.admins = admins
        self.pending_confirm = pending_confirm
        self.auth_sessions = auth_sessions
        self.world_setup_sessions = world_setup_sessions
        self.object_template_sessions = object_template_sessions
        self.barter_sessions = barter_sessions
        self.trade_sessions = trade_sessions
        self.interaction_sessions = interaction_sessions
        self.emit = emit
        self.get_sid = get_sid
        self.broadcast_to_room = broadcast_to_room
        self.disconnect = disconnect
        self.message_in = message_in
        self.message_out = message_out
        self.env_str = env_str
        self.strip_quotes = strip_quotes
        self.resolve_player_sid_global = resolve_player_sid_global
        self.normalize_room_input = normalize_room_input
        self.resolve_room_id_fuzzy = resolve_room_id_fuzzy
        self.simple_rate_limiter = simple_rate_limiter
        self.teleport_player = teleport_player
        self.handle_room_command = handle_room_command
        self.handle_npc_command = handle_npc_command
        self.handle_faction_command = handle_faction_command
        self.purge_prompt = purge_prompt
        self.execute_purge = execute_purge
        self.prepare_purge_snapshot_sids = prepare_purge_snapshot_sids
        self.redact_sensitive = redact_sensitive
        self.is_confirm_yes = is_confirm_yes
        self.is_confirm_no = is_confirm_no
        self.auth_handle = auth_handle
        self.setup_handle = setup_handle
        self.setup_begin = setup_begin
        self.dice_roll = dice_roll
        self.dice_error = dice_error
        self.handle_command = handle_command
        self.save_world = save_world
        
        # Mutable world reference (for purge)
        self._world_ref = [world]
    
    def get_world(self):
        """Get the current world (may have been replaced by purge)."""
        return self._world_ref[0]
    
    def set_world(self, new_world):
        """Set a new world (after purge)."""
        self._world_ref[0] = new_world
        self.world = new_world


# Global context
_ctx: MessageHandlerContext | None = None


def init_message_handler(ctx: MessageHandlerContext) -> None:
    """Initialize the message handler with a context object."""
    global _ctx
    _ctx = ctx


def get_context() -> MessageHandlerContext:
    """Get the current message handler context."""
    if _ctx is None:
        raise RuntimeError("Message handler not initialized. Call init_message_handler() first.")
    return _ctx


def create_message_handler() -> Callable:
    """Create the message event handler.
    
    Returns a function that can be registered as a Socket.IO event handler.
    """
    def handle_message(data):
        """Main chat handler. Triggered when the client emits 'message_to_server'.
        
        Payload shape from client: { 'content': str }
        """
        ctx = get_context()
        world = ctx.get_world()
        
        # Validate payload
        if not isinstance(data, dict) or 'content' not in data:
            ctx.emit(ctx.message_out, {
                'type': 'error',
                'content': 'Invalid payload; expected { "content": string }.'
            })
            return
        
        player_message = data['content']
        
        # Rate limiting and message size cap
        max_len = int(ctx.env_str('MUD_MAX_MESSAGE_LEN', '1000'))
        if isinstance(player_message, str) and len(player_message) > max_len:
            ctx.emit(ctx.message_out, {
                'type': 'error',
                'content': f'Message too long (>{max_len} chars).'
            })
            return
        
        _rate = ctx.simple_rate_limiter.get(ctx.get_sid())
        if not _rate.allow():
            ctx.emit(ctx.message_out, {
                'type': 'error',
                'content': 'You are sending messages too quickly. Please slow down.'
            })
            return
        
        sid = ctx.get_sid()
        
        # Verbose logging
        try:
            sender_label = "unknown"
            if sid in world.players:
                sender_label = world.players[sid].sheet.display_name
            elif sid in ctx.auth_sessions:
                sess = ctx.auth_sessions.get(sid, {})
                temp_name = (sess.get("temp", {}) or {}).get("name")
                mode = sess.get("mode") or "auth"
                step = sess.get("step") or "?"
                if temp_name:
                    sender_label = f"{temp_name} ({mode}:{step})"
                else:
                    sender_label = f"unauthenticated ({mode}:{step})"
            else:
                sender_label = "unauthenticated"
            print(f"From {sender_label} [sid={sid}]: {player_message}")
        except Exception:
            print(f"From [sid={sid}]: {player_message}")
        
        if isinstance(player_message, str):
            text_lower = player_message.strip().lower()
            
            # Pending admin confirmation
            if sid and sid in ctx.pending_confirm:
                action = ctx.pending_confirm.get(sid)
                if text_lower in ("y", "yes"):
                    ctx.pending_confirm.pop(sid, None)
                    if action == 'purge':
                        current_sids = ctx.prepare_purge_snapshot_sids(world)
                        new_world = ctx.execute_purge(ctx.state_path)
                        ctx.set_world(new_world)
                        try:
                            for psid in current_sids:
                                if psid != sid:
                                    ctx.disconnect(psid, namespace="/")
                        except Exception:
                            pass
                        ctx.emit(ctx.message_out, {
                            'type': 'system',
                            'content': 'World purged and reset to factory default.'
                        })
                        return
                    else:
                        ctx.emit(ctx.message_out, {
                            'type': 'error',
                            'content': 'Unknown confirmation action.'
                        })
                        return
                elif text_lower in ("n", "no"):
                    ctx.pending_confirm.pop(sid, None)
                    ctx.emit(ctx.message_out, {
                        'type': 'system',
                        'content': 'Action cancelled.'
                    })
                    return
                else:
                    ctx.emit(ctx.message_out, {
                        'type': 'system',
                        'content': "Please confirm with 'Y' to proceed or 'N' to cancel."
                    })
                    return
            
            # World setup wizard
            if sid and sid in ctx.world_setup_sessions:
                handled, err, emits_list, broadcasts_list = ctx.setup_handle(
                    world, ctx.state_path, sid, player_message, ctx.world_setup_sessions
                )
                if handled:
                    if err:
                        ctx.emit(ctx.message_out, {'type': 'error', 'content': err})
                        return
                    for payload in emits_list:
                        ctx.emit(ctx.message_out, payload)
                    for room_id, payload in broadcasts_list:
                        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
                    return
            
            # Trade/barter flows
            if sid and (sid in ctx.barter_sessions or sid in ctx.trade_sessions):
                import trade_router
                from command_context import CommandContext
                flow_ctx = CommandContext(
                    world=world,
                    state_path=ctx.state_path,
                    saver=ctx.saver,
                    socketio=ctx.socketio,
                    message_out=ctx.message_out,
                    sessions=ctx.sessions,
                    admins=ctx.admins,
                    pending_confirm=ctx.pending_confirm,
                    world_setup_sessions=ctx.world_setup_sessions,
                    barter_sessions=ctx.barter_sessions,
                    trade_sessions=ctx.trade_sessions,
                    interaction_sessions=ctx.interaction_sessions,
                    strip_quotes=ctx.strip_quotes,
                    resolve_player_sid_global=ctx.resolve_player_sid_global,
                    normalize_room_input=ctx.normalize_room_input,
                    resolve_room_id_fuzzy=ctx.resolve_room_id_fuzzy,
                    teleport_player=ctx.teleport_player,
                    handle_room_command=ctx.handle_room_command,
                    handle_npc_command=ctx.handle_npc_command,
                    handle_faction_command=ctx.handle_faction_command,
                    purge_prompt=ctx.purge_prompt,
                    execute_purge=ctx.execute_purge,
                    redact_sensitive=ctx.redact_sensitive,
                    is_confirm_yes=ctx.is_confirm_yes,
                    is_confirm_no=ctx.is_confirm_no,
                    broadcast_to_room=ctx.broadcast_to_room,
                )
                progressed = trade_router.try_handle_flow(flow_ctx, sid, player_message, ctx.emit)
                if progressed:
                    return
            
            # Object template creation wizard
            if sid and sid in ctx.object_template_sessions:
                if _handle_object_template_wizard(ctx, sid, player_message, text_lower):
                    return
            
            # Slash commands
            if player_message.strip().startswith("/"):
                sid = ctx.get_sid()
                ctx.handle_command(sid, player_message.strip())
                return
            
            # Multi-turn auth flow for unauthenticated users
            if sid not in world.players:
                if sid is None:
                    ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Not connected.'})
                    return
                handled, emits2, broadcasts2 = ctx.auth_handle(
                    world, sid, player_message, ctx.sessions, ctx.admins,
                    ctx.state_path, ctx.auth_sessions
                )
                if handled:
                    for payload in emits2:
                        ctx.emit(ctx.message_out, payload)
                    for room_id, payload in broadcasts2:
                        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
                    # First user setup wizard
                    try:
                        if not getattr(world, 'setup_complete', False) and sid in ctx.sessions:
                            uid = ctx.sessions.get(sid)
                            user = world.users.get(uid) if uid else None
                            if user and user.is_admin:
                                ctx.emit(ctx.message_out, {
                                    'type': 'system',
                                    'content': 'You are the first adventurer here and have been made an Admin.'
                                })
                                for p in ctx.setup_begin(ctx.world_setup_sessions, sid):
                                    ctx.emit(ctx.message_out, p)
                                return
                    except Exception:
                        pass
                    return
            
            # Build CommandContext for routers
            from command_context import CommandContext as _CmdCtx
            _early_ctx = _CmdCtx(
                world=world,
                state_path=ctx.state_path,
                saver=ctx.saver,
                socketio=ctx.socketio,
                message_out=ctx.message_out,
                sessions=ctx.sessions,
                admins=ctx.admins,
                pending_confirm=ctx.pending_confirm,
                world_setup_sessions=ctx.world_setup_sessions,
                barter_sessions=ctx.barter_sessions,
                trade_sessions=ctx.trade_sessions,
                interaction_sessions=ctx.interaction_sessions,
                strip_quotes=ctx.strip_quotes,
                resolve_player_sid_global=ctx.resolve_player_sid_global,
                normalize_room_input=ctx.normalize_room_input,
                resolve_room_id_fuzzy=ctx.resolve_room_id_fuzzy,
                teleport_player=ctx.teleport_player,
                handle_room_command=ctx.handle_room_command,
                handle_npc_command=ctx.handle_npc_command,
                handle_faction_command=ctx.handle_faction_command,
                purge_prompt=ctx.purge_prompt,
                execute_purge=ctx.execute_purge,
                redact_sensitive=ctx.redact_sensitive,
                is_confirm_yes=ctx.is_confirm_yes,
                is_confirm_no=ctx.is_confirm_no,
                broadcast_to_room=ctx.broadcast_to_room,
            )
            
            # Interaction router
            import interaction_router
            if interaction_router.try_handle_flow(_early_ctx, sid, player_message, text_lower, ctx.emit):
                return
            
            # Movement router
            import movement_router
            if movement_router.try_handle_flow(_early_ctx, sid, player_message, text_lower, ctx.emit):
                return
            
            # Roll command
            if text_lower == "roll" or text_lower.startswith("roll "):
                if sid not in world.players:
                    ctx.emit(ctx.message_out, {
                        'type': 'error',
                        'content': 'Please authenticate first to roll dice.'
                    })
                    return
                raw = player_message.strip()
                arg = raw[4:].strip() if len(raw) > 4 else ""
                if not arg:
                    ctx.emit(ctx.message_out, {
                        'type': 'error',
                        'content': 'Usage: roll <dice expression> [| Private]'
                    })
                    return
                priv = False
                if '|' in arg:
                    left, right = arg.split('|', 1)
                    expr = left.strip()
                    if right.strip().lower() == 'private':
                        priv = True
                else:
                    expr = arg
                try:
                    result = ctx.dice_roll(expr)
                except ctx.dice_error as e:
                    ctx.emit(ctx.message_out, {'type': 'error', 'content': f'Dice error: {e}'})
                    return
                res_text = f"{result.expression} = {result.total}"
                player_obj = world.players.get(sid)
                pname = player_obj.sheet.display_name if player_obj else 'Someone'
                if priv:
                    ctx.emit(ctx.message_out, {
                        'type': 'system',
                        'content': f"You secretly pull out the sacred geometric stones from your pocket and roll {res_text}."
                    })
                    return
                ctx.emit(ctx.message_out, {
                    'type': 'system',
                    'content': f"You pull out the sacred geometric stones from your pocket and roll {res_text}."
                })
                if player_obj:
                    ctx.broadcast_to_room(player_obj.room_id, {
                        'type': 'system',
                        'content': f"{pname} pulls out the sacred geometric stones from their pocket and rolls {res_text}."
                    }, exclude_sid=sid)
                return
            
            # Dialogue router
            import dialogue_router
            if _early_ctx and dialogue_router.try_handle_flow(_early_ctx, sid or '', player_message, ctx.emit):
                return
            
            return
        return
    
    return handle_message


def _handle_object_template_wizard(ctx, sid: str, player_message: str, text_lower: str) -> bool:
    """Handle the object template creation wizard flow.
    
    Returns True if the message was handled.
    """
    import json as _json
    
    sid_str = cast(str, sid)
    sess = ctx.object_template_sessions.get(sid_str, {"step": "template_key", "temp": {}})
    step = sess.get("step")
    temp = sess.get("temp", {})
    text_stripped = player_message.strip()
    text_lower2 = text_stripped.lower()
    
    def _is_skip(s: str) -> bool:
        sl = (s or "").strip().lower()
        return sl == "" or sl in ("skip", "none", "-")
    
    def _echo_raw(s: str) -> None:
        if s and not _is_skip(s):
            ctx.emit(ctx.message_out, {'type': 'system', 'content': s})
    
    if text_lower2 in ("cancel",):
        ctx.object_template_sessions.pop(sid_str, None)
        ctx.emit(ctx.message_out, {'type': 'system', 'content': 'Object template creation cancelled.'})
        return True
    
    def _ask_next(current: str) -> None:
        sess['step'] = current
        ctx.object_template_sessions[sid_str] = sess
        prompts = {
            'template_key': "Enter a unique template key (letters, numbers, underscores), e.g., sword_bronze:",
            'display_name': "Enter display name (required), e.g., Bronze Sword:",
            'description': "Enter a short description (required):",
            'object_tags': "Enter comma-separated tags (optional; default: small). Examples: weapon,cutting damage,small:",
            'material_tag': "Enter material tag (optional), e.g., bronze (Enter to skip or type 'skip'):",
            'value': "Enter value in coins (optional integer; Enter to skip or type 'skip'):",
            'satiation_value': "Enter hunger satiation value (optional int; Enter to skip), e.g., 25 for food:",
            'hydration_value': "Enter thirst hydration value (optional int; Enter to skip), e.g., 25 for drink:",
            'durability': "Enter durability (optional integer; Enter to skip or type 'skip'):",
            'quality': "Enter quality (optional), e.g., average (Enter to skip or type 'skip'):",
            'loot_location_hint': "Enter loot location hint as JSON object or a plain name (optional). Examples: {\"display_name\": \"Old Chest\"} or Old Chest. Enter to skip:",
            'crafting_recipe': "Enter crafting recipe as JSON array of objects or comma-separated names (optional). Examples: [{\"display_name\":\"Bronze Ingot\"}],Hammer or Enter to skip (or type 'skip'):",
            'deconstruct_recipe': "Enter deconstruct recipe as JSON array of objects or comma-separated names (optional). Enter to skip (or type 'skip'):",
            'confirm': "Type 'save' to save this template, or 'cancel' to abort.",
        }
        ctx.emit(ctx.message_out, {'type': 'system', 'content': prompts.get(current, '...')})
    
    def _parse_recipe_input(s: str):
        if _is_skip(s):
            return []
        try:
            parsed = _json.loads(s)
            if isinstance(parsed, list):
                out = []
                for el in parsed:
                    if isinstance(el, dict):
                        out.append(el)
                    elif isinstance(el, (str, int)):
                        out.append({"display_name": str(el)})
                return out
            if isinstance(parsed, dict):
                return [parsed]
            return [{"display_name": str(parsed)}]
        except Exception:
            names = [p.strip() for p in s.split(',') if p.strip()]
            return [{"display_name": n} for n in names]
    
    world = ctx.get_world()
    
    if step == 'template_key':
        key = re.sub(r"[^A-Za-z0-9_]+", "_", text_stripped)
        if not key:
            ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Template key cannot be empty.'})
            return True
        if key in getattr(world, 'object_templates', {}):
            ctx.emit(ctx.message_out, {'type': 'error', 'content': f"Template key '{key}' already exists. Choose another."})
            return True
        temp['key'] = key
        sess['temp'] = temp
        _ask_next('display_name')
        return True
    
    if step == 'display_name':
        name = text_stripped
        if len(name) < 1:
            ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Display name is required.'})
            return True
        temp['display_name'] = name
        sess['temp'] = temp
        _ask_next('description')
        return True
    
    if step == 'description':
        if not text_stripped or _is_skip(text_stripped):
            ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Description is required.'})
            _ask_next('description')
            return True
        temp['description'] = text_stripped
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('object_tags')
        return True
    
    if step == 'object_tags':
        if not _is_skip(text_stripped):
            tags = [t.strip() for t in text_stripped.split(',') if t.strip()]
        else:
            tags = ['small']
        temp['object_tags'] = list(dict.fromkeys(tags))
        sess['temp'] = temp
        _ask_next('material_tag')
        return True
    
    if step == 'material_tag':
        temp['material_tag'] = None if _is_skip(text_stripped) else text_stripped
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('value')
        return True
    
    if step == 'value':
        if _is_skip(text_stripped):
            temp['value'] = None
        else:
            try:
                temp['value'] = int(text_stripped)
            except Exception:
                ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        sess['temp'] = temp
        _ask_next('satiation_value')
        return True
    
    if step == 'satiation_value':
        if _is_skip(text_stripped):
            temp['satiation_value'] = None
        else:
            try:
                temp['satiation_value'] = int(text_stripped)
            except Exception:
                ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        sess['temp'] = temp
        _ask_next('hydration_value')
        return True
    
    if step == 'hydration_value':
        if _is_skip(text_stripped):
            temp['hydration_value'] = None
        else:
            try:
                temp['hydration_value'] = int(text_stripped)
            except Exception:
                ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        sess['temp'] = temp
        _ask_next('durability')
        return True
    
    if step == 'durability':
        if _is_skip(text_stripped):
            temp['durability'] = None
        else:
            try:
                temp['durability'] = int(text_stripped)
            except Exception:
                ctx.emit(ctx.message_out, {'type': 'error', 'content': 'Please enter an integer or press Enter to skip.'})
                return True
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('quality')
        return True
    
    if step == 'quality':
        temp['quality'] = None if _is_skip(text_stripped) else text_stripped
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('loot_location_hint')
        return True
    
    if step == 'link_to_object_uuid':
        temp['link_to_object_uuid'] = None
        sess['temp'] = temp
        _ask_next('loot_location_hint')
        return True
    
    if step == 'loot_location_hint':
        if _is_skip(text_stripped):
            temp['loot_location_hint'] = None
        else:
            odata = None
            try:
                parsed = _json.loads(text_stripped)
                if isinstance(parsed, dict):
                    odata = parsed
                else:
                    odata = {"display_name": str(parsed)}
            except Exception:
                odata = {"display_name": text_stripped}
            temp['loot_location_hint'] = odata
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('crafting_recipe')
        return True
    
    if step == 'crafting_recipe':
        temp['crafting_recipe'] = _parse_recipe_input(text_stripped)
        _echo_raw(text_stripped)
        sess['temp'] = temp
        _ask_next('deconstruct_recipe')
        return True
    
    if step == 'deconstruct_recipe':
        temp['deconstruct_recipe'] = _parse_recipe_input(text_stripped)
        _echo_raw(text_stripped)
        sess['temp'] = temp
        try:
            preview = {
                'display_name': temp.get('display_name'),
                'description': temp.get('description', ''),
                'object_tags': temp.get('object_tags', ['small']),
                'material_tag': temp.get('material_tag'),
                'value': temp.get('value'),
                'satiation_value': temp.get('satiation_value'),
                'hydration_value': temp.get('hydration_value'),
                'durability': temp.get('durability'),
                'quality': temp.get('quality'),
                'loot_location_hint': temp.get('loot_location_hint'),
                'crafting_recipe': temp.get('crafting_recipe', []),
                'deconstruct_recipe': temp.get('deconstruct_recipe', []),
            }
            raw = _json.dumps(preview, ensure_ascii=False, indent=2)
        except Exception:
            raw = '(error building preview)'
        ctx.emit(ctx.message_out, {'type': 'system', 'content': f"Preview of template object:\n{raw}"})
        _ask_next('confirm')
        return True
    
    if step == 'confirm':
        if text_lower2 not in ('save', 'y', 'yes'):
            ctx.emit(ctx.message_out, {'type': 'system', 'content': "Not saved. Type 'save' to save or 'cancel' to abort."})
            return True
        try:
            from world import Object as _Obj
            key = temp.get('key')
            if not key:
                raise ValueError('Missing template key')
            llh_dict = temp.get('loot_location_hint')
            crafting_list = temp.get('crafting_recipe', [])
            decon_list = temp.get('deconstruct_recipe', [])
            llh_obj = _Obj.from_dict(llh_dict) if llh_dict else None
            craft_objs = [_Obj.from_dict(o) for o in crafting_list]
            decon_objs = [_Obj.from_dict(o) for o in decon_list]
            tags_final = list(dict.fromkeys(temp.get('object_tags', ['small'])))
            try:
                if temp.get('satiation_value') is not None:
                    tags_final.append(f"Edible: {int(temp['satiation_value'])}")
                if temp.get('hydration_value') is not None:
                    tags_final.append(f"Drinkable: {int(temp['hydration_value'])}")
            except Exception:
                pass
            obj = _Obj(
                display_name=temp.get('display_name'),
                description=temp.get('description', ''),
                object_tags=set(tags_final),
                material_tag=temp.get('material_tag'),
                value=temp.get('value'),
                satiation_value=temp.get('satiation_value'),
                hydration_value=temp.get('hydration_value'),
                loot_location_hint=llh_obj,
                durability=temp.get('durability'),
                quality=temp.get('quality'),
                crafting_recipe=craft_objs,
                deconstruct_recipe=decon_objs,
                link_target_room_id=temp.get('link_target_room_id'),
                link_to_object_uuid=temp.get('link_to_object_uuid'),
            )
            if not hasattr(world, 'object_templates'):
                world.object_templates = {}
            world.object_templates[key] = obj
            try:
                ctx.save_world(world, ctx.state_path, debounced=True)
            except Exception:
                pass
            ctx.object_template_sessions.pop(sid_str, None)
            ctx.emit(ctx.message_out, {'type': 'system', 'content': f"Saved object template '{key}'."})
            return True
        except Exception as e:
            ctx.emit(ctx.message_out, {'type': 'error', 'content': f'Failed to save template: {e}'})
            return True
    
    _ask_next('template_key')
    return True


# Exported functions
__all__ = [
    'MessageHandlerContext',
    'init_message_handler',
    'get_context',
    'create_message_handler',
]
