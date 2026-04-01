# Darkweb Monitoring & Intelligence Platform

## Summary
An integrated cyber threat intelligence platform that combines:
- darkweb / surface web crawling
- indicator extraction and watchlist matching
- Telegram intelligence collection
- cryptocurrency wallet tracing and graph visualization

Built with FastAPI, PostgreSQL, Docker, and Tor.

---

## Key Features
- `.onion` and surface web crawling
- IoC extraction: email, domain, IP, Telegram, BTC, hash, API-key-like strings
- watchlist matching and alert generation
- evidence storage: HTML, text, screenshots
- Telegram intelligence collection
- wallet tracing and graph-based analysis
- dashboard and investigation UI

---

## Architecture

targets → crawl → extract → match → store → alert → UI

Telegram links → Telegram collector → wallet discovery → graph analysis

---

## Quick Start

### Docker
```bash
docker compose up --build
```

### Local
```bash
pip install -r requirements.txt
playwright install
python run.py init_db
python run.py all
```

---

## Configuration

Use `.env.example` as the base configuration.

```env
DATABASE_URL=postgresql://user:password@db:5432/intel
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TOR_ENABLED=true
```

---

## Repository Layout

```text
app/
  api/        # FastAPI routes and UI serving
  crawler/    # scheduler, fetcher, extractor, matcher
  notifier/   # Discord / Telegram alert workers
  telegram/   # Telegram intelligence collection
analyzer/     # wallet tracing and graph APIs
ui/           # frontend pages
```

---

## Main Endpoints
- `/health`
- `/api/summary`
- `/api/targets`
- `/api/watchlist`
- `/api/hits`
- `/api/pages`
- `/api/alerts`
- `/api/graph/*`

---

## Purpose
Designed to simulate a real cyber threat intelligence workflow by connecting crawling, intelligence extraction, messaging-platform enrichment, and wallet tracing in one pipeline.

---

## Role
- backend architecture and data flow design
- crawling and matching engine implementation
- alert pipeline integration
- intelligence visualization support

---

## Documentation
Detailed runtime behavior, operations, and troubleshooting are documented in [README_OPERATIONS.md](README_OPERATIONS.md).
