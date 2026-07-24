"""Synchronous, windowless entry point used exclusively by Windows Task Scheduler.

This module deliberately does not import the GUI entry point.  It bootstraps the
repository path when executed as a file and then runs exactly one persisted
schedule in the Task user's interactive session.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RUNNER_ERROR_LOG = PROJECT_ROOT / "logs" / "scheduled-runner-error.log"


def _record_fatal_error(exc: BaseException) -> None:
    """Persist bootstrap failures because pythonw.exe has no visible console."""
    RUNNER_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUNNER_ERROR_LOG.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{datetime.now().isoformat(timespec='seconds')} scheduled runner failed\n")
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=stream)


def main(argv: list[str] | None = None) -> int:
    """Run one schedule synchronously and return a Task Scheduler exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1 or not arguments[0].strip():
        raise ValueError("scheduled_runner.py requires exactly one schedule_id")

    from src.scheduling.executor import ScheduleExecutor

    return 0 if ScheduleExecutor().run(arguments[0]) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - Task failures must survive pythonw.
        _record_fatal_error(exc)
        raise SystemExit(1) from exc
