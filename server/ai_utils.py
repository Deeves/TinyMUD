"""ai_utils.py — Shared AI helpers (safety settings, small glue).

This module centralizes logic that was previously duplicated across the server
and NPC services, in particular the mapping from a world safety level to the
Google Gemini SDK's safety_settings structure.

Keep it dependency-light and safe to import even when the Google SDK isn't
installed; in that case the exported helpers simply return None.
"""

from __future__ import annotations

from typing import Optional, Any

# Optional Gemini SDK enums (we detect presence at runtime)
try:
    from google.generativeai.types import HarmCategory, HarmBlockThreshold  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    HarmCategory = None  # type: ignore
    HarmBlockThreshold = None  # type: ignore


def safety_settings_for_level(level: Optional[str]) -> Optional[list[dict[str, Any]]]:
    """Return a safety_settings list for Gemini based on the given level.

    Levels: 'G' | 'PG-13' | 'R' | 'OFF' (case-insensitive). If the SDK enums
    are not available, returns None so callers can omit the parameter.
    """
    if HarmCategory is None or HarmBlockThreshold is None:
        return None
    lvl = (level or 'G').upper()

    def mk(threshold):
        cats: list[dict[str, Any]] = []
        for nm in [
            'HARM_CATEGORY_HARASSMENT',
            'HARM_CATEGORY_HATE_SPEECH',
            'HARM_CATEGORY_SEXUAL',
            'HARM_CATEGORY_SEXUAL_AND_MINORS',
            'HARM_CATEGORY_DANGEROUS_CONTENT',
        ]:
            c = getattr(HarmCategory, nm, None)
            if c is not None:
                cats.append({'category': c, 'threshold': threshold})
        return cats or None

    if lvl == 'OFF':
        return mk(HarmBlockThreshold.BLOCK_NONE)
    if lvl == 'R':
        return mk(getattr(HarmBlockThreshold, 'BLOCK_ONLY_HIGH', HarmBlockThreshold.BLOCK_NONE))
    if lvl in ('PG-13', 'PG13', 'PG'):
        return mk(getattr(HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', HarmBlockThreshold.BLOCK_NONE))
    return mk(getattr(HarmBlockThreshold, 'BLOCK_LOW_AND_ABOVE', HarmBlockThreshold.BLOCK_NONE))
