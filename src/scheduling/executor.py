"""Credential-safe full-flow execution for a claimed SQLite schedule."""
from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Callable

from src.browser.automation import BrowserAutomation
from src.config.manager import ConfigManager, PROJECT_ROOT
from src.scheduling.schedule_store import ScheduleRecord, ScheduleStore
from src.security.credentials import CredentialStore
from src.sites.vadana_sum39 import CourseSelectionError, sanitize_diagnostic

NON_RETRYABLE = (ValueError, CourseSelectionError)


def should_retry(exc: Exception) -> bool:
    text = str(exc)
    if isinstance(exc, NON_RETRYABLE):
        return False
    return not any(word in text for word in ("رمز", "Credential", "CAPTCHA", "دو مرحله", "چند درس", "پیدا نشد"))


class ScheduleExecutor:
    """Run Credential Manager → login → exact course → class link → Adobe."""
    def __init__(self, config_manager: ConfigManager | None = None,
                 credentials: CredentialStore | None = None,
                 log: Callable[[str], None] | None = None,
                 store: ScheduleStore | None = None) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.credentials = credentials or CredentialStore()
        self.log = log or (lambda message: print(sanitize_diagnostic(message)))
        self.store = store or ScheduleStore()

    def run_schedule(self, schedule: ScheduleRecord,
                     stop_event: threading.Event | None = None) -> bool:
        config = copy.deepcopy(self.config_manager.load())
        if config.profile_id != schedule.profile_id:
            raise ValueError("Profile زمان‌بندی با Profile ذخیره‌شده تطبیق ندارد.")
        password = self.credentials.get_password(config.profile_id, config.username)
        if not password:
            raise ValueError("رمز ذخیره‌شده در Windows Credential Manager پیدا نشد.")
        config.class_name = schedule.class_name
        config.browser.headless = False
        config.browser.save_session = True
        # Keep ownership of the meeting until it ends; the farewell monitor then
        # releases Chrome/Adobe before the worker accepts another class.
        config.browser.keep_open = True
        config.browser.session_dir = str(PROJECT_ROOT / "browser-session" / "scheduled" / config.profile_id)
        automation = BrowserAutomation(self.log, stop_event or threading.Event())
        # This is deliberately the only worker browser entry point.
        return automation.login_and_enter_class(config, password, 900_000, True, 20)

    def run(self, schedule_id: str, stop_event: threading.Event | None = None) -> bool:
        schedule = self.store.get(schedule_id)
        if schedule is None:
            return False
        return self.run_schedule(schedule, stop_event)
