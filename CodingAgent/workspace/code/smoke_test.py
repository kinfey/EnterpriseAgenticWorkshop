"""Smoke tests for the Fibonacci implementation."""

from solution import fibonacci


assert fibonacci(0) == 0
assert fibonacci(1) == 1
assert fibonacci(10) == 55

for invalid in (True, 1.5, "3", None):
    try:
        fibonacci(invalid)
    except TypeError:
        pass
    else:
        raise AssertionError(f"Expected TypeError for {invalid!r}")

try:
    fibonacci(-1)
except ValueError:
    pass
else:
    raise AssertionError("Expected ValueError for -1")

print("Smoke tests passed.")
