"""Base types for site-specific Playwright adapters."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

LogCallback = Callable[[str], None]


class PageLike(Protocol):
    """Minimal Playwright Page protocol used by adapters and tests."""


@dataclass(slots=True)
class LoginResult:
    """Safe login outcome for UI logging."""

    success: bool
    message: str
    screenshot_path: Path | None = None


class SiteAdapter:
    """Common contract for current and future supported learning systems."""

    login_url: str

    def login(self, page: PageLike, username: str, password: str, timeout_ms: int, stop_event: threading.Event) -> LoginResult:
        """Perform a safe login flow without leaking credentials."""
        raise NotImplementedError
