from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import app_config

APP_DIR = app_config.APP_DIR
ROOT_DIR = app_config.ROOT_DIR
DATA_DIR = app_config.DATA_DIR
DB_PATH = app_config.DB_PATH
OVERRIDES_PATH = DATA_DIR / "normalization_overrides.json"
STATIC_DATA_PATH = app_config.STATIC_DATA_PATH
TRACKING_START_DATE = app_config.TRACKING_START_DATE


CATEGORY_KEYS = ["hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"]
NUMBERED = {
    "1": "hard",
    "2": "soft",
    "3": "spiritual",
    "4": "physical",
    "5": "drift",
}
TARGET_TEXT = "Targets: 60 PO, 10h drift, 10h physical, 1h spiritual"
MONTH_TARGET_TEXT = "Targets: 60 PO/week, 10h drift/week, 10h physical/week, 1h spiritual/week"
DAY_START_HOUR = app_config.DAY_START_HOUR
DRIFT_TARGET_HOURS = 10
DRIFT_ZERO_LINE_HOURS = 20
DRIFT_BASE_POINTS = 20
DRIFT_BONUS_MAX = 5
DAY_RULE_TEXT = "Uses 5 AM accounting days: timed events split at 5 AM; all-day date-only events are zero-hour annotations."


@dataclass
class Totals:
    hard: float = 0.0
    soft: float = 0.0
    spiritual: float = 0.0
    physical: float = 0.0
    drift: float = 0.0
    sleep: float = 0.0
    unscored: float = 0.0

    def add(self, key: str, hours: float) -> None:
        if key not in CATEGORY_KEYS:
            key = "unscored"
        setattr(self, key, getattr(self, key) + hours)

    @property
    def productive_output(self) -> float:
        return self.hard + (0.5 * self.soft)

    def as_payload(self) -> dict[str, float]:
        return {
            "productiveOutput": round(self.productive_output, 2),
            "hard": round(self.hard, 2),
            "soft": round(self.soft, 2),
            "spiritual": round(self.spiritual, 2),
            "physical": round(self.physical, 2),
            "drift": round(self.drift, 2),
            "sleep": round(self.sleep, 2),
            "unscored": round(self.unscored, 2),
        }


@dataclass
class PeriodPayload:
    id: str
    period_type: str
    label: str
    period_start: str
    period_end: str
    subtitle: str
    target_text: str
    source_text: str
    totals: dict[str, float]
    score_raw: float
    score_band: str
    score_components: list[dict[str, object]]
    review: dict[str, str]
    detail: dict[str, object] = field(default_factory=dict)


@dataclass
class DayData:
    totals: Totals = field(default_factory=Totals)
    events: list[dict[str, object]] = field(default_factory=list)
    annotations: list[dict[str, object]] = field(default_factory=list)


@dataclass
class DailyPayload:
    id: str
    cycle_date: str
    label: str
    completed: bool
    subtitle: str
    source_text: str
    totals: dict[str, float]
    score_raw: float
    score_band: str
    score_components: list[dict[str, object]]
    review: dict[str, str]
    detail: dict[str, object] = field(default_factory=dict)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=denver_tz_for_local(parsed))
    return parsed


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    offset = (weekday - current.weekday()) % 7
    return current + timedelta(days=offset + (7 * (n - 1)))


def denver_tz_for_local(moment: datetime) -> timezone:
    dst_start = datetime.combine(nth_weekday(moment.year, 3, 6, 2), time(2))
    dst_end = datetime.combine(nth_weekday(moment.year, 11, 6, 1), time(2))
    naive = moment.replace(tzinfo=None)
    offset_hours = -6 if dst_start <= naive < dst_end else -7
    return timezone(timedelta(hours=offset_hours))


def is_date_only(value: str | None) -> bool:
    return bool(value and "T" not in value)


def duration_hours(start: datetime, end: datetime) -> float:
    wall_start = start.replace(tzinfo=None)
    wall_end = end.replace(tzinfo=None)
    return max(0.0, (wall_end - wall_start).total_seconds() / 3600)


def classify(title: str | None) -> str:
    text = (title or "").strip()
    lowered = text.lower()
    suffix = re.search(r"(?:^|[^\d])([1-5])\s*$", text)
    if suffix:
        return NUMBERED[suffix.group(1)]
    if any(term in lowered for term in ("sick", "illness", "fever", "flu")):
        return "unscored"
    if "sleep" in lowered:
        return "sleep"
    if any(term in lowered for term in ("gym", "bjj", "mma", "sparring", "workout", "weightlifting", "cardio", "hiking", "stretch", "massage")):
        return "physical"
    if any(term in lowered for term in ("meditat", "reiki", "journeying", "spiritual")):
        return "spiritual"
    if any(term in lowered for term in ("scroll", "chilling", "video game", "blanket")):
        return "drift"
    if re.search(r"\b(anime|shows?|games?)\b", lowered):
        return "drift"
    return "unscored"


def allocation_for_title(title: str | None) -> dict[str, float]:
    text = (title or "").strip()
    percent_matches = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*([1-5])", text)
    if percent_matches:
        allocations: dict[str, float] = defaultdict(float)
        total = sum(float(percent) for percent, _ in percent_matches)
        if total > 0:
            for percent, number in percent_matches:
                allocations[NUMBERED[number]] += float(percent) / total
            return dict(allocations)
    return {classify(title): 1.0}


def normalize_allocation(raw: dict[str, object]) -> dict[str, float]:
    allocations: dict[str, float] = defaultdict(float)
    for key, value in raw.items():
        if key == "note":
            continue
        category = NUMBERED.get(str(key), str(key))
        if category not in CATEGORY_KEYS:
            continue
        allocations[category] += float(value)
    total = sum(allocations.values())
    if total <= 0:
        return {"unscored": 1.0}
    return {key: value / total for key, value in allocations.items()}


def load_overrides() -> dict[str, dict[str, dict[str, float]]]:
    if not OVERRIDES_PATH.exists():
        return {"event_id_overrides": {}, "title_overrides": {}}
    payload = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {
        "event_id_overrides": {
            event_id: normalize_allocation(allocation)
            for event_id, allocation in payload.get("event_id_overrides", {}).items()
            if isinstance(allocation, dict)
        },
        "title_overrides": {
            title: normalize_allocation(allocation)
            for title, allocation in payload.get("title_overrides", {}).items()
            if isinstance(allocation, dict)
        },
    }


def allocation_for_event(event_id: str, title: str | None, overrides: dict[str, dict[str, dict[str, float]]]) -> dict[str, float]:
    if event_id in overrides["event_id_overrides"]:
        return overrides["event_id_overrides"][event_id]
    if title and title in overrides["title_overrides"]:
        return overrides["title_overrides"][title]
    return allocation_for_title(title)


def accounting_date_for(moment: datetime) -> date:
    if moment.time() < time(DAY_START_HOUR):
        return moment.date() - timedelta(days=1)
    return moment.date()


def next_accounting_boundary(moment: datetime) -> datetime:
    return accounting_day_start(accounting_date_for(moment) + timedelta(days=1))


def accounting_day_start(accounting_day: date) -> datetime:
    naive = datetime.combine(accounting_day, time(DAY_START_HOUR))
    return naive.replace(tzinfo=denver_tz_for_local(naive))


def split_by_accounting_day(start: datetime, end: datetime) -> list[tuple[date, datetime, datetime]]:
    parts: list[tuple[date, datetime, datetime]] = []
    current = start
    while current < end:
        part_end = min(end, next_accounting_boundary(current))
        if current < part_end:
            parts.append((accounting_date_for(current), current, part_end))
        current = part_end
    return parts


def add_date_only_annotation(daily: dict[date, DayData], row: sqlite3.Row) -> None:
    start = date.fromisoformat(row["start_time"])
    end = date.fromisoformat(row["end_time"])
    if end <= start:
        end = start + timedelta(days=1)
    current = start
    while current < end:
        daily[current].annotations.append({
            "id": row["event_id"],
            "title": row["summary"] or "Untitled",
            "date": current.isoformat(),
            "kind": "allDay",
        })
        current += timedelta(days=1)


def event_priority(event: dict[str, object]) -> tuple[int, str]:
    category = str(event.get("category") or "unscored")
    priority = {
        "hard": 0,
        "soft": 1,
        "physical": 2,
        "spiritual": 2,
        "drift": 3,
        "sleep": 4,
        "unscored": 9,
    }.get(category, 9)
    return priority, str(event.get("title") or "")


def make_gap_event(accounting_day: date, index: int, start: datetime, end: datetime) -> dict[str, object]:
    return {
        "id": f"gap-{accounting_day.isoformat()}-{index}",
        "title": "Untracked gap",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hours": round(duration_hours(start, end), 2),
        "category": "unscored",
        "allocations": {"unscored": 1.0},
        "generated": True,
    }


def normalize_day_records(daily: dict[date, DayData]) -> None:
    now = datetime.now().astimezone()
    current_accounting_day = accounting_date_for(now)
    for accounting_day, record in daily.items():
        day_start = accounting_day_start(accounting_day)
        day_end = accounting_day_start(accounting_day + timedelta(days=1))
        close_gaps_through = day_end if accounting_day < current_accounting_day else None
        events = sorted(
            record.events,
            key=lambda event: (
                parse_dt(str(event["start"])),
                event_priority(event),
                parse_dt(str(event["end"])),
            ),
        )
        record.totals = Totals()
        normalized_events: list[dict[str, object]] = []
        cursor = day_start
        gap_index = 1
        for event in events:
            start = parse_dt(str(event["start"]))
            end = parse_dt(str(event["end"]))
            if end <= day_start or start >= day_end:
                continue
            start = max(start, day_start)
            end = min(end, day_end)
            if close_gaps_through and start > cursor:
                gap = make_gap_event(accounting_day, gap_index, cursor, start)
                gap_index += 1
                record.totals.add("unscored", float(gap["hours"]))
                normalized_events.append(gap)
            adjusted_start = max(start, cursor)
            if end <= adjusted_start:
                continue
            hours = duration_hours(adjusted_start, end)
            adjusted_event = dict(event)
            adjusted_event["start"] = adjusted_start.isoformat()
            adjusted_event["end"] = end.isoformat()
            adjusted_event["hours"] = round(hours, 2)
            allocations = adjusted_event.get("allocations") if isinstance(adjusted_event.get("allocations"), dict) else {"unscored": 1.0}
            for allocation_category, weight in allocations.items():
                record.totals.add(str(allocation_category), hours * float(weight))
            normalized_events.append(adjusted_event)
            cursor = max(cursor, end)
        if close_gaps_through and cursor < day_end:
            gap = make_gap_event(accounting_day, gap_index, cursor, day_end)
            record.totals.add("unscored", float(gap["hours"]))
            normalized_events.append(gap)
        record.events = normalized_events


def load_daily_records() -> dict[date, DayData]:
    daily: dict[date, DayData] = defaultdict(DayData)
    overrides = load_overrides()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT event_id, summary, start_time, end_time
            FROM calendar_events_raw
            WHERE start_time IS NOT NULL AND end_time IS NOT NULL
            ORDER BY start_time
            """
        ).fetchall()
    for row in rows:
        if is_date_only(row["start_time"]) or is_date_only(row["end_time"]):
            add_date_only_annotation(daily, row)
            continue
        start = parse_dt(row["start_time"])
        end = parse_dt(row["end_time"])
        allocations = allocation_for_event(row["event_id"], row["summary"], overrides)
        category = max(allocations, key=allocations.get)
        for index, (accounting_date, part_start, part_end) in enumerate(split_by_accounting_day(start, end), start=1):
            hours = duration_hours(part_start, part_end)
            if hours <= 0:
                continue
            record = daily[accounting_date]
            record.events.append({
                "id": row["event_id"] if index == 1 else f"{row['event_id']}#{index}",
                "sourceId": row["event_id"],
                "title": row["summary"] or "Untitled",
                "start": part_start.isoformat(),
                "end": part_end.isoformat(),
                "hours": round(hours, 2),
                "category": category,
                "allocations": {key: round(value, 3) for key, value in allocations.items()},
            })
    normalize_day_records(daily)
    return dict(daily)


def load_daily_totals() -> dict[date, Totals]:
    return {cycle_date: data.totals for cycle_date, data in load_daily_records().items()}


def fmt_hours(value: float) -> str:
    hours = int(value)
    minutes = round((value - hours) * 60)
    if minutes == 60:
        hours += 1
        minutes = 0
    return f"{hours}h {minutes:02d}m"


def date_label(start: date, end: date) -> str:
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%b')} {start.day}-{end.day}, {start.year}"
        return f"{start.strftime('%b')} {start.day}-{end.strftime('%b')} {end.day}, {start.year}"
    return f"{start.strftime('%b')} {start.day}, {start.year}-{end.strftime('%b')} {end.day}, {end.year}"


def month_label(month_start: date) -> str:
    return month_start.strftime("%B %Y")


def sum_dates(daily: dict[date, Totals], dates: list[date]) -> Totals:
    totals = Totals()
    for current in dates:
        day = daily.get(current)
        if not day:
            continue
        for key in CATEGORY_KEYS:
            totals.add(key, getattr(day, key))
    return totals


def po_score(po: float) -> float:
    if po <= 60:
        return po
    if po <= 80:
        return 60 + ((po - 60) * 0.6)
    if po <= 100:
        return 72 + ((po - 80) * 0.4)
    return 80 + ((po - 100) * 0.2)


def drift_score(drift: float) -> float:
    if drift <= DRIFT_TARGET_HOURS:
        under_target = DRIFT_TARGET_HOURS - drift
        return DRIFT_BASE_POINTS + min(DRIFT_BONUS_MAX, under_target * 0.5)
    if drift >= DRIFT_ZERO_LINE_HOURS:
        return 0
    return DRIFT_BASE_POINTS * ((DRIFT_ZERO_LINE_HOURS - drift) / (DRIFT_ZERO_LINE_HOURS - DRIFT_TARGET_HOURS))


def score_totals(totals: Totals, days: int) -> tuple[float, str, list[dict[str, object]]]:
    scale = 7 / days if days else 1
    po_weekly = totals.productive_output * scale
    drift_weekly = totals.drift * scale
    physical_weekly = totals.physical * scale
    spiritual_weekly = totals.spiritual * scale

    components = [
        {"label": "PO", "value": round(po_score(po_weekly), 1), "max": 60, "colorKey": "productiveOutput"},
        {"label": "Drift", "value": round(drift_score(drift_weekly), 1), "max": 20, "colorKey": "drift"},
        {"label": "Physical", "value": round(min(15, 15 * (physical_weekly / 10)), 1), "max": 15, "colorKey": "physical"},
        {"label": "Spiritual", "value": round(min(5, 5 * (spiritual_weekly / 1)), 1), "max": 5, "colorKey": "spiritual"},
    ]
    raw = round(sum(float(component["value"]) for component in components), 1)
    if raw >= 90:
        band = "A"
    elif raw >= 80:
        band = "B"
    elif raw >= 70:
        band = "C"
    elif raw >= 60:
        band = "D"
    else:
        band = "F"
    return raw, band, components


def review_text(totals: Totals, score: float, days: int) -> dict[str, str]:
    scale = 7 / days if days else 1
    po_weekly = totals.productive_output * scale
    drift_weekly = totals.drift * scale
    physical_weekly = totals.physical * scale
    spiritual_weekly = totals.spiritual * scale
    sleep_avg = totals.sleep / days if days else 0

    win = f"{round(totals.productive_output, 1)} PO total, with {round(totals.hard, 1)} hard-work hours."
    if po_weekly >= 60:
        win = f"Output cleared the 60 PO weekly standard at {round(po_weekly, 1)} weekly-equivalent PO."
    elif physical_weekly >= 10:
        win = f"Physical work cleared target at {round(physical_weekly, 1)} weekly-equivalent hours."

    leaks = [
        ("drift", 1 - min(1, drift_score(drift_weekly) / 20), f"Drift is the main leak at {round(drift_weekly, 1)} weekly-equivalent hours against the 10h target."),
        ("physical", 1 - min(1, physical_weekly / 10), f"Physical work is the weakest lever at {round(physical_weekly, 1)} weekly-equivalent hours against the 10h target."),
        ("spiritual", 1 - min(1, spiritual_weekly / 1), f"Spiritual work is the weakest lever at {round(spiritual_weekly, 1)} weekly-equivalent hours against the 1h target."),
        ("po", 1 - min(1, po_weekly / 60), f"Productive Output is the limiting factor at {round(po_weekly, 1)} weekly-equivalent PO against the 60 target."),
    ]
    leak = max(leaks, key=lambda item: item[1])[2]
    return {
        "win": win,
        "leak": leak,
        "sleepDisplay": fmt_hours(sleep_avg),
        "sleepDetail": f"{round(totals.sleep, 2)}h total sleep / {days} accounting days",
    }


def portable_day_label(cycle_date: date) -> str:
    return f"{cycle_date.strftime('%a, %b')} {cycle_date.day}, {cycle_date.year}"


def week_starts(first: date, last_completed: date) -> list[date]:
    starts: list[date] = []
    current = first
    if current.weekday() != 0:
        starts.append(current)
        current = current + timedelta(days=(7 - current.weekday()))
    while current <= last_completed:
        starts.append(current)
        current += timedelta(days=7)
    return starts


def month_starts(first: date, last_completed: date) -> list[date]:
    current = date(first.year, first.month, 1)
    starts: list[date] = []
    while current <= last_completed:
        starts.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return starts


def build_week_payload(
    daily: dict[date, Totals],
    start: date,
    last_completed: date,
    daily_records: dict[date, DayData] | None = None,
) -> PeriodPayload:
    days_until_sunday = 6 - start.weekday()
    end = min(start + timedelta(days=days_until_sunday), last_completed)
    days = (end - start).days + 1
    dates = [start + timedelta(days=offset) for offset in range(days)]
    totals = sum_dates(daily, dates)
    score, band, components = score_totals(totals, days)
    label = date_label(start, end)
    day_details = []
    for current in dates:
        day_totals = daily.get(current, Totals())
        day_score, day_band, _ = score_totals(day_totals, 1)
        day_details.append({
            "date": current.isoformat(),
            "label": current.strftime("%a"),
            "score": round(day_score),
            "band": day_band,
            "hard": round(day_totals.hard, 1),
            "soft": round(day_totals.soft, 1),
            "spiritual": round(day_totals.spiritual, 1),
            "physical": round(day_totals.physical, 1),
            "drift": round(day_totals.drift, 1),
            "sleep": round(day_totals.sleep, 1),
            "unscored": round(day_totals.unscored, 1),
            "annotations": [
                annotation["title"]
                for annotation in (daily_records.get(current).annotations if daily_records and current in daily_records else [])
            ],
        })
    return PeriodPayload(
        id=f"week-{start.isoformat()}",
        period_type="week",
        label=label,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        subtitle=f"{label}. Generated from raw Google Calendar data using 5 AM accounting days.",
        target_text=TARGET_TEXT,
        source_text="Current data source: raw Google Calendar API sync",
        totals=totals.as_payload(),
        score_raw=score,
        score_band=band,
        score_components=components,
        review=review_text(totals, score, days),
        detail={"days": day_details},
    )


def build_daily_payload(cycle_date: date, data: DayData, completed: bool) -> DailyPayload:
    score, band, components = score_totals(data.totals, 1)
    label = portable_day_label(cycle_date)
    timeline = sorted(data.events, key=lambda event: event["start"])
    return DailyPayload(
        id=f"day-{cycle_date.isoformat()}",
        cycle_date=cycle_date.isoformat(),
        label=label,
        completed=completed,
        subtitle=f"{label}. 5 AM accounting day generated from raw Google Calendar data.",
        source_text="Current data source: raw Google Calendar API sync",
        totals=data.totals.as_payload(),
        score_raw=score,
        score_band=band,
        score_components=components,
        review=review_text(data.totals, score, 1),
        detail={"timeline": timeline, "annotations": sorted(data.annotations, key=lambda item: item["title"])},
    )


def build_month_payload(daily: dict[date, Totals], start: date, last_completed: date) -> PeriodPayload:
    next_month = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    end = min(next_month - timedelta(days=1), last_completed)
    days = (end - start).days + 1
    dates = [start + timedelta(days=offset) for offset in range(days)]
    totals = sum_dates(daily, dates)
    score, band, components = score_totals(totals, days)
    label = month_label(start)
    week_details = []
    current = start
    while current <= end:
        week_end = min(current + timedelta(days=6 - current.weekday()), end)
        period_days = (week_end - current).days + 1
        period_dates = [current + timedelta(days=offset) for offset in range(period_days)]
        week_totals = sum_dates(daily, period_dates)
        week_score, _, _ = score_totals(week_totals, period_days)
        week_details.append({
            "label": f"{current.strftime('%b')} {current.day}-{week_end.day}",
            "score": round(week_score),
            "hard": round(week_totals.hard, 1),
            "soft": round(week_totals.soft, 1),
            "spiritual": round(week_totals.spiritual, 1),
            "physical": round(week_totals.physical, 1),
            "drift": round(week_totals.drift, 1),
            "sleep": round(week_totals.sleep, 1),
            "unscored": round(week_totals.unscored, 1),
        })
        current = week_end + timedelta(days=1)
    detail = {
        "weeks": week_details,
        "trends": [
            {"label": "PO vs target", "value": min(100, round((totals.productive_output / max(1, days) * 7 / 60) * 100)), "text": "Weekly equivalent", "colorKey": "productiveOutput"},
            {"label": "Drift control", "value": min(100, round((drift_score(totals.drift / max(1, days) * 7) / 20) * 100)), "text": "Lower is better", "colorKey": "drift"},
            {"label": "Physical consistency", "value": min(100, round(((totals.physical / max(1, days) * 7) / 10) * 100)), "text": "Weekly equivalent", "colorKey": "physical"},
            {"label": "Spiritual consistency", "value": min(100, round(((totals.spiritual / max(1, days) * 7) / 1) * 100)), "text": "Weekly equivalent", "colorKey": "spiritual"},
        ],
        "notes": [
            {"label": "Source", "text": "Generated from raw Google Calendar events."},
            {"label": "Grouping", "text": DAY_RULE_TEXT},
            {"label": "Next target", "text": "Use this as a generated baseline; refine after daily review design is locked."},
        ],
        "dataNotes": [
            {"label": "Completed period", "text": f"{start.isoformat()} through {end.isoformat()}."},
            {"label": "Confidence", "text": "Good for numbered category totals; mixed unlabeled blocks remain unscored unless title rules classify them."},
            {"label": "Importer", "text": "Google Calendar API raw sync feeds this generated period row."},
        ],
    }
    return PeriodPayload(
        id=f"month-{start.strftime('%Y-%m')}",
        period_type="month",
        label=label,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        subtitle=f"{label}. Generated from raw Google Calendar data using 5 AM accounting days.",
        target_text=MONTH_TARGET_TEXT,
        source_text="Current data source: raw Google Calendar API sync",
        totals=totals.as_payload(),
        score_raw=score,
        score_band=band,
        score_components=components,
        review=review_text(totals, score, days),
        detail=detail,
    )


def save_payloads(payloads: list[PeriodPayload], replace_generated: bool = True) -> None:
    with connect() as connection:
        if replace_generated:
            connection.execute("DELETE FROM period_reviews")
        for payload in payloads:
            connection.execute(
                """
                INSERT INTO period_reviews (
                    id, period_type, label, period_start, period_end, subtitle, target_text, source_text,
                    score_raw, score_band, totals_json, score_components_json, review_json, detail_json, updated_at
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
                    payload.id,
                    payload.period_type,
                    payload.label,
                    payload.period_start,
                    payload.period_end,
                    payload.subtitle,
                    payload.target_text,
                    payload.source_text,
                    payload.score_raw,
                    payload.score_band,
                    json.dumps(payload.totals, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(payload.score_components, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(payload.review, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(payload.detail, separators=(",", ":"), ensure_ascii=True),
                ),
            )
        connection.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('period_reviews_generated_at', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (datetime.now().astimezone().replace(microsecond=0).isoformat(),),
        )


def save_daily_payloads(payloads: list[DailyPayload], replace_generated: bool = True) -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_reviews (
                id TEXT PRIMARY KEY,
                cycle_date TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                completed INTEGER NOT NULL,
                subtitle TEXT NOT NULL,
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
        if replace_generated:
            connection.execute("DELETE FROM daily_reviews")
        for payload in payloads:
            connection.execute(
                """
                INSERT INTO daily_reviews (
                    id, cycle_date, label, completed, subtitle, source_text, score_raw, score_band,
                    totals_json, score_components_json, review_json, detail_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    cycle_date = excluded.cycle_date,
                    label = excluded.label,
                    completed = excluded.completed,
                    subtitle = excluded.subtitle,
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
                    payload.id,
                    payload.cycle_date,
                    payload.label,
                    1 if payload.completed else 0,
                    payload.subtitle,
                    payload.source_text,
                    payload.score_raw,
                    payload.score_band,
                    json.dumps(payload.totals, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(payload.score_components, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(payload.review, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(payload.detail, separators=(",", ":"), ensure_ascii=True),
                ),
            )


def _daily_payload_from_row(row: sqlite3.Row) -> dict[str, object]:
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


def _period_payload_from_row(row: sqlite3.Row) -> dict[str, object]:
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


def _options(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{"id": row["id"], "label": row["label"], "completed": row.get("completed", True)} for row in rows]


def _trend_rows(rows: list[dict[str, object]], period_type: str) -> dict[str, object]:
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


def export_static_data() -> dict[str, object]:
    with connect() as connection:
        daily_rows = [
            _daily_payload_from_row(row)
            for row in connection.execute("SELECT * FROM daily_reviews ORDER BY cycle_date DESC").fetchall()
        ]
        daily_rows_ascending = list(reversed(daily_rows))
        week_rows = [
            _period_payload_from_row(row)
            for row in connection.execute(
                "SELECT * FROM period_reviews WHERE period_type = 'week' ORDER BY period_start DESC"
            ).fetchall()
        ]
        month_rows = [
            _period_payload_from_row(row)
            for row in connection.execute(
                "SELECT * FROM period_reviews WHERE period_type = 'month' ORDER BY period_start DESC"
            ).fetchall()
        ]
        raw = connection.execute(
            """
            SELECT COUNT(*) AS event_count, MIN(start_time) AS first_start, MAX(end_time) AS last_end
            FROM calendar_events_raw
            """
        ).fetchone()
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
        profile = connection.execute("SELECT * FROM score_profiles WHERE id = 'default-v0'").fetchone()
    payload = {
        "generatedAt": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "home": {
            "latestDay": daily_rows[0] if daily_rows else None,
            "latestWeek": week_rows[0] if week_rows else None,
            "latestMonth": month_rows[0] if month_rows else None,
            "db": {
                "calendarRaw": {
                    "eventCount": raw["event_count"] if raw else 0,
                    "firstStart": raw["first_start"] if raw else None,
                    "lastEnd": raw["last_end"] if raw else None,
                },
                "periodReviews": {
                    "summaries": [
                        {"type": "day", "completedRows": sum(1 for row in daily_rows if row["completed"])},
                        {"type": "week", "completedRows": len(week_rows)},
                        {"type": "month", "completedRows": len(month_rows)},
                    ]
                },
            },
        },
        "days": {"options": _options(daily_rows), "byId": {row["id"]: row for row in daily_rows}},
        "weeks": {"options": _options(week_rows), "byId": {row["id"]: row for row in week_rows}},
        "months": {"options": _options(month_rows), "byId": {row["id"]: row for row in month_rows}},
        "trends": {
            "day": _trend_rows(daily_rows_ascending, "day"),
            "week": _trend_rows(list(reversed(week_rows)), "week"),
            "month": _trend_rows(list(reversed(month_rows)), "month"),
        },
        "settings": {
            "scoreProfile": {
                "id": profile["id"] if profile else "default-v0",
                "name": profile["name"] if profile else "Default V0",
                "config": json.loads(profile["config_json"]) if profile else {},
            },
            "categoryRules": {
                "suffixes": {"1": "hard", "2": "soft", "3": "spiritual", "4": "physical", "5": "drift"},
                "dayAccounting": DAY_RULE_TEXT,
            },
        },
        "syncRuns": sync_runs,
    }
    STATIC_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATIC_DATA_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return payload


def generate(completed_through: date | None = None) -> tuple[int, int, int]:
    daily_records = load_daily_records()
    if not daily_records:
        return 0, 0, 0
    daily = {cycle_date: data.totals for cycle_date, data in daily_records.items()}
    first = max(TRACKING_START_DATE, min(daily_records))
    raw_last = max(daily_records)
    last_completed = completed_through or min(raw_last, date.today() - timedelta(days=1))
    daily_payloads = [
        build_daily_payload(current, daily_records[current], current <= last_completed)
        for current in sorted(daily_records)
        if current >= TRACKING_START_DATE
    ]
    payloads: list[PeriodPayload] = []
    for start in week_starts(first, last_completed):
        payloads.append(build_week_payload(daily, start, last_completed, daily_records))
    for start in month_starts(first, last_completed):
        next_month = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
        if next_month - timedelta(days=1) <= last_completed:
            payloads.append(build_month_payload(daily, start, last_completed))
    save_daily_payloads(daily_payloads)
    save_payloads(payloads)
    export_static_data()
    days = len(daily_payloads)
    weeks = sum(1 for payload in payloads if payload.period_type == "week")
    months = sum(1 for payload in payloads if payload.period_type == "month")
    return days, weeks, months


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate completed weekly and monthly review rows from raw calendar events.")
    parser.add_argument("--completed-through", help="YYYY-MM-DD. Defaults to yesterday or the latest raw calendar day, whichever is earlier.")
    args = parser.parse_args()
    completed_through = date.fromisoformat(args.completed_through) if args.completed_through else None
    days, weeks, months = generate(completed_through)
    print(f"Generated {days} daily rows, {weeks} weekly rows, and {months} monthly rows in {DB_PATH}")


if __name__ == "__main__":
    main()
