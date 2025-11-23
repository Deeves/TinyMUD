"""Faction generation for /faction commands.

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

Service Contract:
    All public functions return 4-tuple: (handled, error, emits, broadcasts)
    - handled: bool - whether the command was recognized
    - error: str | None - error message if any
    - emits: List[dict] - messages to send to the acting player
    - broadcasts: List[Tuple[str, dict]] - (room_id, message) pairs for room broadcasts
"""

from __future__ import annotations

from typing import List, Tuple, Optional, Dict, Any
import os
import json
import re
import uuid

from persistence_utils import save_world
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
        save_world(world, state_path, debounced=True)
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


def handle_faction_command(world: World, state_path: str, sid: str | None, args: List[str]) -> Tuple[bool, Optional[str], List[dict], List[Tuple[str, dict]]]:
    """Handle /faction commands.
    
    This powerful admin command suite manages the faction system that creates
    meaningful political relationships between players and NPCs. Think of factions
    as your world's organized groups - guilds, tribes, nations, or any collective
    that creates dynamic social structures and conflicts.
    
    Supported commands:
    - factiongen: Generate AI-powered faction networks with rooms and NPCs
    - addfaction: Create a new faction with specified name and description
    - removefaction: Permanently delete a faction and clean up references
    - addmember: Add a player or NPC to an existing faction
    - removemember: Remove a player or NPC from a faction
    - addally: Establish alliance between two factions
    - removeally: Break alliance between factions  
    - addrival: Create rivalry between factions
    - removerival: Remove rivalry relationship
    
    Returns: (handled, error, emits, broadcasts)
    """
    # Always import helpers at function start for clean organization
    from id_parse_utils import strip_quotes, parse_pipe_parts, fuzzy_resolve
    from safe_utils import safe_call
    
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    
    if not args:
        # Provide comprehensive usage help that teaches admins what's possible
        usage_msg = (
            "Usage: /faction <command> [args...]\n"
            "Commands:\n"
            "  factiongen - Generate AI faction network\n"
            "  addfaction <name> | <description> - Create new faction\n"
            "  removefaction <name> - Delete faction\n"
            "  addmember <faction> | <player_or_npc> - Add member\n"
            "  removemember <faction> | <player_or_npc> - Remove member\n"
            "  addally <faction1> | <faction2> - Create alliance\n"
            "  removeally <faction1> | <faction2> - Break alliance\n"
            "  addrival <faction1> | <faction2> - Create rivalry\n"
            "  removerival <faction1> | <faction2> - Remove rivalry"
        )
        return True, usage_msg, emits, broadcasts
    
    sub = (args[0] or '').strip().lower()
    sub_args = args[1:]
    
    # Helper function to resolve faction by name with fuzzy matching
    def _resolve_faction_by_name(faction_name: str) -> Tuple[bool, Optional[str], Optional[Faction]]:
        """Find a faction by name using fuzzy resolution for user-friendly input.
        
        This helper makes faction commands tolerant of typos and partial names,
        just like room and player resolution throughout the system.
        """
        if not faction_name.strip():
            return False, "Faction name cannot be empty.", None
            
        faction_name = strip_quotes(faction_name.strip())
        faction_names = [f.name for f in world.factions.values()]
        
        # Use the same fuzzy resolution logic as other parts of the system
        ok, err, resolved_name = fuzzy_resolve(faction_name, faction_names)
        if not ok or not resolved_name:
            if faction_names:
                suggestions = ", ".join(faction_names[:5])
                return False, f"Faction '{faction_name}' not found. Available: {suggestions}", None
            else:
                return False, f"Faction '{faction_name}' not found. No factions exist yet.", None
        
        # Find the faction object by resolved name
        faction = world.get_faction_by_name(resolved_name)
        if not faction:
            return False, f"Internal error: faction '{resolved_name}' lookup failed.", None
            
        return True, None, faction
    
    # Helper function to resolve player or NPC for membership operations  
    def _resolve_entity_for_membership(entity_name: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """Resolve a player or NPC name to their stable ID for faction membership.
        
        Returns (success, error, entity_id, display_name) where entity_id is
        either a user.user_id for players or NPC UUID for NPCs.
        """
        if not entity_name.strip():
            return False, "Entity name cannot be empty.", None, None
            
        entity_name = strip_quotes(entity_name.strip())
        
        # First try to find as a user (player)
        user = world.get_user_by_display_name(entity_name)
        if user:
            return True, None, user.user_id, user.display_name
        
        # Then try as NPC using fuzzy resolution on NPC names
        npc_names = list(world.npc_sheets.keys())
        if npc_names:
            ok, err, resolved_npc = fuzzy_resolve(entity_name, npc_names)
            if ok and resolved_npc:
                npc_id = world.get_or_create_npc_id(resolved_npc)
                return True, None, npc_id, resolved_npc
        
        # Not found as either player or NPC
        available_players = [u.display_name for u in world.users.values()]
        available_npcs = list(world.npc_sheets.keys())
        all_available = available_players + available_npcs
        
        if all_available:
            suggestions = ", ".join(all_available[:5])
            return False, f"'{entity_name}' not found as player or NPC. Available: {suggestions}", None, None
        else:
            return False, f"'{entity_name}' not found. No players or NPCs exist yet.", None, None

    # Helper to validate pipe syntax - ensures the pipe was actually provided
    def _validate_pipe_syntax(args_text: str, expected_parts: int) -> bool:
        """Check if the pipe syntax was actually used, not just padded by parse_pipe_parts."""
        # Count actual pipe characters in the input
        pipe_count = args_text.count('|')
        # For expected_parts pieces, we need exactly (expected_parts - 1) pipes
        return pipe_count == (expected_parts - 1)

    # Save world state after any mutations (standard pattern throughout system)
    def _save_world():
        """Best-effort world persistence that won't crash the server on failure."""
        safe_call(lambda: world.save_to_file(state_path))

    # Handle the legacy factiongen command (AI-powered faction generation)
    if sub == 'factiongen':
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
        return True, None, emits, broadcasts

    # /faction addfaction <name> | <description>
    if sub == 'addfaction':
        if not sub_args:
            return True, "Usage: /faction addfaction <name> | <description>", emits, broadcasts
        
        # Parse name and description from pipe-separated arguments
        parts_joined = " ".join(sub_args)
        
        # Validate that pipe syntax was actually provided
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction addfaction <name> | <description>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction addfaction <name> | <description>", emits, broadcasts
            
        faction_name, description = parse_result
        faction_name = strip_quotes(faction_name.strip())
        description = description.strip()
        
        if not faction_name:
            return True, "Faction name cannot be empty.", emits, broadcasts
        
        # Check if faction already exists (case-insensitive)
        if world.get_faction_by_name(faction_name):
            return True, f"Faction '{faction_name}' already exists.", emits, broadcasts
        
        # Create the new faction
        try:
            faction = world.create_faction(faction_name, description)
            _save_world()
            emits.append({
                'type': 'system',
                'content': f"Created faction '[b]{faction.name}[/b]' with {len(description)} character description."
            })
            return True, None, emits, broadcasts
        except ValueError as e:
            return True, str(e), emits, broadcasts
        except Exception:
            return True, "Failed to create faction due to internal error.", emits, broadcasts

    # /faction removefaction <name>
    if sub == 'removefaction':
        if not sub_args:
            return True, "Usage: /faction removefaction <name>", emits, broadcasts
            
        faction_name = " ".join(sub_args).strip()
        ok, err, faction = _resolve_faction_by_name(faction_name)
        if not ok or not faction:
            return True, err or "Faction not found.", emits, broadcasts
        
        # Remove the faction (this also cleans up references in other factions)
        member_count = faction.get_total_members()
        removed = world.remove_faction(faction.faction_id)
        
        if removed:
            _save_world()
            emits.append({
                'type': 'system', 
                'content': f"Removed faction '[b]{faction.name}[/b]' and its {member_count} member(s). Allied/rival references cleaned up."
            })
        else:
            emits.append({
                'type': 'system',
                'content': f"Faction '{faction.name}' was already removed or not found."
            })
        
        return True, None, emits, broadcasts

    # /faction addmember <faction> | <player_or_npc>
    if sub == 'addmember':
        if not sub_args:
            return True, "Usage: /faction addmember <faction> | <player_or_npc>", emits, broadcasts
            
        parts_joined = " ".join(sub_args)
        
        # Validate pipe syntax
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction addmember <faction> | <player_or_npc>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction addmember <faction> | <player_or_npc>", emits, broadcasts
            
        faction_name, entity_name = parse_result
        
        # Resolve faction
        ok_faction, err_faction, faction = _resolve_faction_by_name(faction_name)
        if not ok_faction or not faction:
            return True, err_faction or "Faction not found.", emits, broadcasts
        
        # Resolve player or NPC
        ok_entity, err_entity, entity_id, display_name = _resolve_entity_for_membership(entity_name)
        if not ok_entity or not entity_id:
            return True, err_entity or "Player or NPC not found.", emits, broadcasts
        
        # Check if entity is a player (user_id) or NPC (npc_id from our mapping)
        is_player = entity_id in world.users
        
        # Add to appropriate member list
        if is_player:
            added = faction.add_member_player(entity_id)
            member_type = "player"
        else:
            added = faction.add_member_npc(entity_id)
            member_type = "NPC"
        
        if added:
            _save_world()
            emits.append({
                'type': 'system',
                'content': f"Added {member_type} '[b]{display_name}[/b]' to faction '[b]{faction.name}[/b]'. Total members: {faction.get_total_members()}"
            })
        else:
            emits.append({
                'type': 'system',
                'content': f"{member_type.title()} '[b]{display_name}[/b]' is already a member of faction '[b]{faction.name}[/b]'."
            })
        
        return True, None, emits, broadcasts

    # /faction removemember <faction> | <player_or_npc>  
    if sub == 'removemember':
        if not sub_args:
            return True, "Usage: /faction removemember <faction> | <player_or_npc>", emits, broadcasts
            
        parts_joined = " ".join(sub_args)
        
        # Validate pipe syntax
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction removemember <faction> | <player_or_npc>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction removemember <faction> | <player_or_npc>", emits, broadcasts
            
        faction_name, entity_name = parse_result
        
        # Resolve faction
        ok_faction, err_faction, faction = _resolve_faction_by_name(faction_name)
        if not ok_faction or not faction:
            return True, err_faction or "Faction not found.", emits, broadcasts
        
        # Resolve player or NPC
        ok_entity, err_entity, entity_id, display_name = _resolve_entity_for_membership(entity_name)
        if not ok_entity or not entity_id:
            return True, err_entity or "Player or NPC not found.", emits, broadcasts
        
        # Check if entity is a player or NPC and remove from appropriate list
        is_player = entity_id in world.users
        
        if is_player:
            removed = faction.remove_member_player(entity_id)
            member_type = "player"
        else:
            removed = faction.remove_member_npc(entity_id)  
            member_type = "NPC"
        
        if removed:
            _save_world()
            emits.append({
                'type': 'system',
                'content': f"Removed {member_type} '[b]{display_name}[/b]' from faction '[b]{faction.name}[/b]'. Remaining members: {faction.get_total_members()}"
            })
        else:
            emits.append({
                'type': 'system',
                'content': f"{member_type.title()} '[b]{display_name}[/b]' was not a member of faction '[b]{faction.name}[/b]'."
            })
        
        return True, None, emits, broadcasts

    # /faction addally <faction1> | <faction2>
    if sub == 'addally':
        if not sub_args:
            return True, "Usage: /faction addally <faction1> | <faction2>", emits, broadcasts
            
        parts_joined = " ".join(sub_args)
        
        # Validate pipe syntax
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction addally <faction1> | <faction2>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction addally <faction1> | <faction2>", emits, broadcasts
            
        faction1_name, faction2_name = parse_result
        
        # Resolve both factions
        ok1, err1, faction1 = _resolve_faction_by_name(faction1_name)
        if not ok1 or not faction1:
            return True, f"First faction: {err1 or 'not found'}", emits, broadcasts
            
        ok2, err2, faction2 = _resolve_faction_by_name(faction2_name)
        if not ok2 or not faction2:
            return True, f"Second faction: {err2 or 'not found'}", emits, broadcasts
        
        # Prevent self-alliance
        if faction1.faction_id == faction2.faction_id:
            return True, "A faction cannot be allied with itself.", emits, broadcasts
        
        # Create bidirectional alliance (both factions mark each other as allies)
        added1 = faction1.add_ally(faction2.faction_id)
        added2 = faction2.add_ally(faction1.faction_id)
        
        if added1 or added2:
            _save_world()
            if added1 and added2:
                emits.append({
                    'type': 'system',
                    'content': f"Created alliance between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]'."
                })
            else:
                emits.append({
                    'type': 'system', 
                    'content': f"Alliance between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]' already existed."
                })
        else:
            emits.append({
                'type': 'system',
                'content': f"Alliance between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]' already exists."
            })
        
        return True, None, emits, broadcasts

    # /faction removeally <faction1> | <faction2>
    if sub == 'removeally':
        if not sub_args:
            return True, "Usage: /faction removeally <faction1> | <faction2>", emits, broadcasts
            
        parts_joined = " ".join(sub_args)
        
        # Validate pipe syntax
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction removeally <faction1> | <faction2>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction removeally <faction1> | <faction2>", emits, broadcasts
            
        faction1_name, faction2_name = parse_result
        
        # Resolve both factions
        ok1, err1, faction1 = _resolve_faction_by_name(faction1_name)
        if not ok1 or not faction1:
            return True, f"First faction: {err1 or 'not found'}", emits, broadcasts
            
        ok2, err2, faction2 = _resolve_faction_by_name(faction2_name)
        if not ok2 or not faction2:
            return True, f"Second faction: {err2 or 'not found'}", emits, broadcasts
        
        # Remove bidirectional alliance 
        removed1 = faction1.remove_ally(faction2.faction_id)
        removed2 = faction2.remove_ally(faction1.faction_id)
        
        if removed1 or removed2:
            _save_world()
            emits.append({
                'type': 'system',
                'content': f"Removed alliance between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]'."
            })
        else:
            emits.append({
                'type': 'system',
                'content': f"No alliance existed between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]'."
            })
        
        return True, None, emits, broadcasts

    # /faction addrival <faction1> | <faction2>
    if sub == 'addrival':
        if not sub_args:
            return True, "Usage: /faction addrival <faction1> | <faction2>", emits, broadcasts
            
        parts_joined = " ".join(sub_args)
        
        # Validate pipe syntax
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction addrival <faction1> | <faction2>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction addrival <faction1> | <faction2>", emits, broadcasts
            
        faction1_name, faction2_name = parse_result
        
        # Resolve both factions
        ok1, err1, faction1 = _resolve_faction_by_name(faction1_name)
        if not ok1 or not faction1:
            return True, f"First faction: {err1 or 'not found'}", emits, broadcasts
            
        ok2, err2, faction2 = _resolve_faction_by_name(faction2_name)
        if not ok2 or not faction2:
            return True, f"Second faction: {err2 or 'not found'}", emits, broadcasts
        
        # Prevent self-rivalry
        if faction1.faction_id == faction2.faction_id:
            return True, "A faction cannot be rival with itself.", emits, broadcasts
        
        # Create bidirectional rivalry (both factions mark each other as rivals)
        added1 = faction1.add_rival(faction2.faction_id)
        added2 = faction2.add_rival(faction1.faction_id)
        
        if added1 or added2:
            _save_world()
            if added1 and added2:
                emits.append({
                    'type': 'system',
                    'content': f"Created rivalry between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]'."
                })
            else:
                emits.append({
                    'type': 'system',
                    'content': f"Rivalry between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]' already existed."
                })
        else:
            emits.append({
                'type': 'system',
                'content': f"Rivalry between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]' already exists."
            })
        
        return True, None, emits, broadcasts

    # /faction removerival <faction1> | <faction2>
    if sub == 'removerival':
        if not sub_args:
            return True, "Usage: /faction removerival <faction1> | <faction2>", emits, broadcasts
            
        parts_joined = " ".join(sub_args)
        
        # Validate pipe syntax
        if not _validate_pipe_syntax(parts_joined, 2):
            return True, "Usage: /faction removerival <faction1> | <faction2>", emits, broadcasts
        
        parse_result = safe_call(lambda: parse_pipe_parts(parts_joined, expected=2))
        if parse_result is None:
            return True, "Usage: /faction removerival <faction1> | <faction2>", emits, broadcasts
            
        faction1_name, faction2_name = parse_result
        
        # Resolve both factions
        ok1, err1, faction1 = _resolve_faction_by_name(faction1_name)
        if not ok1 or not faction1:
            return True, f"First faction: {err1 or 'not found'}", emits, broadcasts
            
        ok2, err2, faction2 = _resolve_faction_by_name(faction2_name)
        if not ok2 or not faction2:
            return True, f"Second faction: {err2 or 'not found'}", emits, broadcasts
        
        # Remove bidirectional rivalry
        removed1 = faction1.remove_rival(faction2.faction_id)
        removed2 = faction2.remove_rival(faction1.faction_id)
        
        if removed1 or removed2:
            _save_world()
            emits.append({
                'type': 'system',
                'content': f"Removed rivalry between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]'."
            })
        else:
            emits.append({
                'type': 'system',
                'content': f"No rivalry existed between '[b]{faction1.name}[/b]' and '[b]{faction2.name}[/b]'."
            })
        
        return True, None, emits, broadcasts

    # Command not recognized - let the router know this wasn't handled
    return False, None, emits, broadcasts
