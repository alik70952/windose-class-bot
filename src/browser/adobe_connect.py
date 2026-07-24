"""Safe Adobe Connect protocol detection and launch helpers."""
from __future__ import annotations
import os, platform, re, time
from dataclasses import dataclass
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"adobeconnect", "connectpro", "acconnect", "adobe-connect"}
_TOKEN_RE = re.compile(r"([?&](?:token|sid|session|key|ticket|auth)=[^&\s]+)", re.I)

@dataclass(slots=True)
class AdobeLaunchResult:
    status: str
    message: str

class AdobeConnectLauncher:
    """Windows-only launcher that validates Adobe Connect custom protocol URIs."""
    def __init__(self, startfile=None, process_checker=None) -> None:
        self.startfile = startfile or getattr(os, "startfile", None)
        self.process_checker = process_checker or (lambda: False)
        self._last_uri = ""

    def is_windows(self) -> bool:
        return platform.system().lower() == "windows" or os.name == "nt"

    def sanitize(self, value: str) -> str:
        parsed = urlparse(value or "")
        if parsed.scheme in {"http", "https"}:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path[:40]}..."
        return _TOKEN_RE.sub("?...", value or "")[:80]

    def is_valid_uri(self, uri: str) -> bool:
        parsed = urlparse(uri or "")
        return bool(parsed.scheme and parsed.scheme.lower() in _ALLOWED_SCHEMES and len(uri) < 4096)

    def protocol_registered(self, scheme: str) -> bool:
        if not self.is_windows():
            return False
        try:
            import winreg  # type: ignore
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme):
                return True
        except Exception:
            return False

    def launch_uri(self, uri: str) -> AdobeLaunchResult:
        if not self.is_valid_uri(uri):
            return AdobeLaunchResult("adobe_connect_not_installed", "URI اجرای Adobe Connect معتبر نیست.")
        scheme = urlparse(uri).scheme.lower()
        if not self.protocol_registered(scheme) or self.startfile is None:
            return AdobeLaunchResult("adobe_connect_not_installed", "Adobe Connect روی این سیستم نصب یا برای لینک کلاس ثبت نشده است.")
        if uri == self._last_uri:
            return AdobeLaunchResult("needs_user_action", "درخواست بازکردن Adobe Connect قبلاً ارسال شده است.")
        self._last_uri = uri
        self.startfile(uri)  # no shell=True; delegates validated protocol to Windows association
        return AdobeLaunchResult("needs_user_action", "درخواست اجرای Adobe Connect به Windows ارسال شد.")

    def wait_for_launch(self, seconds: int, stop_event=None) -> str:
        deadline = time.monotonic() + max(0, seconds)
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                return "Stopped"
            if self.process_checker():
                return "adobe_connect_launched"
            time.sleep(0.5)
        return "adobe_connect_launch_timeout"
