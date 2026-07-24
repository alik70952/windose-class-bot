"""Load and save non-sensitive application settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config.json")


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
    browser: BrowserSettings = field(default_factory=BrowserSettings)


class ConfigManager:
    """Persist application configuration as JSON without storing passwords."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> AppConfig:
        """Return settings from disk or a default configuration when missing."""
        if not self.path.exists():
            return AppConfig()
        with self.path.open("r", encoding="utf-8") as file:
            data: dict[str, Any] = json.load(file)
        browser_data = data.get("browser", {}) if isinstance(data.get("browser", {}), dict) else {}
        return AppConfig(
            profile_name=str(data.get("profile_name", "")),
            login_url=str(data.get("login_url", "")),
            username=str(data.get("username", "")),
            class_name=str(data.get("class_name", "")),
            adobe_connect_url=str(data.get("adobe_connect_url", "")),
            browser=BrowserSettings(
                headless=bool(browser_data.get("headless", False)),
                keep_open=bool(browser_data.get("keep_open", True)),
                save_session=bool(browser_data.get("save_session", False)),
                session_dir=str(browser_data.get("session_dir", "browser-session")),
            ),
        )

    def save(self, config: AppConfig) -> None:
        """Write non-sensitive settings to disk in a readable JSON format."""
        self.path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
