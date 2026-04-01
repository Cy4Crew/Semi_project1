# Darkweb Monitor

Darkweb Monitor is a Python-based monitoring system for **surface web and darkweb (.onion) sources**.  
It crawls target pages, extracts indicators such as emails, domains, IP addresses, usernames, phone numbers, and crypto addresses, compares them against a watchlist, stores the results in PostgreSQL, and delivers alerts through configured channels.

It also ships with a lightweight web UI and REST API for reviewing targets, pages, hits, extracted items, and alerts.

---

## Overview

This project is designed around a continuous monitoring loop:

1. Load crawl targets and watchlist entries from JSON seed files
2. Queue eligible targets for crawling
3. Fetch pages with normal HTTP requests or through Tor
4. Extract structured indicators from page content
5. Match extracted values against a watchlist
6. Save evidence and metadata into PostgreSQL
7. Trigger alert delivery through stdout, Discord, or Telegram
8. Expose the collected data through a FastAPI backend and static UI

The repository supports both **local execution** and **Docker-based execution**.

---

## Main Features

- **Darkweb support with Tor**
  - `.onion` crawling through a SOCKS proxy
  - Optional Tor routing for all requests
- **Asynchronous crawling**
  - Multi-worker queue-based scheduler
  - Depth-based expansion for discovered links
- **Indicator extraction**
  - Email
  - Domain
  - IPv4
  - Phone number
  - Username-like values
  - Crypto-related patterns depending on extractor rules
- **Watchlist matching**
  - Exact normalized matching
  - Regex watchlist entries supported
- **Evidence collection**
  - HTML dump
  - Text dump
  - Optional screenshot capture with Playwright
- **Alert delivery**
  - stdout
  - Discord webhook
  - Telegram bot
- **FastAPI backend**
  - Summary endpoint
  - Target management
  - Watchlist management
  - Recent pages / hits / extracted items / alerts
  - Reload endpoint for seed files
- **Static UI**
  - Dashboard
  - Targets
  - Watchlist
  - Hits
  - Alerts
  - Investigation / analytics / graph pages

---

## Repository Structure

```text
.
├── app/
│   ├── api/
│   │   ├── main.py
│   │   ├── routes_targets.py
│   │   ├── routes_watchlist.py
│   │   ├── routes_hits.py
│   │   └── routes_pages.py
│   ├── core/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   └── seed_loader.py
│   ├── crawler/
│   │   ├── scheduler.py
│   │   ├── fetcher.py
│   │   ├── extractor.py
│   │   ├── matcher.py
│   │   └── screenshot.py
│   ├── notifier/
│   │   ├── worker.py
│   │   ├── discord.py
│   │   └── telegram.py
│   ├── repository/
│   │   ├── alerts.py
│   │   ├── extracted_items.py
│   │   ├── pages.py
│   │   ├── targets.py
│   │   ├── watchlist.py
│   │   └── watchlist_hits.py
│   ├── models/
│   ├── init_db.py
│   └── __init__.py
├── ui/
│   ├── index.html
│   ├── targets.html
│   ├── watchlist.html
│   ├── hits.html
│   ├── alerts.html
│   ├── pages.html
│   ├── analytics.html
│   ├── graph.html
│   ├── investigation.html
│   └── assets/
├── docker-compose.yml
├── Dockerfile
├── run.py
├── run.bat
├── reset.bat
├── restart_docker.bat
├── targets.json
├── watchlist.json
├── .env.example
├── README.md
└── README_OPERATIONS.md
```

---

## Architecture

```text
targets.json / watchlist.json
        ↓
     seed_loader
        ↓
      PostgreSQL
        ↓
      scheduler
        ↓
       queue
        ↓
      workers
        ↓
  fetch → extract → match
        ↓
 save pages / extracted_items / hits / alerts
        ↓
   alert_worker delivery
        ↓
  FastAPI + static UI
```

---

## Execution Modes

The entry point is `run.py`.

Supported modes:

```bash
python run.py all
python run.py api
python run.py crawler
python run.py alert_worker
python run.py init_db
```

### Mode details

- `all`
  - Starts API server, crawler, and alert worker together
- `api`
  - Starts only the FastAPI application
- `crawler`
  - Starts only the scheduler and crawl workers
- `alert_worker`
  - Starts only the alert delivery worker
- `init_db`
  - Creates required tables, indexes, and loads seed data

On startup for non-init modes, the application also resets queued target state in the database to avoid stuck queue flags from previous runs.

---

## Requirements

### Local
- Python 3.11+ recommended
- PostgreSQL
- Playwright browser dependencies
- Tor, if using `.onion` crawling outside Docker

### Docker
- Docker
- Docker Compose

---

## Quick Start with Docker

1. Copy environment file:

```bash
cp .env.example .env
```

2. Review `.env` values.

3. Start the stack:

```bash
docker-compose up --build
```

4. Open the service:

```text
http://localhost:8000
```

The Docker stack includes:

- `db` → PostgreSQL 16
- `tor` → SOCKS proxy for onion access
- `app` → FastAPI + crawler + alert worker container

### Docker-mounted paths

The container mounts these paths from the repository:

- `./evidence -> /app/evidence`
- `./ui -> /app/ui`
- `./targets.json -> /app/targets.json`
- `./watchlist.json -> /app/watchlist.json`

This means screenshots, HTML dumps, and text dumps remain available on the host machine.

---

## Quick Start Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
playwright install
```

2. Prepare PostgreSQL and update `.env`.

3. Initialize the database:

```bash
python run.py init_db
```

4. Start the full application:

```bash
python run.py
```

Or explicitly:

```bash
python run.py all
```

---

## Configuration

Configuration is defined in `app/core/config.py` through environment variables.

### Example `.env`

```env
API_HOST=0.0.0.0
API_PORT=8000
API_KEY=changeme

DATABASE_URL=postgresql://intel:intelpass@db:5432/intel

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

TOR_ENABLED=true
TOR_FOR_ALL_REQUESTS=false
TOR_SOCKS_HOST=tor
TOR_SOCKS_PORT=9050
TOR_PROXY_URL=socks5h://tor:9050

REQUEST_TIMEOUT_SECONDS=60
```

### Important settings

- `API_HOST`, `API_PORT`
  - API server bind address and port
- `API_KEY`
  - Required for protected write operations
- `DATABASE_URL`
  - PostgreSQL connection string
- `POLL_INTERVAL_SECONDS`
  - Producer loop interval
- `WORKER_COUNT`
  - Number of concurrent crawl workers
- `MAX_DEPTH`
  - Maximum recursive link expansion depth
- `MAX_PAGES_PER_HOST`
  - Per-cycle page cap per host
- `ALERT_COOLDOWN_SECONDS`
  - Prevents repeated alerts for the same hit too frequently
- `SCREENSHOT_ENABLED`
  - Enables Playwright screenshots
- `PLAYWRIGHT_TIMEOUT_MS`
  - Screenshot page load timeout
- `TOR_ENABLED`
  - Enables Tor-aware fetching
- `TOR_FOR_ALL_REQUESTS`
  - Routes all traffic through Tor when enabled

---

## Seed Files

### `targets.json`

Defines seed targets to crawl.

Example:

```json
[
  {
    "seed_url": "http://exampleonionaddress.onion/",
    "label": "target-001"
  }
]
```

### `watchlist.json`

Defines values to monitor.

Supported styles include:

- single pattern
- multiple patterns
- regex patterns

Example:

```json
[
  {
    "type": "email",
    "pattern": "test@example.com",
    "label": "demo-email"
  },
  {
    "type": "domain",
    "patterns": ["mail.ru", "proton.me"],
    "label": "demo-domain"
  },
  {
    "type": "domain",
    "patterns": [".*\\.ru$", ".*\\.su$"],
    "is_regex": true,
    "label": "regex-domain"
  }
]
```

The loader accepts:

- `type`
- `pattern`
- `patterns`
- `label`
- `is_regex`

---

## API Overview

### Public endpoints

- `GET /health`
- `GET /`
- `GET /api/summary`
- `GET /api/targets`
- `GET /api/watchlist`
- `GET /api/hits/recent`
- `GET /api/extracted/recent`
- `GET /api/alerts/recent`
- `GET /api/pages/recent`

### Protected endpoints

These require the configured API key:

- `POST /api/reload`
- `POST /api/targets`
- `DELETE /api/targets/{target_id}`
- `POST /api/watchlist`
- `DELETE /api/watchlist/{watchlist_id}`

### Utility routes

- `/evidence/...`
- `/app/evidence/screenshots/{filename:path}`
- `/debug/screenshot/{filename:path}`

The extra screenshot routes exist to keep previously stored screenshot paths accessible even when legacy path formats appear in the database.

---

## UI Pages

The project contains a static frontend under `ui/`.

Main pages include:

- `index.html`
- `targets.html`
- `watchlist.html`
- `hits.html`
- `alerts.html`
- `pages.html`
- `analytics.html`
- `graph.html`
- `investigation.html`

These pages are served by FastAPI under `/ui` and the root dashboard is mapped to `index.html`.

---

## Data Model

The database is initialized in `app/init_db.py`.

### Core tables

- `targets`
  - crawl seeds and queue state
- `pages`
  - fetched page metadata and evidence paths
- `extracted_items`
  - structured indicators extracted from pages
- `watchlist`
  - monitored patterns and regex entries
- `watchlist_hits`
  - matches between extracted items and watchlist entries
- `alerts`
  - per-channel delivery records

### Stored page metadata includes

- target reference
- URL and host
- title
- status code
- content hash
- fetched timestamp
- screenshot path
- raw HTML path
- text dump path
- meaningful/skip flags
- error message

---

## How the Crawl Pipeline Works

### 1. Seed loading
`init_db()` loads `targets.json` and `watchlist.json` into PostgreSQL.

### 2. Producer loop
The scheduler periodically queries due targets using revisit timing rules.

### 3. Queueing
Eligible targets are normalized, marked queued, and pushed into an async queue.

### 4. Worker processing
Each worker fetches the page, extracts indicators, saves page records, and evaluates matches.

### 5. Link expansion
If depth and filtering rules allow it, discovered links are enqueued for deeper crawling.

### 6. Alert generation
New hits create alert records for delivery channels.

### 7. Alert delivery
The alert worker reads pending alerts and sends them to stdout, Discord, or Telegram.

---

## Alerts

Alert delivery is implemented in `app/notifier/worker.py`.

Supported channels:

- `stdout`
- `discord`
- `telegram`

Alert messages include:

- matched watchlist type
- watch value
- matched extracted value
- source URL
- title, when available
- label, when available
- screenshot path, when available

Cooldown handling is controlled with `ALERT_COOLDOWN_SECONDS`.

---

## Evidence Output

The application writes evidence into:

```text
evidence/
├── html/
├── text/
└── screenshots/
```

Generated outputs may include:

- raw HTML snapshot
- extracted text dump
- Playwright screenshot

This is useful for later validation and investigation.

---

## Common Run Commands

### Full stack
```bash
python run.py all
```

### API only
```bash
python run.py api
```

### Crawler only
```bash
python run.py crawler
```

### Alert worker only
```bash
python run.py alert_worker
```

### Docker stack
```bash
docker-compose up --build
```

---

## Expected Behavior

When the system is working correctly, you should see:

- targets loaded into the database
- pages being fetched continuously
- extracted items increasing over time
- recent hits when watchlist matches occur
- alert records only for real hit events
- screenshots saved when screenshot capture is enabled

---

## Troubleshooting Summary

- No pages fetched
  - check DB connection, targets, queue state, and scheduler loop
- No extracted items
  - verify fetch results and extractor logic
- No hits
  - verify watchlist type, normalization, and regex correctness
- No alerts
  - verify webhook/token configuration and cooldown behavior
- No screenshots
  - verify Playwright installation and `SCREENSHOT_ENABLED=true`

---

## Notes

- `.onion` crawling requires Tor connectivity.
- Routing all traffic through Tor may significantly slow crawling.
- Large `MAX_DEPTH` and high worker counts can rapidly increase load.
- Regex watchlist entries should be validated carefully to avoid noisy matches.
- Evidence directories should be persisted in production.

---

## Additional Documentation

Detailed runtime behavior, debugging flow, and operational notes are documented in [README_OPERATIONS.md](README_OPERATIONS.md).
