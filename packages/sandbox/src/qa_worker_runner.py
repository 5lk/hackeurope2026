from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class QAWorkerResult:
    summary: str
    artifacts: list[str]
    files_changed: list[str]
    notes: list[str]
    tests_passed: int
    tests_failed: int
    line_coverage: float
    branch_coverage: float
    uncovered_lines: list[str]


@dataclass
class QAWorkerRunner:
    """
    Stub QA worker runner.

    In a full implementation, this would spin up a sandbox, inject prompts,
    create test files only, run tests, collect coverage, and return a detailed
    QA handoff-compatible result.
    """

    def run(
        self, task_id: str, prompt: str, system_prompt: Optional[str] = None
    ) -> QAWorkerResult:
        summary = (
            "QA worker runner stub executed. No sandbox actions performed. "
            "This placeholder should be replaced with real test/coverage execution."
        )
        return QAWorkerResult(
            summary=summary,
            artifacts=[],
            files_changed=[],
            notes=[f"Received task {task_id}.", "No-op stub implementation."],
            tests_passed=0,
            tests_failed=0,
            line_coverage=0.0,
            branch_coverage=0.0,
            uncovered_lines=[],
        )
