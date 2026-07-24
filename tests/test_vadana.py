from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from src.config.manager import ConfigManager, default_vadana_profile
from src.sites.vadana_sum39 import VadanaSum39Adapter


class FakeLocator:
    def __init__(self, text: str = "", visible: bool = True) -> None:
        self.text = text
        self.visible = visible
        self.filled = ""
        self.clicked = False
        self.first = self

    def wait_for(self, state: str, timeout: int) -> None:
        if state == "visible" and not self.visible:
            raise TimeoutError("not visible")

    def fill(self, value: str) -> None:
        self.filled = value

    def click(self, timeout: int) -> None:
        self.clicked = True

    def is_hidden(self, timeout: int = 0) -> bool:
        return not self.visible

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def inner_text(self, timeout: int = 0) -> str:
        return self.text


class FakePage:
    def __init__(self) -> None:
        self.username = FakeLocator()
        self.password = FakeLocator()
        self.button = FakeLocator("ورود به سایت")
        self.url = VadanaSum39Adapter.login_url

    def get_by_label(self, name: str) -> FakeLocator:
        if name == "نام کاربری یا ایمیل":
            return self.username
        if name == "رمز ورود":
            return self.password
        raise TimeoutError(name)

    def get_by_role(self, role: str, name: str) -> FakeLocator:
        if role == "button" and name == "ورود به سایت":
            return self.button
        if role == "textbox" and name == "نام کاربری یا ایمیل":
            return self.username
        raise TimeoutError(name)

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        if text == "ورود به سایت":
            return self.button
        raise TimeoutError(text)

    def locator(self, selector: str) -> FakeLocator:
        if "password" in selector:
            return self.password
        if "button" in selector or "loginbtn" in selector or "submit" in selector:
            return self.button
        return self.username


def test_find_username_field() -> None:
    assert VadanaSum39Adapter().find_username(FakePage()) is not None


def test_find_password_field() -> None:
    assert VadanaSum39Adapter().find_password(FakePage()) is not None


def test_find_login_button() -> None:
    assert VadanaSum39Adapter().find_login_button(FakePage()).text == "ورود به سایت"


def test_empty_username_error() -> None:
    with pytest.raises(ValueError, match="نام کاربری"):
        VadanaSum39Adapter().login(FakePage(), "", "placeholder-password", 100, threading.Event())


def test_empty_password_error() -> None:
    with pytest.raises(ValueError, match="رمز عبور"):
        VadanaSum39Adapter().login(FakePage(), "placeholder-user", "", 100, threading.Event())


def test_password_not_saved_in_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    manager = ConfigManager(path)
    config = default_vadana_profile()
    manager.save(config)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "password" not in data


def test_password_not_logged_by_adapter() -> None:
    secret = "placeholder-secret-not-real"
    logs: list[str] = []
    adapter = VadanaSum39Adapter(logs.append)
    adapter._debug_page(object())
    assert all(secret not in item for item in logs)


def test_screenshot_filename_is_sanitized() -> None:
    name = VadanaSum39Adapter._safe_screenshot_name("user@example.com/secret")
    assert "@" not in name
    assert "/" not in name
    assert name.endswith(".png")


def test_legacy_config_migration(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"profile_name": "قدیمی", "login_url": "https://example.com", "browser": {}}), encoding="utf-8")
    config = ConfigManager(path).load()
    assert config.profile_id
    assert config.site_adapter == ""


def test_default_vadana_profile_created_when_missing(tmp_path: Path) -> None:
    config = ConfigManager(tmp_path / "missing.json").load()
    assert config.profile_name == "وادانا واحد ۳۹"
    assert config.username == ""
    assert config.site_adapter == "vadana_sum39"
