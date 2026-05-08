# SPEC: LRU Cache

## Task
Implement an LRU (Least Recently Used) cache as a class `LRUCache` in
`workspace/code/solution.py`.

## Required Skills
- @PYTHON_STYLE.md
- @ALGO_PATTERNS.md

## API
- `LRUCache(capacity: int)` — construct with a positive integer capacity.
- `get(key) -> value | -1` — return value if present and mark as most-recently
  used; otherwise return `-1`.
- `put(key, value) -> None` — insert/update; if size exceeds capacity, evict
  the least-recently-used entry.

## Complexity Contract
- `get` and `put` must both be **O(1) average time**.
- Add a one-line complexity comment at the top of each method
  (per `@ALGO_PATTERNS.md`).

## Implementation Hint
Use `collections.OrderedDict` (move_to_end + popitem(last=False)) — this is
the simplest pattern that satisfies the O(1) contract, consistent with
"Use the simplest pattern that satisfies the spec" from `@ALGO_PATTERNS.md`.

## Validation
- `capacity` must be a positive int; raise `ValueError` otherwise.

## Smoke Test (in `if __name__ == "__main__":`)
```
c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1          # 1 is now MRU
c.put(3, 3)                   # evicts key 2
assert c.get(2) == -1
c.put(4, 4)                   # evicts key 1
assert c.get(1) == -1
assert c.get(3) == 3
assert c.get(4) == 4
print("OK")
```
