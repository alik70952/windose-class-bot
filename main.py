"""Application entry point for Windows Class Bot."""
from __future__ import annotations
import argparse
from src.app import run_app
from src.scheduling.executor import ScheduleExecutor

def main() -> int:
    """Run GUI or a background schedule selected by id."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-schedule", dest="schedule_id", default="")
    args = parser.parse_args()
    if args.schedule_id:
        return 0 if ScheduleExecutor().run(args.schedule_id) else 1
    run_app(); return 0

if __name__ == "__main__":
    raise SystemExit(main())
