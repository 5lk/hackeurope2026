from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from packages.core.src.types import Handoff, Task


class IntegrationWorker(Protocol):
    def assign_task(self, task: Task) -> Handoff: ...


@dataclass
class WorkerPool:
    """
    Stub worker pool for integration tasks.

    This is a minimal placeholder that returns a summary-only handoff.
    Replace with real sandboxed execution or distributed worker logic.
    """

    def assign_task(self, task: Task) -> Handoff:
        return Handoff(
            task_id=task.id,
            summary=(
                "Integration task received by WorkerPool. "
                "No execution performed in stub."
            ),
            artifacts=[],
            files_changed=[],
            notes=[f"Integration task '{task.title}' is pending implementation."],
        )
