from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    max_subtasks: int = 12
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
    project_root: Optional[Path] = None
    project_files: List[str] = field(default_factory=list)


@dataclass
class QASandbox:
    """
    QA worker sandbox runner.

    Responsibilities:
    - Generate pytest files based on SWE handoffs and architecture contracts.
    - Run tests in the output project.
    - Execute coverage and report metrics.
    """

    llm: LLMClient
    prompts_dir: Optional[str] = None
    output_dir: Optional[str] = None

    def run(self, task: Task, context: QATaskContext) -> QAHandoff:
        system_prompt = load_prompt("qa-worker.md", self.prompts_dir)
        prompt = _format_leaf_prompt(task, context)

        plan_prompt = (
            prompt + "\n\nReturn JSON with keys: summary, tests[]. "
            "Each test entry must include a relative path (under tests/) "
            "and a short purpose."
        )
        plan_result = self.llm.generate_json(
            plan_prompt,
            system_prompt=system_prompt,
            schema_hint={
                "summary": "string",
                "tests": [
                    {
                        "path": "string",
                        "purpose": "string",
                    }
                ],
            },
        )

        summary = (
            str(plan_result.get("summary", "")).strip() or "QA worker planned tests."
        )
        test_entries = plan_result.get("tests", []) or []

        files_changed: List[str] = []
        project_root = context.project_root or Path(self.output_dir or "output")
        project_root.mkdir(parents=True, exist_ok=True)

        for entry in test_entries:
            rel_path = str(entry.get("path", "")).strip()
            if not rel_path:
                continue
            rel_path = _normalize_test_path(rel_path)
            if not _is_safe_relative_path(rel_path):
                continue

            content_prompt = (
                prompt
                + f"\n\nGenerate ONLY the content for file path: {rel_path}\n"
                + "Return JSON with keys: path, content_base64."
            )
            try:
                content_result = self.llm.generate_json(
                    content_prompt,
                    system_prompt=system_prompt,
                    schema_hint={
                        "path": "string",
                        "content_base64": "string",
                    },
                )
                content_b64 = str(content_result.get("content_base64", "")).strip()
            except Exception:
                raw_text = self.llm.generate(
                    content_prompt, system_prompt=system_prompt
                ).text
                content_b64 = _fallback_content_b64(raw_text)

            if not content_b64:
                continue
            content = _decode_b64(content_b64)
            if content is None:
                continue

            target = project_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            files_changed.append(str(target))

        coverage_report, tests_passed, tests_failed, run_notes = (
            _run_tests_with_coverage(project_root)
        )

        notes = [
            "QA worker generated tests and executed coverage.",
            *run_notes,
        ]

        return QAHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=[],
            files_changed=files_changed,
            notes=notes,
            coverage_report=coverage_report,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
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
                project_root=Path(self.sandbox.output_dir or "output"),
                project_files=_list_project_files(self.sandbox.output_dir),
            )
            return self.sandbox.run(task, context)

        subtasks = self._decompose(task)
        handoffs: List[QAHandoff] = []
        if not subtasks:
            aggregate = self._aggregate(task, handoffs)
            if aggregate.coverage_report.line_coverage < self.config.coverage_target:
                return self._replan_for_coverage(task, aggregate)
            return aggregate

        worker_count = min(len(subtasks), self.config.max_subtasks)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self.decompose_and_execute, subtask, depth + 1): subtask
                for subtask in subtasks
            }
            for future in as_completed(future_map):
                handoff = future.result()
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
                scope=list(task_dict.get("scope", []) or []),
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
        uncovered_lines: List[str] = []

        total_statements = 0
        total_covered = 0
        total_branches = 0
        total_covered_branches = 0

        for handoff in handoffs:
            files_changed.extend(handoff.files_changed)
            notes.append(f"Subtask {handoff.task_id}: {handoff.summary}")
            total_passed += handoff.tests_passed
            total_failed += handoff.tests_failed
            uncovered_lines.extend(handoff.coverage_report.uncovered_lines)

            if handoff.coverage_report.line_coverage > 0:
                total_covered += int(
                    handoff.coverage_report.line_coverage * 10000
                )  # scaled
                total_statements += 10000
            if handoff.coverage_report.branch_coverage > 0:
                total_covered_branches += int(
                    handoff.coverage_report.branch_coverage * 10000
                )
                total_branches += 10000

        line_coverage = total_covered / total_statements if total_statements else 0.0
        branch_coverage = (
            total_covered_branches / total_branches if total_branches else 0.0
        )

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
    files_summary = "\n".join(context.project_files) or "No project files found."
    return (
        "You are the QA Worker. Write and run tests only.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        f"Architect Contracts:\n{contract_summary}\n\n"
        f"SWE Handoffs Summary:\n{swe_summary}\n\n"
        f"Project Files:\n{files_summary}\n\n"
        f"Coverage target: {context.coverage_target}\n"
        "Return a concise summary of the tests you will create."
    )


def _normalize_test_path(rel_path: str) -> str:
    normalized = rel_path.replace("\\", "/").strip()
    if not normalized.startswith("tests/"):
        normalized = f"tests/{normalized.lstrip('/')}"
    if not normalized.endswith(".py"):
        normalized = f"{normalized}.py"
    return normalized


def _is_safe_relative_path(rel_path: str) -> bool:
    if rel_path.startswith(("/", "\\")):
        return False
    if ":" in rel_path:
        return False
    return ".." not in Path(rel_path).parts


def _decode_b64(content_b64: str) -> Optional[str]:
    try:
        return base64.b64decode(content_b64).decode("utf-8")
    except Exception:
        return None


def _fallback_content_b64(raw_text: str) -> str:
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return ""
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            content_b64 = str(data.get("content_base64", "")).strip()
            if content_b64:
                return content_b64
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                content_b64 = str(data.get("content_base64", "")).strip()
                if content_b64:
                    return content_b64
        except Exception:
            pass

    return base64.b64encode(cleaned.encode("utf-8")).decode("utf-8")


def _list_project_files(output_dir: Optional[str]) -> List[str]:
    root = Path(output_dir or "output")
    if not root.exists():
        return []
    files: List[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(str(path.relative_to(root)))
    return files


def _run_tests_with_coverage(
    project_root: Path,
) -> Tuple[CoverageReport, int, int, List[str]]:
    notes: List[str] = []
    coverage_report = CoverageReport(0.0, 0.0, [])
    tests_passed = 0
    tests_failed = 0

    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--disable-warnings",
        "--maxfail=1",
        "--cov=.",
        "--cov-report=term-missing",
        "--cov-report=json:coverage.json",
    ]

    result = _run_command(pytest_cmd, project_root)
    if result is None:
        notes.append("Pytest execution failed to start.")
        return coverage_report, tests_passed, tests_failed, notes

    if result["returncode"] != 0 and _cov_args_not_supported(result["output"]):
        notes.append("pytest-cov not available; falling back to coverage.")
        coverage_cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            "--maxfail=1",
        ]
        coverage_run = _run_command(coverage_cmd, project_root)
        if coverage_run is None:
            notes.append("Coverage execution failed to start.")
            return coverage_report, tests_passed, tests_failed, notes

        json_cmd = [
            sys.executable,
            "-m",
            "coverage",
            "json",
            "-o",
            "coverage.json",
        ]
        _run_command(json_cmd, project_root)
        result = coverage_run

    output_text = result["output"]
    tests_passed, tests_failed = _parse_pytest_results(output_text)
    if result["returncode"] != 0 and tests_failed == 0:
        tests_failed = 1

    coverage_path = project_root / "coverage.json"
    if coverage_path.exists():
        coverage_report = _parse_coverage_json(coverage_path)
        notes.append("Coverage report generated.")
    else:
        notes.append("Coverage report not generated.")

    return coverage_report, tests_passed, tests_failed, notes


def _run_command(cmd: List[str], cwd: Path) -> Optional[Dict[str, object]]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return {"returncode": proc.returncode, "output": output}
    except Exception:
        return None


def _cov_args_not_supported(output: str) -> bool:
    return (
        "unrecognized arguments: --cov" in output
        or "--cov" in output
        and "error" in output.lower()
    )


def _parse_pytest_results(output: str) -> Tuple[int, int]:
    passed = 0
    failed = 0
    summary_match = re.search(r"=+\\s+(.*)\\s+=+", output)
    if not summary_match:
        return passed, failed
    summary = summary_match.group(1)
    passed_match = re.search(r"(\\d+)\\s+passed", summary)
    failed_match = re.search(r"(\\d+)\\s+failed", summary)
    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    return passed, failed


def _parse_coverage_json(path: Path) -> CoverageReport:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return CoverageReport(0.0, 0.0, [])

    files = data.get("files", {}) or {}
    total_statements = 0
    total_covered = 0
    total_branches = 0
    total_covered_branches = 0
    uncovered_lines: List[str] = []

    for file_path, file_data in files.items():
        summary = file_data.get("summary", {}) or {}
        num_statements = int(summary.get("num_statements", 0) or 0)
        covered_lines = int(summary.get("covered_lines", 0) or 0)
        num_branches = int(summary.get("num_branches", 0) or 0)
        covered_branches = int(summary.get("covered_branches", 0) or 0)

        total_statements += num_statements
        total_covered += covered_lines
        total_branches += num_branches
        total_covered_branches += covered_branches

        missing_lines = file_data.get("missing_lines", []) or []
        for line_no in missing_lines:
            uncovered_lines.append(f"{file_path}:{line_no}")

    line_coverage = (
        float(total_covered) / float(total_statements) if total_statements else 0.0
    )
    branch_coverage = (
        float(total_covered_branches) / float(total_branches) if total_branches else 0.0
    )

    return CoverageReport(
        line_coverage=line_coverage,
        branch_coverage=branch_coverage,
        uncovered_lines=uncovered_lines,
    )
