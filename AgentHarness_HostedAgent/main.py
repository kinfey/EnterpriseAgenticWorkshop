"""Managed-style hosted agent: an adversarial Skill-Testing harness on Foundry.

Architecture
============
        ┌──────────────────┐    execute(name, input) -> str    ┌──────────┐
        │  Orchestrator    │ ──────────────────────────────────▶│  Hands   │
        │ (brain on        │                                    │ (sandbox)│
        │  Foundry chat)   │     emit_note / get_events         └──────────┘
        └─────────┬────────┘
                  │
                  ▼
        ┌──────────────────┐
        │   SessionStore   │  durable, append-only, external to context window
        └──────────────────┘

Hands registered in the sandbox pool (one disposable sandbox per call):

  - list_test_cases      : enumerate the 10 edge-knowledge cases
  - run_business_agent   : run business agent on a chosen Foundry deployment
                           (DeepSeek-V4-Flash or gpt-5.5)
  - validate_format      : deterministic format checker (no LLM)
  - judge_rubric         : LLM-as-judge rubric grader (Foundry)
  - craft_attack         : single-shot adversarial prompt
  - next_attack_prompt   : next-turn adversarial prompt with feedback loop
  - run_full_benchmark   : orchestrate all 10 cases × 2 models end-to-end

The orchestrator never sees raw secrets — Foundry creds live in the vault
and are injected by `DefaultAzureCredential` inside each hand at call time.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Annotated, Any

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # silently ignore when no .env (hosted mode)
except ImportError:  # python-dotenv is optional in hosted runtime
    pass

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity.aio import DefaultAzureCredential

from harness import SessionStore, SandboxPool, CredentialVault
from skills import (
    MODELS,
    PROJECT_ENDPOINT,
    TEST_CASES,
    find_case,
    get_model,
    validate,
)
from skills.business_agent import run_business
from skills.test_agent import craft_attack as _craft_attack, next_attack_prompt as _next_attack_prompt
from skills.judge import grade as _grade
from skills.config import ORCHESTRATOR_MODEL, SESSION_DIR

if not PROJECT_ENDPOINT:
    raise RuntimeError(
        "Set FOUNDRY_PROJECT_ENDPOINT in your .env (Microsoft Foundry project endpoint)."
    )

# Singletons outside the sandbox boundary --------------------------------------
SESSIONS = SessionStore(root_dir=SESSION_DIR)
VAULT = CredentialVault()
# Optional: any outbound creds the hands might need (none required for Foundry).
SANDBOX = SandboxPool(vault=VAULT)

CURRENT_SESSION_ID = SESSIONS.create_session(
    session_id=os.getenv("SESSION_ID") or str(uuid.uuid4())
)


# Helper: run async coroutine from sync sandbox-tool body. The host event loop
# is already running, so we can't asyncio.run; we use a fresh loop in a thread.
def _run_async(coro):
    import threading

    result: dict[str, Any] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            result["value"] = loop.run_until_complete(coro)
        except Exception as e:  # noqa: BLE001
            result["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


# ----- Hands (sandbox tools) --------------------------------------------------

def _hand_list_test_cases(_input: dict[str, Any], _vault: CredentialVault) -> str:
    return json.dumps(
        [{"id": c.id, "knowledge_point": c.knowledge_point, "attack_strategy": c.attack_strategy}
         for c in TEST_CASES],
        ensure_ascii=False,
    )


def _hand_run_business(input: dict[str, Any], _vault: CredentialVault) -> str:
    model = input.get("model")
    prompt = input.get("prompt")
    if not isinstance(model, str) or not isinstance(prompt, str):
        return "ERROR: 'model' and 'prompt' (string) are required."
    spec = get_model(model)
    output = _run_async(run_business(spec.deployment, prompt))
    return output


def _hand_validate_format(input: dict[str, Any], _vault: CredentialVault) -> str:
    output = input.get("output", "")
    if not isinstance(output, str):
        return "ERROR: 'output' must be a string."
    checks, overall, score = validate(output)
    return json.dumps(
        {
            "overall_pass": overall,
            "score": round(score, 4),
            "checks": [{"id": c.check_id, "pass": c.passed, "evidence": c.evidence} for c in checks],
        },
        ensure_ascii=False,
    )


def _hand_judge_rubric(input: dict[str, Any], _vault: CredentialVault) -> str:
    model = input.get("model")
    user_prompt = input.get("user_prompt", "")
    output = input.get("output", "")
    if not isinstance(model, str) or not user_prompt or not output:
        return "ERROR: 'model', 'user_prompt', 'output' are all required."
    spec = get_model(model)
    verdict = _run_async(_grade(spec.deployment, user_prompt, output))
    return json.dumps(
        {
            "overall_pass": verdict.overall_pass,
            "score": verdict.score,
            "checks": verdict.checks,
        },
        ensure_ascii=False,
    )


def _hand_craft_attack(input: dict[str, Any], _vault: CredentialVault) -> str:
    model = input.get("model")
    case_id = input.get("case_id")
    if not isinstance(model, str) or not isinstance(case_id, str):
        return "ERROR: 'model' and 'case_id' are required."
    case = find_case(case_id)
    if case is None:
        return f"ERROR: unknown case_id '{case_id}'."
    spec = get_model(model)
    prompt = _run_async(_craft_attack(spec.deployment, case.knowledge_point, case.attack_strategy))
    return prompt


def _hand_next_attack_prompt(input: dict[str, Any], _vault: CredentialVault) -> str:
    model = input.get("model")
    case_id = input.get("case_id")
    turn = int(input.get("turn", 1))
    prev_output = input.get("previous_output")
    prev_pass = input.get("previous_pass")
    prev_score = input.get("previous_score")
    if not isinstance(model, str) or not isinstance(case_id, str):
        return "ERROR: 'model' and 'case_id' are required."
    case = find_case(case_id)
    if case is None:
        return f"ERROR: unknown case_id '{case_id}'."
    spec = get_model(model)
    prompt = _run_async(_next_attack_prompt(
        spec.deployment, case.knowledge_point, case.attack_strategy,
        turn, prev_output, prev_pass, prev_score,
    ))
    return prompt


def _hand_run_full_benchmark(input: dict[str, Any], _vault: CredentialVault) -> str:
    """End-to-end: every case × every model with multi-turn attack + judge."""
    only = input.get("only")  # optional case_id filter
    max_turns = int(input.get("max_turns", 3))
    use_judge = bool(input.get("use_judge", True))
    judge_model = input.get("judge_model") or MODELS[0].label

    cases = TEST_CASES if not only else [c for c in TEST_CASES if c.id == only]
    if not cases:
        return f"ERROR: no cases matched only='{only}'."

    summary: list[dict[str, Any]] = []
    for case in cases:
        for model in MODELS:
            record = _run_one_case(case.id, model.label, max_turns, use_judge, judge_model)
            summary.append(record)

    return json.dumps({"runs": summary}, ensure_ascii=False)


def _run_one_case(case_id: str, model_label: str, max_turns: int,
                  use_judge: bool, judge_model: str) -> dict[str, Any]:
    case = find_case(case_id)
    spec = get_model(model_label)
    turns: list[dict[str, Any]] = []
    prev_output: str | None = None
    prev_pass: bool | None = None
    prev_score: float | None = None
    final_prompt = ""

    for t in range(1, max_turns + 1):
        prompt = _run_async(_next_attack_prompt(
            spec.deployment, case.knowledge_point, case.attack_strategy,
            t, prev_output, prev_pass, prev_score,
        ))
        try:
            output = _run_async(run_business(spec.deployment, prompt))
            err = None
        except Exception as e:  # noqa: BLE001
            output = ""
            err = f"{type(e).__name__}: {e}"
        if err:
            checks, overall, score = [], False, 0.0
        else:
            checks_list, overall, score = validate(output)
            checks = [{"id": c.check_id, "pass": c.passed, "evidence": c.evidence}
                      for c in checks_list]
        turns.append({
            "turn": t,
            "prompt": prompt,
            "output": output,
            "error": err,
            "overall_pass": overall,
            "score": round(score, 4),
        })
        SESSIONS.emit_event(CURRENT_SESSION_ID, "benchmark_turn", {
            "case_id": case.id, "model": model_label,
            "turn": t, "pass": overall, "score": score,
        })
        prev_output, prev_pass, prev_score = output, overall, score
        final_prompt = prompt
        if not overall:
            break

    rubric: dict[str, Any] | None = None
    if use_judge and prev_output:
        try:
            judge_spec = get_model(judge_model)
            verdict = _run_async(_grade(judge_spec.deployment, final_prompt, prev_output))
            rubric = {
                "overall_pass": verdict.overall_pass,
                "score": verdict.score,
                "checks": verdict.checks,
            }
        except Exception as e:  # noqa: BLE001
            rubric = {"error": f"{type(e).__name__}: {e}"}

    return {
        "case_id": case.id,
        "model": model_label,
        "knowledge_point": case.knowledge_point,
        "attack_strategy": case.attack_strategy,
        "final_pass": prev_pass if prev_pass is not None else False,
        "final_score": prev_score or 0.0,
        "turns": turns,
        "rubric": rubric,
    }


# Register hands ---------------------------------------------------------------
SANDBOX.register("list_test_cases", _hand_list_test_cases,
                 description="Return the catalogue of 10 edge-knowledge test cases.")
SANDBOX.register("run_business_agent", _hand_run_business,
                 description="Run business script-generator on Foundry (model={DeepSeek-V4-Flash|GPT-5.5}, prompt=str).")
SANDBOX.register("validate_format", _hand_validate_format,
                 description="Deterministic format check on a business-agent output (output=str).")
SANDBOX.register("judge_rubric", _hand_judge_rubric,
                 description="LLM-as-judge rubric grade (model=, user_prompt=, output=).")
SANDBOX.register("craft_attack", _hand_craft_attack,
                 description="Single-shot adversarial prompt for a case (model=, case_id=).")
SANDBOX.register("next_attack_prompt", _hand_next_attack_prompt,
                 description="Multi-turn next adversarial prompt (model, case_id, turn, previous_output, previous_pass, previous_score).")
SANDBOX.register("run_full_benchmark", _hand_run_full_benchmark,
                 description="Run all cases × all models end-to-end (only?, max_turns?, use_judge?, judge_model?).")


# ----- Tools the orchestrator brain sees --------------------------------------

def execute(
    name: Annotated[str, "One of: list_test_cases, run_business_agent, validate_format, judge_rubric, craft_attack, next_attack_prompt, run_full_benchmark"],
    input_json: Annotated[str, "JSON-encoded arguments for the tool. Use '{}' if none."],
) -> str:
    """Call any registered 'hand' in a fresh, cattle-style sandbox."""
    try:
        payload: dict[str, Any] = json.loads(input_json) if input_json else {}
        if not isinstance(payload, dict):
            return "ERROR: input_json must decode to a JSON object."
    except json.JSONDecodeError as e:
        return f"ERROR: invalid input_json: {e}"

    SESSIONS.emit_event(CURRENT_SESSION_ID, "tool_call",
                        {"name": name, "input": VAULT.redact(payload)})
    result = SANDBOX.execute(name, payload)
    SESSIONS.emit_event(CURRENT_SESSION_ID, "tool_result",
                        {"name": name, "output_preview": result[:1000]})
    return result


def list_tools() -> str:
    """Return the names + descriptions of every 'hand' you can call via execute()."""
    return json.dumps(SANDBOX.list_tools(), ensure_ascii=False)


def list_models() -> str:
    """Return the Microsoft Foundry deployments wired into this harness."""
    return json.dumps(
        [{"label": m.label, "deployment": m.deployment} for m in MODELS],
        ensure_ascii=False,
    )


def get_events(
    start: Annotated[int, "First event index (0-based)."] = 0,
    end: Annotated[int, "Exclusive end index; -1 means up to latest."] = -1,
) -> str:
    """Re-read any slice of the durable session log."""
    stop = None if end < 0 else end
    events = SESSIONS.get_events(CURRENT_SESSION_ID, start=start, end=stop)
    return json.dumps(
        [{"i": e.index, "type": e.type, "payload": e.payload, "ts": e.ts} for e in events],
        ensure_ascii=False,
    )


def emit_note(
    note: Annotated[str, "Free-form note to persist in the durable session log."],
) -> str:
    """Append a checkpoint note to the durable session log."""
    ev = SESSIONS.emit_event(CURRENT_SESSION_ID, "note", {"text": note})
    return f"ok (event #{ev.index})"


# ----- Orchestrator instructions ----------------------------------------------

INSTRUCTIONS = """You are the commander of an adversarial Skill-Testing experiment (a managed-style hosted agent).

Your environment
----------------
- All of your hands are invoked through `execute(name, input_json)`. Call `list_tools()`
  first for the catalogue, then `list_models()` to see the wired-in Microsoft Foundry
  deployments (DeepSeek-V4-Flash + GPT-5.5).
- Every `execute` runs in a one-shot sandbox; state does not persist across calls.
- Your durable memory is the session log, not the context window. Use `get_events(start, end)`
  to replay any slice; persist key findings with `emit_note(note)`.
- Any call whose result starts with `ERROR:` is a recoverable error — decide for yourself
  whether to retry with different arguments or switch to a different tool.

Typical experiment flow
-----------------------
1. List tools + list models; use `list_test_cases` to pull the 10 edge cases.
2. Pick a case_id + model:
   a. `craft_attack` to obtain the round-1 adversarial prompt;
   b. `run_business_agent` to make the business agent generate a script;
   c. `validate_format` for the deterministic format check;
   d. On PASS, call `next_attack_prompt(turn=2, previous_output=..., previous_pass=true, previous_score=...)`
      to let the attacker switch strategy and try again; typically capped at 3 turns.
   e. Once done, call `judge_rubric` to have another Foundry model grade against the 5-item rubric.
3. To run everything in one shot — every case × every model across user requests —
   call `run_full_benchmark`.
4. Persist each case's PASS/FAIL, score curve, and break-points via `emit_note`; end with
   a comparison conclusion.

Keep replies to the user concise — do not paste the entire script into the reply; let the
session log carry the details.
"""


async def main() -> None:
    async with DefaultAzureCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=ORCHESTRATOR_MODEL,
            credential=credential,
            allow_preview=True,
        )
        agent = Agent(
            client,
            instructions=INSTRUCTIONS,
            name="SkillTestingHarness",
            tools=[execute, list_tools, list_models, get_events, emit_note],
        )
        SESSIONS.emit_event(CURRENT_SESSION_ID, "session_start", {
            "agent": "SkillTestingHarness",
            "orchestrator_model": ORCHESTRATOR_MODEL,
            "models_under_test": [m.label for m in MODELS],
        })
        print("Skill-Testing Harness running on http://localhost:8088")
        print(f"Session id: {CURRENT_SESSION_ID}  (log dir: {SESSION_DIR})")
        print(f"Orchestrator: {ORCHESTRATOR_MODEL}")
        print(f"Models under test: {', '.join(m.label for m in MODELS)}")
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
