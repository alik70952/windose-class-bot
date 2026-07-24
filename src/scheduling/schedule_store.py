"""Transactional SQLite queue used by the persistent scheduler worker."""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "data" / "scheduler.db"
STATUSES = {"pending", "running", "succeeded", "failed", "cancelled"}


@dataclass(slots=True)
class ScheduleRecord:
    id: str
    profile_id: str
    class_name: str
    run_at_epoch: float
    delay_hours: int
    delay_minutes: int
    status: str = "pending"
    attempt_count: int = 0
    max_attempts: int = 3
    created_at_epoch: float = 0
    updated_at_epoch: float = 0
    claimed_at_epoch: float | None = None
    claimed_by: str | None = None
    completed_at_epoch: float | None = None
    last_error: str | None = None
    last_result: str | None = None


class ScheduleStore:
    """Small SQLite repository whose claims are serialized by BEGIN IMMEDIATE."""

    def __init__(self, path: Path | str = DATABASE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                class_name TEXT NOT NULL,
                run_at_epoch REAL NOT NULL,
                delay_hours INTEGER NOT NULL,
                delay_minutes INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','cancelled')),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                created_at_epoch REAL NOT NULL,
                updated_at_epoch REAL NOT NULL,
                claimed_at_epoch REAL,
                claimed_by TEXT,
                completed_at_epoch REAL,
                last_error TEXT,
                last_result TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS schedules_due ON schedules(status, run_at_epoch, created_at_epoch)")

    @staticmethod
    def _record(row: sqlite3.Row | None) -> ScheduleRecord | None:
        return ScheduleRecord(**dict(row)) if row else None

    def create(self, profile_id: str, class_name: str, run_at_epoch: float,
               delay_hours: int, delay_minutes: int, *, schedule_id: str | None = None,
               max_attempts: int = 3, cancel_pending_same_class: bool = True) -> ScheduleRecord:
        now = time.time()
        item = ScheduleRecord(schedule_id or uuid.uuid4().hex, profile_id, class_name,
                              run_at_epoch, delay_hours, delay_minutes, max_attempts=max_attempts,
                              created_at_epoch=now, updated_at_epoch=now)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if cancel_pending_same_class:
                db.execute("UPDATE schedules SET status='cancelled', updated_at_epoch=? "
                           "WHERE profile_id=? AND class_name=? AND status='pending'",
                           (now, profile_id, class_name))
            columns = list(asdict(item))
            db.execute(f"INSERT INTO schedules ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                       tuple(asdict(item)[column] for column in columns))
            db.commit()
        return item

    def get(self, schedule_id: str) -> ScheduleRecord | None:
        with self._connect() as db:
            return self._record(db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone())

    def list(self, status: str | None = None) -> list[ScheduleRecord]:
        query, args = "SELECT * FROM schedules", ()
        if status:
            query, args = query + " WHERE status=?", (status,)
        with self._connect() as db:
            return [ScheduleRecord(**dict(row)) for row in db.execute(query + " ORDER BY run_at_epoch, created_at_epoch", args)]

    def cancel(self, schedule_id: str) -> bool:
        with self._connect() as db:
            result = db.execute("UPDATE schedules SET status='cancelled', updated_at_epoch=? "
                                "WHERE id=? AND status='pending'", (time.time(), schedule_id))
            return result.rowcount == 1

    def claim_due(self, claimed_by: str, now: float | None = None) -> ScheduleRecord | None:
        now = time.time() if now is None else now
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM schedules WHERE status='pending' AND run_at_epoch<=? "
                             "ORDER BY run_at_epoch, created_at_epoch LIMIT 1", (now,)).fetchone()
            if row is None:
                db.commit()
                return None
            changed = db.execute("UPDATE schedules SET status='running', attempt_count=attempt_count+1, "
                                 "claimed_at_epoch=?, claimed_by=?, updated_at_epoch=? "
                                 "WHERE id=? AND status='pending'", (now, claimed_by, now, row["id"]))
            db.commit()
            return self.get(row["id"]) if changed.rowcount == 1 else None

    def finish(self, schedule_id: str, succeeded: bool, *, result: str = "", error: str = "") -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("UPDATE schedules SET status=?, updated_at_epoch=?, completed_at_epoch=?, "
                       "last_result=?, last_error=? WHERE id=? AND status='running'",
                       ("succeeded" if succeeded else "failed", now, now, result or None, error or None, schedule_id))

    def retry(self, schedule_id: str, delay_seconds: float, error: str) -> bool:
        now = time.time()
        with self._connect() as db:
            changed = db.execute("UPDATE schedules SET status='pending', run_at_epoch=?, updated_at_epoch=?, "
                                 "claimed_at_epoch=NULL, claimed_by=NULL, last_error=? "
                                 "WHERE id=? AND status='running' AND attempt_count<max_attempts",
                                 (now + delay_seconds, now, error, schedule_id))
            return changed.rowcount == 1

    def recover_stale(self, now: float | None = None, stale_seconds: float = 600) -> tuple[int, int]:
        now = time.time() if now is None else now
        cutoff = now - stale_seconds
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            retried = db.execute("UPDATE schedules SET status='pending', updated_at_epoch=?, claimed_at_epoch=NULL, "
                                 "claimed_by=NULL WHERE status='running' AND claimed_at_epoch<? "
                                 "AND attempt_count<max_attempts", (now, cutoff)).rowcount
            failed = db.execute("UPDATE schedules SET status='failed', updated_at_epoch=?, completed_at_epoch=?, "
                                "last_error=COALESCE(last_error,'stale worker claim') WHERE status='running' "
                                "AND claimed_at_epoch<? AND attempt_count>=max_attempts", (now, now, cutoff)).rowcount
            db.commit()
            return retried, failed
