#!/usr/bin/env python3
"""AgentSwarm — Multi-agent project builder powered by Gemini API.

Usage:
    python -m agentswarm.main                          # prompts for idea
    python -m agentswarm.main "make flappy bird"       # idea as argument
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import load_config
from .events import EngineEvent, EventBus, EventType
from .gemini import GeminiClient, LLMMessage
from .logger import get_logger, setup_logging
from .parsing import parse_worker_response
from .planner import Planner
from .project_state import read_project_state, read_file_contents
from .reconciler import Reconciler
from .subplanner import Subplanner
from .worker import WorkerPool

logger = get_logger("main")

MAX_VALIDATION_ROUNDS = 3
VALIDATION_TIMEOUT_S = 30


async def run(request: str) -> None:
    config = load_config()
    setup_logging(level="info")

    logger.info("AgentSwarm starting")
    logger.info("Request: %s", request)
    logger.info("Model: %s", config.llm.model)
    logger.info("Max workers: %d", config.max_workers)
    logger.info("Output dir: %s", config.output_dir.resolve())

    # Clean output directory from previous runs.
    if config.output_dir.exists():
        shutil.rmtree(config.output_dir)
        logger.info("Cleared previous output directory")

    # Ensure output directory exists.
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Build components.
    client = GeminiClient(
        endpoint=config.llm.endpoint,
        api_key=config.llm.api_key,
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        temperature=config.llm.temperature,
        timeout_s=config.llm.timeout_s,
    )

    # Flesh out vague ideas into detailed specs.
    print()
    print("  Expanding idea...")
    request = await _flesh_out_idea(client, request)
    print(f"  Specification:\n  {request[:300]}{'...' if len(request) > 300 else ''}")
    print()
    logger.info("Expanded request: %s", request[:500])

    prompts_dir = Path(__file__).parent / "prompts"

    worker_pool = WorkerPool(client, config.output_dir, prompts_dir, config.max_workers)
    worker_pool.load_prompts()

    root_prompt = (prompts_dir / "root-planner.md").read_text(encoding="utf-8")
    subplanner_prompt = (prompts_dir / "subplanner.md").read_text(encoding="utf-8")

    subplanner = Subplanner(config, client, worker_pool, subplanner_prompt)
    planner = Planner(config, client, worker_pool, root_prompt, subplanner)

    # Reconciler (optional background task).
    reconciler_task = None
    reconciler = None
    if config.reconciler_enabled:
        reconciler_prompt_path = prompts_dir / "reconciler.md"
        if reconciler_prompt_path.exists():
            reconciler_prompt = reconciler_prompt_path.read_text(encoding="utf-8")
            reconciler = Reconciler(config, client, reconciler_prompt, config.output_dir)
            reconciler.on_fix_tasks = planner.inject_tasks
            reconciler_task = asyncio.create_task(reconciler.run_periodic())

    start_time = time.time()

    try:
        await planner.run_loop(request)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        planner.stop()
    finally:
        if reconciler:
            reconciler.stop()
        if reconciler_task:
            reconciler_task.cancel()
            try:
                await reconciler_task
            except asyncio.CancelledError:
                pass

    elapsed_build = time.time() - start_time
    total_tasks = len(planner.dispatched_ids)
    total_handoffs = len(planner.all_handoffs)
    completed = sum(1 for h in planner.all_handoffs if h.status == "complete")

    print()
    print("=" * 60)
    print(f"  AgentSwarm — Build Complete")
    print(f"  Time:     {elapsed_build:.1f}s")
    print(f"  Tasks:    {total_tasks} dispatched, {completed} completed")
    print(f"  Tokens:   {client.total_tokens_used:,}")
    print(f"  API calls: {client.total_requests}")
    print(f"  Output:   {config.output_dir.resolve()}")
    print("=" * 60)

    # --- Generate launch script ---
    print()
    print("  Generating launch script...")
    await _generate_launch_script(client, config.output_dir)

    # --- Post-build validation ---
    print()
    print("=" * 60)
    print("  Post-Build Validation")
    print("=" * 60)

    # Step 1: Install dependencies if requirements.txt exists.
    await _install_dependencies(config.output_dir)

    # Step 2: Validation loop — run code, run tests, fix errors.
    engineering_prompt = (prompts_dir / "engineering.md").read_text(encoding="utf-8")
    await _validation_loop(client, config.output_dir, engineering_prompt)

    await client.close()

    total_elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"  AgentSwarm — All Done")
    print(f"  Total time: {total_elapsed:.1f}s")
    print(f"  Total tokens: {client.total_tokens_used:,}")
    print(f"  Total API calls: {client.total_requests}")
    print("=" * 60)


async def _generate_launch_script(client: GeminiClient, output_dir: Path) -> None:
    """Ask Gemini to write a launch.bat that runs the project with zero intervention."""
    state = read_project_state(output_dir)
    all_contents = read_file_contents(output_dir, state.file_tree)

    file_tree_str = "\n".join(state.file_tree) if state.file_tree else "(empty)"
    contents_str = ""
    for path, content in all_contents.items():
        contents_str += f"\n### {path}\n```\n{content}\n```\n"

    messages = [
        LLMMessage(role="system", content=(
            "You are a devops helper. You write Windows batch files. "
            "Respond with ONLY the raw batch file content. No markdown fences. No explanation."
        )),
        LLMMessage(role="user", content=f"""Write a Windows batch file called launch.bat that launches this project with ZERO human intervention.

Rules:
- The bat file lives in the project root directory (same folder as the files listed below)
- It should install any dependencies first (pip install -r requirements.txt if it exists, or pip install specific packages)
- Then launch the main entry point of the project
- For Python projects: use `python main.py` or `python -m package_name` as appropriate
- For HTML/JS projects: use `start index.html` to open in browser, OR if it needs a server use `python -m http.server 8000` then `start http://localhost:8000`
- Include `@echo off` at the top
- Include `pause` at the end so the window stays open if there are errors
- If the project uses pygame, try `pip install pygame-ce` as fallback if `pip install pygame` fails
- Keep it simple and robust

## Project File Tree
{file_tree_str}

## Project Files
{contents_str}
"""),
    ]

    try:
        response = await client.complete(messages)
        bat_content = response.content.strip()

        # Strip markdown fences if Gemini wrapped it anyway.
        if bat_content.startswith("```"):
            lines = bat_content.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            bat_content = "\n".join(lines)

        bat_path = output_dir / "launch.bat"
        bat_path.write_text(bat_content, encoding="utf-8")
        print(f"  Created: {bat_path.resolve()}")
    except Exception as e:
        logger.warning("Failed to generate launch.bat: %s", e)
        print(f"  WARNING: Could not generate launch.bat: {e}")


async def _flesh_out_idea(client: GeminiClient, raw_idea: str) -> str:
    """Take a vague user idea and expand it into a detailed project specification."""
    messages = [
        LLMMessage(role="system", content=(
            "You are a product designer. The user gives you a short project idea. "
            "Expand it into a clear, detailed specification in 1-2 paragraphs. "
            "Include: what the project is, key features, the main user interactions, and what the end result looks like. "
            "Be specific about colors, layout, and behavior. "
            "\n\n"
            "CRITICAL — Technology choices:\n"
            "- If the user specifies a technology (tkinter, pygame, flask, HTML, etc.), you MUST use that exact technology. Do NOT substitute.\n"
            "- If the user says 'tkinter', use tkinter. Do NOT change it to pygame.\n"
            "- If the user says 'pygame', use pygame.\n"
            "- If the user says 'HTML' or 'web', use HTML/JS/CSS.\n"
            "- Only if NO technology is mentioned, suggest one: Python+pygame for games, HTML/JS/CSS for visual demos, Python+tkinter for desktop apps.\n"
            "\n"
            "IMPORTANT: All graphics must be drawn programmatically (shapes, code-defined colors). "
            "NEVER mention external asset files (no .png, .ttf, .wav). "
            "Respond with ONLY the expanded specification. No preamble."
        )),
        LLMMessage(role="user", content=raw_idea),
    ]

    try:
        response = await client.complete(messages)
        expanded = response.content.strip()
        if len(expanded) > len(raw_idea) * 1.5 and len(expanded) > 100:
            return expanded
        return raw_idea
    except Exception as e:
        logger.warning("Idea expansion failed: %s — using raw input", e)
        return raw_idea


async def _install_dependencies(output_dir: Path) -> None:
    """Install dependencies from requirements.txt if it exists."""
    req_file = output_dir / "requirements.txt"
    if not req_file.exists():
        logger.info("No requirements.txt found — skipping dependency install")
        return

    logger.info("Installing dependencies from requirements.txt")
    print("  Installing dependencies...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(output_dir),
        )
        if result.returncode == 0:
            print("  Dependencies installed successfully.")
            logger.info("pip install succeeded")
        else:
            print(f"  pip install failed (exit {result.returncode})")
            if result.stderr:
                # Try pygame-ce fallback if pygame fails.
                if "pygame" in result.stderr.lower():
                    logger.info("pygame install failed — trying pygame-ce")
                    print("  Retrying with pygame-ce...")
                    # Replace pygame with pygame-ce in requirements.
                    req_text = req_file.read_text(encoding="utf-8")
                    req_text = req_text.replace("pygame", "pygame-ce")
                    req_file.write_text(req_text, encoding="utf-8")
                    result2 = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(output_dir),
                    )
                    if result2.returncode == 0:
                        print("  Dependencies installed with pygame-ce.")
                    else:
                        print(f"  pygame-ce also failed: {result2.stderr[:200]}")
                else:
                    print(f"  Error: {result.stderr[:300]}")
    except subprocess.TimeoutExpired:
        print("  pip install timed out after 120s")
    except Exception as e:
        print(f"  pip install error: {e}")


async def _validation_loop(
    client: GeminiClient,
    output_dir: Path,
    engineering_prompt: str,
) -> None:
    """Run the project and tests, feeding errors back to Gemini for auto-fix."""
    for round_num in range(1, MAX_VALIDATION_ROUNDS + 1):
        print(f"\n  --- Validation Round {round_num}/{MAX_VALIDATION_ROUNDS} ---")

        errors: list[str] = []

        # Find the main entry point.
        entry_point = _find_entry_point(output_dir)

        # Test 1: Run the main entry point (quick check — just import/syntax errors).
        if entry_point:
            print(f"  Running: {entry_point} ...")
            error = _run_project_check(output_dir, entry_point)
            if error:
                errors.append(f"RUNTIME ERROR running {entry_point}:\n{error}")
                print(f"  FAILED: Runtime error detected")
            else:
                print(f"  PASSED: No import/syntax errors")
        else:
            print("  WARNING: No entry point found (no main.py or __main__.py)")

        # Test 2: Run pytest if tests exist.
        test_dirs = _find_test_files(output_dir)
        if test_dirs:
            print(f"  Running tests ({len(test_dirs)} test files found)...")
            error = _run_tests(output_dir)
            if error:
                errors.append(f"TEST FAILURES:\n{error}")
                print(f"  FAILED: Test errors detected")
            else:
                print(f"  PASSED: All tests pass")
        else:
            print("  No test files found — skipping test run")

        # If no errors, we're done!
        if not errors:
            print(f"\n  Validation PASSED on round {round_num}.")
            return

        # Feed errors back to Gemini for auto-fix.
        print(f"\n  {len(errors)} error(s) found — sending to Gemini for auto-fix...")
        fixed = await _auto_fix_errors(client, output_dir, engineering_prompt, errors)
        if not fixed:
            print("  Auto-fix failed or produced no changes.")
            if round_num < MAX_VALIDATION_ROUNDS:
                print("  Retrying...")
            continue

        # Re-install deps in case requirements changed.
        await _install_dependencies(output_dir)

    print(f"\n  Validation completed after {MAX_VALIDATION_ROUNDS} rounds.")
    print("  Some issues may remain — check the output manually.")


def _find_entry_point(output_dir: Path) -> str | None:
    """Find the main entry point of the generated project."""
    # Check common patterns.
    candidates = [
        "main.py",
        "app.py",
        "run.py",
    ]

    for candidate in candidates:
        if (output_dir / candidate).exists():
            return candidate

    # Check for __main__.py in any package.
    for p in output_dir.rglob("__main__.py"):
        rel = p.relative_to(output_dir)
        package = rel.parent
        if package != Path("."):
            return f"-m {package.as_posix().replace('/', '.')}"
        return "__main__.py"

    return None


def _run_project_check(output_dir: Path, entry_point: str) -> str | None:
    """Run the project's entry point in a quick check mode.

    Uses python -c to import and do a syntax/import check without actually
    running the full program (which might open a window, etc.).
    """
    if entry_point.startswith("-m "):
        module = entry_point[3:]
        check_code = f"import importlib; importlib.import_module('{module}')"
    else:
        # For a file, try importing it as a module check.
        module_name = entry_point.replace("/", ".").replace("\\", ".").removesuffix(".py")
        check_code = f"import importlib.util, sys; spec = importlib.util.spec_from_file_location('{module_name}', '{entry_point}'); mod = importlib.util.module_from_spec(spec)"

    try:
        result = subprocess.run(
            [sys.executable, "-c", check_code],
            capture_output=True,
            text=True,
            timeout=VALIDATION_TIMEOUT_S,
            cwd=str(output_dir),
        )
        if result.returncode != 0:
            return (result.stderr or result.stdout or "Unknown error")[:2000]
        return None
    except subprocess.TimeoutExpired:
        return None  # Timeout is OK for GUI apps.
    except Exception as e:
        return str(e)[:500]


def _find_test_files(output_dir: Path) -> list[Path]:
    """Find all test files in the project."""
    test_files = []
    for p in output_dir.rglob("test_*.py"):
        test_files.append(p)
    for p in output_dir.rglob("*_test.py"):
        if p not in test_files:
            test_files.append(p)
    return test_files


def _run_tests(output_dir: Path) -> str | None:
    """Run pytest on the output project."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(output_dir),
        )
        if result.returncode != 0:
            return (result.stdout + "\n" + result.stderr)[:3000]
        return None
    except subprocess.TimeoutExpired:
        return "Tests timed out after 60s"
    except Exception as e:
        return str(e)[:500]


async def _auto_fix_errors(
    client: GeminiClient,
    output_dir: Path,
    engineering_prompt: str,
    errors: list[str],
) -> bool:
    """Send errors + full project code to Gemini and apply fixes."""
    # Read all project files.
    state = read_project_state(output_dir)
    all_contents = read_file_contents(output_dir, state.file_tree)

    file_tree_str = "\n".join(state.file_tree)
    contents_str = ""
    for path, content in all_contents.items():
        contents_str += f"\n### {path}\n```\n{content}\n```\n"

    errors_str = "\n\n".join(errors)

    user_msg = f"""## Auto-Fix Task

The project has been built but has errors that need fixing. Below are the errors and the full project code. Fix ALL errors.

## Errors Found

{errors_str}

## Current Project File Tree
{file_tree_str}

## Full Project Code
{contents_str}

---

Fix all the errors above. Return ONLY a JSON object with file_operations for every file you need to modify.
Key rules:
- Fix the actual errors (NameError, ImportError, etc.)
- Use relative imports within packages (from .module import ...)
- Define all constants before use or import from constants file
- NEVER create external asset files (.png, .ttf, .wav, etc.)
- Include complete file contents for every file you modify
"""

    from .worker import WORKER_RESPONSE_FORMAT

    messages = [
        LLMMessage(role="system", content=engineering_prompt + WORKER_RESPONSE_FORMAT),
        LLMMessage(role="user", content=user_msg),
    ]

    try:
        response = await client.complete(messages)
        result = parse_worker_response(response.content, "auto-fix")

        if not result.file_operations:
            logger.warning("Auto-fix returned no file operations")
            return False

        files_fixed = 0
        for op in result.file_operations:
            # Block asset files.
            ext = "." + op.path.rsplit(".", 1)[-1].lower() if "." in op.path else ""
            asset_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico",
                         ".ttf", ".otf", ".woff", ".mp3", ".wav", ".ogg", ".mp4", ".avi", ".mov"}
            if ext in asset_exts:
                logger.warning("Blocked asset file in auto-fix: %s", op.path)
                continue

            target = output_dir / op.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(op.content, encoding="utf-8")
            files_fixed += 1
            print(f"    Fixed: {op.path}")

        logger.info("Auto-fix applied %d file changes", files_fixed)
        return files_fixed > 0

    except Exception as e:
        logger.error("Auto-fix failed: %s", e)
        return False


async def _conversation_to_spec(client: GeminiClient, conversation: list[dict]) -> str:
    """Convert a conversation transcript into a detailed project specification."""
    conv_text = "\n".join(
        f"{msg.get('role', 'unknown')}: {msg.get('text', '')}"
        for msg in conversation
    )

    messages = [
        LLMMessage(role="system", content=(
            "You are a product designer. You have a conversation transcript between a user and an AI "
            "assistant where the user described their startup or project idea in detail.\n\n"
            "Your job is to extract ALL important details from this conversation and produce a clear, "
            "detailed project specification that a development team can build from immediately.\n\n"
            "Include:\n"
            "- What the project is and its purpose\n"
            "- Key features and functionality\n"
            "- User interactions and flows\n"
            "- Technical requirements and constraints\n"
            "- Visual design details (colors, layout, behavior)\n"
            "- What the end result should look and feel like\n\n"
            "CRITICAL — Technology choices:\n"
            "- If the user specified a technology (tkinter, pygame, flask, HTML, etc.), use that EXACT technology.\n"
            "- If no technology is mentioned, suggest: Python+pygame for games, HTML/JS/CSS for visual demos, "
            "Python+tkinter for desktop apps.\n\n"
            "IMPORTANT: All graphics must be drawn programmatically (shapes, code-defined colors). "
            "NEVER mention external asset files (no .png, .ttf, .wav). "
            "Respond with ONLY the expanded specification. No preamble."
        )),
        LLMMessage(role="user", content=f"Here is the conversation transcript:\n\n{conv_text}"),
    ]

    try:
        response = await client.complete(messages)
        spec = response.content.strip()
        if len(spec) > 100:
            return spec
        return conv_text
    except Exception as e:
        logger.warning("Conversation-to-spec failed: %s — using raw transcript", e)
        return conv_text


async def run_from_conversation(conversation: list[dict], event_bus: EventBus) -> None:
    """Run the engine from a frontend conversation transcript (called by the server)."""
    config = load_config()
    setup_logging(level="info")

    event_bus.emit(EngineEvent(type=EventType.ENGINE_STARTED))

    logger.info("AgentSwarm starting (from conversation, %d messages)", len(conversation))
    logger.info("Model: %s", config.llm.model)
    logger.info("Max workers: %d", config.max_workers)
    logger.info("Output dir: %s", config.output_dir.resolve())

    if config.output_dir.exists():
        shutil.rmtree(config.output_dir)
        logger.info("Cleared previous output directory")
    config.output_dir.mkdir(parents=True, exist_ok=True)

    client = GeminiClient(
        endpoint=config.llm.endpoint,
        api_key=config.llm.api_key,
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        temperature=config.llm.temperature,
        timeout_s=config.llm.timeout_s,
    )

    # Convert conversation to spec instead of fleshing out a single idea.
    request = await _conversation_to_spec(client, conversation)
    event_bus.emit(EngineEvent(
        type=EventType.SPEC_CREATED,
        data={"spec": request},
    ))
    logger.info("Spec from conversation: %s", request[:500])

    prompts_dir = Path(__file__).parent / "prompts"

    worker_pool = WorkerPool(client, config.output_dir, prompts_dir, config.max_workers, event_bus)
    worker_pool.load_prompts()

    root_prompt = (prompts_dir / "root-planner.md").read_text(encoding="utf-8")
    subplanner_prompt = (prompts_dir / "subplanner.md").read_text(encoding="utf-8")

    subplanner = Subplanner(config, client, worker_pool, subplanner_prompt, event_bus)
    planner = Planner(config, client, worker_pool, root_prompt, subplanner, event_bus)

    reconciler_task = None
    reconciler = None
    if config.reconciler_enabled:
        reconciler_prompt_path = prompts_dir / "reconciler.md"
        if reconciler_prompt_path.exists():
            reconciler_prompt = reconciler_prompt_path.read_text(encoding="utf-8")
            reconciler = Reconciler(config, client, reconciler_prompt, config.output_dir, event_bus)
            reconciler.on_fix_tasks = planner.inject_tasks
            reconciler_task = asyncio.create_task(reconciler.run_periodic())

    start_time = time.time()

    try:
        await planner.run_loop(request)
    except KeyboardInterrupt:
        planner.stop()
    except Exception as e:
        logger.error("Engine error: %s", e)
    finally:
        if reconciler:
            reconciler.stop()
        if reconciler_task:
            reconciler_task.cancel()
            try:
                await reconciler_task
            except asyncio.CancelledError:
                pass

    elapsed = time.time() - start_time
    total_tasks = len(planner.dispatched_ids)
    completed = sum(1 for h in planner.all_handoffs if h.status == "complete")

    event_bus.emit(EngineEvent(
        type=EventType.BUILD_COMPLETE,
        data={
            "time": round(elapsed, 1),
            "tasks_dispatched": total_tasks,
            "tasks_completed": completed,
            "tokens": client.total_tokens_used,
            "api_calls": client.total_requests,
        },
    ))

    # Generate launch script.
    await _generate_launch_script(client, config.output_dir)

    # Post-build validation.
    engineering_prompt = (prompts_dir / "engineering.md").read_text(encoding="utf-8")

    event_bus.emit(EngineEvent(type=EventType.VALIDATION_STARTED))
    await _install_dependencies(config.output_dir)
    await _validation_loop(client, config.output_dir, engineering_prompt)

    await client.close()

    event_bus.emit(EngineEvent(
        type=EventType.ENGINE_DONE,
        data={
            "total_time": round(time.time() - start_time, 1),
            "total_tokens": client.total_tokens_used,
        },
    ))


def main() -> None:
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        print()
        print("  AgentSwarm — Multi-agent Project Builder")
        print("  Powered by Gemini API")
        print()
        request = input("  What would you like to build? > ").strip()
        if not request:
            print("No request provided. Exiting.")
            sys.exit(1)

    asyncio.run(run(request))


if __name__ == "__main__":
    main()
