"""Background schedule executor with retry and profile locking."""
from __future__ import annotations
import threading, time
from datetime import datetime
from typing import Callable
from src.browser.automation import BrowserAutomation
from src.config.manager import ConfigManager
from src.notifications import notify
from src.scheduling.manager import ScheduleManager
from src.scheduling.models import ClassSchedule
from src.scheduling.profile_lock import ProfileLock
from src.sites.vadana_sum39 import CourseSelectionError, sanitize_diagnostic
from src.security.credentials import CredentialStore

NON_RETRYABLE = (ValueError, CourseSelectionError)

def should_retry(exc: Exception) -> bool:
    """Return False for credential/user-action/permanent course-selection failures."""
    text = str(exc)
    if isinstance(exc, NON_RETRYABLE): return False
    return not any(key in text for key in ["رمز", "Credential", "CAPTCHA", "دو مرحله", "چند درس", "پیدا نشد"])

class ScheduleExecutor:
    """Execute one stored schedule without interactive prompts."""
    def __init__(self, config_manager: ConfigManager | None = None, credentials: CredentialStore | None = None, log: Callable[[str], None] | None = None) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.credentials = credentials or CredentialStore()
        self.log = log or (lambda message: print(message))
    def run(self, schedule_id: str, stop_event: threading.Event | None = None) -> bool:
        stop_event = stop_event or threading.Event()
        manager = ScheduleManager(self.config_manager)
        schedule = manager.get(schedule_id)
        if schedule is None:
            self.log("زمان‌بندی پیدا نشد."); return False
        self.log("اجرای زمان‌بندی آغاز شد")
        try:
            with ProfileLock(schedule.profile_id):
                self.log("زمان محلی اجرا تأیید شد")
                return self._run_with_retry(schedule, stop_event, manager)
        except Exception as exc:
            self._finish(schedule, manager, "Failed", sanitize_diagnostic(str(exc)))
            notify("Windows Class Bot", schedule.last_error)
            return False
    def _run_with_retry(self, schedule: ClassSchedule, stop_event: threading.Event, manager: ScheduleManager) -> bool:
        attempts = max(1, schedule.retry_count + 1)
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1: self.log(f"تلاش مجدد {attempt} از {attempts}")
                ok = self._run_once(schedule, stop_event)
                self._finish(schedule, manager, "Success" if ok else "Failed", "")
                notify("Windows Class Bot", f"ورود به کلاس «{schedule.class_name}» با موفقیت انجام شد." if ok else "ورود به کلاس ناموفق بود.")
                return ok
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts or not should_retry(exc): break
                stop_event.wait(max(0, schedule.retry_delay_seconds))
        self._finish(schedule, manager, "Failed", sanitize_diagnostic(str(last_exc or "خطای نامشخص")))
        return False
    def _run_once(self, schedule: ClassSchedule, stop_event: threading.Event) -> bool:
        config = self.config_manager.load()
        if config.profile_id != schedule.profile_id:
            raise ValueError("Profile زمان‌بندی با config فعلی تطبیق ندارد.")
        password = self.credentials.get_password(config.profile_id, config.username)
        if not password:
            raise ValueError("رمز ذخیره‌شده در Windows Credential Manager پیدا نشد.")
        self.log("اطلاعات حساب از Credential Manager دریافت شد")
        self.log("کلاس زمان‌بندی‌شده دریافت شد")
        config.class_name = schedule.class_name
        config.browser.keep_open = schedule.keep_browser_open
        config.browser.save_session = schedule.save_session
        automation = BrowserAutomation(self.log, stop_event)
        return automation.login_and_enter_class(config, password, schedule.class_entry_timeout_seconds * 1000, schedule.launch_adobe_connect, schedule.adobe_launch_wait_seconds)
    def _finish(self, schedule: ClassSchedule, manager: ScheduleManager, status: str, error: str) -> None:
        schedule.last_run_at = datetime.now().isoformat(timespec="seconds")
        schedule.last_run_status = "Completed" if status == "Success" and schedule.recurrence == "once" else status
        if status == "Success" and schedule.recurrence == "once":
            schedule.enabled = False
        schedule.last_error = error
        manager.upsert(schedule)
