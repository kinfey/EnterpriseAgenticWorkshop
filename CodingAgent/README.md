# CodingAgent · Copilot Code-Generation Agent on the OpenClaw Framework

> Drive a **code-generation Agent** inside the [OpenClaw](https://docs.openclaw.ai/) sandbox using GitHub Copilot (default `claude-opus-4.7`). Two core techniques:
>
> 1. **Context Optimization** — the Coder Agent uses `@FILE.md` references to pull in Skill specs from `workspace/skills/`, injecting only what is actually needed into the context.
> 2. **Error Correction** — the Runner captures the full Python Traceback, and the Diagnoser Agent specializes in turning that Traceback into an actionable `Patch Plan` that gets fed back to the Coder for the next repair cycle.
>
> Inspired by, and scaffolded from, the sibling project [`OpenClaw_AgentHarness`](../OpenClaw_AgentHarness/README.md).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  iteration N                                                             │
│                                                                          │
│  Coder      read SPEC.md → parse @SKILL.md refs → load only those Skills │
│             read DIAGNOSIS.md (if present) → write solution.py           │
│                                                                          │
│  Runner     run solution / pytest / smoke_test inside OpenClaw sandbox   │
│             capture Traceback verbatim → write RUN_LOG.md                │
│                                                                          │
│  if PASS → exit 0                                                        │
│  if FAIL → Diagnoser parses Traceback → writes DIAGNOSIS.md (Patch Plan) │
│            enter iteration N+1 (Coder reads Patch Plan and fixes)        │
└──────────────────────────────────────────────────────────────────────────┘
```

| Agent       | Emoji | Responsibility                                                     | Tool allow-list         |
|-------------|------|---------------------------------------------------------------------|-------------------------|
| `coder`     | 🧑‍💻   | Read SPEC + referenced Skills + DIAGNOSIS, write `solution.py`      | `read`, `write`, `edit` |
| `runner`    | 🏃   | Execute the code, write the full Traceback into `RUN_LOG.md`         | `read`, `write`, `exec` |
| `diagnoser` | 🩺   | Translate the Traceback into a `Patch Plan` (`DIAGNOSIS.md`)         | `read`, `write`         |

Only `runner` has `exec`, and `tools.exec.allowedPaths` only whitelists `workspace/code/`.

---

## Directory Layout

```
CodingAgent/
├── README.md                ← this file
├── docker-compose.yml       ← secrets-init + openclaw + harness
├── .env.example             ← copy to .env, then fill in COPILOT_GITHUB_TOKEN
├── setup.sh                 ← one-shot bootstrap
├── config/
│   └── openclaw.json        ← three agent definitions + Copilot Provider
├── security/
│   └── secrets-init.sh      ← startup-time Gateway Token rotation
├── harness/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── openclaw_client.py   ← invokes the OpenClaw CLI via docker exec
│   └── orchestrator.py      ← self-loop driver (Coder → Runner → Diagnoser)
└── workspace/
    ├── AGENTS.md
    ├── skills/              ← Skill docs used by Context Optimization
    │   ├── PYTHON_STYLE.md
    │   ├── ALGO_PATTERNS.md
    │   ├── ERROR_HANDLING.md
    │   └── TESTING.md
    └── code/
        ├── SPEC.md          ← task definition (with @SKILL.md references)
        ├── solution.py      ← produced by the Coder
        ├── RUN_LOG.md       ← produced by the Runner (full Traceback)
        └── DIAGNOSIS.md     ← produced by the Diagnoser (Patch Plan)
```

---

## Technique 1 · Context Optimization (Skill `@` references)

The "Required Skills" section inside `workspace/code/SPEC.md`:

```markdown
- @PYTHON_STYLE.md
- @ALGO_PATTERNS.md
- @ERROR_HANDLING.md
- @TESTING.md
```

The orchestrator parses these references with the regex `r"@([A-Za-z0-9_\-]+\.md)"`, verifies that each one actually exists under `workspace/skills/`, and then injects the resulting list into the `# Skill References` section of the Coder Prompt. The Coder system prompt has a hard rule: **read only the listed Skill files; do not load anything else**.

To add or replace a skill, just drop a new Markdown file under `workspace/skills/` and reference it from `SPEC.md` with `@xxx.md`.

---

## Technique 2 · Error Correction (Traceback feedback loop)

The Runner system prompt requires `RUN_LOG.md` to contain:

```
## Result          PASS / FAIL
## Command         <command run>
## Exit Code       <integer>
## Stdout          ```<verbatim>```
## Stderr / Traceback   ```<verbatim Python traceback>```
```

The Diagnoser is only invoked on `FAIL`, and emits a `DIAGNOSIS.md` with a fixed structure:

```
## Failure Signature   <ExceptionType: message>
## Root Cause          <2-4 sentences>
## Affected Lines      <file:line — code>
## Patch Plan          - imperative bullet 1
                       - imperative bullet 2
## Regression Risk     <one-liner>
```

When the next iteration starts, the orchestrator explicitly tells the Coder in its prompt: "read DIAGNOSIS.md and apply each item in the Patch Plan." This turns "let Copilot stare at a Traceback and figure something out" from an ad-hoc one-shot into a **structured repair contract**.

---

## How to Run

This project has **two entry points**:

- **A. Run from the command line** (good for first-time validation, CI, or batch-running after editing SPEC.md)
- **B. Drive it through OpenCode** (good for using it as a tool from inside a chat — see [Using it from OpenCode](#using-it-from-opencode-mcp-integration) below)

Both share the environment setup in [Steps 0–3](#step-0--prerequisites).

---

### Step 0 · Prerequisites

| Dependency | Purpose | Verification command |
|------|------|---------|
| Docker Desktop ≥ 24 (with compose v2) | Run the secrets-init / openclaw / harness containers | `docker compose version` |
| GitHub CLI (optional) | One-line way to grab a Copilot token | `gh auth status` |
| GitHub account with a Copilot subscription | Calls `claude-opus-4.7` | — |
| Free port 18790 | Public port of the OpenClaw Gateway (offset from OpenClaw_AgentHarness) | `lsof -i :18790` |

> **macOS note**: Docker Desktop must be running, and you need to enable **"Allow the default Docker socket to be used"** in Settings → Advanced, because the harness container mounts `/var/run/docker.sock`.

---

### Step 1 · Get a Copilot token and write it into .env

```bash
cd /Users/lokinfey/Downloads/Samples/CodingAgent
cp .env.example .env
# Pick either way to write the token:
echo "COPILOT_GITHUB_TOKEN=$(gh auth token)" >> .env
# Or open .env in an editor and replace ghu_replace_me with your token
```

`.env` needs at least these two entries:

```bash
COPILOT_GITHUB_TOKEN=ghu_xxxxxxxxxxxxxxxxxxxxxxxxxxx
MAX_ITERATIONS=4
```

---

### Step 2 · One-shot bootstrap (only needed once)

```bash
chmod +x setup.sh security/secrets-init.sh
./setup.sh
```

`setup.sh` will:

1. Verify that docker / compose are available;
2. Pull the three base images `alpine:3.19`, `python:3.12-slim`, `ghcr.io/openclaw/openclaw:latest`;
3. Run `docker compose build harness` to build the harness image;
4. Set permissions of `config/` and `workspace/` to 700.

When it finishes successfully it prints `Done.`.

---

### Step 3 · Prepare a task

The bundled [workspace/code/SPEC.md](workspace/code/SPEC.md) is a "balanced parentheses" sample task that references 4 Skills. You can run it as-is to validate the whole pipeline.

To switch tasks:

```bash
# 1) Edit the task definition (you can use @FILE.md under ## Required Skills
#    to reference skills under workspace/skills/)
$EDITOR workspace/code/SPEC.md

# 2) Wipe the previous artifacts to avoid stale-result confusion
rm -f workspace/code/solution.py workspace/code/RUN_LOG.md \
      workspace/code/DIAGNOSIS.md workspace/code/smoke_test.py \
      workspace/code/test_solution.py
```

> Want to add a new skill? Drop a `MY_SKILL.md` into [workspace/skills/](workspace/skills) and add `- @MY_SKILL.md` to SPEC.md.

---

### Entry point A · Command line

```bash
# Foreground run (recommended — full logs, exits automatically when done)
docker compose up --abort-on-container-exit harness

# Or run the gateway in the background and run harness once
docker compose up -d openclaw
docker compose run --rm harness
```

**Expected logs**:

```
========================================================================
  CodingAgent — OpenClaw + Copilot self-correcting code generator
  Workspace: /workspace
  Max iterations: 4
========================================================================
[orchestrator] Skill references in SPEC.md: ['PYTHON_STYLE.md', 'ALGO_PATTERNS.md', 'ERROR_HANDLING.md', 'TESTING.md']
[openclaw_client] Gateway ready ✓

━━━━━━ Iteration 1/4 ━━━━━━
[openclaw_client] → agent='coder'    ...
[coder]    reply: {"status":"done","file":"solution.py","skills_used":[...]}
[openclaw_client] → agent='runner'   ...
[runner]   reply: {"status":"FAIL","exit_code":1,"log":"RUN_LOG.md"}
>>> Iteration 1 status: FAIL
[openclaw_client] → agent='diagnoser' ...
[diagnoser] reply: {"status":"diagnosed","exception":"AssertionError: ...","file":"DIAGNOSIS.md"}

━━━━━━ Iteration 2/4 ━━━━━━
[coder]    reply: {"status":"done", ...}
[runner]   reply: {"status":"PASS","exit_code":0,"log":"RUN_LOG.md"}
>>> Iteration 2 status: PASS
✅ Solution passed — pipeline complete.
```

**Exit codes** of the harness process: `0 = PASS`, `1 = exhausted MAX_ITERATIONS while still failing`, `2 = SPEC.md missing`.

**Artifacts** (under `workspace/code/` on the host — you can `cat` them or open them in an editor directly):

| File | Source | Meaning |
|------|------|------|
| `solution.py`    | Coder    | The final code |
| `RUN_LOG.md`     | Runner   | `## Result` `## Stdout` `## Stderr / Traceback` |
| `DIAGNOSIS.md`   | Diagnoser | Only present if some iteration failed; cleared once the final iteration passes |

**Tuning**:

```bash
# Override max iterations on the fly (you can also bake it into MAX_ITERATIONS in .env)
MAX_ITERATIONS=6 docker compose up --abort-on-container-exit harness

# Tail OpenClaw gateway logs separately
docker logs -f codingagent-openclaw
```

---

### Entry point B · Drive it from OpenCode

See the [Using it from OpenCode (MCP integration)](#using-it-from-opencode-mcp-integration) section below for full details. Shortest path:

```bash
pip install -r mcp/requirements.txt   # install the MCP SDK
opencode                              # start OpenCode from the CodingAgent/ directory
# Then inside OpenCode:
#   /agent codingagent
#   write an LRU cache, follow @PYTHON_STYLE.md @ALGO_PATTERNS.md
```

OpenCode will pick up [opencode.json](opencode.json) automatically and launch the stdio MCP server [mcp/mcp_server.py](mcp/mcp_server.py); the server runs `docker compose up harness` on the host to drive the pipeline once and returns the result back to OpenCode.

---

### Step 4 · Re-run / switch task

```bash
# Edit SPEC.md, wipe artifacts, run again
$EDITOR workspace/code/SPEC.md
rm -f workspace/code/solution.py workspace/code/RUN_LOG.md workspace/code/DIAGNOSIS.md
docker compose up --abort-on-container-exit harness
```

> Don't want to wipe artifacts manually? The orchestrator already deletes `solution.py` and `RUN_LOG.md` at the start of each iteration; `DIAGNOSIS.md` is only deleted on iteration 1, and is preserved afterwards as feedback. Manual cleanup is just a safety net so you don't read stale artifacts from a previous task.

---

## Key Design Points

### Models go through Copilot's built-in Provider

`config/openclaw.json`:

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

Authentication comes from `COPILOT_GITHUB_TOKEN` (mirrored to `GH_TOKEN` to match the plugin's multi-source detection order).

### Tool allow-list — directory-precise

```json
"tools": {
  "exec":  { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace/code"] },
  "read":  { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace"] },
  "write": { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace"] }
}
```

Each agent further trims this with `agents.list[].tools.deny` so that Coder/Diagnoser cannot get `exec`, and Runner cannot get `edit`.

### Startup-time token rotation

`security/secrets-init.sh` runs before all other services. It generates a fresh Gateway Token, writes it into the tmpfs volume `/run/secrets/gateway-token`, and uses `jq` to inject it into `gateway.auth.token` and `gateway.remote.token` in `config/openclaw.json`.

### Workspace = single source of truth

The host's `./workspace/` is mounted into both:

- The OpenClaw container at `/home/node/.openclaw/workspace` (Agents read/write)
- The Harness container at `/workspace` (the orchestrator reads/writes)

So once an Agent writes a file, `orchestrator.py` can immediately validate the result through the host view.

---

## Troubleshooting

| Symptom | Investigation |
|------|------|
| `harness` is stuck on `Waiting for gateway` | `docker logs codingagent-openclaw` — usually `COPILOT_GITHUB_TOKEN` is empty or expired |
| `Copilot token exchange failed: HTTP 403` / `model fallback decision: candidate_failed reason=auth` | A PAT straight from `gh auth token` typically does not have the Copilot OAuth scope, so the gateway's live token exchange gets rejected by GitHub. This project's [`security/secrets-init.sh`](security/secrets-init.sh) follows [docs.openclaw.ai → Non-interactive onboarding](https://docs.openclaw.ai/providers/github-copilot#copilot-proxy-plugin-copilot-proxy) and writes the token directly into `config/agents/<id>/agent/auth-profiles.json` so the gateway reads a stored profile (no exchange). If you still get 403, the token itself has no Copilot subscription; switch to device flow:<br/><br/>**One-shot device-flow bootstrap** (see [Copilot credential repair](#copilot-credential-repair) below): `docker compose down -v && docker compose up -d openclaw && docker exec -it codingagent-openclaw node /app/openclaw.mjs models auth login-github-copilot` |
| The Coder references a Skill that doesn't exist | The orchestrator prints `Skill references in SPEC.md` in its startup logs; non-existent `@FILE.md` entries are dropped silently |
| The Runner reports `pytest not found` | The system prompt already includes `pip install --quiet pytest` as a fallback; if that still fails, confirm `tools.exec.enabled=true` |
| The Diagnoser doesn't write DIAGNOSIS.md | The orchestrator prints `⚠️ Diagnoser did not write DIAGNOSIS.md`; the next iteration's Coder will fly blind. Consider raising `MAX_ITERATIONS` |
| The model doesn't exist | `docker compose exec codingagent-openclaw openclaw models auth login --provider github-copilot --method device`, or change the primary to `github-copilot/claude-sonnet-4.5` |

---

## Copilot Credential Repair

If the gateway keeps reporting `Copilot token exchange failed: HTTP 403`, the `COPILOT_GITHUB_TOKEN` in your `.env` does not have the Copilot OAuth scope (a token from `gh auth token` is exactly this case by default). Pick one of the two repair paths:

### Option A · Reuse the credentials already logged in by the sibling OpenClaw_AgentHarness

If you previously completed device-flow login in [`../OpenClaw_AgentHarness`](../OpenClaw_AgentHarness/README.md), those credentials can be reused directly:

```bash
cd /Users/lokinfey/Downloads/Samples

# 1) Copy the exchanged Copilot API token cache
mkdir -p CodingAgent/config/credentials
cp OpenClaw_AgentHarness/config/credentials/github-copilot.token.json \
   CodingAgent/config/credentials/

# 2) Copy the auth-profile to all three agents
for AGENT in coder runner diagnoser; do
  mkdir -p CodingAgent/config/agents/$AGENT/agent
  cp OpenClaw_AgentHarness/config/agents/coder/agent/auth-profiles.json \
     CodingAgent/config/agents/$AGENT/agent/
  cp OpenClaw_AgentHarness/config/agents/coder/agent/auth-state.json \
     CodingAgent/config/agents/$AGENT/agent/ 2>/dev/null || true
done

# 3) Sync .env so the next start-up doesn't have secrets-init overwrite this with the old token
WORKING_TOKEN=$(python3 -c "import json; print(json.load(open('OpenClaw_AgentHarness/config/agents/coder/agent/auth-profiles.json'))['profiles']['github-copilot:github']['token'])")
sed -i.bak "s|^COPILOT_GITHUB_TOKEN=.*|COPILOT_GITHUB_TOKEN=$WORKING_TOKEN|" CodingAgent/.env

cd CodingAgent
docker compose down -v
docker compose up --abort-on-container-exit harness
```

### Option B · Run a one-time device-flow login inside the CodingAgent container (recommended, self-contained)

```bash
cd /Users/lokinfey/Downloads/Samples/CodingAgent

# 1) Clean start, skip the secrets-init seeding (keep the .env token as ghu_replace_me)
docker compose down -v
sed -i.bak 's|^COPILOT_GITHUB_TOKEN=.*|COPILOT_GITHUB_TOKEN=ghu_replace_me|' .env
docker compose up -d openclaw

# 2) Interactive login from inside the container (must use -it)
docker exec -it codingagent-openclaw \
  node /app/openclaw.mjs models auth login-github-copilot
# → open the printed URL in a browser, enter the 8-digit code → wait for OK in the terminal

# 3) Reuse main's auth-profile for all three agents
for AGENT in coder runner diagnoser; do
  mkdir -p config/agents/$AGENT/agent
  cp config/agents/main/agent/auth-profiles.json \
     config/agents/$AGENT/agent/
done

# 4) Sync .env to the new token (so secrets-init uses a consistent value on restart)
NEW_TOKEN=$(python3 -c "import json; print(json.load(open('config/agents/main/agent/auth-profiles.json'))['profiles']['github-copilot:github']['token'])")
sed -i.bak "s|^COPILOT_GITHUB_TOKEN=.*|COPILOT_GITHUB_TOKEN=$NEW_TOKEN|" .env

# 5) Run the pipeline
docker compose up --abort-on-container-exit harness
```

The `ghu_...` token obtained via device flow already carries the Copilot scope, so the gateway's `Copilot token exchange` step succeeds and caches the short-lived Copilot API token in `config/credentials/github-copilot.token.json`. When the cache expires, the gateway re-exchanges using the stored `ghu_...` automatically — you don't have to do anything.

---

## Using it from OpenCode (MCP integration)

This repo ships a stdio MCP server that wraps the whole pipeline as a tool callable directly from [OpenCode](https://opencode.ai).

### 1. Install the MCP SDK

```bash
pip install -r mcp/requirements.txt
```

### 2. Register it with OpenCode

The repo-root [opencode.json](opencode.json) already declares the server plus a `codingagent` mode agent:

```jsonc
{
  "mcp": {
    "codingagent": {
      "type": "local",
      "command": ["python", "${workspaceFolder}/mcp/mcp_server.py"],
      "environment": { "CODINGAGENT_ROOT": "${workspaceFolder}" }
    }
  },
  "agent": {
    "codingagent": { "tools": { "codingagent*": true }, ... }
  }
}
```

Keep this file under `CodingAgent/` and start OpenCode from that directory — it will pick up the file automatically. Alternatively, copy the `mcp` block into `~/.config/opencode/config.json` to register the tool globally.

### 3. Tools exposed

| Tool | Purpose |
|------|------|
| `codingagent_list_skills`        | List every Skill available under `workspace/skills/` |
| `codingagent_read_skill(name)`   | Read a Skill's full text (OpenCode users can use it as context reference) |
| `codingagent_add_skill(name, content)` | Write a new Skill file; future SPECs can reference it as `@<name>.md` |
| `codingagent_generate(spec, max_iterations?, timeout_seconds?)` | Write the SPEC into `workspace/code/SPEC.md`, run the docker compose pipeline once, return the final `solution.py` / `RUN_LOG.md` / `DIAGNOSIS.md` |

### 4. Use it from OpenCode like this

```text
> /agent codingagent
> Write an LRU cache class keyed by str, evicted at the capacity given in the spec.
> Follow @PYTHON_STYLE.md @ALGO_PATTERNS.md @ERROR_HANDLING.md.
```

The agent's system prompt makes it call `codingagent_list_skills` first to confirm the available skills, then rewrite the user request into a SPEC with a `## Required Skills` section, and finally call `codingagent_generate` to run the full feedback loop. On failure it returns the Patch Plan from `DIAGNOSIS.md`, and the OpenCode user can drive another round of feedback.

### Caveats

- The MCP server runs **on the host**, and drives the pipeline through `docker compose -f docker-compose.yml up harness`, so the Docker daemon must be available.
- It is best to run `./setup.sh` once before the first call so that the `harness` image, the token volume and `.env` are all ready.
- If you run multiple `codingagent_generate` calls concurrently, they will fight over the same workspace; serialize the calls (OpenCode's tool calls are serial by default).

---

## Shutdown

```bash
docker compose down -v   # -v also wipes the old token from the secrets volume
```
