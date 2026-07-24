"""Load, migrate, and save non-sensitive application settings."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from src.scheduling.models import ClassSchedule

CONFIG_PATH = Path("config.json")
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
        return self._from_dict(data)

    def save(self, config: AppConfig) -> None:
        """Write non-sensitive settings to disk in a readable JSON format."""
        data = asdict(config)
        data.pop("password", None)
        for schedule in data.get("schedules", []):
            if isinstance(schedule, dict):
                schedule.pop("password", None)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
        )
