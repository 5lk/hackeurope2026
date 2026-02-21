from __future__ import annotations

from dataclasses import dataclass

from packages.core.src.task_domain import (
    ARCHITECTURE,
    IMPLEMENTATION,
    INTEGRATION,
    TESTING,
)
from packages.core.src.types import Handoff, Task


@dataclass
class DepartmentRouter:
    architect: object
    swe: object
    qa: object
    worker_pool: object

    def route(self, task: Task) -> Handoff:
        if task.domain == ARCHITECTURE:
            return self.architect.decompose_and_execute(task, depth=0)
        if task.domain == IMPLEMENTATION:
            return self.swe.decompose_and_execute(task, depth=0)
        if task.domain == TESTING:
            return self.qa.decompose_and_execute(task, depth=0)
        if task.domain == INTEGRATION:
            return self.worker_pool.assign_task(task)
        raise ValueError(f"Unknown task domain: {task.domain}")
