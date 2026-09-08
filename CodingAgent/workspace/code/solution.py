"""Provide an O(1) least-recently-used cache."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any


class LRUCache:
    """Store a fixed number of values using least-recently-used eviction."""

    def __init__(self, capacity: int) -> None:
        """Initialize a cache with the requested capacity.

        Args:
            capacity: Maximum number of entries the cache may hold.

        Returns:
            None.
        """
        # O(1) time, O(1) space.
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity must be a positive integer")

        self._capacity = capacity
        self._items: OrderedDict[Any, Any] = OrderedDict()

    def get(self, key: Any) -> Any:
        """Return a cached value and mark its key as most recently used.

        Args:
            key: Key whose cached value should be retrieved.

        Returns:
            The cached value when present; otherwise, -1.
        """
        # O(1) average time, O(1) space.
        if key not in self._items:
            return -1

        self._items.move_to_end(key)
        return self._items[key]

    def put(self, key: Any, value: Any) -> None:
        """Insert or update a value and evict the least-recently-used entry.

        Args:
            key: Key to insert or update.
            value: Value to associate with the key.

        Returns:
            None.
        """
        # O(1) average time, O(1) auxiliary space.
        if key in self._items:
            self._items.move_to_end(key)
        self._items[key] = value

        if len(self._items) > self._capacity:
            self._items.popitem(last=False)


if __name__ == "__main__":
    c = LRUCache(2)
    c.put(1, 1)
    c.put(2, 2)
    assert c.get(1) == 1
    c.put(3, 3)
    assert c.get(2) == -1
    c.put(4, 4)
    assert c.get(1) == -1
    assert c.get(3) == 3
    assert c.get(4) == 4
    print("OK")
