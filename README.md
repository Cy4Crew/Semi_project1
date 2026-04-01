# Darkweb Monitor

This project is a Python-based intelligence collection and analysis platform built around four connected functions:

1. **Surface web / darkweb monitoring**
2. **Indicator extraction and watchlist matching**
3. **Telegram-based intelligence collection**
4. **Crypto wallet trace analysis and graph visualization**

The system is not a single crawler only. It is a **hybrid monitoring stack** that combines web crawling, IoC extraction, alerting, Telegram collection, and wallet tracing into one PostgreSQL-backed service.

---

## What the project does

At runtime, the project continuously:

- loads crawl targets from `targets.json`
- loads watchlist rules from `watchlist.json`
- fetches web pages from normal sites and `.onion` sites
- extracts indicators such as email, domain, IP, Telegram links, URLs, BTC addresses, hashes, and API-key-like strings
- compares extracted values to the watchlist
- stores evidence and hit history in PostgreSQL
- sends alerts through Discord or Telegram when new matches appear
- exposes collected data through a FastAPI backend and static UI
- collects Telegram channel / bot / chat intelligence through a separate bridge
- registers discovered wallet addresses into the wallet-tracing subsystem
- visualizes wallet relationships through graph APIs and UI pages

---

## Main components

### 1. Web crawler
Located mainly in:

- `app/crawler/scheduler.py`
- `app/crawler/fetcher.py`
- `app/crawler/extractor.py`
- `app/crawler/matcher.py`
- `app/crawler/screenshot.py`

Responsibilities:

- schedule due targets from the database
- fetch pages asynchronously
- support Tor routing for `.onion` URLs
- normalize discovered links
- save HTML/text/screenshot evidence
- extract indicators from page text
- generate watchlist hits and queue alerts

### 2. FastAPI backend
Located mainly in:

- `app/api/main.py`
- `app/api/routes_targets.py`
- `app/api/routes_watchlist.py`
- `app/api/routes_hits.py`
- `app/api/routes_pages.py`
- `app/api/routes_rl.py`

Responsibilities:

- health check
- summary counts
- target CRUD
- watchlist CRUD
- recent hits / pages / alerts
- ransomware.live-related endpoints
- evidence and UI serving
- graph API registration from `analyzer/routes_graph.py`

### 3. Alert subsystem
Located in:

- `app/notifier/worker.py`
- `app/notifier/discord.py`
- `app/notifier/telegram.py`

Responsibilities:

- poll pending alerts from DB
- format hit details
- send outbound notifications
- mark alerts as sent or failed

### 4. Telegram intelligence bridge
Located in:

- `app/telegram/telegram_bridge.py`
- `app/telegram/scanner.py`
- `app/telegram/recorder.py`
- `app/telegram/bot_handler.py`

Responsibilities:

- monitor Telegram links extracted from crawled pages
- join or inspect public Telegram channels
- distinguish bots vs normal channels
- collect raw messages, members, wallets, private invite links, and extracted artifacts
- bridge discovered BTC / ETH wallets into the wallet tracker

### 5. Wallet tracing / graph analysis
Located in:

- `analyzer/worker.py`
- `analyzer/tracer.py`
- `analyzer/routes_graph.py`
- `analyzer/etherscan_client.py`
- `analyzer/mempool_client.py`

Responsibilities:

- maintain tracked wallets and trace queue
- poll EVM and BTC transaction activity
- aggregate wallet edges into the database
- expose graph data for the UI

---

## Repository structure

```text
.
├── analyzer/
│   ├── worker.py
│   ├── tracer.py
│   ├── routes_graph.py
│   ├── etherscan_client.py
│   ├── mempool_client.py
│   └── evm_filter_config.py
├── app/
│   ├── api/
│   ├── core/
│   ├── crawler/
│   ├── models/
│   ├── notifier/
│   ├── repository/
│   ├── telegram/
│   └── init_db.py
├── ui/
│   ├── index.html
│   ├── hits.html
│   ├── alerts.html
│   ├── pages.html
│   ├── targets.html
│   ├── watchlist.html
│   ├── graph.html
│   ├── analytics.html
│   ├── investigation.html
│   ├── incidents.html
│   ├── crypto_wallet.html
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

## High-level flow

```text
targets.json + watchlist.json
            ↓
         init_db
            ↓
        PostgreSQL
            ↓
   scheduler / workers
            ↓
   fetch → extract → match
            ↓
 pages / extracted_items / hits / alerts
            ↓
  FastAPI + UI + notifier worker
            ↓
 Discord / Telegram delivery

Telegram links found in pages
            ↓
telegram_bridge
            ↓
tg_* tables + wallet registration
            ↓
tracked_wallets / trace_queue
            ↓
analyzer.worker / tracer
            ↓
graph API + wallet UI
```

---

## Runtime modes

The entry point is `run.py`.

Supported modes:

```bash
python run.py all
python run.py api
python run.py crawler
python run.py alert_worker
python run.py init_db
```

### `python run.py all`
Starts:

- FastAPI server
- crawler scheduler and workers
- alert worker
- Telegram bridge

Use this for full local execution.

### `python run.py api`
Starts only the API and static UI.

### `python run.py crawler`
Starts only the crawler loop.

### `python run.py alert_worker`
Starts only the alert delivery worker.

### `python run.py init_db`
Creates tables, indexes, views, migrations, wallet tracker schema, and optionally seed data.

---

## Environment variables

Start from `.env.example`.

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

TELEGRAM_COLLECTOR_API_ID=
TELEGRAM_COLLECTOR_API_HASH=
TELEGRAM_COLLECTOR_SESSION=

MORALIS_API_KEY=
```

### Important notes

- `TOR_ENABLED=true` is required for `.onion` crawling.
- `.onion` requests are routed through Tor automatically.
- Telegram bridge will not work without collector credentials.
- Wallet tracing for EVM chains depends on the configured external API client.
- Alert channels are enabled only if their credentials are set.

---

## Docker execution

### 1. Prepare `.env`
Copy `.env.example` to `.env` and fill required values.

### 2. Start all services
```bash
docker compose up --build
```

### 3. Run in background
```bash
docker compose up -d --build
```

### 4. View logs
```bash
docker compose logs -f
```

### 5. Stop services
```bash
docker compose down
```

### Included services

`docker-compose.yml` defines:

- `db`: PostgreSQL 16
- `tor`: SOCKS proxy container for `.onion` access
- `app`: main FastAPI + crawler application
- `worker`: analyzer wallet worker

---

## Local execution

Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Initialize DB:

```bash
python run.py init_db
```

Run everything:

```bash
python run.py all
```

---

## Windows helper scripts

### `run.bat`
Starts containers and follows logs.

### `reset.bat`
Stops containers and removes volumes. This fully resets DB state.

### `restart_docker.bat`
Restarts Docker Desktop and waits until the daemon is ready.

---

## Core database tables

The database schema is initialized in `app/init_db.py`.

### Core monitoring tables
- `targets`
- `pages`
- `extracted_items`
- `watchlist`
- `watchlist_hits`
- `alerts`

### Telegram collection tables
- `tg_channels`
- `tg_channel_admins`
- `tg_raw_messages`
- `tg_wallets`
- `tg_extracted_info`
- `tg_private_channels`
- `tg_members`

### Darkweb / ransomware ingestion tables
- `darkweb_posts`
- `rl_info_cache`
- `rl_victims_cache`

### Wallet tracing tables
Created from `analyzer/schema_wallet_tracker.sql` and used by the analyzer / graph subsystem.

---

## Indicator types currently extracted

From `app/crawler/extractor.py`, the crawler can extract:

- `email`
- `onion`
- `domain`
- `phone`
- `username`
- `ipv4`
- `url`
- `telegram`
- `btc`
- `api_key`
- `hash`

The extractor also normalizes values and rejects common false positives such as:

- static asset suffixes for domains
- placeholder domains
- localhost URLs
- weak or repetitive hash-like strings
- noisy usernames
- invalid phone-like strings

---

## Watchlist behavior

The watchlist supports:

- exact normalized matching
- regex matching via `is_regex=true`

Matching flow:

1. extracted value is normalized
2. exact match is checked first
3. regex match is checked next
4. a hit is created per **URL + matched value**
5. an alert is created per **value**, not for every repeated URL

That means:

- same URL scanned again → existing hit updated, no new alert
- same value found on a new URL → new hit possible, alert deduplicated by value
- alert delivery happens only for configured channels

---

## Alert behavior

Channels are activated automatically:

- Discord if `DISCORD_WEBHOOK_URL` is set
- Telegram if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set

Alerts are stored first in DB, then processed by the alert worker.

This gives the project:

- retry visibility
- failure logging
- deduplication by `alert_fingerprint`

---

## UI pages

The `ui/` directory includes:

- `index.html` — overview dashboard
- `targets.html` — target list / management
- `watchlist.html` — watchlist list / management
- `pages.html` — recent page history
- `hits.html` — hit history
- `alerts.html` — alert status
- `graph.html` — relationship / wallet graph
- `analytics.html` — aggregate analytics
- `investigation.html` — case-style detail view
- `incidents.html` — incident-focused page
- `crypto_wallet.html` — wallet-oriented view

The backend serves:

- `/` → overview page
- `/ui/...` → static UI assets
- `/evidence/...` → saved evidence files

---

## Main API endpoints

### Core
- `GET /health`
- `GET /`
- `GET /api/summary`
- `POST /api/reload`

### Targets
Defined in `app/api/routes_targets.py`

### Watchlist
Defined in `app/api/routes_watchlist.py`

### Hits / alerts / pages
Defined in:
- `app/api/routes_hits.py`
- `app/api/routes_pages.py`

### Ransomware.live integration
Defined in `app/api/routes_rl.py`

Examples:
- `GET /api/rl/info`
- `POST /api/rl/info/refresh`
- `GET /api/rl/groups`
- `GET /api/rl/victims`

### Graph endpoints
Mounted from `analyzer/routes_graph.py` under:

- `/api/graph/...`

---

## Evidence output

The crawler stores evidence under `evidence/`:

- `evidence/html`
- `evidence/text`
- `evidence/screenshots`

This is used for:

- later verification
- investigation UI
- alert context
- screenshot links in hits

---

## External dependencies and integrations

This project depends on several external services or APIs depending on enabled features:

- Tor proxy container for `.onion` fetching
- PostgreSQL for persistence
- Playwright Chromium for screenshots
- Telegram client credentials for bridge collection
- Discord webhook for notifications
- Telegram bot API for notifications
- ransomware.live API for group / victim data
- Moralis or equivalent EVM history API through analyzer client
- mempool-based BTC API client for BTC tracing

---

## Known characteristics of the current codebase

This repository already contains several subsystems in one codebase. Because of that:

- it is broader than a typical course crawler project
- crawler, Telegram bridge, and wallet analyzer are coupled through the same DB
- runtime logs can become noisy if all components run together
- deployment should be staged carefully if you want stable demos

For a presentation or class submission, the cleanest explanation is:

> “This is an integrated monitoring and analysis platform that starts from web crawling, expands into Telegram intelligence, and links discovered wallets into a graph-based crypto trace workflow.”

---

## Recommended demo scope

For a stable demo, enable these first:

1. crawler
2. watchlist matching
3. evidence storage
4. API/UI
5. Discord or Telegram alerts

Then add, only if credentials are ready:

6. Telegram bridge
7. wallet graph tracing
8. ransomware.live enrichment

This reduces failure points during demonstration.

---

## Best practice

Keep `targets.json`, `watchlist.json`, `.env`, and evidence paths aligned with the deployed environment. Most startup failures in this project come from configuration mismatch, missing credentials, or stale database state rather than from the crawler logic itself.

---

## Additional Documentation

Detailed runtime behavior, debugging flow, and operational notes are documented in [README_OPERATIONS.md](README_OPERATIONS.md).
