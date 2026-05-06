# RUN_LOG

## Command
```
python3 smoke_test.py
```
(working dir: `workspace/code`)

## Output
```
OK
```

## Result
**PASS** — all SPEC smoke-test rows verified:

- size after two puts = 2
- `get(1)` returns `"a"` and refreshes recency
- `put(3,"c")` evicts key 2 (LRU)
- `get(2)` → `-1`, `get(3)` → `"c"`
- `put(1,"A")` updates value and bumps recency
- `len(c) == 2`, `1 in c == True`, `99 in c == False`
- `LRUCache(0)` → `ValueError`
- `LRUCache("x")` → `TypeError`
- `LRUCache(True)` → `TypeError` (bool guard, since `bool` is subclass of `int`)

No traceback. Diagnoser not invoked.
