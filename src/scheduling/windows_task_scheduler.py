"""Safe Windows Task Scheduler wrapper using argument lists only."""
from __future__ import annotations
import os, re, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import actual_run_time, windows_weekday

@dataclass(slots=True)
class TaskResult:
    success: bool
    message: str
    args: list[str]

def sanitize_task_name(schedule_id: str) -> str:
    """Create task name only from a safe schedule id."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", schedule_id)[:64] or "schedule"
    return f"WindowsClassBot_{safe}"

def build_run_command(schedule_id: str, executable: str | None = None, script: str | None = None) -> list[str]:
    """Build a credential-free command line for scheduled background execution."""
    exe = executable or (sys.executable if not getattr(sys, "frozen", False) else sys.executable)
    if getattr(sys, "frozen", False):
        return [exe, "--run-schedule", schedule_id]
    return [exe, script or os.path.abspath("main.py"), "--run-schedule", schedule_id]

class WindowsTaskScheduler:
    """Register/delete class schedules in Windows without shell=True."""
    def __init__(self, runner=subprocess.run) -> None:
        self.runner = runner
    def register(self, schedule: ClassSchedule) -> TaskResult:
        if os.name != "nt":
            return TaskResult(False, "ثبت Task فقط روی Windows قابل اجراست.", [])
        task = sanitize_task_name(schedule.id)
        run_time, _ = actual_run_time(schedule.start_time, schedule.early_minutes)
        cmd = " ".join(f'"{p}"' if " " in p else p for p in build_run_command(schedule.id))
        sc = "WEEKLY" if schedule.recurrence == "weekly" else "ONCE"
        args = ["schtasks.exe", "/Create", "/F", "/TN", task, "/TR", cmd, "/SC", sc, "/ST", run_time]
        if sc == "WEEKLY": args += ["/D", windows_weekday(schedule.weekday)]
        completed = self.runner(args, capture_output=True, text=True, check=False)
        return TaskResult(completed.returncode == 0, completed.stderr.strip() or completed.stdout.strip() or "Task ثبت شد.", args)
    def delete(self, schedule_id: str) -> TaskResult:
        if os.name != "nt": return TaskResult(False, "حذف Task فقط روی Windows قابل اجراست.", [])
        args = ["schtasks.exe", "/Delete", "/F", "/TN", sanitize_task_name(schedule_id)]
        c = self.runner(args, capture_output=True, text=True, check=False)
        return TaskResult(c.returncode == 0, c.stderr.strip() or c.stdout.strip() or "Task حذف شد.", args)
