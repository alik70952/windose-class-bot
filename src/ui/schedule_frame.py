"""Schedule management frame separated from automation logic."""
from __future__ import annotations
import threading
from datetime import datetime, timedelta
from tkinter import END, messagebox
import customtkinter as ctk
from src.classes.presets import CLASS_PRESETS, ClassPreset
from src.scheduling.manager import ScheduleManager
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import convert_12h_to_24h, convert_24h_to_12h, effective_for_date, effective_for_weekday, format_12h, next_run_datetime, remaining_text
from src.scheduling.windows_task_scheduler import WindowsTaskScheduler
from src.scheduling.executor import ScheduleExecutor

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

class ScheduleFrame(ctk.CTkFrame):
    """Persian 12-hour schedule form and list for the three fixed class cards."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master); self.manager=ScheduleManager(config_manager); self.logs=logs; self.selected_id=""
        self.class_var=ctk.StringVar(value=CLASS_PRESETS[0].name); self.type_var=ctk.StringVar(value="weekly"); self.weekday_var=ctk.StringVar(value=CLASS_PRESETS[0].weekday)
        self.hour_var=ctk.StringVar(value="09"); self.minute_var=ctk.StringVar(value="15"); self.period_var=ctk.StringVar(value="AM")
        self.early_var=ctk.StringVar(value="5"); self.wait_var=ctk.StringVar(value="15"); self.late_var=ctk.StringVar(value="15"); self.adobe_wait_var=ctk.StringVar(value="20")
        self.launch_var=ctk.BooleanVar(value=True); self.keep_var=ctk.BooleanVar(value=True); self.enabled_var=ctk.BooleanVar(value=True)
        self._build(); self.prefill_for_class(CLASS_PRESETS[0], log=False); self.refresh(); self._tick_clock()
    def _build(self):
        ctk.CTkLabel(self,text="زمان‌بندی ورود خودکار به کلاس",font=("Tahoma",18,"bold"),anchor="e").pack(fill="x",pady=(8,4))
        self.clock_label=ctk.CTkLabel(self,text="زمان‌بندی براساس ساعت محلی این رایانه اجرا می‌شود.",anchor="e"); self.clock_label.pack(fill="x",padx=8)
        ctk.CTkLabel(self,text="AM = قبل از ظهر | PM = بعد از ظهر | 12:00 PM = 12 ظهر | 12:00 AM = 12 شب | 01:30 PM = 1:30 بعدازظهر | 09:15 AM = 9:15 صبح",anchor="e",wraplength=760).pack(fill="x",padx=8)
        form=ctk.CTkFrame(self); form.pack(fill="x",padx=8,pady=6)
        for i in range(4): form.grid_columnconfigure(i,weight=1)
        self.class_menu=ctk.CTkOptionMenu(form,variable=self.class_var,values=[p.name for p in CLASS_PRESETS],command=lambda _v:self._update_summary())
        self.type_menu=ctk.CTkOptionMenu(form,variable=self.type_var,values=["once","weekly"],command=lambda _v:self._update_summary())
        self.weekday_menu=ctk.CTkOptionMenu(form,variable=self.weekday_var,values=WEEKDAYS,command=lambda _v:self._update_summary())
        self.date_entry=ctk.CTkEntry(form,justify="right",placeholder_text="YYYY-MM-DD")
        self.hour_menu=ctk.CTkOptionMenu(form,variable=self.hour_var,values=[f"{i:02d}" for i in range(1,13)],command=lambda _v:self._update_summary())
        self.minute_menu=ctk.CTkOptionMenu(form,variable=self.minute_var,values=[f"{i:02d}" for i in range(60)],command=lambda _v:self._update_summary())
        self.period_menu=ctk.CTkOptionMenu(form,variable=self.period_var,values=["AM","PM"],command=lambda _v:self._update_summary())
        for idx,(label,w) in enumerate([("کلاس",self.class_menu),("نوع زمان‌بندی",self.type_menu),("روز هفته",self.weekday_menu),("تاریخ فقط یک‌بار",self.date_entry)]):
            ctk.CTkLabel(form,text=label,anchor="e").grid(row=(idx//2)*2,column=idx%2*2+1,sticky="e",padx=8,pady=(6,2)); w.grid(row=(idx//2)*2+1,column=idx%2*2,columnspan=2,sticky="ew",padx=8)
        ctk.CTkLabel(form,text="ساعت شروع کلاس",anchor="e").grid(row=4,column=3,sticky="e",padx=8,pady=(8,2)); self.hour_menu.grid(row=5,column=3,sticky="ew",padx=4); self.minute_menu.grid(row=5,column=2,sticky="ew",padx=4); self.period_menu.grid(row=5,column=1,sticky="ew",padx=4)
        self.early_menu=ctk.CTkOptionMenu(form,variable=self.early_var,values=["0","5","10","15"],command=lambda _v:self._update_summary())
        self.wait_menu=ctk.CTkOptionMenu(form,variable=self.wait_var,values=["1","5","10","15","30"]); self.adobe_wait_menu=ctk.CTkOptionMenu(form,variable=self.adobe_wait_var,values=["10","20","30","60"]); self.late_menu=ctk.CTkOptionMenu(form,variable=self.late_var,values=["5","10","15","30"])
        for col,(label,w) in enumerate([("ورود زودتر",self.early_menu),("حداکثر انتظار لینک (دقیقه)",self.wait_menu),("انتظار Adobe (ثانیه)",self.adobe_wait_menu),("حداکثر تأخیر مجاز (دقیقه)",self.late_menu)]):
            ctk.CTkLabel(form,text=label,anchor="e").grid(row=6,column=col,sticky="e",padx=8,pady=(8,2)); w.grid(row=7,column=col,sticky="ew",padx=8)
        ctk.CTkCheckBox(form,text="اجرای Adobe Connect",variable=self.launch_var).grid(row=8,column=3,sticky="e",padx=8,pady=8); ctk.CTkCheckBox(form,text="مرورگر باز بماند",variable=self.keep_var).grid(row=8,column=2,sticky="e",padx=8,pady=8); ctk.CTkCheckBox(form,text="زمان‌بندی فعال باشد",variable=self.enabled_var).grid(row=8,column=1,sticky="e",padx=8,pady=8)
        self.summary_label=ctk.CTkLabel(self,text="",anchor="e",wraplength=760); self.summary_label.pack(fill="x",padx=8,pady=4)
        actions=ctk.CTkFrame(self); actions.pack(fill="x",padx=8,pady=6)
        for text,cmd in [("ذخیره زمان‌بندی",self.save),("ویرایش زمان‌بندی",self.edit_selected),("حذف زمان‌بندی",self.delete),("فعال/غیرفعال‌کردن",self.toggle),("اجرای همین حالا",self.run_now),("بررسی Task ذخیره‌شده",self.verify_task),("همگام‌سازی با ساعت Windows",self.sync_windows_time),("آزمایش زمان‌بندی در 2 دقیقه آینده",self.test_in_two_minutes)]: ctk.CTkButton(actions,text=text,command=cmd).pack(side="right",padx=3,pady=4)
        self.list_frame=ctk.CTkFrame(self); self.list_frame.pack(fill="x",padx=8,pady=(4,10))
    def _tick_clock(self):
        self.clock_label.configure(text=f"زمان‌بندی براساس ساعت محلی این رایانه اجرا می‌شود. ساعت فعلی رایانه: {datetime.now().strftime('%I:%M %p')}"); self.after(30000,self._tick_clock)
    def _update_summary(self):
        try:
            start=convert_12h_to_24h(self.hour_var.get(),self.minute_var.get(),self.period_var.get()); run,_=__import__('src.scheduling.time_utils',fromlist=['actual_run_time']).actual_run_time(start,int(self.early_var.get()))
            self.summary_label.configure(text=(f"کلاس و ربات ساعت {format_12h(start)} اجرا می‌شوند." if int(self.early_var.get())==0 else f"کلاس ساعت {format_12h(start)} شروع می‌شود و ربات ساعت {format_12h(run)} اجرا خواهد شد."))
        except Exception as exc: self.summary_label.configure(text=str(exc))
    def prefill_for_class(self,preset:ClassPreset,log:bool=True):
        self.class_var.set(preset.name); self.weekday_var.set(preset.weekday); h,m,p=convert_24h_to_12h(preset.start_time); self.hour_var.set(h); self.minute_var.set(m); self.period_var.set(p); self._update_summary(); self.update_idletasks()
        if log: self.logs.log("کلاس در فرم زمان‌بندی انتخاب شد")
    def _schedule_from_form(self):
        try: start=convert_12h_to_24h(self.hour_var.get(),self.minute_var.get(),self.period_var.get())
        except ValueError as exc: self.logs.log(str(exc)); return None
        s=ClassSchedule(id=self.selected_id or __import__('uuid').uuid4().hex, profile_id="vadana-sum39", class_name=self.class_var.get(), recurrence=self.type_var.get(), weekday=self.weekday_var.get(), date=self.date_entry.get().strip(), start_time=start, class_start_time=start, early_minutes=int(self.early_var.get()), class_entry_timeout_seconds=int(self.wait_var.get())*60, launch_adobe_connect=self.launch_var.get(), keep_browser_open=self.keep_var.get(), enabled=self.enabled_var.get(), adobe_launch_wait_seconds=int(self.adobe_wait_var.get()), max_late_start_minutes=int(self.late_var.get()))
        if s.recurrence=="weekly": s.effective_run_time,s.effective_run_weekday=effective_for_weekday(s.weekday,start,s.early_minutes)
        else: s.effective_run_time,s.effective_run_date=effective_for_date(s.date,start,s.early_minutes)
        s.next_run=next_run_datetime(s).isoformat(timespec="seconds"); return s
    def save(self):
        s=self._schedule_from_form();
        if not s: return
        self.manager.upsert(s); self.selected_id=s.id; r=WindowsTaskScheduler().register(s); self.logs.log("Windows Task ساخته شد" if r.success else r.message); self.refresh()
    def refresh(self):
        for child in self.list_frame.winfo_children(): child.destroy()
        for s in self.manager.list():
            row=ctk.CTkFrame(self.list_frame); row.pack(fill="x",pady=4); row.bind("<Button-1>",lambda _e,sid=s.id:setattr(self,'selected_id',sid))
            nr=next_run_datetime(s); text=f"{s.class_name}\nشروع کلاس: {format_12h(s.class_start_time or s.start_time)} | اجرای ربات: {format_12h(s.effective_run_time)} | {'هفتگی' if s.recurrence=='weekly' else 'فقط یک‌بار'} | {s.effective_run_weekday or s.effective_run_date or s.weekday or s.date} | {'فعال' if s.enabled else 'غیرفعال'} | اجرای بعدی: {nr.strftime('%Y-%m-%d %I:%M %p')} | زمان باقی‌مانده: {remaining_text(nr)} | آخرین اجرا: {s.last_run_at or '—'} | نتیجه: {s.last_run_status}"
            ctk.CTkLabel(row,text=text,justify="right",anchor="e",wraplength=760).pack(side="right",fill="x",expand=True,padx=6)
    def _load(self,sid):
        s=self.manager.get(sid); self.selected_id=sid
        if s: self.class_var.set(s.class_name); self.type_var.set(s.recurrence); self.weekday_var.set(s.weekday); self.date_entry.delete(0,END); self.date_entry.insert(0,s.date); h,m,p=convert_24h_to_12h(s.class_start_time or s.start_time); self.hour_var.set(h); self.minute_var.set(m); self.period_var.set(p); self.early_var.set(str(s.early_minutes)); self.wait_var.set(str(s.wait_timeout_minutes)); self.launch_var.set(s.launch_adobe_connect); self.keep_var.set(s.keep_browser_open); self.enabled_var.set(s.enabled); self.adobe_wait_var.set(str(s.adobe_launch_wait_seconds)); self.late_var.set(str(s.max_late_start_minutes)); self._update_summary()
    def edit_selected(self):
        if self.selected_id: self._load(self.selected_id)
    def delete(self):
        if self.selected_id: self.manager.delete(self.selected_id); WindowsTaskScheduler().delete(self.selected_id); self.selected_id=""; self.refresh()
    def toggle(self):
        s=self.manager.get(self.selected_id)
        if s: s.enabled=not s.enabled; self.manager.upsert(s); WindowsTaskScheduler().register(s); self.refresh()
    def run_now(self):
        if self.selected_id and messagebox.askyesno("تأیید","اجرای دستی روز و ساعت زمان‌بندی را نادیده می‌گیرد. ادامه می‌دهید؟"): threading.Thread(target=ScheduleExecutor(log=self.logs.log).run,args=(self.selected_id,),daemon=True).start()
    def verify_task(self):
        s=self.manager.get(self.selected_id); self.logs.log(WindowsTaskScheduler().verify(s).message if s else "زمان‌بندی انتخاب نشده است.")
    def sync_windows_time(self):
        for s in self.manager.list():
            if s.enabled: WindowsTaskScheduler().register(s)
        self.logs.log("همگام‌سازی با ساعت محلی Windows انجام شد.")
    def test_in_two_minutes(self):
        s=self._schedule_from_form();
        if not s: return
        when=datetime.now()+timedelta(minutes=2); s.id="test_"+s.id; s.test_schedule=True; s.recurrence="once"; s.date=when.date().isoformat(); s.class_start_time=when.strftime('%H:%M'); s.early_minutes=0; s.effective_run_time=s.class_start_time; s.effective_run_date=s.date; self.manager.upsert(s); self.logs.log(WindowsTaskScheduler().register(s).message); self.refresh()
