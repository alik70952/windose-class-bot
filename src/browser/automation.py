"""Playwright browser automation routines."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src.config.manager import BrowserSettings

LogCallback = Callable[[str], None]


class BrowserAutomation:
    """Open Google Chrome with Playwright for class automation tasks."""

    def __init__(self, log: LogCallback, stop_event: threading.Event | None = None) -> None:
        self.log = log
        self.stop_event = stop_event or threading.Event()

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
