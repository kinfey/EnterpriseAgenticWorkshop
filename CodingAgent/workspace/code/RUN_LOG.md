## Result
PASS

## Command
python3 smoke_test.py

## Exit Code
0

## Stdout
```
OK: is_balanced_brackets('') == True
OK: is_balanced_brackets('()') == True
OK: is_balanced_brackets('([])') == True
OK: is_balanced_brackets('([)]') == False
OK: is_balanced_brackets('(') == False
OK: is_balanced_brackets(')(') == False
OK: is_balanced_brackets('a(b[c]d)e') == True
OK: TypeError raised for non-str input: expected str, got int
ALL SMOKE TESTS PASSED
```

## Stderr / Traceback
```
```
