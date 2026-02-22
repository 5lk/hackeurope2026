"""Manager planning loop — iterative LLM-driven task decomposition.

Ported from packages/orchestrator/src/planner.ts.  The core loop pattern is:
500ms ticks → check planning triggers → call LLM → parse → dispatch tasks →
collect handoffs → repeat until done.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Config
from .events import EngineEvent, EventBus, EventType
from .gemini import GeminiClient, LLMMessage
from .parsing import PlannerResponse, RawTaskInput, parse_planner_response
from .project_state import read_project_state
from .types import Handoff, HandoffMetrics, Task, TaskStatus, TeamRole

if TYPE_CHECKING:
    from .subplanner import Subplanner
    from .worker import WorkerPool

logger = logging.getLogger("agentswarm.planner")

LOOP_SLEEP_MS = 500
MIN_HANDOFFS_FOR_REPLAN = 3
BACKOFF_BASE_MS = 2_000
BACKOFF_MAX_MS = 30_000
MAX_CONSECUTIVE_ERRORS = 10
MAX_HANDOFF_SUMMARY_CHARS = 400
MAX_FILES_PER_HANDOFF = 30

# Conversation compaction threshold: when the conversation history exceeds
# this many characters total, we compact to keep context manageable.
CONVERSATION_COMPACTION_CHARS = 200_000

# Max times we'll nudge the LLM to emit engineering tasks before giving up.
MAX_EMPTY_PLAN_NUDGES = 3

# Source code extensions — files that count as "real project output" (not just docs).
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb",
    ".php", ".swift", ".kt", ".cs", ".r", ".lua", ".sh", ".bat",
}


class Planner:
    """The Manager — iterative planning loop that decomposes a request into
    tasks, dispatches them to workers/subplanners, and replans based on
    handoff feedback.
    """

    def __init__(
        self,
        config: Config,
        client: GeminiClient,
        worker_pool: WorkerPool,
        system_prompt: str,
        subplanner: Subplanner | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.worker_pool = worker_pool
        self.system_prompt = system_prompt
        self.subplanner = subplanner
        self.event_bus = event_bus

        # Conversation state.
        self.conversation: list[LLMMessage] = []
        self.scratchpad = ""

        # Handoff tracking.
        self.all_handoffs: list[Handoff] = []
        self.handoffs_since_last_plan: list[Handoff] = []
        self.pending_handoffs: list[tuple[Task, Handoff]] = []

        # Task tracking.
        self.active_tasks: set[str] = set()
        self.dispatched_ids: set[str] = set()
        self.all_tasks: list[Task] = []
        self.task_counter = 0

        # Delta tracking for follow-ups.
        self._prev_file_tree: set[str] = set()

        self._running = False
        self._injected_tasks: list[Task] = []

        # Nudge tracking — prevents premature termination when no source files exist.
        self._empty_plan_nudges = 0
        self._nudge_pending = False

    def _emit(self, event: EngineEvent) -> None:
        if self.event_bus:
            self.event_bus.emit(event)

    async def run_loop(self, request: str) -> None:
        """Main entry point — runs the planning loop until all work is done."""
        self._running = True
        self.conversation = [LLMMessage(role="system", content=self.system_prompt)]

        iteration = 0
        planning_done = False
        consecutive_errors = 0

        logger.info("Starting planning loop for request: %s", request[:200])

        while self._running and iteration < self.config.max_planner_iterations:
            # Drain completed handoffs.
            self._collect_completed_handoffs()

            # Inject reconciler fix tasks if any.
            if self._injected_tasks:
                injected = self._injected_tasks[:]
                self._injected_tasks.clear()
                logger.info("Injecting %d fix tasks from reconciler", len(injected))
                self._dispatch_tasks(injected)

            # Planning trigger conditions (same as TS planner.ts).
            has_capacity = self.worker_pool.active_count < self.config.max_workers
            enough_handoffs = len(self.handoffs_since_last_plan) >= MIN_HANDOFFS_FOR_REPLAN
            no_active_work = len(self.active_tasks) == 0 and iteration > 0
            needs_plan = has_capacity and (iteration == 0 or enough_handoffs or no_active_work) and not planning_done

            if needs_plan:
                try:
                    tasks = await self._plan(request, iteration)
                    iteration += 1
                    consecutive_errors = 0
                    self.handoffs_since_last_plan = []

                    if not tasks and not self.active_tasks:
                        if iteration == 1:
                            logger.warning("LLM returned no tasks on first iteration — done")
                            planning_done = True
                        elif self._project_has_source_files():
                            planning_done = True
                        elif self._empty_plan_nudges >= MAX_EMPTY_PLAN_NUDGES:
                            logger.error(
                                "LLM refused to emit engineering tasks after %d nudges — giving up",
                                self._empty_plan_nudges,
                            )
                            planning_done = True
                        else:
                            self._empty_plan_nudges += 1
                            self._nudge_pending = True
                            logger.warning(
                                "LLM returned 0 tasks but no source files exist — nudging (%d/%d)",
                                self._empty_plan_nudges,
                                MAX_EMPTY_PLAN_NUDGES,
                            )
                    elif tasks:
                        self._empty_plan_nudges = 0
                        self._dispatch_tasks(tasks)

                except Exception as e:
                    consecutive_errors += 1
                    backoff_s = min(
                        (BACKOFF_BASE_MS / 1000) * (2 ** (consecutive_errors - 1)),
                        BACKOFF_MAX_MS / 1000,
                    )
                    logger.error(
                        "Planning failed (attempt %d), retrying in %.0fs: %s",
                        consecutive_errors,
                        backoff_s,
                        e,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error("Aborting after %d consecutive failures", MAX_CONSECUTIVE_ERRORS)
                        break
                    await asyncio.sleep(backoff_s)
                    continue

            # Done?
            if planning_done and not self.active_tasks:
                break

            await asyncio.sleep(LOOP_SLEEP_MS / 1000)

        # Wait for any remaining active tasks.
        while self.active_tasks and self._running:
            self._collect_completed_handoffs()
            await asyncio.sleep(LOOP_SLEEP_MS / 1000)

        self._running = False
        logger.info(
            "Planning loop complete — %d iterations, %d tasks dispatched, %d handoffs collected",
            iteration,
            len(self.dispatched_ids),
            len(self.all_handoffs),
        )

    async def _plan(self, request: str, iteration: int) -> list[Task]:
        """Build the prompt, call LLM, parse response, return new Task objects."""
        state = read_project_state(self.config.output_dir)

        if iteration == 0:
            msg = self._build_initial_message(request, state.file_tree)
        else:
            msg = self._build_follow_up_message(state.file_tree)

        self.conversation.append(LLMMessage(role="user", content=msg))
        self._maybe_compact_conversation()

        logger.info(
            "Planning iteration %d (handoffs=%d, active=%d, dispatched=%d)",
            iteration + 1,
            len(self.handoffs_since_last_plan),
            len(self.active_tasks),
            len(self.dispatched_ids),
        )

        self._emit(EngineEvent(
            type=EventType.PLANNING_ITERATION,
            data={"iteration": iteration + 1},
        ))

        response = await self.client.complete(self.conversation)

        # Add assistant response to conversation history.
        self.conversation.append(LLMMessage(role="assistant", content=response.content))

        # Parse.
        parsed = parse_planner_response(response.content)
        if parsed.scratchpad:
            self.scratchpad = parsed.scratchpad
            logger.debug("Scratchpad: %s", self.scratchpad[:500])

        # Build Task objects.
        tasks = self._build_tasks_from_raw(parsed.tasks)

        logger.info(
            "Plan produced %d new tasks (tokens=%d, latency=%dms)",
            len(tasks),
            response.total_tokens,
            response.latency_ms,
        )

        # Update delta tracking.
        self._prev_file_tree = set(state.file_tree)

        return tasks

    def _build_initial_message(self, request: str, file_tree: list[str]) -> str:
        parts = [
            f"## User Request\n{request}\n",
            f"## Project File Tree\n",
        ]
        if file_tree:
            parts.append("\n".join(file_tree))
        else:
            parts.append("(empty project — nothing built yet)")
        parts.append("\n\nThis is the initial planning call. Analyze the request and produce your first batch of tasks.")
        return "\n".join(parts)

    def _build_follow_up_message(self, file_tree: list[str]) -> str:
        parts: list[str] = []

        # Delta file tree.
        current_set = set(file_tree)
        new_files = sorted(current_set - self._prev_file_tree)
        removed_files = sorted(self._prev_file_tree - current_set)

        parts.append("## Project State Update\n")
        if new_files:
            parts.append(f"### New files ({len(new_files)})\n" + "\n".join(new_files))
        if removed_files:
            parts.append(f"### Removed files ({len(removed_files)})\n" + "\n".join(removed_files))
        if not new_files and not removed_files:
            parts.append("No file tree changes since last plan.")

        parts.append(f"\nTotal files: {len(file_tree)}")

        # New handoffs.
        if self.handoffs_since_last_plan:
            parts.append(f"\n## Task Handoffs ({len(self.handoffs_since_last_plan)} since last plan)\n")
            for h in self.handoffs_since_last_plan:
                parts.append(f"### Task {h.task_id} — {h.status}")
                summary = h.summary[:MAX_HANDOFF_SUMMARY_CHARS]
                if len(h.summary) > MAX_HANDOFF_SUMMARY_CHARS:
                    summary += "..."
                parts.append(f"Summary: {summary}")

                files = [str(f) for f in h.files_changed[:MAX_FILES_PER_HANDOFF]]
                if len(h.files_changed) > MAX_FILES_PER_HANDOFF:
                    files.append(f"... ({len(h.files_changed) - MAX_FILES_PER_HANDOFF} more)")
                parts.append(f"Files changed: {', '.join(files)}")

                if h.concerns:
                    parts.append(f"Concerns: {'; '.join(str(c) for c in h.concerns)}")
                if h.suggestions:
                    parts.append(f"Suggestions: {'; '.join(str(s) for s in h.suggestions)}")
                parts.append("")

        # Active tasks.
        if self.active_tasks:
            parts.append(f"\n## Currently Active Tasks ({len(self.active_tasks)})")
            for tid in sorted(self.active_tasks):
                task = next((t for t in self.all_tasks if t.id == tid), None)
                if task:
                    parts.append(f"- {tid}: {task.description[:120]}")
            parts.append("")

        parts.append(
            "Continue planning. Review handoffs and project state. "
            "Rewrite your scratchpad and emit the next batch of tasks. "
            "Return empty tasks array if all work is done."
        )

        # Inject a strong nudge if the LLM tried to stop without creating source files.
        if self._nudge_pending:
            self._nudge_pending = False
            parts.append(
                "\n\n## CRITICAL — PROJECT INCOMPLETE\n\n"
                "You returned an empty tasks array on the previous iteration, but the project "
                "has NO source code files yet — only documentation/spec files exist. "
                "The project is NOT done.\n\n"
                "You MUST now emit Engineering tasks. The minimum deliverables before you can "
                "return an empty tasks array:\n"
                "1. A constants/config file with all shared values\n"
                "2. A main entry point file (main.py, index.html, etc.)\n"
                "3. All core feature source files\n"
                "4. A requirements.txt (if applicable)\n\n"
                "Review the SPEC.md / handoff reports and create Engineering tasks for the "
                "ACTUAL implementation NOW. Do NOT return an empty tasks array."
            )

        return "\n".join(parts)

    def _build_tasks_from_raw(self, raw_tasks: list[RawTaskInput]) -> list[Task]:
        """Convert raw LLM output to Task objects, deduplicating by ID."""
        tasks: list[Task] = []

        for raw in raw_tasks:
            if not raw.description or not raw.description.strip():
                continue

            self.task_counter += 1
            task_id = raw.id or f"task-{self.task_counter:03d}"

            if task_id in self.dispatched_ids:
                logger.debug("Skipping duplicate task ID: %s", task_id)
                continue

            # Parse team.
            team = TeamRole.ENGINEERING
            if raw.team:
                try:
                    team = TeamRole(raw.team.lower())
                except ValueError:
                    pass

            task = Task(
                id=task_id,
                description=raw.description,
                scope=raw.scope or [],
                acceptance=raw.acceptance or "",
                priority=raw.priority or 5,
                team=team,
            )
            tasks.append(task)

        return tasks

    def _dispatch_tasks(self, tasks: list[Task]) -> None:
        """Fire-and-forget dispatch of tasks to workers/subplanners."""
        for task in tasks:
            if task.id in self.dispatched_ids:
                continue

            self.dispatched_ids.add(task.id)
            self.active_tasks.add(task.id)
            self.all_tasks.append(task)

            logger.info(
                "Dispatching task %s (team=%s, scope=%d, priority=%d): %s",
                task.id,
                task.team.value,
                len(task.scope),
                task.priority,
                task.description[:100],
            )

            self._emit(EngineEvent(
                type=EventType.TASK_DISPATCHED,
                task_id=task.id,
                parent_id=task.parent_id,
                team=task.team.value if task.team else "engineering",
                description=task.description[:200],
            ))

            asyncio.create_task(self._dispatch_single(task))

    async def _dispatch_single(self, task: Task) -> None:
        """Execute a single task, handling subplanner decomposition."""
        try:
            # Check if decomposition is needed.
            if self.subplanner and self.subplanner.should_decompose(task, depth=0):
                logger.info("Task %s is complex (scope=%d) — decomposing via subplanner", task.id, len(task.scope))
                self._emit(EngineEvent(
                    type=EventType.SUBPLANNER_STARTED,
                    task_id=task.id,
                    description=f"Decomposing complex task (scope={len(task.scope)})",
                ))
                handoff = await self.subplanner.decompose_and_execute(task, depth=0)
            else:
                handoff = await self.worker_pool.execute_task(task)

            self.pending_handoffs.append((task, handoff))

        except Exception as e:
            logger.error("Task %s dispatch failed: %s", task.id, e)
            self.pending_handoffs.append((
                task,
                Handoff(
                    task_id=task.id,
                    status="failed",
                    summary=f"Dispatch failed: {e}",
                    concerns=[str(e)],
                    metrics=HandoffMetrics(duration_ms=0),
                ),
            ))

    def _collect_completed_handoffs(self) -> None:
        """Drain pending handoffs into the accumulator lists."""
        while self.pending_handoffs:
            task, handoff = self.pending_handoffs.pop(0)
            self.all_handoffs.append(handoff)
            self.handoffs_since_last_plan.append(handoff)
            self.active_tasks.discard(task.id)

    def _maybe_compact_conversation(self) -> None:
        """If the conversation is too long, compact to avoid context overflow."""
        total_chars = sum(len(m.content) for m in self.conversation)
        if total_chars <= CONVERSATION_COMPACTION_CHARS:
            return

        logger.warning(
            "Conversation compaction triggered (%d chars > %d threshold)",
            total_chars,
            CONVERSATION_COMPACTION_CHARS,
        )

        # Keep: system prompt (index 0), first user msg (index 1), last 5 exchanges.
        system_msg = self.conversation[0]
        first_user = self.conversation[1] if len(self.conversation) > 1 else None
        recent = self.conversation[-10:]  # last 5 exchanges = 10 messages

        compacted = [system_msg]
        if first_user and first_user not in recent:
            compacted.append(first_user)

        # Add a summary of what was compacted.
        compacted.append(LLMMessage(
            role="user",
            content=f"[Context compacted — {len(self.conversation) - len(recent)} earlier messages removed. "
                    f"Current scratchpad: {self.scratchpad[:1000]}. "
                    f"Total tasks dispatched: {len(self.dispatched_ids)}. "
                    f"Active tasks: {len(self.active_tasks)}. "
                    f"Total handoffs: {len(self.all_handoffs)}.]"
        ))

        compacted.extend(recent)
        self.conversation = compacted

        logger.info(
            "Conversation compacted: %d messages, %d chars",
            len(self.conversation),
            sum(len(m.content) for m in self.conversation),
        )

    def _project_has_source_files(self) -> bool:
        """Check if the output project contains actual source code files (not just docs)."""
        state = read_project_state(self.config.output_dir)
        for f in state.file_tree:
            ext = "." + f.rsplit(".", 1)[-1].lower() if "." in f else ""
            if ext in _SOURCE_EXTENSIONS:
                return True
        return False

    def inject_tasks(self, tasks: list[Task]) -> None:
        """Called by the reconciler to inject fix tasks into the next planning cycle."""
        self._injected_tasks.extend(tasks)

    def stop(self) -> None:
        self._running = False
