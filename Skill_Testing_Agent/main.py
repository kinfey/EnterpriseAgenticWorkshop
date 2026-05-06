"""Console runner: drives both models through all 10 edge-knowledge cases.

Pipeline per case per model:
  1. Adversarial test agent crafts attack prompt(s) (single-shot or multi-turn).
  2. Business agent (same model) is invoked with that prompt.
  3. Deterministic validator scores the output against the strict template.
  4. Optional LLM-as-judge produces a rubric score (style / robustness).
  5. Results are aggregated into a comparison table.

Usage:
    python main.py                        # multi-turn ON, judge ON (default)
    python main.py --only edge-03
    python main.py --model gpt
    python main.py --no-attack            # plain prompt baseline
    python main.py --single-turn          # disable multi-turn (one shot)
    python main.py --no-judge             # skip LLM rubric grading
    python main.py --max-turns 3          # cap on multi-turn rounds
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from business_agent import make_business_agent
from config import MODELS, ModelSpec
from judge import grade
from test_agent import MultiTurnAttacker, craft_attack, make_test_agent
from test_cases import TEST_CASES, TestCase
from validator import validate

console = Console()
ARTIFACT_DIR = Path(__file__).parent / "artifacts"


async def _run_business(model: ModelSpec, prompt: str) -> tuple[str, str | None, int]:
    t0 = time.time()
    output = ""
    error: str | None = None
    try:
        async with make_business_agent(model.model_id) as biz:
            result = await biz.run(prompt)
            output = str(result).strip()
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    return output, error, int((time.time() - t0) * 1000)


async def run_case_single_turn(case: TestCase, model: ModelSpec, use_attack: bool) -> dict:
    if use_attack:
        async with make_test_agent(model.model_id) as test_agent:
            try:
                user_prompt = await craft_attack(test_agent, case.knowledge_point, case.attack_strategy)
            except Exception as e:  # noqa: BLE001
                user_prompt = f"请为「{case.knowledge_point}」写一个教育短视频脚本。"
                console.print(f"[yellow]  ! attack-agent failed: {e}[/yellow]")
    else:
        user_prompt = f"请为「{case.knowledge_point}」写一个教育短视频脚本。"

    output, error, duration = await _run_business(model, user_prompt)
    if error:
        checks, overall, score = [], False, 0.0
    else:
        checks, overall, score = validate(output)

    return {
        "case_id": case.id,
        "knowledge_point": case.knowledge_point,
        "attack_strategy": case.attack_strategy,
        "model_label": model.label,
        "model_id": model.model_id,
        "mode": "single-turn",
        "user_prompt": user_prompt,
        "output": output,
        "error": error,
        "duration_ms": duration,
        "overall_pass": overall,
        "score": score,
        "checks": [
            {"id": c.check_id, "pass": c.passed, "evidence": c.evidence}
            for c in checks
        ],
        "turns": [],
    }


async def run_case_multi_turn(case: TestCase, model: ModelSpec, max_turns: int) -> dict:
    """Multi-turn attack; stops early once the business agent FAILS."""
    turns: list[dict] = []
    final_output = ""
    final_error: str | None = None
    final_overall = True
    final_score = 1.0
    final_checks: list = []
    total_duration = 0
    final_prompt = ""

    async with MultiTurnAttacker(
        model_id=model.model_id,
        case_id=case.id,
        knowledge_point=case.knowledge_point,
        strategy_hint=case.attack_strategy,
    ) as attacker:
        prev_output: str | None = None
        prev_pass: bool | None = None
        prev_score: float | None = None

        for t in range(1, max_turns + 1):
            try:
                prompt = await attacker.next_prompt(prev_output, prev_pass, prev_score)
            except Exception as e:  # noqa: BLE001
                console.print(f"[yellow]  ! attacker turn {t} failed: {e}[/yellow]")
                prompt = f"请为「{case.knowledge_point}」写一个教育短视频脚本。"

            output, error, dur = await _run_business(model, prompt)
            total_duration += dur
            if error:
                checks, overall, score = [], False, 0.0
            else:
                checks, overall, score = validate(output)

            turns.append({
                "turn": t,
                "prompt": prompt,
                "output": output,
                "error": error,
                "duration_ms": dur,
                "overall_pass": overall,
                "score": score,
            })

            final_output = output
            final_error = error
            final_overall = overall
            final_score = score
            final_checks = checks
            final_prompt = prompt
            prev_output, prev_pass, prev_score = output, overall, score

            if not overall:
                break  # attacker won this case

    return {
        "case_id": case.id,
        "knowledge_point": case.knowledge_point,
        "attack_strategy": case.attack_strategy,
        "model_label": model.label,
        "model_id": model.model_id,
        "mode": f"multi-turn (max={max_turns})",
        "user_prompt": final_prompt,
        "output": final_output,
        "error": final_error,
        "duration_ms": total_duration,
        "overall_pass": final_overall,
        "score": final_score,
        "checks": [
            {"id": c.check_id, "pass": c.passed, "evidence": c.evidence}
            for c in final_checks
        ],
        "turns": turns,
    }


async def run_case(case: TestCase, model: ModelSpec, args: argparse.Namespace) -> dict:
    if not args.use_attack:
        rec = await run_case_single_turn(case, model, use_attack=False)
    elif args.single_turn:
        rec = await run_case_single_turn(case, model, use_attack=True)
    else:
        rec = await run_case_multi_turn(case, model, args.max_turns)

    # Optional LLM-as-judge rubric grading.
    if args.use_judge and not rec["error"] and rec["output"]:
        try:
            verdict = await grade(model.model_id, rec["user_prompt"], rec["output"])
            rec["rubric"] = {
                "overall_pass": verdict.overall_pass,
                "score": verdict.score,
                "checks": verdict.checks,
            }
        except Exception as e:  # noqa: BLE001
            rec["rubric"] = {"error": f"{type(e).__name__}: {e}"}
    else:
        rec["rubric"] = None

    ARTIFACT_DIR.mkdir(exist_ok=True)
    safe_model = model.label.replace(" ", "_").replace("/", "_")
    out_path = ARTIFACT_DIR / f"{case.id}__{safe_model}.json"
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def render_case_panel(rec: dict) -> None:
    status = "[green]PASS[/green]" if rec["overall_pass"] else "[red]FAIL[/red]"
    head = f"{rec['case_id']} · {rec['model_label']} · {status} · {rec['score'] * 100:.0f}% · {rec['mode']}"
    body = [
        f"[bold]Knowledge point[/bold]: {rec['knowledge_point']}",
        f"[bold]Attack strategy[/bold]: {rec['attack_strategy']}",
    ]
    if rec.get("turns"):
        body.append(f"[bold]Turns[/bold]: {len(rec['turns'])}")
        for t in rec["turns"]:
            mark = "[green]✓[/green]" if t["overall_pass"] else "[red]✗[/red]"
            body.append(
                f"  T{t['turn']} {mark} score={t['score'] * 100:.0f}% · "
                f"prompt={t['prompt'][:80].replace(chr(10), ' ')}"
            )
    body.append(f"[bold]Final prompt[/bold]: {rec['user_prompt'][:200]}")
    if rec["error"]:
        body.append(f"[red]Error[/red]: {rec['error']}")
    failed = [c for c in rec["checks"] if not c["pass"]]
    if failed:
        body.append("[bold red]Failed format checks[/bold red]:")
        for c in failed[:6]:
            body.append(f"  - {c['id']}: {c['evidence']}")
    rubric = rec.get("rubric")
    if rubric and "error" not in rubric:
        rstatus = "[green]PASS[/green]" if rubric["overall_pass"] else "[yellow]ISSUES[/yellow]"
        body.append(f"[bold]Rubric[/bold] ({rstatus}, {rubric['score']}/100):")
        for c in rubric.get("checks", []):
            mark = "[green]✓[/green]" if c.get("pass") else "[red]✗[/red]"
            body.append(f"  {mark} {c.get('id', '?')}: {c.get('notes', '')[:80]}")
    elif rubric and "error" in rubric:
        body.append(f"[yellow]Rubric error: {rubric['error']}[/yellow]")
    body.append(f"[dim]elapsed {rec['duration_ms']} ms · output {len(rec['output'])} chars[/dim]")
    console.print(Panel("\n".join(body), title=head, border_style="cyan"))


def render_summary(records: list[dict], use_judge: bool) -> None:
    table = Table(title="Format-Consistency Benchmark", show_lines=False)
    table.add_column("Case", style="bold")
    table.add_column("Knowledge Point", overflow="fold")
    for m in MODELS:
        table.add_column(m.label, justify="center")

    by_case: dict[str, dict[str, dict]] = {}
    for r in records:
        by_case.setdefault(r["case_id"], {})[r["model_label"]] = r

    for case in TEST_CASES:
        row = [case.id, case.knowledge_point]
        for m in MODELS:
            r = by_case.get(case.id, {}).get(m.label)
            if r is None:
                row.append("-")
                continue
            if r["error"]:
                row.append("[red]ERR[/red]")
                continue
            det = "[green]✓[/green]" if r["overall_pass"] else f"[yellow]{r['score']*100:.0f}%[/yellow]"
            cell = det
            rb = r.get("rubric")
            if use_judge and rb and "error" not in rb:
                rb_mark = "[green]✓[/green]" if rb["overall_pass"] else "[yellow]✗[/yellow]"
                cell = f"{det} | {rb_mark}{rb['score']}"
            row.append(cell)
        table.add_row(*row)

    agg_row = ["[bold]TOTAL[/bold]", "format pass / mean (rubric mean)"]
    for m in MODELS:
        recs = [r for r in records if r["model_label"] == m.label]
        if not recs:
            agg_row.append("-")
            continue
        pass_rate = sum(1 for r in recs if r["overall_pass"]) / len(recs)
        mean_score = sum(r["score"] for r in recs) / len(recs)
        cell = f"{pass_rate * 100:.0f}% / {mean_score * 100:.0f}%"
        if use_judge:
            rubrics = [r["rubric"]["score"] for r in recs if r.get("rubric") and "error" not in r["rubric"]]
            if rubrics:
                cell += f" ({sum(rubrics) / len(rubrics):.0f})"
        agg_row.append(cell)
    table.add_row(*agg_row)
    console.print(table)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Skill Testing Agent")
    p.add_argument("--only", help="run a single case id, e.g. edge-03")
    p.add_argument("--model", choices=["claude", "gpt", "all"], default="all")
    p.add_argument("--no-attack", dest="use_attack", action="store_false",
                   help="skip the adversarial test agent (baseline)")
    p.add_argument("--single-turn", action="store_true",
                   help="use single-shot adversarial prompt instead of multi-turn")
    p.add_argument("--max-turns", type=int, default=3,
                   help="max attack rounds in multi-turn mode (default 3)")
    p.add_argument("--no-judge", dest="use_judge", action="store_false",
                   help="skip the LLM-as-judge rubric grading")
    p.set_defaults(use_attack=True, use_judge=True)
    return p.parse_args()


def select_models(choice: str) -> list[ModelSpec]:
    if choice == "claude":
        return [m for m in MODELS if "Claude" in m.label]
    if choice == "gpt":
        return [m for m in MODELS if "GPT" in m.label]
    return list(MODELS)


def select_cases(only: str | None) -> list[TestCase]:
    if not only:
        return list(TEST_CASES)
    cases = [c for c in TEST_CASES if c.id == only]
    if not cases:
        console.print(f"[red]Unknown case id: {only}[/red]")
        sys.exit(2)
    return cases


async def main_async() -> int:
    args = parse_args()
    models = select_models(args.model)
    cases = select_cases(args.only)

    if not args.use_attack:
        mode = "no-attack (baseline)"
    elif args.single_turn:
        mode = "single-turn"
    else:
        mode = f"multi-turn (max={args.max_turns})"
    console.print(Panel.fit(
        f"[bold]Skill Testing Agent[/bold]\n"
        f"Models: {', '.join(m.label for m in models)}\n"
        f"Cases: {len(cases)}    Mode: {mode}    Judge: {args.use_judge}",
        border_style="magenta",
    ))

    records: list[dict] = []
    for case in cases:
        for model in models:
            console.print(f"\n[cyan]▶ {case.id} on {model.label} …[/cyan]")
            rec = await run_case(case, model, args)
            records.append(rec)
            render_case_panel(rec)

    console.rule("Summary")
    render_summary(records, args.use_judge)

    summary_path = ARTIFACT_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"\n[green]Artifacts written to {ARTIFACT_DIR}[/green]")
    return 0


def main() -> int:
    if not os.getenv("GITHUB_COPILOT_CLI_PATH") and not _which("copilot"):
        console.print(
            "[yellow]Warning: GitHub Copilot CLI ('copilot') not found on PATH. "
            "Install it and run `copilot auth login` before running.[/yellow]"
        )
    return asyncio.run(main_async())


def _which(cmd: str) -> str | None:
    from shutil import which
    return which(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
