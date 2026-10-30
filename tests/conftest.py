import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    """설정·저장 폴더를 임시 폴더로 (진짜 fetch_settings.json 을 건드리지 않게)."""
    from app import settings
    monkeypatch.setattr(settings, "APP_DIR", str(tmp_path))
    return tmp_path
