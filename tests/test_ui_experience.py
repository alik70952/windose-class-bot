"""Small headless checks for the UI state-management helpers."""

from types import SimpleNamespace

import pytest

pytest.importorskip("customtkinter")

from src.ui.main_window import MainWindow
from src.ui.schedule_frame import ScheduleFrame


class FakeWidget:
    def __init__(self) -> None:
        self.options = {}

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value


def test_running_state_keeps_only_stop_action_enabled() -> None:
    regular = FakeWidget()
    stop = FakeWidget()
    status = FakeWidget()
    window = SimpleNamespace(
        action_buttons=[regular, stop],
        stop_button=stop,
        run_status_label=status,
    )
    window._set_status = lambda message, kind: MainWindow._set_status(window, message, kind)

    MainWindow._set_running(window, True)

    assert regular.options["state"] == "disabled"
    assert stop.options["state"] == "normal"
    assert "در حال اجرا" in status.options["text"]


def test_idle_state_disables_stop_action() -> None:
    regular = FakeWidget()
    stop = FakeWidget()
    window = SimpleNamespace(
        action_buttons=[regular, stop],
        stop_button=stop,
        run_status_label=FakeWidget(),
    )
    window._set_status = lambda message, kind: MainWindow._set_status(window, message, kind)

    MainWindow._set_running(window, False)

    assert regular.options["state"] == "normal"
    assert stop.options["state"] == "disabled"


def test_one_hour_shortcut_normalizes_delay_fields() -> None:
    frame = SimpleNamespace(delay_hours_var=FakeVar(), delay_minutes_var=FakeVar())

    ScheduleFrame._set_quick_delay(frame, 60)

    assert frame.delay_hours_var.value == "1"
    assert frame.delay_minutes_var.value == "0"
