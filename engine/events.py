"""Event bus for streaming engine progress to the frontend via WebSocket."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    ENGINE_STARTED = "engine_started"
    SPEC_CREATED = "spec_created"
    PLANNING_ITERATION = "planning_iteration"
    TASK_DISPATCHED = "task_dispatched"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    SUBPLANNER_STARTED = "subplanner_started"
    SUBTASK_DISPATCHED = "subtask_dispatched"
    RECONCILER_ISSUE = "reconciler_issue"
    BUILD_COMPLETE = "build_complete"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_RESULT = "validation_result"
    ENGINE_DONE = "engine_done"


@dataclass
class EngineEvent:
    type: EventType
    task_id: Optional[str] = None
    parent_id: Optional[str] = None
    team: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "task_id": self.task_id,
            "parent_id": self.parent_id,
            "team": self.team,
            "description": self.description,
            "status": self.status,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class EventBus:
    """Simple async event bus for broadcasting engine events to WebSocket subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def emit(self, event: EngineEvent) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop events if subscriber is slow.

    def subscribe(self) -> asyncio.Queue[EngineEvent]:
        q: asyncio.Queue[EngineEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass
