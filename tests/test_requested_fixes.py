from __future__ import annotations
import threading, time
from pathlib import Path
from unittest.mock import Mock
from src.browser.adobe_connect import AdobeConnectLauncher
from src.scheduling.models import ClassSchedule
import src.scheduling.worker_task as worker_task
from src.scheduling.worker_task import WorkerTaskScheduler, build_worker_command, WORKER_TASK_NAME
from src.sites.vadana_sum39 import VadanaSum39Adapter, CourseSelectionError
from src.classes.presets import CLASS_PRESETS
from tests.test_scheduling import Page


def test_schedule_model_requested_fields_no_password():
    s = ClassSchedule(class_name=CLASS_PRESETS[0].name, recurrence="once", date="2026-07-24", start_time="09:15")
    data = s.to_dict()
    assert s.schedule_id == s.id and s.schedule_type == "once"
    assert "password" not in data and "class_name" in data and "launch_adobe_connect" in data


def test_task_uses_schedule_id_and_interactive_for_adobe(monkeypatch):
    monkeypatch.setattr(worker_task, "is_windows", lambda: True)
    monkeypatch.setattr(Path, "is_file", lambda _self: True)
    runner = Mock(return_value=Mock(returncode=0, stdout="ok", stderr=""))
    s = ClassSchedule(id="safeid", launch_adobe_connect=True)
    r = WorkerTaskScheduler(runner).register()
    assert r.success and "/IT" not in r.args
    assert "src.scheduler_worker" in " ".join(build_worker_command()) and "safeid" not in r.task_xml and WORKER_TASK_NAME
    assert runner.call_args.kwargs.get("check") is False


def test_installer_retries_worker_registration_with_uac():
    installer = (Path(__file__).parents[1] / "install.bat").read_text(encoding="utf-8")
    assert "Start-Process" in installer
    assert "-Verb RunAs" in installer
    assert "-Wait -PassThru" in installer
    assert "VADANA_WORKER_PY" in installer


def test_adobe_uri_validation_and_safe_launch(monkeypatch):
    calls = []
    launcher = AdobeConnectLauncher(startfile=calls.append, process_checker=lambda: True)
    monkeypatch.setattr(launcher, "is_windows", lambda: True)
    monkeypatch.setattr(launcher, "protocol_registered", lambda scheme: scheme == "adobeconnect")
    assert not launcher.is_valid_uri("javascript:alert(1)")
    result = launcher.launch_uri("adobeconnect://meeting?id=secret")
    assert result.status == "needs_user_action" and calls
    assert launcher.wait_for_launch(1) == "adobe_connect_launched"


def test_missing_adobe_connect_status(monkeypatch):
    launcher = AdobeConnectLauncher(startfile=lambda _uri: None)
    monkeypatch.setattr(launcher, "is_windows", lambda: True)
    monkeypatch.setattr(launcher, "protocol_registered", lambda scheme: False)
    assert launcher.launch_uri("adobeconnect://meeting").status == "adobe_connect_not_installed"


def test_wait_link_stop_and_timeout_messages():
    p = Page(["مشاهده آرشیو جلسات"])
    stop = threading.Event(); stop.set()
    try:
        VadanaSum39Adapter().enter_online_class(p, "x", 10_000, stop)
    except (CourseSelectionError, RuntimeError) as exc:
        assert "متوقف" in str(exc)
    p2 = Page(["مشاهده آرشیو جلسات"])
    start = time.monotonic()
    try:
        VadanaSum39Adapter().enter_online_class(p2, "x", 1, threading.Event())
    except CourseSelectionError as exc:
        assert "مهلت انتظار" in str(exc)
    assert time.monotonic() - start < 2
