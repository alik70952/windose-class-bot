"""Schedule management frame separated from automation logic."""
from __future__ import annotations
import threading
from tkinter import messagebox
import customtkinter as ctk
from src.scheduling.manager import ScheduleManager
from src.scheduling.time_utils import actual_run_time
from src.scheduling.windows_task_scheduler import WindowsTaskScheduler
from src.scheduling.executor import ScheduleExecutor

class ScheduleFrame(ctk.CTkFrame):
    """Persian schedule list/actions UI."""
    def __init__(self, master, config_manager, logs) -> None:
        super().__init__(master); self.manager=ScheduleManager(config_manager); self.logs=logs; self.selected_id=""; self._build(); self.refresh()
    def _build(self) -> None:
        ctk.CTkLabel(self,text="زمان‌بندی کلاس‌ها",font=("Tahoma",18,"bold"),anchor="e").pack(fill="x",pady=8)
        self.box=ctk.CTkTextbox(self,height=150); self.box.pack(fill="both",expand=True,padx=8)
        actions=ctk.CTkFrame(self); actions.pack(fill="x",pady=6)
        for text,cmd in [("افزودن زمان‌بندی",self.add),("ویرایش زمان‌بندی",self.refresh),("حذف زمان‌بندی",self.delete),("فعال یا غیرفعال‌کردن",self.toggle),("اجرای آزمایشی همین حالا",self.run_now),("ورود به کلاس انتخاب‌شده",self.run_now),("ثبت در Windows Task Scheduler",self.register_task),("حذف از Windows Task Scheduler",self.delete_task),("تازه‌سازی وضعیت",self.refresh),("مشاهده Log",lambda:None)]: ctk.CTkButton(actions,text=text,command=cmd).pack(side="right",padx=3)
    def refresh(self) -> None:
        self.box.configure(state="normal"); self.box.delete("1.0","end")
        for s in self.manager.list():
            rt,off=actual_run_time(s.start_time,s.early_minutes); self.selected_id=self.selected_id or s.id
            self.box.insert("end", f"{s.id[:8]} | {'فعال' if s.enabled else 'غیرفعال'} | {s.class_name} | {s.weekday} | {s.start_time} | {s.early_minutes} دقیقه | {rt}{' روز قبل' if off<0 else ''} | {s.recurrence} | {s.last_run_at} | {s.last_run_status}\n")
        self.box.configure(state="disabled")
    def add(self) -> None: self.logs.log("برای افزودن کامل، از Dialog زمان‌بندی استفاده می‌شود.")
    def delete(self) -> None:
        if self.selected_id: self.manager.delete(self.selected_id); self.selected_id=""; self.refresh()
    def toggle(self) -> None:
        s=self.manager.get(self.selected_id)
        if s: s.enabled=not s.enabled; self.manager.upsert(s); self.refresh()
    def run_now(self) -> None:
        if not self.selected_id: return
        if not messagebox.askyesno("تأیید", "ربات همین حالا تلاش می‌کند وارد کلاس انتخاب‌شده شود. ادامه می‌دهید؟"): return
        threading.Thread(target=ScheduleExecutor(log=self.logs.log).run,args=(self.selected_id,),daemon=True).start()
    def register_task(self) -> None:
        s=self.manager.get(self.selected_id)
        if s: r=WindowsTaskScheduler().register(s); self.logs.log(r.message)
    def delete_task(self) -> None:
        if self.selected_id: self.logs.log(WindowsTaskScheduler().delete(self.selected_id).message)
