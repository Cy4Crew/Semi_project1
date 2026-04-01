# README_OPERATIONS  
## Operational Guide for Runtime, Data Flow, and Troubleshooting

This document explains how to operate the project safely, how the runtime pieces interact, and what to check when the system does not behave as expected.

It is written against the current repository structure, not a generic template.

---

## 1. Runtime architecture

The project has four runtime planes that share the same PostgreSQL database.

### A. Core monitoring plane
Components:

- `run.py`
- `app/crawler/*`
- `app/api/*`
- `app/notifier/*`

This is the basic monitoring loop:
target loading → crawl → extract → match → store → alert → UI

### B. Telegram intelligence plane
Components:

- `app/telegram/telegram_bridge.py`
- `app/telegram/scanner.py`
- `app/telegram/recorder.py`

This plane consumes Telegram links discovered from crawled pages and records additional intelligence into `tg_*` tables.

### C. Wallet analysis plane
Components:

- `analyzer/worker.py`
- `analyzer/tracer.py`
- `analyzer/routes_graph.py`

This plane traces wallets and transaction edges and provides graph data to the UI.

### D. External enrichment plane
Components:

- `app/api/routes_rl.py`

This plane fetches and caches ransomware.live statistics, groups, and recent victims.

---

## 2. Actual startup flow

When `python run.py all` is executed, the code does the following:

1. sets up logging
2. opens the database pool
3. runs `init_db(load_seed_data=True)`
4. creates core tables, indexes, views, and migrations
5. applies `analyzer/schema_wallet_tracker.sql`
6. loads `targets.json` and `watchlist.json`
7. ensures ransomware.live cache rows exist
8. resets stale `targets.is_queued` flags
9. starts:
   - FastAPI server
   - crawler scheduler
   - alert worker
   - Telegram bridge

This is important because the application is designed to recover from interrupted queue state by clearing stale `is_queued` flags on startup.

---

## 3. Scheduler and crawler behavior

Main file: `app/crawler/scheduler.py`

### Producer loop
The producer loop:

- wakes up every `POLL_INTERVAL_SECONDS`
- clears cycle-local tracking sets
- fetches due targets from DB
- marks them queued
- enqueues their seed URLs

### Due target condition
A target is considered due when:

- `enabled = TRUE`
- `is_queued = FALSE`
- `last_fetched_at IS NULL`  
  or
- `last_fetched_at <= NOW() - revisit_after_seconds`

### Queue model
Queue items contain:

- `url`
- `depth`
- `target_id`

### URL handling
The scheduler:

- normalizes URLs
- removes fragments
- rejects unsupported schemes
- caps per-host crawl spread with `MAX_PAGES_PER_HOST`
- uses basic URL classification to reduce low-value paths

### Worker loop
Each worker:

1. gets a queued URL
2. calls `fetch_page()`
3. saves page state
4. extracts indicators
5. stores extracted items
6. matches against watchlist
7. creates hits and alerts if needed
8. enqueues discovered links if depth rules allow
9. marks the target done or failed

---

## 4. Fetching and Tor behavior

Main file: `app/crawler/fetcher.py`

### Proxy rules
The fetcher enables Tor when:

- `TOR_ENABLED=true`
- and either:
  - the URL is `.onion`, or
  - `TOR_FOR_ALL_REQUESTS=true`

### Important consequence
If Tor is not healthy, `.onion` crawling will fail even when the crawler itself is running normally.

### TLS behavior
For `.onion` URLs, the code relaxes certificate verification.  
For normal web URLs, verification stays enabled.

### Extracted fetch result
Each fetch produces:

- final URL
- host
- status code
- title
- raw HTML
- plain text
- content hash
- normalized outgoing links
- error message if fetch failed

---

## 5. Extraction behavior

Main file: `app/crawler/extractor.py`

### Extracted indicator families
- email
- onion
- domain
- phone
- username
- ipv4
- url
- telegram
- btc
- api_key
- hash

### False-positive filtering
The extractor rejects common noise:

- asset file suffixes as domains
- example / localhost values
- malformed phone-like values
- trivial usernames
- low-quality repetitive hashes

### Output shape
Every extracted item contains:

- `type`
- `raw`
- `normalized`
- `group_key`

This normalized representation is what later drives matching and deduplication.

---

## 6. Watchlist matching semantics

Main file: `app/crawler/matcher.py`

This is one of the most important operational details in the project.

### Matching priority
1. exact normalized match
2. regex full match

### Hit fingerprint
Hit fingerprint is based on:

- watchlist item id
- extracted type
- normalized value
- page URL

So the same value on a new URL becomes a new hit record.

### Alert fingerprint
Alert fingerprint is based on:

- watchlist item id
- extracted type
- normalized value

So the same value is not alerted repeatedly just because it appeared on many URLs.

### What this means in practice
- repeated scan of same URL → existing hit updated
- same matched value on another page → new hit may be recorded
- alerts remain deduplicated at value level

This is why hit count and alert count will often differ.

---

## 7. Alert worker behavior

Main file: `app/notifier/worker.py`

The alert worker:

1. fetches pending alerts from `alerts`
2. loads full hit detail
3. sends message to the configured channel
4. marks status as `sent` or `failed`

### Supported outbound channels
- Discord
- Telegram
- stdout for internal visibility

### Important note
The UI intentionally excludes `stdout` alerts from some counts.  
So database rows and dashboard counts may not match if you compare them blindly.

---

## 8. Telegram bridge behavior

Main file: `app/telegram/telegram_bridge.py`

The Telegram bridge polls newly extracted Telegram links from `extracted_items` where `type = 'telegram'`.

### What it does
- reads new Telegram link artifacts after web crawling
- parses target IDs from `t.me/...` links
- distinguishes private invites and public names
- joins or inspects channels
- detects bots
- records raw messages and metadata
- stores wallets and extracted artifacts
- bridges BTC/ETH wallets into the wallet-tracking subsystem

### Stored Telegram tables
- `tg_channels`
- `tg_channel_admins`
- `tg_raw_messages`
- `tg_wallets`
- `tg_extracted_info`
- `tg_private_channels`
- `tg_members`

### Practical risk
If Telegram credentials are absent or invalid, the full `all` mode can still run, but Telegram collection will not be functional.

---

## 9. Wallet analyzer behavior

Main files:

- `analyzer/worker.py`
- `analyzer/tracer.py`
- `analyzer/routes_graph.py`

### Worker role
The analyzer worker processes:

- `trace_queue`
- `tracked_wallets`

It polls transaction history and inserts or updates graph edges.

### BTC and EVM split
- BTC flow uses `mempool_client`
- EVM flow uses the configured external history client

### Graph API role
`analyzer/routes_graph.py` reads tracked wallets and edges and exposes them to the frontend under `/api/graph/...`.

### Operational consequence
This subsystem is logically separate from the crawler, but the repository connects them through Telegram wallet extraction and shared PostgreSQL state.

---

## 10. Database tables you should actually watch

### Core crawler health
- `targets`
- `pages`
- `extracted_items`
- `watchlist_hits`
- `alerts`

### Telegram health
- `tg_raw_messages`
- `tg_wallets`
- `tg_extracted_info`

### Enrichment health
- `darkweb_posts`
- `rl_info_cache`
- `rl_victims_cache`

### Wallet graph health
- `tracked_wallets`
- `tracked_edges`
- `trace_queue`

If the UI looks empty, one of these tables is usually where the failure first becomes visible.

---

## 11. Normal operating procedure

### First setup
1. create `.env`
2. confirm PostgreSQL connection values
3. confirm Tor is available if using `.onion`
4. fill `targets.json`
5. fill `watchlist.json`
6. run DB init or full stack
7. verify `/health`
8. verify `/api/summary`

### Standard run
```bash
docker compose up -d --build
docker compose logs -f
```

### Full reset
```bash
docker compose down -v
```

Or use:
- `reset.bat`

### Docker recovery on Windows
Use:
- `restart_docker.bat`

This script kills Docker Desktop processes, shuts down WSL, restarts Docker Desktop, and waits until `docker info` succeeds.

---

## 12. Verification checklist after startup

After starting the stack, verify in this order:

### A. API
- `GET /health` returns `{ "ok": true }`
- root page loads
- UI assets under `/ui/...` load

### B. Targets loaded
- `targets` table is populated
- `/api/summary` shows target count > 0

### C. Crawling
- `pages` rows increase
- evidence files appear under `evidence/`
- crawler logs show fetch activity

### D. Extraction
- `extracted_items` rows increase

### E. Matching
- `watchlist_hits` rows increase only when extracted values actually match the watchlist

### F. Alerts
- `alerts` rows appear as `pending` then `sent` or `failed`

### G. Telegram
- `tg_*` tables increase only if Telegram links are extracted and bridge credentials are valid

### H. Wallet graph
- `tracked_wallets` / `tracked_edges` increase only if wallet tracing is enabled and seeded

---

## 13. Common failure patterns

### 13.1 `.onion` pages never load
Check:

- `tor` container is running
- `TOR_ENABLED=true`
- `TOR_SOCKS_HOST` and `TOR_SOCKS_PORT` are correct
- target URLs are actually reachable

### 13.2 UI loads but no data appears
Check:

- `targets.json` was loaded
- `watchlist.json` is valid JSON
- `pages` table is increasing
- `/api/summary` is not zeroed
- browser is not caching stale frontend assets

### 13.3 Alerts do not arrive
Check:

- alert channel credentials exist
- `alerts` table contains pending rows
- alert worker is running
- rows are becoming `failed`
- the related webhook/chat IDs are correct

### 13.4 Hits appear but alerts are fewer than expected
Usually normal.  
Reason:

- hits are deduplicated per URL
- alerts are deduplicated per value

This is repository behavior, not necessarily a bug.

### 13.5 Telegram collection does nothing
Check:

- `TELEGRAM_COLLECTOR_API_ID`
- `TELEGRAM_COLLECTOR_API_HASH`
- `TELEGRAM_COLLECTOR_SESSION`
- extracted items actually contain `type='telegram'`

### 13.6 Graph page is empty
Check:

- analyzer worker is running
- `tracked_wallets` has rows
- `tracked_edges` has rows
- graph API router registered successfully at startup

### 13.7 “Internal Server Error” causes JSON parse problems in UI
This happens when frontend code expects JSON but the backend returns an HTML or plain-text error response.  
Check backend logs first, then the corresponding API route.

### 13.8 Reset did not change behavior
If old data still appears, confirm:
- containers were actually recreated
- volumes were removed
- the application is not reading preserved bind-mounted files
- browser cache is cleared

---

## 14. Operational advice for demos and submissions

Because the project combines several subsystems, do not demo every feature at once unless credentials and external services are all verified.

### Stable demo order
1. API + UI
2. crawler
3. evidence saving
4. watchlist hits
5. alerts
6. Telegram bridge
7. wallet graph
8. ransomware.live enrichment

This order isolates failures cleanly.

### For classroom or evaluation use
If reliability matters more than scope, keep the live demo centered on:

- target crawling
- indicator extraction
- watchlist matching
- evidence output
- hit / alert UI

Then describe Telegram and wallet graph as advanced extensions already integrated into the architecture.

---

## 15. Configuration-sensitive files

Treat these as operationally critical:

- `.env`
- `targets.json`
- `watchlist.json`
- `docker-compose.yml`
- `run.py`

If behavior suddenly changes, check these first before assuming a code defect.

---

## 16. Final caution

This codebase shares one database across crawler, Telegram bridge, ransomware enrichment, and wallet tracing. That design is powerful, but it also means one misconfigured subsystem can make the whole stack look broken. When debugging, isolate by subsystem and verify table growth one layer at a time.\n
