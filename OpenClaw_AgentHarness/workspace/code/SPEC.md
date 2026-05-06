# Default sample task. Replace with your own SPEC.md before running ./setup.sh,
# or pass --spec path/to/your_spec.md to orchestrator.py.

# Specification: `is_balanced_brackets(s: str) -> bool`

Implement a function `is_balanced_brackets(s)` in `solution.py` that returns
`True` if the string `s` contains balanced bracket pairs and `False` otherwise.

## Brackets to support

| Open | Close |
|------|-------|
| `(`  | `)`   |
| `[`  | `]`   |
| `{`  | `}`   |

## Rules

1. The function takes a single `str` argument.
2. Non-bracket characters are ignored (e.g. `"a(b)c"` → `True`).
3. An empty string returns `True`.
4. Brackets must close in the correct nested order
   (`"([)]"` → `False`, `"([])"` → `True`).
5. Mismatched / unclosed brackets return `False`.
6. Raise `TypeError` if `s` is not a `str`.

## Public API

```python
def is_balanced_brackets(s: str) -> bool: ...
```

Place the function in `/home/node/.openclaw/workspace/code/solution.py` so that
`from solution import is_balanced_brackets` works from the same directory.
