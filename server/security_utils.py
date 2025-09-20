"""Security helpers for sanitizing data before display or logging.

Currently provides a deep redaction utility to remove or mask sensitive
fields like passwords from nested Python structures (dicts/lists/primitives).
"""

from __future__ import annotations

from typing import Any, Iterable, Set


DEFAULT_SENSITIVE_KEYS: Set[str] = {"password", "password_hash"}


def redact_sensitive(data: Any, keys: Iterable[str] | None = None, mask: str = "***REDACTED***") -> Any:
    """Return a deep-copied structure with sensitive fields redacted.

    - data: Any JSON-serializable Python structure (dict/list/scalars)
    - keys: iterable of key names to redact (case-insensitive). Defaults to password/password_hash.
    - mask: value used to replace sensitive values.

    Notes:
    - Only dict keys matching the sensitive set are replaced; structure is preserved.
    - Operates recursively for dicts and lists/tuples.
    """
    sens = set((keys or DEFAULT_SENSITIVE_KEYS))
    sens_lower = {k.lower() for k in sens}

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for k, v in node.items():
                if isinstance(k, str) and k.lower() in sens_lower:
                    out[k] = mask
                else:
                    out[k] = _walk(v)
            return out
        if isinstance(node, list):
            return [_walk(x) for x in node]
        if isinstance(node, tuple):
            return tuple(_walk(x) for x in node)
        # primitives
        return node

    return _walk(data)
