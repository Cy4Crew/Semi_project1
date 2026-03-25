# Darkweb Monitor (Operational Guide - Full Structured)

A real-time monitoring system that crawls surface web and darkweb (.onion) sources, extracts indicators, stores evidence, and triggers alerts.

---

## What This Is

Crawler + extractor + matcher + alert pipeline designed for continuous darkweb monitoring and intelligence collection.

---

## Overview

Darkweb Monitor is an automated reconnaissance system built for persistent monitoring of both surface web and darkweb environments.

It performs scheduled crawling of target sources, extracts structured indicators (emails, domains, IPs, etc.), matches them against defined watchlists, and triggers alerts when relevant findings are detected.

The system maintains a full historical record using PostgreSQL and supports Tor routing for accessing hidden services.

---

## Key Features

- Surface web + `.onion` crawling via Tor
- Async multi-worker architecture
- Depth-based recursive crawling
- Indicator extraction (email, domain, IP, crypto)
- Watchlist matching (regex / exact)
- Evidence storage (HTML, text, screenshot)
- Alert deduplication with cooldown
- Discord / Telegram integration
- REST API support

---

## Quick Start

1. Run PostgreSQL  
2. Configure `.env`  
3. Initialize DB  
```bash
python -m app.init_db
```
4. Add targets (`targets.json`)  
5. Run  
```bash
python run.py
```

---

## Data Flow (Critical)

1. Load targets
2. Scheduler queues tasks
3. Fetch page (HTTP / Tor)
4. Save raw HTML + text + screenshot
5. Extract indicators
6. Normalize values
7. Match against watchlist
8. Store findings
9. Deduplicate
10. Trigger alert

Relation:
targets → pages → findings → alerts

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

---

## Component Details

### crawler

- scheduler → controls enqueue timing
- fetcher → HTTP / Tor requests
- extractor → regex-based data extraction
- matcher → watchlist comparison
- screenshot → Playwright rendering

### repository

- abstracts DB operations
- ensures consistency

---

## API

GET /api/targets  
POST /api/targets  
GET /api/findings  
GET /api/alerts  

Example:
```json
[
  {"type": "email", "normalized": "admin@example.com"}
]
```

---

## Database Structure

targets → pages → findings → alerts

---

## DB Schema (Full)

```sql
CREATE TABLE targets (
    id SERIAL PRIMARY KEY,
    name TEXT,
    seed_url TEXT UNIQUE,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    last_queued_at TIMESTAMP,
    last_crawled_at TIMESTAMP
);

CREATE TABLE pages (
    id SERIAL PRIMARY KEY,
    target_id INTEGER,
    url TEXT,
    host TEXT,
    title TEXT,
    status_code INT,
    fetched_at TIMESTAMP,
    content_hash TEXT,
    last_changed_at TIMESTAMP,
    raw_html_path TEXT,
    text_dump_path TEXT,
    screenshot_path TEXT
);

CREATE TABLE findings (
    id SERIAL PRIMARY KEY,
    page_id INTEGER,
    type TEXT,
    raw TEXT,
    normalized TEXT,
    group_key TEXT,
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP
);

CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    finding_id INTEGER,
    sent_at TIMESTAMP
);
```

---

## Findings Schema

- raw → original value  
- normalized → cleaned value  
- group_key → type + normalized  
- page_id → source page  

---

## Alert Logic

Trigger:

1. normalized matches watchlist
2. group_key not seen recently

Dedup:
group_key = type + normalized

Cooldown:
- prevents duplicate alerts
- allows re-alert after interval

---

## Alert Example

[ALERT]  
type=email  
value=test@example.com  
url=http://site.onion  

---

## Matcher Regex Rules

Email:
[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}

Domain:
([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}

IPv4:
\b(?:\d{1,3}\.){3}\d{1,3}\b

BTC:
\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b

---

## Watchlist Rules

- regex or exact match
- avoid short patterns
- prefer full tokens

---

## Extractor vs Matcher

extractor → finds all candidates  
matcher → filters relevant ones  

---

## Requirements

```bash
pip install -r requirements.txt
playwright install
```

---

## PostgreSQL

Local:
postgresql://user:password@127.0.0.1:5432/intel  

Docker:
postgresql://user:password@db:5432/intel  

---

## .env

```env
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/intel
WORKER_COUNT=4
MAX_DEPTH=1
MAX_PAGES_PER_HOST=20
ALERT_COOLDOWN_SECONDS=3600
SCREENSHOT_ENABLED=true
TOR_PROXY_URL=socks5h://127.0.0.1:9050
REVISIT_AFTER_SECONDS=300
REQUEST_TIMEOUT_SECONDS=60
```

---

## Crawling Behavior

- MAX_DEPTH controls recursion
- host limit enforced
- revisit interval controls re-fetch

Common issue:
depth=0 → filter problem

---

## Constraints

- host-based limit
- visited URL dedupe
- unchanged content skip

---

## Tor

Local:
tor  

Docker:
tor service  

---

## Logs

[PRODUCER]  
[QUEUE]  
[WORKER]  
[MATCH]  
[ALERT]  

---

## Debug Guide

- no crawl → DB
- no match → extractor
- no alert → cooldown
- depth stuck → filter

---

## Troubleshooting

- Tor fail → proxy
- Playwright fail → reinstall
- DB lock → reduce workers

---

## Operational Tips

- start small depth
- expand patterns gradually
- monitor findings

---

## Summary

System requires:

- DB
- extractor
- matcher
- alert

Any failure breaks pipeline.
