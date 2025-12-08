"""NPC admin operations for /npc commands.

Terminology:
- "room name" (user input) is fuzzy-resolved to a stable internal room id.
- room id (internal) is the key in world.rooms and used for storage.

Supports:
    - /npc add <room name> | <npc name> | <npc description>
    - /npc remove <npc name>  (removes from the admin's current room)
    - /npc generate  (contextual: generates NPC fitting current room and world)
    - /npc generate <room name> | <npc name> | <description>  (explicit)

Backward compatibility:
    - /npc add <room_id> <npc name...>
    - /npc remove <room_id> <npc name...>
    - /npc setdesc <npc name> | <description>
    - /npc setrelation <source name> | <relationship type> | <target name>
    - /npc removerelations <source name> | <target name>
    - /npc setattr <npc name> | <attribute> | <value>
    - /npc setaspect <npc name> | <type> | <value>
    - /npc setmatrix <npc name> | <axis> | <value>
    - /npc sheet <npc name>
    - /npc familygen <room name> | <target npc name> | <relationship>

Service Contract:
    All public functions return 4-tuple: (handled, error, emits, broadcasts)
    - handled: bool - whether the command was recognized
    - error: str | None - error message if any
    - emits: List[dict] - messages to send to the acting player
    - broadcasts: List[Tuple[str, dict]] - (room_id, message) pairs for room broadcasts
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import os
import json
import re

from world import CharacterSheet
from ai_utils import safety_settings_for_level as _shared_safety_settings
from id_parse_utils import (
    strip_quotes as _strip_quotes,
    parse_pipe_parts as _parse_pipe_parts,
    resolve_room_id as _resolve_room_id,
    resolve_npcs_in_room as _resolve_npcs_in_room,
)
import ambition_service
from ambition_model import Ambition

# Optional Gemini support (AI-assisted NPC generation)
try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None  # type: ignore

# Safety categories (optional; depend on SDK version)
try:
    from google.generativeai.types import HarmCategory, HarmBlockThreshold  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    HarmCategory = None  # type: ignore
    HarmBlockThreshold = None  # type: ignore

_GEN_MODEL = None  # lazy-initialized Gemini model


def _get_gemini_model():
    """Return a singleton GenerativeModel if configured; else None.

    Reads the API key from GEMINI_API_KEY or GOOGLE_API_KEY.
    Uses the lightweight flash model for speed. Mirrors server.py defaults.
    """
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


def _safety_settings_for_level(level: str | None):
    """Backwards-compatible wrapper delegating to shared ai_utils.

    Returns a list suitable for Gemini's safety_settings, or None if the SDK
    isn't available or an error occurs.
    """
    try:
        return _shared_safety_settings(level)
    except Exception:
        return None


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort extraction of a single JSON object from model text.

    Accepts raw JSON or text with code fences. Returns dict or None.
    """
    if not text:
        return None
    # Strip Markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    # Find the first {...} block
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start:end+1]
    try:
        return json.loads(snippet)
    except Exception:
        # Try to relax trailing commas and similar minor issues (very light touch)
        try:
            snippet2 = re.sub(r",\s*([}\]])", r"\1", snippet)
            return json.loads(snippet2)
        except Exception:
            return None


def _normalize_room_input(world, sid: str | None, typed: str) -> tuple[bool, str | None, str | None]:
    t = _strip_quotes(typed or "")
    if t.lower() == 'here':
        if not sid or sid not in getattr(world, 'players', {}):
            return False, 'You are nowhere.', None
        player = world.players.get(sid)
        rid = getattr(player, 'room_id', None)
        if not rid:
            return False, 'You are nowhere.', None
        return True, None, rid
    return True, None, t


def _generate_nexus_profile(model, name: str, description: str, world_context: str) -> Optional[dict]:
    """Generate a full Nexus System character profile using AI."""
    prompt = (
        "You are a game master for a TTRPG using the Nexus System (GURPS + FATE + SWN).\n"
        f"Create a full character profile for an NPC named '{name}'.\n"
        f"Description: {description}\n\n"
        f"[World Context]\n{world_context}\n\n"
        "Return ONLY a JSON object with the following schema:\n"
        "{\n"
        "  \"high_concept\": \"string (FATE aspect)\",\n"
        "  \"trouble\": \"string (FATE aspect)\",\n"
        "  \"background\": \"string (SWN style)\",\n"
        "  \"focus\": \"string (SWN style)\",\n"
        "  \"strength\": int (3-18, avg 10),\n"
        "  \"dexterity\": int (3-18, avg 10),\n"
        "  \"intelligence\": int (3-18, avg 10),\n"
        "  \"health\": int (3-18, avg 10),\n"
        "  \"advantages\": [{\"name\": \"string\", \"cost\": int}],\n"
        "  \"disadvantages\": [{\"name\": \"string\", \"cost\": int}],\n"
        "  \"quirks\": [\"string\"],\n"
        "  \"psychosocial_matrix\": {\n"
        "    \"sexuality_hom_het\": int (-10 to 10),\n"
        "    \"physical_presentation_mas_fem\": int (-10 to 10),\n"
        "    \"social_presentation_mas_fem\": int (-10 to 10),\n"
        "    \"auth_egal\": int (-10 to 10),\n"
        "    \"cons_lib\": int (-10 to 10),\n"
        "    \"spirit_mat\": int (-10 to 10),\n"
        "    \"ego_alt\": int (-10 to 10),\n"
        "    \"hed_asc\": int (-10 to 10),\n"
        "    \"nih_mor\": int (-10 to 10),\n"
        "    \"rat_rom\": int (-10 to 10),\n"
        "    \"ske_abso\": int (-10 to 10)\n"
        "  }\n"
        "}\n\n"
        "IMPORTANT: Advantages must total ≤40 points, disadvantages ≥-40 points, quirks max 5."
    )
    try:
        resp = model.generate_content(prompt)
        text = getattr(resp, 'text', None) or str(resp)
        return _extract_json_object(text)
    except Exception:
        return None


def _generate_contextual_npc(model, world_name: Optional[str], world_desc: Optional[str], 
                              world_conflict: Optional[str], room_desc: str, 
                              existing_npcs: List[str], safety_level: str) -> Optional[dict]:
    """Generate a contextually appropriate NPC that fits the world and current room.
    
    Returns a dict with 'name', 'description', and full Nexus System profile.
    """
    world_context = []
    if world_name:
        world_context.append(f"World Name: {world_name}")
    if world_desc:
        world_context.append(f"World Description: {world_desc}")
    if world_conflict:
        world_context.append(f"Main Conflict: {world_conflict}")
    
    wc_text = "\n".join(world_context) if world_context else "A generic fantasy world."
    
    existing_text = ""
    if existing_npcs:
        existing_text = "\n[Existing NPCs in this room]\n" + "\n".join(existing_npcs)
    
    prompt = (
        "You are a game master for a TTRPG using the Nexus System (GURPS + FATE + SWN).\n"
        "Generate a complete NPC that would naturally fit in this location within the world.\n"
        "The NPC should complement existing NPCs (not duplicate them) and fit the room's purpose.\n\n"
        f"[World Context]\n{wc_text}\n\n"
        f"[Room Description]\n{room_desc}\n"
        f"{existing_text}\n\n"
        "Return ONLY a JSON object with this schema:\n"
        "{\n"
        "  \"name\": \"string (unique, fitting name)\",\n"
        "  \"description\": \"string (1-3 sentences about who they are)\",\n"
        "  \"high_concept\": \"string (FATE aspect)\",\n"
        "  \"trouble\": \"string (FATE aspect)\",\n"
        "  \"background\": \"string (SWN background)\",\n"
        "  \"focus\": \"string (SWN focus)\",\n"
        "  \"strength\": int (3-18, avg 10),\n"
        "  \"dexterity\": int (3-18, avg 10),\n"
        "  \"intelligence\": int (3-18, avg 10),\n"
        "  \"health\": int (3-18, avg 10),\n"
        "  \"advantages\": [{\"name\": \"string\", \"cost\": int}],\n"
        "  \"disadvantages\": [{\"name\": \"string\", \"cost\": int}],\n"
        "  \"quirks\": [\"string\"],\n"
        "  \"psychosocial_matrix\": {\n"
        "    \"sexuality_hom_het\": int (-10 to 10),\n"
        "    \"physical_presentation_mas_fem\": int (-10 to 10),\n"
        "    \"social_presentation_mas_fem\": int (-10 to 10),\n"
        "    \"auth_egal\": int (-10 to 10),\n"
        "    \"cons_lib\": int (-10 to 10),\n"
        "    \"spirit_mat\": int (-10 to 10),\n"
        "    \"ego_alt\": int (-10 to 10),\n"
        "    \"hed_asc\": int (-10 to 10),\n"
        "    \"nih_mor\": int (-10 to 10),\n"
        "    \"rat_rom\": int (-10 to 10),\n"
        "    \"ske_abso\": int (-10 to 10)\n"
        "  }\n"
        "}\n\n"
        "IMPORTANT: Advantages must total ≤40 points, disadvantages ≥-40 points, quirks max 5.\n"
        "Make the NPC interesting and appropriate for the setting."
    )
    
    try:
        safety = _safety_settings_for_level(safety_level)
        if safety is not None:
            resp = model.generate_content(prompt, safety_settings=safety)
        else:
            resp = model.generate_content(prompt)
        text = getattr(resp, 'text', None) or str(resp)
        return _extract_json_object(text)
    except Exception:
        return None


def handle_npc_command(world, state_path: str, sid: str | None, args: list[str]) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Handle /npc commands.
    
    Returns: (handled, error, emits, broadcasts)
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    if not args:
        return True, 'Usage: /npc <add|remove|setdesc|setrelation|removerelations|familygen|generate|setattr|setaspect|setmatrix|sheet> ...', emits, broadcasts

    sub = args[0].lower()
    sub_args = args[1:]

    if sub == 'add':
    # New syntax (user-facing room name): /npc add <room name> | <npc name> | <npc description>
        parts_joined = " ".join(sub_args)
        if '|' in parts_joined:
            try:
                room_in, name_in, desc_in = _parse_pipe_parts(parts_joined, expected=3)
            except Exception:
                return True, 'Usage: /npc add <room name> | <npc name> | <npc description>', emits, broadcasts
            room_in = _strip_quotes(room_in)
            name_in = _strip_quotes(name_in)
            desc_in = desc_in.strip()
            if not room_in or not name_in:
                return True, 'Usage: /npc add <room name> | <npc name> | <npc description>', emits, broadcasts
            okn, errn, norm = _normalize_room_input(world, sid, room_in)
            if not okn:
                return True, errn, emits, broadcasts
            val = norm if isinstance(norm, str) else room_in
            rok, rerr, room_res = _resolve_room_id(world, val)
            if not rok or not room_res:
                return True, (rerr or f"Room '{room_in}' not found."), emits, broadcasts
            room = world.rooms.get(room_res)
            if not room:
                return True, f"Room '{room_res}' not found.", emits, broadcasts
            npc_name = name_in
            room.npcs.add(npc_name)
            # Ensure NPC sheet with provided description (create or update)
            sheet = world.npc_sheets.get(npc_name)
            if sheet is None:
                sheet = CharacterSheet(display_name=npc_name, description=(desc_in or f"An NPC named {npc_name}."))
                world.npc_sheets[npc_name] = sheet
            else:
                if desc_in:
                    sheet.description = desc_in
            # Ensure a stable id for this NPC
            try:
                world.get_or_create_npc_id(npc_name)
            except Exception:
                pass
            _save_silent(world, state_path)
            emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added to room '{room_res}'."})
            return True, None, emits, broadcasts

        # Legacy syntax fallback: /npc add <room_id> <npc name...>
        if len(sub_args) < 2:
            return True, 'Usage: /npc add <room name> | <npc name> | <npc description>', emits, broadcasts
        room_id = _strip_quotes(sub_args[0])
        npc_name = _strip_quotes(" ".join(sub_args[1:]).strip())
        okn, errn, norm = _normalize_room_input(world, sid, room_id)
        if not okn:
            return True, errn, emits, broadcasts
        val = norm if isinstance(norm, str) else room_id
        rok, rerr, room_res = _resolve_room_id(world, val)
        if not rok or not room_res:
            return True, (rerr or f"Room '{room_id}' not found."), emits, broadcasts
        room = world.rooms.get(room_res)
        if not room:
            return True, f"Room '{room_res}' not found.", emits, broadcasts
        room.npcs.add(npc_name)
        if npc_name not in world.npc_sheets:
            world.npc_sheets[npc_name] = CharacterSheet(display_name=npc_name, description=f"An NPC named {npc_name}.")
        try:
            world.get_or_create_npc_id(npc_name)
        except Exception:
            pass
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added to room '{room_res}'."})
        return True, None, emits, broadcasts

    if sub == 'familygen':
        # /npc familygen <room name> | <target npc name> | <relationship>
        try:
            parts_joined = " ".join(sub_args)
            room_in, target_in, rel_in = _parse_pipe_parts(parts_joined, expected=3)
        except Exception:
            return True, 'Usage: /npc familygen <room name> | <target npc name> | <relationship>', emits, broadcasts

        room_in = _strip_quotes(room_in)
        target_name = _strip_quotes(target_in)
        relationship = rel_in.strip()
        if not room_in or not target_name or not relationship:
            return True, 'Usage: /npc familygen <room name> | <target npc name> | <relationship>', emits, broadcasts

        # Resolve room (support 'here')
        okn, errn, norm = _normalize_room_input(world, sid, room_in)
        if not okn:
            return True, errn, emits, broadcasts
        val = norm if isinstance(norm, str) else room_in
        rok, rerr, room_res = _resolve_room_id(world, val)
        if not rok or not room_res:
            return True, (rerr or f"Room '{room_in}' not found."), emits, broadcasts
        room = world.rooms.get(room_res)
        if not room:
            return True, f"Room '{room_res}' not found.", emits, broadcasts

        # Ensure target NPC sheet exists (create if missing)
        target_sheet = world.npc_sheets.get(target_name)
        if target_sheet is None:
            target_sheet = CharacterSheet(display_name=target_name, description=f"An NPC named {target_name}.")
            world.npc_sheets[target_name] = target_sheet
            try:
                world.get_or_create_npc_id(target_name)
            except Exception:
                pass

        # Build an AI prompt to generate the related NPC as JSON
        world_name = getattr(world, 'world_name', None)
        world_desc = getattr(world, 'world_description', None)
        world_conflict = getattr(world, 'world_conflict', None)
        world_context = []
        if world_name:
            world_context.append(f"Name: {world_name}")
        if world_desc:
            world_context.append(f"Description: {world_desc}")
        if world_conflict:
            world_context.append(f"Main Conflict: {world_conflict}")
        wc_text = "\n".join(world_context)

        prompt = (
            "You are designing characters for a text-based roleplaying world.\n"
            "Create ONE new NPC who has the following relationship to the target NPC.\n"
            "Return ONLY a compact JSON object with keys: name, description. No markdown, no commentary.\n"
            "Description should be 1-3 sentences, evocative but PG-13. Keep proper nouns consistent with the world.\n\n"
            f"[World]\n{wc_text}\n\n" if wc_text else ""
        ) + (
            f"[Target NPC]\nName: {target_sheet.display_name}\nDescription: {target_sheet.description}\n\n"
            f"[Relationship]\nThe new NPC is the target's: {relationship}.\n\n"
            "Output JSON example: {\"name\":\"<unique name>\",\"description\":\"<1-3 sentences>\"}"
        )

        new_name: Optional[str] = None
        new_desc: Optional[str] = None

        model = _get_gemini_model()
        if model is not None:
            try:
                safety = _safety_settings_for_level(getattr(world, 'safety_level', 'G'))
                if safety is not None:
                    ai_resp = model.generate_content(prompt, safety_settings=safety)
                else:
                    ai_resp = model.generate_content(prompt)
                text = getattr(ai_resp, 'text', None) or str(ai_resp)
                parsed = _extract_json_object(text)
                if parsed and isinstance(parsed, dict):
                    nm = str(parsed.get('name') or '').strip()
                    ds = str(parsed.get('description') or '').strip()
                    if nm:
                        new_name = nm
                    if ds:
                        new_desc = ds
            except Exception:
                # Fall back to offline path below
                pass

        if not new_name:
            # Offline fallback: simple synthesized name/desc
            base = target_sheet.display_name
            new_name = f"{base}'s {relationship.title()}"
        if not new_desc:
            new_desc = f"A character closely connected to {target_sheet.display_name} as their {relationship}."

        # Ensure uniqueness of NPC name in this world
        existing = set(getattr(world, 'npc_sheets', {}).keys())
        if new_name in existing:
            suffix = 2
            base = new_name
            while new_name in existing and suffix < 100:
                new_name = f"{base} {suffix}"
                suffix += 1

        # Create the NPC sheet and place into room
        sheet = CharacterSheet(display_name=new_name, description=new_desc)
        world.npc_sheets[new_name] = sheet
        room.npcs.add(new_name)
        # Ensure ids and set mutual relationship
        try:
            tgt_id = world.get_or_create_npc_id(target_sheet.display_name)
        except Exception:
            tgt_id = None
        try:
            new_id = world.get_or_create_npc_id(new_name)
        except Exception:
            new_id = None
        rels: Dict[str, Dict[str, str]] = getattr(world, 'relationships', {})
        if tgt_id and new_id:
            if tgt_id not in rels:
                rels[tgt_id] = {}
            if new_id not in rels:
                rels[new_id] = {}
            rels[tgt_id][new_id] = relationship
            rels[new_id][tgt_id] = relationship
            world.relationships = rels

        _save_silent(world, state_path)

        emits.append({'type': 'system', 'content': (
            f"[b][Experimental][/b] Generated related NPC: [b]{new_name}[/b] — placed in room '{room_res}'.\n"
            f"Relationship: {target_sheet.display_name} ⇄ {new_name} as [{relationship}]\n"
            f"Description: {new_desc}"
        )})
        return True, None, emits, broadcasts

    if sub == 'list':
        # /npc list [filter]
        filter_str = sub_args[0].lower() if sub_args else ""
        lines = ["[b]NPC List:[/b]"]
        count = 0
        sorted_ids = sorted(world.npc_sheets.keys())
        for nid in sorted_ids:
            if not filter_str or filter_str in nid.lower():
                sheet = world.npc_sheets[nid]
                lines.append(f"- {nid} ({sheet.display_name})")
                count += 1
                if count >= 50:
                    lines.append("... (truncated)")
                    break
        emits.append({'type': 'system', 'content': "\n".join(lines)})
        return True, None, emits, broadcasts

    if sub == 'delete':
        # /npc delete <npc_name> (Permanently from world)
        if not sub_args:
             return True, "Usage: /npc delete <npc name>", emits, broadcasts
        
        parts_joined = " ".join(sub_args)
        npc_name = _strip_quotes(parts_joined)
        
        if npc_name not in world.npc_sheets:
             return True, f"NPC '{npc_name}' not found in registry.", emits, broadcasts
             
        # Cleanup
        # 1. Remove from all rooms
        count_removed = 0
        for r in world.rooms.values():
            if r.npcs and npc_name in r.npcs:
                r.npcs.discard(npc_name)
                count_removed += 1
                
        # 2. Remove character sheet
        del world.npc_sheets[npc_name]
        
        # 3. Remove ID mapping if exists
        try:
             if npc_name in world.npc_ids:
                 del world.npc_ids[npc_name]
        except Exception: pass
            
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' permanently deleted. Removed from {count_removed} rooms."})
        return True, None, emits, broadcasts

    if sub == 'remove':
        # New default: remove by name from the admin's current room
        parts_joined = " ".join(sub_args).strip()
        if parts_joined and '|' not in parts_joined and len(sub_args) >= 1 and sid is not None:
            npc_in = _strip_quotes(parts_joined)
            player = world.players.get(sid)
            if not player:
                return True, 'Please authenticate first.', emits, broadcasts
            room = world.rooms.get(player.room_id)
            if not room:
                return True, 'You are nowhere.', emits, broadcasts
            # Fuzzy resolve within current room
            resolved = _resolve_npcs_in_room(room, [npc_in])
            if not resolved:
                return True, f"NPC '{npc_in}' not found in this room.", emits, broadcasts
            npc_name = resolved[0]
            room.npcs.discard(npc_name)
            _save_silent(world, state_path)
            emits.append({'type': 'system', 'content': f"NPC '{npc_name}' removed from room '{room.id}'."})
            return True, None, emits, broadcasts

        # Legacy/explicit: /npc remove <room_id> | <npc name>  or  /npc remove <room_id> <npc name...>
        if '|' in parts_joined:
            try:
                room_in, npc_in = _parse_pipe_parts(parts_joined, expected=2)
            except Exception:
                return True, 'Usage: /npc remove <room_id> | <npc name>', emits, broadcasts
            room_in = _strip_quotes(room_in)
            npc_in = _strip_quotes(npc_in)
        else:
            if len(sub_args) < 2:
                return True, 'Usage: /npc remove <npc name>', emits, broadcasts
            room_in = _strip_quotes(sub_args[0])
            npc_in = _strip_quotes(" ".join(sub_args[1:]).strip())
        okn, errn, norm = _normalize_room_input(world, sid, room_in)
        if not okn:
            return True, errn, emits, broadcasts
        val = norm if isinstance(norm, str) else room_in
        rok, rerr, room_res = _resolve_room_id(world, val)
        if not rok or not room_res:
            return True, (rerr or f"Room '{room_in}' not found."), emits, broadcasts
        room = world.rooms.get(room_res)
        if not room:
            return True, f"Room '{room_res}' not found.", emits, broadcasts
        # Try fuzzy resolve in that room
        resolved = _resolve_npcs_in_room(room, [npc_in])
        npc_name = resolved[0] if resolved else npc_in
        if npc_name not in room.npcs:
            return True, f"NPC '{npc_in}' not in room '{room_res}'.", emits, broadcasts
        room.npcs.discard(npc_name)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' removed from room '{room_res}'."})
        return True, None, emits, broadcasts

    if sub == 'setdesc':
        try:
            parts_joined = " ".join(sub_args)
            npc_name, desc = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /npc setdesc <npc name> | <description>', emits, broadcasts
        npc_name = _strip_quotes(npc_name)
        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            sheet = CharacterSheet(display_name=npc_name)
            world.npc_sheets[npc_name] = sheet
        # Ensure a stable id for this NPC as well
        try:
            world.get_or_create_npc_id(npc_name)
        except Exception:
            pass
        sheet.description = desc
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' description updated."})
        return True, None, emits, broadcasts

    if sub == 'setrelation':
        # /npc setrelation <source name> | <relationship type> | <target name> [| mutual]
        try:
            parts_joined = " ".join(sub_args)
            # Accept 3 or 4 parts. The 4th optional part is the literal word 'mutual'.
            parts = _parse_pipe_parts(parts_joined)
            if len(parts) < 3:
                raise ValueError('not enough parts')
            # Rejoin extras beyond 3 into the 3rd slot to be tolerant of extra pipes in names
            if len(parts) > 4:
                parts = parts[:3] + ["mutual"]  # if too many, prioritize setting mutual
            if len(parts) == 3:
                src_in, rel_in, tgt_in = parts
                mutual_flag = False
            else:
                src_in, rel_in, tgt_in, mutual_raw = parts[:4]
                mutual_flag = str(mutual_raw).strip().lower() in ("mutual", "yes", "true", "both")
        except Exception:
            return True, 'Usage: /npc setrelation <source name> | <relationship type> | <target name> | mutual', emits, broadcasts

        src_name = _strip_quotes(src_in)
        tgt_name = _strip_quotes(tgt_in)
        rel_type = rel_in.strip()
        if not src_name or not tgt_name or not rel_type:
            return True, 'Usage: /npc setrelation <source name> | <relationship type> | <target name> | mutual', emits, broadcasts

        # Resolve entity IDs for source and target. Entities can be: connected players, any user by display name, or NPC by name.
        def resolve_entity_id(name: str) -> Tuple[Optional[str], Optional[str]]:
            # Try connected players first
            try:
                for psid, p in list(getattr(world, 'players', {}).items()):
                    if p.sheet and p.sheet.display_name.lower() == name.lower():
                        # Players map to their user id if connected
                        # Find user id via sessions if available, else derive by matching user display_name
                        for uid, user in list(getattr(world, 'users', {}).items()):
                            if user.display_name.lower() == name.lower():
                                return user.user_id, user.display_name
            except Exception:
                pass
            # Try any known user
            try:
                user = world.get_user_by_display_name(name)
                if user:
                    return user.user_id, user.display_name
            except Exception:
                pass
            # Try NPC by name
            try:
                if name in getattr(world, 'npc_sheets', {}):
                    npc_id = world.get_or_create_npc_id(name)
                    return npc_id, name
            except Exception:
                pass
            # Try fuzzy within NPC names
            try:
                names = list(getattr(world, 'npc_sheets', {}).keys())
                # simple ci-exact / prefix / substring
                cand = None
                for n in names:
                    if n.lower() == name.lower():
                        cand = n; break
                if cand is None:
                    prefs = [n for n in names if n.lower().startswith(name.lower())]
                    if len(prefs) == 1:
                        cand = prefs[0]
                if cand is None:
                    subs = [n for n in names if name.lower() in n.lower()]
                    if len(subs) == 1:
                        cand = subs[0]
                if cand is not None:
                    npc_id = world.get_or_create_npc_id(cand)
                    return npc_id, cand
            except Exception:
                pass
            return None, None

        src_id, src_resolved = resolve_entity_id(src_name)
        if not src_id:
            return True, f"Source '{src_name}' not found as a player, user, or NPC.", emits, broadcasts
        tgt_id, tgt_resolved = resolve_entity_id(tgt_name)
        if not tgt_id:
            return True, f"Target '{tgt_name}' not found as a player, user, or NPC.", emits, broadcasts

        # Set directed relationship
        rels: Dict[str, Dict[str, str]] = getattr(world, 'relationships', {})
        if src_id not in rels:
            rels[src_id] = {}
        rels[src_id][tgt_id] = rel_type
        # Optional reciprocal
        if mutual_flag:
            if tgt_id not in rels:
                rels[tgt_id] = {}
            rels[tgt_id][src_id] = rel_type
        world.relationships = rels
        _save_silent(world, state_path)
        # Report with resolved display names
        src_disp = src_resolved or src_name
        tgt_disp = tgt_resolved or tgt_name
        if mutual_flag:
            emits.append({'type': 'system', 'content': f"Relationship set (mutual): {src_disp} ⇄ {tgt_disp} as [{rel_type}]"})
        else:
            emits.append({'type': 'system', 'content': f"Relationship set: {src_disp} —[{rel_type}]→ {tgt_disp}"})
        return True, None, emits, broadcasts

    if sub == 'removerelations':
        # /npc removerelations <source> | <target>
        try:
            parts_joined = " ".join(sub_args)
            src_in, tgt_in = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /npc removerelations <source> | <target>', emits, broadcasts

        src_name = _strip_quotes(src_in)
        tgt_name = _strip_quotes(tgt_in)
        if not src_name or not tgt_name:
            return True, 'Usage: /npc removerelations <source> | <target>', emits, broadcasts

        # Reuse resolver from setrelation
        def resolve_entity_id(name: str) -> Tuple[Optional[str], Optional[str]]:
            try:
                for psid, p in list(getattr(world, 'players', {}).items()):
                    if p.sheet and p.sheet.display_name.lower() == name.lower():
                        for uid, user in list(getattr(world, 'users', {}).items()):
                            if user.display_name.lower() == name.lower():
                                return user.user_id, user.display_name
            except Exception:
                pass
            try:
                user = world.get_user_by_display_name(name)
                if user:
                    return user.user_id, user.display_name
            except Exception:
                pass
            try:
                if name in getattr(world, 'npc_sheets', {}):
                    npc_id = world.get_or_create_npc_id(name)
                    return npc_id, name
            except Exception:
                pass
            try:
                names = list(getattr(world, 'npc_sheets', {}).keys())
                cand = None
                for n in names:
                    if n.lower() == name.lower():
                        cand = n; break
                if cand is None:
                    prefs = [n for n in names if n.lower().startswith(name.lower())]
                    if len(prefs) == 1:
                        cand = prefs[0]
                if cand is None:
                    subs = [n for n in names if name.lower() in n.lower()]
                    if len(subs) == 1:
                        cand = subs[0]
                if cand is not None:
                    npc_id = world.get_or_create_npc_id(cand)
                    return npc_id, cand
            except Exception:
                pass
            return None, None

        src_id, src_resolved = resolve_entity_id(src_name)
        if not src_id:
            return True, f"Source '{src_name}' not found as a player, user, or NPC.", emits, broadcasts
        tgt_id, tgt_resolved = resolve_entity_id(tgt_name)
        if not tgt_id:
            return True, f"Target '{tgt_name}' not found as a player, user, or NPC.", emits, broadcasts

        rels: Dict[str, Dict[str, str]] = getattr(world, 'relationships', {})
        changed = False
        if src_id in rels and tgt_id in rels[src_id]:
            try:
                del rels[src_id][tgt_id]
                changed = True
                if not rels[src_id]:
                    del rels[src_id]
            except Exception:
                pass
        if tgt_id in rels and src_id in rels.get(tgt_id, {}):
            try:
                del rels[tgt_id][src_id]
                changed = True
                if not rels[tgt_id]:
                    del rels[tgt_id]
            except Exception:
                pass
        world.relationships = rels
        if changed:
            _save_silent(world, state_path)
            src_disp = src_resolved or src_name
            tgt_disp = tgt_resolved or tgt_name
            emits.append({'type': 'system', 'content': f"Removed relationships between {src_disp} and {tgt_disp}."})
        else:
            emits.append({'type': 'system', 'content': 'No relationships existed to remove.'})
        return True, None, emits, broadcasts

    if sub == 'generate':
        # /npc generate  (contextual to player's current room)
        # OR /npc generate <room name> | <npc name> | <description>
        
        # Check for AI model first
        model = _get_gemini_model()
        if not model:
            return True, "AI generation is not available (no API key configured).", emits, broadcasts

        # Determine if this is contextual (no args) or explicit (with args)
        parts_joined = " ".join(sub_args)
        contextual_mode = not parts_joined.strip() or '|' not in parts_joined
        
        if contextual_mode:
            # Contextual generation: use player's current room
            if not sid:
                return True, 'Usage: /npc generate  (from your current room) OR /npc generate <room name> | <npc name> | <description>', emits, broadcasts
            
            player = world.players.get(sid)
            if not player:
                return True, 'You must be logged in to use contextual generation.', emits, broadcasts
            
            room_res = player.room_id
            room = world.rooms.get(room_res)
            if not room:
                return True, 'You are not in a valid room.', emits, broadcasts

            # Build rich context from world and room
            world_name = getattr(world, 'world_name', None)
            world_desc = getattr(world, 'world_description', None)
            world_conflict = getattr(world, 'world_conflict', None)
            
            # Get other NPCs in the room for context
            existing_npcs = []
            for npc_name in (room.npcs or set()):
                npc_sheet = world.npc_sheets.get(npc_name)
                if npc_sheet:
                    existing_npcs.append(f"  - {npc_name}: {npc_sheet.description}")
            
            emits.append({'type': 'system', 'content': f"Generating contextual NPC for {room.id}... please wait."})
            
            # Generate a full NPC that fits the world and room
            profile = _generate_contextual_npc(model, world_name, world_desc, world_conflict, room.description, existing_npcs, getattr(world, 'safety_level', 'G'))
            if not profile:
                return True, "AI generation failed.", emits, broadcasts
            
            npc_name = profile.get('name', 'Generated NPC')
            npc_desc = profile.get('description', 'A generated character.')
            
        else:
            # Explicit generation: parse arguments
            try:
                room_in, name_in, desc_in = _parse_pipe_parts(parts_joined, expected=3)
            except Exception:
                return True, 'Usage: /npc generate  OR  /npc generate <room name> | <npc name> | <description>', emits, broadcasts
            
            room_in = _strip_quotes(room_in)
            name_in = _strip_quotes(name_in)
            desc_in = desc_in.strip()
            
            if not room_in or not name_in:
                return True, 'Usage: /npc generate  OR  /npc generate <room name> | <npc name> | <description>', emits, broadcasts

            # Resolve room
            okn, errn, norm = _normalize_room_input(world, sid, room_in)
            if not okn:
                return True, errn, emits, broadcasts
            val = norm if isinstance(norm, str) else room_in
            rok, rerr, room_res = _resolve_room_id(world, val)
            if not rok or not room_res:
                return True, (rerr or f"Room '{room_in}' not found."), emits, broadcasts
            room = world.rooms.get(room_res)
            if not room:
                return True, f"Room '{room_res}' not found.", emits, broadcasts

            # Build context
            world_name = getattr(world, 'world_name', None)
            world_desc = getattr(world, 'world_description', None)
            world_context = []
            if world_name:
                world_context.append(f"Name: {world_name}")
            if world_desc:
                world_context.append(f"Description: {world_desc}")
            wc_text = "\n".join(world_context)

            emits.append({'type': 'system', 'content': f"Generating Nexus profile for '{name_in}'... please wait."})
            
            # Generate
            profile = _generate_nexus_profile(model, name_in, desc_in, wc_text)
            if not profile:
                return True, "AI generation failed.", emits, broadcasts
            
            npc_name = name_in
            npc_desc = desc_in

        # Create/Update NPC with generated profile
        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            sheet = CharacterSheet(display_name=npc_name, description=npc_desc)
            world.npc_sheets[npc_name] = sheet
            room.npcs.add(npc_name)
            try:
                world.get_or_create_npc_id(npc_name)
            except Exception:
                pass
        else:
            sheet.description = npc_desc
        
        # Apply profile
        try:
            sheet.high_concept = str(profile.get('high_concept', ''))
            sheet.trouble = str(profile.get('trouble', ''))
            sheet.background = str(profile.get('background', ''))
            sheet.focus = str(profile.get('focus', ''))
            sheet.strength = int(profile.get('strength', 10))
            sheet.dexterity = int(profile.get('dexterity', 10))
            sheet.intelligence = int(profile.get('intelligence', 10))
            sheet.health = int(profile.get('health', 10))
            
            # Process advantages with proper allocation (max 40 points spent)
            advantages_raw = profile.get('advantages', [])
            if isinstance(advantages_raw, list):
                sheet.advantages = []
                total_adv = 0
                for adv in advantages_raw:
                    if isinstance(adv, dict):
                        cost = int(adv.get('cost', 5))
                        if total_adv + cost <= 40:
                            sheet.advantages.append(adv)
                            total_adv += cost
            
            # Process disadvantages with proper allocation (max -40 points)
            disadv_raw = profile.get('disadvantages', [])
            if isinstance(disadv_raw, list):
                sheet.disadvantages = []
                total_disadv = 0
                for dis in disadv_raw:
                    if isinstance(dis, dict):
                        cost = int(dis.get('cost', -5))
                        if total_disadv + cost >= -40:
                            sheet.disadvantages.append(dis)
                            total_disadv += cost
            
            # Quirks (max 5, worth -1 each)
            quirks_raw = profile.get('quirks', [])
            if isinstance(quirks_raw, list):
                sheet.quirks = quirks_raw[:5]
            
            # Psychosocial matrix
            matrix = profile.get('psychosocial_matrix', {})
            if isinstance(matrix, dict):
                for k, v in matrix.items():
                    if hasattr(sheet, k):
                        try:
                            # Clamp to valid range
                            val = max(-10, min(10, int(v)))
                            setattr(sheet, k, val)
                        except Exception:
                            pass
            
            # Recalculate derived stats
            sheet.hp = sheet.strength
            sheet.max_hp = sheet.strength
            sheet.will = sheet.intelligence
            sheet.perception = sheet.intelligence
            sheet.fp = sheet.health
            sheet.max_fp = sheet.health
            
        except Exception as e:
            return True, f"Error applying profile: {e}", emits, broadcasts

        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' generated with full Nexus stats in {room.id}."})
        return True, None, emits, broadcasts

    if sub == 'setattr':
        # /npc setattr <npc name> | <attribute> | <value>
        try:
            parts_joined = " ".join(sub_args)
            npc_in, attr_in, val_in = _parse_pipe_parts(parts_joined, expected=3)
        except Exception:
            return True, 'Usage: /npc setattr <npc name> | <attribute> | <value>', emits, broadcasts
        
        npc_name = _strip_quotes(npc_in)
        attr = attr_in.strip().lower()
        try:
            val = int(val_in.strip())
        except ValueError:
            return True, 'Value must be an integer.', emits, broadcasts

        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            return True, f"NPC '{npc_name}' not found.", emits, broadcasts

        valid_attrs = {'strength', 'dexterity', 'intelligence', 'health', 'hp', 'max_hp', 'will', 'perception', 'fp', 'max_fp'}
        if attr not in valid_attrs:
            return True, f"Invalid attribute. Valid: {', '.join(sorted(valid_attrs))}", emits, broadcasts

        setattr(sheet, attr, val)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Set {npc_name}'s {attr} to {val}."})
        return True, None, emits, broadcasts

    if sub == 'setaspect':
        # /npc setaspect <npc name> | <type> | <value>
        try:
            parts_joined = " ".join(sub_args)
            npc_in, type_in, val_in = _parse_pipe_parts(parts_joined, expected=3)
        except Exception:
            return True, 'Usage: /npc setaspect <npc name> | <high_concept|trouble|background|focus> | <value>', emits, broadcasts
        
        npc_name = _strip_quotes(npc_in)
        aspect_type = type_in.strip().lower()
        val = val_in.strip()

        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            return True, f"NPC '{npc_name}' not found.", emits, broadcasts

        valid_types = {'high_concept', 'trouble', 'background', 'focus'}
        if aspect_type not in valid_types:
            return True, f"Invalid type. Valid: {', '.join(sorted(valid_types))}", emits, broadcasts

        setattr(sheet, aspect_type, val)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Set {npc_name}'s {aspect_type} to '{val}'."})
        return True, None, emits, broadcasts

    if sub == 'setmatrix':
        # /npc setmatrix <npc name> | <axis> | <value>
        try:
            parts_joined = " ".join(sub_args)
            npc_in, axis_in, val_in = _parse_pipe_parts(parts_joined, expected=3)
        except Exception:
            return True, 'Usage: /npc setmatrix <npc name> | <axis> | <value>', emits, broadcasts
        
        npc_name = _strip_quotes(npc_in)
        axis = axis_in.strip().lower()
        try:
            val = int(val_in.strip())
            if not (-10 <= val <= 10):
                raise ValueError
        except ValueError:
            return True, 'Value must be an integer between -10 and 10.', emits, broadcasts

        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            return True, f"NPC '{npc_name}' not found.", emits, broadcasts

        # Check if axis exists on sheet and is an int (heuristic)
        if not hasattr(sheet, axis) or not isinstance(getattr(sheet, axis), int):
             return True, f"Invalid matrix axis '{axis}'.", emits, broadcasts

        setattr(sheet, axis, val)
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Set {npc_name}'s {axis} to {val}."})
        return True, None, emits, broadcasts

    if sub == 'sheet':
        # /npc sheet <npc name>
        try:
            parts_joined = " ".join(sub_args)
            npc_in = _strip_quotes(parts_joined)
        except Exception:
            return True, 'Usage: /npc sheet <npc name>', emits, broadcasts
        
        sheet = world.npc_sheets.get(npc_in)
        if not sheet:
            return True, f"NPC '{npc_in}' not found.", emits, broadcasts

        lines = [
            f"[b]{sheet.display_name}[/b]",
            f"{sheet.description}",
            f"[b]High Concept:[/b] {sheet.high_concept}",
            f"[b]Trouble:[/b] {sheet.trouble}",
            f"[b]Background:[/b] {sheet.background}  [b]Focus:[/b] {sheet.focus}",
            f"[b]ST:[/b] {sheet.strength} [b]DX:[/b] {sheet.dexterity} [b]IQ:[/b] {sheet.intelligence} [b]HT:[/b] {sheet.health}",
            f"[b]HP:[/b] {sheet.hp}/{sheet.max_hp} [b]Will:[/b] {sheet.will} [b]Per:[/b] {sheet.perception} [b]FP:[/b] {sheet.fp}/{sheet.max_fp}",
            "[b]Matrix:[/b]",
            f"  Auth/Egal: {sheet.auth_egal}  Cons/Lib: {sheet.cons_lib}",
            f"  Ego/Alt: {sheet.ego_alt}  Rat/Rom: {sheet.rat_rom}",
        ]
        emits.append({'type': 'system', 'content': "\n".join(lines)})
        return True, None, emits, broadcasts

    if sub == 'psych':
        # /npc psych <npc name>
        try:
            parts_joined = " ".join(sub_args)
            npc_in = _strip_quotes(parts_joined)
        except Exception:
            return True, 'Usage: /npc psych <npc name>', emits, broadcasts
        
        sheet = world.npc_sheets.get(npc_in)
        if not sheet:
            return True, f"NPC '{npc_in}' not found.", emits, broadcasts

        gate_open = ambition_service.check_maslow_gate(sheet)
        gate_status = "[color=green]OPEN[/color]" if gate_open else "[color=red]CLOSED (Needs too low)[/color]"

        lines = [
            f"[b]Psych Profile: {sheet.display_name}[/b]",
            f"[b]Maslow's Gate:[/b] {gate_status}",
            f"  Hunger: {sheet.hunger:.1f}  Thirst: {sheet.thirst:.1f}",
            f"  Safety: {sheet.safety:.1f}  Social: {sheet.socialization:.1f}",
            "",
            "[b]Ambition:[/b]"
        ]
        
        if sheet.ambition:
            a = sheet.ambition
            lines.append(f"  [b]{a.name}[/b]: {a.description}")
            lines.append(f"  Progress: {a.current_milestone_idx}/{len(a.milestones)}")
            milestone = a.get_current_milestone()
            if milestone:
                lines.append(f"  Current Goal: {milestone.description} ({milestone.target_type}: {milestone.target_value})")
            else:
                lines.append("  [color=gold]Ambition Completed![/color]")
        else:
            lines.append("  None (Drifting through life...)")

        emits.append({'type': 'system', 'content': "\n".join(lines)})
        return True, None, emits, broadcasts

    if sub == 'setambition':
        # /npc setambition <npc name> | <ambition_type_id>
        # Types: wealth, warlord, explorer, political, peacekeeper
        try:
            parts_joined = " ".join(sub_args)
            npc_in, type_in = _parse_pipe_parts(parts_joined, expected=2)
        except Exception:
            return True, 'Usage: /npc setambition <npc name> | <wealth|warlord|explorer|political|peacekeeper>', emits, broadcasts
        
        npc_name = _strip_quotes(npc_in)
        amb_type = type_in.strip().lower()

        sheet = world.npc_sheets.get(npc_name)
        if not sheet:
            return True, f"NPC '{npc_name}' not found.", emits, broadcasts

        # Map string to generator function
        new_ambition = None
        if amb_type == 'wealth':
            new_ambition = ambition_service._create_wealth_ambition(sheet)
        elif amb_type == 'warlord':
            new_ambition = ambition_service._create_warlord_ambition(sheet)
        elif amb_type == 'explorer':
            new_ambition = ambition_service._create_explorer_ambition(sheet)
        elif amb_type == 'political':
            new_ambition = ambition_service._create_political_ambition(sheet)
        elif amb_type == 'peacekeeper':
            new_ambition = ambition_service._create_peacekeeper_ambition(sheet)
        else:
            return True, "Invalid ambition type. Options: wealth, warlord, explorer, political, peacekeeper", emits, broadcasts

        sheet.ambition = new_ambition
        _save_silent(world, state_path)
        emits.append({'type': 'system', 'content': f"Set {npc_name}'s ambition to {new_ambition.name}."})
        return True, None, emits, broadcasts

    return False, None, emits, broadcasts


def _save_silent(world, state_path: str) -> None:
    # Debounced persistence to reduce I/O during admin operations
    """Helper to save world state silently using the persistence façade."""
    from persistence_utils import save_world
    try:
        save_world(world, state_path, debounced=True)
    except Exception:
        pass
