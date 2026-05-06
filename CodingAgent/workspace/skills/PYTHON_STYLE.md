# Skill: Python Style

> Loaded by the Coder Agent only when the SPEC references `@PYTHON_STYLE.md`.

## Hard rules

1. **Type hints** on every public function and method (`def f(x: int) -> bool`).
2. **PEP 8** naming: `snake_case` for functions and variables, `PascalCase`
   for classes, `UPPER_CASE` for module-level constants.
3. **Docstrings**: every public function MUST have a one-line summary plus a
   short description of `Args:` and `Returns:`.
4. **No `print` debugging** in shipped code. Use the `logging` module if you
   really need to log.
5. **No bare `except:`**. Always catch a specific `Exception` subclass.
6. **No mutable default arguments** (`def f(xs=[])`). Use `None` + initialize.
7. **f-strings** over `%` formatting and `str.format`.
8. **`pathlib.Path`** over `os.path` for filesystem work.

## Module shape

```python
"""<one-line module summary>"""
from __future__ import annotations

# stdlib imports
# third-party imports
# local imports

# constants
# helpers (prefixed with _ if private)
# public API (the symbols the SPEC tells you to expose)
```
