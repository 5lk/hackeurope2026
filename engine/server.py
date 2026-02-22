"""FastAPI WebSocket server — bridges the frontend to the engine."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .events import EventBus, EventType

logger = logging.getLogger("agentswarm.server")

app = FastAPI(title="AgentSwarm Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/engine")
async def engine_websocket(ws: WebSocket):
    await ws.accept()
    try:
        # Wait for start message with conversation.
        data = await ws.receive_json()
        if data.get("type") != "start":
            await ws.send_json({"type": "error", "message": "Expected {type: 'start', conversation: [...]}"})
            return

        conversation = data.get("conversation", [])

        event_bus = EventBus()
        queue = event_bus.subscribe()

        from .main import run_from_conversation

        engine_task = asyncio.create_task(run_from_conversation(conversation, event_bus))

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    await ws.send_json(event.to_dict())
                    if event.type == EventType.ENGINE_DONE:
                        break
                except asyncio.TimeoutError:
                    if engine_task.done():
                        exc = engine_task.exception()
                        if exc:
                            await ws.send_json({"type": "error", "message": str(exc)})
                        break
                    # Send heartbeat so the connection stays alive.
                    await ws.send_json({"type": "heartbeat"})
        except WebSocketDisconnect:
            engine_task.cancel()
            try:
                await engine_task
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            event_bus.unsubscribe(queue)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


def start_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    start_server()
