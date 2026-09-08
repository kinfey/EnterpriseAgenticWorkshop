# AgentHarness Docker Sandbox

基于 Microsoft Agent Framework 与 GitHub Copilot 的对抗式 Skill-Testing Harness。系统**只部署到本机 Docker Sandbox microVM**，不创建、不连接、也不依赖任何 Azure 资源。

## 架构

```text
本机 Host
├── sbx CLI
├── 项目 workspace（读写挂载）
└── 127.0.0.1:18088
      │
      ▼
Docker Sandbox microVM
├── FastAPI 服务
│   ├── GET /health
│   └── POST /responses
├── Orchestrator Agent
│   ├── GitHubCopilotAgent
│   ├── 模型：GPT-6 Astra
│   └── 工具：execute / list_tools / list_models / get_events / emit_note
├── HandPool（进程内调度）
│   ├── Business Agent ───────┐
│   ├── Adversarial Agent ────┼── GitHub Copilot SDK/runtime
│   ├── LLM Judge ────────────┘      ├── GPT-6 Astra
│   └── Deterministic Validator      └── GPT-5.6 Sol
├── SessionStore
│   └── /home/agent/state/sessions
├── sandbox 内 Python 虚拟环境
│   └── /home/agent/.venvs/skill-testing-harness
├── 独立 filesystem / network
└── 独立 Docker daemon
      │
      └── outbound HTTPS → GitHub Copilot API
```

Docker Sandbox 是唯一运行与隔离边界：

- 不使用 Azure、Foundry、ACR、Bicep、`azd` 或 Managed Identity。
- GitHub Copilot 提供全部模型推理。
- GPT-6 Astra 是默认 Orchestrator，同时参与模型对比。
- GPT-5.6 Sol 是第二个被测模型。
- 项目目录是唯一可写宿主 workspace。
- Session 与 Python 虚拟环境保存在 sandbox 内，停止后仍保留。
- 不挂载宿主机 Docker socket；Agent 创建的容器运行在 microVM 自己的
  Docker daemon 中。
- `HandPool` 只是函数调度器，不是第二层安全 sandbox。所有安全隔离都由
  外层 Docker Sandbox microVM 提供。

### 请求链路

1. 客户端向宿主机 `18088` 端口发送 `POST /responses`。
2. Docker Sandbox 将请求转发到 microVM 内 FastAPI 的 `8088` 端口。
3. GPT-6 Astra Orchestrator 选择并调用注册的 harness 工具。
4. `HandPool` 调度业务 Agent、对抗 Agent、validator 或 judge。
5. 需要 LLM 的 hand 通过 GitHub Copilot SDK 创建独立会话，并选择
   `gpt-6-astra` 或 `gpt-5.6-sol`。
6. 工具事件和响应摘要追加写入 `SessionStore`。
7. FastAPI 返回包含 `id`、`model` 和 `output_text` 的响应。

该端点是项目自身实现的轻量 Responses-style API，不依赖任何云端 Hosted
Agent 服务。

### 状态与安全边界

| 边界 | 位置 | 持久性 |
| --- | --- | --- |
| 源代码与 benchmark 产物 | 挂载的项目 workspace | 保存在宿主机 |
| Python 包与 Copilot runtime cache | Docker Sandbox microVM | stop/start 后保留 |
| Harness session events | `/home/agent/state/sessions` | stop/start 后保留 |
| Copilot OAuth 登录 | sandbox 内 Copilot 配置 | 删除 sandbox 时销毁 |
| Agent 创建的 Docker images/containers | sandbox 内 Docker daemon | 删除 sandbox 时销毁 |

## 前置条件

安装 Docker Sandboxes：

```bash
brew trust docker/tap
brew install docker/tap/sbx
sbx login
```

首次创建后，在 sandbox 内完成 GitHub Copilot OAuth 登录。凭据保存在 microVM 内，不写入仓库或镜像：

```bash
./scripts/docker-sandbox.sh setup
./scripts/docker-sandbox.sh login
```

如果 CLI 询问是否在没有系统 keychain 的 Linux microVM 中使用 plaintext storage，请确认。该文件只存在于隔离 sandbox，执行 `remove` 时会一并删除。

## 直接部署

首次部署需要完成环境创建与 Copilot 登录：

```bash
./scripts/docker-sandbox.sh plan
./scripts/docker-sandbox.sh setup
./scripts/docker-sandbox.sh login
./scripts/docker-sandbox.sh run
```

后台启动：

```bash
./scripts/docker-sandbox.sh start
```

服务端点：

```text
GET  http://localhost:18088/health
POST http://localhost:18088/responses
```

调用示例：

```bash
curl -s http://localhost:18088/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": "请把 edge-03 分别用 GPT-6 Astra 和 GPT-5.6 Sol 跑三轮，并给出 rubric 评分。"
  }'
```

## Sandbox 管理

```bash
./scripts/docker-sandbox.sh setup
./scripts/docker-sandbox.sh shell
./scripts/docker-sandbox.sh status
./scripts/docker-sandbox.sh stop
./scripts/docker-sandbox.sh remove
```

环境配置：

| 配置 | 值 |
| --- | --- |
| Sandbox agent | `copilot`（Docker 官方 Copilot kit） |
| Orchestrator | `gpt-6-astra` |
| Test model 1 | `gpt-6-astra` |
| Test model 2 | `gpt-5.6-sol` |
| CPU / Memory | 4 CPU / 8 GiB |
| Host / Sandbox port | `18088 / 8088` |
| PyPI source | `https://packagefeedproxy.microsoft.io/pypi/simple` |

可通过可选 `.env` 覆盖模型 ID，但仓库中的默认值保持 GPT-6 Astra 与
GPT-5.6 Sol：

```bash
cp .env.example .env
```

## CLI Benchmark

```bash
./scripts/docker-sandbox.sh shell

/home/agent/.venvs/skill-testing-harness/bin/python main_local.py
/home/agent/.venvs/skill-testing-harness/bin/python main_local.py --model astra
/home/agent/.venvs/skill-testing-harness/bin/python main_local.py --model sol
/home/agent/.venvs/skill-testing-harness/bin/python main_local.py --only edge-03
```

## 核心文件

```text
sbxenv.yaml                 # Docker Sandbox、模型与端口
scripts/docker-sandbox.sh   # 创建、安装、运行与删除
main.py                     # 本地 FastAPI + Copilot Orchestrator
main_local.py               # 双模型 benchmark
harness/hands.py            # 进程内 hand 调度
harness/session.py          # append-only session log
skills/copilot_factory.py   # GitHubCopilotAgent 工厂
skills/                     # business / attacker / validator / judge
```

参考：

- [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/)
- [Docker Sandbox Copilot integration](https://docs.docker.com/ai/sandboxes/agents/copilot/)
- [Agent Framework GitHub Copilot](https://github.com/microsoft/agent-framework/tree/main/python/packages/github_copilot)
