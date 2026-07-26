from __future__ import annotations

import threading
from unittest.mock import Mock

from src.browser.meeting_end import (
    AdobeProcessController,
    ChatMessage,
    FarewellConsensus,
    MeetingEndMonitor,
    is_farewell,
    normalize_persian,
)


def test_persian_farewell_variants_are_normalized():
    assert normalize_persian("خسته نباشيد استاد!") == "خسته نباشید استاد"
    assert is_farewell("خدا قوت استاد")
    assert is_farewell("دست‌تون درد نکنه")
    assert not is_farewell("استاد صدا قطع است")


def test_consensus_requires_distinct_identified_participants_and_every_latest_message():
    consensus = FarewellConsensus(minimum_participants=2)
    assert not consensus.reached([ChatMessage("علی", "خسته نباشید")])
    assert consensus.reached([
        ChatMessage("علی", "سلام"),
        ChatMessage("علی", "خسته نباشید استاد"),
        ChatMessage("مریم", "خدا قوت"),
    ])
    assert not consensus.reached([
        ChatMessage("علی", "خسته نباشید"),
        ChatMessage("مریم", "سؤال دارم"),
    ])


def test_monitor_does_not_log_or_persist_chat_and_detects_consensus():
    page = Mock()
    page.is_closed.return_value = False
    page.evaluate.return_value = [
        {"sender": "دانشجو ۱", "text": "خسته نباشید استاد"},
        {"sender": "دانشجو ۲", "text": "خدا قوت"},
    ]
    monitor = MeetingEndMonitor(poll_seconds=0.01)
    assert monitor.wait(page, threading.Event(), 1) == "farewell_consensus"


def test_process_controller_closes_only_new_adobe_pid(monkeypatch):
    monkeypatch.setattr("src.browser.meeting_end.os.name", "nt")
    listing = Mock(returncode=0, stdout='"Connect.exe","10","Console","1","10,000 K"\n"chrome.exe","30","Console","1","20,000 K"')
    killed = Mock(returncode=0, stdout="")
    runner = Mock(side_effect=[listing, killed])
    controller = AdobeProcessController(runner)
    assert controller.close_new(set()) == 1
    assert runner.call_args_list[1].args[0] == ["taskkill.exe", "/PID", "10", "/T"]


def test_process_controller_failure_is_safe(monkeypatch):
    monkeypatch.setattr("src.browser.meeting_end.os.name", "nt")
    controller = AdobeProcessController(Mock(side_effect=OSError("tasklist unavailable")))
    assert controller.snapshot() == set()
    assert controller.close_new({1}) == 0
