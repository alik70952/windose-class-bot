"""CustomTkinter dialog for adding/editing class schedules."""
from __future__ import annotations
import customtkinter as ctk
from src.classes import CLASS_PRESETS, CUSTOM_CLASS_LABEL
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import PERSIAN_WEEKDAYS, validate_time

class ScheduleEditorDialog(ctk.CTkToplevel):
    """Non-blocking Persian schedule editor dialog."""
    def __init__(self, master, schedule: ClassSchedule | None = None) -> None:
        super().__init__(master); self.title("افزودن/ویرایش زمان‌بندی"); self.result: ClassSchedule | None = None
        self.schedule = schedule or ClassSchedule(name=CLASS_PRESETS[0].name, class_name=CLASS_PRESETS[0].name)
        self.entries: dict[str, ctk.CTkEntry] = {}
        for label, key in [("نام دلخواه زمان‌بندی", "name"),("نام کلاس سفارشی", "class_name"),("ساعت شروع", "start_time"),("ساعت پایان نمایشی", "end_time"),("چند دقیقه زودتر وارد شود", "early_minutes"),("تعداد تلاش مجدد", "retry_count"),("فاصله تلاش‌ها", "retry_delay_seconds"),("مدت انتظار فعال‌شدن کلاس", "class_entry_timeout_seconds")]:
            ctk.CTkLabel(self, text=label, anchor="e").pack(fill="x", padx=12, pady=(8,2)); e=ctk.CTkEntry(self, justify="right"); e.insert(0, str(getattr(self.schedule,key))); e.pack(fill="x", padx=12); self.entries[key]=e
        self.class_combo = ctk.CTkComboBox(self, values=[p.name for p in CLASS_PRESETS]+[CUSTOM_CLASS_LABEL]); self.class_combo.set(self.schedule.class_name); self.class_combo.pack(fill="x", padx=12, pady=6)
        self.weekday_combo = ctk.CTkComboBox(self, values=PERSIAN_WEEKDAYS); self.weekday_combo.set(self.schedule.weekday); self.weekday_combo.pack(fill="x", padx=12, pady=6)
        self.recur_combo = ctk.CTkComboBox(self, values=["once", "weekly", "disabled"]); self.recur_combo.set(self.schedule.recurrence); self.recur_combo.pack(fill="x", padx=12, pady=6)
        self.enabled = ctk.BooleanVar(value=self.schedule.enabled); self.keep_open=ctk.BooleanVar(value=self.schedule.keep_browser_open); self.save_session=ctk.BooleanVar(value=self.schedule.save_session); self.launch_adobe=ctk.BooleanVar(value=self.schedule.launch_adobe_connect)
        for text,var in [("فعال",self.enabled),("بازماندن مرورگر",self.keep_open),("ذخیره نشست",self.save_session),("اجرای Adobe Connect",self.launch_adobe)]: ctk.CTkCheckBox(self,text=text,variable=var).pack(anchor="e", padx=12)
        ctk.CTkButton(self, text="ذخیره", command=self._save).pack(pady=10)
    def _save(self) -> None:
        if not validate_time(self.entries["start_time"].get()) or not validate_time(self.entries["end_time"].get()): return
        s=self.schedule; s.name=self.entries["name"].get().strip(); selected=self.class_combo.get(); custom=self.entries["class_name"].get().strip(); s.class_name=custom if selected==CUSTOM_CLASS_LABEL else selected
        s.weekday=self.weekday_combo.get(); s.start_time=self.entries["start_time"].get(); s.end_time=self.entries["end_time"].get(); s.early_minutes=int(self.entries["early_minutes"].get() or 5); s.recurrence=self.recur_combo.get(); s.enabled=self.enabled.get(); s.keep_browser_open=self.keep_open.get(); s.save_session=self.save_session.get(); s.launch_adobe_connect=self.launch_adobe.get(); s.retry_count=int(self.entries["retry_count"].get() or 2); s.retry_delay_seconds=int(self.entries["retry_delay_seconds"].get() or 30); s.class_entry_timeout_seconds=int(self.entries["class_entry_timeout_seconds"].get() or 900); self.result=s; self.destroy()
