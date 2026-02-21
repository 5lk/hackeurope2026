from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from packages.core.src.types import Task


@dataclass
class TaskStatus:
    task: Task
    status: str = "pending"  # pending | running | complete | failed
    result: Optional[object] = None


@dataclass
class TaskQueue:
    tasks: Dict[str, TaskStatus] = field(default_factory=dict)

    def add(self, task: Task) -> None:
        if task.id in self.tasks:
            raise ValueError(f"Task {task.id} already exists.")
        self.tasks[task.id] = TaskStatus(task=task)

    def set_status(
        self, task_id: str, status: str, result: Optional[object] = None
    ) -> None:
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task id: {task_id}")
        self.tasks[task_id].status = status
        self.tasks[task_id].result = result

    def get_status(self, task_id: str) -> str:
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task id: {task_id}")
        return self.tasks[task_id].status

    def can_dispatch(self, task: Task) -> bool:
        return all(self.get_status(dep_id) == "complete" for dep_id in task.depends_on)

    def next_ready(self) -> Optional[Task]:
        for task_status in self.tasks.values():
            if task_status.status == "pending" and self.can_dispatch(task_status.task):
                return task_status.task
        return None

    def ready_tasks(self) -> List[Task]:
        return [
            status.task
            for status in self.tasks.values()
            if status.status == "pending" and self.can_dispatch(status.task)
        ]

    def pending_tasks(self) -> List[Task]:
        return [
            status.task for status in self.tasks.values() if status.status == "pending"
        ]

    def completed_ids(self) -> List[str]:
        return [
            task_id
            for task_id, status in self.tasks.items()
            if status.status == "complete"
        ]
