"""Balanced bracket validator."""
from __future__ import annotations

# Mapping from opening bracket to its matching closing bracket.
_PAIRS: dict[str, str] = {"(": ")", "[": "]", "{": "}"}
_OPENERS: frozenset[str] = frozenset(_PAIRS.keys())
_CLOSERS: frozenset[str] = frozenset(_PAIRS.values())


def is_balanced_brackets(s: str) -> bool:
    """Return True iff `s` has correctly nested bracket pairs.

    Args:
        s: Input string. Non-bracket characters are ignored.

    Returns:
        True if every opener has a matching closer in correct nested order,
        False otherwise. Empty string returns True.

    Raises:
        TypeError: If `s` is not a `str`.
    """
    # O(n) time, O(n) space — single pass with a stack of expected closers.
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    stack: list[str] = []
    for ch in s:
        if ch in _OPENERS:
            stack.append(_PAIRS[ch])
        elif ch in _CLOSERS:
            if not stack or stack.pop() != ch:
                return False
        # non-bracket characters are ignored
    return not stack
