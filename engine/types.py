"""Core data types for AgentSwarm."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class TeamRole(str, Enum):
    PRODUCT = "product"
    ENGINEERING = "engineering"
    QUALITY = "quality"


@dataclass
class Task:
    id: str
    description: str
    scope: list[str]
    acceptance: str
    status: TaskStatus = TaskStatus.PENDING
    team: TeamRole = TeamRole.ENGINEERING
    priority: int = 5
    parent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0


@dataclass
class HandoffMetrics:
    files_created: int = 0
    files_modified: int = 0
    tokens_used: int = 0
    duration_ms: int = 0


@dataclass
class Handoff:
    task_id: str
    status: str  # "complete" | "partial" | "blocked" | "failed"
    summary: str
    files_changed: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    metrics: HandoffMetrics = field(default_factory=HandoffMetrics)


@dataclass
class FileOperation:
    """A single file create/overwrite operation from a worker."""
    path: str       # relative to output_project/
    content: str    # full file content


@dataclass
class WorkerResult:
    """Structured result from a worker Gemini API call."""
    handoff: Handoff
    file_operations: list[FileOperation]
