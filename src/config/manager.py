"""Load, migrate, and save non-sensitive application settings."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from src.scheduling.models import ClassSchedule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# A scheduled process must not depend on the Task Scheduler service's current
# directory.  Keeping this absolute also makes the CLI and GUI read the exact
# same schedule store.
CONFIG_PATH = PROJECT_ROOT / "config.json"
VADANA_PROFILE_NAME = "وادانا واحد ۳۹"
VADANA_LOGIN_URL = "https://vadana-sum39.ec.iau.ir/4043/login/index.php"
VADANA_SITE_ADAPTER = "vadana_sum39"


@dataclass(slots=True)
class BrowserSettings:
    """Browser execution preferences stored outside the password vault."""

    headless: bool = False
    keep_open: bool = True
    save_session: bool = False
    session_dir: str = "browser-session"


@dataclass(slots=True)
class AppConfig:
    """Non-sensitive user profile settings."""

    profile_name: str = ""
    login_url: str = ""
    username: str = ""
    class_name: str = ""
    adobe_connect_url: str = ""
    site_adapter: str = ""
    profile_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    schedules: list[ClassSchedule] = field(default_factory=list)
    scheduler_sqlite_migration_completed: bool = False


def default_vadana_profile() -> AppConfig:
    """Return the local, credential-free Vadana Unit 39 profile template."""
    return AppConfig(
        profile_name=VADANA_PROFILE_NAME,
        login_url=VADANA_LOGIN_URL,
        username="",
        class_name="",
        adobe_connect_url="",
        site_adapter=VADANA_SITE_ADAPTER,
        profile_id="vadana-sum39",
        browser=BrowserSettings(headless=False, keep_open=True, save_session=True, session_dir="browser-session/vadana-sum39"),
    )


class ConfigManager:
    """Persist application configuration as JSON without storing passwords."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> AppConfig:
        """Return settings from disk, migrating old config files when needed."""
        if not self.path.exists():
            return default_vadana_profile()
        with self.path.open("r", encoding="utf-8") as file:
            data: dict[str, Any] = json.load(file)
        config = self._from_dict(data)
        if not config.scheduler_sqlite_migration_completed:
            self._migrate_schedules_once(config)
        return config

    def save(self, config: AppConfig) -> None:
        """Atomically write settings so the worker never reads partial JSON."""
        data = asdict(config)
        # The queue is SQLite-only.  Keep the legacy field out of all future JSON writes.
        data.pop("schedules", None)
        data.pop("password", None)
        for schedule in data.get("schedules", []):
            if isinstance(schedule, dict):
                schedule.pop("password", None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _from_dict(self, data: dict[str, Any]) -> AppConfig:
        """Build a config object from current or legacy JSON without secrets."""
        browser_data = data.get("browser", {}) if isinstance(data.get("browser", {}), dict) else {}
        profile_name = str(data.get("profile_name", ""))
        login_url = str(data.get("login_url", ""))
        site_adapter = str(data.get("site_adapter", ""))
        profile_id = str(data.get("profile_id", "")) or uuid.uuid4().hex
        if profile_name == VADANA_PROFILE_NAME or login_url == VADANA_LOGIN_URL or "vadana-sum39.ec.iau.ir" in login_url or site_adapter == VADANA_SITE_ADAPTER:
            site_adapter = VADANA_SITE_ADAPTER
            login_url = login_url or VADANA_LOGIN_URL
            profile_id = profile_id if profile_id != profile_name else "vadana-sum39"
        schedules_data = data.get("schedules", []) if isinstance(data.get("schedules", []), list) else []
        schedules = [ClassSchedule.from_dict(item) for item in schedules_data if isinstance(item, dict)]
        return AppConfig(
            profile_name=profile_name,
            login_url=login_url,
            username=str(data.get("username", "")),
            class_name=str(data.get("class_name", "")),
            adobe_connect_url=str(data.get("adobe_connect_url", "")),
            site_adapter=site_adapter,
            profile_id=profile_id,
            browser=BrowserSettings(
                headless=bool(browser_data.get("headless", False)),
                keep_open=bool(browser_data.get("keep_open", True)),
                save_session=bool(browser_data.get("save_session", False)),
                session_dir=str(browser_data.get("session_dir", "browser-session")),
            ),
            schedules=schedules,
            scheduler_sqlite_migration_completed=bool(data.get("scheduler_sqlite_migration_completed", False)),
        )

    def _migrate_schedules_once(self, config: AppConfig) -> None:
        """Import enabled, incomplete legacy jobs exactly once, then mark config."""
        from datetime import datetime
        from src.scheduling.schedule_store import ScheduleStore
        store = ScheduleStore(PROJECT_ROOT / "data" / "scheduler.db")
        for schedule in config.schedules:
            if not schedule.enabled or schedule.completed or schedule.last_run_status not in ("", "Pending"):
                continue
            try:
                when = datetime.fromisoformat(schedule.next_run).timestamp() if schedule.next_run else datetime.fromisoformat(
                    f"{schedule.effective_run_date or schedule.date}T{schedule.effective_run_time or schedule.start_time}:00").timestamp()
                if store.get(schedule.id) is None:
                    store.create(schedule.profile_id, schedule.class_name, when, 0, 0,
                                 schedule_id=schedule.id, max_attempts=max(1, schedule.retry_count + 1),
                                 cancel_pending_same_class=False)
            except (ValueError, OSError):
                continue
        config.schedules.clear()
        config.scheduler_sqlite_migration_completed = True
        self.save(config)
