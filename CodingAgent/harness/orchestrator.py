"""
orchestrator.py — Code-generation pipeline with skill-based context
optimization and traceback-driven error correction.

Pipeline (one iteration):

  ┌───────────────────────────────────────────────────────────────────┐
  │ Coder      → reads SPEC.md + @-referenced skills + DIAGNOSIS.md   │
  │              → writes solution.py                                 │
  │ Runner     → executes solution, captures full Traceback           │
  │              → writes RUN_LOG.md (PASS/FAIL + verbatim traceback) │
  │ Diagnoser  → only on FAIL: parses Traceback in RUN_LOG.md         │
  │              → writes DIAGNOSIS.md (Patch Plan for next iteration)│
  └───────────────────────────────────────────────────────────────────┘

PASS → exit 0. FAIL → next iteration; Coder reads DIAGNOSIS.md as feedback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from openclaw_client import call_agent, wait_for_gateway


HOST_WORKSPACE = Path(os.getenv("HARNESS_WORKSPACE", "/workspace"))
CODE_DIR = HOST_WORKSPACE / "code"
SKILLS_DIR = HOST_WORKSPACE / "skills"

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "4"))


# ────────────────────────────────────────────────────────────────────
#  Prompts — Copilot-style @-references make context optimization explicit.
# ────────────────────────────────────────────────────────────────────

CODER_PROMPT = """\
ITERATION {iteration} of {max_iterations}.

# Task
Read the spec at /home/node/.openclaw/workspace/code/SPEC.md and implement it
in /home/node/.openclaw/workspace/code/solution.py.

# Skill References (Context Optimization)
Apply the following Skill documents — read each ONE BEFORE writing code, and
treat them as binding constraints:

{skill_refs}

Each reference above is in the form `@FILE.md` and lives at
/home/node/.openclaw/workspace/skills/FILE.md. Do NOT load any other skill
files; keeping the context lean is part of your job.

# Error Correction Feedback
{feedback_block}

# Output
After saving solution.py, reply with EXACTLY one JSON line:
{{"status":"done","file":"solution.py","skills_used":[...],"notes":"<one-liner>"}}
"""

RUNNER_PROMPT = """\
ITERATION {iteration} of {max_iterations}.

Execute the Coder's implementation and capture the FULL Python traceback if it
fails. Follow your system instructions exactly. The workspace is at
/home/node/.openclaw/workspace/code.

After writing RUN_LOG.md, reply with EXACTLY one JSON line:
{{"status":"PASS"|"FAIL","exit_code":N,"log":"RUN_LOG.md"}}
"""

DIAGNOSER_PROMPT = """\
ITERATION {iteration} of {max_iterations}.

The Runner reported FAIL. Read /home/node/.openclaw/workspace/code/RUN_LOG.md
(it contains a verbatim Python traceback under '## Stderr / Traceback'),
then read solution.py and SPEC.md, and produce
/home/node/.openclaw/workspace/code/DIAGNOSIS.md as specified in your system
instructions. The Coder will read your Patch Plan in the next iteration.

Reply with EXACTLY one JSON line:
{{"status":"diagnosed","exception":"<Type: message>","file":"DIAGNOSIS.md"}}
"""


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
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


def _discover_skill_refs(spec_text: str) -> list[str]:
    """
    Pull `@FILE.md` references out of SPEC.md. Anything that lives under
    workspace/skills/ counts. Order is preserved, duplicates removed.
    """
    seen: list[str] = []
    for m in re.finditer(r"@([A-Za-z0-9_\-]+\.md)", spec_text):
        ref = m.group(1)
        if ref in seen:
            continue
        if (SKILLS_DIR / ref).exists():
            seen.append(ref)
    return seen


def _format_skill_refs(refs: list[str]) -> str:
    if not refs:
        return ("(SPEC.md did not reference any skills explicitly. Re-read SPEC.md "
                "carefully and apply general Python best practices.)")
    lines = []
    for r in refs:
        first_line = ""
        try:
            with (SKILLS_DIR / r).open(encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if raw and not raw.startswith("#"):
                        first_line = raw
                        break
                    if raw.startswith("# "):
                        first_line = raw.lstrip("# ").strip()
                        break
        except OSError:
            pass
        lines.append(f"  - @{r}" + (f"  — {first_line}" if first_line else ""))
    return "\n".join(lines)


def _parse_run_status(runner_json: dict | None, log_text: str) -> str:
    if runner_json and isinstance(runner_json.get("status"), str):
        s = runner_json["status"].upper()
        if s in ("PASS", "FAIL"):
            return s
    m = re.search(r"##\s*Result\s*\n+\s*(PASS|FAIL)", log_text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return "FAIL"


def _reset_iteration_artifacts(keep_diagnosis: bool) -> None:
    """Drop solution.py + RUN_LOG.md so the iteration starts fresh.

    DIAGNOSIS.md is preserved when keep_diagnosis=True so the Coder can read it
    as Error-Correction feedback, then deleted at the start of iteration 1.
    """
    for name in ("solution.py", "RUN_LOG.md"):
        f = CODE_DIR / name
        if f.exists():
            f.unlink()
    if not keep_diagnosis:
        d = CODE_DIR / "DIAGNOSIS.md"
        if d.exists():
            d.unlink()


# ────────────────────────────────────────────────────────────────────
#  Main loop
# ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 72, flush=True)
    print("  CodingAgent — OpenClaw + Copilot self-correcting code generator", flush=True)
    print(f"  Workspace: {HOST_WORKSPACE}", flush=True)
    print(f"  Max iterations: {MAX_ITERATIONS}", flush=True)
    print("=" * 72, flush=True)

    spec_path = CODE_DIR / "SPEC.md"
    if not spec_path.exists():
        print(f"❌ Missing spec: {spec_path}", flush=True)
        return 2

    spec_text = _read(spec_path)
    skill_refs = _discover_skill_refs(spec_text)
    print(f"[orchestrator] Skill references in SPEC.md: {skill_refs or '(none)'}",
          flush=True)

    wait_for_gateway()

    # Wipe any cross-run agent session memory.
    subprocess.run(
        ["docker", "exec", os.getenv("OPENCLAW_CONTAINER", "codingagent-openclaw"),
         "bash", "-lc",
         "rm -rf /home/node/.openclaw/agents/*/sessions/* 2>/dev/null || true"],
        check=False,
    )

    final_status = "FAIL"
    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n━━━━━━ Iteration {iteration}/{MAX_ITERATIONS} ━━━━━━", flush=True)

        # Iteration 1: clean slate. Iterations >1: keep DIAGNOSIS.md so the
        # Coder can act on it (Error Correction loop).
        _reset_iteration_artifacts(keep_diagnosis=(iteration > 1))

        # ---- Coder ----------------------------------------------------------
        prior_diag = _read(CODE_DIR / "DIAGNOSIS.md")
        feedback_block = (
            "There IS a prior diagnosis at "
            "/home/node/.openclaw/workspace/code/DIAGNOSIS.md describing why your "
            "previous attempt failed. READ IT and address every bullet under "
            "'## Patch Plan' before writing solution.py."
            if prior_diag
            else "First iteration — no prior failures yet."
        )
        coder_reply = call_agent(
            "coder",
            CODER_PROMPT.format(
                iteration=iteration,
                max_iterations=MAX_ITERATIONS,
                skill_refs=_format_skill_refs(skill_refs),
                feedback_block=feedback_block,
            ),
        )
        print(f"[coder] reply: {coder_reply[:240]}", flush=True)
        if not (CODE_DIR / "solution.py").exists():
            print("❌ Coder did not produce solution.py", flush=True)
            break

        # ---- Runner ---------------------------------------------------------
        runner_reply = call_agent(
            "runner",
            RUNNER_PROMPT.format(iteration=iteration, max_iterations=MAX_ITERATIONS),
            timeout=900,
        )
        print(f"[runner] reply: {runner_reply[:240]}", flush=True)

        log_text = _read(CODE_DIR / "RUN_LOG.md")
        runner_json = _extract_json(runner_reply)
        status = _parse_run_status(runner_json, log_text)
        print(f"\n>>> Iteration {iteration} status: {status}", flush=True)

        if status == "PASS":
            final_status = "PASS"
            print("\n✅ Solution passed — pipeline complete.", flush=True)
            break

        # ---- Diagnoser (Error Correction) ----------------------------------
        # Drop any stale diagnosis so we can detect whether this iteration's
        # diagnoser actually wrote a fresh file.
        old_diag = CODE_DIR / "DIAGNOSIS.md"
        if old_diag.exists():
            old_diag.unlink()

        diag_reply = call_agent(
            "diagnoser",
            DIAGNOSER_PROMPT.format(
                iteration=iteration, max_iterations=MAX_ITERATIONS
            ),
        )
        print(f"[diagnoser] reply: {diag_reply[:240]}", flush=True)
        if not old_diag.exists():
            print("⚠️  Diagnoser did not write DIAGNOSIS.md — coder will retry blind.",
                  flush=True)

    print("\n" + "=" * 72, flush=True)
    print(f"  FINAL: {final_status}", flush=True)
    print(f"  solution.py:   {(CODE_DIR / 'solution.py').exists()}", flush=True)
    print(f"  RUN_LOG.md:    {(CODE_DIR / 'RUN_LOG.md').exists()}", flush=True)
    print(f"  DIAGNOSIS.md:  {(CODE_DIR / 'DIAGNOSIS.md').exists()}", flush=True)
    print("=" * 72, flush=True)
    return 0 if final_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
