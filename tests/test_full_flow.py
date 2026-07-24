from __future__ import annotations

import threading
from unittest.mock import Mock

import pytest

from src.browser.automation import BrowserAutomation
from src.config.manager import ConfigManager, VADANA_SITE_ADAPTER, default_vadana_profile
from src.sites.base import LoginResult


class Visible:
    first = None
    def __init__(self, visible=True):
        self.first = self
        self.visible = visible
    def wait_for(self, *a, **k):
        if not self.visible:
            raise TimeoutError()


class LoginField(Visible):
    pass


class Page:
    def __init__(self, dashboard=False, login=True):
        self.dashboard = dashboard
        self.login = login
        self.url = "https://vadana-sum39.ec.iau.ir/4043/login/index.php" if login else "https://vadana-sum39.ec.iau.ir/my/"
        self.gotos = []
    def goto(self, url, **kwargs):
        self.gotos.append(url)
    def get_by_text(self, text, exact=False):
        return Visible(self.dashboard and text == "درس‌های من")
    def locator(self, selector):
        return LoginField(self.login)


def cfg(class_name="انس با قرآن کریم"):
    c = default_vadana_profile()
    c.username = "user"
    c.class_name = class_name
    c.browser.keep_open = False
    c.browser.save_session = False
    return c


def test_start_bot_callback_not_bound_to_open_site():
    source = __import__("pathlib").Path("src/ui/main_window.py").read_text(encoding="utf-8")
    body = source.split("    def start_bot", 1)[1].split("    def delete_saved_password", 1)[0]
    assert "_run_full_class_flow" in body
    assert "_run_browser" not in body
    assert "open_site" not in body


def test_missing_class_before_browser_error():
    logs = []
    flow = BrowserAutomation(logs.append, threading.Event())
    with pytest.raises(ValueError, match="ابتدا یک کلاس"):
        flow.login_and_enter_class(cfg(class_name=""), "pass")
    assert "Chrome در حال اجرا است" not in logs


def test_vadana_domain_migrates_adapter(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"login_url":"https://vadana-sum39.ec.iau.ir/4043/login/index.php"}', encoding="utf-8")
    assert ConfigManager(path).load().site_adapter == VADANA_SITE_ADAPTER


def test_valid_session_skips_login_and_opens_course_then_enters():
    logs = []
    flow = BrowserAutomation(logs.append, threading.Event())
    page = Page(dashboard=True, login=False)
    adapter = Mock()
    assert flow._ensure_login_state(page, adapter, cfg(), "pass") is True
    adapter.login.assert_not_called()
    assert "نشست ورود معتبر است" in logs


def test_invalid_session_runs_login_then_course_methods(monkeypatch):
    logs = []
    flow = BrowserAutomation(logs.append, threading.Event())
    page = Page(dashboard=False, login=True)
    adapter = Mock()
    adapter.login.return_value = LoginResult(True, "ok")
    assert flow._ensure_login_state(page, adapter, cfg(), "pass") is True
    adapter.login.assert_called_once()
    assert "صفحه ورود شناسایی شد" in logs


def test_full_flow_calls_open_course_and_enter_not_goto_success(monkeypatch):
    calls = []
    class Context:
        pages = []
        def new_page(self): return Page(dashboard=True, login=False)
        def close(self): calls.append("close")
    class Chromium:
        def launch(self, **kwargs): return Mock(new_context=lambda: Context(), close=lambda: None)
    class PW:
        chromium = Chromium()
        def __enter__(self): return self
        def __exit__(self, *a): pass
    adapter = Mock()
    adapter.open_course.side_effect = lambda *a: calls.append("open_course")
    adapter.enter_online_class.side_effect = lambda page, *a: calls.append("enter_online_class") or page
    monkeypatch.setattr("src.browser.automation.sync_playwright", lambda: PW())
    monkeypatch.setattr("src.browser.automation.get_adapter", lambda name: adapter)
    assert BrowserAutomation(lambda m: None, threading.Event()).login_and_enter_class(cfg(), "pass") is True
    assert calls[:2] == ["open_course", "enter_online_class"]


def test_stop_event_blocks_flow_before_browser():
    event = threading.Event(); event.set()
    flow = BrowserAutomation(lambda m: None, event)
    with pytest.raises(RuntimeError, match="متوقف"):
        flow._check_stop()


def test_password_not_in_logs_on_validation_error():
    secret = "super-secret-password"
    logs = []
    with pytest.raises(ValueError):
        BrowserAutomation(logs.append).login_and_enter_class(cfg(class_name=""), secret)
    assert secret not in "\n".join(logs)
