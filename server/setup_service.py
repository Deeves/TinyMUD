"""
setup_service.py — World setup wizard (admin-only) extracted from the socket layer.

What this does, in plain words:
- Guides the first admin through naming their world, describing it, choosing a
  comfort/safety level, creating a starting room, and optionally adding a first
  NPC — all as a friendly interactive flow.

Design goals:
- Keep everything pure: return lists of messages to emit, never touch sockets.
- Store transient state in a provided world_setup_sessions dict keyed by SID.
- Make contributors comfortable: tiny functions, clear steps, gentle validation.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import re
import os

from world import Room, CharacterSheet
from persistence_utils import save_world
from safe_utils import safe_call, safe_call_with_default

# Optional AI import
try:
    import google.generativeai as genai  # type: ignore
    AI_AVAILABLE = True
except ImportError:
    genai = None
    AI_AVAILABLE = False


def _generate_quick_world(world, state_path: str) -> Tuple[bool, str]:
    """Generate a starting room and NPC using AI based on world details.

    Robustness goals:
    - Gemini may prepend prose or wrap JSON in code fences. We attempt to extract
      the first valid JSON object rather than assuming a pristine response.
    - Empty or filtered responses are surfaced with a friendly, actionable error.
    - We *never* raise; always return (ok, error_msg) for the caller to fall back.
    """
    if not AI_AVAILABLE or genai is None:  # pragma: no cover (depends on extra lib)
        return False, "AI not available for quick generation."

    world_name = getattr(world, 'world_name', 'Unnamed World')
    world_desc = getattr(world, 'world_description', 'A mysterious place.')
    world_conflict = getattr(world, 'world_conflict', 'Unknown conflicts.')

    # Configure API if not already done
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return False, "No Gemini API key found."
    try:  # pragma: no cover (network)
        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        # Prefer a stable / widely available model name. Fall back cascade.
        # Project standard: only use these two model identifiers.
        # 1. gemini-flash-lite-latest  (fast, inexpensive; preferred)
        # 2. gemini-2.5-pro            (heavier fallback if the flash model is unavailable)
        preferred_models = [
            'gemini-flash-lite-latest',
            'gemini-2.5-pro',
        ]
        last_err: Optional[Exception] = None
        model = None
        for name in preferred_models:
            try:
                model = genai.GenerativeModel(name)  # type: ignore[attr-defined]
                break
            except Exception as e:  # keep trying
                last_err = e
        if model is None and last_err is not None:
            return False, f"Failed to init Gemini model: {last_err}"  # pragma: no cover
    except Exception as e:  # pragma: no cover
        return False, f"Failed to configure AI: {e}"

    prompt = (
        f"Generate ONLY JSON for a starting room and NPC for this MUD world.\n\n"
        f"World Name: {world_name}\n"
        f"World Description: {world_desc}\n"
        f"World Conflict: {world_conflict}\n\n"
        "Return a single JSON object with keys 'room' and 'npc'. NO extra narration.\n"
        "Schema: { 'room': { 'id': 'snake_case_id', 'description': '...' }, 'npc': { 'name': 'Name', 'description': '...' } }\n"
        "The 'id' MUST be snake_case, <= 32 chars. Descriptions 1-3 sentences."
    )

    import json

    def _extract_json_block(raw: str) -> Optional[str]:
        """Attempt to isolate the first JSON object in raw text.

        Strategy:
        1. Strip code fences ``` and ```json markers.
        2. Scan for the first '{' then parse braces to find the matching '}'.
        3. Return that substring if it parses as JSON.
        """
        if not raw:
            return None
        # Remove common code fence wrappers
        fence_re = re.compile(r"```(?:json)?|```", re.IGNORECASE)
        cleaned = fence_re.sub("", raw).strip()
        # Fast path: direct parse succeeds
        if safe_call(json.loads, cleaned) is not None:
            return cleaned
        # Brace matching
        start_idx = cleaned.find('{')
        if start_idx == -1:
            return None
        depth = 0
        for i, ch in enumerate(cleaned[start_idx:], start=start_idx):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start_idx:i+1]
                    if safe_call(json.loads, candidate) is not None:
                        return candidate
                    return None
        return None

    if model is None:  # Defensive guard for type checkers / unexpected failures
        return False, "AI model unavailable after initialization attempts."

    try:  # pragma: no cover (network path)
        response = model.generate_content(prompt)  # type: ignore[assignment]
    except Exception as e:  # pragma: no cover
        return False, f"Model call failed: {e}"

    # Different SDK versions expose content differently; try several fallbacks.
    raw_text = safe_call_with_default(lambda: getattr(response, 'text', '') or '', '')
    if not raw_text:
        # Try candidates -> parts
        def _extract_parts():
            # response.candidates[0].content.parts is typically a list of objects with a 'text' attr
            parts = []
            for c in getattr(response, 'candidates', []) or []:  # type: ignore[attr-defined]
                content_obj = getattr(c, 'content', None)
                if not content_obj:
                    continue
                for p in getattr(content_obj, 'parts', []) or []:
                    t = getattr(p, 'text', None)
                    if t:
                        parts.append(t)
            return "\n".join(parts).strip()
        raw_text = safe_call_with_default(_extract_parts, '')

    if not raw_text:
        return False, "Empty AI response (possibly filtered)."

    json_block = _extract_json_block(raw_text)
    if not json_block:
        # Provide a shortened preview to aid debugging, but avoid logging giant text.
        preview = raw_text[:120].replace('\n', ' ')
        return False, f"Could not parse AI JSON (preview: {preview}...)"

    try:
        data = json.loads(json_block)
    except Exception as e:
        return False, f"Invalid JSON structure: {e}"

    room_data = data.get('room', {}) if isinstance(data, dict) else {}
    npc_data = data.get('npc', {}) if isinstance(data, dict) else {}

    room_id = room_data.get('id') or 'starting_room'
    # Sanitize room id to snake_case subset
    room_id = re.sub(r'[^a-z0-9_]+', '_', room_id.lower())[:32] or 'starting_room'
    room_desc = room_data.get('description', 'A basic starting room.')
    npc_name = npc_data.get('name', 'Guide')
    npc_desc = npc_data.get('description', 'A helpful guide.')

    try:
        # Create room
        world.rooms[room_id] = Room(id=room_id, description=room_desc)
        world.start_room_id = room_id
        # Create NPC
        world.rooms[room_id].npcs.add(npc_name)
        sheet = CharacterSheet(display_name=npc_name, description=npc_desc)
        world.npc_sheets[npc_name] = sheet
        world.get_or_create_npc_id(npc_name)
        save_world(world, state_path, debounced=True)
    except Exception as e:
        return False, f"Failed to apply generated data: {e}"

    return True, ""


def begin_setup(world_setup_sessions: Dict[str, dict], sid: str) -> List[dict]:
    """Initialize the setup state and return the first prompt to the admin."""
    world_setup_sessions[sid] = {"step": "world_name", "temp": {}}
    return [
        {'type': 'system', 'content': "Let's set up your world! What's the name of this world?"}
    ]


def handle_setup_input(world, state_path: str, sid: str, player_message: str, world_setup_sessions: Dict[str, dict]) -> Tuple[bool, List[dict]]:
    """Advance the setup wizard given the latest input.

    Contract:
    - Inputs: world, path to state file, sid, raw player_message, sessions dict
    - Output: (handled, emits)
      • handled=True means the message was consumed by the wizard (caller should return)
      • emits: list of payloads to send back to the admin
    """
    emits: List[dict] = []
    if sid not in world_setup_sessions:
        return False, emits

    sess = world_setup_sessions.get(sid, {"step": "world_name", "temp": {}})
    step = sess.get("step")
    temp = sess.get("temp", {})
    text_raw = player_message or ""
    text_lower = text_raw.strip().lower()

    # Universal controls
    if text_lower in ("cancel", "back"):
        world_setup_sessions.pop(sid, None)
        emits.append({'type': 'system', 'content': 'Setup cancelled. Use /setup to restart if needed.'})
        return True, emits

    # Step: world name
    if step == 'world_name':
        name = text_raw.strip()
        if len(name) < 2 or len(name) > 64:
            emits.append({'type': 'error', 'content': 'World name must be 2-64 characters.'})
            return True, emits
        world.world_name = name
        sess['step'] = 'world_description'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Describe the world in 1-3 sentences:'})
        return True, emits

    # Step: world description
    if step == 'world_description':
        desc = text_raw.strip()
        if len(desc) < 10:
            emits.append({'type': 'error', 'content': 'Please add a bit more detail (>= 10 chars).'})
            return True, emits
        world.world_description = desc
        sess['step'] = 'world_conflict'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Describe the main conflict of this world:'})
        return True, emits

    # Step: world conflict
    if step == 'world_conflict':
        conflict = text_raw.strip()
        if len(conflict) < 5:
            emits.append({'type': 'error', 'content': 'Please provide a short conflict summary (>= 5 chars).'})
            return True, emits
        world.world_conflict = conflict
        # Ask for creation mode next
        sess['step'] = 'creation_mode'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            "Do you want to manually create the starting room and NPC, or have the system generate some rooms and NPCs based on your world details?\n"
            "Type 'manual' or 'quick'."
        )})
        return True, emits

    # Step: creation mode
    if step == 'creation_mode':
        mode = text_lower.strip()
        if mode not in ('manual', 'quick'):
            emits.append({'type': 'error', 'content': 'Please answer with manual or quick.'})
            return True, emits
        temp['creation_mode'] = mode
        sess['temp'] = temp
        if mode == 'manual':
            # Proceed to safety level as before
            sess['step'] = 'safety_level'
            world_setup_sessions[sid] = sess
            emits.append({'type': 'system', 'content': (
                "What type of roleplay are you and your group comfortable with?\n"
                "Choose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], [b]Low (R)[/b], or [b]Safety Filters Off[/b].\n"
                "You can type: G, PG-13, R, or OFF."
            )})
            return True, emits
        elif mode == 'quick':
            # Generate quick rooms and NPCs
            ok, err = _generate_quick_world(world, state_path)
            if not ok:
                emits.append({'type': 'error', 'content': f'Quick generation failed: {err}. Falling back to manual.'})
                sess['step'] = 'safety_level'
                world_setup_sessions[sid] = sess
                emits.append({'type': 'system', 'content': (
                    "What type of roleplay are you and your group comfortable with?\n"
                    "Choose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], [b]Low (R)[/b], or [b]Safety Filters Off[/b].\n"
                    "You can type: G, PG-13, R, or OFF."
                )})
                return True, emits
            # Success, proceed to safety level
            sess['step'] = 'safety_level'
            world_setup_sessions[sid] = sess
            emits.append({'type': 'system', 'content': (
                "Quick world generation complete! What type of roleplay are you and your group comfortable with?\n"
                "Choose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], [b]Low (R)[/b], or [b]Safety Filters Off[/b].\n"
                "You can type: G, PG-13, R, or OFF."
            )})
            return True, emits

    # Step: safety level
    if step == 'safety_level':
        level_raw = text_raw.strip().upper()
        if level_raw in ("HIGH", "G", "ALL-AGES"):
            level = 'G'
        elif level_raw in ("MEDIUM", "PG13", "PG-13", "PG_13", "PG"):
            level = 'PG-13'
        elif level_raw in ("LOW", "R"):
            level = 'R'
        elif level_raw in ("OFF", "NONE", "NO FILTERS", "SAFETY FILTERS OFF"):
            level = 'OFF'
        else:
            emits.append({'type': 'error', 'content': 'Please answer with G, PG-13, R, or OFF.'})
            return True, emits
        try:
            world.safety_level = level
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'advanced_goap'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            "Do you want to enable the advanced GOAP AI for NPCs? This uses Gemini for richer planning when available. "
            "Type yes or no (default: no)."
        )})
        return True, emits

    # Step: advanced GOAP opt-in
    if step == 'advanced_goap':
        answer = text_lower.strip()
        yes_vals = {"yes", "y", "enable", "enabled", "true", "on"}
        no_vals = {"no", "n", "disable", "disabled", "false", "off", "skip", ""}
        if answer in yes_vals:
            world.advanced_goap_enabled = True
        elif answer in no_vals:
            world.advanced_goap_enabled = False
        else:
            emits.append({'type': 'error', 'content': 'Please answer with yes or no.'})
            return True, emits
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'room_id'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Create the starting room. Enter a room id (letters, numbers, underscores), e.g., town_square:'})
        return True, emits

    # Step: room id
    if step == 'room_id':
        rid = re.sub(r"[^A-Za-z0-9_]+", "_", text_raw.strip())
        if not rid:
            emits.append({'type': 'error', 'content': 'Room id cannot be empty.'})
            return True, emits
        if rid in world.rooms:
            emits.append({'type': 'error', 'content': f"Room id '{rid}' already exists. Choose another."})
            return True, emits
        temp['room_id'] = rid
        sess['temp'] = temp
        sess['step'] = 'room_desc'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Enter a description for the starting room:'})
        return True, emits

    # Step: room description (creates room and moves player there if present)
    if step == 'room_desc':
        rdesc = text_raw.strip()
        rid = temp.get('room_id')
        if not rid:
            emits.append({'type': 'error', 'content': 'Internal error: missing room id.'})
            return True, emits
        world.rooms[rid] = Room(id=rid, description=rdesc)
        world.start_room_id = rid
        # Move current player there if logged in
        if sid in world.players:
            try:
                world.move_player(sid, rid)
            except Exception:
                pass
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'npc_name'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Create an NPC for this room. Enter an NPC name (or type "skip"):'})
        return True, emits

    # Step: npc name (or skip)
    if step == 'npc_name':
        npc_name = text_raw.strip()
        if npc_name.lower() in ('skip', 'none'):
            world.setup_complete = True
            try:
                save_world(world, state_path, debounced=True)
            except Exception:
                pass
            world_setup_sessions.pop(sid, None)
            emits.append({'type': 'system', 'content': 'World setup complete! Others will now see your world description and conflict on login.'})
            # Show look
            emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
            return True, emits
        temp['npc_name'] = npc_name
        sess['temp'] = temp
        sess['step'] = 'npc_desc'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': f'Enter a short description for {npc_name}:'})
        return True, emits

    # Step: npc description (finalizes NPC and completes setup)
    if step == 'npc_desc':
        npc_desc = text_raw.strip()
        rid = temp.get('room_id')
        npc_name = temp.get('npc_name')
        room = world.rooms.get(rid)
        if room and npc_name:
            room.npcs.add(npc_name)
            sheet = world.npc_sheets.get(npc_name)
            if sheet is None:
                sheet = CharacterSheet(display_name=npc_name, description=npc_desc)
                world.npc_sheets[npc_name] = sheet
            else:
                sheet.description = npc_desc
            try:
                world.get_or_create_npc_id(npc_name)
            except Exception:
                pass
            try:
                world.save_to_file(state_path)
            except Exception:
                pass
        world.setup_complete = True
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        world_setup_sessions.pop(sid, None)
        emits.append({'type': 'system', 'content': f"NPC '{npc_name}' added. World setup complete!"})
        emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
        return True, emits

    # Unknown step — be gentle and reset
    world_setup_sessions.pop(sid, None)
    emits.append({'type': 'error', 'content': 'Setup session lost. Use /setup to start again.'})
    return True, emits
