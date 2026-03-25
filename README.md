# Darkweb Monitor

A real-time monitoring system that crawls surface web and darkweb (.onion) sources, extracts indicators, and triggers alerts.

---

## Overview

Darkweb Monitor continuously scans target sites, extracts indicators (email, domain, IP, etc.), matches them against a watchlist, and sends alerts when matches occur.

---

## Quick Start (Local)

```bash
pip install -r requirements.txt
playwright install
python -m app.init_db
python run.py
```

---

## Quick Start (Docker)

```bash
docker-compose up --build
```

---

## Project Structure

```plaintext
app/
├── crawler/
├── repository/
└── init_db.py

run.py
targets.json
watchlist.json
.env
```

---

## Core Flow

targets → crawl → extract → match → save → alert

---

## Environment Notes

### Local
```env
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/intel
TOR_PROXY_URL=socks5h://127.0.0.1:9050
```

### Docker
```env
DATABASE_URL=postgresql://user:password@db:5432/intel
TOR_PROXY_URL=socks5h://tor:9050
```

---

## Features

- Supports Tor (.onion)
- PostgreSQL storage
- Alerting via Discord / Telegram

---

## Verify It Works

```text
[PRODUCER] due_targets=...
[WORKER] picked depth=0 ...
[MATCH] ...
[ALERT] sent
```

If you see MATCH and ALERT logs, the system is working correctly.

---

## Common Issues

```text
no crawl  → check DB / targets
no match  → check watchlist / extractor
no alert  → check webhook / cooldown
```

---

## Watchlist Note

```text
pattern too broad → false positives 발생
```

---

## More Details

See `README_OPERATIONS_FULL.md` for full documentation.
