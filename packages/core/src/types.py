from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict


class AgentRole(str, Enum):
    MANAGER = "manager"
    ARCHITECT = "architect"
    ARCHITECT_INSTANCE = "architect-instance"
    SWE = "swe"
    SWE_WORKER = "swe-worker"
    QA = "qa"
    QA_WORKER = "qa-worker"
    RECONCILER = "reconciler"


TaskDomain = Literal["architecture", "implementation", "testing", "integration"]


@dataclass
class Task:
    id: str
    title: str
    description: str
    scope: List[str]
    domain: TaskDomain
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleContract:
    module: str
    responsibilities: List[str]
    inputs: List[str]
    outputs: List[str]
    invariants: List[str]
    error_modes: List[str]


@dataclass
class Handoff:
    task_id: str
    summary: str
    artifacts: List[str] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ArchitectHandoff(Handoff):
    contracts: List[ModuleContract] = field(default_factory=list)


@dataclass
class SWEHandoff(Handoff):
    pass


@dataclass
class CoverageReport:
    line_coverage: float
    branch_coverage: float
    uncovered_lines: List[str]


@dataclass
class QAHandoff(Handoff):
    coverage_report: CoverageReport = field(
        default_factory=lambda: CoverageReport(0.0, 0.0, [])
    )
    tests_passed: int = 0
    tests_failed: int = 0


@dataclass
class ManagerTask(Task):
    depends_on: List[str] = field(default_factory=list)


class LLMTaskResult(TypedDict):
    scratchpad: str
    tasks: List[Dict[str, Any]]
