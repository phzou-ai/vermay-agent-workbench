from __future__ import annotations

from .models import MessageRecord
from .store import MainAgentStore


def recent_messages(store: MainAgentStore, context_id: str, *, limit: int = 10) -> list[MessageRecord]:
    if limit <= 0:
        return []
    return store.list_context_messages(context_id, limit=limit)
