# AgentHarness_HostedAgent

> A **managed-style hosted agent** + **adversarial Skill-Testing harness** built on Microsoft Agent Framework.
> It inherits the 4-layer harness architecture (Brain / Hands / Session / Vault) from
> [maf_harness_managed_hosted_agent](https://github.com/microsoft/Agent-Framework-Samples/tree/main/09.Cases/maf_harness_managed_hosted_agent),
> and wraps the entire "business agent ↔ adversarial agent ↔ deterministic validator ↔ LLM judge"
> experiment pipeline of [Skill_Testing_Agent](../Skill_Testing_Agent/README.md) as hands registered
> into the sandbox pool.
> The model layer is migrated from GitHub Copilot to **Microsoft Foundry**: the two deployments
> under test are **DeepSeek-V4-Flash** and **gpt-5.5**.

---

## 1. Architecture

```
       ┌──────────────────────────┐    execute(name,input) -> str       ┌──────────┐
       │   Orchestrator (Brain)   │ ───────────────────────────────────▶│  Hands   │
       │  Foundry hosted agent    │                                     │ (sandbox │
       │  (bound to gpt-5.5)      │  emit_note / get_events / list_*    │  cattle) │
       └──────────────┬───────────┘                                     └──────────┘
                      │
                      ▼
       ┌──────────────────────────┐
       │       SessionStore       │ append-only log, decoupled from the brain's context window
       └──────────────────────────┘
```

- **Brain**: the `SkillTestingHarness` agent in [main.py](main.py), running on `ResponsesHostServer`
  (Foundry hosted agent / Responses protocol). It exposes only 5 tools: `execute / list_tools /
  list_models / get_events / emit_note`.
- **Hands**: the `SandboxPool` in [harness/sandbox.py](harness/sandbox.py). Each `execute` opens a
  one-shot sandbox that is retired right after use; hands share no state. This project registers
  7 hands:
  | hand | purpose |
  | --- | --- |
  | `list_test_cases` | fetch the 10 edge-knowledge cases |
  | `run_business_agent` | run the business agent on DeepSeek-V4-Flash or gpt-5.5 |
  | `validate_format` | deterministic format check (no LLM) |
  | `judge_rubric` | LLM-as-judge rubric grading on a Foundry model (5 items) |
  | `craft_attack` | single-shot adversarial prompt |
  | `next_attack_prompt` | multi-turn adversarial prompt with feedback |
  | `run_full_benchmark` | run all 10 cases × 2 models × multiple turns end-to-end |
- **Session**: file-level append-only log in [harness/session.py](harness/session.py). The brain
  re-reads any slice via `get_events`, and `wake(session_id)` recovers state after a crash.
- **Vault**: in [harness/vault.py](harness/vault.py), credentials are registered by logical name
  and the sandbox never sees the raw token. This project only calls Foundry, so Foundry's
  `DefaultAzureCredential` runs through `azure-identity` directly inside the hand.

The "business agent / attacker agent / judge" under test are all `Agent(FoundryChatClient(...))`,
constructed through the factory in [skills/foundry_factory.py](skills/foundry_factory.py).

---

## 2. Mapping to Skill_Testing_Agent

| Skill_Testing_Agent | AgentHarness_HostedAgent |
| --- | --- |
| `business_agent.py` | [skills/business_agent.py](skills/business_agent.py) (`GitHubCopilotAgent` → `FoundryChatClient`) |
| `MultiTurnAttacker` in `test_agent.py` | the stateless `next_attack_prompt` in [skills/test_agent.py](skills/test_agent.py) (multi-turn logic is reassembled by brain + session, hand stays cattle-style) |
| `judge.py` | [skills/judge.py](skills/judge.py) |
| `validator.py` | [skills/validator.py](skills/validator.py) |
| `test_cases.py` | [skills/test_cases.py](skills/test_cases.py) |
| `config.py` (claude/gpt) | [skills/config.py](skills/config.py) (**DeepSeek-V4-Flash + gpt-5.5**) |
| `main.py` (console runner) | [main_local.py](main_local.py) — same Rich table output |
| n/a | [main.py](main.py) — wraps everything above as a hosted agent speaking the Responses protocol |

---

## 3. How to run

### Prerequisites

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in FOUNDRY_PROJECT_ENDPOINT.
# If needed, change MODEL_DEEPSEEK / MODEL_GPT to the actual deployment names in your Foundry project.
az login   # DefaultAzureCredential needs this
```

### A · Local CLI (fastest way to validate model differences)

```bash
python main_local.py                      # full run: multi-turn + judge
python main_local.py --only edge-03
python main_local.py --model deepseek     # DeepSeek-V4-Flash only
python main_local.py --model gpt          # gpt-5.5 only
python main_local.py --no-attack          # baseline, plain prompt
python main_local.py --single-turn        # disable multi-turn
python main_local.py --no-judge           # disable LLM rubric
python main_local.py --max-turns 5
```

Each case lands in `artifacts/edge-XX__<Model>.json`, and the final aggregate is written to
`artifacts/summary.json`. The console output is a Rich comparison table: deterministic checks
on the left (✓ / partial-pass %), LLM judge on the right (✓ + 0–100 score), and an aggregated
pass-rate footer.

### B · Run as a hosted agent (Responses protocol)

```bash
# 1. Start the service locally
python main.py
# Output:
#   Skill-Testing Harness running on http://localhost:8088
#   Session id: <uuid>  (log dir: ./sessions)
#   Orchestrator: gpt-5.5
#   Models under test: DeepSeek-V4-Flash, GPT-5.5

# 2. Any Responses-protocol client can drive it, for example:
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": "请把 edge-03 用 DeepSeek-V4-Flash 跑 multi-turn 3 轮，并用 gpt-5.5 做 rubric 评分，最后给我对比结论。"
  }'

# Multi-turn: pass back the response id from the previous turn
# curl -s http://localhost:8088/responses \
#   -H "Content-Type: application/json" \
#   -d '{"input": "继续对 edge-04 跑一遍。", "previous_response_id": "<resp_id>"}'
```

The brain composes hand calls on its own according to the experiment flow described in `INSTRUCTIONS`.

### C · Deploy to Microsoft Foundry (the `azd ai agent` route)

This is the deployment path recommended by
[microsoft-foundry/foundry-samples · hosted-agents](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents):
**no Bicep / `azure.yaml`** — everything is described by [`agent.manifest.yaml`](agent.manifest.yaml)
(container + model resources) and driven by the `azd ai agent` extension.

#### C.1 · Required tools

```bash
# Azure Developer CLI + AI agent extension
curl -fsSL https://aka.ms/install-azd.sh | bash      # macOS/Linux
azd ext install azure.ai.agents
azd auth login
az login                                              # DefaultAzureCredential needs this
```

#### C.2 · Initialize from a separate empty directory outside this project

> ⚠️ `azd ai agent init` copies every source file next to the manifest into
> `<target>/src/<agent-name>/`.
> So **the manifest directory must NOT equal the directory you run the command in**, otherwise
> you get:
> `target '...' is inside the manifest directory '...'. Move the manifest to a separate directory containing only the agent files.`
> The correct flow is to step out of this project, create an empty directory as the azd
> workspace, and point `-m` back at the manifest in this repo.

```bash
# Step out of this project and create a clean azd working directory
cd ..
mkdir skill-testing-harness-deploy && cd skill-testing-harness-deploy

# Reference the manifest in the source project via a relative path
azd ai agent init -m ../AgentHarness_HostedAgent/agent.manifest.yaml
```

After running this, `skill-testing-harness-deploy/` looks like:

```
skill-testing-harness-deploy/
├── azure.yaml                       # generated by azd
├── .azure/<env>/.env                # generated env vars (FOUNDRY_PROJECT_ENDPOINT etc.)
└── src/
    └── skill-testing-harness/       # ← this is the actual deployed copy
        ├── main.py
        ├── harness/  skills/
        ├── Dockerfile  agent.yaml  agent.manifest.yaml
        └── requirements.txt
```

`azd ai agent init` will also walk you through:

1. Selecting / creating a Foundry project (it will run `azd provision` for you if none exists);
2. Mapping the two `kind: model` resources in the manifest to actual model ids in the Foundry catalogue;
3. Generating `.azure/<env>/.env` already populated with `FOUNDRY_PROJECT_ENDPOINT`, `MODEL_GPT`, `MODEL_DEEPSEEK`.

> ⚠️ If the DeepSeek deployment in your Foundry subscription is not exposed as `deepseek-v4-flash`,
> change it to the actual id (such as `deepseek-r1`) during the `azd ai agent init` interactive
> prompts, or override it afterwards with `azd env set MODEL_DEEPSEEK <real-deployment-name>`.
> Same for the gpt entry — replace it with `gpt-4.1`, `gpt-4o`, or whatever deployment is
> currently available to you.

#### C.3 · Provision resources and deploy

```bash
# Still inside skill-testing-harness-deploy/

# 1) provision — must run first! It creates/binds ACR, the Foundry project, and the model
#    deployments, and writes AZURE_CONTAINER_REGISTRY_ENDPOINT (etc.) into .azure/<env>/.env.
azd provision

# 2) Verify the ACR endpoint has been written to the environment
azd env get-values | grep -i CONTAINER_REGISTRY
# Expect to see: AZURE_CONTAINER_REGISTRY_ENDPOINT="cr<random>.azurecr.io"

# 3) Deploy the container to the Foundry hosted agent
azd deploy
```

> ⚠️ **Skipping `azd provision` and going straight to `azd deploy` will fail** with:
> `could not determine container registry endpoint, ensure 'registry' has been set in the docker options or 'AZURE_CONTAINER_REGISTRY_ENDPOINT' environment variable has been set`
> because `azd deploy` does not create the ACR — it only pushes the image to the ACR that
> was already provisioned.

##### Using an existing ACR (instead of letting azd create a new one)

```bash
az acr list --query "[].{name:name,loginServer:loginServer,rg:resourceGroup}" -o table

azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <your-acr>.azurecr.io
az acr login --name <your-acr>
az role assignment create \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --role AcrPush \
  --scope $(az acr show --name <your-acr> --query id -o tsv)

azd deploy
```

##### When `azd provision` itself fails (for example you picked a deleted Foundry project in the wizard)

```bash
rm -rf .azure                       # wipe the old env
azd ai agent init -m ../AgentHarness_HostedAgent/agent.manifest.yaml
# Re-select an actually existing Foundry account / project
azd provision
azd deploy
```

> When you change source files later, sync them across:
> `rsync -a --delete ../AgentHarness_HostedAgent/ src/skill-testing-harness/ \`
> &nbsp;&nbsp;`--exclude .azure --exclude .venv --exclude artifacts --exclude sessions`
> Or just edit directly under `src/skill-testing-harness/` — that copy is the one azd actually deploys.

At runtime, Foundry injects:

| Environment variable | Source |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry hosting runtime |
| `MODEL_GPT` / `MODEL_DEEPSEEK` | the two `kind: model` resources in the manifest |
| `ORCHESTRATOR_MODEL` | manifest default `{{MODEL_GPT}}` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | injected automatically by Foundry (OTel telemetry) |

#### C.4 · Invoking the deployed agent

```bash
# Invoke the live agent through azd
azd ai agent invoke "请把 edge-03 用 DeepSeek-V4-Flash 跑 multi-turn 3 轮，并用 gpt-5.5 做 rubric 评分。"

# Or chat with it inside the Foundry portal Agent Playground;
# Or hit its Responses endpoint directly (azd will print the address):
curl -X POST "$AGENT_ENDPOINT/responses" \
  -H "Authorization: Bearer $(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)" \
  -H "Content-Type: application/json" \
  -d '{"input": "先用 list_test_cases 拉一下，再 run_full_benchmark only=edge-03。"}'
```

#### C.5 · Pure local container (no deployment)

If you only want to docker-run it locally (without going through Foundry), use [Dockerfile](Dockerfile):

```bash
docker build -t skill-testing-harness .
docker run --rm -p 8088:8088 --env-file .env skill-testing-harness
```

---

## 4. What you will see after a full run

```
                     Foundry Format-Consistency Benchmark
┌─────────┬──────────────────────────────┬─────────────────────┬─────────────┐
│  Case   │ Knowledge Point              │ DeepSeek-V4-Flash   │   GPT-5.5   │
├─────────┼──────────────────────────────┼─────────────────────┼─────────────┤
│ edge-01 │ 量子纠缠对日常生活的影响     │ ✓ | ✓92             │ ✓ | ✓95     │
│ edge-02 │ 哥德尔不完备性定理           │ 67% | ✗63           │ ✓ | ✓88     │
│ ...     │ ...                          │ ...                 │ ...         │
│ TOTAL   │ pass rate / mean (rubric)    │ 60% / 78% (74)      │ 90% / 95% (89) │
└─────────┴──────────────────────────────┴─────────────────────┴─────────────┘
```

Each `artifacts/edge-XX__<Model>.json` records: the starting prompt, every per-turn prompt drift,
the model's answer, the hit map of all 9 deterministic checks, and the 5 rubric scores.

---

## 5. File layout

```
AgentHarness_HostedAgent/
├── README.md
├── agent.yaml             # container agent protocol (kind: hosted, responses 1.0.0)
├── agent.manifest.yaml    # azd ai agent deployment manifest (model resources + injected env vars)
├── Dockerfile
├── .dockerignore .gitignore .env.example
├── requirements.txt
├── main.py                # ← Brain: hosted-agent entry point (runs on Foundry)
├── main_local.py          # local CLI runner that calls skills/* directly
├── harness/               # 4-layer harness (mirrors the upstream maf sample)
│   ├── __init__.py
│   ├── sandbox.py         # SandboxPool / cattle-style hands
│   ├── session.py         # durable SessionStore (append-only jsonl)
│   └── vault.py           # CredentialVault (injected by logical name)
├── skills/                # business logic that the hands actually call
│   ├── __init__.py
│   ├── config.py          # Foundry deployments: DeepSeek-V4-Flash + gpt-5.5
│   ├── foundry_factory.py # FoundryChatClient + DefaultAzureCredential
│   ├── business_agent.py  # script-generation Agent with a strict template
│   ├── test_agent.py      # single-shot / multi-turn adversarial prompt generation
│   ├── judge.py           # 5-item rubric LLM judge
│   ├── validator.py       # 9-item deterministic format check
│   └── test_cases.py      # 10 edge-knowledge cases
└── artifacts/             # JSON traces + summary.json from each run
```

---

## 6. Key differences vs. the upstream sample

| Dimension | upstream maf sample | This project |
| --- | --- | --- |
| Models | a single `MODEL_DEPLOYMENT_NAME` | DeepSeek-V4-Flash + gpt-5.5 dual-model A/B |
| Hands | generic sandboxes: `python_exec / shell_exec / http_fetch` | 7 Skill-Testing-specific hands (business / attacker / judge / validator / benchmark) |
| Purpose | a generic managed-style template | an adversarial evaluation harness for the "educational video script output contract" |
| Local CLI | none | [main_local.py](main_local.py) with Rich table + JSON artifacts |
| Session usage | generic event log | every `benchmark_turn` records case_id / model / pass / score for replay |

---

## 7. Troubleshooting

| Symptom | Diagnosis |
| --- | --- |
| `Set FOUNDRY_PROJECT_ENDPOINT in your .env` | `.env` is empty or `python-dotenv` is not installed |
| `DefaultAzureCredential failed to retrieve a token` | run `az login`, or use Managed Identity in the Foundry hosted environment |
| `HTTP 404` from FoundryChatClient | the deployment name (`MODEL_DEEPSEEK` / `MODEL_GPT`) does not match what's in the Foundry project; run `azd env get-values` to see what was injected, or check the Foundry portal; fix locally with `azd env set MODEL_DEEPSEEK <real-name>` |
| `azd ai agent init` cannot find the `azure.ai.agents` extension | run `azd ext install azure.ai.agents`; the extension is still in preview and requires azd ≥ 1.10 |
| `azd deploy` fails with "model id not found" | `resources[].id` in the manifest does not match the Foundry catalogue; change to an actually available id like `gpt-4.1` / `gpt-4o` / `deepseek-r1` |
| `azd deploy` reports `could not determine container registry endpoint` | you skipped `azd provision`. Run `azd provision` first, or manually set `azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <acr>.azurecr.io` and grant `AcrPush` |
| `azd provision` reports `failed to get Foundry project: ... 404` | the wizard pointed at a deleted Foundry account/project. `rm -rf .azure`, re-run `azd ai agent init`, and pick an existing project |
| Judge always FAILs | the model wraps JSON inside a ```` ``` ```` fence — `_extract_json` already covers braces; if it still fails, the response is not JSON, look at `artifacts/*.json.raw` |
| `run_full_benchmark` times out mid-run | raise `REQUEST_TIMEOUT` in `.env` (the legacy name `FOUNDRY_TIMEOUT` is still accepted locally), or lower `max_turns` |
| `azd deploy` reports `Environment variable 'FOUNDRY_*' is reserved` | Foundry reserves the `FOUNDRY_*` / `AGENT_*` prefixes; the manifest's `environment_variables` cannot use those names. This project already renamed `FOUNDRY_TIMEOUT` to `REQUEST_TIMEOUT` |

---

## 8. References

- Upstream managed-style sample: <https://github.com/microsoft/Agent-Framework-Samples/tree/main/09.Cases/maf_harness_managed_hosted_agent>
- Foundry hosted-agents official sample (source of the deployment path): <https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents>
- Foundry deployment docs: <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent>
- Foundry agent management: <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent>
- Skill_Testing_Agent (same repo, sibling directory): [../Skill_Testing_Agent/README.md](../Skill_Testing_Agent/README.md)
- Microsoft Agent Framework Foundry provider docs: <https://learn.microsoft.com/en-us/agent-framework/agents/providers/foundry?pivots=programming-language-python>
- Managed-Agent design origin (Anthropic): <https://www.anthropic.com/engineering/managed-agents>
