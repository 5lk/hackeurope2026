from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.core.src.task_domain import ARCHITECTURE
from packages.core.src.types import ArchitectHandoff, ModuleContract, Task


@dataclass
class ArchitectConfig:
    max_depth: int = 2
    scope_threshold: int = 5
    max_subtasks: int = 8


DEFAULT_ARCHITECT_CONFIG = ArchitectConfig()


def should_decompose(task: Task, config: ArchitectConfig, depth: int) -> bool:
    if depth >= config.max_depth:
        return False
    if len(task.scope) < config.scope_threshold:
        return False
    return True


@dataclass
class ArchitectContext:
    prompts_dir: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    contracts: List[ModuleContract] = field(default_factory=list)
    collaboration_notes: List[str] = field(default_factory=list)


@dataclass
class ArchitectSandbox:
    """
    Minimal architect sandbox runner.

    This is a placeholder hook for a real sandbox runner. It delegates to Gemini
    using the architect-instance prompt. It is only allowed to write markdown
    and interface/type-only files at runtime, but enforcement is left to the
    sandbox runner implementation.
    """

    llm: LLMClient
    prompts_dir: Optional[str] = None
    output_dir: Optional[str] = "output"

    def run(self, task: Task, context: ArchitectContext) -> ArchitectHandoff:
        system_prompt = load_prompt("architect-instance.md", self.prompts_dir)
        prompt = _format_leaf_prompt(task, context)
        result = self.llm.generate(prompt, system_prompt=system_prompt)
        summary = result.text.strip()

        if self.output_dir:
            output_path = Path(self.output_dir) / "ARCH.md"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(summary + "\n", encoding="utf-8")
            context.artifacts.append(str(output_path))

        return ArchitectHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=context.artifacts,
            files_changed=[],
            notes=["Architect instance completed (summary only)."],
            contracts=context.contracts,
        )


@dataclass
class ArchitectLead:
    llm: LLMClient
    sandbox: ArchitectSandbox
    config: ArchitectConfig = field(default_factory=lambda: DEFAULT_ARCHITECT_CONFIG)
    prompts_dir: Optional[str] = None

    def decompose_and_execute(self, task: Task, depth: int = 0) -> ArchitectHandoff:
        if not should_decompose(task, self.config, depth):
            context = ArchitectContext()
            return self.sandbox.run(task, context)

        subtasks = self._decompose(task)
        handoffs: List[ArchitectHandoff] = []
        for subtask in subtasks:
            handoff = self.decompose_and_execute(subtask, depth + 1)
            handoffs.append(handoff)

        return self._aggregate(task, handoffs)

    def _decompose(self, task: Task) -> List[Task]:
        system_prompt = load_prompt("architect.md", self.prompts_dir)
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
            raise ValueError("Architect decomposition did not return a task list.")

        subtasks: List[Task] = []
        for idx, task_dict in enumerate(
            tasks_payload[: self.config.max_subtasks], start=1
        ):
            subtask = Task(
                id=f"{task.id}.{idx}",
                title=str(task_dict.get("title", f"{task.title} / {idx}")),
                description=str(task_dict.get("description", "")),
                scope=list(task_dict.get("scope", [])),
                domain=ARCHITECTURE,
                depends_on=[],
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
                    domain=ARCHITECTURE,
                    depends_on=[],
                    metadata={"parent": task.id},
                )
            ]

        return subtasks

    def _aggregate(
        self, task: Task, handoffs: List[ArchitectHandoff]
    ) -> ArchitectHandoff:
        artifacts: List[str] = []
        contracts: List[ModuleContract] = []
        notes: List[str] = []

        for handoff in handoffs:
            artifacts.extend(handoff.artifacts)
            contracts.extend(handoff.contracts)
            notes.append(f"Subtask {handoff.task_id}: {handoff.summary}")

        summary = f"Architect lead completed {len(handoffs)} subtasks for {task.title}."

        return ArchitectHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=artifacts,
            files_changed=[],
            notes=notes,
            contracts=contracts,
        )


def _format_lead_prompt(task: Task, max_subtasks: int) -> str:
    return (
        "You are the Architect Lead. Decompose the task into at most "
        f"{max_subtasks} architecture subtasks.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        "Return JSON with keys: scratchpad, tasks[]. Each task must include "
        "title, description, scope."
    )


def _format_leaf_prompt(task: Task, context: ArchitectContext) -> str:
    return (
        "You are the Architect Instance. Produce design artifacts only.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        f"Collaboration Notes:\n{context.collaboration_notes}\n\n"
        "Return a concise summary of the ARCH.md content and any interfaces/types "
        "you would write. Do not include implementations."
    )
