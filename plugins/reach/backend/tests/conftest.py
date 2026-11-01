"""Uses the API test database and client. Reach tests live with the plugin."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["DEFAULT_TENANT"] = ""
os.environ["JWT_SECRET"] = "test-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "test-pin-pepper-16chars"
os.environ["ENCRYPTION_SECRET"] = "test-encryption-secret-32-chars!"
os.environ["API_KEY"] = "test-api-key-value"
os.environ["API_HOST"] = "127.0.0.1"
os.environ["API_PORT"] = "8000"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["SYNC_MAX_BATCH_SIZE"] = "100"
os.environ["LOGIN_MAX_ATTEMPTS"] = "3"
os.environ["LOGIN_LOCKOUT_MINUTES"] = "15"
os.environ["SCHEDULER_ENABLED"] = "false"

ROOT = Path(__file__).resolve().parents[4]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API / "tests"))
sys.path.insert(0, str(API))
sys.path.insert(0, str(ROOT / "plugins" / "reach"))

_spec = importlib.util.spec_from_file_location("api_tests_conftest", API / "tests" / "conftest.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules["api_tests_conftest"] = _module
_spec.loader.exec_module(_module)

session = _module.session
client = _module.client
_isolated_limits = _module._isolated_limits
