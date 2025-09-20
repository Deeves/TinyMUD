from __future__ import annotations

import re
from typing import List, Tuple, Iterable


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


def parse_tell(text: str) -> Tuple[bool, str | None, str | None]:
    """Parse variations of the 'tell' command.

    Supported forms:
    - tell <name> <message>                  (single-word name)
    - tell <name>: <message>
    - tell <name> -- <message>
    - tell "Multi Word Name" <message>
    - tell 'Multi Word Name': <message>

    Returns: (is_tell, target or None, message or None)
    - is_tell: whether input begins with 'tell'
    - target: resolved target string when present
    - message: extracted message content if present
    """
    if not isinstance(text, str):
        return False, None, None
    stripped = text.strip()
    if not stripped.lower().startswith("tell"):
        return False, None, None

    after = stripped[4:].lstrip()  # remove 'tell'
    if not after:
        return True, None, None

    # Quoted name first
    if after[:1] in ('"', "'"):
        q = after[0]
        try:
            end_idx = after.find(q, 1)
        except Exception:
            end_idx = -1
        if end_idx != -1:
            target = after[1:end_idx].strip()
            rest = after[end_idx + 1 :].lstrip()
            # Optional separators
            if rest.startswith(":" ):
                rest = rest[1:].lstrip()
            elif rest.startswith("--"):
                rest = rest[2:].lstrip()
            msg = rest.strip() if rest else None
            return True, target if target else None, msg
        # If quote not closed, fall through to generic parsing

    # Unquoted: support <name>: <message> or <name> -- <message>
    # Prefer separators to allow multi-word names without quotes
    if ":" in after:
        left, right = after.split(":", 1)
        target = left.strip().strip('"').strip("'")
        msg = right.strip()
        return True, (target or None), (msg or None)
    if "--" in after:
        left, right = after.split("--", 1)
        target = left.strip().strip('"').strip("'")
        msg = right.strip()
        return True, (target or None), (msg or None)

    # Fallback: first token is the name, remainder is message
    parts = after.split(None, 1)
    if len(parts) == 1:
        # 'tell Bob' with no message
        return True, parts[0].strip(), None
    target, msg = parts[0].strip(), parts[1].strip()
    return True, (target or None), (msg or None)


def parse_whisper(text: str) -> Tuple[bool, str | None, str | None]:
    """Parse variations of the 'whisper' command.

    Supported forms:
    - whisper <name> <message>
    - whisper <name>: <message>
    - whisper <name> -- <message>
    - whisper "Multi Word Name" <message>
    - whisper 'Multi Word Name': <message>

    Returns: (is_whisper, target or None, message or None)
    """
    if not isinstance(text, str):
        return False, None, None
    stripped = text.strip()
    if not stripped.lower().startswith("whisper"):
        return False, None, None

    after = stripped[7:].lstrip()  # remove 'whisper'
    if not after:
        return True, None, None

    # Quoted name first
    if after[:1] in ('"', "'"):
        q = after[0]
        try:
            end_idx = after.find(q, 1)
        except Exception:
            end_idx = -1
        if end_idx != -1:
            target = after[1:end_idx].strip()
            rest = after[end_idx + 1 :].lstrip()
            # Optional separators
            if rest.startswith(":" ):
                rest = rest[1:].lstrip()
            elif rest.startswith("--"):
                rest = rest[2:].lstrip()
            msg = rest.strip() if rest else None
            return True, target if target else None, msg
        # Fall through

    # Unquoted: support <name>: <message> or <name> -- <message>
    if ":" in after:
        left, right = after.split(":", 1)
        target = left.strip().strip('"').strip("'")
        msg = right.strip()
        return True, (target or None), (msg or None)
    if "--" in after:
        left, right = after.split("--", 1)
        target = left.strip().strip('"').strip("'")
        msg = right.strip()
        return True, (target or None), (msg or None)

    # Fallback: first token is the name, remainder is message
    parts = after.split(None, 1)
    if len(parts) == 1:
        return True, parts[0].strip(), None
    target, msg = parts[0].strip(), parts[1].strip()
    return True, (target or None), (msg or None)


def extract_npc_mentions(text: str, npc_names: Iterable[str]) -> List[str]:
    """Return a list of NPC names that are mentioned in the given text.

    Matching is case-insensitive and uses word boundaries at the start and end
    of the NPC name to avoid substring false positives (e.g., 'Al' in 'Alice').
    The returned list preserves the order they appear in npc_names and is unique.
    """
    if not isinstance(text, str) or not text:
        return []
    mentions: list[str] = []
    seen: set[str] = set()
    for name in npc_names:
        if not isinstance(name, str) or not name:
            continue
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            if name not in seen:
                seen.add(name)
                mentions.append(name)
    return mentions
