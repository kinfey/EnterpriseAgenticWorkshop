# AGENTS.md — OpenClaw Self-Loop Testing Workspace

This workspace is shared by three agents who collaborate on a code → test → run feedback loop:

| Agent | Role | Tools |
|-------|------|-------|
| **Agent A — Coder** 🧑‍💻 | Reads `code/SPEC.md`, writes `code/solution.py`. Reads `code/RUN_REPORT.md` if present and fixes the failures. | `read`, `write`, `edit` |
| **Agent B — Tester** 🧪 | Reads spec + solution, writes `code/test_solution.py` (pytest cases). | `read`, `write`, `edit` |
| **Agent C — Runner** 🏃 | Runs `pytest test_solution.py`, writes `code/RUN_REPORT.md`. | `read`, `write`, `exec` |

## Folder layout

```
workspace/
├── AGENTS.md          ← this file
├── IDENTITY.md        ← per-agent identity card
└── code/              ← shared scratch directory (the only place exec is allowed)
    ├── SPEC.md         (input — written by orchestrator)
    ├── solution.py     (written by Agent A)
    ├── test_solution.py (written by Agent B)
    └── RUN_REPORT.md   (written by Agent C, consumed by Agent A on next iteration)
```

## Loop contract

1. Orchestrator drops `SPEC.md` and clears any prior artifacts.
2. **Coder** writes `solution.py`.
3. **Tester** writes `test_solution.py`.
4. **Runner** executes pytest; writes `RUN_REPORT.md` with PASS/FAIL.
5. If FAIL and iterations remain → loop back to step 2 (Coder reads RUN_REPORT and patches).
6. If PASS → orchestrator stops.

## Rules

- Never run code outside the `code/` directory.
- Always import from `solution.py` in tests — never inline the implementation.
- Keep file paths exactly as listed; the orchestrator and other agents depend on them.
