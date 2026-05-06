# Specification: `is_balanced_brackets(s: str) -> bool`

Implement a function `is_balanced_brackets(s)` in `solution.py` that returns
`True` iff `s` contains balanced bracket pairs.

## Required Skills

Apply the following Skill documents (the Coder reads each one before writing
code; this is the **Context Optimization** mechanism):

- @PYTHON_STYLE.md
- @ALGO_PATTERNS.md
- @ERROR_HANDLING.md
- @TESTING.md

## Brackets

| Open | Close |
|------|-------|
| `(`  | `)`   |
| `[`  | `]`   |
| `{`  | `}`   |

## Rules

1. Single `str` argument.
2. Non-bracket characters are ignored: `"a(b)c"` → `True`.
3. Empty string → `True`.
4. Brackets must close in correct nested order: `"([)]"` → `False`,
   `"([])"` → `True`.
5. Unclosed / mismatched brackets → `False`.
6. Raise `TypeError` if `s` is not a `str`.

## Public API

```python
def is_balanced_brackets(s: str) -> bool: ...
```

Located at `/home/node/.openclaw/workspace/code/solution.py` so that
`from solution import is_balanced_brackets` works from the same directory.

## Smoke Test

| Input         | Expected         |
|---------------|------------------|
| `""`          | `True`           |
| `"()"`        | `True`           |
| `"([])"`      | `True`           |
| `"([)]"`      | `False`          |
| `"("`         | `False`          |
| `")("`        | `False`          |
| `"a(b[c]d)e"` | `True`           |
| `123`         | raises `TypeError` |
