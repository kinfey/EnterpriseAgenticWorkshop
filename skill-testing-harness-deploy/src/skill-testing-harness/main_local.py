"""Local console runner — same harness, no hosted-agent server.

Drives every test case through both Microsoft Foundry deployments
(DeepSeek-V4-Flash + GPT-5.5) using the same skills/* the hosted agent uses,
and prints a Rich comparison table.

Usage:
    python main_local.py                   # full multi-turn + judge
    python main_local.py --only edge-03
    python main_local.py --model gpt
    python main_local.py --no-attack
    python main_local.py --single-turn
    python main_local.py --no-judge
    python main_local.py --max-turns 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skills import MODELS, TEST_CASES, find_case, get_model, validate
from skills.business_agent import run_business
from skills.judge import grade
from skills.test_agent import craft_attack, next_attack_prompt

console = Console()
ARTIFACT_DIR = Path(__file__).parent / "artifacts"


async def _run_business(model_label: str, prompt: str) -> tuple[str, str | None, int]:
    spec = get_model(model_label)
    t0 = time.time()
    out = ""
    err: str | None = None
    try:
        out = await run_business(spec.deployment, prompt)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    return out, err, int((time.time() - t0) * 1000)


async def run_case_single_turn(case_id: str, model_label: str, use_attack: bool) -> dict:
    case = find_case(case_id)
    spec = get_model(model_label)
    if use_attack:
        try:
            user_prompt = await craft_attack(spec.deployment, case.knowledge_point, case.attack_strategy)
        except Exception as e:  # noqa: BLE001
            user_prompt = f"请为「{case.knowledge_point}」写一个教育短视频脚本。"
            console.print(f"[yellow]  ! attack agent failed: {e}[/yellow]")
    else:
        user_prompt = f"请为「{case.knowledge_point}」写一个教育短视频脚本。"

    out, err, dur = await _run_business(model_label, user_prompt)
    if err:
        checks, overall, score = [], False, 0.0
    else:
        checks, overall, score = validate(out)
    return _format_record(case, spec, "single-turn", user_prompt, out, err, dur, overall, score, checks, [])


async def run_case_multi_turn(case_id: str, model_label: str, max_turns: int) -> dict:
    case = find_case(case_id)
    spec = get_model(model_label)
    turns: list[dict] = []
    final_out = ""
    final_err: str | None = None
    final_overall = True
    final_score = 1.0
    final_checks: list = []
    total_dur = 0
    final_prompt = ""
    prev_out: str | None = None
    prev_pass: bool | None = None
    prev_score: float | None = None

    for t in range(1, max_turns + 1):
        try:
            prompt = await next_attack_prompt(
                spec.deployment, case.knowledge_point, case.attack_strategy,
                t, prev_out, prev_pass, prev_score,
            )
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]  ! attacker turn {t} failed: {e}[/yellow]")
            prompt = f"请为「{case.knowledge_point}」写一个教育短视频脚本。"

        out, err, dur = await _run_business(model_label, prompt)
        total_dur += dur
        if err:
            checks, overall, score = [], False, 0.0
        else:
            checks, overall, score = validate(out)
        turns.append({"turn": t, "prompt": prompt, "output": out, "error": err,
                      "duration_ms": dur, "overall_pass": overall, "score": score})
        final_out, final_err, final_overall, final_score, final_checks = (
            out, err, overall, score, checks)
        final_prompt = prompt
        prev_out, prev_pass, prev_score = out, overall, score
        if not overall:
            break

    return _format_record(case, spec, f"multi-turn (max={max_turns})", final_prompt,
                          final_out, final_err, total_dur, final_overall, final_score,
                          final_checks, turns)


def _format_record(case, spec, mode, prompt, out, err, dur, overall, score, checks, turns):
    return {
        "case_id": case.id,
        "knowledge_point": case.knowledge_point,
        "attack_strategy": case.attack_strategy,
        "model_label": spec.label,
        "deployment": spec.deployment,
        "mode": mode,
        "user_prompt": prompt,
        "output": out,
        "error": err,
        "duration_ms": dur,
        "overall_pass": overall,
        "score": score,
        "checks": [{"id": c.check_id, "pass": c.passed, "evidence": c.evidence} for c in checks],
        "turns": turns,
    }


async def run_case(case_id: str, model_label: str, args) -> dict:
    if not args.use_attack:
        rec = await run_case_single_turn(case_id, model_label, use_attack=False)
    elif args.single_turn:
        rec = await run_case_single_turn(case_id, model_label, use_attack=True)
    else:
        rec = await run_case_multi_turn(case_id, model_label, args.max_turns)

    if args.use_judge and not rec["error"] and rec["output"]:
        try:
            spec = get_model(model_label)
            verdict = await grade(spec.deployment, rec["user_prompt"], rec["output"])
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
    safe_model = rec["model_label"].replace(" ", "_").replace("/", "_")
    (ARTIFACT_DIR / f"{rec['case_id']}__{safe_model}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def render_case_panel(rec: dict) -> None:
    status = "[green]PASS[/green]" if rec["overall_pass"] else "[red]FAIL[/red]"
    head = f"{rec['case_id']} · {rec['model_label']} · {status} · {rec['score']*100:.0f}% · {rec['mode']}"
    body = [f"[bold]Knowledge point[/bold]: {rec['knowledge_point']}",
            f"[bold]Attack strategy[/bold]: {rec['attack_strategy']}"]
    if rec.get("turns"):
        body.append(f"[bold]Turns[/bold]: {len(rec['turns'])}")
        for t in rec["turns"]:
            mark = "[green]✓[/green]" if t["overall_pass"] else "[red]✗[/red]"
            body.append(f"  T{t['turn']} {mark} score={t['score']*100:.0f}% · "
                        f"prompt={t['prompt'][:80].replace(chr(10), ' ')}")
    body.append(f"[bold]Final prompt[/bold]: {rec['user_prompt'][:200]}")
    if rec["error"]:
        body.append(f"[red]Error[/red]: {rec['error']}")
    failed = [c for c in rec["checks"] if not c["pass"]]
    if failed:
        body.append("[bold red]Failed format checks[/bold red]:")
        for c in failed[:6]:
            body.append(f"  - {c['id']}: {c['evidence']}")
    rb = rec.get("rubric")
    if rb and "error" not in rb:
        rstatus = "[green]PASS[/green]" if rb["overall_pass"] else "[yellow]ISSUES[/yellow]"
        body.append(f"[bold]Rubric[/bold] ({rstatus}, {rb['score']}/100):")
        for c in rb.get("checks", []):
            mark = "[green]✓[/green]" if c.get("pass") else "[red]✗[/red]"
            body.append(f"  {mark} {c.get('id','?')}: {c.get('notes','')[:80]}")
    elif rb and "error" in rb:
        body.append(f"[yellow]Rubric error: {rb['error']}[/yellow]")
    body.append(f"[dim]Duration {rec['duration_ms']} ms · Output {len(rec['output'])} chars[/dim]")
    console.print(Panel("\n".join(body), title=head, border_style="cyan"))


def render_summary(records: list[dict], use_judge: bool) -> None:
    table = Table(title="Foundry Format-Consistency Benchmark", show_lines=False)
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

    agg = ["[bold]TOTAL[/bold]", "format pass / mean (rubric mean)"]
    for m in MODELS:
        recs = [r for r in records if r["model_label"] == m.label]
        if not recs:
            agg.append("-")
            continue
        pass_rate = sum(1 for r in recs if r["overall_pass"]) / len(recs)
        mean_score = sum(r["score"] for r in recs) / len(recs)
        cell = f"{pass_rate*100:.0f}% / {mean_score*100:.0f}%"
        if use_judge:
            rubrics = [r["rubric"]["score"] for r in recs
                       if r.get("rubric") and "error" not in r["rubric"]]
            if rubrics:
                cell += f" ({sum(rubrics)/len(rubrics):.0f})"
        agg.append(cell)
    table.add_row(*agg)
    console.print(table)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AgentHarness_HostedAgent local CLI")
    p.add_argument("--only", help="run a single case id, e.g. edge-03")
    p.add_argument("--model", choices=["deepseek", "gpt", "all"], default="all")
    p.add_argument("--no-attack", dest="use_attack", action="store_false")
    p.add_argument("--single-turn", action="store_true")
    p.add_argument("--max-turns", type=int, default=3)
    p.add_argument("--no-judge", dest="use_judge", action="store_false")
    p.set_defaults(use_attack=True, use_judge=True)
    return p.parse_args()


async def amain() -> int:
    args = parse_args()
    cases = TEST_CASES if not args.only else [c for c in TEST_CASES if c.id == args.only]
    if not cases:
        console.print(f"[red]No cases match --only={args.only}[/red]")
        return 2
    if args.model == "deepseek":
        models = [m for m in MODELS if "deepseek" in m.label.lower()]
    elif args.model == "gpt":
        models = [m for m in MODELS if "gpt" in m.label.lower()]
    else:
        models = MODELS

    records: list[dict] = []
    for case in cases:
        for m in models:
            console.print(f"[cyan]→ {case.id} · {m.label}[/cyan]")
            rec = await run_case(case.id, m.label, args)
            records.append(rec)
            render_case_panel(rec)

    render_summary(records, use_judge=args.use_judge)
    summary_path = ARTIFACT_DIR / "summary.json"
    summary_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[dim]summary -> {summary_path}[/dim]")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
