"""Schedule management frame separated from automation logic."""
from __future__ import annotations
import threading
from datetime import datetime, timedelta
from tkinter import END, messagebox
import customtkinter as ctk
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.scheduling.manager import ScheduleManager
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import actual_run_time, adjusted_weekday, convert_12h_to_24h, convert_24h_to_12h, format_12h, next_run_datetime, remaining_text
from src.scheduling.windows_task_scheduler import WindowsTaskScheduler
from src.scheduling.executor import ScheduleExecutor

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

class ScheduleFrame(ctk.CTkFrame):
    """Persian schedule form and list for fixed class cards with 12-hour UI."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master)
        self.manager = ScheduleManager(config_manager); self.logs = logs; self.selected_id = ""
        self.class_var = ctk.StringVar(value=CLASS_PRESETS[0].name); self.type_var = ctk.StringVar(value="weekly"); self.weekday_var = ctk.StringVar(value=CLASS_PRESETS[0].weekday)
        self.hour_var = ctk.StringVar(value="09"); self.minute_var = ctk.StringVar(value="15"); self.period_var = ctk.StringVar(value="AM")
        self.early_var = ctk.StringVar(value="5"); self.wait_var = ctk.StringVar(value="15"); self.adobe_wait_var = ctk.StringVar(value="20")
        self.launch_var = ctk.BooleanVar(value=True); self.keep_var = ctk.BooleanVar(value=True); self.enabled_var = ctk.BooleanVar(value=True)
        self.summary_var = ctk.StringVar(value=""); self.clock_var = ctk.StringVar(value="")
        self._build(); self.prefill_for_class(CLASS_PRESETS[0], log=False); self.refresh(); self._tick_clock()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="زمان‌بندی ورود خودکار به کلاس", font=("Tahoma",18,"bold"), anchor="e").pack(fill="x", pady=(8,4))
        form = ctk.CTkFrame(self); form.pack(fill="x", padx=8, pady=6)
        for i in range(4): form.grid_columnconfigure(i, weight=1)
        self.class_menu = ctk.CTkOptionMenu(form, variable=self.class_var, values=[p.name for p in CLASS_PRESETS], command=lambda _=None:self._update_summary())
        self.type_menu = ctk.CTkOptionMenu(form, variable=self.type_var, values=["once", "weekly"], command=lambda _=None:self._update_summary())
        self.weekday_menu = ctk.CTkOptionMenu(form, variable=self.weekday_var, values=WEEKDAYS, command=lambda _=None:self._update_summary())
        self.date_entry = ctk.CTkEntry(form, justify="right", placeholder_text="YYYY-MM-DD")
        for idx,(label,w) in enumerate([("کلاس",self.class_menu),("نوع",self.type_menu),("روز هفته",self.weekday_menu),("تاریخ",self.date_entry)]):
            ctk.CTkLabel(form,text=label,anchor="e").grid(row=(idx//2)*2,column=idx%2*2+1,sticky="e",padx=8,pady=(6,2)); w.grid(row=(idx//2)*2+1,column=idx%2*2,columnspan=2,sticky="ew",padx=8)
        ctk.CTkLabel(form,text="ساعت شروع کلاس",anchor="e").grid(row=4,column=3,sticky="e",padx=8,pady=(8,2))
        self.hour_menu=ctk.CTkComboBox(form,variable=self.hour_var,values=[f"{i:02d}" for i in range(1,13)],command=lambda _=None:self._update_summary(),width=70)
        self.minute_menu=ctk.CTkComboBox(form,variable=self.minute_var,values=[f"{i:02d}" for i in range(60)],command=lambda _=None:self._update_summary(),width=70)
        self.period_menu=ctk.CTkComboBox(form,variable=self.period_var,values=["AM","PM"],command=lambda _=None:self._update_summary(),width=70)
        time_box=ctk.CTkFrame(form); time_box.grid(row=5,column=2,columnspan=2,sticky="e",padx=8); self.period_menu.pack(side="right",padx=3); self.minute_menu.pack(side="right",padx=3); ctk.CTkLabel(time_box,text=":").pack(side="right"); self.hour_menu.pack(side="right",padx=3)
        ctk.CTkLabel(form,text="AM = قبل از ظهر | PM = بعد از ظهر\n12:00 PM = 12 ظهر | 12:00 AM = 12 شب",anchor="e",justify="right").grid(row=5,column=0,columnspan=2,sticky="e",padx=8)
        self.early_menu = ctk.CTkOptionMenu(form, variable=self.early_var, values=["0", "5", "10", "15"], command=lambda _=None:self._update_summary())
        self.wait_menu = ctk.CTkOptionMenu(form, variable=self.wait_var, values=["1", "5", "10", "15", "30"])
        self.adobe_wait_menu = ctk.CTkOptionMenu(form, variable=self.adobe_wait_var, values=["10", "20", "30", "60"])
        for col,(label,w) in enumerate([("ورود زودتر",self.early_menu),("حداکثر انتظار فعال‌شدن کلاس",self.wait_menu),("انتظار برای Adobe Connect",self.adobe_wait_menu)]):
            ctk.CTkLabel(form,text=label,anchor="e").grid(row=6,column=col+1,sticky="e",padx=8,pady=(8,2)); w.grid(row=7,column=col+1,sticky="ew",padx=8)
        ctk.CTkCheckBox(form,text="اجرای Adobe Connect",variable=self.launch_var).grid(row=8,column=3,sticky="e",padx=8,pady=8)
        ctk.CTkCheckBox(form,text="مرورگر باز بماند",variable=self.keep_var).grid(row=8,column=2,sticky="e",padx=8,pady=8)
        ctk.CTkCheckBox(form,text="زمان‌بندی فعال باشد",variable=self.enabled_var).grid(row=8,column=1,sticky="e",padx=8,pady=8)
        ctk.CTkLabel(form,text="زمان‌بندی براساس ساعت محلی این رایانه اجرا می‌شود.",anchor="e").grid(row=9,column=0,columnspan=4,sticky="e",padx=8)
        ctk.CTkLabel(form,textvariable=self.clock_var,anchor="e").grid(row=10,column=0,columnspan=4,sticky="e",padx=8)
        ctk.CTkLabel(form,textvariable=self.summary_var,anchor="e",justify="right",wraplength=760).grid(row=11,column=0,columnspan=4,sticky="ew",padx=8,pady=8)
        actions = ctk.CTkFrame(self); actions.pack(fill="x", padx=8, pady=6)
        for text,cmd in [("ذخیره زمان‌بندی",self.save),("ویرایش زمان‌بندی",self.edit_selected),("حذف زمان‌بندی",self.delete),("آزمایش زمان‌بندی در 2 دقیقه آینده",self.test_in_two_minutes),("بررسی Task ذخیره‌شده",self.verify_selected),("همگام‌سازی با ساعت Windows",self.sync_all),("اجرای آزمایشی همین حالا",self.run_now)]:
            ctk.CTkButton(actions,text=text,command=cmd).pack(side="right",padx=4,pady=4)
        self.list_frame = ctk.CTkFrame(self); self.list_frame.pack(fill="x", padx=8, pady=(4,10))

    def _tick_clock(self):
        self.clock_var.set(f"ساعت فعلی رایانه: {datetime.now().strftime('%I:%M %p')}"); self._update_summary(); self.after(60000, self._tick_clock)
    def _update_summary(self):
        try:
            start=convert_12h_to_24h(self.hour_var.get(), self.minute_var.get(), self.period_var.get()); run,off=actual_run_time(start,int(self.early_var.get())); run12=format_12h(run); start12=format_12h(start)
            if self.type_var.get()=="weekly": self.summary_var.set(f"این زمان‌بندی هر {adjusted_weekday(self.weekday_var.get(), off)} ساعت {run12} اجرا می‌شود تا برای کلاس {start12} آماده باشد. کلاس ساعت {start12} شروع می‌شود؛ ربات ساعت {run12} اجرا خواهد شد.")
            else: self.summary_var.set(f"این زمان‌بندی در تاریخ انتخاب‌شده ساعت {run12} اجرا می‌شود.")
        except Exception as exc: self.summary_var.set(str(exc))

    def prefill_for_class(self, preset: ClassPreset, log: bool=True) -> None:
        self.class_var.set(preset.name); self.weekday_var.set(preset.weekday); h,m,p=convert_24h_to_12h(preset.start_time); self.hour_var.set(h); self.minute_var.set(m); self.period_var.set(p); self._update_summary()
        if log: self.logs.log("زمان‌بندی انتخاب شد")
    def _schedule_from_form(self, temporary: bool=False) -> ClassSchedule | None:
        try:
            t=convert_12h_to_24h(self.hour_var.get(),self.minute_var.get(),self.period_var.get()); early=int(self.early_var.get()); run,_=actual_run_time(t,early)
            if not self.class_var.get(): raise ValueError("کلاس انتخاب نشده است.")
            if self.type_var.get()=="weekly" and not self.weekday_var.get(): raise ValueError("روز هفته برای زمان‌بندی هفتگی انتخاب نشده است.")
            if self.type_var.get()=="once" and next_run_datetime("once", self.weekday_var.get(), self.date_entry.get().strip(), t, early) <= datetime.now(): raise ValueError("تاریخ و ساعت زمان‌بندی یک‌بار در گذشته است.")
        except Exception as exc: self.logs.log(str(exc)); return None
        return ClassSchedule(id=self.selected_id or __import__('uuid').uuid4().hex, profile_id="vadana-sum39", class_name=self.class_var.get(), recurrence=self.type_var.get(), weekday=self.weekday_var.get(), date=self.date_entry.get().strip(), start_time=t, class_start_time=t, effective_run_time=run, task_time=run, early_minutes=early, class_entry_timeout_seconds=int(self.wait_var.get())*60, launch_adobe_connect=self.launch_var.get(), keep_browser_open=self.keep_var.get(), enabled=self.enabled_var.get(), adobe_launch_wait_seconds=int(self.adobe_wait_var.get()), temporary=temporary)
    def save(self) -> None:
        s=self._schedule_from_form();
        if not s: return
        r=WindowsTaskScheduler().register(s)
        if r.success or __import__('os').name != 'nt': self.manager.upsert(s); self.selected_id=s.id; self.logs.log("زمان‌بندی ذخیره شد"); self.refresh()
        self.logs.log("Windows Task ساخته و تأیید شد" if r.success else r.message)
    def refresh(self) -> None:
        for child in self.list_frame.winfo_children(): child.destroy()
        for s in self.manager.list():
            row=ctk.CTkFrame(self.list_frame); row.pack(fill="x",pady=4); row.bind("<Button-1>",lambda _e, sid=s.id: setattr(self,'selected_id',sid))
            run_time,_=actual_run_time(s.start_time,s.early_minutes)
            try: nxt=next_run_datetime(s.recurrence,s.weekday,s.date,s.start_time,s.early_minutes); next_txt=f"{format_12h(nxt.strftime('%H:%M'))}"; rem=remaining_text(nxt)
            except Exception: next_txt="نامعتبر"; rem="—"
            text=f"{s.class_name}\nشروع کلاس: {format_12h(s.start_time)} | اجرای ربات: {format_12h(run_time)} | اجرای بعدی: {s.weekday if s.recurrence=='weekly' else s.date}، {next_txt} | باقی‌مانده: {rem} | {'فعال' if s.enabled else 'غیرفعال'} | نتیجه: {s.last_run_status}"
            ctk.CTkLabel(row,text=text,justify="right",anchor="e",wraplength=720).pack(side="right",fill="x",expand=True,padx=6)
            for textb,cmd in [("ویرایش",lambda sid=s.id:self._load(sid)),("حذف",lambda sid=s.id:self._delete_id(sid)),("اجرای همین حالا",lambda sid=s.id:self._run_id(sid))]: ctk.CTkButton(row,text=textb,width=90,command=cmd).pack(side="left",padx=3)
    def _load(self,sid):
        s=self.manager.get(sid); self.selected_id=sid
        if not s: return
        h,m,p=convert_24h_to_12h(s.start_time); self.class_var.set(s.class_name); self.type_var.set(s.recurrence); self.weekday_var.set(s.weekday); self.date_entry.delete(0,END); self.date_entry.insert(0,s.date); self.hour_var.set(h); self.minute_var.set(m); self.period_var.set(p); self.early_var.set(str(s.early_minutes)); self.wait_var.set(str(s.wait_timeout_minutes)); self.launch_var.set(s.launch_adobe_connect); self.keep_var.set(s.keep_browser_open); self.enabled_var.set(s.enabled); self.adobe_wait_var.set(str(s.adobe_launch_wait_seconds)); self._update_summary()
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
    def test_in_two_minutes(self):
        due=datetime.now()+timedelta(minutes=2); h,m,p=convert_24h_to_12h(due.strftime('%H:%M')); self.hour_var.set(h); self.minute_var.set(m); self.period_var.set(p); self.type_var.set('once'); self.date_entry.delete(0,END); self.date_entry.insert(0,due.strftime('%Y-%m-%d')); s=self._schedule_from_form(temporary=True)
        if s: self.manager.upsert(s); self.selected_id=s.id; r=WindowsTaskScheduler().register(s); self.logs.log("Task آزمایشی دو دقیقه آینده ساخته شد" if r.success else r.message); self.refresh()
    def verify_selected(self):
        s=self.manager.get(self.selected_id)
        if s: self.logs.log(WindowsTaskScheduler().verify(s).message)
    def sync_all(self):
        for s in self.manager.list():
            if s.enabled: self.logs.log(WindowsTaskScheduler().register(s).message)
        self.refresh()
