"""Real Windows end-to-end smoke test for the persistent scheduler service.

Run from an interactive user desktop after saving a real Vadana profile and
Credential Manager password.  No credential is read or printed by this script.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.manager import ConfigManager
from src.scheduling.schedule_store import ScheduleStore
from src.scheduling.worker_runtime import worker_is_healthy
from src.scheduling.worker_task import WorkerTaskScheduler, ensure_scheduler_worker_running


def wait_for_status(store: ScheduleStore, schedule_id: str, timeout: float = 240) -> str:
    deadline = time.monotonic() + timeout
    observed = set()
    while time.monotonic() < deadline:
        item = store.get(schedule_id)
        if item:
            observed.add(item.status)
            if item.status in {"succeeded", "failed", "cancelled"}:
                print(f"  {schedule_id[:8]} statuses={sorted(observed)} final={item.status}")
                return item.status
        time.sleep(1)
    raise TimeoutError(f"schedule {schedule_id} did not finish; observed={observed}")


def main() -> int:
    if sys.platform != "win32":
        print("FAIL: this is a real Windows-only smoke test (current platform is not Windows).")
        return 2
    scheduler = WorkerTaskScheduler()
    registration = scheduler.register()
    if not registration.success:
        raise RuntimeError(f"task registration failed: {registration.message}")
    verification = scheduler.verify()
    if not verification.success:
        raise RuntimeError(f"task verification failed: {verification.message}")
    healthy = ensure_scheduler_worker_running(scheduler=scheduler)
    if not healthy.success or not worker_is_healthy():
        raise RuntimeError("worker did not produce a valid heartbeat/PID/lock")

    config = ConfigManager().load()
    if not config.profile_id or not config.username or not config.class_name:
        raise RuntimeError("save a real profile, username, and class in the GUI first")
    store = ScheduleStore()
    first = store.create(config.profile_id, config.class_name, time.time() + 60, 0, 1,
                         schedule_id=f"smoke-{uuid.uuid4().hex}")
    print("Task verified; worker healthy; first 60-second schedule queued.")
    wait_for_status(store, first.id)
    if not worker_is_healthy():
        raise RuntimeError("worker died after first schedule")

    second = store.create(config.profile_id, config.class_name, time.time() + 60, 0, 1,
                          schedule_id=f"smoke-{uuid.uuid4().hex}")
    print("Second 60-second schedule queued.")
    wait_for_status(store, second.id)
    before = time.time(); time.sleep(20)
    if not worker_is_healthy(now=before + 20):
        raise RuntimeError("worker heartbeat did not remain fresh after GUI-independent wait")
    print("PASS: task/action/working directory, two executions, and continued heartbeat verified.")
    print("Confirm the visible Chrome window on the interactive desktop during both executions.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
