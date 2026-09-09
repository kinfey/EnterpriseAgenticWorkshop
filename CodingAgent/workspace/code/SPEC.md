# Fibonacci Function

Implement `fibonacci(n: int) -> int` in `solution.py`.

## Required Skills

@PYTHON_STYLE.md
@TESTING.md

## Requirements

- Validate that `n` is a non-negative integer.
- Reject booleans as invalid integers.
- Raise `TypeError` when `n` is not an integer.
- Raise `ValueError` when `n` is negative.
- Return the nth Fibonacci number, with `fibonacci(0) == 0` and `fibonacci(1) == 1`.
- Use an efficient iterative implementation.
- Add and run a smoke test covering base cases, a typical value, and invalid inputs.
- Continue the self-correcting pipeline until the result is PASS, subject to `max_iterations=4`.
- Return the final `solution.py`.