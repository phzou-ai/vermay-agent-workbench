from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import BaseMessage, SystemMessage

from .memory import SQLiteMemoryStore
from .skills import SkillStore


@dataclass
class RuntimeContextProvider:
    memory: SQLiteMemoryStore | None = None
    skills: SkillStore | None = None
    memory_limit: int = 5
    skill_limit: int = 3

    def context_messages(self, user_input: str) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        if self.memory is not None:
            memory_items = self.memory.retrieve(user_input, limit=self.memory_limit)
            if memory_items:
                content = "\n".join(f"- [{item.id}] {item.content}" for item in memory_items)
                messages.append(SystemMessage(content=f"Memory:\n{content}"))

        if self.skills is not None:
            skills = self.skills.retrieve(user_input, limit=self.skill_limit)
            if skills:
                sections = []
                for skill in skills:
                    sections.append(
                        "\n".join(
                            [
                                f"## {skill.name}",
                                f"version: {skill.version}",
                                f"description: {skill.description}",
                                "",
                                skill.content,
                            ]
                        )
                    )
                messages.append(SystemMessage(content="Relevant skills:\n\n" + "\n\n".join(sections)))
        return messages
