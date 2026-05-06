# Skill: Algorithm Patterns

> Loaded by the Coder Agent only when the SPEC references `@ALGO_PATTERNS.md`.

Use the simplest pattern that satisfies the spec. Pick from this menu before
inventing something new.

## Bracket / nesting validation
- Stack of expected closers. Push the matching closer when you see an opener;
  on a closer, the top of the stack must equal it. Empty stack at end ⇒ valid.

## Sliding window
- For "longest / shortest contiguous subarray with property P". Two pointers,
  shrink from the left while P is violated.

## Two-pointer
- Sorted array, pair-sum, palindrome checks, in-place dedup.

## Hash map for O(n) lookups
- Frequency counts, complement search (two-sum), grouping anagrams.

## Recursion vs iteration
- Default to iteration. Use recursion only for naturally recursive structures
  (trees, divide-and-conquer). Always state and check the base case first.

## Complexity contract
- For any function you write: comment the time and space complexity at the
  top of the function in a single line, e.g. `# O(n) time, O(1) space`.
