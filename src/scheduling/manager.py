"""Compatibility facade backed exclusively by the SQLite schedule store."""
from __future__ import annotations

from datetime import datetime
from src.scheduling.models import ClassSchedule
from src.scheduling.schedule_store import ScheduleStore


class ScheduleManager:
    def __init__(self, config_manager=None, store: ScheduleStore | None = None) -> None:
        self.store = store or ScheduleStore()

    def list(self) -> list[ClassSchedule]:
        return [self._model(item) for item in self.store.list()]

    def get(self, schedule_id: str) -> ClassSchedule | None:
        item = self.store.get(schedule_id)
        return self._model(item) if item else None

    def upsert(self, schedule: ClassSchedule) -> None:
        existing = self.store.get(schedule.id)
        if existing:
            return
        when = datetime.fromisoformat(schedule.next_run).timestamp() if schedule.next_run else datetime.fromisoformat(
            f"{schedule.effective_run_date or schedule.date}T{schedule.effective_run_time or schedule.start_time}:00").timestamp()
        self.store.create(schedule.profile_id, schedule.class_name, when, 0, 0, schedule_id=schedule.id)

    def delete(self, schedule_id: str) -> None:
        self.store.cancel(schedule_id)

    @staticmethod
    def _model(item) -> ClassSchedule:
        when = datetime.fromtimestamp(item.run_at_epoch)
        return ClassSchedule(id=item.id, profile_id=item.profile_id, class_name=item.class_name,
                             recurrence="once", date=when.date().isoformat(), effective_run_date=when.date().isoformat(),
                             start_time=when.strftime("%H:%M"), effective_run_time=when.strftime("%H:%M"),
                             next_run=when.isoformat(), enabled=item.status == "pending",
                             completed=item.status in ("succeeded", "failed", "cancelled"),
                             last_run_status=item.status, last_error=item.last_error or "")
