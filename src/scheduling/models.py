"""Schedule data model and status labels."""
from __future__ import annotations
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Recurrence = Literal["once", "weekly", "disabled"]

RUN_STATUS_LABELS: dict[str, str] = {
    "Pending": "در انتظار", "Launching": "در حال اجرا", "LoggingIn": "در حال ورود",
    "OpeningDashboard": "بازکردن میزکار", "FindingCourse": "جست‌وجوی درس",
    "OpeningCourse": "بازکردن درس", "WaitingForClass": "انتظار کلاس",
    "EnteringClass": "ورود به کلاس", "LaunchingAdobeConnect": "اجرای Adobe Connect",
    "Success": "موفق", "Failed": "ناموفق", "Stopped": "متوقف‌شده", "NeedsUserAction": "نیازمند اقدام کاربر",
}

@dataclass(slots=True)
class ClassSchedule:
    """Credential-free class schedule persisted in local config."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    date: str = ""
    name: str = ""
    profile_id: str = "vadana-sum39"
    class_name: str = ""
    weekday: str = "یکشنبه"
    start_time: str = "09:15"
    class_start_time: str = ""
    effective_run_time: str = ""
    effective_run_weekday: str = ""
    effective_run_date: str = ""
    end_time: str = "12:15"
    early_minutes: int = 5
    recurrence: Recurrence = "weekly"
    enabled: bool = True
    keep_browser_open: bool = True
    save_session: bool = True
    launch_adobe_connect: bool = True
    retry_count: int = 2
    retry_delay_seconds: int = 30
    class_entry_timeout_seconds: int = 900
    adobe_launch_wait_seconds: int = 20
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    last_run_at: str = ""
    last_run_status: str = "Pending"
    last_error: str = ""
    next_run: str = ""
    completed: bool = False
    max_late_start_minutes: int = 15
    test_schedule: bool = False
    windows_task_name: str = ""

    @property
    def schedule_id(self) -> str:
        return self.id

    @property
    def schedule_type(self) -> str:
        return self.recurrence

    @schedule_type.setter
    def schedule_type(self, value: str) -> None:
        self.recurrence = value  # type: ignore[assignment]

    @property
    def wait_timeout_minutes(self) -> int:
        return max(1, self.class_entry_timeout_seconds // 60)

    @wait_timeout_minutes.setter
    def wait_timeout_minutes(self, value: int) -> None:
        self.class_entry_timeout_seconds = int(value) * 60

    @property
    def last_run(self) -> str:
        return self.last_run_at

    @property
    def last_status(self) -> str:
        return self.last_run_status

    def to_dict(self) -> dict[str, Any]:
        """Serialize without credentials."""
        data = asdict(self)
        data.pop("password", None)
        for sensitive in ("password", "token", "cookie", "username"):
            data.pop(sensitive, None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassSchedule":
        """Load schedule with defaults for forward/backward compatibility."""
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in allowed and k != "password"}
        obj = cls(**clean)
        if not obj.class_start_time: obj.class_start_time = obj.start_time
        if not obj.effective_run_time:
            from src.scheduling.time_utils import actual_run_time, effective_for_date, effective_for_weekday
            obj.effective_run_time, _ = actual_run_time(obj.class_start_time, obj.early_minutes)
            if obj.recurrence == "weekly": obj.effective_run_time, obj.effective_run_weekday = effective_for_weekday(obj.weekday, obj.class_start_time, obj.early_minutes)
            elif obj.date: obj.effective_run_time, obj.effective_run_date = effective_for_date(obj.date, obj.class_start_time, obj.early_minutes)
        return obj
