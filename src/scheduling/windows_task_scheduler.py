"""Safe Windows Task Scheduler wrapper using XML and argument lists only."""
from __future__ import annotations
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import effective_for_date, effective_for_weekday, next_run_datetime, windows_weekday

@dataclass(slots=True)
class TaskResult:
    success: bool; message: str; args: list[str]; task_xml: str = ""

def is_windows() -> bool: return sys.platform == "win32"
def project_root() -> Path: return Path(__file__).resolve().parents[2]
def sanitize_task_name(schedule_id: str) -> str:
    return f"WindowsClassBot_{(re.sub(r'[^A-Za-z0-9_-]', '_', schedule_id)[:64] or 'schedule')}"
def build_run_command(schedule_id: str, executable: str | None = None, script: str | None = None) -> list[str]:
    """Build the direct, console-free scheduled-runner action.

    ``pythonw.exe`` is intentional: using python.exe/main.py made Task Scheduler
    create a transient console and unnecessarily imported the GUI launcher.
    """
    root = project_root()
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    exe = executable or (str(pythonw) if pythonw.exists() else sys.executable)
    return [exe, script or str(root / "src" / "scheduled_runner.py"), schedule_id]


def format_run_command(command: list[str]) -> str:
    """Return the exact Windows command line represented by an action."""
    return subprocess.list2cmdline(command)

def build_task_xml(schedule: ClassSchedule) -> str:
    if not schedule.effective_run_time:
        schedule.effective_run_time = schedule.class_start_time or schedule.start_time
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"; ET.register_namespace("", ns)
    task = ET.Element(f"{{{ns}}}Task", {"version": "1.4"})
    reg = ET.SubElement(task, f"{{{ns}}}RegistrationInfo"); ET.SubElement(reg, f"{{{ns}}}Description").text = "Windows Class Bot class schedule"
    principals = ET.SubElement(task, f"{{{ns}}}Principals"); principal = ET.SubElement(principals, f"{{{ns}}}Principal", {"id":"Author"})
    ET.SubElement(principal, f"{{{ns}}}LogonType").text = "InteractiveToken"; ET.SubElement(principal, f"{{{ns}}}RunLevel").text = "LeastPrivilege"
    triggers = ET.SubElement(task, f"{{{ns}}}Triggers")
    nr = next_run_datetime(schedule)
    if schedule.recurrence == "weekly":
        trig = ET.SubElement(triggers, f"{{{ns}}}CalendarTrigger"); ET.SubElement(trig, f"{{{ns}}}StartBoundary").text = nr.isoformat(timespec="seconds")
        sched = ET.SubElement(trig, f"{{{ns}}}ScheduleByWeek"); ET.SubElement(sched, f"{{{ns}}}WeeksInterval").text = "1"
        days = ET.SubElement(sched, f"{{{ns}}}DaysOfWeek"); ET.SubElement(days, f"{{{ns}}}{windows_weekday(schedule.effective_run_weekday or schedule.weekday).title()}")
    else:
        trig = ET.SubElement(triggers, f"{{{ns}}}TimeTrigger"); ET.SubElement(trig, f"{{{ns}}}StartBoundary").text = nr.isoformat(timespec="seconds")
    ET.SubElement(trig, f"{{{ns}}}Enabled").text = str(schedule.enabled).lower()
    settings = ET.SubElement(task, f"{{{ns}}}Settings")
    for k,v in {"MultipleInstancesPolicy":"IgnoreNew","DisallowStartIfOnBatteries":"false","StopIfGoingOnBatteries":"false","AllowHardTerminate":"true","StartWhenAvailable":"true","RunOnlyIfNetworkAvailable":"false","WakeToRun":"true","Enabled":str(schedule.enabled).lower(),"ExecutionTimeLimit":"PT2H"}.items(): ET.SubElement(settings, f"{{{ns}}}{k}").text=v
    restart=ET.SubElement(settings, f"{{{ns}}}RestartOnFailure"); ET.SubElement(restart, f"{{{ns}}}Interval").text="PT1M"; ET.SubElement(restart, f"{{{ns}}}Count").text="3"
    actions=ET.SubElement(task, f"{{{ns}}}Actions", {"Context":"Author"}); ex=ET.SubElement(actions, f"{{{ns}}}Exec")
    cmd=build_run_command(schedule.id)
    ET.SubElement(ex, f"{{{ns}}}Command").text=cmd[0]
    ET.SubElement(ex, f"{{{ns}}}Arguments").text=subprocess.list2cmdline(cmd[1:])
    ET.SubElement(ex, f"{{{ns}}}WorkingDirectory").text=str(project_root())
    return ET.tostring(task, encoding="unicode")

class WindowsTaskScheduler:
    def __init__(self, runner=subprocess.run) -> None: self.runner = runner
    def register(self, schedule: ClassSchedule) -> TaskResult:
        if schedule.recurrence == "weekly": schedule.effective_run_time, schedule.effective_run_weekday = effective_for_weekday(schedule.weekday, schedule.class_start_time or schedule.start_time, schedule.early_minutes)
        elif schedule.date: schedule.effective_run_time, schedule.effective_run_date = effective_for_date(schedule.date, schedule.class_start_time or schedule.start_time, schedule.early_minutes)
        command = build_run_command(schedule.id)
        if not Path(command[0]).is_file():
            return TaskResult(False, f"Python زمان‌بندی پیدا نشد: {command[0]}", command)
        if not Path(command[1]).is_file():
            return TaskResult(False, f"Runner زمان‌بندی پیدا نشد: {command[1]}", command)
        xml = build_task_xml(schedule); task = sanitize_task_name(schedule.id)
        if not is_windows(): return TaskResult(False, "ثبت Task فقط روی Windows قابل اجراست.", ["schtasks.exe","/Create","/XML","<xml>","/TN",task], xml)
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f: f.write(xml); path=f.name
        # InteractiveToken is defined in the XML.  Mixing /IT with /XML is
        # redundant and can produce inconsistent registrations across Windows.
        args=["schtasks.exe","/Create","/F","/TN",task,"/XML",path]
        c=self.runner(args,capture_output=True,text=True,check=False)
        return TaskResult(c.returncode==0, c.stderr.strip() or c.stdout.strip() or "Task ثبت شد.", args, xml)
    def verify(self, schedule: ClassSchedule) -> TaskResult:
        if not is_windows(): return TaskResult(False, "بررسی Task فقط روی Windows قابل اجراست.", [], build_task_xml(schedule))
        args=["schtasks.exe","/Query","/TN",sanitize_task_name(schedule.id),"/XML"]
        c=self.runner(args,capture_output=True,text=True,check=False)
        return TaskResult(c.returncode==0, c.stderr.strip() or c.stdout.strip(), args)
    def last_run_result(self, schedule_id: str) -> TaskResult:
        """Read Task Scheduler's numeric LastTaskResult without locale parsing."""
        task = sanitize_task_name(schedule_id)
        if not is_windows():
            return TaskResult(False, "Last Run Result فقط روی Windows قابل دریافت است.", [])
        command = f"(Get-ScheduledTaskInfo -TaskName '{task}').LastTaskResult"
        args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        completed = self.runner(args, capture_output=True, text=True, check=False)
        message = completed.stderr.strip() or completed.stdout.strip() or "نامشخص"
        return TaskResult(completed.returncode == 0, message, args)
    def delete(self, schedule_id: str) -> TaskResult:
        if not is_windows(): return TaskResult(False, "حذف Task فقط روی Windows قابل اجراست.", [])
        args=["schtasks.exe","/Delete","/F","/TN",sanitize_task_name(schedule_id)]; c=self.runner(args,capture_output=True,text=True,check=False)
        return TaskResult(c.returncode==0, c.stderr.strip() or c.stdout.strip() or "Task حذف شد.", args)
