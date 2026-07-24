"""Install, verify, start, and health-check the one Windows worker task."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from src.scheduling.worker_runtime import worker_is_healthy

WORKER_TASK_NAME = "VadanaClassBotWorker"
LEGACY_TASK_NAMES = ("VadanaClassBot-Worker",)


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
    pythonw = project_root() / ".venv" / "Scripts" / "pythonw.exe"
    # script remains accepted for API compatibility, but never becomes a script action.
    return [executable or str(pythonw), "-m", "src.scheduler_worker"]


def format_run_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def build_worker_task_xml() -> str:
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", ns)
    task = ET.Element(f"{{{ns}}}Task", {"version": "1.4"})
    registration = ET.SubElement(task, f"{{{ns}}}RegistrationInfo")
    ET.SubElement(registration, f"{{{ns}}}Description").text = "Vadana Class Bot persistent SQLite worker"
    principals = ET.SubElement(task, f"{{{ns}}}Principals")
    principal = ET.SubElement(principals, f"{{{ns}}}Principal", {"id": "Author"})
    ET.SubElement(principal, f"{{{ns}}}UserId").text = os.environ.get("USERNAME", "")
    ET.SubElement(principal, f"{{{ns}}}LogonType").text = "InteractiveToken"
    ET.SubElement(principal, f"{{{ns}}}RunLevel").text = "LeastPrivilege"
    triggers = ET.SubElement(task, f"{{{ns}}}Triggers")
    ET.SubElement(ET.SubElement(triggers, f"{{{ns}}}LogonTrigger"), f"{{{ns}}}Enabled").text = "true"
    settings = ET.SubElement(task, f"{{{ns}}}Settings")
    values = {"MultipleInstancesPolicy": "IgnoreNew", "DisallowStartIfOnBatteries": "false",
              "StopIfGoingOnBatteries": "false", "StartWhenAvailable": "true", "WakeToRun": "true",
              "Enabled": "true", "ExecutionTimeLimit": "PT0S"}
    for key, value in values.items():
        ET.SubElement(settings, f"{{{ns}}}{key}").text = value
    restart = ET.SubElement(settings, f"{{{ns}}}RestartOnFailure")
    ET.SubElement(restart, f"{{{ns}}}Interval").text = "PT1M"
    ET.SubElement(restart, f"{{{ns}}}Count").text = "999"
    action = ET.SubElement(ET.SubElement(task, f"{{{ns}}}Actions", {"Context": "Author"}), f"{{{ns}}}Exec")
    command = build_worker_command()
    ET.SubElement(action, f"{{{ns}}}Command").text = command[0]
    ET.SubElement(action, f"{{{ns}}}Arguments").text = "-m src.scheduler_worker"
    ET.SubElement(action, f"{{{ns}}}WorkingDirectory").text = str(project_root())
    return ET.tostring(task, encoding="unicode")


class WorkerTaskScheduler:
    def __init__(self, runner=subprocess.run) -> None:
        self.runner = runner

    def remove_legacy_tasks(self) -> None:
        if not is_windows():
            return
        # Query XML/verbose output, then remove every old/per-job or unsafe action.
        queried = self.runner(["schtasks.exe", "/Query", "/FO", "CSV", "/V"], capture_output=True, text=True, check=False)
        for line in (queried.stdout or "").splitlines():
            lowered = line.lower()
            name = line.split(",", 1)[0].strip('"\\ ')
            legacy = (name.startswith("VadanaClassBot-") or any(token in lowered for token in
                      ("main.py", "scheduled_runner.py", "schedule_worker.py", "cmd.exe", "run.bat")))
            if legacy and name != WORKER_TASK_NAME:
                self.runner(["schtasks.exe", "/Delete", "/F", "/TN", name], capture_output=True, text=True, check=False)

    def register(self) -> TaskResult:
        command = build_worker_command()
        xml = build_worker_task_xml()
        args = ["schtasks.exe", "/Create", "/F", "/TN", WORKER_TASK_NAME, "/XML", "<xml>"]
        if not is_windows():
            return TaskResult(False, "ثبت Worker فقط روی Windows قابل اجراست.", args, xml)
        if not Path(command[0]).is_file():
            return TaskResult(False, f"pythonw.exe پیدا نشد: {command[0]}", command, xml)
        self.remove_legacy_tasks()
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as stream:
            stream.write(xml); args[-1] = stream.name
        try:
            completed = self.runner(args, capture_output=True, text=True, check=False)
        finally:
            Path(args[-1]).unlink(missing_ok=True)
        return TaskResult(completed.returncode == 0, completed.stderr.strip() or completed.stdout.strip(), args, xml)

    def verify(self) -> TaskResult:
        args = ["schtasks.exe", "/Query", "/TN", WORKER_TASK_NAME, "/XML"]
        if not is_windows():
            return TaskResult(False, "بررسی Task فقط روی Windows قابل اجراست.", args)
        completed = self.runner(args, capture_output=True, text=True, check=False)
        xml = completed.stdout or ""
        valid = completed.returncode == 0 and all(value in xml for value in
                ("pythonw.exe", "-m src.scheduler_worker", str(project_root())))
        return TaskResult(valid, completed.stderr.strip() or ("Task معتبر است." if valid else "Action مربوط به Worker معتبر نیست."), args, xml)

    def start(self) -> TaskResult:
        args = ["schtasks.exe", "/Run", "/TN", WORKER_TASK_NAME]
        if not is_windows():
            return TaskResult(False, "اجرای Worker فقط روی Windows قابل اجراست.", args)
        completed = self.runner(args, capture_output=True, text=True, check=False)
        return TaskResult(completed.returncode == 0, completed.stderr.strip() or completed.stdout.strip(), args)


def _detached_start() -> bool:
    if not is_windows():
        return False
    pythonw = build_worker_command()[0]
    try:
        subprocess.Popen([pythonw, "-m", "src.scheduler_worker"], cwd=project_root(),
                         creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS |
                                        subprocess.CREATE_NEW_PROCESS_GROUP), close_fds=True)
        return True
    except OSError:
        return False


def ensure_scheduler_worker_running(timeout: float = 10.0,
                                    scheduler: WorkerTaskScheduler | None = None,
                                    sleep=time.sleep) -> TaskResult:
    if worker_is_healthy():
        return TaskResult(True, "Worker سالم است.", [])
    scheduler = scheduler or WorkerTaskScheduler()
    verified = scheduler.verify()
    if not verified.success:
        verified = scheduler.register()
    started = scheduler.start() if verified.success else verified
    if not started.success:
        _detached_start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if worker_is_healthy():
            return TaskResult(True, "Worker با Heartbeat معتبر فعال است.", started.args, verified.task_xml)
        sleep(0.25)
    return TaskResult(False, "سرویس اجرای خودکار راه‌اندازی نشد.", started.args, verified.task_xml)


WorkerTaskScheduler.ensure_running = lambda self: ensure_scheduler_worker_running(scheduler=self)  # compatibility
