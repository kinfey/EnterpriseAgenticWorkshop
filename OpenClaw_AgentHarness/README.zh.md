# OpenClaw Agent Harness · 自循环测试流水线

> **Agent A 写代码 → Agent B 写测试 → Agent C 在 OpenClaw 沙箱中执行并反馈**
>
> 全部基于 [OpenClaw](https://docs.openclaw.ai/) Docker Gateway 与多 Agent Workspace，模型走 GitHub Copilot 内置 Provider 的 **Claude Opus 4.7**。

---

## 它是什么

一个用 Docker Compose 启动的小型多 Agent 流水线。三个互不越权的 Agent 通过共享的 [OpenClaw Workspace](https://docs.openclaw.ai/concepts/agent-workspace) 协作完成一项「自我闭环」的代码 → 测试 → 运行 → 反馈循环：

| Agent | 角色 | 工具集 (allowlist) |
|-------|------|-------------------|
| **Agent A — Coder** 🧑‍💻 | 读 `SPEC.md`，把实现写到 `solution.py`。如果上一轮有失败报告，按报告里的「Suggested Fixes」修复 | `read`, `write`, `edit` |
| **Agent B — Tester** 🧪 | 读规范 + 实现，把 pytest 用例写到 `test_solution.py` | `read`, `write`, `edit` |
| **Agent C — Runner** 🏃 | 在 [OpenClaw Multi-Agent Sandbox](https://docs.openclaw.ai/tools/multi-agent-sandbox-tools) 里执行 pytest，并把通过/失败结果写成 `RUN_REPORT.md` | `read`, `write`, **`exec`** |

只有 Agent C 拥有 `exec` 工具，并且通过 `tools.exec.allowedPaths` 把可执行范围严格限制在 `workspace/code/` 一个子目录里。

参考的官方文档：

- 安装：<https://docs.openclaw.ai/install/docker>
- 多 Agent 沙箱工具：<https://docs.openclaw.ai/tools/multi-agent-sandbox-tools>
- Workspace 概念：<https://docs.openclaw.ai/concepts/agent-workspace>
- GitHub Copilot Provider：<https://docs.openclaw.ai/providers/github-copilot>

灵感来源：<https://github.com/kinfey/Multi-AI-Agents-Cloud-Native/tree/main/code/openclaw_security>

---

## 目录结构

```
OpenClaw_AgentHarness/
├── README.md                ← 本文件
├── docker-compose.yml       ← secrets-init + openclaw + harness 三容器
├── .env.example             ← 把它复制成 .env 后填入 COPILOT_GITHUB_TOKEN
├── setup.sh                 ← 一键引导
├── config/
│   └── openclaw.json        ← 三个 Agent + GitHub Copilot Provider + 工具白名单
├── security/
│   └── secrets-init.sh      ← 每次启动轮换 Gateway Token
├── workspace/               ← OpenClaw Agent Workspace（容器里挂在 /home/node/.openclaw/workspace）
│   ├── AGENTS.md
│   ├── IDENTITY.md
│   └── code/
│       └── SPEC.md          ← 任务规范（自带一个示例：括号匹配函数）
└── harness/
    ├── Dockerfile
    ├── requirements.txt
    ├── openclaw_client.py   ← 调用 OpenClaw Gateway 的封装
    └── orchestrator.py      ← 自循环主控，A → B → C → 反馈 → A …
```

---

## 一次完整流程

```
┌─────────────────────────────────────────────────────────────────────┐
│  iteration N                                                        │
│                                                                     │
│  orchestrator → POST /v1/chat/completions  (model=openclaw:coder)   │
│      ↳ Agent A 读 SPEC.md (+ 上轮 RUN_REPORT.md) → 写 solution.py   │
│                                                                     │
│  orchestrator → POST /v1/chat/completions  (model=openclaw:tester)  │
│      ↳ Agent B 读 SPEC.md + solution.py → 写 test_solution.py       │
│                                                                     │
│  orchestrator → POST /v1/chat/completions  (model=openclaw:runner)  │
│      ↳ Agent C 在 sandbox 内 exec  pytest -v                        │
│        → 写 RUN_REPORT.md (PASS / FAIL + Suggested Fixes)           │
│                                                                     │
│  orchestrator 解析报告:                                              │
│      PASS → 退出，状态码 0                                           │
│      FAIL → 进入 iteration N+1（Agent A 会读到失败原因继续修复）      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 准备 GitHub Copilot Token

OpenClaw 的 [github-copilot Provider](https://docs.openclaw.ai/providers/github-copilot) 默认模型即为 `github-copilot/claude-opus-4.7`。准备一份具备 Copilot 订阅的 GitHub Token：

```bash
# 已安装 gh CLI 且已登录的最简方式：
gh auth token
```

### 2. 配置 .env

```bash
cd OpenClaw_AgentHarness
cp .env.example .env
# 编辑 .env，填入：
#   COPILOT_GITHUB_TOKEN=<上一步拿到的 token>
```

### 3. 一键引导

```bash
chmod +x setup.sh && ./setup.sh
```

### 4. 跑一轮流水线

```bash
docker compose up --abort-on-container-exit harness
```

期望日志：

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

最终 `workspace/code/` 目录里会有：

- `solution.py` — Agent A 的代码
- `test_solution.py` — Agent B 的 pytest 用例
- `RUN_REPORT.md` — Agent C 的执行报告

### 5. 换一个题目

修改 [workspace/code/SPEC.md](workspace/code/SPEC.md)，删除 `solution.py / test_solution.py / RUN_REPORT.md`，再次执行第 4 步即可。

---

## 关键设计要点

### 模型 — Claude Opus 4.7

`config/openclaw.json` 中：

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

Provider 级配置走 OpenClaw 的内置 `github-copilot` 插件，鉴权来自环境变量 `COPILOT_GITHUB_TOKEN`（同时同步到 `GH_TOKEN`，匹配插件的多源探测顺序）。

### 工具白名单 — 精确到目录

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

每个 Agent 又在 `agents.list[].tools.allow / deny` 上做了二级裁剪，确保 Coder/Tester 拿不到 `exec`，Runner 拿不到 `edit`/`apply_patch`。

### 启动期 Token 轮换

`security/secrets-init.sh` 容器在所有服务启动之前先跑一次，生成新的 64 位随机 Gateway Token，写入 `tmpfs` 卷 `/run/secrets/gateway-token`，并用 `jq` 把它注入到 `config/openclaw.json` 的 `gateway.auth.token` 字段。Harness 容器以只读方式挂载同一个 tmpfs 卷取 token；OpenClaw 容器以只读方式挂载，并设置 `OPENCLAW_TOKEN_FILE=/run/secrets/gateway-token`。

### Workspace = 单一可信源

宿主机 `./workspace/` 同时挂到：

- OpenClaw 容器里的 `/home/node/.openclaw/workspace`（Agents 读写）
- Harness 容器里的 `/workspace`（编排器读写）

所以 `orchestrator.py` 可以在 Agent 写完文件后立即在宿主机视图下检查产物是否生成。

---

## 排错

| 现象 | 排查 |
|------|------|
| `harness` 卡在 `Waiting for gateway` | `docker logs openclaw`，确认 healthcheck 返回 200。一般是 `COPILOT_GITHUB_TOKEN` 没填或失效 |
| `agent 'coder' HTTP 401` | Token 轮换不一致。`docker compose down -v && ./setup.sh` 重置 tmpfs 卷 |
| Runner 报 `pytest not found` | Runner prompt 里已经做了 `pip install pytest` 的兜底；如果还是失败，确认 `tools.exec.enabled=true` 且未把 Runner 的 `exec` 在 `agents.list[]` 里 deny 掉 |
| 模型不存在 | 确认你的 GitHub 账户 Copilot 订阅可访问 `claude-opus-4.7`。否则把 `agents.defaults.model.primary` 换成 `github-copilot/claude-sonnet-4.5` 或运行一次 `docker compose exec openclaw openclaw models auth login --provider github-copilot --method device` |

---

## 关闭

```bash
docker compose down -v   # -v 同时清掉 secrets 卷里的旧 token
```
