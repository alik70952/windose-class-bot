from pathlib import Path
from unittest.mock import Mock

import src.scheduling.worker_task as worker_task
from src.scheduling.worker_task import WORKER_TASK_NAME, WorkerTaskScheduler, build_worker_command, build_worker_task_xml


def test_fixed_task_uses_pythonw_module():
    command, xml = build_worker_command(), build_worker_task_xml()
    assert command[-2:] == ["-m", "src.scheduler_worker"]
    assert "pythonw.exe" in command[0] and "-m src.scheduler_worker" in xml
    assert "<WorkingDirectory>" in xml and "WakeToRun>true" in xml


def test_no_per_schedule_task_is_created(monkeypatch):
    monkeypatch.setattr(worker_task, "is_windows", lambda: True)
    monkeypatch.setattr(Path, "is_file", lambda _self: True)
    runner = Mock(return_value=Mock(returncode=0, stdout="", stderr=""))
    result = WorkerTaskScheduler(runner).register()
    creates = [call.args[0] for call in runner.call_args_list if "/Create" in call.args[0]]
    assert result.success and len(creates) == 1 and WORKER_TASK_NAME in creates[0]


def test_old_tasks_are_removed(monkeypatch):
    monkeypatch.setattr(worker_task, "is_windows", lambda: True)
    output = '"VadanaClassBot-old","python main.py"\n"unsafe","cmd.exe /c run.bat"'
    runner = Mock(side_effect=[Mock(returncode=0, stdout=output, stderr=""), Mock(returncode=0, stdout="", stderr=""), Mock(returncode=0, stdout="", stderr="")])
    WorkerTaskScheduler(runner).remove_legacy_tasks()
    deletes = [call.args[0] for call in runner.call_args_list if "/Delete" in call.args[0]]
    assert len(deletes) == 2


def test_ui_waits_for_valid_heartbeat(monkeypatch):
    states = iter([False, False, True])
    monkeypatch.setattr(worker_task, "worker_is_healthy", lambda: next(states))
    scheduler = Mock(); scheduler.verify.return_value = worker_task.TaskResult(True, "", []); scheduler.start.return_value = worker_task.TaskResult(True, "", [])
    assert worker_task.ensure_scheduler_worker_running(1, scheduler, sleep=lambda _: None).success


def test_ui_does_not_show_success_without_worker(monkeypatch):
    monkeypatch.setattr(worker_task, "worker_is_healthy", lambda: False)
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(worker_task.time, "monotonic", lambda: next(ticks))
    scheduler = Mock(); scheduler.verify.return_value = worker_task.TaskResult(True, "", []); scheduler.start.return_value = worker_task.TaskResult(True, "", [])
    assert not worker_task.ensure_scheduler_worker_running(1, scheduler, sleep=lambda _: None).success


def test_failed_task_start_reports_fallback_reason(monkeypatch):
    monkeypatch.setattr(worker_task, "worker_is_healthy", lambda: False)
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(worker_task.time, "monotonic", lambda: next(ticks))
    fallback = worker_task.TaskResult(False, "pythonw پیدا نشد", ["pythonw.exe"])
    monkeypatch.setattr(worker_task, "_detached_start", lambda: fallback)
    scheduler = Mock()
    scheduler.verify.return_value = worker_task.TaskResult(False, "Task وجود ندارد", [])
    scheduler.register.return_value = worker_task.TaskResult(False, "Access is denied", [])

    result = worker_task.ensure_scheduler_worker_running(1, scheduler, sleep=lambda _: None)

    assert not result.success
    assert "Access is denied" in result.message and "pythonw پیدا نشد" in result.message
    assert result.args == ["pythonw.exe"]
