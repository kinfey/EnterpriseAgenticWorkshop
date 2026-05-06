"""LRU (Least Recently Used) cache implementation.

Follows @PYTHON_STYLE.md and @ALGO_PATTERNS.md (hash map + ordered structure
for O(1) average get/put).
"""
from __future__ import annotations

# stdlib imports
from collections import OrderedDict
from typing import Any, Hashable

# public API
__all__ = ["LRUCache"]

# sentinel returned by get() on a miss (per SPEC)
_MISS: int = -1


class LRUCache:
    """Fixed-capacity Least Recently Used cache.

    Backed by ``collections.OrderedDict`` which behaves as a hash map plus a
    doubly-linked list, giving O(1) average ``get`` and ``put``. Recency order
    is *most-recent-last*: ``move_to_end`` refreshes a key, ``popitem(last=False)``
    evicts the oldest.
    """

    def __init__(self, capacity: int) -> None:
        """Create an empty cache with the given capacity.

        Args:
            capacity: Maximum number of entries. Must be a positive ``int``.

        Returns:
            None.
        """
        # Reject bools explicitly: bool is a subclass of int in Python.
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise TypeError(
                f"capacity must be an int, got {type(capacity).__name__}"
            )
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")

        self._capacity: int = capacity
        self._store: OrderedDict[Hashable, Any] = OrderedDict()

    # ------------------------------------------------------------------ #
    # Core API                                                           #
    # ------------------------------------------------------------------ #

    def get(self, key: Hashable) -> Any:
        """Return the value for ``key`` and mark it as most recently used.

        # O(1) average time, O(1) extra space

        Args:
            key: Hashable key to look up.

        Returns:
            The stored value if ``key`` is present, otherwise ``-1``.
        """
        if key not in self._store:
            return _MISS
        self._store.move_to_end(key, last=True)
        return self._store[key]

    def put(self, key: Hashable, value: Any) -> None:
        """Insert or update ``key`` -> ``value``, evicting the LRU on overflow.

        # O(1) average time, O(1) extra space

        Args:
            key: Hashable key to insert or refresh.
            value: Associated value.

        Returns:
            None.
        """
        if key in self._store:
            self._store[key] = value
            self._store.move_to_end(key, last=True)
            return

        if len(self._store) >= self._capacity:
            # Evict least recently used (front of the OrderedDict).
            self._store.popitem(last=False)
        self._store[key] = value

    # ------------------------------------------------------------------ #
    # Dunder helpers                                                     #
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        """Return current number of cached entries.

        # O(1) time, O(1) space

        Returns:
            Number of entries currently held.
        """
        return len(self._store)

    def __contains__(self, key: object) -> bool:
        """Membership test that does NOT affect recency.

        # O(1) average time, O(1) space

        Args:
            key: Key to test for presence.

        Returns:
            ``True`` if the key is currently cached, else ``False``.
        """
        return key in self._store

    def __repr__(self) -> str:
        """Developer-friendly representation.

        Returns:
            String like ``LRUCache(capacity=2, size=1)``.
        """
        return (
            f"LRUCache(capacity={self._capacity}, size={len(self._store)})"
        )
