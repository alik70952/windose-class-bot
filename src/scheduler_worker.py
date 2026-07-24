"""Windowless, synchronous, persistent SQLite scheduler worker."""
from __future__ import annotations

import os
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from src.scheduling.executor import ScheduleExecutor, should_retry
from src.scheduling.schedule_store import ScheduleRecord, ScheduleStore
from src.scheduling.worker_runtime import WorkerProcessLock, write_heartbeat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ERROR_LOG = PROJECT_ROOT / "logs" / "scheduler-worker.log"
POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 2.0
RETRY_DELAYS = (15, 30, 60)


def record_error(exc: BaseException) -> None:
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{time.strftime('%Y-%m-%dT%H:%M:%S')} worker error\n")
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=stream)


class SchedulerWorker:
    """Claim and execute exactly one job at a time; failures never end the loop."""
    def __init__(self, store: ScheduleStore | None = None,
                 executor_factory: Callable[[], ScheduleExecutor] = ScheduleExecutor,
                 poll_seconds: float = POLL_SECONDS, worker_id: str | None = None) -> None:
        self.store = store or ScheduleStore()
        self.executor_factory = executor_factory
        self.poll_seconds = min(1.0, max(0.01, poll_seconds))
        self.worker_id = worker_id or f"{os.getpid()}"
        self.started_at = time.time()
        self._last_heartbeat = 0.0

    def heartbeat(self, force: bool = False) -> None:
        now = time.time()
        if force or now - self._last_heartbeat >= HEARTBEAT_SECONDS:
            write_heartbeat(os.getpid(), self.started_at, now)
            self._last_heartbeat = now

    def execute(self, job: ScheduleRecord) -> bool:
        try:
            result = self.executor_factory().run_schedule(job)
            self.store.finish(job.id, bool(result), result="full_login_flow" if result else "flow returned false",
                              error="" if result else "full login flow returned false")
            return bool(result)
        except Exception as exc:  # one bad class must never kill this process
            record_error(exc)
            delay_index = max(0, min(job.attempt_count - 1, len(RETRY_DELAYS) - 1))
            if should_retry(exc) and self.store.retry(job.id, RETRY_DELAYS[delay_index], str(exc)):
                return False
            self.store.finish(job.id, False, error=str(exc))
            return False

    def tick(self, now: float | None = None) -> str | None:
        self.heartbeat()
        self.store.recover_stale(now)
        job = self.store.claim_due(self.worker_id, now)
        if job is None:
            return None
        self.execute(job)  # synchronous by design: the next queue item remains pending
        return job.id

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        self.heartbeat(force=True)
        # Browser/Adobe work may take minutes.  A tiny heartbeat pump keeps the
        # externally verifiable liveness signal fresh without executing jobs in
        # parallel; all queue claiming and browser work stays on this thread.
        heartbeat_stop = threading.Event()
        def pump() -> None:
            while not heartbeat_stop.wait(HEARTBEAT_SECONDS):
                try:
                    self.heartbeat(force=True)
                except OSError as exc:
                    record_error(exc)
        heartbeat_thread = threading.Thread(target=pump, name="scheduler-heartbeat", daemon=True)
        heartbeat_thread.start()
        try:
            while not stop_event.is_set():
                try:
                    self.tick()
                except BaseException as exc:
                    record_error(exc)
                stop_event.wait(self.poll_seconds)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=HEARTBEAT_SECONDS + .5)


# Compatibility name for callers while the old module is deliberately removed.
ScheduleWorker = SchedulerWorker


def main() -> int:
    lock = WorkerProcessLock()
    if not lock.acquire():
        return 0
    try:
        SchedulerWorker().run_forever()
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
