"""Playwright browser automation routines."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:  # pragma: no cover - lets unit tests run without browser deps.
    class PlaywrightError(Exception):
        pass
    def sync_playwright():
        raise PlaywrightError("Playwright نصب نیست.")

from src.config.manager import AppConfig, BrowserSettings
from src.config.manager import VADANA_LOGIN_URL, VADANA_SITE_ADAPTER
from src.sites import get_adapter
from src.sites.vadana_sum39 import sanitize_diagnostic

LogCallback = Callable[[str], None]


class BrowserAutomation:
    """Open Google Chrome with Playwright for class automation tasks."""

    def __init__(self, log: LogCallback, stop_event: threading.Event | None = None) -> None:
        self.log = log
        self.stop_event = stop_event or threading.Event()


    def login_to_site(self, config: AppConfig, password: str, timeout_ms: int = 60_000) -> bool:
        """Run a site-adapter login in real Chrome without exposing credentials."""
        self.log("در حال آماده‌سازی Google Chrome...")
        try:
            adapter = get_adapter(config.site_adapter)
            with sync_playwright() as playwright:
                if config.browser.save_session:
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(Path(config.browser.session_dir)),
                        channel="chrome",
                        headless=config.browser.headless,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                    browser = None
                else:
                    browser = playwright.chromium.launch(channel="chrome", headless=config.browser.headless)
                    context = browser.new_context()
                    page = context.new_page()

                self.log("نام کاربری دریافت شد")
                self.log("رمز عبور از Windows Credential Manager دریافت شد" if password else "رمز عبور از رابط کاربری دریافت شد")
                result = adapter.login(page, config.username, password, timeout_ms, self.stop_event)

                if config.browser.keep_open and not config.browser.headless and result.success and not self.stop_event.is_set():
                    self.log("مرورگر باز می‌ماند. برای توقف از دکمه توقف ربات استفاده کنید.")
                    while not self.stop_event.wait(0.5):
                        if page.is_closed():
                            break

                context.close()
                if browser is not None:
                    browser.close()
                if result.success:
                    self.log("مرورگر بسته شد." if not config.browser.keep_open else "عملیات ورود پایان یافت.")
                else:
                    self.log(result.message)
                return result.success
        except PlaywrightError as exc:
            self.log(f"خطای مرورگر: {exc}")
        except Exception as exc:  # noqa: BLE001 - keep the desktop app alive on unexpected errors.
            self.log(f"خطای پیش‌بینی‌نشده: {exc}")
        return False


    def login_and_enter_class(self, config: AppConfig, password: str, timeout_ms: int = 900_000, launch_adobe_connect: bool = True) -> bool:
        """Run the full Vadana class flow; opening a URL alone is never success."""
        self.log("اجرای کامل ربات آغاز شد")
        self._validate_full_flow_inputs(config, password)
        self.log("Profile فعال بارگذاری شد")
        self.log("کلاس انتخاب‌شده دریافت شد")
        context = None
        browser = None
        active_page = None
        try:
            adapter = get_adapter(config.site_adapter)
            adapter.log = self.log
            with sync_playwright() as playwright:
                self.log("Chrome در حال اجرا است")
                if config.browser.save_session:
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(Path(config.browser.session_dir)),
                        channel="chrome",
                        headless=config.browser.headless,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = playwright.chromium.launch(channel="chrome", headless=config.browser.headless)
                    context = browser.new_context()
                    page = context.new_page()

                self._check_stop()
                self.log("در حال بررسی نشست ورود")
                logged_in = self._ensure_login_state(page, adapter, config, password)
                if not logged_in:
                    raise RuntimeError("ورود به وادانا انجام نشد.")

                self._check_stop()
                adapter.open_course(page, config.class_name, 60_000, self.stop_event)
                self._check_stop()
                self.log("در حال بررسی لینک ورود به کلاس")
                active_page = adapter.enter_online_class(page, config.class_name, timeout_ms, self.stop_event)
                self.log("درخواست ورود به کلاس ارسال شد")

                if launch_adobe_connect and config.adobe_connect_url:
                    self.log("در صورت نیاز Adobe Connect توسط لینک کلاس یا آدرس تنظیم‌شده باز می‌شود")
                    active_page.goto(config.adobe_connect_url, wait_until="domcontentloaded", timeout=60_000)

                if config.browser.keep_open and not config.browser.headless and not self.stop_event.is_set():
                    self.log("مرورگر باز می‌ماند. برای توقف از دکمه توقف ربات استفاده کنید.")
                    while not self.stop_event.wait(0.5):
                        if active_page.is_closed():
                            break

                self.log("جریان کامل ربات با موفقیت انجام شد")
                return True
        except Exception as exc:
            message = sanitize_diagnostic(str(exc))
            self.log(f"خطای ورود به کلاس: {message}")
            raise
        finally:
            if context is not None and not (config.browser.keep_open and not config.browser.headless and not self.stop_event.is_set()):
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None and not (config.browser.keep_open and not config.browser.headless and not self.stop_event.is_set()):
                try:
                    browser.close()
                except Exception:
                    pass

    def _validate_full_flow_inputs(self, config: AppConfig, password: str) -> None:
        if not config.profile_id:
            raise ValueError("Profile انتخاب نشده است.")
        if not config.login_url.startswith(("http://", "https://")):
            raise ValueError("URL ورود خالی یا نامعتبر است.")
        if not config.username.strip():
            raise ValueError("نام کاربری خالی است.")
        if not password:
            raise ValueError("رمز عبور وارد یا در Windows Credential Manager ذخیره نشده است.")
        if not config.class_name.strip():
            raise ValueError("ابتدا یک کلاس یا زمان‌بندی را انتخاب کنید.")
        if config.site_adapter != VADANA_SITE_ADAPTER:
            raise ValueError("Site Adapter پشتیبانی نمی‌شود.")

    def _ensure_login_state(self, page, adapter, config: AppConfig, password: str) -> bool:
        page.goto(config.login_url, wait_until="domcontentloaded", timeout=60_000)
        if self._dashboard_visible(page):
            self.log("نشست ورود معتبر است")
            self.log("صفحه میزکار شناسایی شد")
            return True
        if self._login_visible(page) or "/login/index.php" in getattr(page, "url", ""):
            self.log("صفحه ورود شناسایی شد")
            self.log("اطلاعات ورود امن دریافت شد")
            result = adapter.login(page, config.username, password, 60_000, self.stop_event)
            if not result.success:
                raise RuntimeError(result.message)
            self.log("ورود موفق بود")
            return True
        self.log("وضعیت نشست نامشخص است؛ صفحه ورود دوباره بررسی می‌شود")
        page.goto(VADANA_LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        if self._dashboard_visible(page):
            self.log("نشست ورود معتبر است")
            self.log("صفحه میزکار شناسایی شد")
            return True
        self.log("صفحه ورود شناسایی شد")
        self.log("اطلاعات ورود امن دریافت شد")
        result = adapter.login(page, config.username, password, 60_000, self.stop_event)
        if not result.success:
            raise RuntimeError(result.message)
        self.log("ورود موفق بود")
        return True

    def _dashboard_visible(self, page) -> bool:
        try:
            page.get_by_text("درس‌های من", exact=True).wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            return False

    def _login_visible(self, page) -> bool:
        try:
            page.locator("input#username, input[name='username']").first.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            return False

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise RuntimeError("عملیات توسط کاربر متوقف شد.")

    def open_site(self, url: str, settings: BrowserSettings) -> bool:
        """Open a URL in real Google Chrome and report success without crashing the app."""
        self.log("در حال آماده‌سازی Google Chrome...")
        try:
            with sync_playwright() as playwright:
                if settings.save_session:
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(Path(settings.session_dir)),
                        channel="chrome",
                        headless=settings.headless,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                    browser = None
                else:
                    browser = playwright.chromium.launch(channel="chrome", headless=settings.headless)
                    context = browser.new_context()
                    page = context.new_page()

                self.log(f"در حال باز کردن سایت: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                self.log("سایت با موفقیت باز شد.")

                if self.stop_event.is_set():
                    self.log("عملیات توسط کاربر متوقف شد.")

                if settings.keep_open and not settings.headless and not self.stop_event.is_set():
                    self.log("مرورگر باز می‌ماند. برای توقف از دکمه توقف ربات استفاده کنید.")
                    while not self.stop_event.wait(0.5):
                        if page.is_closed():
                            break

                context.close()
                if browser is not None:
                    browser.close()
                self.log("مرورگر بسته شد.")
                return True
        except PlaywrightError as exc:
            self.log(f"خطای مرورگر: {exc}")
        except Exception as exc:  # noqa: BLE001 - keep the desktop app alive on unexpected errors.
            self.log(f"خطای پیش‌بینی‌نشده: {exc}")
        return False
