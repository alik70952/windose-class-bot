"""Application entry point for Windows Class Bot."""
from __future__ import annotations

import argparse
import sys
import traceback
from tkinter import messagebox

from src.config.manager import PROJECT_ROOT

STARTUP_LOG_PATH = PROJECT_ROOT / "logs" / "startup-error.log"
STARTUP_ERROR_MESSAGE = "برنامه هنگام راه‌اندازی با خطا مواجه شد."


def _write_startup_error(exc: BaseException) -> None:
    """Write a local startup traceback without logging credentials or config contents."""
    STARTUP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    STARTUP_LOG_PATH.write_text(details, encoding="utf-8")


def _show_startup_error_message() -> None:
    """Best-effort GUI notice that must never hide the original startup error."""
    try:
        messagebox.showerror(
            "خطای راه‌اندازی",
            f"{STARTUP_ERROR_MESSAGE}\nجزئیات در {STARTUP_LOG_PATH} ذخیره شد.",
        )
    except Exception:  # noqa: BLE001 - messagebox is optional during broken GUI startup.
        pass


def main(argv: list[str] | None = None) -> int:
    """Run the GUI or a background schedule selected by id."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-schedule", dest="schedule_id", default="")
    args = parser.parse_args(argv)

    if args.schedule_id:
        from src.scheduling.executor import ScheduleExecutor

        return 0 if ScheduleExecutor().run(args.schedule_id) else 1

    from src.app import run_app

    run_app()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level startup logging for double-click launches.
        _write_startup_error(exc)
        print(STARTUP_ERROR_MESSAGE, file=sys.stderr)
        print(f"جزئیات در {STARTUP_LOG_PATH} ذخیره شد.", file=sys.stderr)
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        _show_startup_error_message()
        raise SystemExit(1) from exc
