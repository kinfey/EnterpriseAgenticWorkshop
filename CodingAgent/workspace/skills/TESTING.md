# Skill: Testing & Smoke Tests

> Loaded by the Coder/Runner Agents when the SPEC references `@TESTING.md`.

## Smoke test contract

When the SPEC contains a `## Smoke Test` section, the Runner generates
`smoke_test.py` next to `solution.py`:

```python
"""smoke_test.py — minimal end-to-end check for solution.py."""
from solution import <public_api>

def main() -> int:
    failures: list[str] = []
    # one assertion per row in the spec's Smoke Test table
    # ...
    if failures:
        for f in failures:
            print("FAIL:", f)
        raise SystemExit(1)
    print("OK")
    return 0

if __name__ == "__main__":
    main()
```

Rules:
- The file MUST exit non-zero on any mismatch so the Runner captures a
  traceback.
- Use plain `assert` so failures surface as `AssertionError` with a useful
  message: `assert got == want, f"f({arg!r}) -> {got!r}, want {want!r}"`.
- Cover at minimum: happy path, one boundary case, one invalid input case
  (wrap with `pytest.raises`-equivalent: a `try/except` that re-raises if the
  expected exception was NOT raised).
