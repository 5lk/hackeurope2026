from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.core.src.task_domain import ARCHITECTURE
from packages.core.src.types import (
    ArchitectHandoff,
    ArchitectureFilePlan,
    ModuleContract,
    Task,
)


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
    file_plan: Optional[ArchitectureFilePlan] = None


@dataclass
class ArchitectSandbox:
    """
    Architect sandbox runner.

    Responsibilities:
    - Ask the LLM for structured contracts and a file plan.
    - Write design artifacts (e.g., ARCH.md and optional DESIGN.md files).
    """

    llm: LLMClient
    prompts_dir: Optional[str] = None
    output_dir: Optional[str] = "output"

    def run(self, task: Task, context: ArchitectContext) -> ArchitectHandoff:
        system_prompt = load_prompt("architect-instance.md", self.prompts_dir)
        prompt = _format_leaf_prompt(task, context)

        result = self.llm.generate_json(
            prompt,
            system_prompt=system_prompt,
            schema_hint={
                "summary": "string",
                "file_plan": {
                    "files": ["string"],
                    "notes": ["string"],
                    "metadata": {"string": "string"},
                },
                "contracts": [
                    {
                        "module": "string",
                        "responsibilities": ["string"],
                        "inputs": ["string"],
                        "outputs": ["string"],
                        "invariants": ["string"],
                        "error_modes": ["string"],
                    }
                ],
            },
        )

        summary = (
            str(result.get("summary", "")).strip()
            or "Architect produced design artifacts."
        )

        contracts: List[ModuleContract] = []
        for contract in result.get("contracts", []) or []:
            contracts.append(
                ModuleContract(
                    module=str(contract.get("module", "")).strip(),
                    responsibilities=list(contract.get("responsibilities", []) or []),
                    inputs=list(contract.get("inputs", []) or []),
                    outputs=list(contract.get("outputs", []) or []),
                    invariants=list(contract.get("invariants", []) or []),
                    error_modes=list(contract.get("error_modes", []) or []),
                )
            )

        file_plan_payload = result.get("file_plan", {}) or {}
        file_plan = ArchitectureFilePlan(
            files=list(file_plan_payload.get("files", []) or []),
            notes=list(file_plan_payload.get("notes", []) or []),
            metadata=dict(file_plan_payload.get("metadata", {}) or {}),
        )
        context.file_plan = file_plan
        context.contracts = contracts

        artifacts: List[str] = []
        if self.output_dir:
            output_root = Path(self.output_dir)
            output_root.mkdir(parents=True, exist_ok=True)
            safe_id = task.id.replace(".", "_")
            arch_path = output_root / f"ARCH_{safe_id}.md"
            arch_content = _render_arch_md(task, summary, contracts, file_plan)
            arch_path.write_text(arch_content, encoding="utf-8")
            artifacts.append(str(arch_path))

            for file_path in file_plan.files:
                if not file_path.strip().endswith(".md"):
                    continue
                target = output_root / file_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    _render_design_stub(task, file_path, contracts),
                    encoding="utf-8",
                )
                artifacts.append(str(target))

        context.artifacts.extend(artifacts)

        return ArchitectHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=context.artifacts,
            files_changed=[],
            notes=[
                "Architect instance produced structured contracts and file plan.",
                "Design artifacts written to output directory.",
            ],
            contracts=contracts,
            file_plan=file_plan,
        )


@dataclass
class ArchitectLead:
    llm: LLMClient
    sandbox: ArchitectSandbox
    config: ArchitectConfig = field(default_factory=lambda: DEFAULT_ARCHITECT_CONFIG)
    prompts_dir: Optional[str] = None

    def decompose_and_execute(self, task: Task, depth: int = 0) -> ArchitectHandoff:
        if not should_decompose(task, self.config, depth):
            context = ArchitectContext(prompts_dir=self.prompts_dir)
            return self.sandbox.run(task, context)

        subtasks = self._decompose(task)
        handoffs: List[ArchitectHandoff] = []
        if not subtasks:
            return self._aggregate(task, handoffs)

        worker_count = min(len(subtasks), self.config.max_subtasks)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self.decompose_and_execute, subtask, depth + 1): subtask
                for subtask in subtasks
            }
            for future in as_completed(future_map):
                handoff = future.result()
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
                scope=list(task_dict.get("scope", []) or []),
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
        file_plan = handoffs[-1].file_plan if handoffs else None

        return ArchitectHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=artifacts,
            files_changed=[],
            notes=notes,
            contracts=contracts,
            file_plan=file_plan,
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
        "Return JSON with: summary, file_plan, contracts. "
        "file_plan.files must be relative paths for design docs (e.g., DESIGN.md). "
        "Contracts must be structured and specific."
    )


def _render_arch_md(
    task: Task,
    summary: str,
    contracts: List[ModuleContract],
    file_plan: ArchitectureFilePlan,
) -> str:
    lines: List[str] = [
        "# Architecture",
        "",
        f"**Task**: {task.title} (`{task.id}`)",
        "",
        "## Summary",
        summary,
        "",
        "## File Plan",
    ]
    if file_plan.files:
        lines.extend([f"- {path}" for path in file_plan.files])
    else:
        lines.append("- (No additional design files specified)")
    if file_plan.notes:
        lines.extend(["", "## File Plan Notes"])
        lines.extend([f"- {note}" for note in file_plan.notes])

    lines.append("")
    lines.append("## Module Contracts")
    if not contracts:
        lines.append("- (No contracts returned)")
    else:
        for contract in contracts:
            lines.append(f"### {contract.module}")
            if contract.responsibilities:
                lines.append("**Responsibilities**")
                lines.extend([f"- {item}" for item in contract.responsibilities])
            if contract.inputs:
                lines.append("**Inputs**")
                lines.extend([f"- {item}" for item in contract.inputs])
            if contract.outputs:
                lines.append("**Outputs**")
                lines.extend([f"- {item}" for item in contract.outputs])
            if contract.invariants:
                lines.append("**Invariants**")
                lines.extend([f"- {item}" for item in contract.invariants])
            if contract.error_modes:
                lines.append("**Error Modes**")
                lines.extend([f"- {item}" for item in contract.error_modes])
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def _render_design_stub(
    task: Task, file_path: str, contracts: List[ModuleContract]
) -> str:
    lines: List[str] = [
        f"# Design Notes: {file_path}",
        "",
        f"Generated for task `{task.id}` - {task.title}.",
        "",
        "## Scope",
        ", ".join(task.scope) if task.scope else "(No scope provided)",
        "",
        "## Related Module Contracts",
    ]
    if not contracts:
        lines.append("- (No contracts returned)")
    else:
        for contract in contracts:
            lines.append(f"- {contract.module}")
    lines.append("")
    lines.append("## Notes")
    lines.append("Add detailed design decisions here.")
    return "\n".join(lines).strip() + "\n"
