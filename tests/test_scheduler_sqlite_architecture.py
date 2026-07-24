from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from src.config.manager import ConfigManager
from src.scheduling.executor import ScheduleExecutor
from src.scheduling.schedule_store import ScheduleRecord, ScheduleStore


def record():
    return ScheduleRecord("id", "profile", "Exact Class", 1, 0, 1, created_at_epoch=1, updated_at_epoch=1)


def test_schedules_use_sqlite_not_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"profile_id": "profile", "schedules": [{
        "id": "legacy", "profile_id": "profile", "class_name": "Class", "recurrence": "once",
        "date": "2030-01-01", "effective_run_date": "2030-01-01", "effective_run_time": "01:00"
    }]}), encoding="utf-8")
    manager = ConfigManager(config_path); config = manager.load()
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.scheduler_sqlite_migration_completed and "schedules" not in saved


def test_worker_uses_full_login_flow(tmp_path):
    config = Mock(profile_id="profile", username="user", class_name="")
    config.browser = Mock()
    manager = Mock(); manager.load.return_value = config
    credentials = Mock(); credentials.get_password.return_value = "secret"
    automation = Mock(); automation.login_and_enter_class.return_value = True
    executor = ScheduleExecutor(manager, credentials, store=ScheduleStore(tmp_path / "db"))
    from unittest.mock import patch
    with patch("src.scheduling.executor.BrowserAutomation", return_value=automation):
        assert executor.run_schedule(record())
    automation.login_and_enter_class.assert_called_once()


def test_worker_uses_separate_browser_profile(tmp_path):
    config = Mock(profile_id="profile", username="user", class_name="")
    config.browser = Mock(); manager = Mock(); manager.load.return_value = config
    credentials = Mock(); credentials.get_password.return_value = "secret"
    from unittest.mock import patch
    with patch("src.scheduling.executor.BrowserAutomation") as automation:
        automation.return_value.login_and_enter_class.return_value = True
        ScheduleExecutor(manager, credentials, store=ScheduleStore(tmp_path / "db")).run_schedule(record())
        used_config = automation.return_value.login_and_enter_class.call_args.args[0]
    assert used_config.browser.headless is False
    assert Path(used_config.browser.session_dir).parts[-2:] == ("scheduled", "profile")
