"""Local-time schedule helpers and Persian weekday mapping."""
from __future__ import annotations
import re
from datetime import date, datetime, time, timedelta

PERSIAN_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
WINDOWS_WEEKDAYS = {"شنبه":"SAT", "یکشنبه":"SUN", "دوشنبه":"MON", "سه‌شنبه":"TUE", "چهارشنبه":"WED", "پنجشنبه":"THU", "جمعه":"FRI"}
_PY_WEEKDAY_TO_PERSIAN = {5:"شنبه", 6:"یکشنبه", 0:"دوشنبه", 1:"سه‌شنبه", 2:"چهارشنبه", 3:"پنجشنبه", 4:"جمعه"}
_PERSIAN_TO_PY_WEEKDAY = {v:k for k,v in _PY_WEEKDAY_TO_PERSIAN.items()}

def validate_time(value: str) -> bool:
    """Return True for strict HH:MM 24-hour local time."""
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value or ""))

def parse_time(value: str) -> time:
    """Parse HH:MM or raise ValueError with Persian text."""
    if not validate_time(value):
        raise ValueError("فرمت ساعت باید HH:MM و معتبر باشد.")
    h, m = map(int, value.split(":"))
    return time(h, m)

def validate_12h_parts(hour: int | str, minute: int | str, period: str) -> tuple[int, int, str]:
    """Validate 12-hour UI parts and normalize AM/PM."""
    try:
        h, m = int(hour), int(minute)
    except (TypeError, ValueError) as exc:
        raise ValueError("ساعت و دقیقه باید عددی باشند.") from exc
    p = str(period).strip().upper()
    if h < 1 or h > 12:
        raise ValueError("ساعت باید بین 01 تا 12 باشد.")
    if m < 0 or m > 59:
        raise ValueError("دقیقه باید بین 00 تا 59 باشد.")
    if p not in {"AM", "PM"}:
        raise ValueError("دوره زمانی فقط می‌تواند AM یا PM باشد.")
    return h, m, p

def convert_12h_to_24h(hour: int | str, minute: int | str, period: str) -> str:
    """Convert safe 12-hour UI input to canonical HH:MM local time."""
    h, m, p = validate_12h_parts(hour, minute, period)
    if p == "AM":
        hour24 = 0 if h == 12 else h
    else:
        hour24 = 12 if h == 12 else h + 12
    return f"{hour24:02d}:{m:02d}"

def convert_24h_to_12h(value: str) -> tuple[str, str, str]:
    """Convert canonical HH:MM to zero-padded 12-hour display parts."""
    parsed = parse_time(value)
    period = "AM" if parsed.hour < 12 else "PM"
    hour = parsed.hour % 12 or 12
    return f"{hour:02d}", f"{parsed.minute:02d}", period

def format_12h(value: str) -> str:
    h, m, p = convert_24h_to_12h(value)
    return f"{h}:{m} {p}"

def windows_weekday(persian: str) -> str:
    """Map Persian weekday to schtasks /D value."""
    try: return WINDOWS_WEEKDAYS[persian]
    except KeyError as exc: raise ValueError(f"روز هفته نامعتبر است: {persian}") from exc

def actual_run_time(start_time: str, early_minutes: int) -> tuple[str, int]:
    """Return HH:MM effective run time and day offset (-1 if previous day)."""
    parsed = parse_time(start_time)
    base = datetime(2000, 1, 2, parsed.hour, parsed.minute)
    actual = base - timedelta(minutes=max(0, int(early_minutes)))
    return actual.strftime("%H:%M"), (actual.date() - base.date()).days

def effective_run_datetime(class_date: date, class_start_time: str, early_minutes: int) -> datetime:
    parsed = parse_time(class_start_time)
    return datetime.combine(class_date, parsed) - timedelta(minutes=max(0, int(early_minutes)))

def adjusted_weekday(weekday: str, day_offset: int) -> str:
    idx = PERSIAN_WEEKDAYS.index(weekday)
    return PERSIAN_WEEKDAYS[(idx + day_offset) % 7]

def next_run_datetime(recurrence: str, weekday: str, date_value: str, start_time: str, early_minutes: int, now: datetime | None = None) -> datetime:
    """Compute nearest future effective run using local system time."""
    now = now or datetime.now()
    if recurrence == "once":
        try:
            class_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("تاریخ باید با قالب YYYY-MM-DD معتبر باشد.") from exc
        return effective_run_datetime(class_date, start_time, early_minutes)
    if weekday not in _PERSIAN_TO_PY_WEEKDAY:
        raise ValueError("روز هفته برای زمان‌بندی هفتگی معتبر نیست.")
    days = (_PERSIAN_TO_PY_WEEKDAY[weekday] - now.weekday()) % 7
    candidate = effective_run_datetime((now + timedelta(days=days)).date(), start_time, early_minutes)
    if candidate <= now:
        candidate = effective_run_datetime((now + timedelta(days=days + 7)).date(), start_time, early_minutes)
    return candidate

def remaining_text(target: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now(); delta = target - now
    if delta.total_seconds() <= 0: return "گذشته"
    days = delta.days; hours = delta.seconds // 3600; minutes = (delta.seconds % 3600) // 60
    parts=[]
    if days: parts.append(f"{days} روز")
    if hours: parts.append(f"{hours} ساعت")
    if minutes or not parts: parts.append(f"{minutes} دقیقه")
    return " و ".join(parts)

def is_too_late_to_start(schedule, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    due = next_run_datetime(schedule.recurrence, schedule.weekday, schedule.date, schedule.start_time, schedule.early_minutes, now - timedelta(days=8))
    while schedule.recurrence == "weekly" and due + timedelta(days=7) <= now:
        due += timedelta(days=7)
    late = (now - due).total_seconds() / 60
    return late > getattr(schedule, "max_late_start_minutes", 15)
