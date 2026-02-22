"""Recursive task decomposition — ported from subplanner.ts.

When a task's scope is large enough (>= SCOPE_THRESHOLD files) and depth
hasn't exceeded MAX_DEPTH, the subplanner breaks it into subtasks, dispatches
them (potentially recursing), and aggregates the handoffs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .config import Config
from .events import EngineEvent, EventBus, EventType
from .gemini import GeminiClient, LLMMessage
from .parsing import PlannerResponse, RawTaskInput, parse_planner_response
from .project_state import read_project_state
from .types import Handoff, HandoffMetrics, Task, TaskStatus, TeamRole

if TYPE_CHECKING:
    from .worker import WorkerPool

logger = logging.getLogger("agentswarm.subplanner")

MAX_DEPTH = 3
SCOPE_THRESHOLD = 4
MAX_SUBTASKS = 10
LOOP_SLEEP_S = 0.5
MIN_HANDOFFS_FOR_REPLAN = 1
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 30.0
MAX_CONSECUTIVE_ERRORS = 5
MAX_SUBPLANNER_ITERATIONS = 20
MAX_HANDOFF_SUMMARY_CHARS = 300
MAX_FILES_PER_HANDOFF = 30


class Subplanner:
    """Recursive decomposition engine for complex tasks."""

    def __init__(
        self,
        config: Config,
        client: GeminiClient,
        worker_pool: WorkerPool,
        system_prompt: str,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.worker_pool = worker_pool
        self.system_prompt = system_prompt
        self.event_bus = event_bus

    def _emit(self, event: EngineEvent) -> None:
        if self.event_bus:
            self.event_bus.emit(event)

    def should_decompose(self, task: Task, depth: int) -> bool:
        """Check if a task warrants decomposition."""
        if depth >= MAX_DEPTH:
            return False
        if len(task.scope) < SCOPE_THRESHOLD:
            return False
        return True

    async def decompose_and_execute(self, parent_task: Task, depth: int = 0) -> Handoff:
        """Decompose a parent task into subtasks, dispatch them, collect handoffs."""
        logger.info(
            "Subplanner starting — task=%s depth=%d scope=%d",
            parent_task.id,
            depth,
            len(parent_task.scope),
        )

        pending_handoffs: list[tuple[Task, Handoff]] = []
        all_handoffs: list[Handoff] = []
        handoffs_since_last_plan: list[Handoff] = []
        active_tasks: set[str] = set()
        dispatched_ids: set[str] = set()
        all_subtasks: list[Task] = []

        conversation = [LLMMessage(role="system", content=self.system_prompt)]
        scratchpad = ""
        iteration = 0
        planning_done = False
        consecutive_errors = 0

        try:
            while iteration < MAX_SUBPLANNER_ITERATIONS:
                # Drain completed handoffs.
                self._collect_handoffs(pending_handoffs, all_handoffs, handoffs_since_last_plan, active_tasks)

                has_capacity = self.worker_pool.active_count < self.config.max_workers
                enough_handoffs = len(handoffs_since_last_plan) >= MIN_HANDOFFS_FOR_REPLAN
                no_active = len(active_tasks) == 0 and iteration > 0
                needs_plan = has_capacity and (iteration == 0 or enough_handoffs or no_active) and not planning_done

                if needs_plan:
                    try:
                        state = read_project_state(self.config.output_dir)

                        if iteration == 0:
                            msg = self._build_initial_message(parent_task, state.file_tree, depth)
                        else:
                            msg = self._build_follow_up_message(
                                state.file_tree, handoffs_since_last_plan, active_tasks, all_subtasks,
                            )

                        conversation.append(LLMMessage(role="user", content=msg))

                        logger.info(
                            "Subplanner iteration %d for %s (handoffs=%d, active=%d)",
                            iteration + 1,
                            parent_task.id,
                            len(handoffs_since_last_plan),
                            len(active_tasks),
                        )

                        response = await self.client.complete(conversation)
                        conversation.append(LLMMessage(role="assistant", content=response.content))

                        parsed = parse_planner_response(response.content)
                        if parsed.scratchpad:
                            scratchpad = parsed.scratchpad

                        subtasks = self._build_subtasks(parsed.tasks, parent_task, dispatched_ids)

                        handoffs_since_last_plan = []
                        iteration += 1
                        consecutive_errors = 0

                        if not subtasks and len(active_tasks) == 0:
                            if iteration == 1:
                                # Atomic task — send directly to worker.
                                logger.info("Task %s is atomic — sending to worker directly", parent_task.id)
                                handoff = await self.worker_pool.execute_task(parent_task)
                                return handoff
                            else:
                                planning_done = True
                        elif subtasks:
                            all_subtasks.extend(subtasks)
                            self._dispatch_subtasks(
                                subtasks, parent_task, depth,
                                pending_handoffs, active_tasks, dispatched_ids,
                            )

                    except Exception as e:
                        consecutive_errors += 1
                        backoff = min(BACKOFF_BASE_S * (2 ** (consecutive_errors - 1)), BACKOFF_MAX_S)
                        logger.error(
                            "Subplanner plan failed (attempt %d) for %s: %s",
                            consecutive_errors,
                            parent_task.id,
                            e,
                        )
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            break
                        await asyncio.sleep(backoff)
                        continue

                if planning_done and not active_tasks:
                    break
                if not planning_done and not active_tasks and iteration > 0 and not handoffs_since_last_plan:
                    break

                await asyncio.sleep(LOOP_SLEEP_S)

            # Final drain.
            self._collect_handoffs(pending_handoffs, all_handoffs, handoffs_since_last_plan, active_tasks)

            # Wait for stragglers.
            while active_tasks:
                self._collect_handoffs(pending_handoffs, all_handoffs, handoffs_since_last_plan, active_tasks)
                await asyncio.sleep(LOOP_SLEEP_S)

            return self._aggregate_handoffs(parent_task, all_subtasks, all_handoffs)

        except Exception as e:
            logger.error("Subplanner failed for %s: %s", parent_task.id, e)
            return Handoff(
                task_id=parent_task.id,
                status="failed",
                summary=f"Subplanner decomposition failed: {e}",
                concerns=[str(e)],
                metrics=HandoffMetrics(duration_ms=0),
            )

    def _build_initial_message(self, parent: Task, file_tree: list[str], depth: int) -> str:
        parts = [
            f"## Parent Task",
            f"- **ID**: {parent.id}",
            f"- **Description**: {parent.description}",
            f"- **Scope**: {', '.join(parent.scope)}",
            f"- **Acceptance**: {parent.acceptance}",
            f"- **Priority**: {parent.priority}",
            f"- **Team**: {parent.team.value if parent.team else 'engineering'}",
            f"- **Decomposition Depth**: {depth}",
            "",
            f"## Project File Tree",
            "\n".join(file_tree) if file_tree else "(empty project)",
            "",
            "This is the initial planning call. Respond with a JSON object: "
            '{ "scratchpad": "your analysis", "tasks": [...] }. '
            "If the task is atomic, return empty tasks array.",
        ]
        return "\n".join(parts)

    def _build_follow_up_message(
        self,
        file_tree: list[str],
        new_handoffs: list[Handoff],
        active_tasks: set[str],
        all_subtasks: list[Task],
    ) -> str:
        parts = [f"## Updated Project File Tree\n{chr(10).join(file_tree)}\n"]

        if new_handoffs:
            parts.append(f"## New Subtask Handoffs ({len(new_handoffs)} since last plan)")
            for h in new_handoffs:
                parts.append(f"### Task {h.task_id} — {h.status}")
                summary = h.summary[:MAX_HANDOFF_SUMMARY_CHARS]
                parts.append(f"Summary: {summary}")
                files = [str(f) for f in h.files_changed[:MAX_FILES_PER_HANDOFF]]
                parts.append(f"Files changed: {', '.join(files)}")
                if h.concerns:
                    parts.append(f"Concerns: {'; '.join(str(c) for c in h.concerns)}")
                if h.suggestions:
                    parts.append(f"Suggestions: {'; '.join(str(s) for s in h.suggestions)}")
                parts.append("")

        if active_tasks:
            parts.append(f"## Currently Active Subtasks ({len(active_tasks)})")
            for tid in sorted(active_tasks):
                t = next((st for st in all_subtasks if st.id == tid), None)
                if t:
                    parts.append(f"- {tid}: {t.description[:120]}")
            parts.append("")

        parts.append(
            "Continue planning. Review handoffs and emit next batch. "
            "Return empty tasks array if all work is done."
        )
        return "\n".join(parts)

    def _build_subtasks(
        self,
        raw_tasks: list[RawTaskInput],
        parent: Task,
        dispatched_ids: set[str],
    ) -> list[Task]:
        subtasks: list[Task] = []
        sub_counter = len(dispatched_ids)

        for raw in raw_tasks:
            if not raw.description or not raw.description.strip():
                continue

            sub_counter += 1
            task_id = raw.id or f"{parent.id}-sub-{sub_counter}"

            if task_id in dispatched_ids:
                logger.debug("Skipping duplicate subtask %s", task_id)
                continue

            # Validate scope is subset of parent.
            valid_scope = raw.scope or []
            if parent.scope:
                invalid = [f for f in valid_scope if f not in parent.scope]
                if invalid:
                    logger.warning(
                        "Subtask %s scope has files outside parent — removing: %s",
                        task_id,
                        invalid,
                    )
                    valid_scope = [f for f in valid_scope if f in parent.scope]
                    if not valid_scope:
                        logger.warning("Subtask %s has no valid scope — skipping", task_id)
                        continue

            team = parent.team or TeamRole.ENGINEERING
            if raw.team:
                try:
                    team = TeamRole(raw.team.lower())
                except ValueError:
                    pass

            subtasks.append(Task(
                id=task_id,
                parent_id=parent.id,
                description=raw.description,
                scope=valid_scope,
                acceptance=raw.acceptance or "",
                priority=raw.priority or parent.priority,
                team=team,
            ))

        if len(subtasks) > MAX_SUBTASKS:
            logger.warning(
                "Too many subtasks (%d) for %s — truncating to %d",
                len(subtasks),
                parent.id,
                MAX_SUBTASKS,
            )
            subtasks = subtasks[:MAX_SUBTASKS]

        return subtasks

    def _dispatch_subtasks(
        self,
        subtasks: list[Task],
        parent: Task,
        current_depth: int,
        pending_handoffs: list[tuple[Task, Handoff]],
        active_tasks: set[str],
        dispatched_ids: set[str],
    ) -> None:
        for st in subtasks:
            dispatched_ids.add(st.id)
            active_tasks.add(st.id)

            logger.info(
                "Dispatching subtask %s (team=%s, scope=%d): %s",
                st.id,
                st.team.value,
                len(st.scope),
                st.description[:100],
            )

            self._emit(EngineEvent(
                type=EventType.SUBTASK_DISPATCHED,
                task_id=st.id,
                parent_id=parent.id,
                team=st.team.value if st.team else "engineering",
                description=st.description[:200],
            ))

            asyncio.create_task(
                self._execute_subtask(st, parent, current_depth, pending_handoffs, active_tasks)
            )

    async def _execute_subtask(
        self,
        subtask: Task,
        parent: Task,
        current_depth: int,
        pending_handoffs: list[tuple[Task, Handoff]],
        active_tasks: set[str],
    ) -> None:
        try:
            if self.should_decompose(subtask, current_depth + 1):
                logger.info(
                    "Subtask %s still complex — recursing (depth=%d)",
                    subtask.id,
                    current_depth + 1,
                )
                handoff = await self.decompose_and_execute(subtask, current_depth + 1)
            else:
                handoff = await self.worker_pool.execute_task(subtask)

            pending_handoffs.append((subtask, handoff))

        except Exception as e:
            logger.error("Subtask %s failed: %s", subtask.id, e)
            pending_handoffs.append((
                subtask,
                Handoff(
                    task_id=subtask.id,
                    status="failed",
                    summary=f"Subtask execution failed: {e}",
                    concerns=[str(e)],
                    metrics=HandoffMetrics(duration_ms=0),
                ),
            ))
        finally:
            active_tasks.discard(subtask.id)

    @staticmethod
    def _collect_handoffs(
        pending: list[tuple[Task, Handoff]],
        all_handoffs: list[Handoff],
        since_last_plan: list[Handoff],
        active_tasks: set[str],
    ) -> None:
        while pending:
            task, handoff = pending.pop(0)
            all_handoffs.append(handoff)
            since_last_plan.append(handoff)
            active_tasks.discard(task.id)

    @staticmethod
    def _aggregate_handoffs(parent: Task, subtasks: list[Task], handoffs: list[Handoff]) -> Handoff:
        completed = sum(1 for h in handoffs if h.status == "complete")
        failed = sum(1 for h in handoffs if h.status == "failed")
        total = len(subtasks)

        if completed == total:
            status = "complete"
        elif failed == total:
            status = "failed"
        elif completed > 0:
            status = "partial"
        else:
            status = "blocked"

        summary_parts = [f"[{h.task_id}] ({h.status}): {h.summary}" for h in handoffs]
        summary = (
            f'Decomposed "{parent.description[:80]}" into {total} subtasks. '
            f"{completed} complete, {failed} failed, {total - completed - failed} other.\n\n"
            + "\n".join(summary_parts)
        )

        all_files: set[str] = set()
        all_concerns: list[str] = []
        all_suggestions: list[str] = []
        total_tokens = 0
        max_duration = 0

        for h in handoffs:
            all_files.update(h.files_changed)
            all_concerns.extend(f"[{h.task_id}] {c}" for c in h.concerns)
            all_suggestions.extend(f"[{h.task_id}] {s}" for s in h.suggestions)
            total_tokens += h.metrics.tokens_used
            max_duration = max(max_duration, h.metrics.duration_ms)

        return Handoff(
            task_id=parent.id,
            status=status,
            summary=summary,
            files_changed=sorted(all_files),
            concerns=all_concerns,
            suggestions=all_suggestions,
            metrics=HandoffMetrics(
                tokens_used=total_tokens,
                duration_ms=max_duration,
                files_created=sum(h.metrics.files_created for h in handoffs),
                files_modified=sum(h.metrics.files_modified for h in handoffs),
            ),
        )
