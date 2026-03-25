# Darkweb Monitor

A real-time monitoring system that crawls surface web and darkweb (.onion) sources, extracts indicators, and triggers alerts.

---

## Overview

Darkweb Monitor continuously scans target sites, extracts indicators (email, domain, IP, etc.), matches them against a watchlist, and sends alerts when matches occur.

---

## Quick Start

```bash
pip install -r requirements.txt
playwright install
python -m app.init_db
python run.py
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

## Notes

- Supports Tor (.onion)
- Uses PostgreSQL
- Alerts via Discord / Telegram

---

## More Details

See `README_OPERATIONS.md` for full documentation.
