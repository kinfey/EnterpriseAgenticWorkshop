"""Smoke test for LRUCache (Runner-generated)."""
from __future__ import annotations

from solution import LRUCache


def main() -> None:
    c = LRUCache(2)
    c.put(1, "a")
    c.put(2, "b")
    assert len(c) == 2, f"expected size 2, got {len(c)}"

    assert c.get(1) == "a"          # 1 is now MRU; 2 is LRU
    c.put(3, "c")                   # evicts key 2
    assert c.get(2) == -1, "key 2 should have been evicted"
    assert c.get(3) == "c"

    c.put(1, "A")                   # update + bump
    assert c.get(1) == "A"
    assert c.get(3) == "c"          # 3 still present

    # Membership does not affect recency
    assert 1 in c
    assert 99 not in c
    assert len(c) == 2

    # Validation
    try:
        LRUCache(0)
    except ValueError:
        pass
    else:
        raise AssertionError("LRUCache(0) should raise ValueError")

    try:
        LRUCache("x")  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("LRUCache('x') should raise TypeError")

    try:
        LRUCache(True)  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("LRUCache(True) should raise TypeError (bool guard)")

    print("OK")


if __name__ == "__main__":
    main()
