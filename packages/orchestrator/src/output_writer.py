from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from packages.core.src.types import Handoff


@dataclass
class OutputWriter:
    """
    Handles writing orchestration artifacts to an output directory.
    """

    output_dir: Path
    wipe_on_start: bool = True
    written_files: List[Path] = field(default_factory=list)

    def prepare(self) -> None:
        """
        Create the output directory and optionally wipe it.
        """
        if self.wipe_on_start and self.output_dir.exists():
            for path in sorted(self.output_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """
        Resolve a safe path within the output directory to prevent traversal.
        """
        target = (self.output_dir / relative_path).resolve()
        base = self.output_dir.resolve()
        if base not in target.parents and target != base:
            raise ValueError(f"Unsafe output path: {relative_path}")
        return target

    def write_text(self, relative_path: str, content: str) -> Path:
        """
        Write a text file relative to the output directory.
        """
        target = self._resolve_safe_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.written_files.append(target)
        return target

    def write_handoff_summary(self, handoff: Handoff) -> Path:
        """
        Save a handoff summary to a markdown file.
        """
        safe_id = handoff.task_id.replace("/", "_")
        filename = f"{safe_id}.md"
        content = self._format_handoff(handoff)
        return self.write_text(filename, content)

    def write_handoffs(self, handoffs: Iterable[Handoff]) -> List[Path]:
        """
        Save all handoff summaries.
        """
        paths: List[Path] = []
        for handoff in handoffs:
            paths.append(self.write_handoff_summary(handoff))
        return paths

    def write_project_files(self, files: Iterable[tuple[str, str]]) -> List[Path]:
        """
        Write generated project files (path, content) safely into output.
        """
        written: List[Path] = []
        for relative_path, content in files:
            written.append(self.write_text(relative_path, content))
        return written

    def _format_handoff(self, handoff: Handoff) -> str:
        parts = [
            f"# Handoff: {handoff.task_id}",
            "",
            f"**Summary**: {handoff.summary}",
            "",
        ]

        if handoff.artifacts:
            parts.append("## Artifacts")
            parts.extend([f"- {path}" for path in handoff.artifacts])
            parts.append("")

        if handoff.files_changed:
            parts.append("## Files Changed")
            parts.extend([f"- {path}" for path in handoff.files_changed])
            parts.append("")

        if handoff.notes:
            parts.append("## Notes")
            parts.extend([f"- {note}" for note in handoff.notes])
            parts.append("")

        return "\n".join(parts)
