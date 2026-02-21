from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SWEWorkerResult:
    summary: str
    artifacts: list[str]
    files_changed: list[str]
    notes: list[str]


@dataclass
class SWEWorkerRunner:
    """
    Stub SWE worker runner.

    In a full implementation, this would spin up a sandbox, inject prompts,
    run the model with tool access, apply patches, and return a detailed handoff.
    """

    def run(
        self, task_id: str, prompt: str, system_prompt: Optional[str] = None
    ) -> SWEWorkerResult:
        summary = (
            "SWE worker runner stub executed. No sandbox actions performed. "
            "This placeholder should be replaced with real tool-backed execution."
        )
        return SWEWorkerResult(
            summary=summary,
            artifacts=[],
            files_changed=[],
            notes=[f"Received task {task_id}.", "No-op stub implementation."],
        )
