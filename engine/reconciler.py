"""Simplified reconciler — periodic scan of output_project/ for obvious issues."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .events import EngineEvent, EventBus, EventType
from .gemini import GeminiClient, LLMMessage
from .parsing import parse_llm_task_array
from .project_state import read_project_state, read_file_contents
from .types import Handoff, Task, TaskStatus, TeamRole

logger = logging.getLogger("agentswarm.reconciler")

# Asset file extensions that should never exist in the project.
ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".mp3", ".wav", ".ogg", ".flac", ".aac",
    ".mp4", ".avi", ".mov", ".webm",
}

# Patterns that indicate asset file loading in code.
ASSET_LOAD_PATTERNS = [
    re.compile(r'pygame\.image\.load\s*\('),
    re.compile(r'pygame\.font\.Font\s*\(\s*["\'][^"\']+\.(ttf|otf|woff)', re.IGNORECASE),
    re.compile(r'pygame\.mixer\.\w+\.load\s*\('),
    re.compile(r'open\s*\([^)]*\.(png|jpg|jpeg|gif|bmp|svg|ttf|wav|mp3|ogg)', re.IGNORECASE),
]

# Pattern for bare (non-relative) intra-package imports.
BARE_IMPORT_PATTERN = re.compile(r'^from\s+(?!\.)[a-z_][a-z0-9_]*\s+import\s+', re.MULTILINE)


class Reconciler:
    """Periodically scans output_project/ for issues and generates fix tasks."""

    def __init__(
        self,
        config: Config,
        client: GeminiClient,
        system_prompt: str,
        output_dir: Path,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.system_prompt = system_prompt
        self.output_dir = output_dir
        self._running = False
        self.on_fix_tasks: Optional[Callable[[list[Task]], None]] = None
        self._task_counter = 0
        self.event_bus = event_bus

    def _emit(self, event: EngineEvent) -> None:
        if self.event_bus:
            self.event_bus.emit(event)

    async def run_periodic(self) -> None:
        """Run sweeps in a loop until stopped."""
        self._running = True
        while self._running:
            await asyncio.sleep(self.config.reconciler_interval_s)
            if not self._running:
                break
            try:
                fix_tasks = await self.sweep()
                if fix_tasks and self.on_fix_tasks:
                    logger.info("Reconciler found %d issues — injecting fix tasks", len(fix_tasks))
                    self.on_fix_tasks(fix_tasks)
            except Exception as e:
                logger.error("Reconciler sweep failed: %s", e)

    async def sweep(self) -> list[Task]:
        """Scan for issues and return fix tasks."""
        state = read_project_state(self.output_dir)
        if not state.file_tree:
            return []

        issues = self._scan_for_issues(state.file_tree)
        if not issues:
            logger.debug("Reconciler sweep: no issues found")
            return []

        # Read contents of problematic files to give LLM context.
        problem_files = set()
        for issue in issues:
            # Extract file path from issue string.
            for f in state.file_tree:
                if f in issue:
                    problem_files.add(f)

        file_contents = read_file_contents(self.output_dir, list(problem_files))

        context_str = ""
        if file_contents:
            for path, content in file_contents.items():
                context_str += f"\n### {path}\n```\n{content}\n```\n"

        # Ask LLM to generate fix tasks.
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=issues + "\n\n## File Contents\n" + context_str),
        ]

        response = await self.client.complete(messages)

        try:
            raw_tasks = parse_llm_task_array(response.content)
        except Exception:
            logger.warning("Reconciler could not parse fix tasks from LLM response")
            return []

        tasks: list[Task] = []
        for raw in raw_tasks:
            if not raw.description:
                continue
            self._task_counter += 1
            task_id = raw.id or f"fix-{self._task_counter:03d}"
            tasks.append(Task(
                id=task_id,
                description=raw.description,
                scope=raw.scope or [],
                acceptance=raw.acceptance or "Fix the identified issue",
                priority=raw.priority or 1,
                team=TeamRole.ENGINEERING,
            ))

        return tasks[:5]  # Max 5 fix tasks per sweep.

    def _scan_for_issues(self, file_tree: list[str]) -> str:
        """Scan output_project/ for structural issues."""
        issues: list[str] = []

        for rel_path in file_tree:
            if rel_path.startswith("..."):
                continue

            full = self.output_dir / rel_path

            # 1. Check for asset files that should not exist.
            ext = full.suffix.lower()
            if ext in ASSET_EXTENSIONS:
                issues.append(f"ASSET FILE VIOLATION: {rel_path} — external asset files are forbidden. Must be replaced with programmatic code.")
                continue

            # 2. Check for empty files.
            try:
                if full.is_file() and full.stat().st_size == 0:
                    issues.append(f"Empty file: {rel_path}")
                    continue
            except OSError:
                continue

            # 3. Scan source files for deeper issues.
            if ext in {".py", ".ts", ".js", ".tsx", ".jsx", ".java", ".rs", ".go", ".c", ".cpp", ".h"}:
                try:
                    text = full.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                # Check for TODO/placeholder markers.
                if "TODO: implement" in text or "# TODO" in text.upper():
                    count = text.upper().count("TODO")
                    issues.append(f"Contains {count} TODO markers: {rel_path}")

                if "pass  # placeholder" in text:
                    issues.append(f"Contains placeholder pass statements: {rel_path}")

                # Check for asset file loading in code.
                for pattern in ASSET_LOAD_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        issues.append(f"ASSET LOADING in code: {rel_path} — found '{match.group()}'. Must use programmatic shapes/system fonts instead.")

                # Check for bare imports (potential intra-package issue).
                if ext == ".py":
                    # Determine if this file is inside a package (has __init__.py nearby).
                    parent = full.parent
                    is_in_package = (parent / "__init__.py").exists()

                    if is_in_package:
                        for line_no, line in enumerate(text.splitlines(), 1):
                            stripped = line.strip()
                            if stripped.startswith("from ") and " import " in stripped:
                                # Skip stdlib and known third-party imports.
                                module = stripped.split("from ", 1)[1].split(" import")[0].strip()
                                if (
                                    not module.startswith(".")
                                    and not module.startswith("__")
                                    and module not in _STDLIB_MODULES
                                    and module.split(".")[0] not in _KNOWN_THIRD_PARTY
                                ):
                                    # Check if it looks like an intra-package import.
                                    potential_file = parent / (module.replace(".", "/") + ".py")
                                    if potential_file.exists() or (parent / module / "__init__.py").exists():
                                        issues.append(
                                            f"BARE IMPORT in {rel_path}:{line_no} — "
                                            f"'from {module} import ...' should be 'from .{module} import ...'. "
                                            f"Use relative imports within packages."
                                        )

        if not issues:
            return ""

        return (
            f"## Project Issues Detected\n\n"
            f"File tree has {len(file_tree)} files.\n\n"
            f"### Issues Found ({len(issues)} total)\n"
            + "\n".join(f"- {issue}" for issue in issues[:20])
            + "\n\nGenerate targeted fix tasks as a JSON array. Include the NO ASSETS reminder in every fix task."
        )

    def stop(self) -> None:
        self._running = False


# Common stdlib module names (not exhaustive, but covers common false positives).
_STDLIB_MODULES = {
    "os", "sys", "re", "json", "math", "random", "time", "datetime",
    "pathlib", "collections", "itertools", "functools", "typing",
    "abc", "io", "copy", "enum", "dataclasses", "logging", "unittest",
    "argparse", "subprocess", "threading", "multiprocessing", "asyncio",
    "socket", "http", "urllib", "hashlib", "hmac", "secrets", "string",
    "textwrap", "struct", "csv", "configparser", "tempfile", "shutil",
    "glob", "fnmatch", "stat", "traceback", "warnings", "contextlib",
    "decimal", "fractions", "statistics", "pprint", "dis", "inspect",
    "importlib", "pkgutil", "platform", "signal", "queue", "heapq",
    "bisect", "array", "weakref", "types", "operator",
}

# Common third-party packages (top-level import names).
_KNOWN_THIRD_PARTY = {
    "pygame", "flask", "django", "fastapi", "numpy", "pandas", "scipy",
    "matplotlib", "requests", "httpx", "aiohttp", "sqlalchemy", "pydantic",
    "click", "rich", "pytest", "dotenv", "PIL", "cv2", "torch",
    "tensorflow", "sklearn", "celery", "redis", "boto3", "paramiko",
    "yaml", "toml", "bs4", "lxml", "jinja2", "werkzeug", "uvicorn",
    "gunicorn", "starlette", "anyio", "trio", "attr", "attrs",
}
