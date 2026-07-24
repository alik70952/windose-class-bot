"""Schedule management frame separated from automation logic."""
from __future__ import annotations
from datetime import datetime, timedelta
import subprocess
import uuid
import customtkinter as ctk
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.scheduling.manager import ScheduleManager
from src.scheduling.models import ClassSchedule
from src.scheduling.windows_task_scheduler import (
    WindowsTaskScheduler,
    build_run_command,
    format_run_command,
    project_root,
    sanitize_task_name,
)


class ScheduleFrame(ctk.CTkFrame):
    """Minimal delay-based scheduler for the fixed Vadana class cards."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master)
        self.manager = ScheduleManager(config_manager)
        self.config_manager = config_manager
        self.logs = logs
        self.selected_id = ""
        self.class_var = ctk.StringVar(value=CLASS_PRESETS[0].name)
        self.delay_hours_var = ctk.StringVar(value="0")
        self.delay_minutes_var = ctk.StringVar(value="5")
        self._build()
        self.prefill_for_class(CLASS_PRESETS[0], log=False)
        self.refresh()

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

        ctk.CTkButton(self, text="اجرا", command=self.save).pack(anchor="e", padx=8, pady=6)

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
        self.manager.upsert(s)
        self.selected_id = s.id
        scheduler = WindowsTaskScheduler()
        r = scheduler.register(s)
        command = build_run_command(s.id)
        self.logs.log(f"Task name: {sanitize_task_name(s.id)}")
        self.logs.log(f"schedule_id: {s.id}")
        self.logs.log(f"Action Command: {command[0]}")
        self.logs.log(f"Action Arguments: {subprocess.list2cmdline(command[1:])}")
        self.logs.log(f"WorkingDirectory: {project_root()}")
        self.logs.log(f"StartBoundary: {s.next_run}")
        self.logs.log(f"config.json: {self.config_manager.path.resolve()}")
        self.logs.log(f"Manual command: {format_run_command(command)}")
        if r.success:
            self.logs.log(f"Last Run Result: {scheduler.last_run_result(s.id).message}")
        self.logs.log("زمان‌بندی اجرا ثبت شد." if r.success else r.message)
        self.status_label.configure(text="زمان‌بندی ثبت شد." if r.success else r.message)
        self.refresh()

    def refresh(self):
        """Keep the schedule section free of lists, tables, and extra controls."""
        if not self.selected_id:
            self.status_label.configure(text="هنوز زمان‌بندی ثبت نشده است.")
