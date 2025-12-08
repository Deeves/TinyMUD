from __future__ import annotations

"""
look_service.py — Room and object presentation helpers.

Why this file exists (and why it's neat):
- The server was doing a lot of heavy lifting to format room descriptions and
  object summaries inline. Useful, but it made the main loop beefy and harder
  to read.
- Here we tease apart that logic into small, pure, testable functions. Each
  function takes plain data (World/Room/Object) and returns strings. No sockets,
  no globals, no side‑effects.

How to use it:
- Call format_look(world, sid) to get a pretty BBCode description of the room
  for a specific player.
- Call resolve_object_in_room(room, name_raw) to fuzzy‑match an object by its
  display name. You’ll get back either the object or a set of suggestion names.
- Call format_object_summary(obj, world) to produce a compact BBCode summary
  of an object’s headline details.

If you’re new to the codebase: these helpers are intentionally tiny and cozy.
They’re a perfect place to make your first contribution. Add a new detail to
the look output? Make it here, keep the server zen.
"""

from typing import Any, Tuple


def format_look(w, sid: str | None) -> str:
    """Return a formatted room description for the given player SID.

    Contract:
    - Inputs: world (w), sid (str|None)
    - Output: single BBCode string describing the current room, nearby players,
      NPCs, Travel Points, and Objects.

    This is deliberately defensive: if something goes sideways (missing room,
    odd data), we fall back to the world’s own describe_room_for implementation.
    """
    if sid is None or sid not in w.players:
        return "You are in the backrooms. How did you get here? try /teleport to escape."
    try:
        player = w.players.get(sid)
        if not player:
            return "You are in the backrooms. How did you get here? try /teleport to escape."
        room = w.rooms.get(player.room_id)
        if not room:
            return "You are in the backrooms. How did you get here? try /teleport to escape."

        lines: list[str] = []
        room_desc = (room.description or "").strip()
        lines.append(f"You are in {room.id}. {room_desc}")

        bits: list[str] = []
        TRAVEL_COLOR = "#FFA500"  # orange for travel points
        # Other players (exclude viewer)
        try:
            other_sids = [psid for psid in room.players if psid != sid]
            other_names = [w.players[psid].sheet.display_name for psid in other_sids if psid in w.players]
            if other_names:
                bits.append("Players: " + ", ".join(sorted(other_names)))
        except Exception:
            pass

        # NPCs present
        try:
            if getattr(room, 'npcs', None) and room.npcs:
                bits.append("NPCs: " + ", ".join(sorted(room.npcs)))
        except Exception:
            pass

        # Objects present (including fixed fixtures and items)
        try:
            tp_names: list[str] = []
            obj_names: list[str] = []
            vals = list(room.objects.values()) if isinstance(room.objects, dict) else []
            if vals:
                for o in vals:
                    try:
                        name = getattr(o, 'display_name', None)
                        if not name:
                            continue
                        tags = set(getattr(o, 'object_tags', []) or [])
                        if 'Travel Point' in tags:
                            tp_names.append(f"[color={TRAVEL_COLOR}]{str(name)}[/color]")
                        else:
                            obj_names.append(str(name))
                    except Exception:
                        continue
            else:
                # Fallback to doors/stairs only as travel points
                if getattr(room, 'doors', None):
                    for dname in sorted(room.doors.keys()):
                        tp_names.append(f"[color={TRAVEL_COLOR}]{dname}[/color]")
                if getattr(room, 'stairs_up_to', None):
                    tp_names.append(f"[color={TRAVEL_COLOR}]stairs up[/color]")
                if getattr(room, 'stairs_down_to', None):
                    tp_names.append(f"[color={TRAVEL_COLOR}]stairs down[/color]")

            def _unique_sorted(lst: list[str]) -> list[str]:
                seen = {}
                for x in lst:
                    if x not in seen:
                        seen[x] = True
                return sorted(seen.keys(), key=lambda s: s.lower())

            tp_names = _unique_sorted(tp_names)
            obj_names = _unique_sorted(obj_names)
            if tp_names:
                bits.append("Travel Points: " + ", ".join(tp_names))
            if obj_names:
                bits.append("Objects: " + ", ".join(obj_names))
        except Exception:
            pass

        if bits:
            lines.append("; ".join(bits))

        return "\n".join(lines)
    except Exception:
        # Fall back to existing world description on any unexpected error
        try:
            return w.describe_room_for(sid)
        except Exception:
            return "You are nowhere."


def resolve_object_in_room(room, name_raw: str) -> Tuple[Any | None, list[str]]:
    """Fuzzy‑resolve an Object in the given room by display name.

    Matching order: case‑insensitive exact, prefix, substring.
    Returns (obj | None, suggestions: list[str]). If multiple matches exist for
    a rule, we return suggestions instead of guessing.
    """
    if not room or not getattr(room, 'objects', None):
        return None, []
    try:
        objs = list(room.objects.values())
        target = (name_raw or "").strip()
        tlow = target.lower()
        if not tlow:
            return None, []
        exact = [o for o in objs if getattr(o, 'display_name', '').lower() == tlow]
        if len(exact) == 1:
            return exact[0], []
        if len(exact) > 1:
            return None, [getattr(o, 'display_name', 'Unnamed') for o in exact]
        pref = [o for o in objs if getattr(o, 'display_name', '').lower().startswith(tlow)]
        if len(pref) == 1:
            return pref[0], []
        if len(pref) > 1:
            return None, [getattr(o, 'display_name', 'Unnamed') for o in pref]
        subs = [o for o in objs if tlow in getattr(o, 'display_name', '').lower()]
        if len(subs) == 1:
            return subs[0], []
        if len(subs) > 1:
            return None, [getattr(o, 'display_name', 'Unnamed') for o in subs]
        return None, []
    except Exception:
        return None, []


def format_object_summary(obj: Any, w) -> str:
    """Cook up a compact BBCode summary for an Object.

    We skip empty attributes and keep the prose readable. If the object is a
    Travel Point, we color the title to visually separate “things you can go
    through” from “things you can grab”.
    """
    try:
        name_disp = getattr(obj, 'display_name', 'Unnamed')
        tags_set = set(getattr(obj, 'object_tags', []) or [])
        if 'Travel Point' in tags_set:
            title = f"[b][color=#FFA500]{name_disp}[/color][/b]"
        else:
            title = f"[b]{name_disp}[/b]"
        lines: list[str] = [title]
        desc = (getattr(obj, 'description', '') or '').strip()
        if desc:
            lines.append(desc)

        details_bits: list[str] = []
        material = getattr(obj, 'material_tag', None)
        if material:
            details_bits.append(f"Material: {material}")
        quality = getattr(obj, 'quality', None)
        if quality:
            details_bits.append(f"Quality: {quality}")
        durability = getattr(obj, 'durability', None)
        if durability is not None:
            details_bits.append(f"Durability: {durability}")
        value = getattr(obj, 'value', None)
        if value is not None:
            details_bits.append(f"Value: {value} coin{'s' if int(value) != 1 else ''}")
        try:
            tags = list(getattr(obj, 'object_tags', []) or [])
            tags = [str(t) for t in tags if t]
            seen = set()
            tags_u: list[str] = []
            for t in tags:
                if t not in seen:
                    seen.add(t)
                    tags_u.append(t)
            if tags_u:
                details_bits.append("Tags: " + ", ".join(tags_u))
        except Exception:
            pass

        if details_bits:
            lines.append("[i]" + " • ".join(details_bits) + "[/i]")

        try:
            llh = getattr(obj, 'loot_location_hint', None)
            if llh is not None:
                name = getattr(llh, 'display_name', None) or 'somewhere appropriate'
                lines.append(f"Typically found at: {name}.")
        except Exception:
            pass

        try:
            craft = [getattr(o, 'display_name', 'Unnamed') for o in (getattr(obj, 'crafting_recipe', []) or []) if o]
            if craft:
                lines.append("Recipe: " + ", ".join(craft))
        except Exception:
            pass
        try:
            decon = [getattr(o, 'display_name', 'Unnamed') for o in (getattr(obj, 'deconstruct_recipe', []) or []) if o]
            if decon:
                lines.append("Deconstructs into: " + ", ".join(decon))
        except Exception:
            pass

        try:
            link = getattr(obj, 'link_target_room_id', None)
            if link:
                lines.append(f"This appears to lead to: {link}.")
        except Exception:
            pass

        # Ownership line (if any)
        try:
            owner_id = getattr(obj, 'owner_id', None)
            if owner_id:
                owner_name = None
                # Try resolve as player user_id
                try:
                    for u in getattr(w, 'users', {}).values():
                        if getattr(u, 'user_id', None) == owner_id:
                            owner_name = getattr(u, 'display_name', None)
                            break
                except Exception:
                    pass
                if owner_name is None:
                    # Try resolve as NPC id via reverse lookup
                    try:
                        npc_map = getattr(w, 'npc_ids', {}) or {}
                        for nm, nid in npc_map.items():
                            if nid == owner_id:
                                owner_name = nm; break
                    except Exception:
                        pass
                if owner_name:
                    lines.append(f"Owned by: {owner_name}")
                else:
                    lines.append("Owned by: [unknown]")
        except Exception:
            pass

        return "\n".join(lines)
    except Exception:
        try:
            return f"[b]{getattr(obj, 'display_name', 'Object')}[/b]"
        except Exception:
            return "An object."
