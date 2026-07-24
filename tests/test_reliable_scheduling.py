from __future__ import annotations
from datetime import datetime, timedelta
from unittest.mock import Mock
import re
import pytest
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import convert_12h_to_24h, convert_24h_to_12h, actual_run_time, effective_for_weekday, next_run_datetime, format_12h
import src.scheduling.worker_task as worker_task
from src.scheduling.worker_task import WorkerTaskScheduler, WORKER_TASK_NAME, build_worker_task_xml, build_worker_command, format_run_command, project_root
from src.scheduling.schedule_lock import ScheduleLock
from src import schedule_worker

@pytest.mark.parametrize('h,m,p,out', [(12,0,'AM','00:00'),(12,0,'PM','12:00'),(1,0,'PM','13:00'),(11,59,'PM','23:59'),(12,30,'AM','00:30')])
def test_12_to_24(h,m,p,out): assert convert_12h_to_24h(h,m,p)==out
@pytest.mark.parametrize('inp,out', [('00:00',('12','00','AM')),('12:30',('12','30','PM')),('13:30',('01','30','PM')),('09:15',('09','15','AM')),('23:59',('11','59','PM'))])
def test_24_to_12(inp,out): assert convert_24h_to_12h(inp)==out
@pytest.mark.parametrize('h,m,p', [(0,0,'AM'),(13,0,'AM'),(1,60,'AM'),(1,0,'XX')])
def test_invalid_ui_time(h,m,p):
    with pytest.raises(ValueError): convert_12h_to_24h(h,m,p)
def test_early_and_previous_day():
    assert actual_run_time('12:00',10)==('11:50',0)
    assert actual_run_time('00:05',10)==('23:55',-1)
    assert effective_for_weekday('دوشنبه','00:05',10)==('23:55','یکشنبه')
def test_task_uses_effective_time_and_settings(monkeypatch):
    monkeypatch.setattr(worker_task, 'is_windows', lambda: True)
    runner=Mock(return_value=Mock(returncode=0,stdout='ok',stderr=''))
    s=ClassSchedule(id='abc', class_start_time='12:00', start_time='12:00', early_minutes=10, launch_adobe_connect=True)
    r=WorkerTaskScheduler(runner).register()
    assert r.success
    assert 'StartWhenAvailable' in r.task_xml and 'true' in r.task_xml
    assert 'MultipleInstancesPolicy' in r.task_xml and 'IgnoreNew' in r.task_xml
    assert 'InteractiveToken' in r.task_xml
    assert str(project_root()) in r.task_xml
    assert 'schedule_worker.py' in r.task_xml and 'abc' not in r.task_xml and '<LogonTrigger>' in r.task_xml
    assert 'password' not in r.task_xml.lower()
def test_weekly_next_run_future():
    s=ClassSchedule(recurrence='weekly', effective_run_time='09:15', effective_run_weekday='یکشنبه')
    assert next_run_datetime(s, datetime(2026,7,24,10,0)) > datetime(2026,7,24,10,0)
def test_once_past_detectable():
    s=ClassSchedule(recurrence='once', effective_run_date='2020-01-01', effective_run_time='00:00')
    assert next_run_datetime(s) < datetime.now()
def test_late_limit():
    s=ClassSchedule(recurrence='once', effective_run_date=(datetime.now()-timedelta(minutes=45)).date().isoformat(), effective_run_time=(datetime.now()-timedelta(minutes=45)).strftime('%H:%M'), max_late_start_minutes=15)
    from src.scheduling.executor import ScheduleExecutor
    assert not ScheduleExecutor()._late_allowed(s)
def test_schedule_lock_blocks_second(tmp_path):
    with ScheduleLock('x', tmp_path):
        with pytest.raises(RuntimeError):
            with ScheduleLock('x', tmp_path): pass
def test_display_and_storage_formats():
    s=ClassSchedule(class_start_time=convert_12h_to_24h('12','00','PM'))
    assert s.class_start_time=='12:00' and format_12h(s.class_start_time)=='12:00 PM'
def test_command_credential_free():
    cmd=build_worker_command()
    assert 'schedule_worker.py' in cmd[-1] and not any('password' in p.lower() for p in cmd)

def test_windows_command_quotes_project_paths():
    cmd = build_worker_command(executable=r'C:\Program Files\Python\python.exe', script=r'C:\Class Bot\schedule_worker.py')
    rendered = format_run_command(cmd)
    assert rendered == r'"C:\Program Files\Python\python.exe" "C:\Class Bot\schedule_worker.py"'
    xml = build_worker_task_xml()
    assert '<WorkingDirectory>' in xml and str(project_root()) in xml
def test_worker_task_is_singleton():
    xml = build_worker_task_xml()
    assert WORKER_TASK_NAME == "VadanaClassBot-Worker"
    assert "schedule_worker.py" in xml
    assert "RestartOnFailure" in xml
    assert "ExecutionTimeLimit>PT0S" in xml
