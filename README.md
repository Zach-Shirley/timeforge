# Timeforge

A local-first dashboard for turning Google Calendar time blocks into daily, weekly, and monthly self-review metrics.

The app reads calendar events into SQLite, normalizes them into 5 AM accounting days, scores completed periods, and serves a small dashboard from a Python backend plus static HTML/CSS/JS.

## Features

- Google Calendar import through OAuth or exported `.ics` / JSON files.
- Local SQLite analytics store.
- Daily, weekly, monthly, trends, compare, DB status, and settings pages.
- Numeric title suffix classification:
  - `1` hard work
  - `2` soft work
  - `3` spiritual / meditation
  - `4` physical / health
  - `5` drift / entertainment
- Unnumbered sleep, routine, chores, travel, illness, and ambiguous blocks remain unscored unless rules classify them.
- Mixed blocks can be split by percentage, such as `(70% 5, 30% 2)`.
- Sleep events are assigned to the wake-up day as full events.
- Date-only / all-day Google Calendar events are annotations, not 24-hour blocks.

## What Is Not Committed

Private runtime data is intentionally ignored:

- `.env`
- `Data/time_tracking.sqlite`
- `Data/google_credentials.json`
- `Data/google_token.json`
- `Data/normalization_overrides.json`
- generated `Dashboard/data/app-data.json`
- generated review notes and logs

Use the example files instead:

- `.env.example`
- `Data/normalization_overrides.example.json`
- `Dashboard/data/app-data.example.json`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` for your timezone, start date, and local data paths.

Initialize the DB and start the app:

```powershell
.\.venv\Scripts\python App/server.py --init-db
.\.venv\Scripts\python App/server.py --host 127.0.0.1 --port 8787
```

Open:

```text
http://localhost:8787/
```

## Google Calendar Sync

1. Create a Google Cloud OAuth desktop client.
2. Enable the Google Calendar API.
3. Download the OAuth client JSON.
4. Save it to the path configured by `TIME_OUTPUT_GOOGLE_CREDENTIALS_PATH`, usually:

```text
Data/google_credentials.json
```

Seed from your configured start date:

```powershell
.\.venv\Scripts\python App/calendar_sync.py google-api --from-start
.\.venv\Scripts\python App/review_generator.py
```

Update later:

```powershell
.\.venv\Scripts\python App/calendar_sync.py google-api
.\.venv\Scripts\python App/review_generator.py
```

The homepage `Sync Data` button runs the same update/regenerate path through the local server.

## Import From Export

```powershell
.\.venv\Scripts\python App/calendar_sync.py import-file "path/to/calendar.ics"
.\.venv\Scripts\python App/review_generator.py
```

## Local Hostname

The simplest URL is:

```text
http://localhost:8787/
```

For a nicer local URL without the port, use the Timeforge local launcher or a reverse proxy. See [docs/local-hostname.md](docs/local-hostname.md).
`Caddyfile.example` includes a starting point.

## Project Structure

```text
App/
  app_config.py
  calendar_sync.py
  review_generator.py
  server.py
Dashboard/
  index.html
  daily.html
  time-tracking-dashboard.html
  time-tracking-monthly-review.html
  trends.html
  compare.html
  db-status.html
  settings.html
Data/
  local private runtime data, ignored by Git
docs/
  setup notes
```

## Scoring Defaults

- Productive Output = hard work + 0.5 * soft work.
- PO target: 60 weekly-equivalent hours, 60 points.
- Drift target: 10h/week, zero-line at 20h/week, 20 base points.
- Under-target drift bonus: 0.5 points per hour under 10h, capped at 5 extra points.
- Physical target: 10h/week, 15 points.
- Spiritual target: 1h/week, 5 points.

These defaults are currently code/config driven and can be changed later into a full settings editor.
