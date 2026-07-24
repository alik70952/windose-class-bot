"""Register the single, persistent scheduler worker with Windows.

Task Scheduler is only the worker's supervisor.  Class schedules never become
Windows tasks; they remain records in ``config.json`` and are dispatched by the
long-running worker.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

WORKER_TASK_NAME = "VadanaClassBot-Worker"


@dataclass(slots=True)
class TaskResult:
    success: bool
    message: str
    args: list[str]
    task_xml: str = ""


def is_windows() -> bool:
    return sys.platform == "win32"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_worker_command(executable: str | None = None, script: str | None = None) -> list[str]:
    root = project_root()
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    return [executable or (str(pythonw) if pythonw.exists() else sys.executable),
            script or str(root / "src" / "schedule_worker.py")]


def format_run_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def build_worker_task_xml() -> str:
    """Build one logon-triggered task that Windows restarts after a crash."""
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", ns)
    task = ET.Element(f"{{{ns}}}Task", {"version": "1.4"})
    registration = ET.SubElement(task, f"{{{ns}}}RegistrationInfo")
    ET.SubElement(registration, f"{{{ns}}}Description").text = "Vadana Class Bot persistent schedule worker"
    principals = ET.SubElement(task, f"{{{ns}}}Principals")
    principal = ET.SubElement(principals, f"{{{ns}}}Principal", {"id": "Author"})
    ET.SubElement(principal, f"{{{ns}}}LogonType").text = "InteractiveToken"
    ET.SubElement(principal, f"{{{ns}}}RunLevel").text = "LeastPrivilege"
    triggers = ET.SubElement(task, f"{{{ns}}}Triggers")
    trigger = ET.SubElement(triggers, f"{{{ns}}}LogonTrigger")
    ET.SubElement(trigger, f"{{{ns}}}Enabled").text = "true"
    settings = ET.SubElement(task, f"{{{ns}}}Settings")
    values = {
        "MultipleInstancesPolicy": "IgnoreNew", "DisallowStartIfOnBatteries": "false",
        "StopIfGoingOnBatteries": "false", "StartWhenAvailable": "true",
        "RunOnlyIfNetworkAvailable": "false", "WakeToRun": "false", "Enabled": "true",
        "ExecutionTimeLimit": "PT0S",
    }
    for key, value in values.items():
        ET.SubElement(settings, f"{{{ns}}}{key}").text = value
    restart = ET.SubElement(settings, f"{{{ns}}}RestartOnFailure")
    ET.SubElement(restart, f"{{{ns}}}Interval").text = "PT1M"
    ET.SubElement(restart, f"{{{ns}}}Count").text = "999"
    actions = ET.SubElement(task, f"{{{ns}}}Actions", {"Context": "Author"})
    action = ET.SubElement(actions, f"{{{ns}}}Exec")
    command = build_worker_command()
    ET.SubElement(action, f"{{{ns}}}Command").text = command[0]
    ET.SubElement(action, f"{{{ns}}}Arguments").text = subprocess.list2cmdline(command[1:])
    ET.SubElement(action, f"{{{ns}}}WorkingDirectory").text = str(project_root())
    return ET.tostring(task, encoding="unicode")


class WorkerTaskScheduler:
    """Idempotently install/query the one worker task."""
    def __init__(self, runner=subprocess.run) -> None:
        self.runner = runner

    def register(self) -> TaskResult:
        command = build_worker_command()
        if not Path(command[0]).is_file() or not Path(command[1]).is_file():
            return TaskResult(False, f"Worker یا Python پیدا نشد: {format_run_command(command)}", command)
        xml = build_worker_task_xml()
        args = ["schtasks.exe", "/Create", "/F", "/TN", WORKER_TASK_NAME, "/XML", "<xml>"]
        if not is_windows():
            return TaskResult(False, "ثبت Worker فقط روی Windows قابل اجراست.", args, xml)
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as stream:
            stream.write(xml)
            path = stream.name
        args[-1] = path
        completed = self.runner(args, capture_output=True, text=True, check=False)
        message = completed.stderr.strip() or completed.stdout.strip() or "Worker ثبت شد."
        return TaskResult(completed.returncode == 0, message, args, xml)

    def start(self) -> TaskResult:
        args = ["schtasks.exe", "/Run", "/TN", WORKER_TASK_NAME]
        if not is_windows():
            return TaskResult(False, "اجرای Worker فقط روی Windows قابل اجراست.", args)
        completed = self.runner(args, capture_output=True, text=True, check=False)
        return TaskResult(completed.returncode == 0,
                          completed.stderr.strip() or completed.stdout.strip() or "Worker اجرا شد.", args)

    def ensure_running(self) -> TaskResult:
        result = self.register()
        if not result.success:
            return result
        started = self.start()
        started.task_xml = result.task_xml
        return started
