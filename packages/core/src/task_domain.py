from __future__ import annotations

from typing import Iterable, List

from .types import Task, TaskDomain

ARCHITECTURE: TaskDomain = "architecture"
IMPLEMENTATION: TaskDomain = "implementation"
TESTING: TaskDomain = "testing"
INTEGRATION: TaskDomain = "integration"


def is_domain(task: Task, domain: TaskDomain) -> bool:
    return task.domain == domain


def is_architecture(task: Task) -> bool:
    return is_domain(task, ARCHITECTURE)


def is_implementation(task: Task) -> bool:
    return is_domain(task, IMPLEMENTATION)


def is_testing(task: Task) -> bool:
    return is_domain(task, TESTING)


def is_integration(task: Task) -> bool:
    return is_domain(task, INTEGRATION)


def filter_by_domain(tasks: Iterable[Task], domain: TaskDomain) -> List[Task]:
    return [task for task in tasks if task.domain == domain]


def any_blocked_by_dependencies(task: Task, completed_ids: Iterable[str]) -> bool:
    completed = set(completed_ids)
    return any(dep_id not in completed for dep_id in task.depends_on)
