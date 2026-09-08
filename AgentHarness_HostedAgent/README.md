# AgentHarness Docker Sandbox

An adversarial Skill-Testing harness built with Microsoft Agent Framework and GitHub Copilot. It is **deployed only to a local Docker Sandbox microVM** and creates, connects to, or depends on no Azure resources.

## Architecture

```text
Local host
├── sbx CLI
├── project workspace (read/write mount)
└── 127.0.0.1:18088
      │
      ▼
Docker Sandbox microVM
├── FastAPI service
│   ├── GET /health
│   └── POST /responses
├── Orchestrator Agent
│   ├── GitHubCopilotAgent
│   ├── model: GPT-6 Astra
│   └── tools: execute / list_tools / list_models / get_events / emit_note
├── HandPool (in-process dispatch)
│   ├── Business Agent ───────┐
│   ├── Adversarial Agent ────┼── GitHub Copilot SDK/runtime
│   ├── LLM Judge ────────────┘      ├── GPT-6 Astra
│   └── Deterministic Validator      └── GPT-5.6 Sol
├── SessionStore
│   └── /home/agent/state/sessions
├── sandbox-local Python virtual environment
│   └── /home/agent/.venvs/skill-testing-harness
├── isolated filesystem and network
└── isolated Docker daemon
      │
      └── outbound HTTPS → GitHub Copilot API
```

Docker Sandbox is the only runtime and isolation boundary:

- No Azure, Foundry, ACR, Bicep, `azd`, or managed identity.
- GitHub Copilot supplies all model inference.
- GPT-6 Astra is the default orchestrator and first comparison model.
- GPT-5.6 Sol is the second comparison model.
- The project directory is the only writable host workspace.
- Session state and the Python environment persist inside the sandbox.
- The host Docker socket is never mounted. Containers started by an agent use
  the microVM's own Docker daemon.
- `HandPool` is a function dispatcher, not another security boundary. All
  security isolation is provided by the outer Docker Sandbox microVM.

### Request flow

1. A client sends `POST /responses` to host port `18088`.
2. Docker Sandbox forwards the request to FastAPI on sandbox port `8088`.
3. The GPT-6 Astra orchestrator selects a registered harness tool.
4. `HandPool` invokes the business, attacker, validator, or judge operation.
5. LLM-backed hands create isolated GitHub Copilot SDK sessions using either
   `gpt-6-astra` or `gpt-5.6-sol`.
6. Tool events and response summaries are appended to `SessionStore`.
7. FastAPI returns a response containing `id`, `model`, and `output_text`.

The endpoint is a lightweight Responses-style API owned by this project; it
does not require a cloud-hosted agent service.

### State and security boundaries

| Boundary | Location | Persistence |
| --- | --- | --- |
| Source and generated benchmark artifacts | Mounted project workspace | Stored on the host |
| Python packages and Copilot runtime cache | Docker Sandbox microVM | Preserved across stop/start |
| Harness session events | `/home/agent/state/sessions` | Preserved across stop/start |
| Copilot OAuth login | Sandbox-local Copilot configuration | Removed with the sandbox |
| Docker images and containers created by agents | Sandbox-local Docker daemon | Removed with the sandbox |

## Prerequisites

Install Docker Sandboxes:

```bash
brew trust docker/tap
brew install docker/tap/sbx
sbx login
```

After creating the sandbox, complete GitHub Copilot OAuth authentication inside the microVM. The credential persists inside the sandbox and is not written to the repository or image:

```bash
./scripts/docker-sandbox.sh setup
./scripts/docker-sandbox.sh login
```

If the CLI asks to use plaintext storage because the Linux microVM has no system keychain, confirm it. The file remains inside the isolated sandbox and is deleted with `remove`.

## Deploy directly

The first deployment requires setup and Copilot authentication:

```bash
./scripts/docker-sandbox.sh plan
./scripts/docker-sandbox.sh setup
./scripts/docker-sandbox.sh login
./scripts/docker-sandbox.sh run
```

Start in the background:

```bash
./scripts/docker-sandbox.sh start
```

Endpoints:

```text
GET  http://localhost:18088/health
POST http://localhost:18088/responses
```

```bash
curl -s http://localhost:18088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Run edge-03 against GPT-6 Astra and GPT-5.6 Sol for three turns and grade both."
  }'
```

## Sandbox lifecycle

```bash
./scripts/docker-sandbox.sh setup
./scripts/docker-sandbox.sh shell
./scripts/docker-sandbox.sh status
./scripts/docker-sandbox.sh stop
./scripts/docker-sandbox.sh remove
```

| Setting | Value |
| --- | --- |
| Sandbox agent | `copilot` (Docker's official Copilot kit) |
| Orchestrator | `gpt-6-astra` |
| Test model 1 | `gpt-6-astra` |
| Test model 2 | `gpt-5.6-sol` |
| CPU / Memory | 4 CPU / 8 GiB |
| Host / Sandbox port | `18088 / 8088` |
| PyPI source | `https://packagefeedproxy.microsoft.io/pypi/simple` |

Model IDs can be overridden in an optional `.env`, but the committed defaults
remain GPT-6 Astra and GPT-5.6 Sol:

```bash
cp .env.example .env
```

## Benchmark CLI

```bash
./scripts/docker-sandbox.sh shell

/home/agent/.venvs/skill-testing-harness/bin/python main_local.py
/home/agent/.venvs/skill-testing-harness/bin/python main_local.py --model astra
/home/agent/.venvs/skill-testing-harness/bin/python main_local.py --model sol
/home/agent/.venvs/skill-testing-harness/bin/python main_local.py --only edge-03
```

## Key files

```text
sbxenv.yaml                 # sandbox, models, and port
scripts/docker-sandbox.sh   # create, install, run, and remove
main.py                     # local FastAPI + Copilot orchestrator
main_local.py               # two-model benchmark
harness/hands.py            # in-process hand dispatch
harness/session.py          # append-only session state
skills/copilot_factory.py   # GitHubCopilotAgent factory
skills/                     # business / attacker / validator / judge
```

References:

- [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/)
- [Docker Sandbox Copilot integration](https://docs.docker.com/ai/sandboxes/agents/copilot/)
- [Agent Framework GitHub Copilot](https://github.com/microsoft/agent-framework/tree/main/python/packages/github_copilot)
