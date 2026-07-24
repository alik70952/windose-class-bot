"""Recoverable local profile lock to prevent simultaneous profile use."""
from __future__ import annotations
import json, os, time
from pathlib import Path

class ProfileLock:
    """File lock with PID/timestamp and stale recovery."""
    def __init__(self, profile_id: str, lock_dir: Path = Path("locks"), stale_seconds: int = 7200) -> None:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in profile_id)[:80]
        self.path = lock_dir / f"{safe}.lock"
        self.stale_seconds = stale_seconds
        self.acquired = False
    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if time.time() - float(data.get("timestamp", 0)) < self.stale_seconds:
                    return False
            except Exception: pass
            self.path.unlink(missing_ok=True)
        self.path.write_text(json.dumps({"pid": os.getpid(), "timestamp": time.time()}), encoding="utf-8")
        self.acquired = True
        return True
    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True); self.acquired = False
    def __enter__(self):
        if not self.acquire(): raise RuntimeError("یک عملیات دیگر برای همین Profile در حال اجراست.")
        return self
    def __exit__(self, *args) -> None: self.release()
