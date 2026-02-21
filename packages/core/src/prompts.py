from __future__ import annotations

from pathlib import Path
from typing import Optional


class PromptNotFoundError(FileNotFoundError):
    pass


def load_prompt(prompt_name: str, prompts_dir: Optional[str] = None) -> str:
    """
    Load a prompt file from the prompts directory.

    Args:
        prompt_name: File name (e.g., "manager.md").
        prompts_dir: Optional override directory path. If omitted, resolves to
            the repository root's "prompts" folder based on this file location.

    Returns:
        The prompt content as a string.

    Raises:
        PromptNotFoundError: If the prompt file does not exist.
    """
    if prompts_dir:
        base_dir = Path(prompts_dir)
    else:
        base_dir = Path(__file__).resolve().parents[3] / "prompts"

    prompt_path = base_dir / prompt_name
    if not prompt_path.exists():
        raise PromptNotFoundError(f"Prompt not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")
