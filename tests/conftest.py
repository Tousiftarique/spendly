import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def app(tmp_path, monkeypatch):
    from database import db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")

    if "app" in sys.modules:
        app_module = importlib.reload(sys.modules["app"])
    else:
        import app as app_module

    app_module.app.config.update(TESTING=True)
    yield app_module.app
