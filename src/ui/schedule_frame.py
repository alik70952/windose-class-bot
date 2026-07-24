"""Schedule management frame separated from automation logic."""
from __future__ import annotations
from datetime import datetime, timedelta
import uuid
import customtkinter as ctk
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.scheduling.manager import ScheduleManager
from src.scheduling.schedule_store import ScheduleStore
from src.scheduling.models import ClassSchedule
from src.scheduling.worker_task import ensure_scheduler_worker_running
from src.security.credentials import CredentialStore


class ScheduleFrame(ctk.CTkFrame):
    """Minimal delay-based scheduler for the fixed Vadana class cards."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master)
        self.manager = ScheduleManager(config_manager)
        self.store = ScheduleStore()
        self.config_manager = config_manager
        self.logs = logs
        self.selected_id = ""
        self.class_var = ctk.StringVar(value=CLASS_PRESETS[0].name)
        self.delay_hours_var = ctk.StringVar(value="0")
        self.delay_minutes_var = ctk.StringVar(value="5")
        self._build()
        self.delay_hours_var.trace_add("write", self._update_preview)
        self.delay_minutes_var.trace_add("write", self._update_preview)
        self.prefill_for_class(CLASS_PRESETS[0], log=False)
        self.refresh()
        self._update_preview()

    def _build(self):
        ctk.CTkLabel(self, text="زمان‌بندی ساده اجرای ربات", font=("Tahoma", 18, "bold"), anchor="e").pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(self, text="کلاس انتخاب‌شده:", anchor="e").pack(fill="x", padx=8, pady=(8, 2))
        self.selected_class_label = ctk.CTkLabel(self, text=self.class_var.get(), anchor="e", font=("Tahoma", 14, "bold"))
        self.selected_class_label.pack(fill="x", padx=8, pady=(0, 8))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=8, pady=8)
        for i in range(2):
            form.grid_columnconfigure(i, weight=1)

        self.hours_entry = ctk.CTkEntry(form, textvariable=self.delay_hours_var, justify="center", width=90)
        self.minutes_entry = ctk.CTkEntry(form, textvariable=self.delay_minutes_var, justify="center", width=90)
        ctk.CTkLabel(form, text="چند ساعت دیگر:", anchor="e").grid(row=0, column=1, sticky="e", padx=8, pady=(8, 2))
        self.hours_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkLabel(form, text="چند دقیقه دیگر:", anchor="e").grid(row=0, column=0, sticky="e", padx=8, pady=(8, 2))
        self.minutes_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        quick = ctk.CTkFrame(self, fg_color="transparent")
        quick.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkLabel(quick, text="انتخاب سریع:", anchor="e").pack(side="right", padx=(8, 0))
        for minutes in (5, 15, 30, 60):
            label = "۱ ساعت" if minutes == 60 else f"{minutes} دقیقه"
            ctk.CTkButton(
                quick,
                text=label,
                width=76,
                height=28,
                fg_color=("#68707c", "#3b414b"),
                command=lambda value=minutes: self._set_quick_delay(value),
            ).pack(side="right", padx=3)

        self.preview_label = ctk.CTkLabel(self, text="", anchor="e", font=("Tahoma", 12, "bold"), text_color="#4da3ff")
        self.preview_label.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkButton(self, text="ثبت زمان‌بندی", command=self.save, height=38).pack(anchor="e", padx=8, pady=6)

        self.status_label = ctk.CTkLabel(self, text="هنوز زمان‌بندی ثبت نشده است.", anchor="e", font=("Tahoma", 11), wraplength=760)
        self.status_label.pack(fill="x", padx=8, pady=(4, 10))

    def _selected_preset(self) -> ClassPreset:
        return next((p for p in CLASS_PRESETS if p.name == self.class_var.get()), CLASS_PRESETS[0])

    def prefill_for_class(self, preset: ClassPreset, log: bool = True):
        self.class_var.set(preset.name)
        self.selected_class_label.configure(text=preset.name)
        self.update_idletasks()
        if log:
            self.logs.log("کلاس در فرم زمان‌بندی انتخاب شد")

    def _delay(self) -> timedelta | None:
        try:
            hours = int(self.delay_hours_var.get() or 0)
            minutes = int(self.delay_minutes_var.get() or 0)
        except ValueError:
            return None
        if hours < 0 or minutes < 0 or minutes > 59 or (hours == 0 and minutes == 0):
            return None
        return timedelta(hours=hours, minutes=minutes)

    def _set_quick_delay(self, minutes: int) -> None:
        """Fill the delay fields from a common, mistake-resistant shortcut."""
        hours, remaining_minutes = divmod(minutes, 60)
        self.delay_hours_var.set(str(hours))
        self.delay_minutes_var.set(str(remaining_minutes))

    def _update_preview(self, *_args) -> None:
        """Show the concrete local run time before the user saves anything."""
        if not getattr(self, "preview_label", None):
            return
        delay = self._delay()
        if delay is None:
            self.preview_label.configure(text="زمان اجرای معتبر را وارد کنید.", text_color="#ef6461")
            return
        when = datetime.now() + delay
        self.preview_label.configure(
            text=f"زمان تقریبی اجرا روی همین رایانه: {when:%Y/%m/%d  %H:%M}",
            text_color="#4da3ff",
        )

    def _schedule_from_form(self):
        delay = self._delay()
        if delay is None:
            self.status_label.configure(text="زمان را به‌صورت عددی وارد کنید؛ دقیقه باید بین 0 تا 59 باشد و کل زمان نباید صفر باشد.")
            self.logs.log("زمان واردشده معتبر نیست.")
            return None
        when = datetime.now() + delay
        return ClassSchedule(
            id=uuid.uuid4().hex,
            # Use the persisted profile identity.  A hard-coded value caused
            # background runs to stop before BrowserAutomation for migrated or
            # user-created profiles.
            profile_id=self.config_manager.load().profile_id,
            class_name=self.class_var.get(),
            recurrence="once",
            date=when.date().isoformat(),
            start_time=when.strftime("%H:%M"),
            class_start_time=when.strftime("%H:%M"),
            early_minutes=0,
            effective_run_time=when.strftime("%H:%M"),
            effective_run_date=when.date().isoformat(),
            class_entry_timeout_seconds=900,
            launch_adobe_connect=True,
            keep_browser_open=True,
            enabled=True,
            adobe_launch_wait_seconds=20,
            max_late_start_minutes=15,
            next_run=when.isoformat(timespec="seconds"),
        )

    def save(self):
        s = self._schedule_from_form()
        if not s:
            return
        config = self.config_manager.load()
        if not config.profile_id or not config.username or not CredentialStore().get_password(config.profile_id, config.username):
            self.status_label.configure(text="زمان‌بندی ثبت نشد: Profile یا Credential معتبر نیست.")
            return
        delay = self._delay()
        assert delay is not None
        item = self.store.create(s.profile_id, s.class_name, datetime.fromisoformat(s.next_run).timestamp(),
                                 delay.days * 24 + delay.seconds // 3600,
                                 (delay.seconds % 3600) // 60, schedule_id=s.id)
        self.selected_id = s.id
        result = ensure_scheduler_worker_running()
        self.logs.log(f"schedule_id: {s.id}")
        current = self.store.get(item.id)
        if result.success and current is not None and current.status == "pending":
            self.logs.log("زمان‌بندی در SQLite ثبت شد و Heartbeat معتبر است.")
            self.status_label.configure(text="تایم زمان‌بندی شما ثبت شد.")
        else:
            # Do not throw away the user's schedule just because Windows Task
            # Scheduler (or its heartbeat check) is temporarily unavailable.
            # It remains pending and will be picked up after the worker starts,
            # including on the next app launch/logon.
            self.logs.log(result.message)
            self.status_label.configure(
                text="زمان‌بندی ثبت شد، اما سرویس خودکار هنوز فعال نیست. "
                     "install.bat را اجرا کنید. جزئیات خطا در گزارش ثبت شد."
            )
        self.refresh()

    def refresh(self):
        """Keep the schedule section free of lists, tables, and extra controls."""
        if not self.selected_id:
            self.status_label.configure(text="هنوز زمان‌بندی ثبت نشده است.")
