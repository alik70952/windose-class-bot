"""Schedule management frame separated from automation logic."""
from __future__ import annotations
import threading
from tkinter import END, messagebox
import customtkinter as ctk
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.scheduling.manager import ScheduleManager
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import actual_run_time, validate_time
from src.scheduling.windows_task_scheduler import WindowsTaskScheduler
from src.scheduling.executor import ScheduleExecutor

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

class ScheduleFrame(ctk.CTkFrame):
    """Persian schedule form and list for the three fixed class cards."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master)
        self.manager = ScheduleManager(config_manager); self.logs = logs; self.selected_id = ""
        self.class_var = ctk.StringVar(value=CLASS_PRESETS[0].name)
        self.type_var = ctk.StringVar(value="weekly"); self.weekday_var = ctk.StringVar(value=CLASS_PRESETS[0].weekday)
        self.early_var = ctk.StringVar(value="5"); self.wait_var = ctk.StringVar(value="15")
        self.launch_var = ctk.BooleanVar(value=True); self.keep_var = ctk.BooleanVar(value=True); self.enabled_var = ctk.BooleanVar(value=True)
        self.adobe_wait_var = ctk.StringVar(value="20")
        self._build(); self.prefill_for_class(CLASS_PRESETS[0], log=False); self.refresh()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="زمان‌بندی ورود خودکار به کلاس", font=("Tahoma",18,"bold"), anchor="e").pack(fill="x", pady=(8,4))
        form = ctk.CTkFrame(self); form.pack(fill="x", padx=8, pady=6)
        for i in range(4): form.grid_columnconfigure(i, weight=1)
        self.class_menu = ctk.CTkOptionMenu(form, variable=self.class_var, values=[p.name for p in CLASS_PRESETS])
        self.type_menu = ctk.CTkOptionMenu(form, variable=self.type_var, values=["once", "weekly"])
        self.weekday_menu = ctk.CTkOptionMenu(form, variable=self.weekday_var, values=WEEKDAYS)
        self.date_entry = ctk.CTkEntry(form, justify="right", placeholder_text="YYYY-MM-DD")
        self.time_entry = ctk.CTkEntry(form, justify="right")
        widgets = [("انتخاب کلاس", self.class_menu),("نوع زمان‌بندی", self.type_menu),("روز هفته", self.weekday_menu),("تاریخ یک‌بار", self.date_entry),("ساعت ورود HH:MM", self.time_entry)]
        for idx,(label,w) in enumerate(widgets):
            ctk.CTkLabel(form,text=label,anchor="e").grid(row=(idx//2)*2,column=idx%2*2+1,sticky="e",padx=8,pady=(6,2)); w.grid(row=(idx//2)*2+1,column=idx%2*2,columnspan=2,sticky="ew",padx=8)
        self.early_menu = ctk.CTkOptionMenu(form, variable=self.early_var, values=["0", "5", "10", "15"])
        self.wait_menu = ctk.CTkOptionMenu(form, variable=self.wait_var, values=["1", "5", "10", "15", "30"])
        self.adobe_wait_menu = ctk.CTkOptionMenu(form, variable=self.adobe_wait_var, values=["10", "20", "30", "60"])
        for col,(label,w) in enumerate([("چند دقیقه زودتر",self.early_menu),("حداکثر انتظار لینک (دقیقه)",self.wait_menu),("مدت انتظار اجرای Adobe (ثانیه)",self.adobe_wait_menu)]):
            ctk.CTkLabel(form,text=label,anchor="e").grid(row=6,column=col,sticky="e",padx=8,pady=(8,2)); w.grid(row=7,column=col,sticky="ew",padx=8)
        ctk.CTkCheckBox(form,text="پس از ورود، Adobe Connect اجرا شود",variable=self.launch_var).grid(row=8,column=3,sticky="e",padx=8,pady=8)
        ctk.CTkCheckBox(form,text="بعد از اجرای Adobe Connect مرورگر باز بماند",variable=self.keep_var).grid(row=8,column=2,sticky="e",padx=8,pady=8)
        ctk.CTkCheckBox(form,text="فعال",variable=self.enabled_var).grid(row=8,column=1,sticky="e",padx=8,pady=8)
        actions = ctk.CTkFrame(self); actions.pack(fill="x", padx=8, pady=6)
        for text,cmd in [("ذخیره زمان‌بندی",self.save),("ویرایش زمان‌بندی",self.edit_selected),("حذف زمان‌بندی",self.delete),("فعال/غیرفعال کردن",self.toggle),("اجرای آزمایشی همین حالا",self.run_now)]:
            ctk.CTkButton(actions,text=text,command=cmd).pack(side="right",padx=4,pady=4)
        self.list_frame = ctk.CTkFrame(self); self.list_frame.pack(fill="x", padx=8, pady=(4,10))

    def prefill_for_class(self, preset: ClassPreset, log: bool=True) -> None:
        self.class_var.set(preset.name); self.weekday_var.set(preset.weekday); self.time_entry.delete(0,END); self.time_entry.insert(0,preset.start_time)
        if log: self.logs.log("زمان‌بندی انتخاب شد")

    def _schedule_from_form(self) -> ClassSchedule | None:
        t = self.time_entry.get().strip()
        if not validate_time(t): self.logs.log("ساعت HH:MM معتبر نیست."); return None
        return ClassSchedule(id=self.selected_id or __import__('uuid').uuid4().hex, profile_id="vadana-sum39", class_name=self.class_var.get(), recurrence=self.type_var.get(), weekday=self.weekday_var.get(), date=self.date_entry.get().strip(), start_time=t, early_minutes=int(self.early_var.get()), class_entry_timeout_seconds=int(self.wait_var.get())*60, launch_adobe_connect=self.launch_var.get(), keep_browser_open=self.keep_var.get(), enabled=self.enabled_var.get(), adobe_launch_wait_seconds=int(self.adobe_wait_var.get()))

    def save(self) -> None:
        s = self._schedule_from_form()
        if not s: return
        self.manager.upsert(s); self.selected_id=s.id; self.logs.log("زمان‌بندی ذخیره شد"); self.refresh()
        r=WindowsTaskScheduler().register(s); self.logs.log("Windows Task ساخته شد" if r.success else r.message)

    def refresh(self) -> None:
        for child in self.list_frame.winfo_children(): child.destroy()
        for s in self.manager.list():
            row=ctk.CTkFrame(self.list_frame); row.pack(fill="x",pady=4); row.bind("<Button-1>",lambda _e, sid=s.id: setattr(self,'selected_id',sid))
            run_time,_=actual_run_time(s.start_time,s.early_minutes)
            text=f"{s.class_name}\n{'هفتگی' if s.recurrence=='weekly' else 'فقط یک‌بار'} | {s.weekday if s.recurrence=='weekly' else s.date} | اجرا: {run_time} | زودتر: {s.early_minutes} | {'فعال' if s.enabled else 'غیرفعال'} | آخرین اجرا: {s.last_run_at or '—'} | نتیجه: {s.last_run_status} | اجرای بعدی: {run_time}"
            ctk.CTkLabel(row,text=text,justify="right",anchor="e",wraplength=560).pack(side="right",fill="x",expand=True,padx=6)
            for textb,cmd in [("ویرایش",lambda sid=s.id:self._load(sid)),("حذف",lambda sid=s.id:self._delete_id(sid)),("اجرای همین حالا",lambda sid=s.id:self._run_id(sid))]: ctk.CTkButton(row,text=textb,width=90,command=cmd).pack(side="left",padx=3)

    def _load(self,sid):
        s=self.manager.get(sid); self.selected_id=sid
        if not s: return
        self.class_var.set(s.class_name); self.type_var.set(s.recurrence); self.weekday_var.set(s.weekday); self.date_entry.delete(0,END); self.date_entry.insert(0,s.date); self.time_entry.delete(0,END); self.time_entry.insert(0,s.start_time); self.early_var.set(str(s.early_minutes)); self.wait_var.set(str(s.wait_timeout_minutes)); self.launch_var.set(s.launch_adobe_connect); self.keep_var.set(s.keep_browser_open); self.enabled_var.set(s.enabled); self.adobe_wait_var.set(str(s.adobe_launch_wait_seconds))
    def edit_selected(self):
        if self.selected_id: self._load(self.selected_id)
    def delete(self):
        if self.selected_id: self._delete_id(self.selected_id)
    def _delete_id(self,sid): self.manager.delete(sid); WindowsTaskScheduler().delete(sid); self.selected_id=""; self.refresh()
    def toggle(self):
        s=self.manager.get(self.selected_id)
        if s: s.enabled=not s.enabled; self.manager.upsert(s); WindowsTaskScheduler().register(s); self.refresh()
    def run_now(self):
        if self.selected_id: self._run_id(self.selected_id)
    def _run_id(self,sid):
        if messagebox.askyesno("تأیید", "اجرای دستی روز و ساعت زمان‌بندی را نادیده می‌گیرد. ادامه می‌دهید؟"):
            threading.Thread(target=ScheduleExecutor(log=self.logs.log).run,args=(sid,),daemon=True).start()
