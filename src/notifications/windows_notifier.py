"""Best-effort local Windows notifications."""
from __future__ import annotations
import os, subprocess

def notify(title: str, message: str) -> None:
    """Show a non-blocking notification when optional platform support exists."""
    if os.name != "nt":
        return
    try:
        import winotify  # type: ignore
        winotify.Notification(app_id="Windows Class Bot", title=title, msg=message).show()
    except Exception:
        try:
            subprocess.run(["msg", "%USERNAME%", f"{title}: {message}"], check=False, capture_output=True, text=True)
        except Exception:
            return
