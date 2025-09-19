from __future__ import annotations

import re
from typing import List, Tuple


def split_targets(targets_part: str) -> List[str]:
    """Split a targets string into individual NPC names.
    Splits on ' and ' (case-insensitive) and commas, preserving multi-word names.
    Removes surrounding quotes and extra spaces.
    """
    if not targets_part:
        return []
    # Normalize commas to ' and ' and split on 'and'
    normalized = re.sub(r",", " and ", targets_part)
    parts = re.split(r"\band\b", normalized, flags=re.IGNORECASE)
    targets: list[str] = []
    for p in parts:
        name = p.strip().strip('"').strip("'")
        if name:
            targets.append(name)
    # Dedupe preserve order (case-insensitive key)
    seen: set[str] = set()
    result: list[str] = []
    for t in targets:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            result.append(t)
    return result


def parse_say(text: str) -> Tuple[bool, List[str] | None, str | None]:
    """Parse variations of the 'say' command.

    Supported forms:
    - say <message>
    - say to <npc>[ and <npc>...]: <message>
    - say to <npc>[ and <npc>...] "<message>"
    - say to <npc>[, <npc>..., and <npc>] -- <message>

    Returns: (is_say, targets or None, message or None)
    - is_say: whether input begins with 'say'
    - targets: list of target names if 'say to', else None (no specific target)
    - message: extracted message content if present
    """
    if not isinstance(text, str):
        return False, None, None
    stripped = text.strip()
    if not stripped.lower().startswith("say"):
        return False, None, None

    after = stripped[3:].lstrip()  # remove 'say'
    if not after:
        return True, None, None

    if after.lower().startswith("to "):
        spec = after[3:]  # after 'to '
        # Try quoted message first
        m = re.search(r"[\"'](.*)[\"']", spec)
        if m:
            msg = m.group(1).strip()
            targets_part = spec[:m.start()].strip()
        else:
            if ":" in spec:
                targets_part, msg = spec.split(":", 1)
                msg = msg.strip()
                targets_part = targets_part.strip()
            elif "--" in spec:
                targets_part, msg = spec.split("--", 1)
                msg = msg.strip()
                targets_part = targets_part.strip()
            else:
                return True, split_targets(spec.strip()), None
        targets = split_targets(targets_part)
        return True, targets, msg if msg else None

    # say <message>
    return True, None, after.strip() if after.strip() else None
