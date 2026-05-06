# OpenClaw Agent Harness · Self-Loop Testing Pipeline

> **Agent A writes the code → Agent B writes the tests → Agent C runs them in the OpenClaw sandbox and feeds back the results**
>
> Everything is built on the [OpenClaw](https://docs.openclaw.ai/) Docker Gateway and a multi-agent Workspace. The model is **Claude Opus 4.7**, served via GitHub Copilot's built-in provider.

---

## What it is

A small multi-agent pipeline brought up with Docker Compose. Three non-overlapping agents collaborate through a shared [OpenClaw Workspace](https://docs.openclaw.ai/concepts/agent-workspace) to complete a self-contained code → test → run → feedback loop:

| Agent | Role | Tools (allowlist) |
|-------|------|-------------------|
| **Agent A — Coder** 🧑‍💻 | Reads `SPEC.md` and writes the implementation to `solution.py`. If a failure report exists from the previous round, follow the "Suggested Fixes" section to repair it. | `read`, `write`, `edit` |
| **Agent B — Tester** 🧪 | Reads the spec and the implementation, then writes pytest cases to `test_solution.py`. | `read`, `write`, `edit` |
| **Agent C — Runner** 🏃 | Runs pytest inside the [OpenClaw Multi-Agent Sandbox](https://docs.openclaw.ai/tools/multi-agent-sandbox-tools) and writes the pass/fail results to `RUN_REPORT.md`. | `read`, `write`, **`exec`** |

Only Agent C has the `exec` tool, and `tools.exec.allowedPaths` strictly scopes execution to the single sub-directory `workspace/code/`.

Reference docs:

- Install: <https://docs.openclaw.ai/install/docker>
- Multi-agent sandbox tools: <https://docs.openclaw.ai/tools/multi-agent-sandbox-tools>
- Workspace concept: <https://docs.openclaw.ai/concepts/agent-workspace>
- GitHub Copilot provider: <https://docs.openclaw.ai/providers/github-copilot>

Inspired by: <https://github.com/kinfey/Multi-AI-Agents-Cloud-Native/tree/main/code/openclaw_security>

---

## Directory layout

```
OpenClaw_AgentHarness/
├── README.md                ← this file
├── docker-compose.yml       ← three containers: secrets-init + openclaw + harness
├── .env.example             ← copy to .env and fill in COPILOT_GITHUB_TOKEN
├── setup.sh                 ← one-shot bootstrap
├── config/
│   └── openclaw.json        ← three agents + GitHub Copilot provider + tool allowlists
├── security/
│   └── secrets-init.sh      ← rotates the gateway token on every boot
├── workspace/               ← OpenClaw Agent Workspace (mounted at /home/node/.openclaw/workspace inside the container)
│   ├── AGENTS.md
│   ├── IDENTITY.md
│   └── code/
│       └── SPEC.md          ← task specification (ships with a sample: balanced-brackets function)
└── harness/
    ├── Dockerfile
    ├── requirements.txt
    ├── openclaw_client.py   ← wrapper around the OpenClaw Gateway
    └── orchestrator.py      ← self-loop driver: A → B → C → feedback → A …
```

---

## A complete run

```
┌─────────────────────────────────────────────────────────────────────┐
│  iteration N                                                        │
│                                                                     │
│  orchestrator → POST /v1/chat/completions  (model=openclaw:coder)   │
│      ↳ Agent A reads SPEC.md (+ previous RUN_REPORT.md) → writes    │
│        solution.py                                                  │
│                                                                     │
│  orchestrator → POST /v1/chat/completions  (model=openclaw:tester)  │
│      ↳ Agent B reads SPEC.md + solution.py → writes                 │
│        test_solution.py                                             │
│                                                                     │
│  orchestrator → POST /v1/chat/completions  (model=openclaw:runner)  │
│      ↳ Agent C runs `pytest -v` inside the sandbox                  │
│        → writes RUN_REPORT.md (PASS / FAIL + Suggested Fixes)       │
│                                                                     │
│  orchestrator parses the report:                                    │
│      PASS → exit, status code 0                                     │
│      FAIL → enter iteration N+1 (Agent A reads the failure reason   │
│             and continues fixing)                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Quick start

### 1. Get a GitHub Copilot token

OpenClaw's [github-copilot provider](https://docs.openclaw.ai/providers/github-copilot) defaults to `github-copilot/claude-opus-4.7`. Obtain a GitHub token that has Copilot access:

```bash
# Easiest path if you already have gh CLI installed and signed in:
gh auth token
```

### 2. Configure .env

```bash
cd OpenClaw_AgentHarness
cp .env.example .env
# Edit .env and fill in:
#   COPILOT_GITHUB_TOKEN=<the token from the previous step>
```

### 3. Bootstrap

```bash
chmod +x setup.sh && ./setup.sh
```

### 4. Run one pipeline

```bash
docker compose up --abort-on-container-exit harness
```

Expected log:

```
━━━━━━ Iteration 1/3 ━━━━━━
[openclaw_client] → agent='coder' ...
[openclaw_client] ← agent='coder' (XXX chars)
[openclaw_client] → agent='tester' ...
[openclaw_client] ← agent='tester' (XXX chars)
[openclaw_client] → agent='runner' ...
[openclaw_client] ← agent='runner' (XXX chars)
>>> Iteration 1 status: PASS
✅ Tests passed — pipeline complete.
```

In the end, `workspace/code/` will contain:

- `solution.py` — Agent A's code
- `test_solution.py` — Agent B's pytest cases
- `RUN_REPORT.md` — Agent C's execution report

### 5. Try a different task

Edit [workspace/code/SPEC.md](workspace/code/SPEC.md), delete `solution.py / test_solution.py / RUN_REPORT.md`, and re-run step 4.

---

## Key design points

### Model — Claude Opus 4.7

In `config/openclaw.json`:

```json
"agents": {
  "defaults": {
    "model": {
      "primary": "github-copilot/claude-opus-4.7",
      "fallbacks": ["github-copilot/claude-sonnet-4.5"]
    }
  }
}
```

The provider-level configuration uses OpenClaw's built-in `github-copilot` plugin. Authentication comes from the `COPILOT_GITHUB_TOKEN` environment variable (also mirrored to `GH_TOKEN` to match the plugin's multi-source detection order).

### Tool allowlist — scoped to a single directory

```json
"tools": {
  "exec":  { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace/code"] },
  "read":  { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace"] },
  "write": { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace"] },
  "browser":   { "enabled": false },
  "web_search":{ "enabled": false },
  "web_fetch": { "enabled": false }
}
```

Each agent is then further restricted via `agents.list[].tools.allow / deny`, which guarantees that the Coder/Tester cannot acquire `exec`, and the Runner cannot acquire `edit` / `apply_patch`.

### Token rotation at startup

The `security/secrets-init.sh` container runs once before any other service. It generates a fresh 64-character random gateway token, writes it to the `tmpfs` volume `/run/secrets/gateway-token`, and uses `jq` to inject it into the `gateway.auth.token` field of `config/openclaw.json`. The harness container mounts the same tmpfs volume read-only to read the token; the OpenClaw container also mounts it read-only and is configured with `OPENCLAW_TOKEN_FILE=/run/secrets/gateway-token`.

### Workspace = single source of truth

The host `./workspace/` directory is bind-mounted into both:

- The OpenClaw container at `/home/node/.openclaw/workspace` (where the agents read and write)
- The harness container at `/workspace` (where the orchestrator reads and writes)

This means `orchestrator.py` can immediately verify, from the host's view, that an agent actually produced its output file.

---

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| `harness` is stuck at `Waiting for gateway` | Run `docker logs openclaw` and confirm the healthcheck returns 200. Usually `COPILOT_GITHUB_TOKEN` is missing or expired. |
| `agent 'coder' HTTP 401` | Token rotation is out of sync. Reset the tmpfs volume with `docker compose down -v && ./setup.sh`. |
| Runner reports `pytest not found` | The Runner prompt already falls back to `pip install pytest`. If it still fails, confirm `tools.exec.enabled=true` and that the Runner has not had `exec` denied in `agents.list[]`. |
| Model not found | Confirm your GitHub account's Copilot subscription can access `claude-opus-4.7`. Otherwise change `agents.defaults.model.primary` to `github-copilot/claude-sonnet-4.5`, or run `docker compose exec openclaw openclaw models auth login --provider github-copilot --method device` once. |

---

## Shutdown

```bash
docker compose down -v   # -v also wipes the old token from the secrets volume
```
