# CodingAgent · OpenClaw 框架下的 Copilot 代码生成 Agent

> 用 GitHub Copilot（默认 `claude-opus-4.7`）在 [OpenClaw](https://docs.openclaw.ai/) 沙箱内驱动一个**代码生成 Agent**。两个核心技巧：
>
> 1. **Context Optimization** — Coder Agent 通过 `@FILE.md` 引用 `workspace/skills/` 下的 Skill 定义文档，只把真正用得到的规范注入上下文。
> 2. **Error Correction** — Runner 捕获完整 Python Traceback，Diagnoser Agent 专门把 Traceback 翻译成可执行的 `Patch Plan`，反馈给 Coder 进行下一轮修复。
>
> 灵感与脚手架借鉴自同仓库的 [`OpenClaw_AgentHarness`](../OpenClaw_AgentHarness/README.md)。

---

## 架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│  iteration N                                                             │
│                                                                          │
│  Coder      读 SPEC.md → 解析 @SKILL.md 引用 → 仅加载被引用的 Skill       │
│             读 DIAGNOSIS.md（若存在）→ 写 solution.py                    │
│                                                                          │
│  Runner     在 OpenClaw sandbox 内运行 solution / pytest / smoke_test    │
│             逐字捕获 Traceback → 写 RUN_LOG.md                            │
│                                                                          │
│  if PASS → 退出 0                                                        │
│  if FAIL → Diagnoser 解析 Traceback → 写 DIAGNOSIS.md（Patch Plan）       │
│            进入 iteration N+1（Coder 读取 Patch Plan 修复）              │
└──────────────────────────────────────────────────────────────────────────┘
```

| Agent       | Emoji | 职责                                                  | 工具白名单            |
|-------------|------|------------------------------------------------------|---------------------|
| `coder`     | 🧑‍💻   | 读 SPEC + 被引用的 Skill + DIAGNOSIS，写 `solution.py`  | `read`, `write`, `edit` |
| `runner`    | 🏃   | 执行代码，把完整 Traceback 写进 `RUN_LOG.md`             | `read`, `write`, `exec` |
| `diagnoser` | 🩺   | 把 Traceback 翻译成 `Patch Plan`（`DIAGNOSIS.md`）       | `read`, `write` |

只有 `runner` 拥有 `exec`，并且 `tools.exec.allowedPaths` 仅放行 `workspace/code/`。

---

## 目录结构

```
CodingAgent/
├── README.md                ← 本文件
├── docker-compose.yml       ← secrets-init + openclaw + harness
├── .env.example             ← 复制成 .env 后填 COPILOT_GITHUB_TOKEN
├── setup.sh                 ← 一键引导
├── config/
│   └── openclaw.json        ← 三个 Agent 定义 + Copilot Provider
├── security/
│   └── secrets-init.sh      ← 启动期 Gateway Token 轮换
├── harness/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── openclaw_client.py   ← 经 docker exec 调用 OpenClaw CLI
│   └── orchestrator.py      ← 自循环主控（Coder → Runner → Diagnoser）
└── workspace/
    ├── AGENTS.md
    ├── skills/              ← Context Optimization 用的 Skill 文档
    │   ├── PYTHON_STYLE.md
    │   ├── ALGO_PATTERNS.md
    │   ├── ERROR_HANDLING.md
    │   └── TESTING.md
    └── code/
        ├── SPEC.md          ← 任务定义（含 @SKILL.md 引用）
        ├── solution.py      ← 由 Coder 产出
        ├── RUN_LOG.md       ← 由 Runner 产出（完整 Traceback）
        └── DIAGNOSIS.md     ← 由 Diagnoser 产出（Patch Plan）
```

---

## 技巧 1 · Context Optimization（Skill `@` 引用）

`workspace/code/SPEC.md` 里的「Required Skills」段：

```markdown
- @PYTHON_STYLE.md
- @ALGO_PATTERNS.md
- @ERROR_HANDLING.md
- @TESTING.md
```

Orchestrator 用一段正则 `r"@([A-Za-z0-9_\-]+\.md)"` 把这些引用解析出来，校验它们是否真的存在于 `workspace/skills/`，再把列表注入到 Coder Prompt 的 `# Skill References` 段。Coder 的系统提示里有硬性规则：**只读被列出的 Skill 文件，不许加载其它**。

要新增/替换技能，只需在 `workspace/skills/` 下放一个新的 Markdown，再在 `SPEC.md` 用 `@xxx.md` 引用即可。

---

## 技巧 2 · Error Correction（Traceback 闭环）

Runner 系统提示要求 `RUN_LOG.md` 必须包含：

```
## Result          PASS / FAIL
## Command         <运行命令>
## Exit Code       <整数>
## Stdout          ```<verbatim>```
## Stderr / Traceback   ```<verbatim Python traceback>```
```

Diagnoser 只在 `FAIL` 时被调用，输出固定结构的 `DIAGNOSIS.md`：

```
## Failure Signature   <ExceptionType: message>
## Root Cause          <2-4 sentences>
## Affected Lines      <file:line — code>
## Patch Plan          - imperative bullet 1
                       - imperative bullet 2
## Regression Risk     <one-liner>
```

下一轮 Coder 启动时，orchestrator 会在 Prompt 里点名：「读 DIAGNOSIS.md，逐条落实 Patch Plan」。这把「让 Copilot 看 Traceback 自己想办法」从一次随机调用，固化成了**结构化的修复合同**。

---

## 如何执行

本项目有 **两种运行入口**：

- **A. 命令行直接跑**（适合首次验证 / CI / 修改 SPEC.md 后批量跑题）
- **B. 通过 OpenCode 调用**（适合在对话里把它当工具用，详见后文 [给 OpenCode 调用](#给-opencode-调用mcp-集成)）

两种方式共用 [步骤 0–3](#步骤-0--环境前置) 的环境准备。

---

### 步骤 0 · 环境前置

| 依赖 | 用途 | 校验命令 |
|------|------|---------|
| Docker Desktop ≥ 24（含 compose v2） | 启动 secrets-init / openclaw / harness 三容器 | `docker compose version` |
| GitHub CLI（可选） | 一行拿到 Copilot token | `gh auth status` |
| 具备 Copilot 订阅的 GitHub 账户 | 调用 `claude-opus-4.7` | — |
| 端口 18790 空闲 | OpenClaw Gateway 对外端口（与 OpenClaw_AgentHarness 错开） | `lsof -i :18790` |

> **macOS 提示**：Docker Desktop 必须开着，且需要在 Settings → Advanced 勾上 **"Allow the default Docker socket to be used"**，因为 harness 容器要挂 `/var/run/docker.sock`。

---

### 步骤 1 · 拿到 Copilot Token 并写入 .env

```bash
cd /Users/lokinfey/Downloads/Samples/CodingAgent
cp .env.example .env
# 任选一种方式写入 token：
echo "COPILOT_GITHUB_TOKEN=$(gh auth token)" >> .env
# 或用编辑器把 .env 里的 ghu_replace_me 替换成你的 token
```

`.env` 至少需要这两项：

```bash
COPILOT_GITHUB_TOKEN=ghu_xxxxxxxxxxxxxxxxxxxxxxxxxxx
MAX_ITERATIONS=4
```

---

### 步骤 2 · 一键引导（只需做一次）

```bash
chmod +x setup.sh security/secrets-init.sh
./setup.sh
```

`setup.sh` 会：

1. 校验 docker / compose 可用；
2. 拉 `alpine:3.19` `python:3.12-slim` `ghcr.io/openclaw/openclaw:latest` 三个基础镜像；
3. `docker compose build harness` 生成 harness 镜像；
4. 给 `config/` `workspace/` 设置 700 权限。

成功结束时会打印 `Done.` 字样。

---

### 步骤 3 · 准备任务

仓库自带的 [workspace/code/SPEC.md](workspace/code/SPEC.md) 是「括号匹配」示例题，引用了 4 份 Skill。直接跑就能验证整条链路。

要换题目：

```bash
# 1) 编辑任务定义（可在 ## Required Skills 段用 @FILE.md 引用 workspace/skills/ 下的技能）
$EDITOR workspace/code/SPEC.md

# 2) 清掉上一轮的产物，避免误判
rm -f workspace/code/solution.py workspace/code/RUN_LOG.md \
      workspace/code/DIAGNOSIS.md workspace/code/smoke_test.py \
      workspace/code/test_solution.py
```

> 想新增技能？在 [workspace/skills/](workspace/skills) 下放一个 `MY_SKILL.md`，然后在 SPEC.md 里写 `- @MY_SKILL.md` 即可。

---

### 入口 A · 命令行执行

```bash
# 前台跑（推荐，看完整日志，按完成自动退出）
docker compose up --abort-on-container-exit harness

# 或后台跑 gateway，然后单独跑一次 harness
docker compose up -d openclaw
docker compose run --rm harness
```

**期望日志**：

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

**退出码**：harness 进程 `0 = PASS`，`1 = 用尽 MAX_ITERATIONS 仍 FAIL`，`2 = SPEC.md 缺失`。

**产物**（在宿主机的 `workspace/code/` 下，能直接 cat / 编辑器打开）：

| 文件 | 来源 | 含义 |
|------|------|------|
| `solution.py`    | Coder    | 最终代码 |
| `RUN_LOG.md`     | Runner   | `## Result` `## Stdout` `## Stderr / Traceback` |
| `DIAGNOSIS.md`   | Diagnoser | 仅在中途失败过才有；最后一轮通过则会被清掉 |

**调参**：

```bash
# 临时改最大迭代次数（也可写进 .env 的 MAX_ITERATIONS）
MAX_ITERATIONS=6 docker compose up --abort-on-container-exit harness

# 单独看 OpenClaw gateway 日志
docker logs -f codingagent-openclaw
```

---

### 入口 B · 通过 OpenCode 调用

详细说明见下方 [给 OpenCode 调用（MCP 集成）](#给-opencode-调用mcp-集成) 一节。最短路径：

```bash
pip install -r mcp/requirements.txt   # 安装 MCP SDK
opencode                              # 在 CodingAgent/ 目录启动 OpenCode
# 然后在 OpenCode 里：
#   /agent codingagent
#   写一个 LRU 缓存，遵守 @PYTHON_STYLE.md @ALGO_PATTERNS.md
```

OpenCode 会自动识别 [opencode.json](opencode.json)，启动 [mcp/mcp_server.py](mcp/mcp_server.py) 这个 stdio MCP server；server 在宿主机上 `docker compose up harness` 跑一遍流水线，把结果回传给 OpenCode。

---

### 步骤 4 · 复跑 / 换题

```bash
# 改 SPEC.md，清产物，再跑一次
$EDITOR workspace/code/SPEC.md
rm -f workspace/code/solution.py workspace/code/RUN_LOG.md workspace/code/DIAGNOSIS.md
docker compose up --abort-on-container-exit harness
```

> 不想清产物？orchestrator 在每轮开头会自动删掉 `solution.py` 和 `RUN_LOG.md`；`DIAGNOSIS.md` 只有在第 1 轮迭代时被清，后续保留作为反馈。手动清理只是为了避免读到上一次任务的旧产物。

---

## 关键设计点

### 模型走 Copilot 内置 Provider

`config/openclaw.json`：

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

鉴权来自 `COPILOT_GITHUB_TOKEN`（同步到 `GH_TOKEN`，匹配插件的多源探测顺序）。

### 工具白名单 — 精确到目录

```json
"tools": {
  "exec":  { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace/code"] },
  "read":  { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace"] },
  "write": { "enabled": true, "allowedPaths": ["/home/node/.openclaw/workspace"] }
}
```

每个 Agent 还在 `agents.list[].tools.deny` 上做二级裁剪，确保 Coder/Diagnoser 拿不到 `exec`，Runner 拿不到 `edit`。

### 启动期 Token 轮换

`security/secrets-init.sh` 在所有服务之前先跑一次，生成新的 Gateway Token，写入 tmpfs 卷 `/run/secrets/gateway-token`，并通过 `jq` 注入 `config/openclaw.json` 的 `gateway.auth.token` 与 `gateway.remote.token`。

### Workspace = 单一可信源

宿主机 `./workspace/` 同时挂到：

- OpenClaw 容器：`/home/node/.openclaw/workspace`（Agents 读写）
- Harness 容器：`/workspace`（编排器读写）

所以 `orchestrator.py` 在 Agent 写完文件后能立即在宿主机视图下校验产物。

---

## 排错

| 现象 | 排查 |
|------|------|
| `harness` 卡在 `Waiting for gateway` | `docker logs codingagent-openclaw`；多半是 `COPILOT_GITHUB_TOKEN` 没填或失效 |
| `Copilot token exchange failed: HTTP 403` / `model fallback decision: candidate_failed reason=auth` | `gh auth token` 直出的 PAT 通常没有 Copilot OAuth scope，gateway 实时换 token 会被 GitHub 拒绝。本项目的 [`security/secrets-init.sh`](security/secrets-init.sh) 已经按 [docs.openclaw.ai → Non-interactive onboarding](https://docs.openclaw.ai/providers/github-copilot#copilot-proxy-plugin-copilot-proxy) 把 token 直接写入 `config/agents/<id>/agent/auth-profiles.json` 让 gateway 读 stored profile（不再做 exchange）。如果仍 403，说明这枚 token 本身没有 Copilot 订阅；改用 device flow：<br/><br/>**device-flow 一次性引导**（见下文 [Copilot 凭据修复](#copilot-凭据修复)）：`docker compose down -v && docker compose up -d openclaw && docker exec -it codingagent-openclaw node /app/openclaw.mjs models auth login-github-copilot` |
| Coder 引用了不存在的 Skill | orchestrator 在启动日志里打印 `Skill references in SPEC.md`；不存在的 `@FILE.md` 会被静默丢弃 |
| Runner 报 `pytest not found` | 系统提示已包含 `pip install --quiet pytest` 兜底；若仍失败，确认 `tools.exec.enabled=true` |
| Diagnoser 不写 DIAGNOSIS.md | orchestrator 会打印 `⚠️ Diagnoser did not write DIAGNOSIS.md`；下一轮 Coder 会盲打。可以提高 `MAX_ITERATIONS` |
| 模型不存在 | `docker compose exec codingagent-openclaw openclaw models auth login --provider github-copilot --method device`，或把 primary 改成 `github-copilot/claude-sonnet-4.5` |

---

## Copilot 凭据修复

如果 gateway 持续报 `Copilot token exchange failed: HTTP 403`，说明 `.env` 里的 `COPILOT_GITHUB_TOKEN` 没有 Copilot OAuth scope（`gh auth token` 默认就是这种）。两条修复路径任选一条：

### 选项 A · 复用同仓库 OpenClaw_AgentHarness 已登录的凭据

如果你之前在 [`../OpenClaw_AgentHarness`](../OpenClaw_AgentHarness/README.md) 跑通过 device-flow，那里的凭据可以直接借用：

```bash
cd /Users/lokinfey/Downloads/Samples

# 1) 拷已交换的 Copilot API token cache
mkdir -p CodingAgent/config/credentials
cp OpenClaw_AgentHarness/config/credentials/github-copilot.token.json \
   CodingAgent/config/credentials/

# 2) 拷 auth-profile 给三个 agent
for AGENT in coder runner diagnoser; do
  mkdir -p CodingAgent/config/agents/$AGENT/agent
  cp OpenClaw_AgentHarness/config/agents/coder/agent/auth-profiles.json \
     CodingAgent/config/agents/$AGENT/agent/
  cp OpenClaw_AgentHarness/config/agents/coder/agent/auth-state.json \
     CodingAgent/config/agents/$AGENT/agent/ 2>/dev/null || true
done

# 3) 同步 .env，避免下次启动被 secrets-init 用旧 token 覆盖
WORKING_TOKEN=$(python3 -c "import json; print(json.load(open('OpenClaw_AgentHarness/config/agents/coder/agent/auth-profiles.json'))['profiles']['github-copilot:github']['token'])")
sed -i.bak "s|^COPILOT_GITHUB_TOKEN=.*|COPILOT_GITHUB_TOKEN=$WORKING_TOKEN|" CodingAgent/.env

cd CodingAgent
docker compose down -v
docker compose up --abort-on-container-exit harness
```

### 选项 B · 在 CodingAgent 容器内做一次 device-flow 登录（推荐，自给自足）

```bash
cd /Users/lokinfey/Downloads/Samples/CodingAgent

# 1) 干净启动，跳过 secrets-init 的 seed（让 .env 里 token 保持 ghu_replace_me）
docker compose down -v
sed -i.bak 's|^COPILOT_GITHUB_TOKEN=.*|COPILOT_GITHUB_TOKEN=ghu_replace_me|' .env
docker compose up -d openclaw

# 2) 在容器内交互式登录（必须 -it）
docker exec -it codingagent-openclaw \
  node /app/openclaw.mjs models auth login-github-copilot
# → 浏览器打开提示的 URL 输入 8 位 code → 终端等到 OK

# 3) 把 main 的 auth-profile 复用给三个 agent
for AGENT in coder runner diagnoser; do
  mkdir -p config/agents/$AGENT/agent
  cp config/agents/main/agent/auth-profiles.json \
     config/agents/$AGENT/agent/
done

# 4) .env 也同步成这枚新 token（让重启时 secrets-init 用一致的值）
NEW_TOKEN=$(python3 -c "import json; print(json.load(open('config/agents/main/agent/auth-profiles.json'))['profiles']['github-copilot:github']['token'])")
sed -i.bak "s|^COPILOT_GITHUB_TOKEN=.*|COPILOT_GITHUB_TOKEN=$NEW_TOKEN|" .env

# 5) 跑流水线
docker compose up --abort-on-container-exit harness
```

device-flow 拿到的 `ghu_...` token 自带 Copilot scope，gateway 的 `Copilot token exchange` 步骤会成功，并在 `config/credentials/github-copilot.token.json` 缓存短期 Copilot API token；缓存过期时 gateway 会用 stored `ghu_...` 重新 exchange，不需要你再操心。

---

## 给 OpenCode 调用（MCP 集成）

仓库带了一个 stdio MCP server，把整条流水线包装成 [OpenCode](https://opencode.ai) 可以直接调用的工具。

### 1. 安装 MCP SDK

```bash
pip install -r mcp/requirements.txt
```

### 2. 注册到 OpenCode

仓库根目录的 [opencode.json](opencode.json) 已经写好了 server + 一个 `codingagent` 模式 agent：

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

把这个文件留在 `CodingAgent/` 下，从该目录启动 OpenCode 即可被自动识别；或者把 `mcp` 段拷进 `~/.config/opencode/config.json` 做成全局工具。

### 3. 暴露的工具

| 工具 | 作用 |
|------|------|
| `codingagent_list_skills`        | 列出 `workspace/skills/` 下所有可用 Skill |
| `codingagent_read_skill(name)`   | 读取某个 Skill 的全文（OpenCode 用户可用作上下文参考） |
| `codingagent_add_skill(name, content)` | 写入新的 Skill 文件，未来 SPEC 用 `@<name>.md` 引用 |
| `codingagent_generate(spec, max_iterations?, timeout_seconds?)` | 把 SPEC 写入 `workspace/code/SPEC.md`，跑一遍 docker compose 流水线，返回最终 `solution.py` / `RUN_LOG.md` / `DIAGNOSIS.md` |

### 4. 在 OpenCode 里这样用

```text
> /agent codingagent
> 写一个 LRU 缓存类，键类型是 str，按 spec 提供的容量驱逐。要求遵守
> @PYTHON_STYLE.md @ALGO_PATTERNS.md @ERROR_HANDLING.md。
```

Agent 系统提示会让它先调 `codingagent_list_skills` 确认可用技能，再把用户需求改写成带 `## Required Skills` 段的 SPEC，最后调用 `codingagent_generate` 跑完整闭环。失败时返回 `DIAGNOSIS.md` 的 Patch Plan，OpenCode 用户可以再补一轮反馈。

### 注意

- MCP server 在**宿主机**上运行，通过 `docker compose -f docker-compose.yml up harness` 驱动流水线，所以 Docker daemon 要可用。
- 第一次调用前最好先跑过一次 `./setup.sh`，确保 `harness` 镜像、token 卷、`.env` 都已就绪。
- 若同时跑多个 `codingagent_generate` 调用，会争用同一个 workspace；建议串行调用（OpenCode 默认就是串行的工具调用）。

---

## 关闭

```bash
docker compose down -v   # -v 同时清掉 secrets 卷里的旧 token
```
