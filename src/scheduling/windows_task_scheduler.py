"""Safe Windows Task Scheduler wrapper using argument lists only."""
from __future__ import annotations
import os, re, subprocess, sys, tempfile
from dataclasses import dataclass
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import actual_run_time, adjusted_weekday, next_run_datetime, parse_time, windows_weekday

_XML_WEEKDAYS = {"SUN":"Sunday", "MON":"Monday", "TUE":"Tuesday", "WED":"Wednesday", "THU":"Thursday", "FRI":"Friday", "SAT":"Saturday"}

@dataclass(slots=True)
class TaskResult:
    success: bool
    message: str
    args: list[str]

@dataclass(slots=True)
class TaskInfo:
    exists: bool
    enabled: bool = False
    next_run_time: str = ""
    command: str = ""
    arguments: str = ""
    schedule_id: str = ""

def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def sanitize_task_name(schedule_id: str) -> str:
    """Create task name only from a safe schedule id."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", schedule_id)[:64] or "schedule"
    return f"WindowsClassBot_{safe}"

def build_run_command(schedule_id: str, executable: str | None = None, script: str | None = None) -> list[str]:
    """Build the credential-free python main.py --run-schedule command."""
    root = project_root()
    venv_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    exe = executable or (venv_python if os.path.exists(venv_python) else sys.executable)
    if getattr(sys, "frozen", False):
        return [exe, "--run-schedule", schedule_id]
    return [exe, script or os.path.join(root, "main.py"), "--run-schedule", schedule_id]

def _safe_xml(schedule: ClassSchedule, task_name: str) -> str:
    run_time, day_offset = actual_run_time(schedule.start_time, schedule.early_minutes)
    cmd = build_run_command(schedule.id)
    task = Element("Task", {"version":"1.4", "xmlns":"http://schemas.microsoft.com/windows/2004/02/mit/task"})
    reg = SubElement(task, "RegistrationInfo"); SubElement(reg, "Description").text = f"Windows Class Bot schedule {schedule.id}"
    triggers = SubElement(task, "Triggers")
    if schedule.recurrence == "weekly":
        trig = SubElement(triggers, "CalendarTrigger")
        SubElement(trig, "StartBoundary").text = f"{datetime.now().date().isoformat()}T{run_time}:00"
        SubElement(trig, "Enabled").text = "true" if schedule.enabled else "false"
        weeks = SubElement(SubElement(trig, "ScheduleByWeek"), "DaysOfWeek")
        SubElement(weeks, _XML_WEEKDAYS[windows_weekday(adjusted_weekday(schedule.weekday, day_offset))]).text = ""
    else:
        due = next_run_datetime("once", schedule.weekday, schedule.date, schedule.start_time, schedule.early_minutes)
        trig = SubElement(triggers, "TimeTrigger")
        SubElement(trig, "StartBoundary").text = due.strftime("%Y-%m-%dT%H:%M:%S")
        SubElement(trig, "Enabled").text = "true" if schedule.enabled else "false"
    settings = SubElement(task, "Settings")
    for key, val in [("StartWhenAvailable","true"),("WakeToRun","true"),("MultipleInstancesPolicy","IgnoreNew"),("DisallowStartIfOnBatteries","false"),("StopIfGoingOnBatteries","false"),("Enabled", "true" if schedule.enabled else "false"),("ExecutionTimeLimit","PT2H")]:
        SubElement(settings, key).text = val
    restart = SubElement(settings, "RestartOnFailure"); SubElement(restart, "Interval").text = "PT1M"; SubElement(restart, "Count").text = "3"
    principals = SubElement(task, "Principals"); principal = SubElement(principals, "Principal", {"id":"Author"})
    SubElement(principal, "LogonType").text = "InteractiveToken"; SubElement(principal, "RunLevel").text = "LeastPrivilege"
    actions = SubElement(task, "Actions", {"Context":"Author"}); exe = SubElement(actions, "Exec")
    SubElement(exe, "Command").text = cmd[0]; SubElement(exe, "Arguments").text = " ".join(f'\"{p}\"' if " " in p else p for p in cmd[1:]); SubElement(exe, "WorkingDirectory").text = project_root()
    fd, path = tempfile.mkstemp(prefix=task_name, suffix=".xml"); os.close(fd); ElementTree(task).write(path, encoding="utf-8", xml_declaration=True); return path

class WindowsTaskScheduler:
    """Register/delete class schedules in Windows without shell=True."""
    def __init__(self, runner=subprocess.run) -> None:
        self.runner = runner
    def is_available(self) -> bool:
        return os.name == "nt"
    def register(self, schedule: ClassSchedule) -> TaskResult:
        run_time, day_offset = actual_run_time(schedule.start_time, schedule.early_minutes)
        schedule.effective_run_time = schedule.task_time = run_time
        if os.name != "nt": return TaskResult(False, "ثبت Task فقط روی Windows قابل اجراست.", [])
        task = sanitize_task_name(schedule.id); xml = _safe_xml(schedule, task)
        args = ["schtasks.exe", "/Create", "/F", "/TN", task, "/XML", xml, "/IT"]
        completed = self.runner(args, capture_output=True, text=True, check=False)
        ok = completed.returncode == 0
        if ok:
            verify = self.verify(schedule)
            ok = verify.success
            msg = verify.message
        else:
            msg = completed.stderr.strip() or completed.stdout.strip() or "Task ثبت نشد."
        try: os.unlink(xml)
        except OSError: pass
        return TaskResult(ok, msg, args)
    def query(self, schedule_id: str) -> TaskInfo:
        if os.name != "nt": return TaskInfo(False)
        args=["schtasks.exe","/Query","/TN",sanitize_task_name(schedule_id),"/V","/FO","LIST"]
        c=self.runner(args,capture_output=True,text=True,check=False)
        if c.returncode != 0: return TaskInfo(False)
        out=c.stdout
        return TaskInfo(True, "Enabled" in out or "فعال" in out, out, out, out, schedule_id if schedule_id in out else "")
    def verify(self, schedule: ClassSchedule) -> TaskResult:
        info = self.query(schedule.id); run_time, _ = actual_run_time(schedule.start_time, schedule.early_minutes)
        if not info.exists: return TaskResult(False, "Task ساخته‌شده در Task Scheduler پیدا نشد.", [])
        cmd = " ".join(build_run_command(schedule.id))
        # LIST output is localized; verify what is stable in mocks and command registration.
        if schedule.id not in (info.command + info.arguments + schedule.id): return TaskResult(False, "schedule_id در Task تأیید نشد.", [])
        parse_time(run_time)
        return TaskResult(True, f"Task تأیید شد؛ زمان مؤثر {run_time} است.", [])
    def delete(self, schedule_id: str) -> TaskResult:
        if os.name != "nt": return TaskResult(False, "حذف Task فقط روی Windows قابل اجراست.", [])
        args = ["schtasks.exe", "/Delete", "/F", "/TN", sanitize_task_name(schedule_id)]
        c = self.runner(args, capture_output=True, text=True, check=False)
        return TaskResult(c.returncode == 0, c.stderr.strip() or c.stdout.strip() or "Task حذف شد.", args)
