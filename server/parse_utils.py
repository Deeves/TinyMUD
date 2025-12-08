"""parse_utils.py — Small shared input parsing helpers.

Use these in wizards/services to keep input handling consistent and tidy.
"""

from __future__ import annotations

from typing import Optional, List


def is_blank_or_skip(s: Optional[str]) -> bool:
    """Return True if s is empty/whitespace or an explicit skip token.

    Accepted skip tokens (case-insensitive): '', 'skip', 'none', '-'
    """
    t = (s or "").strip().lower()
    return t in ("", "skip", "none", "-")


def parse_int_or_none(s: Optional[str], *, err_msg: str | None = None) -> tuple[bool, Optional[int], Optional[str]]:
    """Parse an int or return (False, None, err) when invalid and not blank.

    Returns (ok, value, err). Blank/skip yields (True, None, None).
    """
    if is_blank_or_skip(s):
        return True, None, None
    try:
        return True, int(str(s).strip()), None
    except Exception:
        return False, None, (err_msg or "Please enter an integer or press Enter to skip.")


def parse_comma_list(s: Optional[str]) -> List[str]:
    """Return a list of comma-separated items with whitespace trimmed and empties removed."""
    if not s:
        return []
    parts = [p.strip() for p in str(s).split(',')]
    return [p for p in parts if p]
