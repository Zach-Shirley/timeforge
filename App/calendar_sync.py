from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Iterable

import app_config

APP_DIR = app_config.APP_DIR
ROOT_DIR = app_config.ROOT_DIR
DATA_DIR = app_config.DATA_DIR
DB_PATH = app_config.DB_PATH
DEFAULT_CALENDAR_START = app_config.DEFAULT_CALENDAR_START


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


@dataclass
class NormalizedEvent:
    calendar_id: str
    event_id: str
    summary: str | None
    start_time: str | None
    end_time: str | None
    color_id: str | None
    raw: dict


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
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
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def now_local_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_datetime_input(value: str) -> str:
    if "T" in value:
        parsed = datetime.fromisoformat(value)
    else:
        parsed = datetime.combine(date.fromisoformat(value), time.min)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.replace(microsecond=0).isoformat()


def get_meta(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO app_meta (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def json_time(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("dateTime") or value.get("date")
    return None


def normalize_json_event(event: dict, calendar_id: str) -> NormalizedEvent | None:
    event_id = event.get("id") or event.get("uid") or event.get("event_id")
    if not event_id:
        return None
    return NormalizedEvent(
        calendar_id=calendar_id,
        event_id=str(event_id),
        summary=event.get("summary") or event.get("display_title") or event.get("title"),
        start_time=json_time(event.get("start")) or event.get("start_time"),
        end_time=json_time(event.get("end")) or event.get("end_time"),
        color_id=event.get("colorId") or event.get("color_id"),
        raw=event,
    )


def load_json_events(path: Path, calendar_id: str) -> list[NormalizedEvent]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw_events = payload.get("items") or payload.get("events")
    else:
        raw_events = payload
    if not isinstance(raw_events, list):
        raise ValueError("Expected a JSON list, Google API items list, or object with events/items.")
    return [event for raw in raw_events if isinstance(raw, dict) if (event := normalize_json_event(raw, calendar_id))]


def unfold_ics_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def split_ics_line(line: str) -> tuple[str, str, str]:
    if ":" not in line:
        return line, "", ""
    key_part, value = line.split(":", 1)
    parts = key_part.split(";")
    return parts[0].upper(), ";".join(parts[1:]), value


def parse_ics_datetime(value: str) -> str | None:
    if not value:
        return None
    if len(value) == 8 and value.isdigit():
        return date.fromisoformat(f"{value[0:4]}-{value[4:6]}-{value[6:8]}").isoformat()
    cleaned = value.rstrip("Z")
    formats = ["%Y%m%dT%H%M%S", "%Y%m%dT%H%M"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            if value.endswith("Z"):
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            pass
    return value


def parse_ics(path: Path, calendar_id: str) -> list[NormalizedEvent]:
    text = path.read_text(encoding="utf-8-sig")
    lines = unfold_ics_lines(text)
    events: list[NormalizedEvent] = []
    current: dict[str, object] | None = None
    raw_lines: list[str] = []
    for line in lines:
        key, _, value = split_ics_line(line)
        if key == "BEGIN" and value == "VEVENT":
            current = {}
            raw_lines = [line]
            continue
        if current is None:
            continue
        raw_lines.append(line)
        if key == "END" and value == "VEVENT":
            event_id = str(current.get("UID") or current.get("DTSTAMP") or f"ics-{len(events) + 1}")
            events.append(
                NormalizedEvent(
                    calendar_id=calendar_id,
                    event_id=event_id,
                    summary=current.get("SUMMARY") if isinstance(current.get("SUMMARY"), str) else None,
                    start_time=parse_ics_datetime(str(current.get("DTSTART") or "")),
                    end_time=parse_ics_datetime(str(current.get("DTEND") or "")),
                    color_id=None,
                    raw={"ics": raw_lines},
                )
            )
            current = None
            raw_lines = []
            continue
        if key in {"UID", "SUMMARY", "DTSTART", "DTEND", "DTSTAMP"}:
            current[key] = value
    return events


def upsert_events(
    connection: sqlite3.Connection,
    events: Iterable[NormalizedEvent],
    source: str,
    window_start: str | None,
    window_end: str | None,
) -> int:
    count = 0
    starts: list[str] = []
    ends: list[str] = []
    for event in events:
        if event.start_time:
            starts.append(event.start_time)
        if event.end_time:
            ends.append(event.end_time)
        connection.execute(
            """
            INSERT INTO calendar_events_raw (
                calendar_id, event_id, summary, start_time, end_time, color_id, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(calendar_id, event_id) DO UPDATE SET
                summary = excluded.summary,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                color_id = excluded.color_id,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                event.calendar_id,
                event.event_id,
                event.summary,
                event.start_time,
                event.end_time,
                event.color_id,
                json.dumps(event.raw, separators=(",", ":"), ensure_ascii=True),
            ),
        )
        count += 1
    resolved_start = window_start or (min(starts) if starts else None)
    resolved_end = window_end or (max(ends) if ends else None)
    connection.execute(
        """
        INSERT INTO sync_runs (
            source, status, window_start, window_end, pulled_events, message, finished_at
        )
        VALUES (?, 'imported', ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (source, resolved_start, resolved_end, count, f"Imported {count} raw calendar events."),
    )
    if resolved_end:
        set_meta(connection, "calendar_raw_latest_end", resolved_end)
    set_meta(
        connection,
        "google_calendar_connector_probe",
        f"Raw Google Calendar API sync completed through {resolved_end or 'unknown end'} with {count} events in the latest run.",
    )
    set_meta(
        connection,
        "calendar_sync_status",
        f"Latest sync source {source}: {count} events, {resolved_start or 'unknown start'} -> {resolved_end or 'unknown end'}.",
    )
    return count


def import_file(path: Path, calendar_id: str) -> int:
    with connect() as connection:
        ensure_schema(connection)
        if path.suffix.lower() == ".ics":
            events = parse_ics(path, calendar_id)
        else:
            events = load_json_events(path, calendar_id)
        count = upsert_events(connection, events, f"file:{path.name}", None, None)
    return count


def sync_google_api(
    calendar_id: str,
    credentials_path: Path,
    token_path: Path,
    time_min: str,
    time_max: str,
) -> int:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Google API packages are missing. Install with: "
            "python -m pip install -r requirements.txt"
        ) from exc

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not credentials_path.exists():
                raise SystemExit(f"Missing OAuth client credentials file: {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            credentials = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    service = build("calendar", "v3", credentials=credentials)
    pulled: list[NormalizedEvent] = []
    page_token = None
    while True:
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )
        pulled.extend(
            event
            for raw in result.get("items", [])
            if (event := normalize_json_event(raw, calendar_id))
        )
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    with connect() as connection:
        ensure_schema(connection)
        count = upsert_events(connection, pulled, f"google-api:{calendar_id}", time_min, time_max)
    return count


def status() -> dict[str, object]:
    with connect() as connection:
        ensure_schema(connection)
        raw = connection.execute(
            """
            SELECT COUNT(*) AS count, MIN(start_time) AS first_start, MAX(end_time) AS last_end
            FROM calendar_events_raw
            """
        ).fetchone()
        latest = get_meta(connection, "calendar_raw_latest_end")
        runs = [
            dict(row)
            for row in connection.execute(
                """
                SELECT source, status, window_start, window_end, pulled_events, started_at, finished_at
                FROM sync_runs
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()
        ]
    return {
        "db": str(DB_PATH),
        "rawEvents": raw["count"],
        "firstStart": raw["first_start"],
        "lastEnd": raw["last_end"],
        "latestEndMeta": latest,
        "recentRuns": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or update Google Calendar raw events in SQLite.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-file", help="Import a Google Calendar JSON or ICS export.")
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument("--calendar-id", default="primary")

    api_parser = subparsers.add_parser("google-api", help="Sync directly from Google Calendar API.")
    api_parser.add_argument("--calendar-id", default="primary")
    api_parser.add_argument("--credentials", type=Path, default=app_config.GOOGLE_CREDENTIALS_PATH)
    api_parser.add_argument("--token", type=Path, default=app_config.GOOGLE_TOKEN_PATH)
    api_parser.add_argument("--start", default=None, help="RFC3339 datetime or YYYY-MM-DD. Defaults to latest raw end, then TIME_OUTPUT_CALENDAR_START.")
    api_parser.add_argument("--end", default=None, help="RFC3339 datetime or YYYY-MM-DD. Defaults to now.")
    api_parser.add_argument("--from-start", action="store_true", help="Ignore latest sync state and seed from TIME_OUTPUT_CALENDAR_START.")

    subparsers.add_parser("status", help="Print raw calendar sync status.")

    args = parser.parse_args()
    if args.command == "import-file":
        count = import_file(args.path, args.calendar_id)
        print(f"Imported {count} raw calendar events into {DB_PATH}")
    elif args.command == "google-api":
        with connect() as connection:
            ensure_schema(connection)
            latest = get_meta(connection, "calendar_raw_latest_end")
        start_value = DEFAULT_CALENDAR_START if args.from_start else (args.start or latest or DEFAULT_CALENDAR_START)
        time_min = parse_datetime_input(start_value)
        time_max = parse_datetime_input(args.end) if args.end else now_local_iso()
        count = sync_google_api(args.calendar_id, args.credentials, args.token, time_min, time_max)
        print(f"Synced {count} raw Google Calendar events into {DB_PATH}")
        print(f"Window: {time_min} -> {time_max}")
    elif args.command == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
