# Specification: `LRUCache`

Implement an **LRU (Least Recently Used) cache** in `solution.py`.

## Required Skills

Apply the following Skill documents (Context Optimization — the Coder loads
ONLY these via `@FILE.md` references):

- @PYTHON_STYLE.md
- @ALGO_PATTERNS.md

## Public API

```python
class LRUCache:
    def __init__(self, capacity: int) -> None: ...
    def get(self, key): ...                      # returns value or -1 if missing
    def put(self, key, value) -> None: ...       # insert/update; evict LRU at capacity
    def __len__(self) -> int: ...
    def __contains__(self, key) -> bool: ...
```

## Rules

1. `capacity` must be a positive `int`. Raise `ValueError` if `capacity <= 0`,
   `TypeError` if `capacity` is not an `int`.
2. `get(key)`:
   - If `key` exists: mark it as **most recently used** and return its value.
   - If `key` is missing: return `-1`.
   - O(1) average time.
3. `put(key, value)`:
   - If `key` exists: update value and mark as most recently used.
   - If `key` is new and cache is at capacity: evict the **least recently used**
     entry, then insert.
   - O(1) average time.
4. Iteration order / internal order is **most-recent-last** (Python `OrderedDict`
   convention via `move_to_end`).

## Algorithm Pattern

Use a hash map + doubly-linked-list equivalent. Python's `collections.OrderedDict`
provides both in one structure:
- `move_to_end(key)` to refresh recency on hit/update.
- `popitem(last=False)` to evict the LRU entry.

This yields **O(1) average** for `get` and `put`, **O(n) space** for the cache.
Annotate complexity at the top of each method per `@ALGO_PATTERNS.md`.

## Style

Per `@PYTHON_STYLE.md`: type hints, PEP 8 names, docstrings (`Args:` / `Returns:`),
no bare `except:`, f-strings, `from __future__ import annotations`.

## Smoke Test (Runner will execute)

| Step                           | Expected                  |
|--------------------------------|---------------------------|
| `c = LRUCache(2)`              | created                   |
| `c.put(1, "a"); c.put(2, "b")` | size == 2                 |
| `c.get(1)`                     | `"a"` (1 is now MRU)      |
| `c.put(3, "c")`                | evicts key 2              |
| `c.get(2)`                     | `-1`                      |
| `c.get(3)`                     | `"c"`                     |
| `c.put(1, "A")`                | updates, 1 becomes MRU    |
| `c.get(3)`                     | `"c"` (still present)     |
| `LRUCache(0)`                  | raises `ValueError`       |
| `LRUCache("x")`                | raises `TypeError`        |
| `len(c)`                       | `2`                       |
| `1 in c`                       | `True`                    |
