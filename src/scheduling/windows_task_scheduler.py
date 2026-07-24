"""Safe Windows Task Scheduler wrapper using argument lists and XML import."""
from __future__ import annotations
import os, re, subprocess, sys, getpass
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree as ET
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import effective_run_datetime, shift_weekday

@dataclass(slots=True)
class TaskResult:
    success: bool
    message: str
    args: list[str]
    task_name: str = ""
    next_run_time: str = ""

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
XML_WEEKDAYS = {"شنبه":"Saturday", "یکشنبه":"Sunday", "دوشنبه":"Monday", "سه‌شنبه":"Tuesday", "چهارشنبه":"Wednesday", "پنجشنبه":"Thursday", "جمعه":"Friday"}

def sanitize_task_name(schedule_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", schedule_id)[:64] or "schedule"
    return f"WindowsClassBot_{safe}"

def project_root() -> str:
    return os.getcwd()

def build_run_command(schedule_id: str, executable: str | None = None, script: str | None = None) -> list[str]:
    root = project_root(); venv_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    exe = executable or (venv_python if os.path.exists(venv_python) else sys.executable)
    if getattr(sys, "frozen", False): return [exe, "--run-schedule", schedule_id]
    return [exe, script or os.path.join(root, "main.py"), "--run-schedule", schedule_id]

def build_task_xml(schedule: ClassSchedule) -> str:
    schedule.recalculate_effective_time()
    root = ET.Element("Task", {"version":"1.4", "xmlns":NS})
    reg = ET.SubElement(root,"RegistrationInfo"); ET.SubElement(reg,"Description").text = f"Windows Class Bot schedule {schedule.id}"
    triggers = ET.SubElement(root,"Triggers")
    if schedule.recurrence == "weekly":
        trig = ET.SubElement(triggers,"CalendarTrigger")
        ET.SubElement(trig,"StartBoundary").text = f"{datetime.now().date().isoformat()}T{schedule.effective_run_time}:00"
        ET.SubElement(trig,"Enabled").text = "true" if schedule.enabled else "false"
        weeks = ET.SubElement(ET.SubElement(trig,"ScheduleByWeek"),"DaysOfWeek")
        ET.SubElement(weeks, XML_WEEKDAYS[shift_weekday(schedule.weekday, schedule.effective_day_offset)]).text = ""
    else:
        class_day = datetime.fromisoformat(schedule.date).date() if schedule.date else datetime.now().date()
        run_dt = effective_run_datetime(class_day, schedule.start_time, schedule.early_minutes)
        trig = ET.SubElement(triggers,"CalendarTrigger"); ET.SubElement(trig,"StartBoundary").text = run_dt.isoformat(timespec="seconds"); ET.SubElement(trig,"Enabled").text = "true" if schedule.enabled else "false"
    principals = ET.SubElement(root,"Principals"); pr = ET.SubElement(principals,"Principal", {"id":"Author"})
    ET.SubElement(pr,"UserId").text = getpass.getuser(); ET.SubElement(pr,"LogonType").text = "InteractiveToken"; ET.SubElement(pr,"RunLevel").text = "LeastPrivilege"
    settings = ET.SubElement(root,"Settings")
    for tag, val in [("MultipleInstancesPolicy","IgnoreNew"),("DisallowStartIfOnBatteries","false"),("StopIfGoingOnBatteries","false"),("AllowHardTerminate","true"),("StartWhenAvailable","true"),("WakeToRun","true"),("Enabled","true"),("ExecutionTimeLimit","PT2H")]: ET.SubElement(settings,tag).text = val
    rs = ET.SubElement(settings,"RestartOnFailure"); ET.SubElement(rs,"Interval").text="PT1M"; ET.SubElement(rs,"Count").text="3"
    actions = ET.SubElement(root,"Actions", {"Context":"Author"}); ex = ET.SubElement(actions,"Exec")
    cmd = build_run_command(schedule.id); ET.SubElement(ex,"Command").text = cmd[0]; ET.SubElement(ex,"Arguments").text = " ".join(f'\"{p}\"' if ' ' in p else p for p in cmd[1:]); ET.SubElement(ex,"WorkingDirectory").text = project_root()
    return ET.tostring(root, encoding="unicode")

class WindowsTaskScheduler:
    def __init__(self, runner=subprocess.run) -> None: self.runner = runner
    def register(self, schedule: ClassSchedule) -> TaskResult:
        schedule.recalculate_effective_time(); task = sanitize_task_name(schedule.id)
        if os.name != "nt": return TaskResult(False, "ثبت Task فقط روی Windows قابل اجراست.", [], task, schedule.effective_run_time)
        xml = build_task_xml(schedule)
        args = ["schtasks.exe", "/Create", "/F", "/TN", task, "/XML", "-", "/IT"]
        c = self.runner(args, input=xml, capture_output=True, text=True, check=False)
        ok = c.returncode == 0
        if ok:
            v = self.verify(schedule); ok = v.success; msg = v.message
        else: msg = c.stderr.strip() or c.stdout.strip() or "Task ثبت نشد."
        return TaskResult(ok, msg, args + ["--", schedule.effective_run_time, "--run-schedule", schedule.id], task, schedule.effective_run_time)
    def verify(self, schedule: ClassSchedule) -> TaskResult:
        schedule.recalculate_effective_time(); task=sanitize_task_name(schedule.id); cmd = build_run_command(schedule.id)
        if os.name != "nt": return TaskResult(False, "بررسی Task فقط روی Windows قابل اجراست.", [], task, schedule.effective_run_time)
        args=["schtasks.exe","/Query","/TN",task,"/V","/FO","LIST"]
        c=self.runner(args,capture_output=True,text=True,check=False); out=(c.stdout or '')+(c.stderr or '')
        ok=c.returncode==0 and schedule.id in ' '.join(cmd) and "--run-schedule" in ' '.join(cmd)
        return TaskResult(ok, out.strip() or ("Task معتبر است" if ok else "Task معتبر نیست"), args, task, schedule.effective_run_time)
    def delete(self, schedule_id: str) -> TaskResult:
        task=sanitize_task_name(schedule_id)
        if os.name != "nt": return TaskResult(False, "حذف Task فقط روی Windows قابل اجراست.", [], task)
        args=["schtasks.exe","/Delete","/F","/TN",task]; c=self.runner(args,capture_output=True,text=True,check=False)
        return TaskResult(c.returncode==0, c.stderr.strip() or c.stdout.strip() or "Task حذف شد.", args, task)
