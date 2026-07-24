"""Built-in editable class presets for Vadana schedules."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ClassPreset:
    """A non-sensitive editable class preset."""
    name: str
    weekday: str
    start_time: str
    end_time: str

CLASS_PRESETS: tuple[ClassPreset, ...] = (
    ClassPreset("انس با قرآن کریم", "یکشنبه", "09:15", "12:15"),
    ClassPreset("اندیشه های امامین انقلاب اسلامی و وصایای حضرت امام خمینی(ره)", "شنبه", "13:30", "17:30"),
    ClassPreset("اخلاق اسلامی (مبانی و مفاهیم)", "یکشنبه", "12:30", "17:30"),
)
CUSTOM_CLASS_LABEL = "کلاس سفارشی"
