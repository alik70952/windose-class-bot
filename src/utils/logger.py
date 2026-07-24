"""Thread-safe UI logging helpers."""

from __future__ import annotations

from datetime import datetime
from queue import Queue


class UiLogQueue:
    """Collect log messages from worker threads for display in the UI thread."""

    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()

    def log(self, message: str) -> None:
        """Add a timestamped message to the queue."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._queue.put(f"[{timestamp}] {message}")

    def drain(self) -> list[str]:
        """Return all currently queued messages."""
        messages: list[str] = []
        while not self._queue.empty():
            messages.append(self._queue.get_nowait())
        return messages
