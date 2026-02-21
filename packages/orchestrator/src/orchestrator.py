from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from packages.core.src.llm_client import LLMClient
from packages.core.src.types import (
    ArchitectHandoff,
    Handoff,
    ManagerTask,
    QAHandoff,
    SWEHandoff,
    Task,
)
from packages.orchestrator.src.architect import ArchitectLead, ArchitectSandbox
from packages.orchestrator.src.department_router import DepartmentRouter
from packages.orchestrator.src.manager import Manager
from packages.orchestrator.src.output_writer import OutputWriter
from packages.orchestrator.src.qa import QALead, QASandbox
from packages.orchestrator.src.reconciler import Reconciler
from packages.orchestrator.src.swe import SWELead, SWESandbox
from packages.orchestrator.src.task_queue import TaskQueue
from packages.orchestrator.src.worker_pool import WorkerPool


@dataclass
class RoleModels:
    manager: str = "models/gemini-2.5-pro"
    architect: str = "models/gemini-2.5-pro"
    swe: str = "models/gemini-2.5-pro"
    qa: str = "models/gemini-2.5-flash"


@dataclass
class OrchestratorConfig:
    prompts_dir: Optional[str] = None
    max_cycles: int = 3
    role_models: RoleModels = field(default_factory=RoleModels)
    output_dir: str = "output"
    wipe_output: bool = True
    worker_count: int = 4


@dataclass
class Orchestrator:
    llm: LLMClient
    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)

    def __post_init__(self) -> None:
        manager_llm = self._client_for_model(self.config.role_models.manager)
        architect_llm = self._client_for_model(self.config.role_models.architect)
        swe_llm = self._client_for_model(self.config.role_models.swe)
        qa_llm = self._client_for_model(self.config.role_models.qa)

        self.manager = Manager(manager_llm, prompts_dir=self.config.prompts_dir)
        self.architect = ArchitectLead(
            architect_llm,
            sandbox=ArchitectSandbox(
                architect_llm,
                prompts_dir=self.config.prompts_dir,
                output_dir=self.config.output_dir,
            ),
            prompts_dir=self.config.prompts_dir,
        )
        self.swe = SWELead(
            swe_llm,
            sandbox=SWESandbox(
                swe_llm,
                prompts_dir=self.config.prompts_dir,
                output_dir=Path(self.config.output_dir),
            ),
            prompts_dir=self.config.prompts_dir,
        )
        self.qa = QALead(
            qa_llm,
            sandbox=QASandbox(
                qa_llm,
                prompts_dir=self.config.prompts_dir,
                output_dir=self.config.output_dir,
            ),
            prompts_dir=self.config.prompts_dir,
        )
        self.worker_pool = WorkerPool()
        self.router = DepartmentRouter(
            architect=self.architect,
            swe=self.swe,
            qa=self.qa,
            worker_pool=self.worker_pool,
        )
        self.reconciler = Reconciler()
        self.output_writer = OutputWriter(
            output_dir=Path(self.config.output_dir),
            wipe_on_start=self.config.wipe_output,
        )

    def _client_for_model(self, model_name: str) -> LLMClient:
        if not hasattr(self, "_client_cache"):
            self._client_cache = {}
        cache = self._client_cache

        if model_name in cache:
            return cache[model_name]

        if model_name == self.llm.model:
            client = self.llm
        else:
            client = LLMClient(model=model_name)

        cache[model_name] = client
        return client

    def _role_label(self, task: Task) -> str:
        if task.domain == "architecture":
            return "architect"
        if task.domain == "implementation":
            return "swe"
        if task.domain == "testing":
            return "qa"
        return "manager"

    def run(self, user_prompt: str) -> List[Handoff]:
        all_handoffs: List[Handoff] = []
        cycle_count = 0
        swe_instance = 0
        architect_instance = 0
        qa_instance = 0
        manager_instance = 0

        self.output_writer.prepare()
        manager_instance += 1
        print(f"[manager#{manager_instance}] : initialized output directory")

        worker_count = max(1, self.config.worker_count)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            while cycle_count < self.config.max_cycles:
                cycle_count += 1
                queue = TaskQueue()
                print(f"[manager#{manager_instance}] : planning tasks")
                manager_tasks = self.manager.plan(user_prompt)

                for task in manager_tasks:
                    queue.add(task)
                    print(f"[manager#{manager_instance}] : queued {task.title}")

                while True:
                    ready = [
                        task
                        for task in queue.pending_tasks()
                        if queue.can_dispatch(task)
                    ]
                    if not ready:
                        break

                    batch = ready[:worker_count]
                    futures = {}

                    for next_task in batch:
                        queue.set_status(next_task.id, "running")
                        if next_task.domain == "implementation":
                            swe_instance += 1
                            role_label = f"swe#{swe_instance}"
                        elif next_task.domain == "architecture":
                            architect_instance += 1
                            role_label = f"architect#{architect_instance}"
                        elif next_task.domain == "testing":
                            qa_instance += 1
                            role_label = f"qa#{qa_instance}"
                        else:
                            role_label = self._role_label(next_task)
                        print(f"[{role_label}] : {next_task.title}")
                        futures[executor.submit(self._dispatch_task, next_task)] = (
                            next_task,
                            role_label,
                        )

                    for future in as_completed(futures):
                        next_task, role_label = futures[future]
                        handoff = future.result()
                        queue.set_status(next_task.id, "complete", result=handoff)

                        self.manager.mark_complete(next_task.id)
                        self.attach_handoff(handoff)
                        self._apply_handoff_to_context(handoff)
                        all_handoffs.append(handoff)
                        self.output_writer.write_handoff_summary(handoff)
                        print(f"[{role_label}] : completed {next_task.title}")

                reconciliation = self.reconciler.sweep(all_handoffs)
                if not reconciliation.fix_tasks:
                    break

                for fix_task in reconciliation.fix_tasks:
                    queue.add(fix_task)

                user_prompt = self.manager.next_sprint_prompt()

        return all_handoffs

    def _dispatch_task(self, task: Task) -> Handoff:
        if task.domain == "implementation":
            self.swe.architect_handoff = self._latest_architect_handoff()
            self.swe.existing_implementations = self._collaboration_notes()
            if self.swe.architect_handoff:
                self._write_arch_file_plan(self.swe.architect_handoff)
        if task.domain == "testing":
            self.qa.swe_handoffs = self._swe_handoffs()
            self.qa.architect_handoff = self._latest_architect_handoff()
        return self.router.route(task)

    def _apply_handoff_to_context(self, handoff: Handoff) -> None:
        if isinstance(handoff, ArchitectHandoff):
            self.manager.apply_handoffs(architect_artifacts=handoff.artifacts)
            self._write_arch_file_plan(handoff)
        if isinstance(handoff, QAHandoff):
            report = (
                f"Coverage line={handoff.coverage_report.line_coverage:.2f}, "
                f"branch={handoff.coverage_report.branch_coverage:.2f}"
            )
            self.manager.apply_handoffs(qa_reports=[report])

    def _write_arch_file_plan(self, handoff: ArchitectHandoff) -> None:
        if not handoff.file_plan:
            return
        output_root = Path(self.config.output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        arch_path = output_root / "ARCH.md"
        lines = [
            "# Architecture",
            "",
            "## File Plan",
        ]
        if handoff.file_plan.files:
            lines.extend([f"- {path}" for path in handoff.file_plan.files])
        else:
            lines.append("- (No additional design files specified)")
        if handoff.file_plan.notes:
            lines.extend(["", "## File Plan Notes"])
            lines.extend([f"- {note}" for note in handoff.file_plan.notes])
        arch_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def _latest_architect_handoff(self) -> Optional[ArchitectHandoff]:
        handoffs = [
            h for h in self._handoffs_cache() if isinstance(h, ArchitectHandoff)
        ]
        return handoffs[-1] if handoffs else None

    def _swe_handoffs(self) -> List[SWEHandoff]:
        return [h for h in self._handoffs_cache() if isinstance(h, SWEHandoff)]

    def _collaboration_notes(self) -> List[str]:
        return [handoff.summary for handoff in self._handoffs_cache()]

    def _handoffs_cache(self) -> List[Handoff]:
        if not hasattr(self, "_handoffs"):
            self._handoffs = []
        return self._handoffs  # type: ignore[return-value]

    def attach_handoff(self, handoff: Handoff) -> None:
        self._handoffs_cache().append(handoff)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the multi-department orchestrator."
    )
    parser.add_argument("prompt", type=str, help="User prompt for the Manager.")
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-1.5-pro",
        help="Gemini model name.",
    )
    parser.add_argument(
        "--prompts-dir",
        type=str,
        default=None,
        help="Optional prompts directory override.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    llm = LLMClient(model=args.model)
    orchestrator = Orchestrator(llm, OrchestratorConfig(prompts_dir=args.prompts_dir))
    handoffs = orchestrator.run(args.prompt)
    for handoff in handoffs:
        orchestrator.attach_handoff(handoff)

    print("Orchestration complete.")
    print(f"Handoffs produced: {len(handoffs)}")
    for handoff in handoffs:
        print(f"- {handoff.task_id}: {handoff.summary}")


if __name__ == "__main__":
    main()
