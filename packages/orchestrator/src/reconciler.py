from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from packages.core.src.task_domain import ARCHITECTURE, IMPLEMENTATION, TESTING
from packages.core.src.types import Handoff, Task


@dataclass
class ReconcilerConfig:
    max_retries: int = 3
    coverage_target: float = 0.80


@dataclass
class ReconcilerResult:
    summary: str
    fix_tasks: List[Task] = field(default_factory=list)


@dataclass
class Reconciler:
    """
    Domain-aware reconciler stub.

    In a full implementation, this would run build/test/coverage checks and
    emit fix tasks routed to the appropriate department.
    """

    config: ReconcilerConfig = field(default_factory=ReconcilerConfig)

    def sweep(self, handoffs: List[Handoff]) -> ReconcilerResult:
        """
        Perform a reconciliation sweep and emit any fix tasks.

        Currently returns no fix tasks; placeholder for build/test/coverage
        signal analysis.
        """
        summary = (
            "Reconciler sweep completed. No automated checks executed "
            "(stub implementation)."
        )
        return ReconcilerResult(summary=summary, fix_tasks=[])

    def create_fix_task(
        self,
        title: str,
        description: str,
        domain: str,
        depends_on: Optional[List[str]] = None,
    ) -> Task:
        """
        Create a domain-aware fix task for routing through the DepartmentRouter.
        """
        return Task(
            id=f"fix-{abs(hash(title)) % 10_000}",
            title=title,
            description=description,
            scope=[],
            domain=domain,  # type: ignore[assignment]
            depends_on=depends_on or [],
            metadata={"origin": "reconciler"},
        )

    def route_for_issue(self, issue_type: str) -> str:
        """
        Map an issue type to a task domain.
        """
        if issue_type == "interface-violation":
            return IMPLEMENTATION
        if issue_type == "design-inconsistency":
            return ARCHITECTURE
        if issue_type == "coverage-regression":
            return TESTING
        return IMPLEMENTATION
