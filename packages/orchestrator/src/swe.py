from __future__ import annotations

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from packages.core.src.llm_client import LLMClient
from packages.core.src.prompts import load_prompt
from packages.core.src.task_domain import IMPLEMENTATION
from packages.core.src.types import ArchitectHandoff, SWEHandoff, Task


@dataclass
class SWEConfig:
    max_depth: int = 3
    scope_threshold: int = 4
    max_subtasks: int = 10
    enforce_entrypoint: bool = True
    default_files: Tuple[str, ...] = ("main.py", "README.md", "requirements.txt")


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
    architecture_file_plan: List[str] = field(default_factory=list)


@dataclass
class SWESandbox:
    """
    SWE worker sandbox runner.

    Responsibilities:
    - Request a file plan and then file contents from the LLM.
    - Use architect contracts and file plan to produce a runnable project.
    - Write files to the output directory.
    """

    llm: LLMClient
    prompts_dir: Optional[str] = None
    output_dir: Optional[Path] = None

    def run(self, task: Task, context: SWETaskContext) -> SWEHandoff:
        system_prompt = load_prompt("swe-worker.md", self.prompts_dir)
        prompt = _format_leaf_prompt(task, context)
        print(f"[swe-worker] planning files for {task.id} - {task.title}")

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
        planned_files = _extract_plan_files(plan_result.get("files", []))
        planned_files = _merge_file_plans(planned_files, context.architecture_file_plan)

        planned_files = _ensure_minimal_files(planned_files, DEFAULT_SWE_CONFIG)
        print(f"[swe-worker] files planned ({len(planned_files)}): {planned_files}")

        files_changed: List[str] = []
        if self.output_dir:
            base_dir = Path(self.output_dir)
            for rel_path in planned_files:
                rel_path = rel_path.strip()
                if not rel_path:
                    continue
                if not _is_safe_relative_path(rel_path):
                    continue

                print(f"[swe-worker] generating content for {rel_path}")
                content_prompt = (
                    prompt
                    + f"\n\nPhase 2: Generate ONLY the content for file path: {rel_path}\n"
                    + "Return JSON with keys: path, content_base64."
                )

                content_b64 = _request_file_content_b64(
                    self.llm, system_prompt, content_prompt
                )
                if not content_b64:
                    continue
                content = _decode_b64(content_b64)
                if content is None:
                    continue

                target = base_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                files_changed.append(str(target))

        print(f"[swe-worker] wrote {len(files_changed)} files for {task.id}")
        return SWEHandoff(
            task_id=task.id,
            summary=summary,
            artifacts=[],
            files_changed=files_changed,
            notes=[
                "SWE worker wrote project files (two-phase).",
                "File plan honored architecture guidance where available.",
            ],
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
                architecture_file_plan=_collect_arch_file_plan(self.sandbox.output_dir),
            )
            return self.sandbox.run(task, context)

        subtasks = self._decompose(task)
        handoffs: List[SWEHandoff] = []
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
                scope=list(task_dict.get("scope", []) or []),
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
    contract_text = _render_contracts(context.architect_handoff)
    file_plan = context.architecture_file_plan or []
    return (
        "You are the SWE Worker. Implement a complete, runnable Python project "
        "that satisfies the Architect’s contracts.\n\n"
        f"Task ID: {task.id}\n"
        f"Title: {task.title}\n"
        f"Description: {task.description}\n"
        f"Scope: {task.scope}\n\n"
        f"Architect Handoff Summary:\n{architect_summary}\n\n"
        f"Architect Contracts:\n{contract_text}\n\n"
        f"Architecture File Plan:\n{file_plan}\n\n"
        f"Known Implementations:\n{context.existing_implementations}\n\n"
        f"Collaboration Notes:\n{context.collaboration_notes}\n\n"
        "Rules:\n"
        "- Produce runnable code aligned to the prompt.\n"
        "- Include a clear entrypoint (e.g., main.py) and any dependencies.\n"
        "- Only output Python project files.\n"
        "- Do not write tests in this phase.\n"
        "- Do not modify architecture/design documents.\n\n"
        "Return a concise summary of the code you would write. Do not write tests."
    )


def _render_contracts(handoff: Optional[ArchitectHandoff]) -> str:
    if not handoff or not handoff.contracts:
        return "No contracts provided."
    parts: List[str] = []
    for contract in handoff.contracts:
        parts.append(f"- Module: {contract.module}")
        if contract.responsibilities:
            parts.append(f"  Responsibilities: {', '.join(contract.responsibilities)}")
        if contract.inputs:
            parts.append(f"  Inputs: {', '.join(contract.inputs)}")
        if contract.outputs:
            parts.append(f"  Outputs: {', '.join(contract.outputs)}")
        if contract.invariants:
            parts.append(f"  Invariants: {', '.join(contract.invariants)}")
        if contract.error_modes:
            parts.append(f"  Error Modes: {', '.join(contract.error_modes)}")
    return "\n".join(parts)


def _extract_plan_files(files_payload: Iterable[dict]) -> List[str]:
    files: List[str] = []
    for entry in files_payload or []:
        path = str(entry.get("path", "")).strip()
        if path:
            files.append(path)
    return files


def _merge_file_plans(primary: List[str], secondary: Sequence[str]) -> List[str]:
    merged = list(primary)
    for path in secondary:
        if path not in merged:
            merged.append(path)
    return merged


def _ensure_minimal_files(files: List[str], config: SWEConfig) -> List[str]:
    normalized = list(files)
    for required in config.default_files:
        if required not in normalized:
            normalized.append(required)
    if config.enforce_entrypoint and not any(
        path.endswith("main.py") or path.endswith("app.py") for path in normalized
    ):
        normalized.append("main.py")
    return normalized


def _request_file_content_b64(
    llm: LLMClient, system_prompt: str, content_prompt: str
) -> Optional[str]:
    try:
        content_result = llm.generate_json(
            content_prompt,
            system_prompt=system_prompt,
            schema_hint={
                "path": "string",
                "content_base64": "string",
            },
        )
        content_b64 = str(content_result.get("content_base64", "")).strip()
        if content_b64:
            return content_b64
    except Exception:
        raw_text = llm.generate(content_prompt, system_prompt=system_prompt).text
        content_b64 = _fallback_content_b64(raw_text)
        if content_b64:
            return content_b64
    return None


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


def _is_safe_relative_path(rel_path: str) -> bool:
    if rel_path.startswith(("/", "\\")):
        return False
    if ":" in rel_path:
        return False
    return ".." not in Path(rel_path).parts


def _collect_arch_file_plan(output_dir: Optional[Path]) -> List[str]:
    if not output_dir:
        return []
    arch_path = Path(output_dir) / "ARCH.md"
    if not arch_path.exists():
        return []
    text = arch_path.read_text(encoding="utf-8")
    return _parse_arch_file_plan(text)


def _parse_arch_file_plan(text: str) -> List[str]:
    lines = text.splitlines()
    plan_files: List[str] = []
    in_file_plan = False
    for line in lines:
        if line.strip().lower() == "## file plan":
            in_file_plan = True
            continue
        if in_file_plan:
            if line.startswith("## "):
                break
            match = re.match(r"^-\\s+(.*)", line.strip())
            if match:
                path = match.group(1).strip()
                if path:
                    plan_files.append(path)
    return plan_files
