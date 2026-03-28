# README_OPERATIONS

This document explains how the system behaves internally, how to operate it safely, and how to diagnose the most common runtime failures.

It is intended to complement `README.md`, not replace it.

---

## Runtime Components

The application is composed of three main runtime pieces:

### API server
Defined through FastAPI in `app/api/main.py`.

Responsibilities:

- serves the dashboard and static UI
- exposes read and write API endpoints
- serves evidence files
- provides summary and reload functionality

### Scheduler / crawler
Implemented mainly in `app/crawler/scheduler.py`.

Responsibilities:

- picks due targets from the database
- normalizes and enqueues URLs
- limits crawl spread per host
- processes pages with asynchronous workers
- triggers extraction and matching
- saves crawl evidence and page state

### Alert worker
Implemented in `app/notifier/worker.py`.

Responsibilities:

- reads pending alerts from the database
- fetches hit details
- formats outbound messages
- sends notifications to stdout, Discord, or Telegram
- marks alerts as sent or failed

---

## Startup Flow

When the application starts through `run.py`, the sequence is:

1. logging is initialized
2. connection pool is opened
3. database schema is initialized if needed
4. targets and watchlist are loaded from seed files
5. queued target state is reset
6. selected runtime mode is started

This startup behavior is important because stale queue flags from earlier crashes would otherwise block targets from being scheduled again.

---

## Execution Modes in Practice

### `python run.py all`
Use this for normal single-process development or small deployments.  
It starts:

- FastAPI
- crawler scheduler/workers
- alert worker

### `python run.py api`
Use this when you only need UI/API inspection.

### `python run.py crawler`
Use this when you want to isolate crawling behavior and confirm whether pages, extracted items, and hits are being generated.

### `python run.py alert_worker`
Use this when hits are already being created but alerts are not being delivered.

### `python run.py init_db`
Use this after schema changes, first setup, or after a database reset.

---

## Database Schema Notes

The schema is created in `app/init_db.py`.

### `targets`
Stores configured crawl seeds.

Important fields:

- `seed_url`
- `enabled`
- `is_queued`
- `last_queued_at`
- `last_fetched_at`

### `pages`
Stores fetched page results.

Important fields:

- `url`
- `host`
- `title`
- `status_code`
- `fetched_at`
- `content_hash`
- `is_meaningful`
- `skip_reason`
- `content_changed`
- `raw_html_path`
- `text_dump_path`
- `screenshot_path`
- `error_message`

### `extracted_items`
Stores normalized extracted indicators.

Important fields:

- `type`
- `raw`
- `normalized`
- `group_key`
- `first_seen_at`

Unique constraint:

- `(page_id, type, normalized)`

### `watchlist`
Stores monitoring rules.

Important fields:

- `type`
- `value`
- `normalized`
- `label`
- `enabled`
- `is_regex`

### `watchlist_hits`
Stores match events.

Important fields:

- `extracted_item_id`
- `watchlist_id`
- `page_id`
- `matched_value`
- `fingerprint`
- `first_seen_at`
- `last_seen_at`
- `last_alerted_at`

### `alerts`
Stores delivery attempts per channel.

Important fields:

- `hit_id`
- `channel`
- `status`
- `error_message`
- `created_at`
- `sent_at`
- `alert_fingerprint`

---

## Seed Loading Behavior

The project uses two seed files:

- `targets.json`
- `watchlist.json`

They are loaded by `app/core/seed_loader.py`.

### Targets
`load_targets_file()` reads a JSON array of target objects and upserts them into the database.

### Watchlist
`load_watchlist_file()` accepts:

- a single `pattern`
- multiple `patterns`
- regex entries via `is_regex=true`

If a regex entry fails compilation, it is skipped.  
If a watchlist item is duplicated, it is ignored.

Operationally, this means a malformed `watchlist.json` may silently reduce effective coverage unless you inspect logs and counts.

---

## API Operation Notes

### Public read endpoints

These are useful for runtime validation:

- `GET /health`
- `GET /api/summary`
- `GET /api/targets`
- `GET /api/watchlist`
- `GET /api/pages/recent`
- `GET /api/extracted/recent`
- `GET /api/hits/recent`
- `GET /api/alerts/recent`

### Protected write endpoints

These require the configured API key:

- `POST /api/reload`
- `POST /api/targets`
- `DELETE /api/targets/{target_id}`
- `POST /api/watchlist`
- `DELETE /api/watchlist/{watchlist_id}`

If write operations fail unexpectedly, verify the API key check in `app/core/security.py` and the client-side request headers.

---

## Crawl Scheduler Behavior

The scheduler is the core of the monitoring loop.

### Producer loop
The producer periodically:

- clears cycle-local host counters
- clears cycle-local seen URL state
- queries due targets from the database
- normalizes their URLs
- marks them queued
- inserts them into the async queue

The interval is controlled by:

```env
POLL_INTERVAL_SECONDS
```

### Worker loop
Each worker:

1. takes one queued item
2. fetches the page
3. extracts indicators
4. saves page metadata/evidence
5. saves extracted items
6. matches extracted data to the watchlist
7. enqueues links for deeper crawling when allowed
8. updates target state

### URL filtering and priority
The scheduler defines:

- hard-block patterns
- low-priority patterns
- high-priority patterns

These are used to avoid noisy or low-value URLs such as login/register pages and to favor useful content such as thread or forum pages.

If crawling looks shallow or repetitive, inspect these filter lists first.

---

## Depth Expansion

Depth expansion is controlled primarily by:

```env
MAX_DEPTH
```

Operational effects:

- `0` or very low depth reduces exploration
- higher depth increases coverage but also queue volume and storage growth

If you only ever see seed pages and never internal links, possible causes are:

- `MAX_DEPTH` too low
- link filtering too strict
- fetched pages contain little or no valid link data
- page fetch failed before extraction/expansion

---

## Fetching Behavior

Fetching is implemented in `app/crawler/fetcher.py`.

Operational considerations:

- normal web pages may be fetched directly
- `.onion` pages require Tor routing
- when `TOR_FOR_ALL_REQUESTS=true`, all traffic is routed through Tor
- Tor routing is slower and can introduce timeouts or transient failures
- request timeout is controlled by `REQUEST_TIMEOUT_SECONDS`

Typical failure modes:

- bad Tor proxy host/port
- onion service unreachable
- remote site blocking or timing out
- malformed URLs in target seeds

---

## Extraction Behavior

Extraction happens in `app/crawler/extractor.py`.

The extractor produces structured items with fields such as:

```python
{
    "type": "...",
    "raw": "...",
    "normalized": "...",
    "group_key": "..."
}
```

The exact supported indicator set depends on extractor implementation, but operationally you should expect normalization to matter more than raw string appearance.

If visible content clearly contains a value but no hit is generated, first check whether:

- the extractor is classifying it as the expected type
- normalization changed the value unexpectedly
- the watchlist entry is using the wrong type

---

## Matching Behavior

Matching is handled in `app/crawler/matcher.py`.

The matcher compares extracted normalized values to watchlist rules and, when applicable, creates:

- `watchlist_hits`
- `alerts`

Typical causes of missing hits:

- type mismatch
  - for example, a domain placed in an email watchlist rule
- normalization mismatch
- regex too strict
- watchlist entry disabled
- extracted item never saved due to upstream failure

Typical causes of repeated noisy hits:

- regex too broad
- watchlist built from generic tokens
- target pages contain common high-frequency values

---

## Alert Worker Behavior

The alert worker polls pending alerts in small batches.

For each alert it:

1. loads hit detail from the database
2. builds a formatted message
3. sends to the requested channel
4. updates status to sent or failed

### Supported channels

- `stdout`
- `discord`
- `telegram`

### Alert content usually includes

- watchlist type
- watchlist value
- matched value
- source URL
- page title, if present
- watchlist label, if present
- screenshot path, if present

### Cooldown

Cooldown logic is driven by:

```env
ALERT_COOLDOWN_SECONDS
```

This prevents the same hit from triggering repeated alerts too frequently.

If hits exist but alerts are missing, verify whether the system suppressed new alert creation due to cooldown.

---

## Screenshot Operation

Screenshots are handled by `app/crawler/screenshot.py`.

Requirements:

- `SCREENSHOT_ENABLED=true`
- Playwright installed
- browser launch available in the environment

Output directory:

```text
evidence/screenshots/
```

Operational caveats:

- screenshots can fail on slow pages or protected pages
- Tor + Playwright will be slower than direct browsing
- screenshot failure should not be treated as proof that the crawl failed completely

The API also contains compatibility routes for screenshot paths that may already be stored in older formats.

---

## Evidence and Persistence

The project persists crawl evidence into:

```text
evidence/
├── html/
├── text/
└── screenshots/
```

What to preserve in real deployments:

- PostgreSQL volume
- `evidence/` directory
- `targets.json`
- `watchlist.json`
- `.env`

In Docker, evidence is already mounted to the host.  
If you remove the host directory or containers without understanding volume behavior, you may lose investigation artifacts.

---

## UI Operation Notes

The UI is static HTML/JS served under `/ui`.

Operationally, this means:

- UI rendering depends on the API endpoints being healthy
- frontend issues can look like crawl failures even when the backend is fine
- when debugging, always verify the API directly before assuming the crawler is broken

Suggested order:

1. `GET /health`
2. `GET /api/summary`
3. `GET /api/pages/recent`
4. `GET /api/extracted/recent`
5. `GET /api/hits/recent`
6. then inspect UI pages

---

## Recommended Debugging Order

When the system appears broken, debug in this order.

### Case 1: nothing is happening
Check:

1. is PostgreSQL reachable?
2. did `init_db` run?
3. do targets exist in `/api/targets`?
4. does `/api/summary` show `targets > 0`?
5. is the crawler mode actually running?

### Case 2: targets exist but pages stay at zero
Check:

1. queue reset behavior at startup
2. `get_due_targets()` logic
3. Tor connectivity
4. request timeout
5. malformed seed URLs

### Case 3: pages increase but extracted stays zero
Check:

1. fetched content actually contains parseable text
2. extractor patterns
3. HTML/text storage
4. whether pages are mostly login/search/navigation pages

### Case 4: extracted increases but hits stay zero
Check:

1. watchlist types
2. regex validity
3. normalization differences
4. watchlist contents actually loaded into DB

### Case 5: hits exist but alerts stay zero
Check:

1. pending alert records created?
2. cooldown window active?
3. webhook/token configured?
4. alert worker running?

### Case 6: screenshots missing
Check:

1. Playwright installed
2. browser startup permissions
3. timeout too low
4. screenshot setting disabled

---

## Useful Validation Calls

### Health
```bash
curl http://localhost:8000/health
```

### Summary
```bash
curl http://localhost:8000/api/summary
```

### Recent pages
```bash
curl http://localhost:8000/api/pages/recent
```

### Recent extracted items
```bash
curl http://localhost:8000/api/extracted/recent
```

### Recent hits
```bash
curl "http://localhost:8000/api/hits/recent?limit=20&offset=0"
```

### Recent alerts
```bash
curl "http://localhost:8000/api/alerts/recent?limit=20&offset=0"
```

---

## Operational Best Practices

- Keep `targets.json` focused and clean
- Do not start with a very high `MAX_DEPTH`
- Validate regex watchlist entries before bulk loading
- Persist `evidence/` and database volumes
- Use API responses to separate UI issues from backend issues
- Tune `WORKER_COUNT` conservatively first
- Increase timeouts for Tor-heavy targets rather than assuming crawl logic is broken
- Review alert cooldown before concluding that notifications failed
- Treat screenshots as supporting evidence, not the only proof of successful crawling

---

## Common Misread Situations

### `targets > 0`, `pages = 0`
Usually means scheduling/fetching is failing, not that seed loading failed.

### `pages > 0`, `hits = 0`
Usually means extraction or watchlist mismatch, not necessarily a crawler failure.

### alerts visible in DB but not received externally
Usually means delivery configuration failure or channel-specific error.

### UI looks empty
Could be frontend rendering only. Confirm API JSON first.

---

## Maintenance Notes

After major code changes, especially around schema or repository behavior:

1. re-run `python run.py init_db`
2. confirm table/index creation
3. verify seed reload
4. restart crawler and alert worker
5. validate summary counts through the API

When changing seed files during runtime, use:

```text
POST /api/reload
```

with the proper API key, instead of assuming the running process will automatically re-read the files.

---

## Final Check Before Deployment

Minimum checklist:

- `.env` reviewed
- PostgreSQL persistent storage configured
- Tor reachable
- Playwright available when screenshots are needed
- targets loaded
- watchlist loaded
- `/health` works
- `/api/summary` reflects activity
- recent pages increase during runtime
- alert channel tested with a known hit

If those conditions are satisfied, the system is operational.
