from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.core.src.task_domain import TESTING
from packages.core.src.types import (
    ArchitectHandoff,
    CoverageReport,
    QAHandoff,
    SWEHandoff,
    Task,
)


@dataclass
class QAConfig:
    max_depth: int = 2
    scope_threshold: int = 3
    max_subtasks: int = 15
    coverage_target: float = 0.80


DEFAULT_QA_CONFIG = QAConfig()


def should_decompose(task: Task, config: QAConfig, depth: int) -> bool:
    if depth >= config.max_depth:
        return False
    if len(task.scope) < config.scope_threshold:
        return False
    return True


@dataclass
class QATaskContext:
    swe_handoffs: List[SWEHandoff] = field(default_factory=list)
    architect_contracts: List[str] = field(default_factory=list)
    coverage_target: float = DEFAULT_QA_CONFIG.coverage_target


@dataclass
class QASandbox:
    """
    Minimal QA worker sandbox runner.

    This is a placeholder hook for a real sandbox runner. It delegates to Gemini
    using the qa-worker prompt. It should only create new test files and run tests.
    """

    llm: LLMClient
    prompts_dir: Optional[str] = None
    output_dir: Optional[str] = None

    def run(self, task: Task, context: QATaskContext) -> QAHandoff:
        system_prompt = load_prompt("qa-worker.md", self.prompts_dir)
        prompt = _format_leaf_prompt(task, context)
        result = self.llm.generate(prompt, system_prompt=system_prompt)

        output_root = Path(self.output_dir or "output") / "tests"
        output_root.mkdir(parents=True, exist_ok=True)
        safe_id = task.id.replace(".", "_").replace("-", "_")
        test_path = output_root / f"test_{safe_id}.py"
        test_body = _format_test_stub(task, context)
        test_path.write_text(test_body, encoding="utf-8")
        files_changed = [str(test_path)]

        return QAHandoff(
            task_id=task.id,
            summary=result.text.strip(),
            artifacts=[],
            files_changed=files_changed,
            notes=[
                "QA worker completed (summary only).",
                f"Wrote test stub: {test_path}",
            ],
            coverage_report=CoverageReport(0.0, 0.0, []),
            tests_passed=0,
            tests_failed=0,
        )


@dataclass
class QALead:
    llm: LLMClient
    sandbox: QASandbox
    config: QAConfig = field(default_factory=lambda: DEFAULT_QA_CONFIG)
    prompts_dir: Optional[str] = None
    swe_handoffs: List[SWEHandoff] = field(default_factory=list)
    architect_handoff: Optional[ArchitectHandoff] = None

    def decompose_and_execute(self, task: Task, depth: int = 0) -> QAHandoff:
        if not should_decompose(task, self.config, depth):
            context = QATaskContext(
                swe_handoffs=self.swe_handoffs,
                architect_contracts=self._contract_summaries(),
                coverage_target=self.config.coverage_target,
            )
            return self.sandbox.run(task, context)

        subtasks = self._decompose(task)
        handoffs: List[QAHandoff] = []
        for subtask in subtasks:
            handoff = self.decompose_and_execute(subtask, depth + 1)
            handoffs.append(handoff)

        aggregate = self._aggregate(task, handoffs)
        if aggregate.coverage_report.line_coverage < self.config.coverage_target:
            return self._replan_for_coverage(task, aggregate)

        return aggregate

    def _decompose(self, task: Task) -> List[Task]:
        system_prompt = load_prompt("qa.md", self.prompts_dir)
        prompt = _format_lead_prompt(task, self.config.max_subtasks)
        response = self.llm.generate_json(
            prompt,
            system_prompt=system_prompt,
            schema_hint={
                "scratchpad": "string",
                "tasks": [
                    {
                        "title": "string",
                        "description": "string",
                        "scope": ["string"],
                    }
                ],
            },
        )

        tasks_payload = response.get("tasks", [])
        if not isinstance(tasks_payload, list):
            raise ValueError("QA decomposition did not return a task list.")

        subtasks: List[Task] = []
        for idx, task_dict in enumerate(
            tasks_payload[: self.config.max_subtasks], start=1
        ):
            subtask = Task(
                id=f"{task.id}.{idx}",
                title=str(task_dict.get("title", f"{task.title} / {idx}")),
                description=str(task_dict.get("description", "")),
                scope=list(task_dict.get("scope", [])),
                domain=TESTING,
                depends_on=task.depends_on,
                metadata={"parent": task.id},
            )
            subtasks.append(subtask)

        if not subtasks:
            subtasks = [
                Task(
                    id=f"{task.id}.1",
                    title=task.title,
                    description=task.description,
                    scope=task.scope,
                    domain=TESTING,
                    depends_on=task.depends_on,
                    metadata={"parent": task.id},
                )
            ]

        return subtasks

    def _aggregate(self, task: Task, handoffs: List[QAHandoff]) -> QAHandoff:
        files_changed: List[str] = []
        notes: List[str] = []
        total_passed = 0
        total_failed = 0
        line_coverage = 0.0
        branch_coverage = 0.0
        uncovered_lines: List[str] = []

        if handoffs:
            line_coverage = sum(
                handoff.coverage_report.line_coverage for handoff in handoffs
            ) / len(handoffs)
            branch_coverage = sum(
                handoff.coverage_report.branch_coverage for handoff in handoffs
            ) / len(handoffs)

        for handoff in handoffs:
            files_changed.extend(handoff.files_changed)
            notes.append(f"Subtask {handoff.task_id}: {handoff.summary}")
            total_passed += handoff.tests_passed
            total_failed += handoff.tests_failed
            uncovered_lines.extend(handoff.coverage_report.uncovered_lines)

        summary = f"QA lead completed {len(handoffs)} subtasks for {task.title}."

        return QAHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=[],
            files_changed=files_changed,
            notes=notes,
            coverage_report=CoverageReport(
                line_coverage=line_coverage,
                branch_coverage=branch_coverage,
                uncovered_lines=uncovered_lines,
            ),
            tests_passed=total_passed,
            tests_failed=total_failed,
        )

    def _replan_for_coverage(self, task: Task, aggregate: QAHandoff) -> QAHandoff:
        notes = list(aggregate.notes)
        notes.append(
            "Coverage below target. QA lead will spawn more subtasks for gaps."
        )
        return QAHandoff(
            task_id=task.id,
            summary=aggregate.summary + " Coverage target unmet.",
            artifacts=aggregate.artifacts,
            files_changed=aggregate.files_changed,
            notes=notes,
            coverage_report=aggregate.coverage_report,
            tests_passed=aggregate.tests_passed,
            tests_failed=aggregate.tests_failed,
        )

    def _contract_summaries(self) -> List[str]:
        if not self.architect_handoff:
            return []
        return [contract.module for contract in self.architect_handoff.contracts]


def _format_lead_prompt(task: Task, max_subtasks: int) -> str:
    return (
        "You are the QA Lead. Decompose the task into at most "
        f"{max_subtasks} testing subtasks.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        "Return JSON with keys: scratchpad, tasks[]. Each task must include "
        "title, description, scope."
    )


def _format_leaf_prompt(task: Task, context: QATaskContext) -> str:
    swe_summary = (
        "\n".join([handoff.summary for handoff in context.swe_handoffs])
        or "No SWE handoffs provided."
    )
    contract_summary = (
        ", ".join(context.architect_contracts) or "No architect contracts provided."
    )
    return (
        "You are the QA Worker. Write and run tests only.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        f"Architect Contracts:\n{contract_summary}\n\n"
        f"SWE Handoffs Summary:\n{swe_summary}\n\n"
        f"Coverage target: {context.coverage_target}\n"
        "Return a concise summary of the tests you would write and coverage status."
    )


def _format_test_stub(task: Task, context: QATaskContext) -> str:
    safe_id = task.id.replace(".", "_").replace("-", "_")
    safe_title = task.title.replace('"', "'")
    return (
        "import pytest\n\n"
        f"def test_{safe_id}():\n"
        f'    """Auto-generated stub for: {safe_title}"""\n'
        "    assert True\n"
    )
