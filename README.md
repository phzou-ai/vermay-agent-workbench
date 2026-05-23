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

```bash
cd /Users/phzou/Documents/Code/AI/agent
python3 -m mini_agent.main "check cluster status"
```

更多示例：

```bash
python3 -m mini_agent.main "show pod status"
python3 -m mini_agent.main "check real cluster pods"
python3 -m mini_agent.main "grep nginx errors"
python3 -m mini_agent.main "read nginx log"
python3 -m mini_agent.main "apply deployment fix"
```

默认模型是 Ollama 中的 `deepseek-v4-flash:cloud`。

CLI 默认会在 stderr 输出进度日志，用于区分模型调用、工具执行和最终回答阶段：

```text
[agent] step 1/5: building context
[agent] step 1/5: calling model
[agent] step 1/5: model response Calling tool ssh_kubectl_get.
[agent] step 1/5: tool_call {"name": "ssh_kubectl_get", "arguments": {"resource": "pods"}}
[agent] step 1/5: permission allowed=True requires_approval=False reason=safe tool
[agent] step 1/5: executing tool ssh_kubectl_get
[agent] step 1/5: tool_result ok=True exit_code=0 command=ssh ...
[agent] step 1/5: observation {"ok": true, ...}
```

完整结构化轨迹写入 `traces/*.jsonl`，包含每次 model response、tool call、permission decision、tool result 和 observation。

如需只保留最终 stdout：

```bash
python3 -m mini_agent.main "check real cluster pods" --no-progress
```

限制最大模型调用次数：

```bash
python3 -m mini_agent.main "check real cluster pods" --max-steps 3
```

## 使用 Ollama

先确认 Ollama 已启动，并且模型可用：

```bash
ollama serve
ollama list
```

运行：

```bash
python3 -m mini_agent.main "check cluster status"
```

也可以换成本机已有模型：

```bash
python3 -m mini_agent.main "grep nginx errors" \
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
  "workspaceRoot": "/home/phzou/openclaw-sandboxes",
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
python3 -m mini_agent.main "check real cluster pods"
python3 -m mini_agent.main "describe real api pod in default namespace"
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
  runtime.py
  context_builder.py
  tool_registry.py
  tool_executor.py
  observation.py
  permission.py
  memory.py
  trace.py
  models.py
  main.py
  tools/
    devops.py
data/
  cluster.json
  nginx.log
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
