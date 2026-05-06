# Skill: Error Handling

> Loaded by the Coder Agent only when the SPEC references `@ERROR_HANDLING.md`.

## Validate at the boundary

Validate inputs **once**, at the public function entry point. Internal helpers
trust their callers.

```python
def public_api(s: str) -> bool:
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")
    return _impl(s)
```

## Choose the right exception

| Situation                              | Raise                |
|----------------------------------------|----------------------|
| Wrong argument type                    | `TypeError`          |
| Right type, out-of-range / malformed   | `ValueError`         |
| Lookup miss (caller's key is wrong)    | `KeyError`           |
| Index out of bounds                    | `IndexError`         |
| Operation makes no sense in this state | `RuntimeError`       |

## Never swallow errors silently

- No `except: pass`.
- No `except Exception: return None` unless the spec explicitly allows it.
- If you must convert an exception, chain it: `raise NewError(...) from e`.

## Messages

Error messages must contain (a) what was expected and (b) what was received.
Bad: `"invalid input"`. Good: `"expected non-empty str, got ''"`.
