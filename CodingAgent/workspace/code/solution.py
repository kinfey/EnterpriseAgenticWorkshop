"""Provide an efficient Fibonacci number implementation."""
from __future__ import annotations


def fibonacci(n: int) -> int:
    """Return the Fibonacci number at a validated non-negative index.

    Args:
        n: The zero-based index in the Fibonacci sequence.

    Returns:
        The Fibonacci number at index ``n``.

    Raises:
        TypeError: If ``n`` is not an integer or is a boolean.
        ValueError: If ``n`` is negative.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be non-negative")

    previous, current = 0, 1
    for _ in range(n):
        previous, current = current, previous + current
    return previous
