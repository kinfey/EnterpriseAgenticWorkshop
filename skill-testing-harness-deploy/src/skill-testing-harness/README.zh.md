# AgentHarness_HostedAgent

> Microsoft Agent Framework 上的 **managed-style hosted agent** + **对抗式 Skill-Testing 实验台**。  
> 脱胎于 [maf_harness_managed_hosted_agent](https://github.com/microsoft/Agent-Framework-Samples/tree/main/09.Cases/maf_harness_managed_hosted_agent) 的 4 层 harness 架构（Brain / Hands / Session / Vault），  
> 把 [Skill_Testing_Agent](../Skill_Testing_Agent/README.md) 的「业务 Agent ↔ 对抗 Agent ↔ 确定性 validator ↔ LLM judge」整套实验逻辑作为 hands 注册进 sandbox pool。  
> 模型从 GitHub Copilot 迁移到 **Microsoft Foundry**：被测两枚部署是 **DeepSeek-V4-Flash** 与 **gpt-5.5**。

---

## 1. 架构

```
       ┌──────────────────────────┐    execute(name,input) -> str       ┌──────────┐
       │   Orchestrator (Brain)   │ ───────────────────────────────────▶│  Hands   │
       │  Foundry hosted agent    │                                     │ (sandbox │
       │  (默认绑定 gpt-5.5)      │  emit_note / get_events / list_*    │  cattle) │
       └──────────────┬───────────┘                                     └──────────┘
                      │
                      ▼
       ┌──────────────────────────┐
       │       SessionStore       │ 追加日志，独立于 brain 的 context window
       └──────────────────────────┘
```

- **Brain**：[main.py](main.py) 里的 `SkillTestingHarness` agent，跑在 `ResponsesHostServer`（Foundry hosted agent / Responses 协议）。它只暴露 5 个工具：`execute / list_tools / list_models / get_events / emit_note`。
- **Hands**：[harness/sandbox.py](harness/sandbox.py) 里的 `SandboxPool`。每次 `execute` 都开一个一次性 sandbox，跑完即弃；hands 之间互不共享状态。本项目注册了 7 个 hand：
  | hand | 作用 |
  | --- | --- |
  | `list_test_cases` | 拉 10 条 edge-knowledge case |
  | `run_business_agent` | 用 DeepSeek-V4-Flash 或 gpt-5.5 跑业务 Agent |
  | `validate_format` | 不调用 LLM 的确定性格式校验 |
  | `judge_rubric` | 用 Foundry 模型做 5 项 LLM-as-judge 评分 |
  | `craft_attack` | 单轮对抗 prompt |
  | `next_attack_prompt` | 多轮带反馈的对抗 prompt |
  | `run_full_benchmark` | 一把跑完 10 case × 2 model × 多轮 |
- **Session**：[harness/session.py](harness/session.py) 文件级 append-only log，brain 用 `get_events` 重读任意切片，崩溃后 `wake(session_id)` 恢复。
- **Vault**：[harness/vault.py](harness/vault.py) 凭据按逻辑名注册，sandbox 内拿不到原始 token；本项目对外只调 Foundry，所以 Foundry 的 `DefaultAzureCredential` 在 hand 内部直接走 azure-identity。

被测的「业务 Agent / 对抗 Agent / Judge」都是 `Agent(FoundryChatClient(...))`，工厂在 [skills/foundry_factory.py](skills/foundry_factory.py)。

---

## 2. 与 Skill_Testing_Agent 的对应关系

| Skill_Testing_Agent | AgentHarness_HostedAgent |
| --- | --- |
| `business_agent.py` | [skills/business_agent.py](skills/business_agent.py)（`GitHubCopilotAgent` → `FoundryChatClient`） |
| `test_agent.py` 的 `MultiTurnAttacker` | [skills/test_agent.py](skills/test_agent.py) 的无状态 `next_attack_prompt`（多轮逻辑由 brain + session 重组，hand 保持 cattle） |
| `judge.py` | [skills/judge.py](skills/judge.py) |
| `validator.py` | [skills/validator.py](skills/validator.py) |
| `test_cases.py` | [skills/test_cases.py](skills/test_cases.py) |
| `config.py`（claude/gpt） | [skills/config.py](skills/config.py)（**DeepSeek-V4-Flash + gpt-5.5**） |
| `main.py`（控制台 runner） | [main_local.py](main_local.py) — 同样的 Rich 表格输出 |
| 无 | [main.py](main.py) — 把上面所有逻辑包装成 hosted agent，对外说 Responses 协议 |

---

## 3. 运行方式

### 前置

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填上 FOUNDRY_PROJECT_ENDPOINT
# 必要时改 MODEL_DEEPSEEK / MODEL_GPT 成你 Foundry 项目里实际的部署名
az login   # DefaultAzureCredential 用得到
```

### A · 本地 CLI（最快验证模型差异）

```bash
python main_local.py                      # 全跑：multi-turn + judge
python main_local.py --only edge-03
python main_local.py --model deepseek     # 仅 DeepSeek-V4-Flash
python main_local.py --model gpt          # 仅 gpt-5.5
python main_local.py --no-attack          # baseline，普通 prompt
python main_local.py --single-turn        # 关闭 multi-turn
python main_local.py --no-judge           # 关闭 LLM rubric
python main_local.py --max-turns 5
```

每条 case 落 `artifacts/edge-XX__<Model>.json`，最终汇总写到 `artifacts/summary.json`。控制台是 Rich 对比表：左边是确定性校验（✓ / 部分通过 %），右边是 LLM judge（✓ + 0-100 分），底行是聚合 pass-rate。

### B · 作为 hosted agent 跑（Responses 协议）

```bash
# 1. 本地起服务
python main.py
# 输出：
#   Skill-Testing Harness running on http://localhost:8088
#   Session id: <uuid>  (log dir: ./sessions)
#   Orchestrator: gpt-5.5
#   Models under test: DeepSeek-V4-Flash, GPT-5.5

# 2. 任何 Responses 协议客户端都能驱动它，例如：
curl -s http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": "请把 edge-03 用 DeepSeek-V4-Flash 跑 multi-turn 3 轮，并用 gpt-5.5 做 rubric 评分，最后给我对比结论。"
  }'

# 多轮：把上一轮返回的 response id 带进来
# curl -s http://localhost:8088/responses \
#   -H "Content-Type: application/json" \
#   -d '{"input": "继续对 edge-04 跑一遍。", "previous_response_id": "<resp_id>"}'
```

Brain 会自己按 `INSTRUCTIONS` 描述的实验流程组合调用 hands。

### C · 部署到 Microsoft Foundry（`azd ai agent` 路线）

这是 [microsoft-foundry/foundry-samples · hosted-agents](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents) 官方推荐的部署方式：
**没有 Bicep / `azure.yaml`**，全靠 [`agent.manifest.yaml`](agent.manifest.yaml) 描述容器 + 模型资源，由 `azd ai agent` 扩展驱动。

#### C.1 · 前置工具

```bash
# Azure Developer CLI + AI agent 扩展
curl -fsSL https://aka.ms/install-azd.sh | bash      # macOS/Linux
azd ext install azure.ai.agents
azd auth login
az login                                              # DefaultAzureCredential 需要
```

#### C.2 · 在项目外另起一个空目录初始化

> ⚠️ `azd ai agent init` 会把 manifest 旁边的所有源码 copy 到 `<target>/src/<agent-name>/`。  
> 因此 **manifest 所在目录必须 ≠ 你执行命令的目录**，否则会报：  
> `target '...' is inside the manifest directory '...'. Move the manifest to a separate directory containing only the agent files.`  
> 正确做法是退到本项目外面，新建一个空目录作为 azd workspace，再把 `-m` 指向本仓库里的 manifest。

```bash
# 退到本项目外，建一个干净的 azd 工作目录
cd ..
mkdir skill-testing-harness-deploy && cd skill-testing-harness-deploy

# manifest 用相对路径指回源项目
azd ai agent init -m ../AgentHarness_HostedAgent/agent.manifest.yaml
```

执行完后 `skill-testing-harness-deploy/` 长这样：

```
skill-testing-harness-deploy/
├── azure.yaml                       # azd 自动生成
├── .azure/<env>/.env                # 生成的环境变量（FOUNDRY_PROJECT_ENDPOINT 等）
└── src/
    └── skill-testing-harness/       # ← 这才是真正部署的副本
        ├── main.py
        ├── harness/  skills/
        ├── Dockerfile  agent.yaml  agent.manifest.yaml
        └── requirements.txt
```

`azd ai agent init` 还会引导你：

1. 选 / 建 Foundry 项目（没有就帮你跑 `azd provision`）；
2. 把 manifest 里两个 `kind: model` 资源映射到 Foundry catalog 里实际可用的模型 id；
3. 生成 `.azure/<env>/.env`，里面已经填好 `FOUNDRY_PROJECT_ENDPOINT`、`MODEL_GPT`、`MODEL_DEEPSEEK`。

> ⚠️ 如果你 Foundry 订阅里 DeepSeek 系部署在 catalog 里的 id 不是 `deepseek-v4-flash`，  
> 在 `azd ai agent init` 交互里改成实际 id（例如 `deepseek-r1` 之类），或事后 `azd env set MODEL_DEEPSEEK <real-deployment-name>`。
> 同理 gpt 那一条可以替换成 `gpt-4.1`、`gpt-4o` 等当前可拿到的部署。

#### C.3 · 配资源 + 部署

```bash
# 还在 skill-testing-harness-deploy/ 里

# 1) provision —— 必须先跑！它会创建/绑定 ACR、Foundry 项目、模型部署，
#    并把 AZURE_CONTAINER_REGISTRY_ENDPOINT 等写进 .azure/<env>/.env
azd provision

# 2) 验证 ACR endpoint 已经写进环境
azd env get-values | grep -i CONTAINER_REGISTRY
# 期望看到：AZURE_CONTAINER_REGISTRY_ENDPOINT="cr<random>.azurecr.io"

# 3) 部署容器到 Foundry hosted agent
azd deploy
```

> ⚠️ **跳过 `azd provision` 直接 `azd deploy` 会报错**：  
> `could not determine container registry endpoint, ensure 'registry' has been set in the docker options or 'AZURE_CONTAINER_REGISTRY_ENDPOINT' environment variable has been set`  
> 因为 `azd deploy` 不会自己建 ACR，它只往 provision 阶段创建好的 ACR 里推镜像。

##### 想用现有 ACR（不让 azd 新建）

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

##### `azd provision` 自身报错时（比如向导里选错了已删除的 Foundry 项目）

```bash
rm -rf .azure                       # 清掉旧 env
azd ai agent init -m ../AgentHarness_HostedAgent/agent.manifest.yaml
# 重新选实际存在的 Foundry account / project
azd provision
azd deploy
```

> 后续改了源代码记得同步：  
> `rsync -a --delete ../AgentHarness_HostedAgent/ src/skill-testing-harness/ \`  
> &nbsp;&nbsp;`--exclude .azure --exclude .venv --exclude artifacts --exclude sessions`  
> 或者干脆直接在 `src/skill-testing-harness/` 里改，那边才是 azd 真正部署的副本。

Foundry 在运行时会自动注入：

| 环境变量 | 来源 |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry hosting runtime |
| `MODEL_GPT` / `MODEL_DEEPSEEK` | manifest 里的两条 `kind: model` 资源 |
| `ORCHESTRATOR_MODEL` | manifest 里默认 `{{MODEL_GPT}}` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Foundry 自动注入（OTel 上报） |

#### C.4 · 调用部署后的 agent

```bash
# 通过 azd 直接调用线上 agent
azd ai agent invoke "请把 edge-03 用 DeepSeek-V4-Flash 跑 multi-turn 3 轮，并用 gpt-5.5 做 rubric 评分。"

# 或通过 Foundry portal 在 Agent Playground 里聊；
# 或直接打它的 Responses 端点（端点地址在 azd 输出里）：
curl -X POST "$AGENT_ENDPOINT/responses" \
  -H "Authorization: Bearer $(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)" \
  -H "Content-Type: application/json" \
  -d '{"input": "先用 list_test_cases 拉一下，再 run_full_benchmark only=edge-03。"}'
```

#### C.5 · 纯本地容器（不部署）

如果你只想 docker 本地跑（不上 Foundry），用 [Dockerfile](Dockerfile)：

```bash
docker build -t skill-testing-harness .
docker run --rm -p 8088:8088 --env-file .env skill-testing-harness
```

---

## 4. 跑通后你会看到的对比

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

每条 `artifacts/edge-XX__<Model>.json` 记录：起始 prompt、每一轮的 prompt 漂移、模型回答、9 项确定性 check 的命中情况、5 项 rubric 评分。

---

## 5. 文件清单

```
AgentHarness_HostedAgent/
├── README.md
├── agent.yaml             # 容器 agent 协议声明 (kind: hosted, responses 1.0.0)
├── agent.manifest.yaml    # azd ai agent 部署清单（模型资源 + 注入环境变量）
├── Dockerfile
├── .dockerignore .gitignore .env.example
├── requirements.txt
├── main.py                # ← Brain：hosted agent 入口（Foundry 上跑）
├── main_local.py          # 本地 CLI runner，直接调 skills/*
├── harness/               # 4 层 harness（与 maf 上游样例同构）
│   ├── __init__.py
│   ├── sandbox.py         # SandboxPool / cattle-style hands
│   ├── session.py         # 持久化 SessionStore（jsonl append-only）
│   └── vault.py           # CredentialVault（按逻辑名注入）
├── skills/                # 业务逻辑（hands 真正调用的实现）
│   ├── __init__.py
│   ├── config.py          # Foundry deployment：DeepSeek-V4-Flash + gpt-5.5
│   ├── foundry_factory.py # FoundryChatClient + DefaultAzureCredential
│   ├── business_agent.py  # 模板严格的脚本生成 Agent
│   ├── test_agent.py      # 单轮 / 多轮对抗 prompt 生成
│   ├── judge.py           # 5 项 rubric 的 LLM judge
│   ├── validator.py       # 9 项确定性格式校验
│   └── test_cases.py      # 10 条 edge-knowledge case
└── artifacts/             # 每次运行的 JSON trace + summary.json
```

---

## 6. 与上游样例的差异速查

| 维度 | upstream maf sample | 本项目 |
| --- | --- | --- |
| 模型 | 单一 `MODEL_DEPLOYMENT_NAME` | DeepSeek-V4-Flash + gpt-5.5 双模型对比 |
| Hands | `python_exec / shell_exec / http_fetch` 通用沙箱 | 7 个 Skill-Testing 专用 hand（业务/攻击/judge/validator/benchmark） |
| 用途 | 通用 managed-style 模板 | 围绕「教育视频脚本输出契约」的对抗式评估实验台 |
| 本地 CLI | 无 | [main_local.py](main_local.py) Rich 表格 + JSON artifact |
| Session 用法 | 通用事件日志 | 每轮 `benchmark_turn` 记录 case_id / model / pass / score，便于回放 |

---

## 7. 排错

| 现象 | 排查 |
| --- | --- |
| `Set FOUNDRY_PROJECT_ENDPOINT in your .env` | `.env` 没填或 `python-dotenv` 没装 |
| `DefaultAzureCredential failed to retrieve a token` | `az login`，或在 Foundry hosted 环境下使用 Managed Identity |
| `HTTP 404` from FoundryChatClient | 部署名（`MODEL_DEEPSEEK` / `MODEL_GPT`）和 Foundry 项目里的不一致；运行 `azd env get-values` 看实际注入值，或在 Foundry portal 里确认；本地修：`azd env set MODEL_DEEPSEEK <real-name>` |
| `azd ai agent init` 找不到 `azure.ai.agents` 扩展 | 跑 `azd ext install azure.ai.agents`；扩展仍在预览，需要 azd ≥ 1.10 |
| `azd deploy` 失败 "model id not found" | manifest 里 `resources[].id` 和 Foundry catalog 不一致，改成 `gpt-4.1` / `gpt-4o` / `deepseek-r1` 等实际可用 id |
| `azd deploy` 报 `could not determine container registry endpoint` | 跳过 `azd provision` 了。先跑 `azd provision`，或手动 `azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <acr>.azurecr.io` 并赋 `AcrPush` 权限 |
| `azd provision` 报 `failed to get Foundry project: ... 404` | 向导里选到了已经删除的 Foundry account/project。`rm -rf .azure` 重新 `azd ai agent init`，选实际存在的项目 |
| Judge 永远 FAIL | 模型把 JSON 包在 ```` ``` ```` 围栏里——本项目的 `_extract_json` 已兜底大括号配对；如仍失败说明返回不是 JSON，看 `artifacts/*.json.raw` |
| `run_full_benchmark` 中途超时 | 调高 `.env` 里 `REQUEST_TIMEOUT`（旧名 `FOUNDRY_TIMEOUT` 本地仍兼容），或减小 `max_turns` |
| `azd deploy` 报 `Environment variable 'FOUNDRY_*' is reserved` | Foundry 保留 `FOUNDRY_*` / `AGENT_*` 前缀，manifest 的 `environment_variables` 不能出现这些名字。本项目里已从 `FOUNDRY_TIMEOUT` 改名为 `REQUEST_TIMEOUT` |

---

## 8. 参考

- Managed-style 上游：<https://github.com/microsoft/Agent-Framework-Samples/tree/main/09.Cases/maf_harness_managed_hosted_agent>
- Foundry hosted-agents 官方样例（部署路径来源）：<https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents>
- Foundry 部署官方文档：<https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent>
- Foundry agent 管理：<https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent>
- Skill_Testing_Agent（同仓库，相邻目录）：[../Skill_Testing_Agent/README.md](../Skill_Testing_Agent/README.md)
- Microsoft Agent Framework Foundry provider 文档：<https://learn.microsoft.com/en-us/agent-framework/agents/providers/foundry?pivots=programming-language-python>
- Managed-Agent 设计来源（Anthropic）：<https://www.anthropic.com/engineering/managed-agents>
