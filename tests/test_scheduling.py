from __future__ import annotations
import json, threading
from pathlib import Path
from unittest.mock import Mock
import pytest
from src.classes import CLASS_PRESETS
from src.config.manager import ConfigManager, default_vadana_profile
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import actual_run_time, validate_time, windows_weekday
from src.scheduling.windows_task_scheduler import build_run_command, sanitize_task_name, WindowsTaskScheduler
from src.scheduling.executor import should_retry
from src.scheduling.profile_lock import ProfileLock
from src.sites.vadana_sum39 import CourseSelectionError, normalize_persian_text, sanitize_diagnostic, VadanaSum39Adapter

class L:
    def __init__(self, text='', visible=True): self.text=text; self.visible=visible; self.clicked=False; self.first=self
    def wait_for(self, state='visible', timeout=0):
        if not self.visible: raise TimeoutError()
    def inner_text(self, timeout=0): return self.text
    def click(self, timeout=0): self.clicked=True
    def is_visible(self, timeout=0): return self.visible
class ListLoc:
    def __init__(self, items): self.items=items; self.first=items[0] if items else L('',False)
    def count(self): return len(self.items)
    def nth(self,i): return self.items[i]
    def wait_for(self,*a,**k): return self.first.wait_for(*a,**k)
class Page:
    def __init__(self, links, title='انس با قرآن کریم'):
        self.links=[L(x) for x in links]; self.title=title; self.url='https://x/course/view.php?id=1'
    def get_by_text(self, text, exact=False):
        if text in ['درس‌های من','کلاس آنلاین']: return L(text)
        for l in self.links:
            if l.text==text: return l
        raise TimeoutError()
    def get_by_role(self, role, name, exact=False):
        if role=='link':
            for l in self.links:
                if l.text==name: return l
        raise TimeoutError()
    def locator(self, selector):
        if selector=='a': return ListLoc(self.links)
        return ListLoc([L(self.title)])
    def wait_for_load_state(self,*a,**k): pass

def test_presets_and_defaults():
    assert len(CLASS_PRESETS)==3
    assert CLASS_PRESETS[0].start_time=='09:15' and CLASS_PRESETS[1].weekday=='شنبه'

def test_edit_schedule_time():
    s=ClassSchedule(start_time='09:15'); s.start_time='10:00'; assert s.start_time=='10:00'

def test_actual_time_and_previous_day():
    assert actual_run_time('09:15',5)==('09:10',0)
    assert actual_run_time('00:03',5)==('23:58',-1)

def test_validate_time():
    assert validate_time('13:30') and not validate_time('25:80')

def test_windows_weekday_mapping():
    assert windows_weekday('یکشنبه')=='SUN'

def test_safe_task_name_and_command_has_no_credential():
    s='abc; شماره 123'; name=sanitize_task_name(s)
    assert name.startswith('WindowsClassBot_') and ';' not in name and 'شماره' not in name
    cmd=build_run_command('fake-id')
    assert '--run-schedule' in cmd and 'password' not in ' '.join(cmd).lower()

def test_config_migration_and_no_password(tmp_path: Path):
    p=tmp_path/'config.json'; p.write_text(json.dumps({'profile_name':'x','schedules':[{'class_name':'c','password':'secret'}]}),encoding='utf-8')
    c=ConfigManager(p).load(); assert c.schedules[0].class_name=='c'
    ConfigManager(p).save(c); assert 'secret' not in p.read_text(encoding='utf-8')

def test_normalize_persian_variants():
    assert normalize_persian_text('عربي ي ك ۱۲') == normalize_persian_text('عربی ی ک 12')
    assert normalize_persian_text('نیم\u200c فاصله   (ره)') == normalize_persian_text('نیم فاصله （ره）')

def test_exact_course_found_and_title_verified():
    p=Page(['انس با قرآن کریم']); VadanaSum39Adapter().open_course(p,'انس با قرآن کریم',100,threading.Event()); assert p.links[0].clicked

def test_similar_not_clicked():
    p=Page(['انس با قرآن']);
    with pytest.raises(CourseSelectionError): VadanaSum39Adapter().open_course(p,'انس با قرآن کریم',100,threading.Event())
    assert not p.links[0].clicked

def test_multiple_similar_detected():
    p=Page(['انس با قرآن کریم','انس با قرآن كريم'])
    with pytest.raises(CourseSelectionError, match='چند درس'): VadanaSum39Adapter().open_course(p,'انس با قرآن کریم',100,threading.Event())

def test_enter_class_not_archive():
    p=Page(['مشاهده آرشیو جلسات','ورود به کلاس']); VadanaSum39Adapter().enter_online_class(p,'x',100,threading.Event())
    assert p.links[1].clicked and not p.links[0].clicked

def test_title_mismatch_blocks_entry():
    with pytest.raises(CourseSelectionError): VadanaSum39Adapter()._verify_course_page(Page([], 'درس دیگر'),'انس با قرآن کریم',100,threading.Event())

def test_popup_mock_placeholder():
    assert Page(['ورود به کلاس']).url.startswith('https://')

def test_retry_rules():
    assert should_retry(TimeoutError('network')) and not should_retry(ValueError('رمز اشتباه'))

def test_profile_lock(tmp_path: Path):
    a=ProfileLock('p', tmp_path); b=ProfileLock('p', tmp_path); assert a.acquire(); assert not b.acquire(); a.release(); assert b.acquire(); b.release()

def test_sanitize_error_url():
    assert 'abc' not in sanitize_diagnostic('https://x/?token=abc')

def test_cli_fake_id(monkeypatch):
    from main import main
    monkeypatch.setattr('sys.argv',['main.py','--run-schedule','fake'])
    assert main()==1

def test_task_scheduler_mock(monkeypatch):
    monkeypatch.setattr('os.name','nt')
    runner=Mock(return_value=Mock(returncode=0,stdout='ok',stderr=''))
    r=WindowsTaskScheduler(runner).register(ClassSchedule(id='abc', weekday='شنبه'))
    assert r.success; assert runner.call_args[0][0][0]=='schtasks.exe'
    d=WindowsTaskScheduler(runner).delete('abc'); assert d.success

from datetime import datetime
from src.scheduling.time_utils import convert_12h_to_24h, convert_24h_to_12h, next_run_datetime, is_too_late_to_start, adjusted_weekday


def test_12h_to_24h_required_edges():
    assert convert_12h_to_24h(12,0,'AM') == '00:00'
    assert convert_12h_to_24h(12,0,'PM') == '12:00'
    assert convert_12h_to_24h(1,0,'PM') == '13:00'
    assert convert_12h_to_24h(11,59,'PM') == '23:59'


def test_24h_to_12h_required_edges():
    assert convert_24h_to_12h('00:00') == ('12','00','AM')
    assert convert_24h_to_12h('12:30') == ('12','30','PM')
    assert convert_24h_to_12h('13:30') == ('01','30','PM')


def test_invalid_12h_ui_parts_rejected():
    with pytest.raises(ValueError): convert_12h_to_24h(0,0,'AM')
    with pytest.raises(ValueError): convert_12h_to_24h(13,0,'AM')
    with pytest.raises(ValueError): convert_12h_to_24h(12,0,'NOON')


def test_noon_and_midnight_effective_task_times(monkeypatch):
    monkeypatch.setattr('os.name','nt')
    runner=Mock(return_value=Mock(returncode=0,stdout='TaskName: WindowsClassBot_noon\nEnabled: Yes\nnoon',stderr=''))
    s=ClassSchedule(id='noon', start_time=convert_12h_to_24h(12,0,'PM'), early_minutes=0)
    r=WindowsTaskScheduler(runner).register(s)
    assert r.success and s.effective_run_time == '12:00'
    s2=ClassSchedule(id='midnight', start_time=convert_12h_to_24h(12,0,'AM'), early_minutes=0)
    WindowsTaskScheduler(runner).register(s2)
    assert s2.effective_run_time == '00:00'


def test_weekly_next_run_and_day_rollover():
    now=datetime(2026,7,19,10,0)  # Sunday
    nxt=next_run_datetime('weekly','یکشنبه','', '12:00', 10, now)
    assert nxt.strftime('%Y-%m-%d %H:%M') == '2026-07-19 11:50'
    assert actual_run_time('00:05',10)==('23:55',-1)
    assert adjusted_weekday('دوشنبه', -1) == 'یکشنبه'


def test_once_past_rejected_by_next_run_check():
    assert next_run_datetime('once','یکشنبه','2026-07-19','12:00',0, datetime(2026,7,20,1,0)) < datetime(2026,7,20,1,0)


def test_start_when_available_and_command_schedule_id(monkeypatch):
    monkeypatch.setattr('os.name','nt')
    calls=[]
    def runner(args, **kwargs):
        calls.append(args)
        return Mock(returncode=0, stdout='Enabled: Yes\nsafeid', stderr='')
    s=ClassSchedule(id='safeid', start_time='13:30', early_minutes=15)
    r=WindowsTaskScheduler(runner).register(s)
    assert r.success and s.effective_run_time == '13:15'
    xml_path=calls[0][calls[0].index('/XML')+1]
    assert '--run-schedule' in ' '.join(build_run_command('safeid'))
    assert 'password' not in ' '.join(calls[0]).lower()


def test_late_start_limit():
    s=ClassSchedule(recurrence='once', date='2026-07-24', start_time='12:00', early_minutes=0, max_late_start_minutes=15)
    assert not is_too_late_to_start(s, datetime(2026,7,24,12,7))
    assert is_too_late_to_start(s, datetime(2026,7,24,12,45))


def test_two_minute_temporary_schedule_model():
    s=ClassSchedule(id='tmp', temporary=True, recurrence='once', date='2026-07-24', start_time='10:42', early_minutes=0)
    assert s.temporary and '--run-schedule' in build_run_command('tmp')
