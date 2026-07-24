"""Windowless, persistent dispatcher for every stored class schedule."""
from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.manager import ConfigManager  # noqa: E402
from src.scheduling.manager import ScheduleManager  # noqa: E402
from src.scheduling.models import ClassSchedule  # noqa: E402
from src.scheduling.profile_lock import ProfileLock  # noqa: E402
from src.scheduling.time_utils import PERSIAN_WEEKDAYS, parse_time  # noqa: E402

ERROR_LOG = PROJECT_ROOT / "logs" / "schedule-worker.log"
POLL_SECONDS = 15


def scheduled_occurrence(schedule: ClassSchedule, now: datetime) -> datetime | None:
    """Return the latest occurrence at or before ``now`` in local wall time."""
    if not schedule.enabled or schedule.completed or schedule.recurrence == "disabled":
        return None
    run_time = parse_time(schedule.effective_run_time or schedule.start_time)
    if schedule.recurrence == "once":
        from datetime import date
        return datetime.combine(date.fromisoformat(schedule.effective_run_date or schedule.date), run_time)
    weekday = schedule.effective_run_weekday or schedule.weekday
    target = PERSIAN_WEEKDAYS.index(weekday)
    current = (now.weekday() + 2) % 7
    days_ago = (current - target) % 7
    occurrence = datetime.combine(now.date() - timedelta(days=days_ago), run_time)
    return occurrence if occurrence <= now else occurrence - timedelta(days=7)


def is_due(schedule: ClassSchedule, now: datetime) -> bool:
    occurrence = scheduled_occurrence(schedule, now)
    if occurrence is None or now - occurrence > timedelta(minutes=max(0, schedule.max_late_start_minutes)):
        return False
    if schedule.last_run_at:
        try:
            if datetime.fromisoformat(schedule.last_run_at) >= occurrence:
                return False
        except ValueError:
            pass
    return True


class ScheduleWorker:
    """Poll persisted schedules and dispatch each due occurrence exactly once."""
    def __init__(self, config_manager: ConfigManager | None = None,
                 executor_factory: Callable[[], object] | None = None,
                 poll_seconds: float = POLL_SECONDS) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.executor_factory = executor_factory or self._executor
        self.poll_seconds = poll_seconds
        self._running: set[str] = set()
        self._guard = threading.Lock()

    @staticmethod
    def _executor():
        from src.scheduling.executor import ScheduleExecutor
        return ScheduleExecutor()

    def tick(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        started: list[str] = []
        for schedule in ScheduleManager(self.config_manager).list():
            with self._guard:
                if schedule.id in self._running or not is_due(schedule, now):
                    continue
                self._running.add(schedule.id)
            thread = threading.Thread(target=self._run, args=(schedule.id,),
                                      name=f"schedule-{schedule.id[:8]}", daemon=True)
            thread.start()
            started.append(schedule.id)
        return started

    def _run(self, schedule_id: str) -> None:
        try:
            self.executor_factory().run(schedule_id)  # type: ignore[attr-defined]
        except BaseException as exc:  # keep one class failure from killing the worker
            record_error(exc)
        finally:
            with self._guard:
                self._running.discard(schedule_id)

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:  # malformed/transient config is retried next poll
                record_error(exc)
            stop_event.wait(self.poll_seconds)


def record_error(exc: BaseException) -> None:
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{datetime.now().isoformat(timespec='seconds')} worker error\n")
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=stream)


def main() -> int:
    # A second manually-started process exits; Task Scheduler's IgnoreNew is an
    # additional guard, not the only singleton mechanism.
    lock = ProfileLock("schedule-worker")
    if not lock.acquire():
        return 0
    try:
        ScheduleWorker().run_forever()
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        record_error(exc)
        raise SystemExit(1) from exc
