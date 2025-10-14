from __future__ import annotations

"""Utilities for parsing identifiers and fuzzy-resolving game entities.

Goals:
- Allow single-quoted ids with spaces across commands.
- Provide consistent fuzzy matching (ci-exact, unique prefix, unique substring).
- Offer suggestions when invalid, listing ids with the same first letter (case-insensitive).
"""

from typing import Iterable, List, Optional, Tuple, Dict


def strip_quotes(s: str) -> str:
    """Remove surrounding single or double quotes if the whole string is quoted."""
    if not isinstance(s, str):
        return s
    t = s.strip()
    if len(t) >= 2 and ((t[0] == t[-1] == "'") or (t[0] == t[-1] == '"')):
        return t[1:-1].strip()
    return t


def parse_pipe_parts(s: str, expected: Optional[int] = None) -> List[str]:
    """Split on '|' and trim whitespace and surrounding quotes for each part.

    If expected is provided and there are fewer parts, pad with empty strings;
    if more, the extras are kept joined on the last slot.
    """
    raw = [p.strip() for p in s.split('|')]
    parts = [strip_quotes(p) for p in raw]
    if expected is None:
        return parts
    if len(parts) < expected:
        parts = parts + [""] * (expected - len(parts))
    if len(parts) > expected:
        head = parts[: expected - 1]
        tail = " | ".join(parts[expected - 1 :])
        parts = head + [tail]
    return parts


def _suggest_by_first_letter(typed: str, candidates: Iterable[str]) -> List[str]:
    """Suggest candidates with deterministic sorting for stable results."""
    first = (typed or "").strip()[:1].lower()
    if not first:
        return []
    try:
        matches = [c for c in candidates if isinstance(c, str) and c[:1].lower() == first]
        return _deterministic_sort(matches)
    except Exception:
        return []


def _deterministic_sort(items: List[str]) -> List[str]:
    """Sort items deterministically for stable fuzzy resolution results.
    
    Uses a two-tier sorting approach:
    1. Primary: case-insensitive lexicographic order
    2. Secondary: original case for tie-breaking
    
    This ensures consistent results regardless of input order, locale settings,
    or case variations while maintaining intuitive alphabetical ordering.
    
    Examples:
        ["Apple", "apple", "APPLE"] -> ["APPLE", "Apple", "apple"]
        ["banana", "Bread", "butter"] -> ["banana", "Bread", "butter"]
    """
    return sorted(items, key=lambda x: (x.lower(), x))

def fuzzy_resolve(typed: str, candidates: Iterable[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Generic fuzzy resolver with deterministic ordering.

    Returns (ok, err, resolved_value) where:
    - ok=True with resolved_value when a single candidate is selected
    - ok=False with err message otherwise
    Strategy: exact -> ci-exact -> unique prefix (ci) -> unique substring (ci).
    On ambiguity: list up to 10 candidates in deterministic order.
    On not found: suggest ids with same first letter when available.
    
    Deterministic sorting ensures stable results across different systems, locales,
    and input orderings. Sorts case-insensitively first, then by original case.
    """
    t = (typed or '').strip()
    items = list(candidates)
    if not t:
        return False, 'Identifier required.', None
    # exact
    if t in items:
        return True, None, t
    # ci map
    lower_map: Dict[str, str] = {c.lower(): c for c in items}
    if t.lower() in lower_map:
        return True, None, lower_map[t.lower()]
    # prefix
    prefs = [c for c in items if c.lower().startswith(t.lower())]
    if len(prefs) == 1:
        return True, None, prefs[0]
    if len(prefs) > 1:
        # Deterministic sorting: case-insensitive first, then by original case
        deterministic_prefs = _deterministic_sort(prefs)
        return False, 'Ambiguous id. Did you mean: ' + ", ".join(deterministic_prefs[:10]) + ' ?', None
    # substring
    subs = [c for c in items if t.lower() in c.lower()]
    if len(subs) == 1:
        return True, None, subs[0]
    if len(subs) > 1:
        # Deterministic sorting: case-insensitive first, then by original case  
        deterministic_subs = _deterministic_sort(subs)
        return False, 'Ambiguous id. Did you mean: ' + ", ".join(deterministic_subs[:10]) + ' ?', None
    # not found suggestions
    suggestions = _suggest_by_first_letter(t, items)
    if suggestions:
        return False, f"'{typed}' not found. Did you mean: " + ", ".join(suggestions[:10]) + '?', None
    return False, f"'{typed}' not found.", None


# ----- Entity-specific resolvers -----

def resolve_room_id(world, typed: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Resolve a user-typed room name to an internal room id.

    The server exposes "room names" to users for readability and accepts fuzzy
    matches (exact, ci-exact, unique prefix, unique substring). Internally, the
    world is keyed by stable room ids. This function bridges the two.
    Returns (ok, err, room_id) where room_id is the internal identifier.
    """
    return fuzzy_resolve(strip_quotes(typed), world.rooms.keys())


def resolve_player_sid_global(world, typed: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Resolve a player SID by display name across all connected players.

    Returns (ok, err, sid, resolved_display_name).
    """
    name = strip_quotes(typed)
    display_to_sid: Dict[str, str] = {}
    candidates: List[str] = []
    for psid, p in list(world.players.items()):
        try:
            disp = p.sheet.display_name
        except Exception:
            continue
        if not isinstance(disp, str):
            continue
        candidates.append(disp)
        display_to_sid[disp] = psid
    ok, err, resolved = fuzzy_resolve(name, candidates)
    if not ok or not resolved:
        return False, err, None, None
    return True, None, display_to_sid.get(resolved), resolved


def resolve_player_sid_in_room(world, room, typed: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    name = strip_quotes(typed)
    entries: List[Tuple[str, str]] = []  # (sid, display_name)
    if room is None:
        return False, 'No room.', None, None
    for psid in list(getattr(room, 'players', []) or []):
        try:
            p = world.players.get(psid)
            if p and p.sheet and p.sheet.display_name:
                entries.append((psid, p.sheet.display_name))
        except Exception:
            continue
    candidates = [n for _sid, n in entries]
    ok, err, resolved = fuzzy_resolve(name, candidates)
    if not ok or not resolved:
        return False, err, None, None
    sid = next((sid for sid, n in entries if n == resolved), None)
    return True, None, sid, resolved


def resolve_npcs_in_room(room, requested: List[str]) -> List[str]:
    """Resolve one or more requested NPC names against those present in the room using fuzzy logic.
    Returns resolved names in request order, unique.
    """
    if room is None or not getattr(room, 'npcs', None):
        return []
    in_room = list(room.npcs)
    resolved: List[str] = []
    seen: set[str] = set()
    for req in requested:
        ok, _err, val = fuzzy_resolve(strip_quotes(req), in_room)
        if ok and val and val not in seen:
            resolved.append(val)
            seen.add(val)
    return resolved


def resolve_door_name(room, typed: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Resolve a door name within a room using fuzzy logic.
    Returns (ok, err, resolved_door_name) where resolved door name matches the actual key in room.doors.
    """
    if room is None:
        return False, 'You are nowhere.', None
    door_names = list(getattr(room, 'doors', {}).keys())
    return fuzzy_resolve(strip_quotes(typed), door_names)
