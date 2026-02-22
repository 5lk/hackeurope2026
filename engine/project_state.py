"""Read the output_project/ filesystem state — replacement for git-based readRepoState."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("agentswarm.project_state")

MAX_FILE_TREE_ENTRIES = 500
MAX_FILE_CONTENT_CHARS = 30_000

# Directories to skip when walking the project.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".turbo",
    ".next", ".nuxt", "target",
}

# Binary extensions that we don't include in file content reads.
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".pyc", ".pyo", ".class", ".jar",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}


@dataclass
class ProjectState:
    file_tree: list[str]                        # relative paths sorted
    file_contents: dict[str, str] = field(default_factory=dict)  # path → content


def read_project_state(output_dir: Path) -> ProjectState:
    """Walk output_dir recursively, return the file tree."""
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return ProjectState(file_tree=[])

    files: list[str] = []

    for p in sorted(output_dir.rglob("*")):
        if p.is_dir():
            continue

        rel = p.relative_to(output_dir).as_posix()

        # Skip hidden/build directories.
        parts = rel.split("/")
        if any(part in SKIP_DIRS or part.startswith(".") for part in parts):
            continue

        files.append(rel)

    if len(files) > MAX_FILE_TREE_ENTRIES:
        truncated = len(files) - MAX_FILE_TREE_ENTRIES
        files = files[:MAX_FILE_TREE_ENTRIES]
        files.append(f"... ({truncated} more files)")

    return ProjectState(file_tree=files)


def read_file_contents(
    output_dir: Path,
    paths: list[str],
    max_chars: int = MAX_FILE_CONTENT_CHARS,
) -> dict[str, str]:
    """Read specific file contents from output_project/."""
    contents: dict[str, str] = {}

    for rel_path in paths:
        full = output_dir / rel_path
        if not full.is_file():
            continue

        ext = full.suffix.lower()
        if ext in BINARY_EXTENSIONS:
            contents[rel_path] = f"(binary file, {full.stat().st_size} bytes)"
            continue

        try:
            text = full.read_text(encoding="utf-8", errors="replace")
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            contents[rel_path] = text
        except Exception:
            logger.warning("Could not read %s", rel_path)

    return contents
