# Darkweb Monitor

A real-time monitoring system that crawls web/darkweb sources, extracts sensitive indicators, and triggers alerts.

Supports:
- Surface web + `.onion` (Tor)
- Pattern-based detection (email, domain, IP, etc.)
- Real-time alerting (Discord / Telegram)
- Screenshot evidence capture

---

## Features

- Multi-worker async crawler
- Depth-based link expansion
- Pattern extraction & normalization
- Alert deduplication (cooldown-based)
- Screenshot capture (Playwright)
- Tor support for `.onion` domains

---

## Project Structure

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
 ├── init_db.py
run.py
targets.json
watchlist.json
.env
requirements.txt

---

## Quick Start (Local)

### 1. Install dependencies

pip install -r requirements.txt
playwright install

---

### 2. Run PostgreSQL

Make sure PostgreSQL is running locally.

Example:

postgresql://user:password@127.0.0.1:5432/intel

---

### 3. Configure `.env`

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

---

### 4. Initialize database

python -m app.init_db

---

### 5. Run

python run.py

---

## Docker (Optional)

If using Docker, `DATABASE_URL` must use service name:

postgresql://user:password@db:5432/intel

---

## Tor (.onion support)

### Option 1 (Local Tor)

tor

TOR_PROXY_URL=socks5h://127.0.0.1:9050

### Option 2 (Docker Tor)

TOR_PROXY_URL=socks5h://tor:9050

---

## Data Flow

1. Load targets from `targets.json`
2. Scheduler enqueues URLs
3. Fetch page (HTTP / Tor)
4. Extract content
5. Match against `watchlist.json`
6. Save findings
7. Trigger alert (if matched)

---

## targets.json

Example:

[
  {
    "label": "forum",
    "url": "https://example.com"
  }
]

---

## watchlist.json

Example:

[
  { "type": "email", "pattern": "test@example.com", "label": "test" },
  { "type": "domain", "pattern": "mail.ru", "label": "test" },
  { "type": "phone", "pattern": "01012345678", "label": "test" }
]

---

## Alerts

Alerts trigger when:
- Extracted value matches watchlist pattern
- Not duplicated within cooldown period

Supported:
- Discord Webhook
- Telegram Bot

---

## Screenshot

If enabled:

SCREENSHOT_ENABLED=true

Each matched page is saved as an image using Playwright.

---

## Troubleshooting

### No crawling happens

- Check DB connection
- Check `targets` table is populated

### No alerts

- Ensure `watchlist.json` has valid patterns
- Check cooldown settings
- Verify webhook/token

### `.onion` not working

- Ensure Tor is running
- Check proxy URL

### Playwright errors

playwright install

---

## Notes

- Depth too low → no expansion
- Strict patterns → no matches
- High cooldown → fewer alerts

---

## Recommended

- Use Docker for stability
- Start with small `MAX_DEPTH`
- Gradually expand watchlist patterns
