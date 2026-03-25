# Darkweb Monitor

A real-time monitoring system for crawling surface web and darkweb sources, extracting indicators, storing evidence, and sending alerts when watchlist matches are detected.

---

## Overview

This project is designed to monitor target sites continuously, collect page content, extract useful artifacts, compare them against a watchlist, and notify operators through external alert channels.

It supports both standard web targets and `.onion` services through Tor.

---

## Key Features

- Asynchronous multi-worker crawling
- Depth-based URL expansion
- Surface web and Tor-based `.onion` crawling
- Indicator extraction and normalization
- Watchlist-based matching
- Alert deduplication with cooldown control
- Evidence storage for raw HTML, text dumps, and screenshots
- Discord and Telegram alert delivery

---

## Project Structure

```plaintext
app/
├── api/
├── core/
├── crawler/
│   ├── scheduler.py
│   ├── fetcher.py
│   ├── extractor.py
│   ├── matcher.py
│   └── screenshot.py
├── repository/
└── init_db.py

run.py
targets.json
watchlist.json
.env
requirements.txt
```

### Directory Notes

- `app/api/`  
  API-related logic and endpoints.

- `app/core/`  
  Core configuration, database connection, and shared utilities.

- `app/crawler/`  
  Main crawling pipeline including scheduling, fetching, extraction, matching, and screenshot capture.

- `app/repository/`  
  Database access layer for saving pages, findings, alerts, and target state.

- `app/init_db.py`  
  Database schema initialization.

- `run.py`  
  Main entry point for starting the service.

- `targets.json`  
  Seed targets to monitor.

- `watchlist.json`  
  Patterns used for detection and alerting.

- `.env`  
  Runtime configuration values.

- `requirements.txt`  
  Python dependency list.

---

## How It Works

The system processes data in the following order:

1. Load monitoring targets from `targets.json`
2. Enqueue crawl jobs through the scheduler
3. Fetch target pages over HTTP or Tor
4. Extract indicators and content from fetched pages
5. Compare extracted values against `watchlist.json`
6. Save results and evidence to storage/database
7. Trigger alerts if a new valid match is found

---

## Requirements

Install the following before running the project:

- Python 3.10 or later
- PostgreSQL
- Playwright
- Tor, if `.onion` crawling is required

---

## Installation

```bash
pip install -r requirements.txt
playwright install
```

---

## Configuration

Create a `.env` file in the project root.

### Example

```env
API_HOST=0.0.0.0
API_PORT=8000
API_KEY=changeme

DATABASE_URL=postgresql://user:password@127.0.0.1:5432/intel

POLL_INTERVAL_SECONDS=5
WORKER_COUNT=4
MAX_DEPTH=1
MAX_PAGES_PER_HOST=20
ALERT_COOLDOWN_SECONDS=3600

DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

SCREENSHOT_ENABLED=true
PLAYWRIGHT_TIMEOUT_MS=30000

TOR_PROXY_URL=socks5h://127.0.0.1:9050
```

### Important Notes

- Use `127.0.0.1` or `localhost` for local PostgreSQL.
- Use `db` only when PostgreSQL runs as a Docker service.
- Leave Discord and Telegram fields empty if alerts are not needed.
- Tor proxy must be reachable for `.onion` crawling.

---

## Database Setup

Initialize the database schema before the first run:

```bash
python -m app.init_db
```

---

## Running the Project

```bash
python run.py
```

---

## Docker Notes

When running inside Docker, the database host usually changes from `127.0.0.1` to the service name.

Example:

```env
DATABASE_URL=postgresql://user:password@db:5432/intel
```

If Tor is also containerized:

```env
TOR_PROXY_URL=socks5h://tor:9050
```

---

## Tor Support

This project can crawl `.onion` sites through a SOCKS proxy.

### Local Tor

Run Tor locally:

```bash
tor
```

Then use:

```env
TOR_PROXY_URL=socks5h://127.0.0.1:9050
```

### Docker Tor

If Tor runs as a separate Docker service:

```env
TOR_PROXY_URL=socks5h://tor:9050
```

---

## Target File Format

### `targets.json`

```json
[
  {
    "label": "forum",
    "url": "https://example.com"
  }
]
```

This file defines the initial URLs or seed targets the crawler will monitor.

---

## Watchlist Format

### `watchlist.json`

```json
[
  { "type": "email", "pattern": "test@example.com", "label": "test" },
  { "type": "domain", "pattern": "mail.ru", "label": "test" },
  { "type": "phone", "pattern": "01012345678", "label": "test" }
]
```

This file defines the indicators that should trigger a detection.

---

## Alert Behavior

Alerts are generated only when:

- an extracted value matches a watchlist pattern, and
- the same match is not suppressed by the configured cooldown period

Supported alert channels:

- Discord Webhook
- Telegram Bot

---

## Screenshot Evidence

When screenshot capture is enabled:

```env
SCREENSHOT_ENABLED=true
```

the crawler can save visual evidence of matched pages using Playwright.

This is useful for investigation, reporting, and audit trails.

---

## Troubleshooting

### No crawling activity

Check the following:

- PostgreSQL is running
- `DATABASE_URL` is correct
- the `targets` table is populated
- the scheduler is running normally

### No alerts are sent

Check the following:

- `watchlist.json` contains valid patterns
- alert webhook or bot settings are correct
- cooldown is not suppressing repeated alerts
- extraction is actually producing matches

### `.onion` pages do not load

Check the following:

- Tor is running
- `TOR_PROXY_URL` is correct
- the crawler is configured to use the proxy

### Playwright screenshot errors

Run:

```bash
playwright install
```

and ensure the browser dependencies are installed correctly.

---

## Operational Notes

- Very low `MAX_DEPTH` reduces coverage.
- Very strict patterns reduce match rates.
- Very high cooldown values reduce repeated alerts.
- Large target sets may require more workers and stronger deduplication control.

---

## Recommended Setup

For stable operation:

1. Use PostgreSQL instead of temporary local storage.
2. Keep `MAX_DEPTH` low at first.
3. Start with a small watchlist and expand gradually.
4. Verify matching and alert flow before scaling target volume.
5. Separate local and Docker configuration clearly.

---
