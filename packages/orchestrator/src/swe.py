from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.core.src.task_domain import IMPLEMENTATION
from packages.core.src.types import ArchitectHandoff, SWEHandoff, Task


@dataclass
class SWEConfig:
    max_depth: int = 3
    scope_threshold: int = 4
    max_subtasks: int = 10


DEFAULT_SWE_CONFIG = SWEConfig()


def should_decompose(task: Task, config: SWEConfig, depth: int) -> bool:
    if depth >= config.max_depth:
        return False
    if len(task.scope) < config.scope_threshold:
        return False
    return True


@dataclass
class SWETaskContext:
    architect_handoff: Optional[ArchitectHandoff] = None
    existing_implementations: List[str] = field(default_factory=list)
    collaboration_notes: List[str] = field(default_factory=list)


@dataclass
class SWESandbox:
    """
    Minimal SWE worker sandbox runner.

    This is a placeholder hook for a real sandbox runner. It delegates to Gemini
    using the swe-worker prompt. It should honor Architect contracts and never
    redefine types already declared by the Architect.
    """

    llm: LLMClient
    prompts_dir: Optional[str] = None
    output_dir: Optional[Path] = None

    def run(self, task: Task, context: SWETaskContext) -> SWEHandoff:
        system_prompt = load_prompt("swe-worker.md", self.prompts_dir)
        prompt = _format_leaf_prompt(task, context)

        plan_prompt = (
            prompt
            + "\n\nPhase 1: Return JSON with a high-level summary and a list of file paths only."
        )
        plan_result = self.llm.generate_json(
            plan_prompt,
            system_prompt=system_prompt,
            schema_hint={
                "summary": "string",
                "files": [
                    {
                        "path": "string",
                    }
                ],
            },
        )

        summary = (
            str(plan_result.get("summary", "")).strip() or "SWE worker produced files."
        )
        files_changed: List[str] = []

        if self.output_dir:
            base_dir = Path(self.output_dir)
            for file_entry in plan_result.get("files", []) or []:
                rel_path = str(file_entry.get("path", "")).strip()
                if not rel_path:
                    continue

                content_prompt = (
                    prompt
                    + f"\n\nPhase 2: Generate ONLY the content for file path: {rel_path}\n"
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
                    if not raw_text.strip():
                        continue
                    content_b64 = base64.b64encode(raw_text.encode("utf-8")).decode(
                        "utf-8"
                    )
                if not content_b64:
                    continue
                try:
                    content = base64.b64decode(content_b64).decode("utf-8")
                except Exception:
                    continue

                target = base_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                files_changed.append(str(target))

        return SWEHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=[],
            files_changed=files_changed,
            notes=["SWE worker wrote project files (two-phase)."],
        )


@dataclass
class SWELead:
    llm: LLMClient
    sandbox: SWESandbox
    config: SWEConfig = field(default_factory=lambda: DEFAULT_SWE_CONFIG)
    prompts_dir: Optional[str] = None
    architect_handoff: Optional[ArchitectHandoff] = None
    existing_implementations: List[str] = field(default_factory=list)

    def decompose_and_execute(self, task: Task, depth: int = 0) -> SWEHandoff:
        if not should_decompose(task, self.config, depth):
            context = SWETaskContext(
                architect_handoff=self.architect_handoff,
                existing_implementations=self.existing_implementations,
            )
            return self.sandbox.run(task, context)

        subtasks = self._decompose(task)
        handoffs: List[SWEHandoff] = []
        for subtask in subtasks:
            handoff = self.decompose_and_execute(subtask, depth + 1)
            handoffs.append(handoff)

        return self._aggregate(task, handoffs)

    def _decompose(self, task: Task) -> List[Task]:
        system_prompt = load_prompt("swe.md", self.prompts_dir)
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
            raise ValueError("SWE decomposition did not return a task list.")

        subtasks: List[Task] = []
        for idx, task_dict in enumerate(
            tasks_payload[: self.config.max_subtasks], start=1
        ):
            subtask = Task(
                id=f"{task.id}.{idx}",
                title=str(task_dict.get("title", f"{task.title} / {idx}")),
                description=str(task_dict.get("description", "")),
                scope=list(task_dict.get("scope", [])),
                domain=IMPLEMENTATION,
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
                    domain=IMPLEMENTATION,
                    depends_on=task.depends_on,
                    metadata={"parent": task.id},
                )
            ]

        return subtasks

    def _aggregate(self, task: Task, handoffs: List[SWEHandoff]) -> SWEHandoff:
        files_changed: List[str] = []
        notes: List[str] = []

        for handoff in handoffs:
            files_changed.extend(handoff.files_changed)
            notes.append(f"Subtask {handoff.task_id}: {handoff.summary}")

        summary = f"SWE lead completed {len(handoffs)} subtasks for {task.title}."

        return SWEHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=[],
            files_changed=files_changed,
            notes=notes,
        )


def _format_lead_prompt(task: Task, max_subtasks: int) -> str:
    return (
        "You are the SWE Lead. Decompose the task into at most "
        f"{max_subtasks} implementation subtasks.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        "Return JSON with keys: scratchpad, tasks[]. Each task must include "
        "title, description, scope."
    )


def _format_leaf_prompt(task: Task, context: SWETaskContext) -> str:
    architect_summary = (
        context.architect_handoff.summary
        if context.architect_handoff
        else "No architect handoff provided."
    )
    return (
        "You are the SWE Worker. Implement code that honors the Architect contracts.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        f"Architect Handoff Summary:\n{architect_summary}\n\n"
        f"Known Implementations:\n{context.existing_implementations}\n\n"
        f"Collaboration Notes:\n{context.collaboration_notes}\n\n"
        "Return a concise summary of the code you would write. Do not write tests."
    )
