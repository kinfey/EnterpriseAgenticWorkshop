from solution import LRUCache

c = LRUCache(2)
c.put(1, "a")
c.put(2, "b")
assert len(c) == 2, f"expected size 2, got {len(c)}"
assert c.get(1) == "a", f"expected 'a', got {c.get(1)!r}"
c.put(3, "c")  # evicts 2
assert c.get(2) == -1, f"expected -1, got {c.get(2)!r}"
assert c.get(3) == "c", f"expected 'c', got {c.get(3)!r}"
c.put(1, "A")
assert c.get(3) == "c", f"expected 'c', got {c.get(3)!r}"

try:
    LRUCache(0)
except ValueError:
    pass
else:
    raise AssertionError("LRUCache(0) should raise ValueError")

try:
    LRUCache("x")
except TypeError:
    pass
else:
    raise AssertionError("LRUCache('x') should raise TypeError")

assert len(c) == 2, f"expected len 2, got {len(c)}"
assert (1 in c) is True, "expected 1 in c"

print("SMOKE OK")
