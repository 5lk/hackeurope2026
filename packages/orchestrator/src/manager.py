from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.core.src.task_domain import ARCHITECTURE, IMPLEMENTATION, TESTING
from packages.core.src.types import ManagerTask, Task, TaskDomain


@dataclass
class ManagerConfig:
    max_tasks: int = 20


@dataclass
class ManagerState:
    completed_task_ids: List[str] = field(default_factory=list)
    architect_artifacts: List[str] = field(default_factory=list)
    qa_reports: List[str] = field(default_factory=list)


@dataclass
class Manager:
    llm: LLMClient
    config: ManagerConfig = field(default_factory=ManagerConfig)
    prompts_dir: Optional[str] = None
    state: ManagerState = field(default_factory=ManagerState)

    def plan(self, user_prompt: str) -> List[ManagerTask]:
        system_prompt = load_prompt("manager.md", self.prompts_dir)
        prompt = self._format_plan_prompt(user_prompt)

        response = self.llm.generate_json(
            prompt,
            system_prompt=system_prompt,
            schema_hint={
                "scratchpad": "string",
                "tasks": [
                    {
                        "id": "string",
                        "title": "string",
                        "description": "string",
                        "scope": ["string"],
                        "domain": "architecture|implementation|testing|integration",
                        "dependsOn": ["string"],
                    }
                ],
            },
        )

        tasks_payload = response.get("tasks", [])
        if not isinstance(tasks_payload, list):
            raise ValueError("Manager did not return a task list.")

        tasks: List[ManagerTask] = []
        for idx, task_dict in enumerate(
            tasks_payload[: self.config.max_tasks], start=1
        ):
            task_id = str(task_dict.get("id") or f"task-{idx}")
            domain_value = str(task_dict.get("domain", ARCHITECTURE))
            depends_on = list(task_dict.get("dependsOn", []))

            task = ManagerTask(
                id=task_id,
                title=str(task_dict.get("title", f"Task {idx}")),
                description=str(task_dict.get("description", "")),
                scope=list(task_dict.get("scope", [])),
                domain=domain_value,  # type: ignore[assignment]
                depends_on=depends_on,
                metadata={},
            )
            tasks.append(task)

        if not tasks:
            raise ValueError("Manager returned no tasks.")

        return tasks

    def apply_handoffs(
        self,
        architect_artifacts: Optional[List[str]] = None,
        qa_reports: Optional[List[str]] = None,
    ) -> None:
        if architect_artifacts:
            self.state.architect_artifacts.extend(architect_artifacts)
        if qa_reports:
            self.state.qa_reports.extend(qa_reports)

    def mark_complete(self, task_id: str) -> None:
        if task_id not in self.state.completed_task_ids:
            self.state.completed_task_ids.append(task_id)

    def next_sprint_prompt(self) -> str:
        return (
            "You are the Manager. Plan the next sprint based on completed work.\n"
            f"Completed tasks: {self.state.completed_task_ids}\n"
            f"Architect artifacts: {self.state.architect_artifacts}\n"
            f"QA reports: {self.state.qa_reports}\n"
        )

    def finalize_run_instructions(self, output_dir: str) -> str:
        system_prompt = load_prompt("manager-final.md", self.prompts_dir)
        file_list = self._collect_output_files(output_dir)
        prompt = (
            "Provide run instructions for the generated project.\n\n"
            f"Output directory: {output_dir}\n"
            "Files:\n" + "\n".join(f"- {path}" for path in file_list)
        )
        response = self.llm.generate(prompt, system_prompt=system_prompt)
        return response.text.strip()

    def _collect_output_files(self, output_dir: str) -> List[str]:
        root = Path(output_dir)
        if not root.exists():
            return []
        return [
            str(path.relative_to(root))
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]

    def _format_plan_prompt(self, user_prompt: str) -> str:
        return (
            "You are a technical project manager. "
            "Decompose the work into architecture, implementation, and testing. "
            "You never write code. Every implementation task must reference an "
            "architecture task ID. Every testing task must reference an "
            "implementation task ID.\n\n"
            f"User prompt:\n{user_prompt}\n\n"
            "Return JSON with keys: scratchpad, tasks[]."
        )
