"""Per-schedule process lock with stale PID cleanup."""
from __future__ import annotations
import json, os, time
from pathlib import Path

class ScheduleLock:
    def __init__(self, schedule_id: str, root: Path | None = None) -> None:
        self.path = (root or Path.cwd()) / "logs" / "schedules" / f"{schedule_id}.lock"
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding="utf-8")); pid=int(data.get("pid",0))
                if pid and self._alive(pid): raise RuntimeError("already_running")
            except RuntimeError: raise
            except Exception: pass
            self.path.unlink(missing_ok=True)
        self.path.write_text(json.dumps({"pid":os.getpid(),"created_at":time.time()}), encoding="utf-8")
        return self
    def __exit__(self, *_exc):
        self.path.unlink(missing_ok=True)
    @staticmethod
    def _alive(pid:int)->bool:
        try: os.kill(pid,0); return True
        except OSError: return False
