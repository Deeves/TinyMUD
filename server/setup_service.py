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

Service Contract:
    All public functions return 4-tuple: (handled, error, emits, broadcasts)
    - handled: bool - whether the command was recognized
    - error: str | None - error message if any
    - emits: List[dict] - messages to send to the acting player
    - broadcasts: List[Tuple[str, dict]] - (room_id, message) pairs for room broadcasts
    
    Helper functions may use different contracts (documented per function).
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import re
import os
import threading
import time

from world import Room, CharacterSheet
from persistence_utils import save_world
from concurrency_utils import atomic
from safe_utils import safe_call, safe_call_with_default

# Optional AI import
try:
    import google.generativeai as genai  # type: ignore
    AI_AVAILABLE = True
except ImportError:
    genai = None
    AI_AVAILABLE = False

# Deterministic fallback content for testing and AI failures
# This provides predictable seed content when AI is unavailable or fails
_FALLBACK_SEED_CONTENT = {
    'generic': {
        'room': {
            'id': 'starting_chamber',
            'description': 'A simple chamber with stone walls and a wooden door.'
        },
        'npc': {
            'name': 'Guide',
            'description': 'A friendly guide who helps newcomers.'
        }
    }
}

# Configuration constants for AI robustness
_AI_TIMEOUT_SECONDS = 30.0  # Max time to wait for AI response
_MAX_RESPONSE_LENGTH = 10000  # Max chars to process from AI response


def _call_ai_with_timeout(model, prompt: str, timeout_seconds: float = _AI_TIMEOUT_SECONDS):
    """
    Call AI model with timeout protection and giant text guards.
    
    This prevents the common failure modes of:
    - Hanging indefinitely on slow/unresponsive API calls
    - Processing enormous AI responses that consume excessive memory/CPU
    
    Returns:
        (success: bool, result_or_error: str|object, truncated: bool)
        - success: True if AI call completed successfully within timeout
        - result_or_error: AI response object on success, error string on failure
        - truncated: True if response was truncated due to size limits
    """
    if not model:
        return False, "No AI model available", False
        
    # Thread-safe result containers 
    thread_result = {'response': None, 'error': None, 'truncated': False}
    
    def ai_call():
        """Thread target function for the AI call."""
        try:
            response = model.generate_content(prompt)
            # Extract text with size protection
            raw_text = safe_call_with_default(lambda: getattr(response, 'text', '') or '', '')
            
            # If primary text extraction fails, try the candidates fallback
            if not raw_text:
                def _extract_parts():
                    parts = []
                    for c in getattr(response, 'candidates', []) or []:
                        content_obj = getattr(c, 'content', None)
                        if not content_obj:
                            continue
                        for p in getattr(content_obj, 'parts', []) or []:
                            t = getattr(p, 'text', None)
                            if t:
                                parts.append(t)
                    return "\n".join(parts).strip()
                raw_text = safe_call_with_default(_extract_parts, '')
            
            # Protect against hallucinated giant text
            if len(raw_text) > _MAX_RESPONSE_LENGTH:
                raw_text = raw_text[:_MAX_RESPONSE_LENGTH]
                thread_result['truncated'] = True
            
            # Create a response-like object with the processed text
            class ProcessedResponse:
                def __init__(self, text: str):
                    self.text = text
            
            thread_result['response'] = ProcessedResponse(raw_text)
        except Exception as e:
            thread_result['error'] = str(e)
    
    # Start the AI call in a separate thread
    thread = threading.Thread(target=ai_call, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    # Check if thread completed within timeout
    if thread.is_alive():
        # Thread is still running, meaning it timed out
        return False, f"AI call timed out after {timeout_seconds} seconds", False
    
    # Thread completed, check results
    if thread_result['error']:
        return False, f"AI call failed: {thread_result['error']}", False
    
    if thread_result['response'] is None:
        return False, "AI call completed but returned no result", False
    
    return True, thread_result['response'], thread_result['truncated']


def _get_deterministic_fallback(world) -> Tuple[str, str, str, str]:
    """
    Generate deterministic fallback content based on world properties.
    
    This provides predictable, testable content when AI is unavailable or fails.
    The content is derived from world properties to maintain some customization
    while ensuring deterministic behavior for tests.
    
    Returns: (room_id, room_desc, npc_name, npc_desc)
    """
    # Use world name to create a basic room ID, with fallback
    world_name = getattr(world, 'world_name', 'Unknown World')
    world_desc = getattr(world, 'world_description', 'A mysterious place.')
    
    # Create room ID from world name (sanitized)
    room_id = re.sub(r'[^a-z0-9_]+', '_', world_name.lower())[:20] or 'start_room'
    if not room_id or room_id == '_':
        room_id = 'starting_chamber'
    
    # Create room description incorporating world description
    room_desc = f"The starting point of {world_name.strip()}. {world_desc.strip()}"
    if len(room_desc) > 200:
        room_desc = room_desc[:197] + "..."
    
    # Simple deterministic NPC based on world name length
    name_length = len(world_name.strip())
    if name_length % 3 == 0:
        npc_name, npc_desc = "Guardian", "A steadfast guardian watching over this place."
    elif name_length % 3 == 1:
        npc_name, npc_desc = "Guide", "A helpful guide who knows the local area well."
    else:
        npc_name, npc_desc = "Keeper", "An ancient keeper of knowledge and tradition."
    
    return room_id, room_desc, npc_name, npc_desc


def _generate_quick_world(world, state_path: str) -> Tuple[bool, str]:
    """Generate a starting room and NPC using AI based on world details.

    Robustness improvements:
    - Timeout protection prevents hanging on slow/unresponsive API calls
    - Size limits guard against hallucinated giant text consuming memory/CPU
    - Deterministic fallback provides predictable seed content for tests
    - Heuristic JSON parsing handles various AI response formats gracefully
    - Comprehensive error handling with actionable feedback
    - Always returns (ok, error_msg) tuple - never raises exceptions
    """
    world_name = getattr(world, 'world_name', 'Unnamed World')
    world_desc = getattr(world, 'world_description', 'A mysterious place.')
    world_conflict = getattr(world, 'world_conflict', 'Unknown conflicts.')

    # Try AI generation first if available
    ai_success, ai_error = _try_ai_generation(world, world_name, world_desc, world_conflict)
    if ai_success:
        # Apply AI-generated content to world
        return _apply_generated_content(world, state_path, ai_success, "AI")
    
    # AI failed - use deterministic fallback  
    room_id, room_desc, npc_name, npc_desc = _get_deterministic_fallback(world)
    fallback_data = {
        'room': {'id': room_id, 'description': room_desc},
        'npc': {'name': npc_name, 'description': npc_desc}
    }
    
    success, err = _apply_generated_content(world, state_path, fallback_data, "fallback")
    if success:
        return True, f"Used fallback content (AI unavailable: {ai_error})"
    else:
        return False, f"Both AI and fallback failed. AI error: {ai_error}. Fallback error: {err}"


def _try_ai_generation(world, world_name: str, world_desc: str, world_conflict: str):
    """
    Attempt AI-based world generation with full robustness protections.
    
    Returns: (success_data_or_false, error_message_or_none)
    - If successful: (dict_with_room_and_npc_data, None)  
    - If failed: (False, "descriptive error message")
    """
    import json
    
    if not AI_AVAILABLE or genai is None:
        return False, "AI library not available"

    # Configure API if not already done
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return False, "No Gemini API key found"
        
    try:
        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        
        # Try to initialize a model using project standard cascade
        preferred_models = ['gemini-flash-lite-latest', 'gemini-2.5-pro']
        model = None
        last_err = None
        
        for model_name in preferred_models:
            try:
                model = genai.GenerativeModel(model_name)  # type: ignore[attr-defined]
                break
            except Exception as e:
                last_err = e
                
        if model is None:
            return False, f"Failed to initialize any AI model: {last_err}"
            
    except Exception as e:
        return False, f"Failed to configure AI: {e}"

    # Construct the generation prompt
    prompt = "".join([
        "Generate ONLY JSON for a starting room and NPC for this MUD world.\n\n",
        f"World Name: {world_name}\n",
        f"World Description: {world_desc}\n",
        f"World Conflict: {world_conflict}\n\n",
        "Return a single JSON object with keys 'room' and 'npc'. NO extra narration.\n",
        "Schema: { 'room': { 'id': 'snake_case_id', 'description': '...' }, ",
        "'npc': { 'name': 'Name', 'description': '...' } }\n",
        "The 'id' MUST be snake_case, <= 32 chars. Descriptions 1-3 sentences.",
    ])

    # Call AI with timeout and size protection
    success, result, truncated = _call_ai_with_timeout(model, prompt)
    
    if not success:
        return False, result  # result contains error message
        
    if truncated:
        # Log but continue - truncated responses might still be parseable
        pass
        
    # Extract text from response
    raw_text = getattr(result, 'text', '') if result else ''
    if not raw_text:
        return False, "Empty AI response (possibly filtered)"

    # Parse JSON using robust extraction
    json_block = _extract_json_block(raw_text)
    if not json_block:
        # Provide shortened preview for debugging
        preview = raw_text[:120].replace('\n', ' ')
        return False, f"Could not parse AI JSON (preview: {preview}...)"

    try:
        data = json.loads(json_block)
        if not isinstance(data, dict):
            return False, "AI response is not a JSON object"
            
        # Validate required structure
        room_data = data.get('room', {})
        npc_data = data.get('npc', {})
        
        if not isinstance(room_data, dict) or not isinstance(npc_data, dict):
            return False, "AI response missing required 'room' or 'npc' objects"
            
        return data, None
        
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON from AI: {e}"


def _extract_json_block(raw: str) -> Optional[str]:
    """
    Robustly extract the first JSON object from AI response text.
    
    Handles common AI response patterns:
    - Text wrapped in ```json code fences
    - JSON preceded by explanatory text  
    - JSON with trailing commentary
    
    Strategy:
    1. Remove code fence markers
    2. Find first '{' and match braces to closing '}'
    3. Validate extracted text as valid JSON
    
    Returns the first valid JSON block found, or None.
    """
    if not raw:
        return None
        
    # Remove common code fence wrappers
    fence_re = re.compile(r"```(?:json)?|```", re.IGNORECASE)
    cleaned = fence_re.sub("", raw).strip()
    
    # Quick path: try parsing the whole thing first
    import json
    if safe_call(json.loads, cleaned) is not None:
        return cleaned
    
    # Brace matching to extract first JSON object
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


def _apply_generated_content(world, state_path: str, data, source: str) -> Tuple[bool, str]:
    """
    Apply generated room and NPC data to the world safely.
    
    Args:
        world: World instance to modify
        state_path: Path for saving world state  
        data: Dict containing 'room' and 'npc' data, or False if generation failed
        source: Description of data source ("AI" or "fallback") for error messages
        
    Returns: (success, error_message)
    """
    if not data:
        return False, f"{source} generation returned no data"
        
    try:
        room_data = data.get('room', {})
        npc_data = data.get('npc', {})
        
        # Extract and sanitize room data
        room_id = room_data.get('id') or 'starting_room'
        room_id = re.sub(r'[^a-z0-9_]+', '_', room_id.lower())[:32] or 'starting_room'
        room_desc = room_data.get('description', 'A basic starting room.')
        
        # Extract NPC data
        npc_name = npc_data.get('name', 'Guide')
        npc_desc = npc_data.get('description', 'A helpful guide.')
        
        # Apply changes atomically
        with atomic('world'):
            world.rooms[room_id] = Room(id=room_id, description=room_desc)
            world.start_room_id = room_id
            world.rooms[room_id].npcs.add(npc_name)
            sheet = CharacterSheet(display_name=npc_name, description=npc_desc)
            world.npc_sheets[npc_name] = sheet
            world.get_or_create_npc_id(npc_name)
            
        # Save world state
        save_world(world, state_path, debounced=True)
        return True, ""
        
    except Exception as e:
        return False, f"Failed to apply {source} data: {e}"


def begin_setup(world_setup_sessions: Dict[str, dict], sid: str) -> List[dict]:
    """Initialize the setup state and return the first prompt to the admin."""
    with atomic('setup_sessions'):
        world_setup_sessions[sid] = {"step": "world_name", "temp": {}}
    return [
        {'type': 'system', 'content': "Let's set up your world! What's the name of this world?"}
    ]


def handle_setup_input(
    world,
    state_path: str,
    sid: str,
    player_message: str,
    world_setup_sessions: Dict[str, dict],
) -> Tuple[bool, str | None, List[dict], List[Tuple[str, dict]]]:
    """Advance the setup wizard given the latest input.

    Returns: (handled, error, emits, broadcasts)
    - handled=True means the message was consumed by the wizard (caller should return)
    - error=None normally, error string if something went wrong
    - emits: list of payloads to send back to the admin
    - broadcasts: room broadcasts (typically empty for setup wizard)
    """
    emits: List[dict] = []
    broadcasts: List[Tuple[str, dict]] = []
    if sid not in world_setup_sessions:
        return False, None, emits, broadcasts

    sess = world_setup_sessions.get(sid, {"step": "world_name", "temp": {}})
    step = sess.get("step")
    temp = sess.get("temp", {})
    text_raw = player_message or ""
    text_lower = text_raw.strip().lower()

    # Universal controls
    if text_lower in ("cancel", "back"):
        world_setup_sessions.pop(sid, None)
        emits.append({
            'type': 'system',
            'content': 'Setup cancelled. Use /setup to restart if needed.'
        })
        return True, None, emits, broadcasts

    # Step: world name
    if step == 'world_name':
        name = text_raw.strip()
        if len(name) < 2 or len(name) > 64:
            emits.append({'type': 'error', 'content': 'World name must be 2-64 characters.'})
            return True, None, emits, broadcasts
        with atomic('world'):
            world.world_name = name
        sess['step'] = 'world_description'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Describe the world in 1-3 sentences:'})
        return True, None, emits, broadcasts

    # Step: world description
    if step == 'world_description':
        desc = text_raw.strip()
        if len(desc) < 10:
            emits.append({
                'type': 'error',
                'content': 'Please add a bit more detail (>= 10 chars).'
            })
            return True, None, emits, broadcasts
        with atomic('world'):
            world.world_description = desc
        sess['step'] = 'world_conflict'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Describe the main conflict of this world:'})
        return True, None, emits, broadcasts

    # Step: world conflict
    if step == 'world_conflict':
        conflict = text_raw.strip()
        if len(conflict) < 5:
            emits.append({
                'type': 'error',
                'content': 'Please provide a short conflict summary (>= 5 chars).'
            })
            return True, None, emits, broadcasts
        with atomic('world'):
            world.world_conflict = conflict
        # Ask for creation mode next
        sess['step'] = 'creation_mode'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            "Do you want to manually create the starting room and NPC, or have the "
            "system generate some rooms and NPCs based on your world details?\n"
            "Type 'manual' or 'quick'."
        )})
        return True, None, emits, broadcasts

    # Step: creation mode
    if step == 'creation_mode':
        mode = text_lower.strip()
        if mode not in ('manual', 'quick'):
            emits.append({'type': 'error', 'content': 'Please answer with manual or quick.'})
            return True, None, emits, broadcasts
        temp['creation_mode'] = mode
        sess['temp'] = temp
        if mode == 'manual':
            # Proceed to safety level as before
            sess['step'] = 'safety_level'
            world_setup_sessions[sid] = sess
            emits.append({'type': 'system', 'content': (
                "What type of roleplay are you and your group comfortable with?\n"
                "Choose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], [b]Low (R)[/b], "
                "or [b]Safety Filters Off[/b].\nYou can type: G, PG-13, R, or OFF."
            )})
            return True, None, emits, broadcasts
        elif mode == 'quick':
            # Generate quick rooms and NPCs
            ok, err = _generate_quick_world(world, state_path)
            if not ok:
                emits.append({'type': 'error', 'content': (
                    f'Quick generation failed: {err}. Falling back to manual.'
                )})
                sess['step'] = 'safety_level'
                world_setup_sessions[sid] = sess
                emits.append({'type': 'system', 'content': (
                    "What type of roleplay are you and your group comfortable with?\n"
                    "Choose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], [b]Low (R)[/b], "
                    "or [b]Safety Filters Off[/b].\nYou can type: G, PG-13, R, or OFF."
                )})
                return True, None, emits, broadcasts
            # Success, proceed to safety level
            sess['step'] = 'safety_level'
            world_setup_sessions[sid] = sess
            emits.append({'type': 'system', 'content': (
                "Quick world generation complete! What type of roleplay are you and your "
                "group comfortable with?\nChoose one: [b]High (G)[/b], [b]Medium (PG-13)[/b], "
                "[b]Low (R)[/b], or [b]Safety Filters Off[/b].\nYou can type: G, PG-13, R, or OFF."
            )})
            return True, None, emits, broadcasts

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
            return True, None, emits, broadcasts
        try:
            with atomic('world'):
                world.safety_level = level
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'advanced_goap'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            "Do you want to enable the advanced GOAP AI for NPCs? This uses Gemini for richer "
            "planning when available. Type yes or no (default: no)."
        )})
        return True, None, emits, broadcasts

    # Step: advanced GOAP opt-in
    if step == 'advanced_goap':
        answer = text_lower.strip()
        yes_vals = {"yes", "y", "enable", "enabled", "true", "on"}
        no_vals = {"no", "n", "disable", "disabled", "false", "off", "skip", ""}
        if answer in yes_vals:
            with atomic('world'):
                # Use safe GOAP mode switching to prevent state corruption
                try:
                    from goap_state_manager import reset_goap_mode_safely
                    success, cleanup_actions = reset_goap_mode_safely(world, True)
                    if success and cleanup_actions:
                        print(f"GOAP mode enabled with cleanup: {len(cleanup_actions)} actions")
                except ImportError:
                    # Fallback if goap_state_manager is not available
                    world.advanced_goap_enabled = True
                except Exception as e:
                    print(f"GOAP mode switch failed, using fallback: {e}")
                    world.advanced_goap_enabled = True
        elif answer in no_vals:
            with atomic('world'):
                # Use safe GOAP mode switching to prevent state corruption
                try:
                    from goap_state_manager import reset_goap_mode_safely
                    success, cleanup_actions = reset_goap_mode_safely(world, False)
                    if success and cleanup_actions:
                        print(f"GOAP mode disabled with cleanup: {len(cleanup_actions)} actions")
                except ImportError:
                    # Fallback if goap_state_manager is not available
                    world.advanced_goap_enabled = False
                except Exception as e:
                    print(f"GOAP mode switch failed, using fallback: {e}")
                    world.advanced_goap_enabled = False
        else:
            emits.append({'type': 'error', 'content': 'Please answer with yes or no.'})
            return True, None, emits, broadcasts
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'room_id'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            'Create the starting room. Enter a room id (letters, numbers, underscores), '
            'e.g., town_square:'
        )})
        return True, None, emits, broadcasts

    # Step: room id
    if step == 'room_id':
        rid = re.sub(r"[^A-Za-z0-9_]+", "_", text_raw.strip())
        if not rid:
            emits.append({'type': 'error', 'content': 'Room id cannot be empty.'})
            return True, None, emits, broadcasts
        if rid in world.rooms:
            emits.append({'type': 'error', 'content': (
                f"Room id '{rid}' already exists. Choose another."
            )})
            return True, None, emits, broadcasts
        temp['room_id'] = rid
        sess['temp'] = temp
        sess['step'] = 'room_desc'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': 'Enter a description for the starting room:'})
        return True, None, emits, broadcasts

    # Step: room description (creates room and moves player there if present)
    if step == 'room_desc':
        rdesc = text_raw.strip()
        rid = temp.get('room_id')
        if not rid:
            emits.append({'type': 'error', 'content': 'Internal error: missing room id.'})
            return True, None, emits, broadcasts
        with atomic('world'):
            world.rooms[rid] = Room(id=rid, description=rdesc)
            world.start_room_id = rid
        # Move current player there if logged in
        if sid in world.players:
            try:
                with atomic('world'):
                    world.move_player(sid, rid)
            except Exception:
                pass
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        sess['step'] = 'npc_name'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': (
            'Create an NPC for this room. Enter an NPC name (or type "skip"):'
        )})
        return True, None, emits, broadcasts

    # Step: npc name (or skip)
    if step == 'npc_name':
        npc_name = text_raw.strip()
        if npc_name.lower() in ('skip', 'none'):
            with atomic('world'):
                world.setup_complete = True
            try:
                save_world(world, state_path, debounced=True)
            except Exception:
                pass
            world_setup_sessions.pop(sid, None)
            emits.append({'type': 'system', 'content': (
                'World setup complete! Others will now see your world description and '
                'conflict on login.'
            )})
            # Show look
            emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
            return True, None, emits, broadcasts
        temp['npc_name'] = npc_name
        sess['temp'] = temp
        sess['step'] = 'npc_desc'
        world_setup_sessions[sid] = sess
        emits.append({'type': 'system', 'content': f'Enter a short description for {npc_name}:'})
        return True, None, emits, broadcasts

    # Step: npc description (finalizes NPC and completes setup)
    if step == 'npc_desc':
        npc_desc = text_raw.strip()
        rid = temp.get('room_id')
        npc_name = temp.get('npc_name')
        room = world.rooms.get(rid)
        if room and npc_name:
            with atomic('world'):
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
            save_world(world, state_path, debounced=False)
        except Exception:
            pass
        with atomic('world'):
            world.setup_complete = True
        try:
            save_world(world, state_path, debounced=True)
        except Exception:
            pass
        world_setup_sessions.pop(sid, None)
        emits.append({'type': 'system', 'content': (
            f"NPC '{npc_name}' added. World setup complete!"
        )})
        emits.append({'type': 'system', 'content': world.describe_room_for(sid)})
        return True, None, emits, broadcasts

    # Unknown step — be gentle and reset
    world_setup_sessions.pop(sid, None)
    emits.append({'type': 'error', 'content': 'Setup session lost. Use /setup to start again.'})
    return True, None, emits, broadcasts
