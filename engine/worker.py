"""Worker execution — each task becomes a Gemini API call that returns file operations."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from .config import Config
from .events import EngineEvent, EventBus, EventType
from .gemini import GeminiClient, LLMMessage, RateLimitError
from .parsing import parse_worker_response
from .project_state import read_file_contents, read_project_state
from .types import (
    FileOperation,
    Handoff,
    HandoffMetrics,
    Task,
    TeamRole,
    WorkerResult,
)

logger = logging.getLogger("agentswarm.worker")

TEAM_PROMPT_FILES = {
    TeamRole.ENGINEERING: "engineering.md",
    TeamRole.PRODUCT: "product.md",
    TeamRole.QUALITY: "quality.md",
}

# Appended to every team system prompt so workers know the response format.
WORKER_RESPONSE_FORMAT = """
---

## Output Format

You MUST respond with a single JSON object. No surrounding text, no markdown fences around the outer JSON.

```
{
  "handoff": {
    "status": "complete | partial | blocked | failed",
    "summary": "What you did. 2-4 sentences.",
    "files_changed": ["path/to/file1.py", "path/to/file2.py"],
    "concerns": ["Any risks or issues discovered"],
    "suggestions": ["Ideas for follow-up work"]
  },
  "file_operations": [
    {
      "path": "relative/path/from/project/root.py",
      "content": "FULL file content here. Not a diff. Not a patch. The COMPLETE file."
    }
  ]
}
```

CRITICAL RULES:
- file_operations contains the COMPLETE content of every file you create or modify.
- Path is relative to the project root (e.g., "src/main.py", NOT an absolute path).
- Include ALL files you want to create or modify. Files not listed are left unchanged.
- Content must be the ENTIRE file, not a diff or partial snippet.
- You CANNOT delete files. If a file should be removed, mention it in concerns.
- Output ONLY this JSON object. No explanations before or after it.
- NEVER create asset files (.png, .jpg, .ttf, .wav, etc.). All graphics must be code-drawn.

JSON ENCODING — VERY IMPORTANT:
- The "content" field contains source code with newlines. You MUST use proper JSON escaping.
- Newlines in code MUST be encoded as \\n (backslash-n), NOT literal line breaks inside the JSON string.
- Quotes inside code MUST be escaped as \\" (backslash-quote).
- Backslashes in code MUST be escaped as \\\\ (double backslash).
- Tab characters MUST be encoded as \\t.
- The entire JSON must be valid — parseable by json.loads() in Python.
- Do NOT wrap the JSON in markdown code fences (no ```json ... ```). Output raw JSON only.
"""

WORKER_USER_TEMPLATE = """## Task: {task_id}

**Team:** {team}
**Description:** {description}

**Scope (files to focus on):** {scope}

**Acceptance criteria:** {acceptance}

## Current Project File Tree
{file_tree}

## IMPORTANT CONTEXT: All Existing File Contents

Below are the contents of ALL existing project files. Use these to:
- Verify what constants, functions, and classes already exist
- Use the EXACT import paths and names defined here
- Do NOT redefine constants that already exist — import them instead
- Use relative imports for intra-package references (e.g., `from .constants import ...`)

{all_file_contents}

---

Complete this task. Respond with ONLY the JSON object containing your file_operations and handoff as specified in your system instructions.
Include the FULL content of every file you create or modify.
NEVER create any external asset files (.png, .jpg, .ttf, .wav, etc.). Use programmatic alternatives.
"""


class WorkerPool:
    """Dispatch tasks as parallel Gemini API calls, apply file operations."""

    def __init__(
        self,
        client: GeminiClient,
        output_dir: Path,
        prompts_dir: Path,
        max_workers: int,
        event_bus: EventBus | None = None,
    ) -> None:
        self.client = client
        self.output_dir = output_dir
        self.prompts_dir = prompts_dir
        self.semaphore = asyncio.Semaphore(max_workers)
        self.max_workers = max_workers
        self._team_prompts: dict[TeamRole, str] = {}
        self._active_count = 0
        self.event_bus = event_bus

    def _emit(self, event: EngineEvent) -> None:
        if self.event_bus:
            self.event_bus.emit(event)

    def load_prompts(self) -> None:
        for team, filename in TEAM_PROMPT_FILES.items():
            path = self.prompts_dir / filename
            if path.exists():
                self._team_prompts[team] = path.read_text(encoding="utf-8")
            else:
                logger.warning("Missing prompt file: %s", path)
                self._team_prompts[team] = f"You are the {team.value} team agent."

    async def execute_task(self, task: Task) -> Handoff:
        """Acquire a slot, call Gemini, parse response, write files, return handoff."""
        async with self.semaphore:
            self._active_count += 1
            try:
                return await self._execute_single(task)
            finally:
                self._active_count -= 1

    async def _execute_single(self, task: Task) -> Handoff:
        start = time.time()
        team = task.team or TeamRole.ENGINEERING
        system_prompt = self._team_prompts.get(team, self._team_prompts[TeamRole.ENGINEERING])
        system_prompt += WORKER_RESPONSE_FORMAT

        # Build context — read ALL project files, not just scope files.
        state = read_project_state(self.output_dir)
        all_contents = read_file_contents(self.output_dir, state.file_tree)

        user_prompt = self._build_worker_prompt(task, state.file_tree, all_contents)

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        logger.info(
            "Worker starting task %s (team=%s, scope=%d files, context=%d files)",
            task.id,
            team.value,
            len(task.scope),
            len(all_contents),
        )

        self._emit(EngineEvent(
            type=EventType.TASK_STARTED,
            task_id=task.id,
            team=team.value,
        ))

        try:
            response = await self.client.complete(messages)
            result = parse_worker_response(response.content, task.id)

            # Apply file operations to disk.
            files_created = 0
            files_modified = 0
            for op in result.file_operations:
                target = self.output_dir / op.path
                existed = target.exists()
                target.parent.mkdir(parents=True, exist_ok=True)

                # Block asset files from being written.
                if self._is_asset_file(op.path):
                    logger.warning("Blocked asset file creation: %s (task %s)", op.path, task.id)
                    continue

                target.write_text(op.content, encoding="utf-8")
                if existed:
                    files_modified += 1
                else:
                    files_created += 1
                logger.debug("  Wrote %s (%s)", op.path, "modified" if existed else "created")

            # Update metrics on the handoff.
            result.handoff.metrics = HandoffMetrics(
                tokens_used=response.total_tokens,
                duration_ms=int((time.time() - start) * 1000),
                files_created=files_created,
                files_modified=files_modified,
            )

            logger.info(
                "Worker completed task %s — status=%s, files=%d, tokens=%d, %dms",
                task.id,
                result.handoff.status,
                len(result.file_operations),
                response.total_tokens,
                result.handoff.metrics.duration_ms,
            )

            self._emit(EngineEvent(
                type=EventType.TASK_COMPLETED,
                task_id=task.id,
                status=result.handoff.status,
                data={
                    "summary": result.handoff.summary[:200],
                    "files": len(result.file_operations),
                    "tokens": response.total_tokens,
                    "duration_ms": result.handoff.metrics.duration_ms,
                },
            ))

            return result.handoff

        except RateLimitError:
            logger.warning("Rate-limited on task %s — will retry after backoff", task.id)
            await asyncio.sleep(10)
            try:
                response = await self.client.complete(messages)
                result = parse_worker_response(response.content, task.id)

                files_created = 0
                files_modified = 0
                for op in result.file_operations:
                    target = self.output_dir / op.path
                    existed = target.exists()
                    target.parent.mkdir(parents=True, exist_ok=True)

                    if self._is_asset_file(op.path):
                        logger.warning("Blocked asset file creation: %s (task %s)", op.path, task.id)
                        continue

                    target.write_text(op.content, encoding="utf-8")
                    if existed:
                        files_modified += 1
                    else:
                        files_created += 1

                result.handoff.metrics = HandoffMetrics(
                    tokens_used=response.total_tokens,
                    duration_ms=int((time.time() - start) * 1000),
                    files_created=files_created,
                    files_modified=files_modified,
                )
                return result.handoff
            except Exception as e2:
                return self._failure_handoff(task.id, start, e2)

        except Exception as e:
            return self._failure_handoff(task.id, start, e)

    @staticmethod
    def _is_asset_file(path: str) -> bool:
        """Block creation of external asset files."""
        asset_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp",
            ".ttf", ".otf", ".woff", ".woff2", ".eot",
            ".mp3", ".wav", ".ogg", ".flac", ".aac",
            ".mp4", ".avi", ".mov", ".webm",
        }
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return ext in asset_extensions

    def _build_worker_prompt(
        self,
        task: Task,
        file_tree: list[str],
        all_contents: dict[str, str],
    ) -> str:
        tree_str = "\n".join(file_tree) if file_tree else "(empty project)"

        # Include ALL project file contents for full context.
        contents_str = ""
        if all_contents:
            for path, content in all_contents.items():
                contents_str += f"\n### {path}\n```\n{content}\n```\n"
        else:
            contents_str = "(no files in project yet)"

        return WORKER_USER_TEMPLATE.format(
            task_id=task.id,
            team=task.team.value if task.team else "engineering",
            description=task.description,
            scope=", ".join(task.scope) if task.scope else "(no specific scope)",
            acceptance=task.acceptance,
            file_tree=tree_str,
            all_file_contents=contents_str,
        )

    @staticmethod
    def _failure_handoff(task_id: str, start: float, error: Exception) -> Handoff:
        logger.error("Worker failed for task %s: %s", task_id, error)
        return Handoff(
            task_id=task_id,
            status="failed",
            summary=f"Worker failed: {error}",
            concerns=[str(error)],
            metrics=HandoffMetrics(duration_ms=int((time.time() - start) * 1000)),
        )

    @property
    def active_count(self) -> int:
        return self._active_count
