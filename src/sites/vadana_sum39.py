"""Playwright adapter for Vadana Unit 39 login."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ModuleNotFoundError:  # pragma: no cover - lets unit tests run without browser deps.
    class PlaywrightError(Exception):
        pass
    class PlaywrightTimeoutError(TimeoutError):
        pass

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

PERSIAN_DIGITS = str.maketrans({**{ord(a): b for a, b in zip("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")}, ord("ي"): "ی", ord("ك"): "ک", ord("("): " ", ord(")"): " ", ord("\u200c"): " "})

def normalize_persian_text(value: str) -> str:
    """Normalize Persian/Arabic variants, whitespace, ZWNJ, parentheses, and digits."""
    text = value.translate(PERSIAN_DIGITS).replace("ك", "ک").replace("ي", "ی")
    text = text.replace("（", " ").replace("）", " ")
    return re.sub(r"\s+", " ", text).strip()

def sanitize_diagnostic(value: str) -> str:
    """Remove token-like query strings from diagnostics."""
    return re.sub(r"([?&](?:token|sid|session|key)=)[^&\s]+", r"\1...", value, flags=re.I)[:300]

class CourseSelectionError(RuntimeError):
    """Raised when a course cannot be selected safely."""

# Methods are attached to keep compatibility with the existing adapter class definition.
def _adapter_open_course(self: VadanaSum39Adapter, page, class_name: str, timeout_ms: int, stop_event: threading.Event):
    """Open a course by exact normalized visible link text from the dashboard."""
    self._check_stop(stop_event)
    self.log("صفحه میزکار شناسایی شد")
    try:
        page.get_by_text("درس‌های من", exact=True).wait_for(state="visible", timeout=timeout_ms)
    except Exception as exc:
        raise CourseSelectionError("بخش درس‌های من پیدا نشد.") from exc
    self.log("بخش درس‌های من پیدا شد")
    self.log("در حال جست‌وجوی کلاس انتخاب‌شده")
    target = normalize_persian_text(class_name)
    links = page.locator("a")
    matches: list[tuple[str, object]] = []
    for index in range(links.count()):
        self._check_stop(stop_event)
        link = links.nth(index)
        try:
            text = link.inner_text(timeout=500).strip()
        except Exception:
            continue
        if normalize_persian_text(text) == target:
            matches.append((text, link))
    if len(matches) == 1:
        matches[0][1].click(timeout=timeout_ms); self.log("کلاس موردنظر پیدا شد")
        self._verify_course_page(page, class_name, timeout_ms, stop_event); return page
    if len(matches) > 1:
        names = "، ".join(sorted({m[0] for m in matches})[:5])
        raise CourseSelectionError(f"چند درس با نام مشابه پیدا شد: {names}")
    similar = []
    for index in range(links.count()):
        try:
            text = links.nth(index).inner_text(timeout=300).strip()
            nt = normalize_persian_text(text)
            if target in nt or nt in target: similar.append(text)
        except Exception: pass
    if similar:
        raise CourseSelectionError("درس دقیق پیدا نشد. موارد مشابه فقط برای بررسی: " + "، ".join(similar[:5]))
    raise CourseSelectionError("درس انتخاب‌شده پیدا نشد.")

def _adapter_verify_course_page(self: VadanaSum39Adapter, page, class_name: str, timeout_ms: int, stop_event: threading.Event) -> bool:
    """Verify opened page title before entering online class."""
    self._check_stop(stop_event)
    try: page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception: pass
    self.log("صفحه درس باز شد")
    target = normalize_persian_text(class_name)
    for selector in ["h1", "h2", "[role='heading']", ".page-header-headings"]:
        loc = page.locator(selector)
        try:
            for i in range(min(loc.count(), 5)):
                text = loc.nth(i).inner_text(timeout=500)
                if target in normalize_persian_text(text):
                    self.log("عنوان درس تأیید شد"); return True
        except Exception: continue
    raise CourseSelectionError("عنوان صفحه درس با کلاس انتخاب‌شده تطبیق ندارد.")

def _adapter_enter_online_class(self: VadanaSum39Adapter, page, class_name: str, timeout_ms: int, stop_event: threading.Event):
    """Click the live 'ورود به کلاس' link and never the archive link."""
    end = datetime.now().timestamp() + timeout_ms / 1000
    logged = False
    while datetime.now().timestamp() < end:
        self._check_stop(stop_event)
        try:
            page.get_by_text("کلاس آنلاین", exact=True).wait_for(state="visible", timeout=1000)
        except Exception: pass
        candidates = [lambda: page.get_by_role("link", name="ورود به کلاس", exact=True).first, lambda: page.get_by_text("ورود به کلاس", exact=True).first]
        for factory in candidates:
            try:
                link = factory(); txt = normalize_persian_text(link.inner_text(timeout=500))
                if "آرشیو" not in txt and txt == normalize_persian_text("ورود به کلاس") and link.is_visible(timeout=500):
                    link.click(timeout=timeout_ms); self.log("روی لینک ورود به کلاس کلیک شد"); return page
            except Exception: continue
        if not logged:
            self.log("در انتظار فعال‌شدن لینک ورود به کلاس..."); logged = True
        stop_event.wait(10)
    raise CourseSelectionError("لینک ورود به کلاس در زمان مجاز فعال نشد.")

VadanaSum39Adapter.open_course = _adapter_open_course  # type: ignore[attr-defined]
VadanaSum39Adapter._verify_course_page = _adapter_verify_course_page  # type: ignore[attr-defined]
VadanaSum39Adapter.enter_online_class = _adapter_enter_online_class  # type: ignore[attr-defined]
