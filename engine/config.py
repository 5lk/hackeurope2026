"""Configuration loading from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


@dataclass(frozen=True)
class LLMConfig:
    endpoint: str
    api_key: str
    model: str
    max_tokens: int
    temperature: float
    timeout_s: float


@dataclass(frozen=True)
class Config:
    llm: LLMConfig
    output_dir: Path
    max_workers: int
    max_planner_iterations: int
    reconciler_enabled: bool
    reconciler_interval_s: float


def load_config() -> Config:
    """Load configuration from .env and environment variables."""
    load_dotenv()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required env: GEMINI_API_KEY")

    endpoint = os.environ.get("LLM_ENDPOINT", GEMINI_BASE_URL).rstrip("/")

    llm = LLMConfig(
        endpoint=endpoint,
        api_key=api_key,
        model=os.environ.get("LLM_MODEL", "gemini-2.5-pro"),
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "65536")),
        temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
        timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "300")),
    )

    return Config(
        llm=llm,
        output_dir=Path(os.environ.get("OUTPUT_DIR", "./output_project")),
        max_workers=int(os.environ.get("MAX_WORKERS", "10")),
        max_planner_iterations=int(os.environ.get("MAX_PLANNER_ITERATIONS", "100")),
        reconciler_enabled=os.environ.get("RECONCILER_ENABLED", "true").lower() == "true",
        reconciler_interval_s=float(os.environ.get("RECONCILER_INTERVAL_S", "120")),
    )
