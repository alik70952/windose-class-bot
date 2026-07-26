"""Detect a class farewell consensus and close only meeting resources we own."""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Iterable


_SPACE_RE = re.compile(r"[\s\u200c\u200f\u202a-\u202e]+")
_PUNCTUATION_RE = re.compile(r"[^\w\s\u0600-\u06ff]", re.UNICODE)
_FAREWELL_PATTERNS = (
    re.compile(r"(?:خیلی\s+)?خسته\s*نباشید"),
    re.compile(r"خدا\s*قوت"),
    re.compile(r"دست\s*(?:تون|تان)?\s*درد\s*نکنه"),
    re.compile(r"(?:ممنون|متشکر|سپاس)(?:م\s+استاد|\s+استاد)?"),
    re.compile(r"روز(?:تون|تان)?\s*(?:بخیر|خوش)"),
    re.compile(r"شب(?:تون|تان)?\s*بخیر"),
)


def normalize_persian(value: str) -> str:
    """Normalize common Arabic/Persian variants without retaining chat secrets."""
    translated = (value or "").translate(str.maketrans({
        "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    }))
    return _SPACE_RE.sub(" ", _PUNCTUATION_RE.sub(" ", translated)).strip().lower()


def is_farewell(message: str) -> bool:
    """Return whether a message is a conventional Persian class farewell."""
    normalized = normalize_persian(message)
    return any(pattern.search(normalized) for pattern in _FAREWELL_PATTERNS)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    sender: str
    text: str


class FarewellConsensus:
    """Require every recently active, identified participant to say farewell."""

    def __init__(self, minimum_participants: int = 2) -> None:
        self.minimum_participants = max(2, minimum_participants)

    def reached(self, messages: Iterable[ChatMessage]) -> bool:
        latest_by_sender: dict[str, str] = {}
        for message in messages:
            sender = normalize_persian(message.sender)
            text = message.text.strip()
            if sender and text:
                latest_by_sender[sender] = text
        return (
            len(latest_by_sender) >= self.minimum_participants
            and all(is_farewell(text) for text in latest_by_sender.values())
        )


class AdobeProcessController:
    """Snapshot Adobe Connect PIDs and later stop only processes created afterward."""

    PROCESS_NAMES = {"connect.exe", "adobeconnect.exe", "adobe connect.exe"}

    def __init__(self, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self.runner = runner

    def snapshot(self) -> set[int]:
        if os.name != "nt":
            return set()
        command = ["tasklist.exe", "/FO", "CSV", "/NH"]
        try:
            result = self.runner(command, capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return set()
        found: set[int] = set()
        for line in result.stdout.splitlines():
            fields = [part.strip().strip('"') for part in line.split('","')]
            if len(fields) >= 2 and fields[0].lower() in self.PROCESS_NAMES:
                try:
                    found.add(int(fields[1]))
                except ValueError:
                    continue
        return found

    def close_new(self, before: set[int]) -> int:
        closed = 0
        for pid in self.snapshot() - before:
            try:
                result = self.runner(
                    ["taskkill.exe", "/PID", str(pid), "/T"],
                    capture_output=True, text=True, check=False, timeout=10,
                )
                closed += int(result.returncode == 0)
            except (OSError, subprocess.SubprocessError):
                continue
        return closed


class MeetingEndMonitor:
    """Poll Adobe web-chat DOM and close the page after a farewell consensus."""

    _EXTRACT_SCRIPT = """
    () => {
      const selectors = [
        '[data-testid="chat-message"]', '[data-test="chat-message"]',
        '.chat-message', '.message-wrapper', '[role="log"] [role="listitem"]'
      ];
      const nodes = [...new Set(selectors.flatMap(s => [...document.querySelectorAll(s)]))].slice(-80);
      return nodes.map(node => {
        const sender = node.querySelector('.sender, .author, .user-name, [data-testid="sender"]');
        const body = node.querySelector('.message, .message-text, .content, [data-testid="message-text"]');
        return {sender: (sender?.textContent || '').trim(), text: (body?.textContent || node.textContent || '').trim()};
      });
    }
    """

    def __init__(self, minimum_participants: int = 2, poll_seconds: float = 5.0) -> None:
        self.consensus = FarewellConsensus(minimum_participants)
        self.poll_seconds = max(0.2, poll_seconds)

    def read_messages(self, page) -> list[ChatMessage]:
        try:
            raw = page.evaluate(self._EXTRACT_SCRIPT) or []
        except Exception:
            return []
        return [
            ChatMessage(str(item.get("sender", "")), str(item.get("text", "")))
            for item in raw if isinstance(item, dict)
        ]

    def wait(self, page, stop_event, timeout_seconds: int) -> str:
        deadline = time.monotonic() + max(1, timeout_seconds)
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return "stopped"
            try:
                if page.is_closed():
                    return "meeting_closed"
            except Exception:
                return "meeting_closed"
            if self.consensus.reached(self.read_messages(page)):
                return "farewell_consensus"
            stop_event.wait(min(self.poll_seconds, max(0, deadline - time.monotonic())))
        return "monitor_timeout"
