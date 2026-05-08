"""LRU (Least Recently Used) cache implementation backed by OrderedDict."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Hashable

_MISSING = -1


class LRUCache:
    """Fixed-capacity LRU cache with O(1) average get/put.

    Internal order follows Python's ``OrderedDict`` convention: the most
    recently used entry is at the end, the least recently used at the front.
    """

    def __init__(self, capacity: int) -> None:
        """Initialize the cache.

        Args:
            capacity: Maximum number of entries. Must be a positive ``int``.

        Returns:
            None.
        """
        # O(1) time, O(1) space (allocates an empty OrderedDict).
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise TypeError(f"capacity must be an int, got {type(capacity).__name__}")
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        self._capacity: int = capacity
        self._data: "OrderedDict[Hashable, Any]" = OrderedDict()

    def get(self, key: Hashable) -> Any:
        """Fetch a value and mark its key as most recently used.

        Args:
            key: Hashable key to look up.

        Returns:
            The stored value, or ``-1`` if the key is not present.
        """
        # O(1) average time, O(1) space.
        if key not in self._data:
            return _MISSING
        self._data.move_to_end(key, last=True)
        return self._data[key]

    def put(self, key: Hashable, value: Any) -> None:
        """Insert or update a key/value pair, evicting LRU if needed.

        Args:
            key: Hashable key to insert or update.
            value: Value to associate with ``key``.

        Returns:
            None.
        """
        # O(1) average time, O(1) space (amortized; cache holds <= capacity items).
        if key in self._data:
            self._data[key] = value
            self._data.move_to_end(key, last=True)
            return
        if len(self._data) >= self._capacity:
            self._data.popitem(last=False)
        self._data[key] = value

    def __len__(self) -> int:
        """Return the current number of cached entries."""
        # O(1) time, O(1) space.
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        """Return whether ``key`` is currently cached (does not affect recency)."""
        # O(1) average time, O(1) space.
        return key in self._data
