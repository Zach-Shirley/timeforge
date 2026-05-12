from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import app_config

APP_DIR = app_config.APP_DIR
ROOT_DIR = app_config.ROOT_DIR
DASHBOARD_DIR = app_config.DASHBOARD_DIR
DATA_DIR = app_config.DATA_DIR
DB_PATH = app_config.DB_PATH
try:
    LOCAL_TIMEZONE = ZoneInfo(app_config.TIMEZONE_NAME)
except ZoneInfoNotFoundError:
    LOCAL_TIMEZONE = None


DEFAULT_TARGET = "Targets: 60 PO, 10h drift, 10h physical, 1h spiritual"
DEFAULT_WEEKLY_TARGET = "Targets: 60 PO/week, 10h drift/week, 10h physical/week, 1h spiritual/week"


SEED_REVIEWS: list[dict[str, object]] = []


SCORE_PROFILE = {
    "id": "default-v0",
    "name": "Default V0",
    "config": {
        "productiveOutputTarget": 60,
        "productiveOutputPoints": 60,
        "driftTargetHours": 10,
        "driftZeroLineHours": 20,
        "driftPoints": 20,
        "driftUnderTargetBonusMax": 5,
        "driftUnderTargetBonusPerHour": 0.5,
        "physicalTargetHours": 10,
        "physicalPoints": 15,
        "spiritualTargetHours": 1,
        "spiritualPoints": 5,
        "softWorkWeight": 0.5,
    },
}


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def to_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def today_local_iso() -> str:
    if LOCAL_TIMEZONE is not None:
        return datetime.now(LOCAL_TIMEZONE).date().isoformat()
    return datetime.now().astimezone().date().isoformat()


def init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS score_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                window_start TEXT,
                window_end TEXT,
                pulled_events INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_events_raw (
                calendar_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                summary TEXT,
                start_time TEXT,
                end_time TEXT,
                color_id TEXT,
                raw_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (calendar_id, event_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS normalized_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_event_id TEXT,
                block_start TEXT NOT NULL,
                block_end TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT,
                bucket TEXT,
                confidence REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wake_cycles (
                cycle_date TEXT PRIMARY KEY,
                cycle_start TEXT,
                cycle_end TEXT,
                sleep_hours REAL,
                confidence REAL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS period_reviews (
                id TEXT PRIMARY KEY,
                period_type TEXT NOT NULL CHECK (period_type IN ('week', 'month')),
                label TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                subtitle TEXT NOT NULL,
                target_text TEXT NOT NULL,
                source_text TEXT NOT NULL,
                score_raw REAL NOT NULL,
                score_band TEXT NOT NULL,
                totals_json TEXT NOT NULL,
                score_components_json TEXT NOT NULL,
                review_json TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_period_reviews_type_start ON period_reviews(period_type, period_start DESC)"
        )
        connection.execute(
            """
            INSERT INTO score_profiles (id, name, config_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                config_json = excluded.config_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (SCORE_PROFILE["id"], SCORE_PROFILE["name"], to_json(SCORE_PROFILE["config"])),
        )
        connection.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('google_calendar_connector_probe', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO NOTHING
            """,
            (
                "No Google Calendar sync has been recorded yet. Add OAuth credentials and run a seed sync to populate local data.",
            ),
        )
        for review in SEED_REVIEWS:
            connection.execute(
                """
                INSERT INTO period_reviews (
                    id,
                    period_type,
                    label,
                    period_start,
                    period_end,
                    subtitle,
                    target_text,
                    source_text,
                    score_raw,
                    score_band,
                    totals_json,
                    score_components_json,
                    review_json,
                    detail_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    period_type = excluded.period_type,
                    label = excluded.label,
                    period_start = excluded.period_start,
                    period_end = excluded.period_end,
                    subtitle = excluded.subtitle,
                    target_text = excluded.target_text,
                    source_text = excluded.source_text,
                    score_raw = excluded.score_raw,
                    score_band = excluded.score_band,
                    totals_json = excluded.totals_json,
                    score_components_json = excluded.score_components_json,
                    review_json = excluded.review_json,
                    detail_json = excluded.detail_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    review["id"],
                    review["period_type"],
                    review["label"],
                    review["period_start"],
                    review["period_end"],
                    review["subtitle"],
                    review["target_text"],
                    review["source_text"],
                    review["score_raw"],
                    review["score_band"],
                    to_json(review["totals"]),
                    to_json(review["score_components"]),
                    to_json(review["review"]),
                    to_json(review["detail"]),
                ),
            )


def list_periods(period_type: str) -> list[dict[str, str]]:
    current_date = today_local_iso()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, label
            FROM period_reviews
            WHERE period_type = ? AND period_end < ?
            ORDER BY period_start DESC
            """,
            (period_type, current_date),
        ).fetchall()
    return [{"id": row["id"], "label": row["label"]} for row in rows]


def get_review(period_type: str, review_id: str) -> dict[str, object] | None:
    current_date = today_local_iso()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM period_reviews
            WHERE period_type = ? AND id = ? AND period_end < ?
            """,
            (period_type, review_id, current_date),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "periodStart": row["period_start"],
        "periodEnd": row["period_end"],
        "subtitle": row["subtitle"],
        "targetText": row["target_text"],
        "sourceText": row["source_text"],
        "totals": json.loads(row["totals_json"]),
        "score": {
            "raw": row["score_raw"],
            "band": row["score_band"],
            "components": json.loads(row["score_components_json"]),
        },
        "review": json.loads(row["review_json"]),
        "detail": json.loads(row["detail_json"]),
    }


def review_row_to_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "label": row["label"],
        "periodType": row["period_type"],
        "periodStart": row["period_start"],
        "periodEnd": row["period_end"],
        "subtitle": row["subtitle"],
        "targetText": row["target_text"],
        "sourceText": row["source_text"],
        "totals": json.loads(row["totals_json"]),
        "score": {
            "raw": row["score_raw"],
            "band": row["score_band"],
            "components": json.loads(row["score_components_json"]),
        },
        "review": json.loads(row["review_json"]),
        "detail": json.loads(row["detail_json"]),
    }


def daily_row_to_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "label": row["label"],
        "cycleDate": row["cycle_date"],
        "completed": bool(row["completed"]),
        "subtitle": row["subtitle"],
        "sourceText": row["source_text"],
        "totals": json.loads(row["totals_json"]),
        "score": {
            "raw": row["score_raw"],
            "band": row["score_band"],
            "components": json.loads(row["score_components_json"]),
        },
        "review": json.loads(row["review_json"]),
        "detail": json.loads(row["detail_json"]),
    }


def list_days() -> list[dict[str, object]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, label, completed
            FROM daily_reviews
            ORDER BY cycle_date DESC
            """
        ).fetchall()
    return [{"id": row["id"], "label": row["label"], "completed": bool(row["completed"])} for row in rows]


def get_day(day_id: str) -> dict[str, object] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM daily_reviews
            WHERE id = ?
            """,
            (day_id,),
        ).fetchone()
    return daily_row_to_payload(row) if row else None


def list_review_payloads(period_type: str) -> list[dict[str, object]]:
    current_date = today_local_iso()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM period_reviews
            WHERE period_type = ? AND period_end < ?
            ORDER BY period_start
            """,
            (period_type, current_date),
        ).fetchall()
    return [review_row_to_payload(row) for row in rows]


def list_daily_payloads(include_incomplete: bool = True) -> list[dict[str, object]]:
    with connect() as connection:
        if include_incomplete:
            rows = connection.execute("SELECT * FROM daily_reviews ORDER BY cycle_date").fetchall()
        else:
            rows = connection.execute("SELECT * FROM daily_reviews WHERE completed = 1 ORDER BY cycle_date").fetchall()
    return [daily_row_to_payload(row) for row in rows]


def get_trends(period_type: str) -> dict[str, object]:
    if period_type == "day":
        rows = list_daily_payloads(include_incomplete=False)
    elif period_type in {"week", "month"}:
        rows = list_review_payloads(period_type)
    else:
        rows = []
    return {
        "type": period_type,
        "rows": [
            {
                "id": row["id"],
                "label": row["label"],
                "start": row.get("cycleDate") or row.get("periodStart"),
                "end": row.get("cycleDate") or row.get("periodEnd"),
                "score": row["score"]["raw"],
                "band": row["score"]["band"],
                "totals": row["totals"],
            }
            for row in rows
        ],
    }


def compare_periods(period_type: str, first_id: str, second_id: str) -> dict[str, object] | None:
    if period_type == "day":
        first = get_day(first_id)
        second = get_day(second_id)
    elif period_type in {"week", "month"}:
        first = get_review(period_type, first_id)
        second = get_review(period_type, second_id)
    else:
        return None
    if not first or not second:
        return None
    keys = ["productiveOutput", "hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"]
    deltas = {
        key: round(float(first["totals"].get(key, 0)) - float(second["totals"].get(key, 0)), 2)
        for key in keys
    }
    return {
        "type": period_type,
        "a": first,
        "b": second,
        "scoreDelta": round(float(first["score"]["raw"]) - float(second["score"]["raw"]), 1),
        "deltas": deltas,
    }


def get_home_status() -> dict[str, object]:
    status = get_db_status()
    with connect() as connection:
        latest_day = connection.execute("SELECT * FROM daily_reviews ORDER BY cycle_date DESC LIMIT 1").fetchone()
        latest_completed_week = connection.execute(
            "SELECT * FROM period_reviews WHERE period_type = 'week' ORDER BY period_start DESC LIMIT 1"
        ).fetchone()
        latest_completed_month = connection.execute(
            "SELECT * FROM period_reviews WHERE period_type = 'month' ORDER BY period_start DESC LIMIT 1"
        ).fetchone()
    return {
        "db": status,
        "latestDay": daily_row_to_payload(latest_day) if latest_day else None,
        "latestWeek": review_row_to_payload(latest_completed_week) if latest_completed_week else None,
        "latestMonth": review_row_to_payload(latest_completed_month) if latest_completed_month else None,
    }


def get_settings() -> dict[str, object]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM score_profiles WHERE id = ?", (SCORE_PROFILE["id"],)).fetchone()
    return {
        "scoreProfile": {
            "id": row["id"] if row else SCORE_PROFILE["id"],
            "name": row["name"] if row else SCORE_PROFILE["name"],
            "config": json.loads(row["config_json"]) if row else SCORE_PROFILE["config"],
        },
        "categoryRules": {
            "suffixes": {"1": "hard", "2": "soft", "3": "spiritual", "4": "physical", "5": "drift"},
            "unscored": ["sleep", "routine", "travel", "chores/errands", "odd tasks"],
            "dayAccounting": "Timed events split at 5 AM; all-day date-only events are zero-hour annotations.",
        },
    }


def fetch_one(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> dict[str, object]:
    row = connection.execute(query, params).fetchone()
    return dict(row) if row else {}


def get_db_status() -> dict[str, object]:
    current_date = today_local_iso()
    with connect() as connection:
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ]
        completed_periods = connection.execute(
            """
            SELECT id, period_type, label, period_start, period_end, updated_at
            FROM period_reviews
            WHERE period_end < ?
            ORDER BY period_type, period_start DESC
            """,
            (current_date,),
        ).fetchall()
        period_summaries = []
        for period_type in ("week", "month"):
            total = fetch_one(
                connection,
                "SELECT COUNT(*) AS count FROM period_reviews WHERE period_type = ?",
                (period_type,),
            )
            completed = fetch_one(
                connection,
                """
                SELECT COUNT(*) AS count, MIN(period_start) AS first_start, MAX(period_end) AS last_end
                FROM period_reviews
                WHERE period_type = ? AND period_end < ?
                """,
                (period_type, current_date),
            )
            period_summaries.append(
                {
                    "type": period_type,
                    "totalRows": total.get("count", 0),
                    "completedRows": completed.get("count", 0),
                    "firstStart": completed.get("first_start"),
                    "lastEnd": completed.get("last_end"),
                }
            )
        raw_calendar = fetch_one(
            connection,
            """
            SELECT COUNT(*) AS event_count, MIN(start_time) AS first_start, MAX(end_time) AS last_end
            FROM calendar_events_raw
            """
        )
        sync_runs = [
            dict(row)
            for row in connection.execute(
                """
                SELECT source, status, window_start, window_end, pulled_events, message, started_at, finished_at
                FROM sync_runs
                ORDER BY id DESC
                LIMIT 5
                """
            ).fetchall()
        ]
        score_profiles = fetch_one(connection, "SELECT COUNT(*) AS count FROM score_profiles")
        connector_probe = fetch_one(
            connection,
            "SELECT value, updated_at FROM app_meta WHERE key = 'google_calendar_connector_probe'",
        )
    return {
        "database": {
            "path": str(DB_PATH),
            "exists": DB_PATH.exists(),
            "sizeBytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "tables": tables,
            "currentLocalDate": current_date,
            "completedPeriodRule": "Week and month reviews are selectable only when period_end is before the current local date. Daily incomplete pulls are intentionally not implemented yet.",
        },
        "periodReviews": {
            "summaries": period_summaries,
            "completedRows": [dict(row) for row in completed_periods],
        },
        "calendarRaw": {
            "eventCount": raw_calendar.get("event_count", 0),
            "firstStart": raw_calendar.get("first_start"),
            "lastEnd": raw_calendar.get("last_end"),
        },
        "scoreProfiles": {
            "count": score_profiles.get("count", 0),
            "active": SCORE_PROFILE,
        },
        "syncRuns": sync_runs,
        "connectorProbe": connector_probe,
    }


class TimeTrackingHandler(BaseHTTPRequestHandler):
    server_version = "Timeforge/0.1"

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/sync/calendar":
            try:
                self.send_json(sync_calendar_and_reviews())
            except Exception as error:
                self.send_json({"ok": False, "error": str(error)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/home", "/index.html"}:
            self.send_file(DASHBOARD_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path in {"/daily", "/daily/", "/daily.html"}:
            self.send_file(DASHBOARD_DIR / "daily.html", "text/html; charset=utf-8")
            return
        if path in {"/weekly", "/weekly/", "/time-tracking-dashboard.html"}:
            self.send_file(DASHBOARD_DIR / "time-tracking-dashboard.html", "text/html; charset=utf-8")
            return
        if path in {"/monthly", "/monthly/", "/time-tracking-monthly-review.html"}:
            self.send_file(DASHBOARD_DIR / "time-tracking-monthly-review.html", "text/html; charset=utf-8")
            return
        if path in {"/trends", "/trends/", "/trends.html"}:
            self.send_file(DASHBOARD_DIR / "trends.html", "text/html; charset=utf-8")
            return
        if path in {"/compare", "/compare/", "/compare.html"}:
            self.send_file(DASHBOARD_DIR / "compare.html", "text/html; charset=utf-8")
            return
        if path in {"/settings", "/settings/", "/settings.html"}:
            self.send_file(DASHBOARD_DIR / "settings.html", "text/html; charset=utf-8")
            return
        if path in {"/db", "/db/", "/db-status.html"}:
            self.send_file(DASHBOARD_DIR / "db-status.html", "text/html; charset=utf-8")
            return
        if path == "/api/home/status":
            self.send_json(get_home_status())
            return
        if path == "/api/days":
            self.send_json(list_days())
            return
        if path == "/api/day":
            day_id = parse_qs(parsed.query).get("id", [""])[0]
            day = get_day(day_id)
            if day is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Day not found")
            else:
                self.send_json(day)
            return
        if path == "/api/weeks":
            self.send_json(list_periods("week"))
            return
        if path == "/api/months":
            self.send_json(list_periods("month"))
            return
        if path == "/api/week":
            self.send_review("week", parsed.query)
            return
        if path == "/api/month":
            self.send_review("month", parsed.query)
            return
        if path == "/api/db/status":
            self.send_json(get_db_status())
            return
        if path == "/api/trends":
            period_type = parse_qs(parsed.query).get("type", ["week"])[0]
            self.send_json(get_trends(period_type))
            return
        if path == "/api/compare/options":
            period_type = parse_qs(parsed.query).get("type", ["week"])[0]
            if period_type == "day":
                self.send_json(list_days())
            elif period_type in {"week", "month"}:
                self.send_json(list_periods(period_type))
            else:
                self.send_json([])
            return
        if path == "/api/compare":
            params = parse_qs(parsed.query)
            comparison = compare_periods(
                params.get("type", ["week"])[0],
                params.get("a", [""])[0],
                params.get("b", [""])[0],
            )
            if comparison is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Comparison not found")
            else:
                self.send_json(comparison)
            return
        if path == "/api/settings":
            self.send_json(get_settings())
            return
        if path in {
            "/review-shared.css",
            "/weekly-review.js",
            "/monthly-review.js",
            "/db-status.js",
            "/home.js",
            "/daily.js",
            "/trends.js",
            "/compare.js",
            "/settings.js",
        }:
            self.send_dashboard_asset(path.removeprefix("/"))
            return
        if path.startswith("/dashboard/"):
            self.send_dashboard_asset(path.removeprefix("/dashboard/"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def send_review(self, period_type: str, query: str) -> None:
        review_id = parse_qs(query).get("id", [""])[0]
        if not review_id:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing id")
            return
        review = get_review(period_type, review_id)
        if review is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Review not found")
            return
        self.send_json(review)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    def send_dashboard_asset(self, relative_path: str) -> None:
        requested = (DASHBOARD_DIR / relative_path).resolve()
        try:
            requested.relative_to(DASHBOARD_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        if is_private_dashboard_asset(requested):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if requested.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif requested.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        self.send_file(requested, content_type)

    def send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def sync_calendar_and_reviews() -> dict[str, object]:
    import calendar_sync
    import review_generator

    with calendar_sync.connect() as connection:
        calendar_sync.ensure_schema(connection)
        latest = calendar_sync.get_meta(connection, "calendar_raw_latest_end")
    start_value = latest or calendar_sync.DEFAULT_CALENDAR_START
    time_min = calendar_sync.parse_datetime_input(start_value)
    time_max = calendar_sync.now_local_iso()
    pulled = calendar_sync.sync_google_api(
        app_config.GOOGLE_CALENDAR_ID,
        app_config.GOOGLE_CREDENTIALS_PATH,
        app_config.GOOGLE_TOKEN_PATH,
        time_min,
        time_max,
    )
    days, weeks, months = review_generator.generate()
    return {
        "ok": True,
        "pulledEvents": pulled,
        "windowStart": time_min,
        "windowEnd": time_max,
        "generatedDays": days,
        "generatedWeeks": weeks,
        "generatedMonths": months,
    }


def is_private_dashboard_asset(path: Path) -> bool:
    if app_config.SERVE_STATIC_EXPORT:
        return False
    dashboard_data = (DASHBOARD_DIR / "data").resolve()
    if path == dashboard_data / "app-data.json":
        return True
    return path.name.startswith("time-tracking-baseline-") and path.suffix == ".html"


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Timeforge review app server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--init-db", action="store_true")
    args = parser.parse_args()

    init_db()
    if args.init_db:
        print(f"Initialized {DB_PATH}")
        return

    server = ThreadingHTTPServer((args.host, args.port), TimeTrackingHandler)
    safe_print(f"Serving Timeforge at http://{args.host}:{args.port}/")
    safe_print(f"SQLite DB: {DB_PATH}")
    server.serve_forever()


def safe_print(message: str) -> None:
    try:
        print(message)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "server.crash.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
