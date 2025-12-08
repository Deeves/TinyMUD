from __future__ import annotations

"""Player profile & utility commands router.

Handles:
  /rename
  /describe
  /sheet
  /roll

Behavior preserved exactly from original inline code.
"""

from typing import Any
from command_context import CommandContext, EmitFn
from dice_utils import roll as dice_roll, DiceParseError as DiceError
from persistence_utils import save_world


def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    world = ctx.world
    MESSAGE_OUT = ctx.message_out
    STATE_PATH = ctx.state_path

    if cmd == 'rename':
        if sid is None:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
            return True
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first with /auth.'})
            return True
        if not args:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /rename <new name>'})
            return True
        new_name = " ".join(args).strip()
        if len(new_name) < 2 or len(new_name) > 32:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Name must be between 2 and 32 characters.'})
            return True
        player = world.players.get(sid)
        if not player:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Player not found.'})
            return True
        player.sheet.display_name = new_name
        try:
            save_world(world, STATE_PATH, debounced=True)
        except Exception:  # pragma: no cover
            pass
        emit(MESSAGE_OUT, {'type': 'system', 'content': f'You are now known as {new_name}.'})
        return True

    if cmd == 'describe':
        if sid is None:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
            return True
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first with /auth.'})
            return True
        if not args:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /describe <text>'})
            return True
        text = " ".join(args).strip()
        if len(text) > 300:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Description too long (max 300 chars).'})
            return True
        player = world.players.get(sid)
        if not player:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Player not found.'})
            return True
        player.sheet.description = text
        try:
            save_world(world, STATE_PATH, debounced=True)
        except Exception:  # pragma: no cover
            pass
        emit(MESSAGE_OUT, {'type': 'system', 'content': 'Description updated.'})
        return True

    if cmd == 'sheet':
        if sid is None:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
            return True
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first with /auth.'})
            return True
        player = world.players.get(sid)
        if not player:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Player not found.'})
            return True
        inv_text = player.sheet.inventory.describe()
        currency_amount = int(getattr(player.sheet, 'currency', 0) or 0)
        rel_lines: list[str] = []
        try:
            uid = ctx.sessions.get(sid)
            if uid:
                out_map = (world.relationships.get(uid, {}) or {})
                out_bits: list[str] = []
                for tgt_id, rtype in out_map.items():
                    name = None
                    for u in world.users.values():
                        if u.user_id == tgt_id:
                            name = u.display_name; break
                    if not name:
                        try:
                            for n, nid in world.npc_ids.items():
                                if nid == tgt_id:
                                    name = n; break
                        except Exception:
                            pass
                    if name:
                        out_bits.append(f"{name} [{rtype}]")
                if out_bits:
                    rel_lines.append("[b]Your relations[/b]: " + ", ".join(sorted(out_bits)))
                in_bits: list[str] = []
                for src_id, m in (world.relationships or {}).items():
                    if uid in m:
                        rtype = m.get(uid)
                        name = None
                        for u in world.users.values():
                            if u.user_id == src_id:
                                name = u.display_name; break
                        if not name:
                            try:
                                for n, nid in world.npc_ids.items():
                                    if nid == src_id:
                                        name = n; break
                            except Exception:
                                pass
                        if name and rtype:
                            in_bits.append(f"{name} [{rtype}]")
                if in_bits:
                    rel_lines.append("[b]Relations to you[/b]: " + ", ".join(sorted(in_bits)))
        except Exception:
            pass
        rel_text = ("\n" + "\n".join(rel_lines)) if rel_lines else ""
        content = (
            f"[b]{player.sheet.display_name}[/b]\n"
            f"{player.sheet.description}{rel_text}\n\n"
            f"[b]Currency[/b]\n{currency_amount} coin{'s' if currency_amount != 1 else ''}\n\n"
            f"[b]Inventory[/b]\n{inv_text}"
        )
        emit(MESSAGE_OUT, {'type': 'system', 'content': content})
        return True

    if cmd == 'roll':
        if sid is None:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
            return True
        if sid not in world.players:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Please authenticate first with /auth.'})
            return True
        if not args:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /roll <dice expression> [| Private]'})
            return True
        joined = " ".join(args)
        priv = False
        expr = joined
        if '|' in joined:
            left, right = joined.split('|', 1)
            expr = left.strip()
            if right.strip().lower() == 'private':
                priv = True
        try:
            result = dice_roll(expr)
        except DiceError as e:
            emit(MESSAGE_OUT, {'type': 'error', 'content': f'Dice error: {e}'})
            return True
        res_text = f"{result.expression} = {result.total}"
        player_obj = world.players.get(sid)
        pname = player_obj.sheet.display_name if player_obj else 'Someone'
        if priv:
            emit(MESSAGE_OUT, {'type': 'system', 'content': f"You secretly pull out the sacred geometric stones from your pocket and roll {res_text}."})
            return True
        emit(MESSAGE_OUT, {'type': 'system', 'content': f"You pull out the sacred geometric stones from your pocket and roll {res_text}."})
        if player_obj:
            ctx.broadcast_to_room(player_obj.room_id, {
                'type': 'system',
                'content': f"{pname} pulls out the sacred geometric stones from their pocket and rolls {res_text}."
            }, sid)
        return True

    return False
