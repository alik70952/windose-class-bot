from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

from src.scheduler_worker import SchedulerWorker
from src.scheduling.schedule_store import ScheduleStore
from src.scheduling.worker_runtime import WorkerProcessLock, worker_is_healthy


class Executor:
    calls: list[str] = []
    fail: set[str] = set()
    active = 0
    max_active = 0

    def run_schedule(self, job):
        type(self).calls.append(job.id)
        type(self).active += 1
        type(self).max_active = max(type(self).max_active, type(self).active)
        try:
            if job.id in type(self).fail:
                raise ValueError("permanent test failure")
            return True
        finally:
            type(self).active -= 1


def queue(store, job_id, when=0, class_name=None):
    return store.create("profile", class_name or job_id, when, 0, 1, schedule_id=job_id)


def fresh_worker(tmp_path):
    Executor.calls, Executor.fail, Executor.active, Executor.max_active = [], set(), 0, 0
    return SchedulerWorker(ScheduleStore(tmp_path / "scheduler.db"), Executor, poll_seconds=.01)


def test_worker_executes_second_schedule_after_first_success(tmp_path, monkeypatch):
    worker = fresh_worker(tmp_path); monkeypatch.setattr(worker, "heartbeat", Mock())
    queue(worker.store, "first"); queue(worker.store, "second")
    worker.tick(1); worker.tick(1)
    assert Executor.calls == ["first", "second"]


def test_worker_executes_third_schedule_after_second(tmp_path, monkeypatch):
    worker = fresh_worker(tmp_path); monkeypatch.setattr(worker, "heartbeat", Mock())
    for item in ("first", "second", "third"): queue(worker.store, item)
    for _ in range(3): worker.tick(1)
    assert Executor.calls == ["first", "second", "third"]


def test_worker_remains_alive_after_failed_schedule(tmp_path, monkeypatch):
    worker = fresh_worker(tmp_path); monkeypatch.setattr(worker, "heartbeat", Mock())
    Executor.fail = {"bad"}; queue(worker.store, "bad"); queue(worker.store, "good")
    worker.tick(1); worker.tick(1)
    assert worker.store.get("bad").status == "failed" and worker.store.get("good").status == "succeeded"


def test_worker_survives_second_and_third_execution(tmp_path, monkeypatch):
    test_worker_executes_third_schedule_after_second(tmp_path, monkeypatch)


def test_schedule_claim_is_atomic(tmp_path):
    store = ScheduleStore(tmp_path / "scheduler.db"); queue(store, "one")
    barrier = threading.Barrier(2)
    def claim(name): barrier.wait(); return store.claim_due(name, 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("a", "b")))
    assert sum(result is not None for result in results) == 1


def test_only_one_worker_holds_lock(tmp_path):
    first, second = WorkerProcessLock(tmp_path / "worker.lock"), WorkerProcessLock(tmp_path / "worker.lock")
    assert first.acquire() and not second.acquire()
    first.release(); assert second.acquire(); second.release()


def test_stale_heartbeat_is_not_healthy(tmp_path, monkeypatch):
    heartbeat, lock = tmp_path / "heartbeat.json", tmp_path / "lock"
    heartbeat.write_text(json.dumps({"pid": os.getpid(), "last_heartbeat_epoch": 1, "version": "2"}))
    monkeypatch.setattr("src.scheduling.worker_runtime.pid_is_running", lambda _pid: True)
    assert not worker_is_healthy(now=20, heartbeat_path=heartbeat, lock_path=lock)


def test_dead_pid_is_not_healthy(tmp_path, monkeypatch):
    heartbeat, lock = tmp_path / "heartbeat.json", tmp_path / "lock"
    heartbeat.write_text(json.dumps({"pid": 999, "last_heartbeat_epoch": 19, "version": "2"}))
    monkeypatch.setattr("src.scheduling.worker_runtime.pid_is_running", lambda _pid: False)
    assert not worker_is_healthy(now=20, heartbeat_path=heartbeat, lock_path=lock)


def test_pending_same_class_is_cancelled(tmp_path):
    store = ScheduleStore(tmp_path / "db"); queue(store, "old", 5, "class"); queue(store, "new", 6, "class")
    assert store.get("old").status == "cancelled" and store.get("new").status == "pending"


def test_completed_schedule_does_not_block_new_schedule(tmp_path):
    store = ScheduleStore(tmp_path / "db"); queue(store, "old", 0, "class")
    store.claim_due("w", 1); store.finish("old", True); queue(store, "new", 2, "class")
    assert store.get("new").status == "pending"


def test_worker_executes_jobs_sequentially(tmp_path, monkeypatch):
    worker = fresh_worker(tmp_path); monkeypatch.setattr(worker, "heartbeat", Mock())
    queue(worker.store, "a"); queue(worker.store, "b"); worker.tick(1); worker.tick(1)
    assert Executor.max_active == 1
