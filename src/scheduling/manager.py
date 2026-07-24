"""Persistence and migration helpers for class schedules."""
from __future__ import annotations
from datetime import datetime
import threading
from src.scheduling.models import ClassSchedule

_CONFIG_LOCK = threading.RLock()


class ScheduleManager:
    """Manage schedules embedded in AppConfig-compatible JSON."""
    def __init__(self, config_manager) -> None:
        self.config_manager = config_manager
    def list(self) -> list[ClassSchedule]:
        with _CONFIG_LOCK:
            config = self.config_manager.load()
            return getattr(config, "schedules", [])
    def save_all(self, schedules: list[ClassSchedule]) -> None:
        with _CONFIG_LOCK:
            config = self.config_manager.load()
            setattr(config, "schedules", schedules)
            self.config_manager.save(config)
    def upsert(self, schedule: ClassSchedule) -> None:
        with _CONFIG_LOCK:
            schedules = [s for s in self.list() if s.id != schedule.id]
            schedule.updated_at = datetime.now().isoformat(timespec="seconds")
            schedules.append(schedule)
            self.save_all(schedules)
    def delete(self, schedule_id: str) -> None:
        self.save_all([s for s in self.list() if s.id != schedule_id])
    def get(self, schedule_id: str) -> ClassSchedule | None:
        return next((s for s in self.list() if s.id == schedule_id), None)
