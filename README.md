# Enterprise Agent Workshop

A hands-on workshop for engineering teams building **production-grade Agents inside the enterprise**. The samples in this repository walk you from a single-process skill-testing prototype, through multi-agent sandboxed pipelines, all the way to a hosted agent deployed on **Microsoft Foundry** with full Azure infrastructure.

Designed as a **one-day workshop** (≈ 6–8 hours of code + slides).

The workshop is organized around four recurring engineering concerns that every enterprise Agent program eventually has to solve:

| Concern | Where it shows up |
| --- | --- |
| **Skill definition & adversarial testing** | [`Skill_Testing_Agent/`](Skill_Testing_Agent/), [`AgentHarness_HostedAgent/`](AgentHarness_HostedAgent/) |
| **Sandboxed multi-agent orchestration** | [`OpenClaw_AgentHarness/`](OpenClaw_AgentHarness/), [`CodingAgent/`](CodingAgent/) |
| **Hosted-agent runtime & harness architecture (Brain / Hands / Session / Vault)** | [`AgentHarness_HostedAgent/`](AgentHarness_HostedAgent/) |
| **Cloud deployment to Microsoft Foundry** | [`skill-testing-harness-deploy/`](skill-testing-harness-deploy/) |

---

## Workshop Modules

### 1. `Skill_Testing_Agent/` — Adversarial Skill Testing 101

A minimal **Microsoft Agent Framework + GitHub Copilot SDK (Python)** project that tests a "business Agent" (an educational-video-script generator with a strict output template) against an **adversarial test Agent**. Two models — **Claude Opus 4.7** and **GPT-5.5** — are run in parallel and compared in the console.

Key concepts introduced:

- A **business Agent** with a deterministic output contract.
- An **adversarial test Agent** that crafts edge-case prompts (single-turn and multi-turn).
- A **deterministic validator** that checks the contract without an LLM.
- An **LLM-as-judge** rubric scoring the response on 5 dimensions.
- 10 curated *edge-knowledge* test cases.

Use this module to teach the team how to **define a skill, write its evaluation, and reason about model differences** before any infrastructure is involved.

### 2. `OpenClaw_AgentHarness/` — Multi-Agent Sandbox Pipeline

A Docker-Compose stack that introduces **[OpenClaw](https://docs.openclaw.ai/)** as the sandbox / gateway. Three least-privilege Agents collaborate in a shared workspace through a self-closing loop:

| Agent | Role | Tool allowlist |
| --- | --- | --- |
| **A — Coder** | Reads `SPEC.md`, writes `solution.py` | `read`, `write`, `edit` |
| **B — Tester** | Reads spec + solution, writes `test_solution.py` | `read`, `write`, `edit` |
| **C — Runner** | Runs `pytest` inside the sandbox, writes `RUN_REPORT.md` | `read`, `write`, **`exec`** |

Only Agent C holds the `exec` capability, and it is constrained via `tools.exec.allowedPaths` to a single subdirectory. Models are served through GitHub Copilot's built-in provider (Claude Opus 4.7).

This module teaches **tool allowlists, workspace isolation, gateway-based credential rotation, and self-correcting loops**.

### 3. `CodingAgent/` — Context Optimization & Error Correction

A more advanced OpenClaw pipeline focused on two production techniques:

1. **Context Optimization** — the `coder` Agent only loads Skill documents that the spec explicitly references via `@FILE.md` syntax (`workspace/skills/PYTHON_STYLE.md`, `ALGO_PATTERNS.md`, `ERROR_HANDLING.md`, `TESTING.md`). This keeps the prompt window lean and predictable.
2. **Error Correction** — a dedicated `diagnoser` Agent translates a captured Python traceback into a machine-readable **Patch Plan** (`DIAGNOSIS.md`), which the next iteration of the `coder` consumes.

Three roles — `coder`, `runner`, `diagnoser` — each with a strict tool allowlist, demonstrate how to **scale a self-healing coding loop** while still controlling token spend.

### 4. `AgentHarness_HostedAgent/` — Hosted Agent on Microsoft Foundry

The flagship module. It re-implements the Skill_Testing_Agent logic on top of a **managed-style hosted-agent harness** with the four-layer architecture:

```
       ┌──────────────────────────┐    execute(name,input) -> str       ┌──────────┐
       │   Orchestrator (Brain)   │ ───────────────────────────────────▶│  Hands   │
       │  Foundry hosted agent    │                                     │ (sandbox │
       │  (default: gpt-5.5)      │  emit_note / get_events / list_*    │  cattle) │
       └──────────────┬───────────┘                                     └──────────┘
                      │
                      ▼
       ┌──────────────────────────┐
       │       SessionStore       │  append-only log, decoupled from the brain context window
       └──────────────────────────┘
```

- **Brain** — A `SkillTestingHarness` agent running on `ResponsesHostServer` (Foundry hosted agent / Responses protocol). Exposes only 5 tools: `execute`, `list_tools`, `list_models`, `get_events`, `emit_note`.
- **Hands** — A `SandboxPool` of disposable, stateless workers. Seven hands are registered: `list_test_cases`, `run_business_agent`, `validate_format`, `judge_rubric`, `craft_attack`, `next_attack_prompt`, `run_full_benchmark`.
- **Session** — A file-level append-only log, decoupled from the brain's context window. Replayable via `wake(session_id)`.
- **Vault** — Credentials registered by logical name; sandboxed hands never see raw tokens.

The agents under test are two **Microsoft Foundry deployments**: `DeepSeek-V4-Flash` and `gpt-5.5`. The module ships a CLI runner ([`main_local.py`](AgentHarness_HostedAgent/main_local.py)) for fast model comparison and a hosted entrypoint ([`main.py`](AgentHarness_HostedAgent/main.py)) that speaks the Responses protocol.

This module teaches the **Brain / Hands / Session / Vault** separation and how to keep an enterprise harness debuggable, restartable, and credential-safe.

### 5. `skill-testing-harness-deploy/` — Deploy to Microsoft Foundry with `azd`

An [`azure.yaml`](skill-testing-harness-deploy/azure.yaml) + Bicep package that deploys the harness as a hosted agent (`host: azure.ai.agent`) using `azd up`. Demonstrates the full IaC story: container resources, startup command, remote build, and the `azure.ai.agents` extension.

### 6. `ppt/` — Workshop Slide Deck

The supporting slides delivered alongside the code, in suggested presentation order:

1. `00.enterprise-agent-evolution.pptx` — Why enterprise Agents, and how the field has evolved.
2. `01.openclaw-orchestration-deep-practice.pptx` — Deep-dive on OpenClaw multi-agent orchestration.
3. `02.token-economics-cost-control.pptx` — Token economics and cost control under real workloads.
4. `03.skill-definition-and-testing-standards.pptx` — Skill definition and adversarial-testing standards.
5. `04.coding-agent-token-report.pptx` — A token-usage post-mortem for the coding-agent loop.
6. `05.agent-harness-.pptx` — Walkthrough of the Brain / Hands / Session / Vault harness.

---

## Suggested Learning Path (one-day agenda)

A workable rhythm for a single day (≈ 6–8 hours):

| Block | Module | Slides |
| --- | --- | --- |
| **Morning · Concepts** | `Skill_Testing_Agent/` — vocabulary: business agent, adversarial agent, validator, judge, edge cases | `00`, `03` |
| **Late morning** | `OpenClaw_AgentHarness/` — sandbox, tool allowlists, gateway tokens, multi-agent file collaboration | `01` |
| **Afternoon · Practice** | `CodingAgent/` — context optimization (`@SKILL.md`) + diagnoser-driven error-correction loop | `02`, `04` |
| **Late afternoon** | `AgentHarness_HostedAgent/` — refactor into a hosted agent with Brain / Hands / Session / Vault on Microsoft Foundry | `05` |
| **Wrap-up** | `skill-testing-harness-deploy/` — ship it with `azd up` | — |

---

## Prerequisites

The whole workshop runs against the same baseline environment:

1. **Python 3.12+**
2. **GitHub Copilot** subscription (with seats enabled for the attendees' GitHub accounts).
3. **GitHub Copilot CLI** installed and signed in:
   ```bash
   # Install GitHub CLI first if you don't have it: https://cli.github.com/
   gh extension install github/gh-copilot
   # Or use the dedicated copilot CLI per https://github.com/github/copilot-cli
   copilot auth login
   ```
4. **Microsoft Foundry** project — an Azure subscription with a Foundry project endpoint, plus model deployments for `DeepSeek-V4-Flash` and `gpt-5.5` (names are configurable via env vars).

Additional per-module needs:

| Module | Extra requirements |
| --- | --- |
| `OpenClaw_AgentHarness/`, `CodingAgent/` | Docker + Docker Compose, `COPILOT_GITHUB_TOKEN` |
| `AgentHarness_HostedAgent/` | Azure CLI (`az login`) — `DefaultAzureCredential` is used |
| `skill-testing-harness-deploy/` | Azure Developer CLI (`azd`), Foundry quota in your subscription |

---

## Audience

Internal engineering teams who already ship software in production and now need to:

- Define **skills with testable contracts** instead of free-form prompts.
- Stand up **multi-agent pipelines** that respect the principle of least privilege.
- Reason about **token economics** and context windows under real workloads.
- Migrate from a laptop prototype to a **Foundry-hosted, IaC-deployed** agent runtime.

> The materials are intentionally code-first. Every concept introduced in the slide deck has a runnable counterpart in one of the directories above.

> 中文版 README 见 [README.zh.md](README.zh.md)。
