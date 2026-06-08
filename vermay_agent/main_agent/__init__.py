"""Protocol-independent main-agent core primitives."""

from .core import MainAgentCore
from .dev import DevMockLocalMessageResponder, DevMockLocalTaskRunner, DevMockRuntime, build_dev_mock_runtime
from .models import (
    ArtifactRecord,
    ContextRecord,
    DelegatedTaskRecord,
    DeleteContextResult,
    LocalMessageResult,
    LocalTaskResult,
    MainAgentRequest,
    MainAgentResult,
    MessageRecord,
    MessageRole,
    RegisteredAgentRecord,
    RemoteAgentResult,
    RouteDecisionKind,
    RouteDecisionRecord,
    TaskEventRecord,
    TaskRecord,
    TaskStatus,
)
from .responder import DirectModelLocalMessageResponder, LocalMessageResponder
from .remote_agent import (
    DirectA2ARemoteAgentClient,
    RemoteAgentClient,
    RemoteAgentSendResult,
    RemoteAgentTaskSnapshot,
    fetch_agent_card,
)
from .router import (
    DefaultMainAgentRouter,
    DirectModelRouterModelClient,
    MainAgentRouteDecision,
    MainAgentRouter,
    RouterModelClient,
    RouterModelDecision,
)
from .store import MainAgentStore
from .task_runner import DirectLangGraphLocalTaskRunner, LocalTaskRunner, LocalTaskRunResult

__all__ = [
    "ArtifactRecord",
    "ContextRecord",
    "DelegatedTaskRecord",
    "DeleteContextResult",
    "DirectA2ARemoteAgentClient",
    "DefaultMainAgentRouter",
    "DevMockLocalMessageResponder",
    "DevMockLocalTaskRunner",
    "DevMockRuntime",
    "DirectModelLocalMessageResponder",
    "DirectModelRouterModelClient",
    "DirectLangGraphLocalTaskRunner",
    "LocalMessageResult",
    "LocalTaskResult",
    "LocalMessageResponder",
    "LocalTaskRunner",
    "LocalTaskRunResult",
    "MainAgentCore",
    "MainAgentStore",
    "MainAgentRequest",
    "MainAgentResult",
    "MainAgentRouteDecision",
    "MainAgentRouter",
    "MessageRecord",
    "MessageRole",
    "RegisteredAgentRecord",
    "RemoteAgentClient",
    "RemoteAgentResult",
    "RemoteAgentSendResult",
    "RemoteAgentTaskSnapshot",
    "RouteDecisionKind",
    "RouteDecisionRecord",
    "RouterModelClient",
    "RouterModelDecision",
    "TaskEventRecord",
    "TaskRecord",
    "TaskStatus",
    "build_dev_mock_runtime",
    "fetch_agent_card",
]
