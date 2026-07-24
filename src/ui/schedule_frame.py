"""Schedule management frame separated from automation logic."""
from __future__ import annotations
import threading
from datetime import datetime, timedelta
from tkinter import messagebox
import customtkinter as ctk
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.scheduling.manager import ScheduleManager
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import format_12h, next_run_datetime, remaining_text
from src.scheduling.windows_task_scheduler import WindowsTaskScheduler
from src.scheduling.executor import ScheduleExecutor


class ScheduleFrame(ctk.CTkFrame):
    """Simple delay-based scheduler for the fixed Vadana class cards."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master)
        self.manager = ScheduleManager(config_manager)
        self.logs = logs
        self.selected_id = ""
        self.class_var = ctk.StringVar(value=CLASS_PRESETS[0].name)
        self.delay_hours_var = ctk.StringVar(value="0")
        self.delay_minutes_var = ctk.StringVar(value="5")
        self._build()
        self.prefill_for_class(CLASS_PRESETS[0], log=False)
        self.refresh()
        self._update_summary()

    def _build(self):
        ctk.CTkLabel(self, text="زمان‌بندی ساده اجرای ربات", font=("Tahoma", 18, "bold"), anchor="e").pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(self, text="کلاس را انتخاب کنید، بگویید ربات چند ساعت و چند دقیقه دیگر اجرا شود، سپس دکمه «اجرا» را بزنید.", anchor="e", wraplength=760).pack(fill="x", padx=8)

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=8, pady=8)
        for i in range(4):
            form.grid_columnconfigure(i, weight=1)

        self.class_menu = ctk.CTkOptionMenu(form, variable=self.class_var, values=[p.name for p in CLASS_PRESETS], command=self._on_class_selected)
        ctk.CTkLabel(form, text="کلاس", anchor="e").grid(row=0, column=3, sticky="e", padx=8, pady=(8, 2))
        self.class_menu.grid(row=1, column=1, columnspan=3, sticky="ew", padx=8, pady=(0, 8))

        self.hours_entry = ctk.CTkEntry(form, textvariable=self.delay_hours_var, justify="center", width=90)
        self.minutes_entry = ctk.CTkEntry(form, textvariable=self.delay_minutes_var, justify="center", width=90)
        ctk.CTkLabel(form, text="چند ساعت دیگر", anchor="e").grid(row=2, column=3, sticky="e", padx=8, pady=(8, 2))
        self.hours_entry.grid(row=3, column=3, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkLabel(form, text="چند دقیقه دیگر", anchor="e").grid(row=2, column=2, sticky="e", padx=8, pady=(8, 2))
        self.minutes_entry.grid(row=3, column=2, sticky="ew", padx=8, pady=(0, 8))

        for var in (self.delay_hours_var, self.delay_minutes_var):
            var.trace_add("write", lambda *_args: self._update_summary())

        self.summary_label = ctk.CTkLabel(self, text="", anchor="e", wraplength=760)
        self.summary_label.pack(fill="x", padx=8, pady=4)

        actions = ctk.CTkFrame(self)
        actions.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(actions, text="اجرا", command=self.save).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(actions, text="حذف زمان‌بندی انتخاب‌شده", command=self.delete).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(actions, text="اجرای همین حالا", command=self.run_now).pack(side="right", padx=4, pady=6)

        self.list_frame = ctk.CTkFrame(self)
        self.list_frame.pack(fill="x", padx=8, pady=(4, 10))

    def _selected_preset(self) -> ClassPreset:
        return next((p for p in CLASS_PRESETS if p.name == self.class_var.get()), CLASS_PRESETS[0])

    def _on_class_selected(self, _value: str):
        self.prefill_for_class(self._selected_preset())

    def prefill_for_class(self, preset: ClassPreset, log: bool = True):
        self.class_var.set(preset.name)
        self._update_summary()
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

    def _update_summary(self):
        delay = self._delay()
        if delay is None:
            self.summary_label.configure(text="زمان را به‌صورت عددی وارد کنید؛ دقیقه باید بین 0 تا 59 باشد و کل زمان نباید صفر باشد.")
            return
        when = datetime.now() + delay
        self.summary_label.configure(text=f"ربات برای کلاس «{self.class_var.get()}» در {when.strftime('%Y-%m-%d %H:%M')} اجرا می‌شود.")

    def _schedule_from_form(self):
        delay = self._delay()
        if delay is None:
            self.logs.log("زمان واردشده معتبر نیست.")
            return None
        when = datetime.now() + delay
        return ClassSchedule(
            id=self.selected_id or __import__('uuid').uuid4().hex,
            profile_id="vadana-sum39",
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
        r = WindowsTaskScheduler().register(s)
        self.logs.log("زمان‌بندی اجرا ثبت شد." if r.success else r.message)
        self.refresh()

    def refresh(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        schedules = sorted(self.manager.list(), key=lambda item: item.next_run or item.created_at)
        for s in schedules:
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=4)
            row.bind("<Button-1>", lambda _e, sid=s.id: setattr(self, 'selected_id', sid))
            try:
                nr = next_run_datetime(s)
                next_text = f"{nr.strftime('%Y-%m-%d %H:%M')} | باقی‌مانده: {remaining_text(nr)}"
            except Exception:
                next_text = s.next_run or "—"
            text = f"{s.class_name}\nاجرای برنامه‌ریزی‌شده: {format_12h(s.effective_run_time or s.start_time)} | {next_text} | نتیجه آخر: {s.last_run_status}"
            ctk.CTkLabel(row, text=text, justify="right", anchor="e", wraplength=760).pack(side="right", fill="x", expand=True, padx=6)

    def delete(self):
        if self.selected_id:
            self.manager.delete(self.selected_id)
            WindowsTaskScheduler().delete(self.selected_id)
            self.selected_id = ""
            self.refresh()

    def run_now(self):
        if self.selected_id and messagebox.askyesno("تأیید", "اجرای دستی زمان‌بندی را نادیده می‌گیرد. ادامه می‌دهید؟"):
            threading.Thread(target=ScheduleExecutor(log=self.logs.log).run, args=(self.selected_id,), daemon=True).start()
