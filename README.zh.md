# 企业 Agent Workshop

面向工程团队的实战 Workshop，专注于**在企业内部构建可上生产的 Agent**。本仓库的示例会带你从「单进程的技能测试原型」一路走到「多 Agent 沙箱流水线」，最终落地到部署在 **Microsoft Foundry** 上、配套完整 Azure 基础设施的 hosted agent。

整个 Workshop 按 **一天**（约 6–8 小时的代码 + 幻灯片）的节奏设计。

Workshop 围绕四个工程关注点展开 —— 任何企业级 Agent 项目最终都绕不开这些问题：

| 关注点 | 对应目录 |
| --- | --- |
| **Skill 定义与对抗式测试** | [`Skill_Testing_Agent/`](Skill_Testing_Agent/)、[`AgentHarness_HostedAgent/`](AgentHarness_HostedAgent/) |
| **沙箱化的多 Agent 编排** | [`OpenClaw_AgentHarness/`](OpenClaw_AgentHarness/)、[`CodingAgent/`](CodingAgent/) |
| **Hosted Agent 运行时与 harness 架构（Brain / Hands / Session / Vault）** | [`AgentHarness_HostedAgent/`](AgentHarness_HostedAgent/) |
| **部署到 Microsoft Foundry** | [`skill-testing-harness-deploy/`](skill-testing-harness-deploy/) |

---

## Workshop 模块

### 1. `Skill_Testing_Agent/` — 对抗式 Skill 测试入门

一个最小化的 **Microsoft Agent Framework + GitHub Copilot SDK (Python)** 项目，用一个**对抗式测试 Agent** 去攻击一个「业务 Agent」（教育短视频脚本生成器，输出有严格模板）。在控制台并行对比两个模型 —— **Claude Opus 4.7** 与 **GPT-5.5**。

引入的核心概念：

- 一个具有**确定性输出契约**的业务 Agent。
- 一个能构造边界 prompt（单轮 + 多轮）的**对抗式测试 Agent**。
- 一个**不依赖 LLM** 的确定性 validator，校验契约。
- 一个 **LLM-as-judge** 评分器，从 5 个维度打分。
- 10 条精心设计的*边缘知识点*测试用例。

用这个模块教团队如何在引入任何基础设施之前，就先**定义一个 skill、写出它的评估方法、并能讲清楚不同模型的差异**。

### 2. `OpenClaw_AgentHarness/` — 多 Agent 沙箱流水线

一个用 Docker Compose 启动的小型流水线，引入 **[OpenClaw](https://docs.openclaw.ai/)** 作为沙箱 / 网关。三个最小权限的 Agent 在共享 Workspace 里通过自闭环协作：

| Agent | 角色 | 工具白名单 |
| --- | --- | --- |
| **A — Coder** | 读 `SPEC.md`，写 `solution.py` | `read`、`write`、`edit` |
| **B — Tester** | 读规范 + 实现，写 `test_solution.py` | `read`、`write`、`edit` |
| **C — Runner** | 在沙箱内跑 `pytest`，写 `RUN_REPORT.md` | `read`、`write`、**`exec`** |

只有 Agent C 拥有 `exec` 能力，并且通过 `tools.exec.allowedPaths` 把执行范围严格限定在一个子目录内。模型走 GitHub Copilot 内置 Provider（Claude Opus 4.7）。

这个模块讲清楚：**工具白名单、Workspace 隔离、基于 Gateway 的凭据轮换、自纠错闭环**。

### 3. `CodingAgent/` — Context 优化与错误纠正

一个更进阶的 OpenClaw 流水线，聚焦两项可上生产的工程技巧：

1. **Context Optimization（上下文优化）** —— `coder` Agent 只加载 `SPEC.md` 中通过 `@FILE.md` 显式引用的 Skill 文档（`workspace/skills/PYTHON_STYLE.md`、`ALGO_PATTERNS.md`、`ERROR_HANDLING.md`、`TESTING.md`），保持 prompt window 精简且可控。
2. **Error Correction（错误纠正）** —— 一个独立的 `diagnoser` Agent，把捕获的 Python Traceback 翻译成机器可读的 **Patch Plan**（`DIAGNOSIS.md`），供下一轮 `coder` 直接消费。

三个角色 —— `coder`、`runner`、`diagnoser`，各自带一套严格的工具白名单 —— 演示了如何**在控制 token 开销的前提下扩展自愈式编码循环**。

### 4. `AgentHarness_HostedAgent/` — Microsoft Foundry 上的 Hosted Agent

整个 Workshop 的旗舰模块。它在 **managed-style hosted-agent harness** 上重写了 `Skill_Testing_Agent` 的逻辑，采用四层架构：

```
       ┌──────────────────────────┐    execute(name,input) -> str       ┌──────────┐
       │   Orchestrator (Brain)   │ ───────────────────────────────────▶│  Hands   │
       │  Foundry hosted agent    │                                     │ (sandbox │
       │  （默认 gpt-5.5）        │  emit_note / get_events / list_*    │  cattle) │
       └──────────────┬───────────┘                                     └──────────┘
                      │
                      ▼
       ┌──────────────────────────┐
       │       SessionStore       │  append-only 日志，独立于 brain 的 context window
       └──────────────────────────┘
```

- **Brain** —— `SkillTestingHarness` agent，运行在 `ResponsesHostServer`（Foundry hosted agent / Responses 协议）。对外只暴露 5 个工具：`execute`、`list_tools`、`list_models`、`get_events`、`emit_note`。
- **Hands** —— 一次性、无状态的 `SandboxPool`。本项目注册了 7 个 hand：`list_test_cases`、`run_business_agent`、`validate_format`、`judge_rubric`、`craft_attack`、`next_attack_prompt`、`run_full_benchmark`。
- **Session** —— 文件级 append-only 日志，与 brain 的 context window 解耦；通过 `wake(session_id)` 可以恢复。
- **Vault** —— 凭据按逻辑名注册，sandbox 内的 hand 永远拿不到原始 token。

被测对象是 Microsoft Foundry 上的两个部署：`DeepSeek-V4-Flash` 与 `gpt-5.5`。模块附带一个 CLI runner（[`main_local.py`](AgentHarness_HostedAgent/main_local.py)）用来快速对比模型，以及一个讲 Responses 协议的 hosted 入口（[`main.py`](AgentHarness_HostedAgent/main.py)）。

这个模块讲清楚：**Brain / Hands / Session / Vault 的分层**，以及如何让一个企业级 harness 既好调试、可恢复，又凭据安全。

### 5. `skill-testing-harness-deploy/` — 用 `azd` 部署到 Microsoft Foundry

一个由 [`azure.yaml`](skill-testing-harness-deploy/azure.yaml) + Bicep 组成的部署包，用 `azd up` 把 harness 作为 hosted agent（`host: azure.ai.agent`）发布上去。完整演示 IaC 工作流：容器资源、启动命令、远程构建、`azure.ai.agents` 扩展。

### 6. `ppt/` — Workshop 幻灯片

随代码一起交付的讲义，建议讲解顺序：

1. `00.enterprise-agent-evolution.pptx` —— 为什么要做企业级 Agent，以及这个领域的演进。
2. `01.openclaw-orchestration-deep-practice.pptx` —— OpenClaw 多 Agent 编排深度实战。
3. `02.token-economics-cost-control.pptx` —— 真实负载下的 Token 经济学与成本控制。
4. `03.skill-definition-and-testing-standards.pptx` —— Skill 定义与对抗测试规范。
5. `04.coding-agent-token-report.pptx` —— Coding Agent 闭环的 token 使用复盘。
6. `05.agent-harness-.pptx` —— Brain / Hands / Session / Vault harness 走读。

---

## 一天的建议节奏

一天（约 6–8 小时）的可行编排：

| 时段 | 模块 | 配套幻灯片 |
| --- | --- | --- |
| **上午 · 概念** | `Skill_Testing_Agent/` —— 建立词汇：业务 Agent、对抗 Agent、validator、judge、边缘用例 | `00`、`03` |
| **上午下半段** | `OpenClaw_AgentHarness/` —— 沙箱、工具白名单、Gateway Token、多 Agent 文件协作 | `01` |
| **下午 · 实操** | `CodingAgent/` —— 上下文优化（`@SKILL.md`）+ diagnoser 驱动的错误纠正循环 | `02`、`04` |
| **下午下半段** | `AgentHarness_HostedAgent/` —— 重构为 Brain / Hands / Session / Vault 架构的 hosted agent，跑在 Microsoft Foundry 上 | `05` |
| **收尾** | `skill-testing-harness-deploy/` —— 用 `azd up` 上线 | — |

---

## 环境准备

整个 Workshop 跑在统一的基础环境上：

1. **Python 3.12+**
2. **GitHub Copilot** 订阅（参与者的 GitHub 账号需启用 Copilot 席位）。
3. **GitHub Copilot CLI** —— 已安装并完成登录：
   ```bash
   # 如未安装 GitHub CLI，先安装：https://cli.github.com/
   gh extension install github/gh-copilot
   # 或使用独立的 copilot CLI：https://github.com/github/copilot-cli
   copilot auth login
   ```
4. **Microsoft Foundry** —— 一个 Azure 订阅，包含 Foundry 项目 endpoint，并部署有 `DeepSeek-V4-Flash` 和 `gpt-5.5`（部署名可通过环境变量改）。

各模块的额外依赖：

| 模块 | 额外依赖 |
| --- | --- |
| `OpenClaw_AgentHarness/`、`CodingAgent/` | Docker + Docker Compose，`COPILOT_GITHUB_TOKEN` |
| `AgentHarness_HostedAgent/` | Azure CLI（`az login`）—— 用 `DefaultAzureCredential` |
| `skill-testing-harness-deploy/` | Azure Developer CLI（`azd`），订阅里有 Foundry 配额 |

---

## 适用人群

已经在生产环境交付软件、并准备解决以下问题的企业内部工程团队：

- 用**可测试的契约**而不是自由 prompt 来定义 skill。
- 搭建符合**最小权限原则**的多 Agent 流水线。
- 在真实负载下讨论 **Token 经济学**与 context window。
- 把笔记本上的原型迁移到 **Foundry 托管 + IaC 部署**的 Agent 运行时。

> 整套材料以代码优先 —— 幻灯片里出现的每个概念都能在某个目录里找到可运行的对应实现。

> English README: [README.md](README.md).
