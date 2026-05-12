from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import app_config

APP_DIR = app_config.APP_DIR
ROOT_DIR = app_config.ROOT_DIR
DATA_DIR = app_config.DATA_DIR
DB_PATH = app_config.DB_PATH


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def load_events(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"]
    if isinstance(payload, list):
        return payload
    raise ValueError("Expected a JSON list of events or an object with an events list.")


def event_time(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("dateTime") or value.get("date")
    return None


def import_events(events: list[dict], source_path: Path, calendar_id: str) -> int:
    with connect() as connection:
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
        imported = 0
        starts: list[str] = []
        ends: list[str] = []
        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue
            start_time = event_time(event.get("start"))
            end_time = event_time(event.get("end"))
            if start_time:
                starts.append(start_time)
            if end_time:
                ends.append(end_time)
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
                    calendar_id,
                    event_id,
                    event.get("summary") or event.get("display_title"),
                    start_time,
                    end_time,
                    event.get("colorId") or event.get("color_id"),
                    json.dumps(event, separators=(",", ":"), ensure_ascii=True),
                ),
            )
            imported += 1
        connection.execute(
            """
            INSERT INTO sync_runs (
                source, status, window_start, window_end, pulled_events, message, finished_at
            )
            VALUES (?, 'imported', ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                f"json:{source_path.name}",
                min(starts) if starts else None,
                max(ends) if ends else None,
                imported,
                f"Imported from {source_path}",
            ),
        )
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Google Calendar event JSON into the time tracking SQLite DB.")
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--calendar-id", default="primary")
    args = parser.parse_args()

    events = load_events(args.json_path)
    imported = import_events(events, args.json_path, args.calendar_id)
    print(f"Imported {imported} events into {DB_PATH}")


if __name__ == "__main__":
    main()
