# Mini Agent Workbench

本项目用于学习 Agent Harness 的底层机制。

当前实现为 Phase 1：手写 mini runtime，不依赖 LangGraph。目标是显式展示 Agent runtime 中的核心组件：

- Context builder
- Tool registry
- Tool executor
- Observation handler
- Permission gate
- Trace logger
- Error recovery
- Minimal model client

Demo 主题：DevOps Assistant。

## 运行方式

创建并启用本地 Python 环境：

```bash
cd /Users/phzou/Documents/Code/AI/agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

运行 CLI：

```bash
cd /Users/phzou/Documents/Code/AI/agent
mini-agent "check cluster status"
```

默认 runtime 是 Phase 1 handwritten runtime。可切换到 Phase 2 LangGraph runtime：

```bash
mini-agent "grep nginx errors" --runtime langgraph
```

更多示例：

```bash
mini-agent "show pod status"
mini-agent "check real cluster pods"
mini-agent "grep nginx errors"
mini-agent "weather forecast for Shanghai"
mini-agent "read nginx log"
mini-agent "apply deployment fix"
```

默认模型是 Ollama 中的 `deepseek-v4-flash:cloud`。

CLI 默认会在 stderr 输出 Rich trace view，用于观察完整 harness loop：

```text
Agent Run
Step 1 · Context Build
Step 1 · Model Call
Step 1 · Model Response
Step 1 · Tool Call
Step 1 · Permission Gate
Step 1 · Tool Execute
Step 1 · Tool Result
Step 1 · Observation
Step 2 · Context Build
Step 2 · Model Call
Step 2 · Model Response
Step 2 · Final Answer
```

完整机器可读轨迹写入 `traces/*.jsonl`，包含每次 model response、tool call、permission decision、tool result 和 observation。

如需只保留最终 stdout：

```bash
mini-agent "check real cluster pods" --no-progress
```

限制最大模型调用次数：

```bash
mini-agent "check real cluster pods" --max-steps 3
```

运行测试：

```bash
.venv/bin/python -m pytest
```

## 使用 Ollama

先确认 Ollama 已启动，并且模型可用：

```bash
ollama serve
ollama list
```

运行：

```bash
mini-agent "check cluster status"
```

也可以换成本机已有模型：

```bash
mini-agent "grep nginx errors" \
  --ollama-model qwen3.6:27b
```

Ollama adapter 使用本地 HTTP `/api/chat`，要求模型返回严格 JSON：

```json
{"action":"final","content":"..."}
```

或：

```json
{"action":"tool_call","name":"kubectl_get","arguments":{"resource":"pods"}}
```

## 使用真实 Kubernetes 集群

Demo 同时提供 mock 工具和 SSH-backed 只读工具。

SSH 配置位于：

```text
data/ssh_config.json
```

当前配置：

```json
{
  "target": "phzou@nuc.server.lan",
  "port": 22,
  "strictHostKeyChecking": true,
  "updateHostKeys": true,
  "identityFile": "~/.ssh/openclaw_nuc_ed25519",
  "knownHostsFile": "~/.ssh/known_hosts"
}
```

只读 SSH 工具：

- `ssh_kubectl_get`
- `ssh_kubectl_describe`

示例：

```bash
mini-agent "check real cluster pods"
mini-agent "describe real api pod in default namespace"
```

SSH 工具使用严格 allowlist，不暴露任意 SSH 命令执行。当前支持：

- `kubectl get pods|services|deployments|nodes|namespaces|events`
- `kubectl describe pod|service|deployment|node`

远端 Kubernetes 命令会按顺序尝试：

1. `kubectl`
2. `microk8s kubectl`
3. `/snap/bin/microk8s kubectl`

这用于兼容 MicroK8s 在非交互 SSH shell 中 `/snap/bin` 不在 PATH 的情况。

本机需要满足：

- `~/.ssh/openclaw_nuc_ed25519` 存在并可读。
- `~/.ssh/known_hosts` 中已有 `nuc.server.lan` 的 host key。
- 目标机器可通过 `kubectl` 或 `microk8s kubectl` 访问集群。

## 使用天气工具

天气工具：

- `weather_forecast`

示例：

```bash
mini-agent "weather forecast for Shanghai"
mini-agent "will it rain in San Francisco tomorrow?"
```

该工具通过 `wttr.in` 获取当前天气和 1-3 天天气预报，属于安全只读工具。

## 当前安全策略

危险工具不会自动执行。

当前危险工具：

- `exec_shell`
- `kubectl_apply`
- `delete_resource`

当模型请求危险工具时，runtime 会记录 approval_required 事件并停止执行。

## 目录结构

```text
mini_agent/
  infra/
    ssh.py
  model_clients/
    ollama.py
    protocol.py
  tools/
    devops/
      registry.py
      mock.py
      remote_kubernetes.py
      dangerous.py
    weather/
      registry.py
      forecast.py
  runtime.py
  context_builder.py
  tool_registry.py
  tool_executor.py
  observation.py
  permission.py
  memory.py
  trace.py
  main.py
mini_agent_langgraph/
  state.py
  graph.py
  nodes.py
  routing.py
  adapters.py
  runner.py
data/
  cluster.json
  nginx.log
  ssh_config.json
traces/
```

## Phase 1 范围

包含：

- 最小 agent loop
- mock tools
- 危险工具审批拦截
- observation 格式化
- JSONL trace
- 简单短期 memory
- error recovery 基础路径

不包含：

- LangGraph
- MCP
- A2A
- 长期 memory
- 多模型路由
- self-evolving
- UI

这些内容后续阶段再加入。

## 项目文档

当前 runtime 的现状报告和后续 LangGraph 取舍记录位于：

- [docs/agent-runtime/README.md](docs/agent-runtime/README.md)
- [docs/agent-runtime/current-state.md](docs/agent-runtime/current-state.md)
