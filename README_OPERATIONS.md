# README_OPERATIONS

## Overview

This document explains how the system actually runs, how each subsystem interacts with the database, what configuration controls behavior, and what to verify when something fails.

This repository is not only a crawler. It is a combined monitoring and intelligence pipeline with four major parts:

1. web / darkweb crawler
2. watchlist matching and alert subsystem
3. Telegram intelligence collector
4. wallet tracing and graph analysis subsystem

All of them share the same PostgreSQL database.

---

## Full Runtime Architecture

### Core monitoring plane
Files:
- `run.py`
- `app/crawler/scheduler.py`
- `app/crawler/fetcher.py`
- `app/crawler/extractor.py`
- `app/crawler/matcher.py`
- `app/notifier/worker.py`
- `app/api/*`

Responsibilities:
- load targets and watchlist data
- schedule crawl jobs
- fetch pages
- extract indicators
- compare extracted values against the watchlist
- create hit records and alert records
- expose results through API and UI

### Telegram intelligence plane
Files:
- `app/telegram/telegram_bridge.py`
- `app/telegram/scanner.py`
- `app/telegram/recorder.py`
- `app/telegram/bot_handler.py`

Responsibilities:
- consume Telegram links found during crawling
- inspect channels, groups, bots, and invite links
- store Telegram intelligence in `tg_*` tables
- register discovered wallets into the wallet-tracking subsystem

### Wallet analysis plane
Files:
- `analyzer/worker.py`
- `analyzer/tracer.py`
- `analyzer/routes_graph.py`
- `analyzer/etherscan_client.py`
- `analyzer/mempool_client.py`

Responsibilities:
- track BTC / EVM wallets
- poll transaction history
- create graph edges
- expose wallet / graph data to frontend routes

### External enrichment plane
Files:
- `app/api/routes_rl.py`

Responsibilities:
- retrieve ransomware.live data
- cache group and victim information
- expose enrichment data through API

---

## Startup Behavior

The main entry point is `run.py`.

Supported modes:

```bash
python run.py all
python run.py api
python run.py crawler
python run.py alert_worker
python run.py init_db
```

### `python run.py all`
Starts the complete application stack:
- FastAPI server
- crawler scheduler and workers
- alert worker
- Telegram bridge

### `python run.py api`
Starts the backend API and UI only.

### `python run.py crawler`
Starts crawl scheduling and crawl workers only.

### `python run.py alert_worker`
Starts alert delivery processing only.

### `python run.py init_db`
Initializes database schema, indexes, views, and wallet-tracker schema.

---

## Detailed Startup Sequence

When full startup is executed, the repository behavior is effectively:

1. initialize logging
2. initialize DB connections
3. run schema initialization
4. load `targets.json`
5. load `watchlist.json`
6. ensure cache structures exist
7. reset stale queue flags if needed
8. start application processes

This means many apparent runtime issues are actually configuration or seed-data issues, not crawler logic issues.

---

## Docker Services

`docker-compose.yml` defines the main runtime services:

- `db` — PostgreSQL
- `tor` — SOCKS proxy for `.onion` access
- `app` — FastAPI + crawler + notifier + Telegram bridge
- `worker` — wallet analysis worker

### Common commands

Start:
```bash
docker compose up --build
```

Background start:
```bash
docker compose up -d --build
```

Logs:
```bash
docker compose logs -f
```

Stop:
```bash
docker compose down
```

Full reset:
```bash
docker compose down -v
```

---

## Local Development Run

Install dependencies:
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Initialize database:
```bash
python run.py init_db
```

Run full stack:
```bash
python run.py all
```

---

## Windows Helper Scripts

### `run.bat`
Used for container startup and log attachment.

### `reset.bat`
Stops containers and removes volumes. Use this when you need a full DB reset.

### `restart_docker.bat`
Restarts Docker Desktop and waits until Docker daemon becomes available again.

Use `restart_docker.bat` when Windows Docker named pipe errors appear.

---

## Configuration Reference

Start with `.env.example`.

Important variables include:

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

### Configuration notes

- `.onion` crawling requires Tor to be running and reachable.
- normal web crawling can run without Tor unless all traffic is forced through Tor.
- Telegram collection requires collector credentials.
- alert delivery requires valid Discord webhook or Telegram bot credentials.
- wallet tracing requires its external API configuration to be valid.

---

## Data Files

### `targets.json`
Defines crawl seeds.

Typical structure:
```json
[
  {
    "seed_url": "http://exampleonion.onion/",
    "label": "target-001"
  }
]
```

### `watchlist.json`
Defines watchlist rules used during matching.

Watchlist records are normalized during loading and then used for exact or regex matching.

---

## Scheduler and Queue Behavior

Main file: `app/crawler/scheduler.py`

### Producer loop
The producer loop periodically:
- checks due targets
- marks them queued
- inserts seed URLs into the in-memory queue for workers

### Due target logic
A target is due when:
- it is enabled
- it is not already queued
- it has never been fetched, or revisit interval expired

### Queue item contents
Each queue item includes:
- `target_id`
- `url`
- `depth`

### Depth control
Depth expansion is limited by:
- `MAX_DEPTH`
- per-host page cap
- link normalization and deduplication logic

### Worker behavior
Each worker:
1. dequeues one URL
2. fetches the page
3. extracts text and links
4. stores page evidence
5. extracts indicators
6. matches them
7. creates or updates hits
8. creates alerts when allowed
9. enqueues next links if depth allows

---

## Fetching Behavior

Main file: `app/crawler/fetcher.py`

### Request routing
- `.onion` URLs use Tor proxy
- normal URLs use direct requests unless `TOR_FOR_ALL_REQUESTS=true`

### Result contents
A successful fetch can provide:
- final URL
- HTTP status code
- title
- HTML
- text
- content hash
- outgoing links

### Error handling
When fetch fails, the system should still record failure context so the UI and logs reflect that a target was attempted.

### Operational note
If `.onion` targets never load, the first thing to verify is the Tor container and SOCKS configuration, not the scheduler.

---

## Evidence Storage

The crawler stores evidence under `evidence/` such as:
- HTML
- extracted text
- screenshots

This evidence is used for:
- later investigation
- UI review
- alert context
- proof that a hit came from an actual fetched page

---

## Extraction Behavior

Main file: `app/crawler/extractor.py`

The extractor scans page text and URLs for multiple indicator families.

Supported types include:
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

### Extractor normalization
Extraction is not just regex matching. Values are normalized before storage and before matching.

Examples of normalization goals:
- reduce duplicate formatting variants
- reject obvious placeholders
- filter low-quality false positives
- group semantically equivalent values

### False-positive filtering
The extractor attempts to suppress:
- asset filenames misread as domains
- placeholder domains
- localhost or dummy URLs
- malformed phone-like values
- low-confidence usernames
- repetitive non-hash strings

---

## Matching Semantics

Main file: `app/crawler/matcher.py`

This is operationally important because hit counts and alert counts are intentionally different.

### Matching order
1. exact normalized match
2. regex match

### Hit identity
A hit is effectively scoped by:
- watchlist rule
- extracted type
- normalized value
- page URL

That means the same value on another page can produce another hit.

### Alert identity
An alert is effectively scoped by:
- watchlist rule
- extracted type
- normalized value

That means repeated discovery of the same value does not necessarily create repeated alerts.

### Practical consequence
- same value + same URL repeatedly fetched → update existing hit
- same value + different URL → possibly another hit
- same value overall → usually one alert identity

This is expected behavior, not necessarily a bug.

---

## Alert Pipeline

Main files:
- `app/notifier/worker.py`
- `app/notifier/discord.py`
- `app/notifier/telegram.py`

### Flow
1. hit is created
2. alert row is created in DB
3. alert worker polls pending alerts
4. formatted message is sent to channel
5. row becomes `sent` or `failed`

### Channels
- Discord
- Telegram
- optional internal stdout visibility depending on implementation path

### Why this matters
Because alerts are DB-backed, you can inspect failures after the fact instead of losing delivery state in memory.

---

## Telegram Intelligence Collector

Main files:
- `app/telegram/telegram_bridge.py`
- `app/telegram/scanner.py`
- `app/telegram/recorder.py`

The Telegram collector consumes links already discovered by the crawler.

### What it can store
Depending on the link and credentials:
- channels
- members
- messages
- admins
- invite information
- wallets
- extracted text artifacts

### Table families
Common Telegram tables include:
- `tg_channels`
- `tg_channel_admins`
- `tg_raw_messages`
- `tg_wallets`
- `tg_extracted_info`
- `tg_private_channels`
- `tg_members`

### Operational limitation
If collector credentials are missing, the main application can still run, but Telegram intelligence collection will be incomplete or inactive.

---

## Wallet Tracing and Graph Behavior

Main files:
- `analyzer/worker.py`
- `analyzer/tracer.py`
- `analyzer/routes_graph.py`

### Purpose
The wallet subsystem tracks addresses discovered from Telegram or other sources and builds transaction relationships.

### Split by chain family
- BTC tracing uses mempool-style client logic
- EVM tracing uses configured EVM history client logic

### Output
Graph edges and wallet entities are persisted to DB and then exposed to the UI through `/api/graph/*`.

### Operational limitation
If graph APIs return empty data, check wallet tables first before assuming UI problems.

---

## Database Tables to Monitor

### Core crawler pipeline
- `targets`
- `pages`
- `extracted_items`
- `watchlist`
- `watchlist_hits`
- `alerts`

### Telegram subsystem
- `tg_channels`
- `tg_channel_admins`
- `tg_raw_messages`
- `tg_wallets`
- `tg_extracted_info`
- `tg_private_channels`
- `tg_members`

### Enrichment subsystem
- `darkweb_posts`
- `rl_info_cache`
- `rl_victims_cache`

### Wallet subsystem
- `tracked_wallets`
- `tracked_edges`
- `trace_queue`

If the UI looks empty, check table growth in that order.

---

## UI and API Surface

The frontend under `ui/` typically includes pages such as:
- dashboard
- targets
- watchlist
- pages
- hits
- alerts
- analytics
- investigation
- incidents
- graph
- wallet views

Important backend endpoints include:
- `/health`
- `/api/summary`
- `/api/targets`
- `/api/watchlist`
- `/api/hits`
- `/api/pages`
- `/api/alerts`
- `/api/rl/*`
- `/api/graph/*`

Use `/health` first. Then use `/api/summary` to confirm that the backend is reading live data.

---

## Normal Operating Procedure

### First-time setup
1. create `.env`
2. confirm database connection values
3. confirm Tor settings if `.onion` crawling is needed
4. prepare `targets.json`
5. prepare `watchlist.json`
6. initialize DB
7. run full stack
8. check `/health`
9. check `/api/summary`

### Standard run
```bash
docker compose up -d --build
docker compose logs -f
```

### Standard stop
```bash
docker compose down
```

### Full reset
```bash
docker compose down -v
```

Or use `reset.bat` on Windows.

---

## Verification Checklist After Startup

Check in this order:

### 1. API health
- `/health` returns success
- root or UI page loads
- static assets load

### 2. Targets loaded
- targets exist in DB
- `/api/summary` shows target count > 0

### 3. Crawl activity
- `pages` table grows
- logs show fetch activity
- evidence files appear

### 4. Extraction activity
- `extracted_items` grows

### 5. Match activity
- `watchlist_hits` grows only when actual values match

### 6. Alert activity
- `alerts` rows appear
- statuses change from pending to sent or failed

### 7. Telegram activity
- `tg_*` tables grow only if Telegram links are present and credentials work

### 8. Wallet activity
- wallet tracking tables grow only if wallets are registered and analyzer is running

---

## Common Failure Patterns

### `.onion` pages do not load
Check:
- Tor container is running
- Tor host and port match configuration
- target itself is reachable
- requests are actually going through SOCKS proxy

### UI loads but remains empty
Check:
- `targets.json` was loaded
- DB initialized correctly
- scheduler is running
- `/api/summary` has non-zero values
- frontend is not using stale cached assets

### Alerts do not arrive
Check:
- channel credentials are valid
- alert worker is running
- `alerts` table contains rows
- rows are not stuck in failed state

### Hits exist but alerts are fewer
Usually normal because:
- hits are scoped by URL + value
- alerts are scoped by value

### Telegram collector does nothing
Check:
- collector API credentials
- extracted Telegram links actually exist
- Telegram subsystem is enabled in runtime mode

### Graph page is empty
Check:
- analyzer worker is running
- wallet tables contain rows
- graph routes are mounted successfully

### UI shows JSON parse errors
This usually means the frontend expected JSON but the backend returned an HTML/plain-text error. Inspect backend logs for the failing route.

### Reset did not change behavior
Check:
- volumes were actually removed
- browser cache was cleared
- bind-mounted files were not preserved unexpectedly

---

## Demo Guidance

For stable demonstration, do not enable every subsystem at once unless all credentials are verified.

Recommended demo order:
1. API and UI
2. crawler
3. evidence output
4. watchlist hits
5. alerts
6. Telegram collector
7. wallet graph
8. ransomware.live enrichment

This makes failures easier to isolate.

---

## Best Practices

- keep `targets.json` and `watchlist.json` clean and normalized
- reset DB when schema or seed format changes
- verify each subsystem independently
- inspect database tables before assuming UI issues
- treat configuration mismatches as the first suspect
- do not mix demo scope with unverified external integrations

---

## Final Operational Note

Because crawler, Telegram collector, enrichment logic, and wallet analysis all share one database, one broken subsystem can make the whole project look unhealthy. Debug one layer at a time:

configuration → DB → scheduler → fetch → extract → match → alert → collector → analyzer → UI
