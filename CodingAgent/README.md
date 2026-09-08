# CodingAgent · OpenClaw 2.0 on Docker Sandbox

CodingAgent is a GitHub Copilot-powered code-generation and self-correction loop running on **OpenClaw 2.0 (`2026.8.1`)** inside a **Docker Sandbox microVM**.

The project uses only these Copilot models:

- Primary: `github-copilot/gpt-5.6-sol`
- Fallback: `github-copilot/gpt-5.5`

Claude models are no longer configured.

## Architecture

```mermaid
flowchart TB
    User["Developer / GitHub CLI"] --> Script["sandbox.sh"]
    Browser["Browser"] -->|"127.0.0.1:18790"| PublishedPort["Sandbox port 18790"]
    Script -->|"sbx create / exec"| SBX

    subgraph SBX["Docker Sandbox microVM"]
        Docker["Private Docker daemon"]
        Init["secrets-init"]
        Doctor["openclaw doctor --fix"]
        Pytest["pytest-init"]
        Gateway["OpenClaw 2.0 Gateway<br/>container port 18789"]
        Harness["Python orchestrator"]
        Coder["Coder · GPT-5.6 Sol"]
        Runner["Runner · GPT-5.6 Sol"]
        Diagnoser["Diagnoser · GPT-5.6 Sol"]
        ConfigVol[("config-vol")]
        SecretsVol[("secrets-vol<br/>tmpfs")]
        PytestVol[("pytest-vol")]
        Workspace[("Host workspace<br/>bind mount")]
        Socket["/var/run/docker.sock<br/>private daemon"]

        Docker --> Init
        Init --> ConfigVol
        Init --> SecretsVol
        ConfigVol --> Doctor
        Doctor --> Gateway
        Pytest --> PytestVol
        ConfigVol --> Gateway
        SecretsVol --> Gateway
        PytestVol --> Gateway
        Workspace --> Gateway
        Docker --> Gateway
        Docker --> Harness
        Socket --> Harness
        SecretsVol --> Harness
        Workspace --> Harness
        Harness -->|"docker exec + OpenClaw CLI"| Gateway
        Gateway --> Coder
        Gateway --> Runner
        Gateway --> Diagnoser
        PublishedPort -->|"18790 → 18789"| Gateway
    end

    Gateway -->|"fallback"| GPT55["GPT-5.5"]
    Gateway -->|"GitHub Copilot provider"| Copilot["GitHub Copilot API"]
```

The host runs only `sbx`. Docker Compose, containers, images, volumes, and `/var/run/docker.sock` live inside the isolated microVM. The socket mounted into the harness therefore controls only the sandbox's private Docker daemon.

### Component responsibilities

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| Host control plane | `sandbox.sh` | Creates or reconnects to the microVM, injects the Copilot token, applies network policy, forwards port `18790`, and runs lifecycle commands |
| Isolation boundary | Docker Sandbox | Provides the private Docker daemon, filesystem, network, image store, and container runtime |
| Runtime configuration | `secrets-init` | Copies the tracked credential-free template to `config-vol`, injects the Gateway token, creates per-agent Copilot profiles, and assigns runtime ownership to UID 1000 |
| OpenClaw migration | `openclaw-init` | Runs `openclaw doctor --fix` against `config-vol` to migrate legacy auth profiles into the OpenClaw 2.0 SQLite secret store |
| Test toolchain | `pytest-init` | Installs `pytest==8.3.5` from the Microsoft package proxy into `pytest-vol` |
| Agent runtime | `openclaw` | Hosts Coder, Runner, and Diagnoser and calls GitHub Copilot |
| Orchestration | `harness` | Calls agents through the OpenClaw CLI, parses OpenClaw 2.0 payload responses, checks artifacts, and controls retry iterations |
| Shared output | `workspace/` | Keeps the specification, skills, generated implementation, smoke test, run log, and diagnosis visible on the host |

### Trust and persistence boundaries

- `config/openclaw.json` is only a template; live Gateway and Copilot credentials are written to `config-vol`, not to the Git working tree.
- `secrets-vol` is tmpfs-backed and contains the Gateway token.
- `pytest-vol` is mounted read-only into OpenClaw after initialization.
- `openclaw-init` mounts only `config-vol`, so configuration migration cannot rewrite the host workspace.
- The project workspace is the only host directory shared with the microVM.
- Port forwarding has two layers: host `18790` → microVM `18790` → OpenClaw container `18789`.
- OpenClaw's internal `agents.defaults.sandbox.mode` remains `off` because the complete Compose stack already runs inside the stronger Docker Sandbox microVM boundary.

## Pipeline

1. **Coder** reads `workspace/code/SPEC.md`, referenced `@SKILL.md` files, and any previous `DIAGNOSIS.md`, then writes `solution.py`.
2. **Runner** recreates `smoke_test.py` strictly from the specification, executes it with `python3` or runs an existing pytest suite from the read-only tool volume, and writes the complete output and traceback to `RUN_LOG.md`.
3. On failure, **Diagnoser** writes a structured patch plan to `DIAGNOSIS.md`.
4. The next iteration sends the diagnosis back to Coder until the run passes or `MAX_ITERATIONS` is exhausted.

```mermaid
sequenceDiagram
    participant Host as sandbox.sh
    participant SBX as Docker Sandbox
    participant Gateway as OpenClaw 2.0
    participant Coder
    participant Runner
    participant Diagnoser

    Host->>SBX: deploy
    SBX->>SBX: secrets-init + pytest-init
    SBX->>SBX: openclaw doctor --fix
    SBX->>Gateway: start and wait for health
    Host->>SBX: run
    SBX->>Coder: SPEC + referenced skills + prior diagnosis
    Coder-->>SBX: solution.py
    SBX->>Runner: execute implementation
    Runner-->>SBX: RUN_LOG.md
    alt PASS
        SBX-->>Host: exit 0
    else FAIL
        SBX->>Diagnoser: traceback + solution + spec
        Diagnoser-->>SBX: DIAGNOSIS.md
        SBX->>Coder: next iteration with Patch Plan
    end
```

`./sandbox.sh deploy` is the only command that reruns configuration and auth initialization. `./sandbox.sh run` uses `docker compose run --rm --no-deps harness`, so a pipeline run does not restart or mutate the healthy Gateway.

## What changed in the OpenClaw 2.0 migration

| Area | Previous implementation | Current implementation |
|------|-------------------------|------------------------|
| OpenClaw image | Floating `latest` / older 2026.5 configuration | Pinned official OpenClaw 2.0 image `2026.8.1` |
| Isolation | Compose on the host Docker daemon | Entire Compose stack inside a Docker Sandbox microVM |
| Models | Claude primary and fallback models | GPT-5.6 Sol primary with GPT-5.5 fallback |
| Agent schema | Legacy `agents.list` and `systemPromptOverride` | OpenClaw 2.0 `agents.entries`; task contracts are injected by the orchestrator |
| Authentication | Runtime credentials written under the tracked config directory | Credential-free template plus private `config-vol`, tmpfs secrets, and SQLite migration |
| CLI response handling | Legacy top-level reply shapes | OpenClaw 2.0 `result.payloads[].text` parsing |
| Python execution | Assumed `python` and runtime package installation | Uses `python3` and a pinned, read-only pytest volume |
| Pipeline lifecycle | Compose dependencies restarted for every run | Initialization occurs during `deploy`; `run` starts only an ephemeral harness |
| Smoke tests | Reused potentially stale generated tests | Recreated each iteration from the current SPEC and temporary capture files removed |

## Versions

| Component | Version |
|-----------|---------|
| OpenClaw 2.0 | `ghcr.io/openclaw/openclaw:2026.8.1` |
| Docker Sandboxes | `sbx 0.42.0` or later |
| Primary model | `github-copilot/gpt-5.6-sol` |
| Fallback model | `github-copilot/gpt-5.5` |
| Python | `3.12` |
| pytest | `8.3.5` |

OpenClaw uses date-based release tags. The official [v2026.8.1 release](https://docs.openclaw.ai/releases/2026.8.1) is named **OpenClaw 2.0**.

## Prerequisites

Docker Sandboxes on macOS requires Apple silicon and macOS 14 or later.

```bash
brew trust docker/tap
brew install docker/tap/sbx
# Upgrade an existing installation:
brew upgrade docker/tap/sbx
sbx login
```

Docker Desktop is not required. Each sandbox provides its own Docker daemon, filesystem, and network.

You also need a GitHub account with Copilot access and the GitHub CLI:

```bash
gh auth status
```

Model availability depends on the GitHub Copilot plan and organization policy. The account must expose GPT-5.6 Sol and GPT-5.5 in its live model catalog.

## Quick start

```bash
chmod +x sandbox.sh setup.sh security/secrets-init.sh
./sandbox.sh deploy
./sandbox.sh run
```

`sandbox.sh` reads `COPILOT_GITHUB_TOKEN` from the host environment or obtains it with `gh auth token`. The token is passed into the microVM for the command and is not written into the tracked OpenClaw configuration.

To provide the token explicitly:

```bash
export COPILOT_GITHUB_TOKEN="$(gh auth token)"
./sandbox.sh deploy
```

The deployment creates a sandbox named `codingagent-openclaw`, allocates 4 CPUs and 8 GiB RAM, publishes port `18790`, builds the harness, and starts OpenClaw.

At sandbox creation, `sandbox.sh` allows only the outbound hosts required for GitHub, GHCR, GitHub Copilot, and the Microsoft Python package proxy, including its Azure DevOps package and Blob redirect domains.

Override resources when required:

```bash
OPENCLAW_SANDBOX_CPUS=6 \
OPENCLAW_SANDBOX_MEMORY=12g \
./sandbox.sh deploy
```

## Commands

| Command | Purpose |
|---------|---------|
| `./sandbox.sh deploy` | Create the microVM, build images, and start OpenClaw |
| `./sandbox.sh run` | Execute the complete self-correction pipeline without restarting the Gateway |
| `./sandbox.sh status` | Show sandbox and Compose status |
| `./sandbox.sh logs` | Follow OpenClaw logs |
| `./sandbox.sh shell` | Open a shell in the microVM |
| `./sandbox.sh down` | Stop Compose services and retain the microVM |
| `sbx stop codingagent-openclaw` | Stop the microVM |
| `sbx rm codingagent-openclaw` | Delete the microVM and its internal state |

The OpenClaw Control UI is published at:

```text
http://127.0.0.1:18790/
```

## Configure a task

Edit `workspace/code/SPEC.md`. Skill references use this format:

```markdown
## Required Skills

- @PYTHON_STYLE.md
- @ALGO_PATTERNS.md
- @ERROR_HANDLING.md
- @TESTING.md
```

Referenced files must exist in `workspace/skills/`. Coder loads only the referenced skill documents to keep its context focused.

Generated files are written to `workspace/code/`:

| File | Producer | Purpose |
|------|----------|---------|
| `solution.py` | Coder | Generated implementation |
| `smoke_test.py` | Runner | Test generated from the current SPEC |
| `RUN_LOG.md` | Runner | Command, exit code, stdout, and full traceback |
| `DIAGNOSIS.md` | Diagnoser | Root cause and patch plan after a failed run |

## Model configuration

`config/openclaw.json` uses OpenClaw's built-in [GitHub Copilot provider](https://docs.openclaw.ai/providers/github-copilot):

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "github-copilot/gpt-5.6-sol",
        "fallbacks": ["github-copilot/gpt-5.5"]
      }
    }
  }
}
```

GPT models use OpenClaw's OpenAI Responses transport. Live model availability is discovered from the Copilot API for the authenticated account.

## Credential handling

`config/openclaw.json` is a credential-free template. At startup:

1. `secrets-init` copies the template into the private `config-vol`.
2. It generates or reuses the Gateway token in the tmpfs-backed `secrets-vol`.
3. It injects the Gateway token into the runtime configuration.
4. It creates runtime-only Copilot auth profiles for Coder, Runner, and Diagnoser.
5. `openclaw doctor --fix` migrates those profiles into OpenClaw 2.0's SQLite-backed secret store before the Gateway starts.
6. `pytest-init` installs pinned `pytest==8.3.5` from the Microsoft package proxy into a read-only tool volume.

For interactive device authentication, use the command documented by OpenClaw:

```bash
./sandbox.sh shell
docker exec -it codingagent-openclaw \
  node /app/openclaw.mjs models auth login-github-copilot
```

For normal automated runs, `sandbox.sh` supplies `COPILOT_GITHUB_TOKEN`.

## Docker Sandbox isolation

Docker Sandboxes gives the project:

- A dedicated microVM boundary.
- A private Docker daemon and image store.
- An isolated filesystem and network.
- Explicit workspace sharing and port forwarding.
- Sandbox-specific outbound network policy.

The project directory is mounted at the same absolute path inside the microVM. Changes under `workspace/` therefore remain visible on the host, while containers and Docker volumes remain isolated inside the sandbox.

See the official [Docker Sandboxes documentation](https://docs.docker.com/ai/sandboxes/).

## OpenCode MCP integration

The existing `opencode.json` and `mcp/mcp_server.py` expose the pipeline to OpenCode. Run OpenCode from this directory after deploying the sandbox. Direct command-line execution remains the recommended validation path:

```bash
./sandbox.sh run
```

## Troubleshooting

| Symptom | Resolution |
|---------|------------|
| `sbx` cannot start | Confirm Apple silicon, macOS 14+, `sbx login`, and sufficient memory |
| Gateway health check fails | Run `./sandbox.sh logs` and inspect OpenClaw startup |
| Copilot authentication fails | Confirm `gh auth status` and that the account has Copilot access |
| Model not found | Inspect the live catalog inside the microVM and verify organization policy permits GPT-5.6 Sol |
| Harness cannot access Docker | Recreate the sandbox; the mounted socket must belong to the microVM daemon |
| Port `18790` is unavailable | Stop the conflicting process or set a different published port in `sandbox.sh` |

Inspect the model catalog:

```bash
sbx exec codingagent-openclaw \
  docker exec codingagent-openclaw \
  node /app/openclaw.mjs models list
```

## Shutdown

```bash
./sandbox.sh down
sbx stop codingagent-openclaw
```

To remove all sandbox-local images, containers, and volumes:

```bash
sbx rm codingagent-openclaw
```
