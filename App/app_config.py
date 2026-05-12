from __future__ import annotations

import os
from datetime import date
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent


def load_dotenv(path: Path = ROOT_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT_DIR / path


load_dotenv()

DATA_DIR = env_path("TIME_OUTPUT_DATA_DIR", ROOT_DIR / "Data")
DASHBOARD_DIR = env_path("TIME_OUTPUT_DASHBOARD_DIR", ROOT_DIR / "Dashboard")
DB_PATH = env_path("TIME_OUTPUT_DB_PATH", DATA_DIR / "time_tracking.sqlite")
STATIC_DATA_PATH = env_path("TIME_OUTPUT_STATIC_DATA_PATH", DASHBOARD_DIR / "data" / "app-data.json")

TIMEZONE_NAME = os.environ.get("TIME_OUTPUT_TIMEZONE", "America/Denver")
TRACKING_START_DATE = date.fromisoformat(os.environ.get("TIME_OUTPUT_TRACKING_START_DATE", "2026-01-01"))
DEFAULT_CALENDAR_START = os.environ.get(
    "TIME_OUTPUT_CALENDAR_START",
    f"{TRACKING_START_DATE.isoformat()}T00:00:00",
)
DAY_START_HOUR = int(os.environ.get("TIME_OUTPUT_DAY_START_HOUR", "5"))

GOOGLE_CALENDAR_ID = os.environ.get("TIME_OUTPUT_GOOGLE_CALENDAR_ID", "primary")
GOOGLE_CREDENTIALS_PATH = env_path("TIME_OUTPUT_GOOGLE_CREDENTIALS_PATH", DATA_DIR / "google_credentials.json")
GOOGLE_TOKEN_PATH = env_path("TIME_OUTPUT_GOOGLE_TOKEN_PATH", DATA_DIR / "google_token.json")
SERVE_STATIC_EXPORT = os.environ.get("TIME_OUTPUT_SERVE_STATIC_EXPORT", "0") == "1"
