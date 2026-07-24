"""Local-time schedule helpers and Persian weekday mapping."""
from __future__ import annotations
import re
from datetime import datetime, time, timedelta

PERSIAN_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
WINDOWS_WEEKDAYS = {"شنبه":"SAT", "یکشنبه":"SUN", "دوشنبه":"MON", "سه‌شنبه":"TUE", "چهارشنبه":"WED", "پنجشنبه":"THU", "جمعه":"FRI"}

def validate_time(value: str) -> bool:
    """Return True for strict HH:MM 24-hour local time."""
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value))

def parse_time(value: str) -> time:
    """Parse HH:MM or raise ValueError with Persian text."""
    if not validate_time(value):
        raise ValueError("فرمت ساعت باید HH:MM و معتبر باشد.")
    h, m = map(int, value.split(":"))
    return time(h, m)

def windows_weekday(persian: str) -> str:
    """Map Persian weekday to schtasks /D value."""
    try: return WINDOWS_WEEKDAYS[persian]
    except KeyError as exc: raise ValueError(f"روز هفته نامعتبر است: {persian}") from exc

def actual_run_time(start_time: str, early_minutes: int) -> tuple[str, int]:
    """Return HH:MM actual run time and day offset (-1 if previous day)."""
    parsed = parse_time(start_time)
    base = datetime(2000, 1, 2, parsed.hour, parsed.minute)
    actual = base - timedelta(minutes=max(0, int(early_minutes)))
    return actual.strftime("%H:%M"), (actual.date() - base.date()).days
