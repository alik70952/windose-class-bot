"""Playwright adapter for Vadana Unit 39 login."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.sites.base import LoginResult, SiteAdapter

LocatorFactory = Callable[[], object]


class VadanaSum39Adapter(SiteAdapter):
    """Encapsulate Vadana SUM39 login selectors and safe diagnostics."""

    login_url = "https://vadana-sum39.ec.iau.ir/4043/login/index.php"
    title_text = "سامانه آموزش آنلاین دانشگاه آزاد اسلامی"

    def __init__(self, log: Callable[[str], None] | None = None, debug: bool = False) -> None:
        self.log = log or (lambda _message: None)
        self.debug = debug
        self.last_locator_method = ""

    def login(self, page, username: str, password: str, timeout_ms: int, stop_event: threading.Event) -> LoginResult:
        """Open Vadana, fill credentials, submit, and report a sanitized result."""
        if not username.strip():
            raise ValueError("نام کاربری خالی است.")
        if not password:
            raise ValueError("رمز عبور خالی است.")
        try:
            self._check_stop(stop_event)
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=timeout_ms)
            self.log("صفحه ورود باز شد")
            self._check_stop(stop_event)
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            self._debug_page(page)
            username_box = self.find_username(page, timeout_ms)
            self.log("فیلد نام کاربری پیدا شد")
            self._check_stop(stop_event)
            username_box.fill(username)
            password_box = self.find_password(page, timeout_ms)
            self.log("فیلد رمز عبور پیدا شد")
            self._check_stop(stop_event)
            password_box.fill(password)
            self.log("اطلاعات ورود وارد شد")
            login_button = self.find_login_button(page, timeout_ms)
            self._check_stop(stop_event)
            login_button.click(timeout=timeout_ms)
            self.log("درخواست ورود ارسال شد")
            result = self._wait_for_login_result(page, timeout_ms, stop_event)
            if result.success:
                self.log("ورود با موفقیت انجام شد")
                self.log("ورود انجام شد. برای تعریف مراحل انتخاب کلاس، صفحه بعدی را بررسی کنید.")
                return result
            path = self._save_error_screenshot(page, "login_failed")
            result.screenshot_path = path
            self.log(f"Screenshot خطا ذخیره شد: {path}")
            return result
        except Exception as exc:
            path = self._save_error_screenshot(page, "login_error")
            self.log(f"Screenshot خطا ذخیره شد: {path}")
            if isinstance(exc, PlaywrightError | PlaywrightTimeoutError | ValueError):
                return LoginResult(False, f"خطای ورود وادانا: {exc}", path)
            raise

    def find_username(self, page, timeout_ms: int = 5000):
        """Find the username field using robust locator fallbacks."""
        return self._first_visible(page, [
            ("label: نام کاربری یا ایمیل", lambda: page.get_by_label("نام کاربری یا ایمیل")),
            ("role textbox: نام کاربری یا ایمیل", lambda: page.get_by_role("textbox", name="نام کاربری یا ایمیل")),
            ("label for username", lambda: page.locator('label:has-text("نام کاربری یا ایمیل")').locator("xpath=following::input[1]")),
            ("css input#username", lambda: page.locator("input#username, input[name='username']")),
        ], timeout_ms)

    def find_password(self, page, timeout_ms: int = 5000):
        """Find the password field using robust locator fallbacks."""
        return self._first_visible(page, [
            ("label: رمز ورود", lambda: page.get_by_label("رمز ورود")),
            ("css input[type=password]", lambda: page.locator('input[type="password"]')),
            ("label for password", lambda: page.locator('label:has-text("رمز ورود")').locator("xpath=following::input[1]")),
            ("css input#password", lambda: page.locator("input#password, input[name='password']")),
        ], timeout_ms)

    def find_login_button(self, page, timeout_ms: int = 5000):
        """Find the submit button using robust locator fallbacks."""
        return self._first_visible(page, [
            ("role button: ورود به سایت", lambda: page.get_by_role("button", name="ورود به سایت")),
            ("text: ورود به سایت", lambda: page.get_by_text("ورود به سایت", exact=True)),
            ("css button[type=submit]", lambda: page.locator('button[type="submit"], input[type="submit"]')),
            ("css #loginbtn", lambda: page.locator("#loginbtn")),
        ], timeout_ms)

    def _first_visible(self, page, factories: list[tuple[str, LocatorFactory]], timeout_ms: int):
        for method, factory in factories:
            try:
                locator = factory().first
                locator.wait_for(state="visible", timeout=timeout_ms)
                self.last_locator_method = method
                if self.debug:
                    self.log(f"Locator موفق: {method}")
                return locator
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        raise RuntimeError("عنصر موردنظر در صفحه وادانا پیدا نشد.")

    def _wait_for_login_result(self, page, timeout_ms: int, stop_event: threading.Event) -> LoginResult:
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10_000))
        except PlaywrightTimeoutError:
            pass
        for _ in range(20):
            self._check_stop(stop_event)
            if "/login/index.php" not in page.url:
                return LoginResult(True, "ورود با موفقیت انجام شد")
            try:
                if self.find_login_button(page, 500).is_hidden(timeout=500):
                    return LoginResult(True, "ورود با موفقیت انجام شد")
            except Exception:  # noqa: BLE001 - absence of login button can indicate success.
                return LoginResult(True, "ورود با موفقیت انجام شد")
            error = self._login_error_text(page)
            if error:
                self.log(f"پیام خطای ورود: {error}")
                return LoginResult(False, error)
            if self._needs_manual_challenge(page):
                return LoginResult(False, "CAPTCHA یا احراز هویت دومرحله‌ای دیده شد؛ لطفاً دستی ادامه دهید.")
            stop_event.wait(0.5)
        return LoginResult(False, "نتیجه ورود در زمان مجاز مشخص نشد.")

    def _login_error_text(self, page) -> str:
        candidates = page.locator(".alert-danger, .loginerrors, #loginerrormessage, [role='alert']")
        try:
            if candidates.count() and candidates.first.is_visible(timeout=500):
                return candidates.first.inner_text(timeout=500).strip()
        except PlaywrightError:
            return ""
        return ""

    def _needs_manual_challenge(self, page) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=500)
        except PlaywrightError:
            return False
        return bool(re.search(r"captcha|کپچا|امنیتی|دو.?مرحله", text, re.IGNORECASE))

    def _debug_page(self, page) -> None:
        if not self.debug:
            return
        try:
            buttons = page.locator("button, input[type='submit']")
            texts = []
            for index in range(min(buttons.count(), 10)):
                item = buttons.nth(index)
                if item.is_visible(timeout=250):
                    texts.append(item.inner_text(timeout=250).strip())
            self.log(f"Debug: تعداد inputها={page.locator('input').count()}، password={page.locator('input[type=password]').count()}، buttonها={buttons.count()}، متن دکمه‌ها={texts}")
        except PlaywrightError as exc:
            self.log(f"Debug امن ناموفق بود: {exc}")

    def _save_error_screenshot(self, page, prefix: str) -> Path:
        path = Path("logs/screenshots") / self._safe_screenshot_name(prefix)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.locator('input[type="password"]').evaluate_all("els => els.forEach(e => e.value = '')")
            page.screenshot(path=str(path), full_page=True)
        except Exception:  # noqa: BLE001 - screenshot failure must not hide the original error.
            pass
        return path

    @staticmethod
    def _safe_screenshot_name(prefix: str) -> str:
        safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", prefix)[:40] or "vadana"
        return f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    @staticmethod
    def _check_stop(stop_event: threading.Event) -> None:
        if stop_event.is_set():
            raise RuntimeError("عملیات توسط کاربر متوقف شد.")
