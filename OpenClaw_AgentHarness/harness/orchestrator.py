"""
orchestrator.py — Self-loop testing pipeline driver.

Pipeline (one iteration):

  ┌──────────────────────────────────────────────────────────────────┐
  │ Agent A (coder)  → writes code/solution.py                        │
  │ Agent B (tester) → writes code/test_solution.py                   │
  │ Agent C (runner) → runs pytest, writes code/RUN_REPORT.md         │
  └──────────────────────────────────────────────────────────────────┘

If RUN_REPORT.md says PASS → stop. Otherwise loop back to Agent A,
which now has access to the failure feedback in RUN_REPORT.md.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from openclaw_client import call_agent, wait_for_gateway


# Inside the harness container the workspace is mounted at /workspace.
# Inside the openclaw container the SAME workspace is mounted at
# /home/node/.openclaw/workspace — that is the path agents use.
HOST_WORKSPACE = Path(os.getenv("HARNESS_WORKSPACE", "/workspace"))
CODE_DIR = HOST_WORKSPACE / "code"

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))


# ────────────────────────────────────────────────────────────────────
#  Prompts
# ────────────────────────────────────────────────────────────────────

CODER_PROMPT = """\
ITERATION {iteration} of {max_iterations}.

Read /home/node/.openclaw/workspace/code/SPEC.md and implement the solution.

{feedback_block}

Write the implementation to:
  /home/node/.openclaw/workspace/code/solution.py

After saving, reply with a JSON object:
{{"status":"done","file":"solution.py","notes":"<one-line summary>"}}
"""

TESTER_PROMPT = """\
ITERATION {iteration} of {max_iterations}.

Read:
  /home/node/.openclaw/workspace/code/SPEC.md
  /home/node/.openclaw/workspace/code/solution.py

Then write rigorous pytest test cases covering happy path, edge cases,
boundaries, and invalid input to:
  /home/node/.openclaw/workspace/code/test_solution.py

Use `from solution import ...`. Do NOT modify solution.py.

After saving, reply with a JSON object:
{{"status":"done","file":"test_solution.py","test_count":N}}
"""

RUNNER_PROMPT = """\
ITERATION {iteration} of {max_iterations}.

cd /home/node/.openclaw/workspace/code

Run: python -m pytest test_solution.py -v --tb=short
Capture all output. If pytest is not installed, first run:
  python -m pip install --quiet pytest

Write a Markdown report to:
  /home/node/.openclaw/workspace/code/RUN_REPORT.md

The report MUST contain these sections (use these exact headings):

  ## Result
  PASS  or  FAIL

  ## Summary
  passed=N failed=N errors=N

  ## Failed Tests
  (test name + assertion message; `(none)` if all passed)

  ## Suggested Fixes
  (Concrete advice for the Coder. `(none)` if all passed.)

After writing the report, reply with EXACTLY one final JSON line (and nothing else):
{{"status":"PASS"|"FAIL","passed":N,"failed":N,"report":"RUN_REPORT.md"}}
"""


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    """Pull the LAST JSON object out of an agent reply."""
    matches = list(re.finditer(r"\{[^{}]*\}", text, re.DOTALL))
    for m in reversed(matches):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    return None


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _reset_iteration(keep_report: bool) -> None:
    """Remove stale solution + tests so each iteration starts fresh."""
    for name in ("solution.py", "test_solution.py"):
        f = CODE_DIR / name
        if f.exists():
            f.unlink()
    if not keep_report:
        rep = CODE_DIR / "RUN_REPORT.md"
        if rep.exists():
            rep.unlink()


def _parse_run_status(report_text: str, runner_json: dict | None) -> str:
    """Decide PASS/FAIL from runner JSON first, falling back to report text."""
    if runner_json and isinstance(runner_json.get("status"), str):
        s = runner_json["status"].upper()
        if s in ("PASS", "FAIL"):
            return s
    m = re.search(r"##\s*Result\s*\n+\s*(PASS|FAIL)", report_text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return "FAIL"


# ────────────────────────────────────────────────────────────────────
#  Main loop
# ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70, flush=True)
    print("  OpenClaw Agent Harness — Self-loop testing pipeline", flush=True)
    print(f"  Workspace: {HOST_WORKSPACE}", flush=True)
    print(f"  Max iterations: {MAX_ITERATIONS}", flush=True)
    print("=" * 70, flush=True)

    spec = CODE_DIR / "SPEC.md"
    if not spec.exists():
        print(f"❌ Missing spec: {spec}", flush=True)
        return 2

    wait_for_gateway()

    # Wipe any cross-run agent session memory so each pipeline starts clean
    # (otherwise the LLM may "remember" a prior fabricated success and skip
    # tool calls).
    import subprocess
    subprocess.run(
        ["docker", "exec", os.getenv("OPENCLAW_CONTAINER", "openclaw"),
         "bash", "-lc",
         "rm -rf /home/node/.openclaw/agents/*/sessions/* 2>/dev/null || true"],
        check=False,
    )

    final_status = "FAIL"
    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n━━━━━━ Iteration {iteration}/{MAX_ITERATIONS} ━━━━━━", flush=True)

        # Keep prior RUN_REPORT around as feedback for the coder; tester &
        # solution are always rewritten.
        _reset_iteration(keep_report=(iteration > 1))

        # ---- Agent A: Coder ------------------------------------------------
        prior_report = _read(CODE_DIR / "RUN_REPORT.md")
        feedback_block = (
            "There is a prior run report at "
            "/home/node/.openclaw/workspace/code/RUN_REPORT.md describing test "
            "failures from the previous iteration. READ IT and address every "
            "failure listed under '## Suggested Fixes'."
            if prior_report
            else "This is the first iteration. There is no prior run report yet."
        )
        coder_reply = call_agent(
            "coder",
            CODER_PROMPT.format(
                iteration=iteration,
                max_iterations=MAX_ITERATIONS,
                feedback_block=feedback_block,
            ),
        )
        print(f"[coder] reply: {coder_reply[:200]}", flush=True)
        if not (CODE_DIR / "solution.py").exists():
            print("❌ Coder did not produce solution.py", flush=True)
            final_status = "FAIL"
            break

        # ---- Agent B: Tester -----------------------------------------------
        tester_reply = call_agent(
            "tester",
            TESTER_PROMPT.format(iteration=iteration, max_iterations=MAX_ITERATIONS),
        )
        print(f"[tester] reply: {tester_reply[:200]}", flush=True)
        if not (CODE_DIR / "test_solution.py").exists():
            print("❌ Tester did not produce test_solution.py", flush=True)
            final_status = "FAIL"
            break

        # ---- Agent C: Runner -----------------------------------------------
        # Drop any stale RUN_REPORT before the runner runs so we know it wrote
        # a fresh one this iteration.
        old_report = CODE_DIR / "RUN_REPORT.md"
        if old_report.exists():
            old_report.unlink()

        runner_reply = call_agent(
            "runner",
            RUNNER_PROMPT.format(iteration=iteration, max_iterations=MAX_ITERATIONS),
            timeout=900,
        )
        print(f"[runner] reply: {runner_reply[:300]}", flush=True)

        report_text = _read(old_report)
        runner_json = _extract_json(runner_reply)
        status = _parse_run_status(report_text, runner_json)

        print(f"\n>>> Iteration {iteration} status: {status}", flush=True)
        if status == "PASS":
            final_status = "PASS"
            print("\n✅ Tests passed — pipeline complete.", flush=True)
            break

    # Summary --------------------------------------------------------------
    print("\n" + "=" * 70, flush=True)
    print(f"  FINAL: {final_status}", flush=True)
    print(f"  solution.py:      {(CODE_DIR / 'solution.py').exists()}", flush=True)
    print(f"  test_solution.py: {(CODE_DIR / 'test_solution.py').exists()}", flush=True)
    print(f"  RUN_REPORT.md:    {(CODE_DIR / 'RUN_REPORT.md').exists()}", flush=True)
    print("=" * 70, flush=True)
    return 0 if final_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
