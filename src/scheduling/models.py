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
    name: str = ""
    profile_id: str = "vadana-sum39"
    class_name: str = ""
    weekday: str = "یکشنبه"
    start_time: str = "09:15"
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
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    last_run_at: str = ""
    last_run_status: str = "Pending"
    last_error: str = ""
    windows_task_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize without credentials."""
        data = asdict(self)
        data.pop("password", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassSchedule":
        """Load schedule with defaults for forward/backward compatibility."""
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in allowed and k != "password"}
        return cls(**clean)
