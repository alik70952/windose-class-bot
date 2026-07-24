from __future__ import annotations

import threading
from datetime import datetime, timedelta

from src.config.manager import ConfigManager, default_vadana_profile
from src.schedule_worker import ScheduleWorker, is_due
from src.scheduling.models import ClassSchedule


def once(when: datetime, schedule_id: str = "one") -> ClassSchedule:
    return ClassSchedule(id=schedule_id, recurrence="once", date=when.date().isoformat(),
                         effective_run_date=when.date().isoformat(),
                         start_time=when.strftime("%H:%M"), effective_run_time=when.strftime("%H:%M"),
                         max_late_start_minutes=15)


def test_due_window_and_completed_schedule():
    now = datetime(2026, 7, 24, 12, 5)
    schedule = once(now - timedelta(minutes=5))
    assert is_due(schedule, now)
    schedule.last_run_at = now.isoformat()
    assert not is_due(schedule, now)
    schedule.last_run_at = ""
    schedule.completed = True
    assert not is_due(schedule, now)


def test_worker_dispatches_multiple_schedules_and_stays_reusable(tmp_path):
    now = datetime(2026, 7, 24, 12, 5)
    manager = ConfigManager(tmp_path / "config.json")
    config = default_vadana_profile()
    config.schedules = [once(now, "first"), once(now, "second")]
    manager.save(config)
    calls: list[str] = []
    finished = threading.Event()

    class Executor:
        def run(self, schedule_id):
            calls.append(schedule_id)
            if len(calls) == 2:
                finished.set()

    worker = ScheduleWorker(manager, executor_factory=Executor)
    assert set(worker.tick(now)) == {"first", "second"}
    assert finished.wait(1)
    assert set(calls) == {"first", "second"}
