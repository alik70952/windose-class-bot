"""Local-time schedule helpers and Persian weekday mapping."""
from __future__ import annotations
import re
from datetime import date, datetime, time, timedelta

PERSIAN_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
WINDOWS_WEEKDAYS = {"شنبه":"SAT", "یکشنبه":"SUN", "دوشنبه":"MON", "سه‌شنبه":"TUE", "چهارشنبه":"WED", "پنجشنبه":"THU", "جمعه":"FRI"}

def validate_time(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value or ""))

def parse_time(value: str) -> time:
    if not validate_time(value):
        raise ValueError("فرمت ساعت باید HH:MM و معتبر باشد.")
    h, m = map(int, value.split(":")); return time(h, m)

def convert_12h_to_24h(hour: int | str, minute: int | str, period: str) -> str:
    """Convert validated 12-hour local UI time to internal HH:MM."""
    h = int(hour); m = int(minute); p = (period or "").upper()
    if h < 1 or h > 12: raise ValueError("ساعت باید بین 01 تا 12 باشد.")
    if m < 0 or m > 59: raise ValueError("دقیقه باید بین 00 تا 59 باشد.")
    if p not in {"AM", "PM"}: raise ValueError("دوره باید AM یا PM باشد.")
    if p == "AM": h24 = 0 if h == 12 else h
    else: h24 = 12 if h == 12 else h + 12
    return f"{h24:02d}:{m:02d}"

def convert_24h_to_12h(time_value: str) -> tuple[str, str, str]:
    parsed = parse_time(time_value)
    period = "AM" if parsed.hour < 12 else "PM"
    hour = parsed.hour % 12 or 12
    return f"{hour:02d}", f"{parsed.minute:02d}", period

def format_12h(time_value: str) -> str:
    h, m, p = convert_24h_to_12h(time_value); return f"{h}:{m} {p}"

def windows_weekday(persian: str) -> str:
    try: return WINDOWS_WEEKDAYS[persian]
    except KeyError as exc: raise ValueError(f"روز هفته نامعتبر است: {persian}") from exc

def previous_weekday(persian: str) -> str:
    idx = PERSIAN_WEEKDAYS.index(persian); return PERSIAN_WEEKDAYS[(idx - 1) % 7]

def actual_run_time(start_time: str, early_minutes: int) -> tuple[str, int]:
    parsed = parse_time(start_time)
    base = datetime(2000, 1, 2, parsed.hour, parsed.minute)
    actual = base - timedelta(minutes=max(0, int(early_minutes)))
    return actual.strftime("%H:%M"), (actual.date() - base.date()).days

def effective_for_weekday(class_weekday: str, class_start_time: str, early_minutes: int) -> tuple[str, str]:
    run_time, offset = actual_run_time(class_start_time, early_minutes)
    return run_time, previous_weekday(class_weekday) if offset < 0 else class_weekday

def effective_for_date(class_date: str, class_start_time: str, early_minutes: int) -> tuple[str, str]:
    d = date.fromisoformat(class_date); run_time, offset = actual_run_time(class_start_time, early_minutes)
    return run_time, (d + timedelta(days=offset)).isoformat()

def next_run_datetime(schedule, now: datetime | None = None) -> datetime:
    now = now or datetime.now(); run_t = parse_time(schedule.effective_run_time)
    if schedule.recurrence == "once":
        return datetime.combine(date.fromisoformat(schedule.effective_run_date or schedule.date), run_t)
    weekday = schedule.effective_run_weekday or schedule.weekday
    target = PERSIAN_WEEKDAYS.index(weekday)
    current = (now.weekday() + 2) % 7  # Python Mon=0, Persian Sat=0
    days = (target - current) % 7
    candidate = datetime.combine(now.date() + timedelta(days=days), run_t)
    if candidate <= now: candidate += timedelta(days=7)
    return candidate

def remaining_text(target: datetime, now: datetime | None = None) -> str:
    delta = target - (now or datetime.now())
    if delta.total_seconds() < 0: return "گذشته"
    days, rem = divmod(int(delta.total_seconds()), 86400); hours = rem // 3600; minutes = (rem % 3600) // 60
    return f"{days} روز و {hours} ساعت" if days else f"{hours} ساعت و {minutes} دقیقه"
