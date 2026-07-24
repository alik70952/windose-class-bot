"""Playwright browser automation routines."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src.config.manager import AppConfig, BrowserSettings
from src.sites import get_adapter

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
        """Login if needed, open the selected course, and click the live class link."""
        self.log("در حال آماده‌سازی Google Chrome...")
        try:
            adapter = get_adapter(config.site_adapter)
            with sync_playwright() as playwright:
                if config.browser.save_session:
                    context = playwright.chromium.launch_persistent_context(user_data_dir=str(Path(config.browser.session_dir)), channel="chrome", headless=config.browser.headless)
                    page = context.new_page() if not context.pages else context.pages[0]
                    browser = None
                else:
                    browser = playwright.chromium.launch(channel="chrome", headless=config.browser.headless)
                    context = browser.new_context(); page = context.new_page()
                self.log("OpeningDashboard")
                page.goto(config.login_url, wait_until="domcontentloaded", timeout=60_000)
                if "/login/index.php" in page.url:
                    self.log("LoggingIn")
                    result = adapter.login(page, config.username, password, 60_000, self.stop_event)
                    if not result.success: raise RuntimeError(result.message)
                self.log("FindingCourse")
                adapter.open_course(page, config.class_name, 60_000, self.stop_event)
                self.log("EnteringClass")
                active_page = adapter.enter_online_class(page, config.class_name, timeout_ms, self.stop_event)
                if launch_adobe_connect:
                    self.log("LaunchingAdobeConnect")
                if config.browser.keep_open and not config.browser.headless and not self.stop_event.is_set():
                    self.log("مرورگر باز می‌ماند.")
                    while not self.stop_event.wait(0.5):
                        if active_page.is_closed(): break
                context.close()
                if browser is not None: browser.close()
                return True
        except Exception as exc:
            self.log(f"خطای ورود به کلاس: {exc}")
            raise

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
