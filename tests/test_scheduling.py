from __future__ import annotations
import json, threading
from pathlib import Path
from unittest.mock import Mock
import pytest
from src.classes import CLASS_PRESETS
from src.config.manager import CONFIG_PATH, PROJECT_ROOT, ConfigManager, default_vadana_profile
from src.scheduling.models import ClassSchedule
from src.scheduling.time_utils import actual_run_time, validate_time, windows_weekday
import src.scheduling.windows_task_scheduler as windows_task_scheduler
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
    assert 'scheduled_runner.py' in ' '.join(cmd) and cmd[-1] == 'fake-id' and 'password' not in ' '.join(cmd).lower()

def test_config_migration_and_no_password(tmp_path: Path):
    p=tmp_path/'config.json'; p.write_text(json.dumps({'profile_name':'x','schedules':[{'class_name':'c','password':'secret'}]}),encoding='utf-8')
    c=ConfigManager(p).load(); assert c.schedules[0].class_name=='c'
    ConfigManager(p).save(c); assert 'secret' not in p.read_text(encoding='utf-8')

def test_default_config_path_is_project_absolute():
    assert CONFIG_PATH == PROJECT_ROOT / 'config.json'
    assert CONFIG_PATH.is_absolute()

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
    monkeypatch.setattr(windows_task_scheduler, 'is_windows', lambda: True)
    runner=Mock(return_value=Mock(returncode=0,stdout='ok',stderr=''))
    r=WindowsTaskScheduler(runner).register(ClassSchedule(id='abc', weekday='شنبه'))
    assert r.success; assert runner.call_args[0][0][0]=='schtasks.exe'
    d=WindowsTaskScheduler(runner).delete('abc'); assert d.success
