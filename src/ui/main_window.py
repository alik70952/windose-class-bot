"""Persian CustomTkinter main window."""

from __future__ import annotations

import threading
from pathlib import Path
from shutil import rmtree
from tkinter import END, messagebox
from urllib.parse import urlparse

import customtkinter as ctk

from src.browser.automation import BrowserAutomation
from src.config.manager import AppConfig, BrowserSettings, ConfigManager, VADANA_PROFILE_NAME, VADANA_SITE_ADAPTER
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.security.credentials import CredentialStore
from src.utils.logger import UiLogQueue
from src.ui.schedule_frame import ScheduleFrame


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
        self.current_profile_id = ""

        self.show_password_var = ctk.BooleanVar(value=False)
        self.keep_open_var = ctk.BooleanVar(value=True)
        self.headless_var = ctk.BooleanVar(value=False)
        self.save_session_var = ctk.BooleanVar(value=False)
        self.save_password_var = ctk.BooleanVar(value=True)

        self._build_ui()
        self.load_config()
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
        self._build_class_preset_section(container)
        self.adobe_entry = self._entry(container, "آدرس اختیاری Adobe Connect")

        options = ctk.CTkFrame(container)
        options.pack(fill="x", pady=12)
        for column in range(2):
            options.grid_columnconfigure(column, weight=1)

        ctk.CTkCheckBox(options, text="نمایش رمز عبور", variable=self.show_password_var, command=self._toggle_password).grid(row=0, column=1, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="بعد از ورود مرورگر باز بماند", variable=self.keep_open_var).grid(row=0, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="اجرای Headless", variable=self.headless_var).grid(row=1, column=1, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="ذخیره نشست ورود مرورگر", variable=self.save_session_var).grid(row=1, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(options, text="ذخیره امن رمز عبور", variable=self.save_password_var).grid(row=2, column=1, sticky="e", padx=12, pady=8)

        buttons = ctk.CTkFrame(container)
        buttons.pack(fill="x", pady=12)
        button_specs = [
            ("ذخیره تنظیمات", self.save_config),
            ("بارگذاری تنظیمات", self.load_config),
            ("آزمایش بازشدن سایت", self.test_site),
            ("آزمایش ورود به وادانا", self.test_vadana_login),
            ("ورود خودکار به کلاس", self.start_bot),
            ("توقف ربات", self.stop_bot),
            ("حذف رمز ذخیره‌شده", self.delete_saved_password),
            ("پاک‌کردن نشست", self.clear_browser_session),
        ]
        self.action_buttons = []
        for index, (text, command) in enumerate(button_specs):
            buttons.grid_columnconfigure(index, weight=1)
            button = ctk.CTkButton(buttons, text=text, command=command)
            button.grid(row=0, column=index, padx=5, pady=8, sticky="ew")
            self.action_buttons.append(button)

        ctk.CTkLabel(container, text="گزارش اجرا", font=("Tahoma", 16, "bold"), anchor="e").pack(fill="x", pady=(10, 4))
        self.log_box = ctk.CTkTextbox(container, height=220, font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")

        self.schedule_frame = ScheduleFrame(container, self.config_manager, self.logs)
        self.schedule_frame.pack(fill="both", expand=False, pady=(12, 0))

    def _entry(self, parent: ctk.CTkFrame, label: str, show: str | None = None) -> ctk.CTkEntry:
        """Add a right-aligned label and entry pair."""
        ctk.CTkLabel(parent, text=label, anchor="e", font=("Tahoma", 13)).pack(fill="x", pady=(8, 2))
        entry = ctk.CTkEntry(parent, justify="right", font=("Tahoma", 13), show=show)
        entry.pack(fill="x")
        return entry

    def _build_class_preset_section(self, parent: ctk.CTkFrame) -> None:
        """Build simple fixed class cards for the Vadana Unit 39 profile."""
        self.selected_class_name = ""
        self.class_cards: dict[str, ctk.CTkFrame] = {}
        self.class_status_label = ctk.CTkLabel(parent, text="کلاس انتخاب‌شده: —", anchor="e", font=("Tahoma", 14, "bold"))
        self.class_status_label.pack(fill="x", pady=(12, 2))
        self.class_preset_frame = ctk.CTkFrame(parent)
        self.class_preset_frame.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(self.class_preset_frame, text="انتخاب کلاس", anchor="e", font=("Tahoma", 16, "bold")).pack(fill="x", padx=12, pady=(10, 4))
        for preset in CLASS_PRESETS:
            self._add_class_card(self.class_preset_frame, preset)

    def _add_class_card(self, parent: ctk.CTkFrame, preset: ClassPreset) -> None:
        card = ctk.CTkFrame(parent, border_width=1, border_color="#3b3b3b", fg_color="#242424")
        card.pack(fill="x", padx=12, pady=6)
        card.bind("<Button-1>", lambda _event, name=preset.name: self.select_class(name))
        for column in range(4):
            card.grid_columnconfigure(column, weight=1)
        ctk.CTkLabel(card, text=preset.name, anchor="e", justify="right", font=("Tahoma", 13, "bold"), wraplength=470).grid(row=0, column=1, columnspan=3, sticky="ew", padx=10, pady=(8, 2))
        ctk.CTkLabel(card, text=f"روز کلاس: {preset.weekday}", anchor="e", font=("Tahoma", 12)).grid(row=1, column=2, sticky="e", padx=10, pady=2)
        ctk.CTkLabel(card, text=f"ساعت کلاس: {preset.start_time} تا {preset.end_time}", anchor="e", font=("Tahoma", 12)).grid(row=1, column=1, sticky="e", padx=10, pady=2)
        ctk.CTkButton(card, text="ورود همین حالا", command=lambda p=preset: self.enter_preset_now(p)).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        ctk.CTkButton(card, text="انتخاب", command=lambda name=preset.name: self.select_class(name), width=80).grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 8))
        self.class_cards[preset.name] = card

    def select_class(self, class_name: str) -> None:
        """Select exactly one fixed class and mirror it to the hidden class field."""
        self.selected_class_name = class_name
        self.class_entry.delete(0, END)
        self.class_entry.insert(0, class_name)
        self.class_status_label.configure(text=f"کلاس انتخاب‌شده: {class_name}")
        for name, card in self.class_cards.items():
            selected = name == class_name
            card.configure(border_color="#1f6aa5" if selected else "#3b3b3b", fg_color="#12324a" if selected else "#242424")
        try:
            self.config_manager.save(self._settings_from_ui())
        except Exception:
            pass

    def _toggle_class_picker_visibility(self, config: AppConfig) -> None:
        is_vadana = config.site_adapter == VADANA_SITE_ADAPTER or config.profile_name == VADANA_PROFILE_NAME
        if is_vadana:
            self.class_entry.pack_forget()
            self.class_preset_frame.pack(fill="x", pady=(4, 8))
            self.class_status_label.pack(fill="x", pady=(12, 2))
        else:
            self.class_preset_frame.pack_forget()
            self.class_status_label.pack_forget()
            self.class_entry.pack(fill="x")

    def _toggle_password(self) -> None:
        """Switch password field visibility."""
        self.password_entry.configure(show="" if self.show_password_var.get() else "*")

    def _settings_from_ui(self) -> AppConfig:
        """Build an AppConfig from current form values."""
        return AppConfig(
            profile_name=self.profile_entry.get().strip(),
            login_url=self.url_entry.get().strip(),
            username=self.username_entry.get().strip(),
            class_name=self.selected_class_name or self.class_entry.get().strip(),
            adobe_connect_url=self.adobe_entry.get().strip(),
            site_adapter=VADANA_SITE_ADAPTER if ("وادانا" in self.profile_entry.get() or "vadana-sum39.ec.iau.ir" in self.url_entry.get()) else "",
            profile_id=self.current_profile_id or "vadana-sum39",
            browser=BrowserSettings(
                headless=self.headless_var.get(),
                keep_open=self.keep_open_var.get(),
                save_session=self.save_session_var.get(),
                session_dir="browser-session/vadana-sum39" if "وادانا" in self.profile_entry.get() else "browser-session",
            ),
        )

    def _apply_config(self, config: AppConfig) -> None:
        """Populate form fields from a configuration object."""
        self.current_profile_id = config.profile_id
        for entry, value in (
            (self.profile_entry, config.profile_name),
            (self.url_entry, config.login_url),
            (self.username_entry, config.username),
            (self.class_entry, config.class_name),
            (self.adobe_entry, config.adobe_connect_url),
        ):
            entry.delete(0, END)
            entry.insert(0, value)
        if config.class_name:
            self.select_class(config.class_name)
        else:
            self.class_status_label.configure(text="کلاس انتخاب‌شده: —")
        self._toggle_class_picker_visibility(config)
        self.keep_open_var.set(config.browser.keep_open)
        self.headless_var.set(config.browser.headless)
        self.save_session_var.set(config.browser.save_session)
        password = self.credentials.get_password(config.profile_id, config.username)
        self.password_entry.delete(0, END)
        self.password_entry.insert(0, password)

    def _validate(self, require_class: bool = True) -> AppConfig | None:
        """Validate required fields and URL format before starting automation."""
        config = self._settings_from_ui()
        missing = [name for name, value in (("نام پروفایل", config.profile_name), ("آدرس صفحه ورود", config.login_url), ("نام کاربری", config.username)) if not value]
        if require_class and not self.password_entry.get():
            missing.append("رمز عبور")
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
        if self.save_password_var.get():
            self.credentials.save_password(config.profile_id, config.username, self.password_entry.get())
            self.logs.log("تنظیمات ذخیره شد. رمز عبور در config.json ذخیره نشده است.")
        else:
            self.logs.log("تنظیمات ذخیره شد. ذخیره امن رمز عبور غیرفعال بود.")

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

    def test_vadana_login(self) -> None:
        """Run Vadana login through the dedicated site adapter."""
        config = self._validate(require_class=False)
        if config is None:
            return
        if config.site_adapter != VADANA_SITE_ADAPTER:
            self._show_error("برای آزمایش ورود، پروفایل «وادانا واحد ۳۹» را انتخاب کنید.")
            return
        password = self.password_entry.get() or self.credentials.get_password(config.profile_id, config.username)
        if not password:
            self._show_error("رمز عبور وارد نشده و رمز ذخیره‌شده‌ای پیدا نشد.")
            return
        self._run_vadana_login(config, password)

    def start_bot(self) -> None:
        """Start the full end-to-end class automation flow."""
        if self.worker and self.worker.is_alive():
            self._show_error("اجرای دیگری در حال انجام است.")
            return
        config = self._validate(require_class=False)
        if config is None:
            return
        schedule = self.schedule_frame.manager.get(self.schedule_frame.selected_id) if getattr(self, "schedule_frame", None) and self.schedule_frame.selected_id else None
        if schedule and schedule.class_name:
            config.class_name = schedule.class_name
            config.browser.keep_open = schedule.keep_browser_open
            config.browser.save_session = schedule.save_session
        if not config.class_name:
            self._show_error("ابتدا یکی از کلاس‌های آماده را انتخاب کنید.")
            return
        if config.site_adapter != VADANA_SITE_ADAPTER:
            self._show_error("Site Adapter پشتیبانی نمی‌شود.")
            return
        if not config.username:
            self._show_error("نام کاربری خالی است.")
            return
        password = self._get_or_save_password(config)
        if not password:
            self._show_error("رمز عبور وارد یا در Windows Credential Manager ذخیره نشده است.")
            return
        self._run_full_class_flow(config, password, schedule.launch_adobe_connect if schedule else True, (schedule.class_entry_timeout_seconds * 1000) if schedule else 900_000)

    def enter_preset_now(self, preset: ClassPreset) -> None:
        """Select a fixed class, save it, and immediately run the full manual flow."""
        self.select_class(preset.name)
        config = self._settings_from_ui()
        config.browser.keep_open = True
        config.browser.headless = False
        self.config_manager.save(config)
        password = self._get_or_save_password(config)
        if not password:
            self._show_error("رمز عبور وارد یا در Windows Credential Manager ذخیره نشده است.")
            return
        self._run_full_class_flow(config, password, True, 900_000)

    def _get_or_save_password(self, config: AppConfig) -> str:
        password = self.password_entry.get() or self.credentials.get_password(config.profile_id, config.username)
        if password and self.password_entry.get() and self.save_password_var.get():
            self.credentials.save_password(config.profile_id, config.username, password)
        return password

    def delete_saved_password(self) -> None:
        """Delete the saved password for the stable active profile id."""
        config = self._settings_from_ui()
        self.credentials.delete_password(config.profile_id)
        self.password_entry.delete(0, END)
        self.logs.log("رمز ذخیره‌شده حذف شد.")

    def clear_browser_session(self) -> None:
        """Remove the local browser session directory for the active profile."""
        config = self._settings_from_ui()
        session_path = Path(config.browser.session_dir)
        if session_path.exists():
            rmtree(session_path)
            self.logs.log("نشست مرورگر پاک شد.")
        else:
            self.logs.log("نشست ذخیره‌شده‌ای برای پاک‌کردن پیدا نشد.")

    def stop_bot(self) -> None:
        """Request the browser worker to stop."""
        self.stop_event.set()
        self.logs.log("درخواست توقف ارسال شد.")

    def _run_vadana_login(self, config: AppConfig, password: str) -> None:
        """Run the Vadana login worker without touching Tk widgets from the worker."""
        if self.worker and self.worker.is_alive():
            self._show_error("یک عملیات در حال اجرا است. ابتدا آن را متوقف کنید.")
            return
        self.stop_event.clear()
        self._set_running(True)
        self.logs.log("آزمایش ورود به وادانا شروع شد.")
        automation = BrowserAutomation(self.logs.log, self.stop_event)
        def worker() -> None:
            try:
                automation.login_to_site(config, password)
            finally:
                self.logs.log("WORKER_FINISHED")
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _run_full_class_flow(self, config: AppConfig, password: str, launch_adobe_connect: bool, timeout_ms: int) -> None:
        """Run the shared full class flow in a worker thread."""
        if self.worker and self.worker.is_alive():
            self._show_error("اجرای دیگری در حال انجام است.")
            return
        self.stop_event.clear()
        self._set_running(True)
        automation = BrowserAutomation(self.logs.log, self.stop_event)
        def worker() -> None:
            try:
                automation.login_and_enter_class(config, password, timeout_ms, launch_adobe_connect)
            finally:
                self.logs.log("WORKER_FINISHED")
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _run_browser(self, url: str, settings: BrowserSettings, start_message: str) -> None:
        """Run Playwright work in a background thread so the UI stays responsive."""
        if self.worker and self.worker.is_alive():
            self._show_error("یک عملیات در حال اجرا است. ابتدا آن را متوقف کنید.")
            return
        self.stop_event.clear()
        self._set_running(True)
        self.logs.log(start_message)
        automation = BrowserAutomation(self.logs.log, self.stop_event)
        def worker() -> None:
            try:
                automation.open_site(url, settings)
            finally:
                self.logs.log("WORKER_FINISHED")
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for button in getattr(self, "action_buttons", []):
            button.configure(state=state)

    def _show_error(self, message: str) -> None:
        """Display and log a recoverable error."""
        self.logs.log(message)
        messagebox.showerror("خطا", message)

    def _poll_logs(self) -> None:
        """Move queued worker logs into the textbox from the UI thread."""
        for message in self.logs.drain():
            if message == "WORKER_FINISHED":
                self._set_running(False)
                continue
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(200, self._poll_logs)
