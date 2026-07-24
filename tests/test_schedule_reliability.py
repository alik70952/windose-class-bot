from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import Mock
import os
import pytest
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import convert_12h_to_24h, convert_24h_to_12h, actual_run_time, next_run_datetime, validate_12h, is_too_late, shift_weekday
from src.scheduling.windows_task_scheduler import WindowsTaskScheduler, build_task_xml, build_run_command
from src.scheduling.profile_lock import ProfileLock

def test_required_12h_conversions():
    assert convert_12h_to_24h(12,0,'AM')=='00:00'
    assert convert_12h_to_24h(12,0,'PM')=='12:00'
    assert convert_12h_to_24h(1,0,'PM')=='13:00'
    assert convert_12h_to_24h(11,59,'PM')=='23:59'
    assert convert_24h_to_12h('00:00')==('12','00','AM')
    assert convert_24h_to_12h('12:30')==('12','30','PM')
    assert convert_24h_to_12h('13:30')==('01','30','PM')

def test_invalid_12h_inputs_rejected():
    with pytest.raises(ValueError): validate_12h(0,0,'AM')
    with pytest.raises(ValueError): validate_12h(13,0,'AM')
    with pytest.raises(ValueError): validate_12h(12,0,'NOON')

def test_early_minutes_and_midnight_day_boundary():
    assert actual_run_time('12:00',10)==('11:50',0)
    assert actual_run_time('00:05',10)==('23:55',-1)
    assert shift_weekday('دوشنبه', -1)=='یکشنبه'

def test_task_uses_effective_run_time_and_noon_midnight(monkeypatch):
    monkeypatch.setattr('os.name','nt')
    runner=Mock(return_value=Mock(returncode=0,stdout='ok --run-schedule noon',stderr=''))
    noon=ClassSchedule(id='noon', start_time=convert_12h_to_24h(12,0,'PM'), early_minutes=0)
    midnight=ClassSchedule(id='midnight', start_time=convert_12h_to_24h(12,0,'AM'), early_minutes=0)
    r=WindowsTaskScheduler(runner).register(noon)
    assert r.success and '12:00' in r.args and '00:00' not in r.args
    r2=WindowsTaskScheduler(runner).register(midnight)
    assert r2.success and '00:00' in r2.args

def test_next_weekly_and_past_once_rejected():
    now=datetime(2026,7,24,10,0) # Friday
    nxt=next_run_datetime('weekly','', 'یکشنبه', '12:00', 10, now)
    assert nxt and nxt > now and nxt.strftime('%H:%M')=='11:50'
    assert next_run_datetime('once','2020-01-01','یکشنبه','12:00',0,now) is None

def test_start_when_available_and_command_without_password():
    s=ClassSchedule(id='abc', start_time='12:00')
    xml=build_task_xml(s)
    assert '<StartWhenAvailable>true</StartWhenAvailable>' in xml
    assert '<WakeToRun>true</WakeToRun>' in xml
    assert 'secret' not in xml.lower() and 'password' not in xml.lower()
    cmd=' '.join(build_run_command('abc'))
    assert '--run-schedule' in cmd and 'abc' in cmd and 'password' not in cmd.lower()

def test_too_late_limit():
    s=ClassSchedule(recurrence='once', date='2026-07-24', start_time='12:00', early_minutes=0, max_late_start_minutes=15)
    assert not is_too_late(s, datetime(2026,7,24,12,7))
    assert is_too_late(s, datetime(2026,7,24,12,45))

def test_duplicate_lock_stops_second_run(tmp_path):
    a=ProfileLock('schedule1', tmp_path); b=ProfileLock('schedule1', tmp_path)
    assert a.acquire() and not b.acquire(); a.release()

def test_temp_two_minute_schedule_shape_and_delete_task(monkeypatch):
    monkeypatch.setattr('os.name','nt')
    runner=Mock(return_value=Mock(returncode=0,stdout='ok --run-schedule test_1',stderr=''))
    s=ClassSchedule(id='test_1', is_test=True, recurrence='once', date='2026-07-24', start_time='12:02', early_minutes=0)
    r=WindowsTaskScheduler(runner).register(s)
    assert r.success and 'test_1' in r.args and '--run-schedule' in r.args
    d=WindowsTaskScheduler(runner).delete(s.id)
    assert d.success

def test_edit_am_pm_and_early_changes_effective_time():
    s=ClassSchedule(start_time=convert_12h_to_24h(12,0,'AM'), early_minutes=0); s.recalculate_effective_time(); assert s.task_time=='00:00'
    s.start_time=convert_12h_to_24h(12,0,'PM'); s.recalculate_effective_time(); assert s.start_time=='12:00' and s.task_time=='12:00'
    s.early_minutes=10; s.recalculate_effective_time(); assert s.task_time=='11:50'
