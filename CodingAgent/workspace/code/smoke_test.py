from solution import is_balanced_brackets

cases = [
    ("", True),
    ("()", True),
    ("([])", True),
    ("([)]", False),
    ("(", False),
    (")(", False),
    ("a(b[c]d)e", True),
]

for s, expected in cases:
    got = is_balanced_brackets(s)
    assert got == expected, f"is_balanced_brackets({s!r}) returned {got!r}, expected {expected!r}"
    print(f"OK: is_balanced_brackets({s!r}) == {got!r}")

# TypeError case
try:
    is_balanced_brackets(123)
except TypeError as e:
    print(f"OK: TypeError raised for non-str input: {e}")
else:
    raise AssertionError("Expected TypeError for non-str input")

print("ALL SMOKE TESTS PASSED")
