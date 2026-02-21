from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from packages.core.src.llm_client import LLMClient
from packages.orchestrator.src.orchestrator import Orchestrator, OrchestratorConfig


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the multi-department orchestration system."
    )
    parser.add_argument("prompt", type=str, help="User prompt for the Manager.")
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-1.5-pro",
        help="Gemini model name (default: gemini-1.5-pro).",
    )
    parser.add_argument(
        "--prompts-dir",
        type=str,
        default=None,
        help="Optional override path to the prompts directory.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Gemini models and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    load_dotenv()

    if args.list_models:
        try:
            llm = LLMClient(model=args.model)
        except Exception as exc:
            print(f"Failed to initialize Gemini client: {exc}", file=sys.stderr)
            sys.exit(1)

        models = llm.list_models()
        print("Available models:")
        for model in models:
            print(f"- {model}")
        sys.exit(0)

    try:
        llm = LLMClient(model=args.model)
    except Exception as exc:
        print(f"Failed to initialize Gemini client: {exc}", file=sys.stderr)
        sys.exit(1)

    config = OrchestratorConfig(prompts_dir=args.prompts_dir)
    orchestrator = Orchestrator(llm, config)

    handoffs = orchestrator.run(args.prompt)

    print("Orchestration complete.")
    print(f"Handoffs produced: {len(handoffs)}")
    for handoff in handoffs:
        print(f"- {handoff.task_id}: {handoff.summary}")

    print("\n[manager] : how to run")
    run_instructions = orchestrator.manager.finalize_run_instructions(
        orchestrator.config.output_dir
    )
    print(run_instructions)


if __name__ == "__main__":
    main()
