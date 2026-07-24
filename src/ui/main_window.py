"""Persian CustomTkinter main window."""

from __future__ import annotations

import threading
from tkinter import END, messagebox
from urllib.parse import urlparse

import customtkinter as ctk

from src.browser.automation import BrowserAutomation
from src.config.manager import AppConfig, BrowserSettings, ConfigManager
from src.security.credentials import CredentialStore
from src.utils.logger import UiLogQueue


class MainWindow(ctk.CTk):
    """Main RTL-oriented desktop window for Windows Class Bot."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("ربات ورود به کلاس آنلاین")
        self.geometry("900x760")
        self.minsize(780, 680)

        self.config_manager = ConfigManager()
        self.credentials = CredentialStore()
        self.logs = UiLogQueue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

        self.show_password_var = ctk.BooleanVar(value=False)
        self.keep_open_var = ctk.BooleanVar(value=True)
        self.headless_var = ctk.BooleanVar(value=False)
        self.save_session_var = ctk.BooleanVar(value=False)

        self._build_ui()
        self._poll_logs()

    def _build_ui(self) -> None:
        """Create the form, actions, and log panel."""
        container = ctk.CTkFrame(self)
        container.pack(fill="both", expand=True, padx=24, pady=24)

        title = ctk.CTkLabel(container, text="ربات ورود به کلاس آنلاین", font=("Tahoma", 24, "bold"), anchor="e")
        title.pack(fill="x", pady=(0, 18))

        self.profile_entry = self._entry(container, "نام پروفایل *")
        self.url_entry = self._entry(container, "آدرس صفحه ورود *")
        self.username_entry = self._entry(container, "نام کاربری *")
        self.password_entry = self._entry(container, "رمز عبور *", show="*")
        self.class_entry = self._entry(container, "نام کلاس *")
        self.adobe_entry = self._entry(container, "آدرس اختیاری Adobe Connect")

        options = ctk.CTkFrame(container)
        options.pack(fill="x", pady=12)
        for column in range(2):
            options.grid_columnconfigure(column, weight=1)

        ctk.CTkCheckBox(options, text="نمایش رمز عبور", variable=self.show_password_var, command=self._toggle_password).grid(row=0, column=1, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="باز نگه‌داشتن مرورگر", variable=self.keep_open_var).grid(row=0, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="اجرای Headless", variable=self.headless_var).grid(row=1, column=1, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="ذخیره نشست ورود مرورگر", variable=self.save_session_var).grid(row=1, column=0, sticky="e", padx=12, pady=8)

        buttons = ctk.CTkFrame(container)
        buttons.pack(fill="x", pady=12)
        button_specs = [
            ("ذخیره تنظیمات", self.save_config),
            ("بارگذاری تنظیمات", self.load_config),
            ("آزمایش بازشدن سایت", self.test_site),
            ("شروع ربات", self.start_bot),
            ("توقف ربات", self.stop_bot),
        ]
        for index, (text, command) in enumerate(button_specs):
            buttons.grid_columnconfigure(index, weight=1)
            ctk.CTkButton(buttons, text=text, command=command).grid(row=0, column=index, padx=5, pady=8, sticky="ew")

        ctk.CTkLabel(container, text="گزارش اجرا", font=("Tahoma", 16, "bold"), anchor="e").pack(fill="x", pady=(10, 4))
        self.log_box = ctk.CTkTextbox(container, height=220, font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")

    def _entry(self, parent: ctk.CTkFrame, label: str, show: str | None = None) -> ctk.CTkEntry:
        """Add a right-aligned label and entry pair."""
        ctk.CTkLabel(parent, text=label, anchor="e", font=("Tahoma", 13)).pack(fill="x", pady=(8, 2))
        entry = ctk.CTkEntry(parent, justify="right", font=("Tahoma", 13), show=show)
        entry.pack(fill="x")
        return entry

    def _toggle_password(self) -> None:
        """Switch password field visibility."""
        self.password_entry.configure(show="" if self.show_password_var.get() else "*")

    def _settings_from_ui(self) -> AppConfig:
        """Build an AppConfig from current form values."""
        return AppConfig(
            profile_name=self.profile_entry.get().strip(),
            login_url=self.url_entry.get().strip(),
            username=self.username_entry.get().strip(),
            class_name=self.class_entry.get().strip(),
            adobe_connect_url=self.adobe_entry.get().strip(),
            browser=BrowserSettings(
                headless=self.headless_var.get(),
                keep_open=self.keep_open_var.get(),
                save_session=self.save_session_var.get(),
            ),
        )

    def _apply_config(self, config: AppConfig) -> None:
        """Populate form fields from a configuration object."""
        for entry, value in (
            (self.profile_entry, config.profile_name),
            (self.url_entry, config.login_url),
            (self.username_entry, config.username),
            (self.class_entry, config.class_name),
            (self.adobe_entry, config.adobe_connect_url),
        ):
            entry.delete(0, END)
            entry.insert(0, value)
        self.keep_open_var.set(config.browser.keep_open)
        self.headless_var.set(config.browser.headless)
        self.save_session_var.set(config.browser.save_session)
        password = self.credentials.get_password(config.profile_name, config.username)
        self.password_entry.delete(0, END)
        self.password_entry.insert(0, password)

    def _validate(self, require_class: bool = True) -> AppConfig | None:
        """Validate required fields and URL format before starting automation."""
        config = self._settings_from_ui()
        missing = [name for name, value in (("نام پروفایل", config.profile_name), ("آدرس صفحه ورود", config.login_url), ("نام کاربری", config.username), ("رمز عبور", self.password_entry.get())) if not value]
        if require_class and not config.class_name:
            missing.append("نام کلاس")
        parsed = urlparse(config.login_url)
        if missing:
            self._show_error("فیلدهای ضروری تکمیل نشده‌اند: " + "، ".join(missing))
            return None
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self._show_error("آدرس صفحه ورود معتبر نیست. آدرس باید با http یا https شروع شود.")
            return None
        return config

    def save_config(self) -> None:
        """Save non-sensitive config and the password in keyring."""
        config = self._validate(require_class=False)
        if config is None:
            return
        self.config_manager.save(config)
        self.credentials.save_password(config.profile_name, config.username, self.password_entry.get())
        self.logs.log("تنظیمات ذخیره شد. رمز عبور در config.json ذخیره نشده است.")

    def load_config(self) -> None:
        """Load settings from config.json and password from keyring."""
        try:
            self._apply_config(self.config_manager.load())
            self.logs.log("تنظیمات بارگذاری شد.")
        except Exception as exc:  # noqa: BLE001 - show readable errors in the UI.
            self._show_error(f"خطا در بارگذاری تنظیمات: {exc}")

    def test_site(self) -> None:
        """Open the configured login page as a connectivity/browser test."""
        config = self._validate(require_class=False)
        if config is not None:
            self._run_browser(config.login_url, config.browser, "آزمایش بازشدن سایت شروع شد.")

    def start_bot(self) -> None:
        """Start phase-one bot behavior: open the site for future login steps."""
        config = self._validate(require_class=True)
        if config is not None:
            self._run_browser(config.login_url, config.browser, "شروع ربات: سایت باز می‌شود.")

    def stop_bot(self) -> None:
        """Request the browser worker to stop."""
        self.stop_event.set()
        self.logs.log("درخواست توقف ارسال شد.")

    def _run_browser(self, url: str, settings: BrowserSettings, start_message: str) -> None:
        """Run Playwright work in a background thread so the UI stays responsive."""
        if self.worker and self.worker.is_alive():
            self._show_error("یک عملیات در حال اجرا است. ابتدا آن را متوقف کنید.")
            return
        self.stop_event.clear()
        self.logs.log(start_message)
        automation = BrowserAutomation(self.logs.log, self.stop_event)
        self.worker = threading.Thread(target=automation.open_site, args=(url, settings), daemon=True)
        self.worker.start()

    def _show_error(self, message: str) -> None:
        """Display and log a recoverable error."""
        self.logs.log(message)
        messagebox.showerror("خطا", message)

    def _poll_logs(self) -> None:
        """Move queued worker logs into the textbox from the UI thread."""
        for message in self.logs.drain():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(200, self._poll_logs)
