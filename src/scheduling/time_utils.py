"""Local-time schedule helpers, 12-hour conversion, and Persian weekday mapping."""
from __future__ import annotations
import re
from datetime import date, datetime, time, timedelta

PERSIAN_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
WINDOWS_WEEKDAYS = {"شنبه":"SAT", "یکشنبه":"SUN", "دوشنبه":"MON", "سه‌شنبه":"TUE", "چهارشنبه":"WED", "پنجشنبه":"THU", "جمعه":"FRI"}
PY_WEEKDAY_TO_PERSIAN = {5:"شنبه", 6:"یکشنبه", 0:"دوشنبه", 1:"سه‌شنبه", 2:"چهارشنبه", 3:"پنجشنبه", 4:"جمعه"}
PERSIAN_TO_PY_WEEKDAY = {v:k for k,v in PY_WEEKDAY_TO_PERSIAN.items()}

def validate_time(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value or ""))

def parse_time(value: str) -> time:
    if not validate_time(value):
        raise ValueError("فرمت ساعت باید HH:MM و معتبر باشد.")
    h, m = map(int, value.split(":")); return time(h, m)

def validate_12h(hour: int | str, minute: int | str, period: str) -> tuple[int, int, str]:
    try: h, m = int(hour), int(minute)
    except (TypeError, ValueError) as exc: raise ValueError("ساعت و دقیقه باید عدد باشند.") from exc
    p = (period or "").strip().upper()
    if h < 1 or h > 12: raise ValueError("ساعت باید بین 01 تا 12 باشد.")
    if m < 0 or m > 59: raise ValueError("دقیقه باید بین 00 تا 59 باشد.")
    if p not in {"AM", "PM"}: raise ValueError("دوره ساعت فقط AM یا PM است.")
    return h, m, p

def convert_12h_to_24h(hour: int | str, minute: int | str, period: str) -> str:
    h, m, p = validate_12h(hour, minute, period)
    if p == "AM": h24 = 0 if h == 12 else h
    else: h24 = 12 if h == 12 else h + 12
    return f"{h24:02d}:{m:02d}"

def convert_24h_to_12h(value: str) -> tuple[str, str, str]:
    t = parse_time(value)
    period = "AM" if t.hour < 12 else "PM"
    h = t.hour % 12 or 12
    return f"{h:02d}", f"{t.minute:02d}", period

def format_12h(value: str) -> str:
    h, m, p = convert_24h_to_12h(value); return f"{h}:{m} {p}"

def windows_weekday(persian: str) -> str:
    try: return WINDOWS_WEEKDAYS[persian]
    except KeyError as exc: raise ValueError(f"روز هفته نامعتبر است: {persian}") from exc

def shift_weekday(persian: str, offset_days: int) -> str:
    idx = PERSIAN_WEEKDAYS.index(persian)
    return PERSIAN_WEEKDAYS[(idx + offset_days) % 7]

def actual_run_time(start_time: str, early_minutes: int) -> tuple[str, int]:
    parsed = parse_time(start_time)
    base = datetime(2000, 1, 3, parsed.hour, parsed.minute)
    actual = base - timedelta(minutes=max(0, int(early_minutes)))
    return actual.strftime("%H:%M"), (actual.date() - base.date()).days

def effective_run_datetime(class_date: date, start_time: str, early_minutes: int) -> datetime:
    parsed = parse_time(start_time)
    return datetime.combine(class_date, parsed) - timedelta(minutes=max(0, int(early_minutes)))

def next_run_datetime(recurrence: str, class_date: str, weekday: str, start_time: str, early_minutes: int, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    if recurrence == "disabled": return None
    if recurrence == "once":
        if not class_date: return None
        run = effective_run_datetime(date.fromisoformat(class_date), start_time, early_minutes)
        return run if run >= now else None
    if recurrence == "weekly":
        target = PERSIAN_TO_PY_WEEKDAY[weekday]
        days = (target - now.weekday()) % 7
        class_day = now.date() + timedelta(days=days)
        run = effective_run_datetime(class_day, start_time, early_minutes)
        if run < now:
            run = effective_run_datetime(class_day + timedelta(days=7), start_time, early_minutes)
        return run
    return None

def scheduled_run_for_lateness(schedule, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    if schedule.recurrence == 'once':
        if not schedule.date: return None
        return effective_run_datetime(date.fromisoformat(schedule.date), schedule.start_time, schedule.early_minutes)
    if schedule.recurrence == 'weekly':
        target = PERSIAN_TO_PY_WEEKDAY[schedule.weekday]
        days_since = (now.weekday() - target) % 7
        class_day = now.date() - timedelta(days=days_since)
        run = effective_run_datetime(class_day, schedule.start_time, schedule.early_minutes)
        if run > now:
            run = effective_run_datetime(class_day - timedelta(days=7), schedule.start_time, schedule.early_minutes)
        return run
    return None

def is_too_late(schedule, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    run = scheduled_run_for_lateness(schedule, now)
    if run is None: return False
    return now > run + timedelta(minutes=getattr(schedule, 'max_late_start_minutes', 15))
