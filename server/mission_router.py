from typing import Callable, List
from command_context import CommandContext
from mission_model import MissionStatus
import mission_service
import npc_mission_logic
import id_parse_utils

def try_handle(
    ctx: CommandContext, 
    sid: str, 
    cmd: str, 
    args: List[str], 
    raw: str, 
    emit: Callable
) -> bool:
    if cmd != 'mission':
        return False

    if not args:
        emit({'type': 'system', 'content': 'Usage: /mission <list|detail|offer|accept|reject|generate>'})
        return True

    subcmd = args[0].lower()
    subargs = args[1:]

    # Admin commands logic checks
    if sid in ctx.admins:
        handled, err, emits = mission_service.handle_mission_admin_command(ctx.world, args)
        if handled:
            if err:
                emit({'type': 'error', 'content': err})
            else:
                for e in emits:
                    emit(e)
            return True

    if subcmd == 'list':
        _handle_list(ctx, sid, emit)
        return True
    
    if subcmd == 'detail':
        if not subargs:
            emit({'type': 'error', 'content': 'Usage: /mission detail <mission_id>'})
            return True
        _handle_detail(ctx, sid, subargs[0], emit)
        return True

    if subcmd == 'generate':
        # Test command to generate a mission from a nearby NPC
        _handle_generate(ctx, sid, emit)
        return True

    if subcmd == 'offer':
        if len(subargs) < 2:
            emit({'type': 'error', 'content': 'Usage: /mission offer <target_name> <mission_id>'})
            return True
        _handle_offer(ctx, sid, subargs[0], subargs[1], emit)
        return True

    if subcmd == 'accept':
        if not subargs:
            emit({'type': 'error', 'content': 'Usage: /mission accept <mission_id>'})
            return True
        _handle_accept(ctx, sid, subargs[0], emit)
        return True

    emit({'type': 'error', 'content': f"Unknown mission command: {subcmd}"})
    return True

def _handle_list(ctx: CommandContext, sid: str, emit: Callable):
    player = ctx.world.players.get(sid)
    if not player:
        emit({'type': 'error', 'content': 'Not connected.'})
        return
        
    user_id = ctx.sessions.get(sid)
    
    my_missions = []
    for m in ctx.world.missions.values():
        is_issuer = (m.issuer_id == user_id)
        is_assignee = (m.assignee_id == user_id)
        if is_issuer or is_assignee:
            my_missions.append(m)
            
    if not my_missions:
        emit({'type': 'system', 'content': 'No active missions.'})
        return

    lines = ["[b]Your Missions:[/b]"]
    for m in my_missions:
        role = "Issuer" if m.issuer_id == user_id else "Assignee"
        lines.append(f"- [{m.status.value.upper()}] {m.title} ({role}) (ID: {m.uuid})")
    
    emit({'type': 'system', 'content': "\n".join(lines)})

def _handle_detail(ctx: CommandContext, sid: str, mid: str, emit: Callable):
    mission = ctx.world.missions.get(mid)
    if not mission:
        emit({'type': 'error', 'content': 'Mission not found.'})
        return
        
    lines = [
        f"[b]{mission.title}[/b]",
        f"Status: {mission.status.value}",
        f"Description: {mission.description}",
        "[b]Objectives:[/b]"
    ]
    for obj in mission.objectives:
        status = "[X]" if obj.completed else "[ ]"
        lines.append(f"{status} {obj.description} ({obj.current_count}/{obj.target_count})")
        
    if mission.deadline:
        import time
        remaining = int(mission.deadline - time.time())
        if remaining > 0:
            lines.append(f"Time Remaining: {remaining}s")
        else:
            lines.append("Time Remaining: EXPIRED")
            
    emit({'type': 'system', 'content': "\n".join(lines)})

def _handle_generate(ctx: CommandContext, sid: str, emit: Callable):
    player = ctx.world.players.get(sid)
    if not player: return
    
    room = ctx.world.rooms.get(player.room_id)
    if not room or not room.npcs:
        emit({'type': 'error', 'content': 'No NPCs here to give missions.'})
        return
        
    npc_name = list(room.npcs)[0]
    
    mission = mission_service.generate_dynamic_mission(ctx.world, npc_name)
    if mission:
        ok, err, emits = mission_service.offer_mission(ctx.world, mission.uuid, sid)
        if ok:
            for e in emits:
                emit(e)
        else:
            emit({'type': 'error', 'content': f"Failed to offer: {err}"})
    else:
        emit({'type': 'error', 'content': 'Failed to generate mission.'})

def _handle_offer(ctx: CommandContext, sid: str, target_name: str, mid: str, emit: Callable):
    mission = ctx.world.missions.get(mid)
    if not mission:
        emit({'type': 'error', 'content': 'Mission not found.'})
        return

    # Resolve target
    player = ctx.world.players.get(sid)
    room = ctx.world.rooms.get(player.room_id)
    
    # Try resolving as Player
    target_sid, target_pname = ctx.resolve_player_sid_global(target_name)
    if target_sid:
        # Offer to player
        ok, err, emits = mission_service.offer_mission(ctx.world, mid, target_sid)
        if ok:
            emit({'type': 'system', 'content': f"You offered the mission to {target_pname}."})
            # Also emit to target (handled by service return, but we need to route it)
            # Service returns emits for the target usually.
            # Wait, mission_service.offer_mission returns emits intended for the TARGET.
            # We need to send them to target_sid.
            target_player = ctx.world.players.get(target_sid)
            if target_player:
                # We can't use 'emit' here because that goes to the sender (sid).
                # We need to use ctx.socketio.emit or similar, but ctx doesn't expose raw emit easily for other sids?
                # ctx has message_out constant? No.
                # ctx has broadcast_to_room.
                # We can use ctx.socketio.emit(MESSAGE_OUT, payload, room=target_sid)
                from constants import MESSAGE_OUT
                for e in emits:
                    ctx.socketio.emit(MESSAGE_OUT, e, room=target_sid)
        else:
            emit({'type': 'error', 'content': err})
        return

    # Try resolving as NPC
    # Check room NPCs
    npcs = [n for n in room.npcs if target_name.lower() in n.lower()]
    if npcs:
        npc_name = npcs[0]
        npc_sheet = ctx.world.npc_sheets.get(npc_name)
        if npc_sheet:
            # Evaluate
            user_id = ctx.sessions.get(sid)
            accepted, reason = npc_mission_logic.evaluate_mission_offer(ctx.world, npc_sheet, mission, user_id)
            
            if accepted:
                npc_id = ctx.world.get_or_create_npc_id(npc_name)
                mission_service.accept_mission(ctx.world, mid, npc_id)
                emit({'type': 'npc', 'name': npc_name, 'content': f"{reason} (Mission Accepted)"})
            else:
                emit({'type': 'npc', 'name': npc_name, 'content': f"{reason} (Mission Declined)"})
            return

    emit({'type': 'error', 'content': 'Target not found.'})

def _handle_accept(ctx: CommandContext, sid: str, mid: str, emit: Callable):
    user_id = ctx.sessions.get(sid)
    if not user_id:
        emit({'type': 'error', 'content': 'You must be logged in.'})
        return

    ok, err, emits = mission_service.accept_mission(ctx.world, mid, user_id)
    if ok:
        for e in emits:
            emit(e)
    else:
        emit({'type': 'error', 'content': err})
