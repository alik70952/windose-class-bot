"""Process lock, heartbeat, and health checks for the Windows worker."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOCK_PATH = RUNTIME_DIR / "scheduler-worker.lock"
HEARTBEAT_PATH = RUNTIME_DIR / "scheduler-worker-heartbeat.json"


class WorkerProcessLock:
    """An OS-owned byte-range lock; a stale file is harmless after process death."""
    def __init__(self, path: Path = LOCK_PATH) -> None:
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b")
        try:
            self._file.seek(0)
            if self._file.read(1) == b"":
                self._file.seek(0)
                self._file.write(b"0")
                self._file.flush()
            self._file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # Allows faithful lock regression tests on development hosts.
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self._file.close()
            self._file = None
            return False

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close(); self._file = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("worker_already_running")
        return self

    def __exit__(self, *_args):
        self.release()


def write_heartbeat(pid: int, started_at_epoch: float, now: float | None = None,
                    path: Path = HEARTBEAT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pid": pid, "started_at_epoch": started_at_epoch,
               "last_heartbeat_epoch": time.time() if now is None else now, "version": "2"}
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def pid_is_running(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def worker_is_healthy(*, now: float | None = None, heartbeat_path: Path = HEARTBEAT_PATH,
                      lock_path: Path = LOCK_PATH) -> bool:
    """Require a fresh v2 heartbeat, live PID, and an actively held OS lock."""
    try:
        payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        current = time.time() if now is None else now
        if payload.get("version") != "2" or current - float(payload["last_heartbeat_epoch"]) >= 10:
            return False
        if not pid_is_running(int(payload["pid"])):
            return False
        probe = WorkerProcessLock(lock_path)
        if probe.acquire():
            probe.release()
            return False
        return True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
