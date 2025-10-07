"""Faction generation service for /faction commands.

Implements:
  - /faction factiongen

Behavior:
- Prompts Google Gemini (if configured) to propose a small faction footprint:
  3–6 linked rooms and 2–10 NPCs with relationship links.
- Applies results to the world, enforcing invariants:
  - Rooms created with stable ids and descriptions.
  - Doors between rooms created both directions with Object entries tagged as Travel Points.
  - NPC sheets created, placed into rooms, and assigned stable npc_ids.
  - Directed relationships persisted in world.relationships.
  - Ensure at least one Edible object and one Drinkable object exist in the generated area.
  - Ensure each NPC has an owned bed Object in their assigned room (tag 'Bed', immovable).

Offline fallback:
- If AI isn't available or parsing fails, synthesizes a compact 3-room loop with 3 NPCs,
  simple relationships, a Food Crate and Water Barrel (both consumable), and owned beds.

Contract: handle_faction_command(world, state_path, sid, args) -> (handled, err, emits)
"""

from __future__ import annotations

from typing import List, Tuple, Optional, Dict
import os
import json
import re
import uuid

from world import World, Room, Object, CharacterSheet
from ai_utils import safety_settings_for_level as _shared_safety_settings

# Optional Gemini SDK
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore


_GEN_MODEL = None  # lazy singleton


def _get_gemini_model():
    global _GEN_MODEL
    if _GEN_MODEL is not None:
        return _GEN_MODEL
    if genai is None:
        return None
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        _GEN_MODEL = genai.GenerativeModel('gemini-flash-lite-latest')  # type: ignore[attr-defined]
        return _GEN_MODEL
    except Exception:
        return None


def _safety(world: World):
    try:
        return _shared_safety_settings(getattr(world, 'safety_level', 'G'))
    except Exception:
        return None


def _uniq_room_id(world: World, base: str) -> str:
    """Return a unique room id by appending numeric suffixes if needed."""
    candidate = base
    n = 2
    while candidate in world.rooms or not candidate:
        candidate = f"{base}-{n}"
        n += 1
        if n > 9999:
            candidate = str(uuid.uuid4())
            break
    return candidate


def _ensure_food_and_water(world: World, room_ids: List[str]) -> List[str]:
    """Ensure at least one edible and one drinkable object exist among the given rooms.

    Returns a list of short status lines summarizing created supplies.
    """
    created_notes: List[str] = []
    # Scan whether any Edible/Drinkable present already
    has_food = False
    has_water = False
    try:
        for rid in room_ids:
            r = world.rooms.get(rid)
            if not r:
                continue
            for o in (r.objects or {}).values():
                tags = set(getattr(o, 'object_tags', []) or [])
                # Accept either tag-encoded nutrition or legacy fields
                edible = any(str(t).lower().startswith('edible') for t in tags) or (getattr(o, 'satiation_value', 0) or 0) > 0
                drink = any(str(t).lower().startswith('drinkable') for t in tags) or (getattr(o, 'hydration_value', 0) or 0) > 0
                if edible:
                    has_food = True
                if drink:
                    has_water = True
    except Exception:
        pass

    # Place in the first room if missing
    if room_ids:
        rid0 = room_ids[0]
        r0 = world.rooms.get(rid0)
        if r0:
            if not has_food:
                food = Object(
                    display_name="Food Crate",
                    description="A stout crate filled with bread and dried meat.",
                    object_tags={"small", "Edible: 30"},
                )
                # Provide legacy fields for compatibility as well
                food.satiation_value = 30  # type: ignore[attr-defined]
                r0.objects[food.uuid] = food
                created_notes.append(f"+ Food supply in '{rid0}'")
            if not has_water:
                water = Object(
                    display_name="Water Cask",
                    description="A wooden cask brimming with fresh water.",
                    object_tags={"small", "Drinkable: 30"},
                )
                water.hydration_value = 30  # type: ignore[attr-defined]
                r0.objects[water.uuid] = water
                created_notes.append(f"+ Water supply in '{rid0}'")
    return created_notes


def _create_bed_for_npc(world: World, npc_name: str, room_id: str) -> Optional[str]:
    """Create an owned bed for npc_name in room_id. Returns object uuid or None."""
    room = world.rooms.get(room_id)
    if not room:
        return None
    try:
        npc_id = world.get_or_create_npc_id(npc_name)
    except Exception:
        npc_id = None
    bed = Object(
        display_name=f"bed of {npc_name}",
        description=f"A simple bed reserved for {npc_name}.",
        object_tags={"Immovable", "Bed"},
    )
    if npc_id:
        bed.owner_id = npc_id  # type: ignore[attr-defined]
    room.objects[bed.uuid] = bed
    return bed.uuid


def _extract_json_payload(text: str) -> Optional[dict]:
    """Extract a single JSON object from model text or fenced block.

    Expected schema:
    {
      rooms: [{ id, description }...3-6],
      links: [{ a, door_a, b, door_b }...],
      npcs: [{ name, description, room }...2-10],
      relationships: [{ source, type, target }...]
    }
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start:end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        try:
            snippet2 = re.sub(r",\s*([}\]])", r"\1", snippet)
            return json.loads(snippet2)
        except Exception:
            return None


def _apply_graph_to_world(world: World, state_path: str, graph: dict) -> Tuple[List[str], List[str]]:
    """Create rooms, link doors, add NPCs, relationships, food/water, and beds.

    Returns (room_ids, npc_names) that were created.
    """
    created_rooms: List[str] = []
    created_npcs: List[str] = []

    # 1) Rooms
    rooms_in = graph.get('rooms') or []
    for r in rooms_in:
        if not isinstance(r, dict):
            continue
        rid_raw = str(r.get('id') or '').strip()
        desc = str(r.get('description') or '').strip() or "An empty chamber."
        base = re.sub(r"[^A-Za-z0-9_\-]", "_", rid_raw or "faction_room")[:48] or "faction_room"
        rid = _uniq_room_id(world, base)
        room = Room(id=rid, description=desc)
        world.rooms[rid] = room
        created_rooms.append(rid)

    # Helper: link doors both ways and maintain Object invariants
    def link_rooms(a_id: str, door_a: str, b_id: str, door_b: str) -> None:
        ra = world.rooms.get(a_id)
        rb = world.rooms.get(b_id)
        if not ra or not rb:
            return
        ra.doors[door_a] = b_id
        rb.doors[door_b] = a_id
        # Ensure IDs and Objects
        for room, dname, target in ((ra, door_a, b_id), (rb, door_b, a_id)):
            try:
                if dname not in room.door_ids:
                    room.door_ids[dname] = str(uuid.uuid4())
                oid = room.door_ids.get(dname)
                if oid:
                    if oid not in room.objects:
                        obj = Object(
                            display_name=dname,
                            description=f"A doorway named '{dname}'.",
                            object_tags={"Immovable", "Travel Point"},
                            link_target_room_id=target,
                        )
                        obj.uuid = oid
                        room.objects[oid] = obj
                    else:
                        o = room.objects[oid]
                        o.display_name = dname
                        o.object_tags = set(o.object_tags or set()) | {"Immovable", "Travel Point"}
                        o.link_target_room_id = target
            except Exception:
                pass

    # 2) Links
    for l in (graph.get('links') or []):
        if not isinstance(l, dict):
            continue
        a = str(l.get('a') or '').strip()
        b = str(l.get('b') or '').strip()
        da = str(l.get('door_a') or 'door').strip() or 'door'
        db = str(l.get('door_b') or 'door').strip() or 'door'
        # Fuzzy map: match input ids to created room ids using ci-exact/prefix/substring
        def resolve(input_id: str) -> Optional[str]:
            if input_id in world.rooms:
                return input_id
            # try prefix and substring among created ids
            cands = [rid for rid in created_rooms if rid.lower() == input_id.lower()]
            if cands:
                return cands[0]
            prefs = [rid for rid in created_rooms if rid.lower().startswith(input_id.lower())]
            if len(prefs) == 1:
                return prefs[0]
            subs = [rid for rid in created_rooms if input_id.lower() in rid.lower()]
            if len(subs) == 1:
                return subs[0]
            return None
        ra = resolve(a)
        rb = resolve(b)
        if ra and rb and ra != rb:
            link_rooms(ra, da, rb, db)

    # 3) NPCs
    for n in (graph.get('npcs') or []):
        if not isinstance(n, dict):
            continue
        name = str(n.get('name') or '').strip()
        desc = str(n.get('description') or '').strip() or f"An NPC named {name}."
        room_ref = str(n.get('room') or '').strip()
        if not name:
            continue
        # Choose placement room: try resolve by ci-exact/prefix/substring; else fallback to first room
        rid_place = None
        for rid in created_rooms:
            if rid.lower() == room_ref.lower():
                rid_place = rid; break
        if not rid_place and room_ref:
            prefs = [rid for rid in created_rooms if rid.lower().startswith(room_ref.lower())]
            if len(prefs) == 1:
                rid_place = prefs[0]
        if not rid_place and room_ref:
            subs = [rid for rid in created_rooms if room_ref.lower() in rid.lower()]
            if len(subs) == 1:
                rid_place = subs[0]
        if not rid_place and created_rooms:
            rid_place = created_rooms[0]
        if not rid_place:
            continue
        # Create or update sheet
        sheet = world.npc_sheets.get(name)
        if sheet is None:
            sheet = CharacterSheet(display_name=name, description=desc)
            world.npc_sheets[name] = sheet
        else:
            if desc:
                sheet.description = desc
        try:
            world.get_or_create_npc_id(name)
        except Exception:
            pass
        room_obj = world.rooms.get(rid_place)
        if room_obj:
            room_obj.npcs.add(name)
            created_npcs.append(name)
            # Owned bed per NPC
            _create_bed_for_npc(world, name, rid_place)

    # 4) Relationships (directed)
    rels_in = graph.get('relationships') or []
    if isinstance(rels_in, list):
        rels: Dict[str, Dict[str, str]] = getattr(world, 'relationships', {}) or {}
        for r in rels_in:
            if not isinstance(r, dict):
                continue
            src = str(r.get('source') or '').strip()
            tgt = str(r.get('target') or '').strip()
            rtype = str(r.get('type') or '').strip() or 'ally'
            if not src or not tgt:
                continue
            try:
                sid = world.get_or_create_npc_id(src)
                tid = world.get_or_create_npc_id(tgt)
            except Exception:
                continue
            if sid not in rels:
                rels[sid] = {}
            rels[sid][tid] = rtype
        world.relationships = rels

    # 5) Food & Water
    _ = _ensure_food_and_water(world, created_rooms)

    # Best-effort save
    try:
        world.save_to_file(state_path)
    except Exception:
        pass

    return created_rooms, created_npcs


def _offline_default_graph() -> dict:
    """Return a tiny synthesized faction graph for offline fallback."""
    return {
        "rooms": [
            {"id": "hall", "description": "A timbered meeting hall with a long table and a banner on the wall."},
            {"id": "bunks", "description": "Rows of simple bunk beds and footlockers."},
            {"id": "kitchen", "description": "A warm kitchen with a crackling hearth and stacked barrels."},
        ],
        "links": [
            {"a": "hall", "door_a": "oak door", "b": "bunks", "door_b": "to hall"},
            {"a": "hall", "door_a": "swinging door", "b": "kitchen", "door_b": "to hall"},
        ],
        "npcs": [
            {"name": "Quartermaster", "description": "Keeps the ledgers and keys, stern but fair.", "room": "hall"},
            {"name": "Cook Mira", "description": "Bustling and chatty, always with flour on her hands.", "room": "kitchen"},
            {"name": "Scout Rafe", "description": "Light on his feet, fond of tall tales.", "room": "bunks"},
        ],
        "relationships": [
            {"source": "Quartermaster", "type": "superior", "target": "Scout Rafe"},
            {"source": "Cook Mira", "type": "friend", "target": "Scout Rafe"},
        ],
    }


def _build_ai_prompt(world: World) -> str:
    name = getattr(world, 'world_name', None) or 'Unnamed World'
    desc = getattr(world, 'world_description', None) or ''
    conflict = getattr(world, 'world_conflict', None) or ''
    parts = [
        "Design a compact faction location for a text MUD.",
        "Return ONLY JSON with keys: rooms, links, npcs, relationships. No prose, no markdown.",
        "Constraints: 3-6 rooms; 2-10 NPCs; rooms must be linked via named doors.",
        "Requirements: create meaningful relationships among NPCs. Keep names unique.",
        "Schema:",
        "{",
        "  rooms: [{id: string, description: string}],",
        "  links: [{a: string, door_a: string, b: string, door_b: string}],",
        "  npcs:  [{name: string, description: string, room: string}],",
        "  relationships: [{source: string, type: string, target: string}]",
        "}",
        "World context:",
        f"Name: {name}",
        f"Description: {desc}",
        f"Main Conflict: {conflict}",
        "Notes: keep descriptions concise; avoid unsafe content; names should fit the world.",
    ]
    return "\n".join(p for p in parts if p)


def handle_faction_command(world: World, state_path: str, sid: str | None, args: List[str]) -> Tuple[bool, Optional[str], List[dict]]:
    emits: List[dict] = []
    if not args:
        return True, "Usage: /faction factiongen", emits
    sub = (args[0] or '').strip().lower()
    if sub != 'factiongen':
        return False, None, emits

    # Build AI prompt
    model = _get_gemini_model()
    graph: Optional[dict] = None
    if model is not None:
        prompt = _build_ai_prompt(world)
        try:
            safety = _safety(world)
            if safety is not None:
                resp = model.generate_content(prompt, safety_settings=safety)
            else:
                resp = model.generate_content(prompt)
            text = getattr(resp, 'text', None) or str(resp)
            parsed = _extract_json_payload(text)
            if isinstance(parsed, dict):
                # Clamp counts to bounds just in case
                def clamp_list(lst, lo, hi):
                    if not isinstance(lst, list):
                        return []
                    return list(lst)[:max(lo, min(hi, len(lst)))]
                parsed['rooms'] = clamp_list(parsed.get('rooms') or [], 3, 6)
                parsed['npcs'] = clamp_list(parsed.get('npcs') or [], 2, 10)
                graph = parsed
        except Exception:
            graph = None
    # Enforce minimum sizes; if too small or missing, use offline fallback
    if (graph is None) or (len(graph.get('rooms', [])) < 3) or (len(graph.get('npcs', [])) < 2):
        graph = _offline_default_graph()

    # Apply to world
    rooms_created, npcs_created = _apply_graph_to_world(world, state_path, graph)

    # Emit a concise summary
    room_list = ", ".join(rooms_created) if rooms_created else "(none)"
    npc_list = ", ".join(npcs_created) if npcs_created else "(none)"
    emits.append({
        'type': 'system',
        'content': (
            f"[b][Experimental][/b] Faction generated: rooms [{room_list}] — NPCs [{npc_list}].\n"
            f"Each NPC has an owned bed; food and water sources were ensured."
        )
    })
    return True, None, emits
