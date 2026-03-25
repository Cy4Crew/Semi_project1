# Darkweb Monitor (Operational Guide)

A real-time monitoring system that crawls surface web and darkweb sources, extracts indicators, stores evidence, and triggers alerts.

---

## Overview

This system continuously monitors targets, extracts artifacts, compares them against a watchlist, and sends alerts when matches are detected.

---

## Data Flow (Critical)

1. Load targets (`targets.json`)
2. Scheduler enqueues jobs
3. Fetch page (HTTP / Tor)
4. Extract indicators
5. Normalize values
6. Match against watchlist
7. Save to DB (`pages`, `findings`)
8. Deduplicate
9. Trigger alert

---

## Project Structure

```
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

---

## Database Structure (Essential)

- `targets` → seed URLs
- `pages` → crawled pages
- `findings` → extracted indicators
- `alerts` → triggered alerts

Relation:

```
targets → pages → findings → alerts
```

---

## Alert Logic (Exact)

Alert triggers only when:

1. `normalized` value matches watchlist pattern
2. `(type + normalized)` not seen within cooldown

Deduplication key:

```
group_key = type + normalized
```

---

## Watchlist Rules

- `pattern` is exact match or regex (depending on matcher implementation)
- Avoid overly short patterns (causes false positives)
- Recommended:
  - phone: strict format
  - username: min length ≥ 4
  - domain: full domain, not partial

---

## Required Setup

### Install

```
pip install -r requirements.txt
playwright install
```

### PostgreSQL

Local:
```
postgresql://user:password@127.0.0.1:5432/intel
```

Docker:
```
postgresql://user:password@db:5432/intel
```

---

## .env Example

```
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

TOR_ENABLED=true
TOR_FOR_ALL_REQUESTS=false
TOR_SOCKS_HOST=tor
TOR_SOCKS_PORT=9050
TOR_PROXY_URL=socks5h://tor:9050

REQUEST_TIMEOUT_SECONDS=60

```

---

## Tor (.onion)

Local:
```
tor
TOR_PROXY_URL=socks5h://127.0.0.1:9050
```

Docker:
```
TOR_PROXY_URL=socks5h://tor:9050
```

---

## Crawling Behavior (Important)

- `MAX_DEPTH` controls link expansion
- Depth increases only when:
  - link is discovered
  - enqueue condition passes

Common issue:
→ depth stuck at 0 = filtering or condition problem

---

## Logs (Normal Operation)

```
[PRODUCER] due_targets=10
[QUEUE] target_id=1 url=...
[WORKER] picked depth=0 ...
[MATCH] email=test@example.com
[ALERT] sent
```

If missing:
- no MATCH → extraction issue
- no ALERT → cooldown or webhook issue

---

## Troubleshooting

### No crawling
- DB not initialized
- targets table empty

### No match
- watchlist too strict
- extractor not working

### No alert
- cooldown blocking
- webhook not set

### Depth not increasing
- link filter too strict
- `changed` condition blocking

---

## Operational Recommendations

- Start with `MAX_DEPTH=1`
- Use broad patterns initially
- Verify logs before scaling
- Monitor DB (`findings` table)

---

## Summary

This system depends on:

- correct DB state
- proper extraction
- accurate watchlist
- valid alert configuration

Failure in any step breaks the pipeline.
