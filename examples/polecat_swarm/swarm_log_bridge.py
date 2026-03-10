"""Best-effort bridge from local SwarmLogger records to Mayor API WebSocket."""

from __future__ import annotations

import asyncio
import json
import threading
from queue import Empty, Queue


class SwarmLogBridge:
    """Push structured log records to Mayor API websocket.

    This bridge is optional and never blocks expert execution. If websocket
    dependencies are missing or connection fails, it silently degrades.
    """

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._queue: Queue[dict | None] = Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def push_record(self, record: dict) -> None:
        self._queue.put(record)

    def _run(self) -> None:
        try:
            import websockets  # type: ignore
        except Exception:
            # Dependency is optional for local development.
            return

        asyncio.run(self._drain(websockets))

    async def _drain(self, websockets_module) -> None:
        while not self._stop.is_set():
            try:
                async with websockets_module.connect(self._ws_url) as ws:
                    await ws.send(json.dumps({"type": "register", "caller": "pod"}))

                    while not self._stop.is_set():
                        try:
                            record = self._queue.get(timeout=0.2)
                        except Empty:
                            continue
                        if record is None:
                            break

                        trace_id = str(record.get("trace_id") or "")
                        envelope = {
                            "type": "log_event",
                            "trace_id": trace_id,
                            "payload": record,
                        }
                        await ws.send(json.dumps(envelope))
            except Exception:
                # Retry loop with short delay; keep non-blocking semantics.
                await asyncio.sleep(1.0)
