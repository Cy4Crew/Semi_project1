# Darkweb Monitor (Operations Guide)

This document provides full operational, architectural, and debugging guidance for **Darkweb Monitor**.  
It is intended for actual deployment, maintenance, troubleshooting, and long-term operation.

This is **not** a short introduction.  
It explains how the crawler works, how data flows through the system, how alerts are deduplicated, how Docker and local environments differ, and where to look when the system appears to stop working.

---

## 1. Purpose

Darkweb Monitor is a monitoring pipeline for continuously crawling target sources on both the surface web and the darkweb, extracting indicators from collected content, storing evidence, and generating alerts when extracted data matches a configured watchlist.

The system is designed around the following operational pipeline:

```plaintext
targets → scheduler → fetch → evidence save → extract → normalize → match → findings save → dedupe → alert
```

The practical goal is not just "crawl pages," but to maintain a repeatable monitoring process that can answer these questions reliably:

- What targets are currently being monitored?
- What pages were fetched?
- What changed since the last crawl?
- What indicators were extracted?
- Which extracted values matched the watchlist?
- Which alerts were sent, and why?
- Why did a target stop producing alerts?

---

## 2. Operational Scope

The system supports:

- Surface web crawling over HTTP / HTTPS
- Darkweb `.onion` crawling over Tor
- Recursive crawling with configurable depth
- Host-level crawl limiting
- Change detection through content hashing
- Evidence preservation through HTML, text dumps, and screenshots
- Extraction of structured indicators
- Watchlist-based matching
- Cooldown-based alert deduplication
- Discord / Telegram notification delivery
- API-based visibility into targets, findings, and alerts

This document covers both:

- **Local execution**
- **Docker-based execution**

---

## 3. High-Level Architecture

The system can be understood as five major layers:

### 3.1 Target Management Layer
Responsible for deciding **what to crawl**.

This includes:
- seed URLs
- target enable/disable state
- revisit timing
- queue eligibility

Primary data source:
- `targets` table
- `targets.json` during initialization or seeding

---

### 3.2 Acquisition Layer
Responsible for **retrieving content**.

This includes:
- HTTP requests
- Tor proxy routing
- timeout handling
- page fetch success / failure tracking
- screenshot capture
- raw HTML and text dump storage

Primary code:
- `app/crawler/fetcher.py`
- `app/crawler/screenshot.py`

---

### 3.3 Analysis Layer
Responsible for **turning raw content into structured data**.

This includes:
- regex extraction
- text normalization
- watchlist comparison
- group key generation

Primary code:
- `app/crawler/extractor.py`
- `app/crawler/matcher.py`

---

### 3.4 Persistence Layer
Responsible for **saving crawl results and alert history**.

This includes:
- target status updates
- page records
- finding records
- alert records
- deduplication support through `group_key`

Primary code:
- `app/repository/`

---

### 3.5 Notification Layer
Responsible for **sending alerts outward**.

This includes:
- Discord webhook delivery
- Telegram bot delivery
- cooldown-aware duplicate suppression
- alert send history

---

## 4. End-to-End Data Flow

Below is the actual operational flow from the moment a target becomes eligible.

### Step 1. Target becomes due
A target becomes eligible when:
- it is enabled
- it has not been queued recently
- revisit timing allows new processing

The scheduler queries the database for due targets.

### Step 2. Scheduler enqueues crawl work
The scheduler pushes the seed URL into the internal queue with:
- `target_id`
- `depth=0`
- normalized root URL

### Step 3. Worker picks a queued item
A worker consumes the queue item and begins processing:
- fetch page
- classify result
- save evidence
- extract indicators
- match indicators
- enqueue discovered links if depth allows

### Step 4. Fetch page
The fetcher decides:
- direct HTTP request or Tor-routed request
- timeout behavior
- request headers / user agent
- whether the response is useful enough for parsing

### Step 5. Save evidence
If content is retrieved, the system may store:
- raw HTML
- normalized text dump
- screenshot image

These artifacts support later verification and incident review.

### Step 6. Detect content changes
A `content_hash` is computed and compared with previous state.

If unchanged:
- the system may reduce downstream work
- extraction / alerting may be skipped depending on implementation

If changed:
- extraction proceeds fully
- `last_changed_at` may be updated

### Step 7. Extract indicators
The extractor scans page text and identifies indicator candidates.

Typical extracted types:
- email
- domain
- phone
- username
- ipv4
- btc address

These extracted values are still just candidates.

### Step 8. Normalize indicators
Before matching, raw values are normalized.

Examples:
- remove surrounding punctuation
- lowercase domains / emails
- unify phone representation
- trim formatting noise

This matters because alert deduplication relies on normalized identity.

### Step 9. Match against watchlist
The matcher compares normalized values to watchlist rules.

Matching modes can include:
- exact string comparison
- regex comparison

Only matched values become findings.

### Step 10. Save findings
A finding record is inserted or updated using:
- type
- raw
- normalized
- group_key
- page_id
- timestamps

### Step 11. Apply deduplication and cooldown
The system checks whether this matched value already triggered recently.

If the cooldown has not expired:
- alert is suppressed

If the cooldown has expired or no prior alert exists:
- alert is sent

### Step 12. Send alert
Notification channels are triggered:
- Discord
- Telegram

An alert record is then stored.

### Step 13. Expand crawl depth
If depth constraints allow and extracted links are eligible:
- linked URLs are enqueued with `depth + 1`

This continues until:
- `MAX_DEPTH` reached
- host limit reached
- queue exhausted
- link filters stop expansion

---

## 5. Project Structure

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

## 6. Detailed Component Responsibilities

### 6.1 `app/api/`
This layer exposes the system state externally.

Typical responsibilities:
- target listing
- target creation
- findings lookup
- alert history inspection

This is not the crawler engine itself.  
It is the visibility and control interface.

---

### 6.2 `app/core/`
Shared foundational logic.

Typical responsibilities:
- reading `.env`
- database connection / pool setup
- common helpers
- configuration objects
- logger setup

If configuration values are wrong, many later symptoms appear here first.

---

### 6.3 `app/crawler/scheduler.py`
This is the crawl orchestrator.

Typical responsibilities:
- query due targets
- enqueue root URLs
- manage worker loops
- enforce revisit timing
- track queue state
- coordinate target completion state

This is usually the first place to inspect if:
- nothing starts
- the queue remains empty
- only `depth=0` runs forever

---

### 6.4 `app/crawler/fetcher.py`
This is the network acquisition layer.

Typical responsibilities:
- make HTTP requests
- detect `.onion`
- apply Tor proxy where needed
- enforce timeout
- return status code, content, and metadata

This is usually the first place to inspect if:
- many requests fail
- `.onion` sites never load
- 403 / timeout patterns dominate

---

### 6.5 `app/crawler/extractor.py`
This module finds raw indicators from content.

It should not decide "priority."  
It should decide only: **what structured data appears to exist in the page text**.

Examples:
- find email-shaped strings
- find ipv4-shaped strings
- find possible domains
- find candidate usernames

---

### 6.6 `app/crawler/matcher.py`
This module determines whether extracted values are important.

It should:
- normalize values
- compare against watchlist rules
- produce match events
- build `group_key`

This is where business meaning begins.

---

### 6.7 `app/crawler/screenshot.py`
Responsible for visual evidence capture.

Typical responsibilities:
- launch Playwright browser
- load page
- save screenshot
- handle timeout / render failure

Screenshots are especially useful when:
- page content changes frequently
- HTML evidence is hard to interpret
- visual leak proof is required for reporting

---

### 6.8 `app/repository/`
Database access layer.

Typical responsibilities:
- save page rows
- save findings
- save alerts
- update target state
- retrieve due targets
- manage dedupe lookups

Operationally, this layer matters because inconsistent transaction handling here can make the whole system appear unstable.

---

### 6.9 `app/init_db.py`
Creates schema and indexes.

This must be run before first execution unless the database is already initialized.

If schema and code diverge, symptoms include:
- missing column errors
- failed inserts
- queue processing with no saved state

---

### 6.10 `run.py`
Entrypoint.

Typical responsibilities:
- load configuration
- initialize dependencies
- start crawler
- optionally start API

---

### 6.11 `targets.json`
Seed input for monitored targets.

Typical fields depend on implementation, but commonly include:
- name / label
- seed URL
- enabled state

---

### 6.12 `watchlist.json`
Defines what matters.

Typical entries include:
- `type`
- `pattern`
- `label`

This is where matching sensitivity is controlled.

---

## 7. API Reference

The exact routes depend on implementation, but the operational expectation is as follows.

### `GET /api/targets`
Returns monitored targets and basic crawl state.

Typical use:
- verify target registration
- inspect enabled / disabled state
- confirm seed URLs exist

Example response:
```json
[
  {
    "id": 1,
    "name": "Example Forum",
    "seed_url": "https://example.com",
    "enabled": true
  }
]
```

---

### `POST /api/targets`
Adds a new target.

Typical request:
```json
{
  "name": "Hidden Forum",
  "seed_url": "http://examplehidden.onion",
  "enabled": true
}
```

Expected operational result:
- target inserted
- scheduler eventually picks it up
- crawl begins on next due cycle

---

### `GET /api/findings`
Returns matched findings.

Typical use:
- verify extraction and matching are working
- inspect normalized values
- audit source pages

Example response:
```json
[
  {
    "id": 501,
    "type": "email",
    "raw": "Admin@Example.com",
    "normalized": "admin@example.com",
    "group_key": "email:admin@example.com"
  }
]
```

---

### `GET /api/alerts`
Returns sent alerts.

Typical use:
- confirm notification pipeline worked
- check send history
- debug cooldown behavior

Example response:
```json
[
  {
    "id": 200,
    "finding_id": 501,
    "channel": "discord",
    "sent_at": "2026-03-25T13:20:00Z"
  }
]
```

---

## 8. Database Model

Core relation flow:

```plaintext
targets → pages → findings → alerts
```

### 8.1 `targets`
Stores the root entities the system monitors.

Purpose:
- define seed URLs
- store scheduling state
- track enablement

### 8.2 `pages`
Stores fetched page-level evidence and metadata.

Purpose:
- preserve fetch history
- track content change
- store artifact paths

### 8.3 `findings`
Stores actual matched results.

Purpose:
- represent extracted values that matter
- provide dedupe identity
- connect matched data to source pages

### 8.4 `alerts`
Stores notification send history.

Purpose:
- support cooldown logic
- audit outbound notifications
- debug delivery failures

---

## 9. Full Database Schema (Recommended SQL)

```sql
CREATE TABLE IF NOT EXISTS targets (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    seed_url TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_queued_at TIMESTAMPTZ,
    last_crawled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS pages (
    id BIGSERIAL PRIMARY KEY,
    target_id BIGINT REFERENCES targets(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    host TEXT,
    title TEXT,
    status_code INTEGER,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash TEXT,
    last_changed_at TIMESTAMPTZ,
    is_meaningful BOOLEAN NOT NULL DEFAULT FALSE,
    skip_reason TEXT,
    content_changed BOOLEAN NOT NULL DEFAULT TRUE,
    raw_html_path TEXT,
    text_dump_path TEXT,
    screenshot_path TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id BIGSERIAL PRIMARY KEY,
    page_id BIGINT REFERENCES pages(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    raw TEXT NOT NULL,
    normalized TEXT NOT NULL,
    group_key TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    finding_id BIGINT REFERENCES findings(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_targets_enabled ON targets(enabled);
CREATE INDEX IF NOT EXISTS idx_targets_last_queued_at ON targets(last_queued_at);
CREATE INDEX IF NOT EXISTS idx_pages_target_id ON pages(target_id);
CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url);
CREATE INDEX IF NOT EXISTS idx_pages_host ON pages(host);
CREATE INDEX IF NOT EXISTS idx_findings_page_id ON findings(page_id);
CREATE INDEX IF NOT EXISTS idx_findings_group_key ON findings(group_key);
CREATE INDEX IF NOT EXISTS idx_findings_last_seen_at ON findings(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_alerts_finding_id ON alerts(finding_id);
CREATE INDEX IF NOT EXISTS idx_alerts_sent_at ON alerts(sent_at);
```

---

## 10. Findings Schema

Each finding should preserve both the original extracted value and the normalized identity used for matching and dedupe.

### `type`
Classification of the value.

Examples:
- `email`
- `domain`
- `phone`
- `username`
- `ipv4`
- `btc`

### `raw`
The exact extracted string as found in content.

Example:
```plaintext
Admin@Example.com
```

### `normalized`
The canonical comparison form.

Example:
```plaintext
admin@example.com
```

### `group_key`
Deduplication identity.

Recommended rule:
```plaintext
group_key = type + ":" + normalized
```

This is better than plain concatenation because it prevents ambiguous collisions.

### `page_id`
Foreign key to the page where the finding was observed.

This allows:
- traceability
- evidence lookup
- source verification

---

## 11. Alert Logic

Alerting must be deterministic.  
The system should not "randomly" send or suppress alerts.

### 11.1 Trigger conditions
An alert should only be eligible when:
1. the extractor produced a candidate
2. the matcher confirmed a watchlist hit
3. the finding was saved or updated successfully
4. cooldown rules allow notification

### 11.2 Deduplication rule
Recommended dedupe identity:

```plaintext
group_key = type + ":" + normalized
```

This means:
- same normalized value of same type → same logical finding
- same value seen again on a different page does not necessarily create a new alert immediately

### 11.3 Cooldown behavior
`ALERT_COOLDOWN_SECONDS` controls how often the same logical finding can notify again.

If the last sent alert for a `group_key` is too recent:
- new alert is suppressed

If the cooldown has expired:
- re-alert is allowed

### 11.4 Why cooldown exists
Without cooldown:
- one repeated value across many pages produces alert floods
- operations team loses signal quality
- real incidents become harder to see

### 11.5 Recommended operational interpretation
- Use shorter cooldown for high-priority fast-moving leaks
- Use longer cooldown for noisy indicators

---

## 12. Alert Example

Example logical alert payload:

```plaintext
[ALERT]
type=email
raw=Admin@Example.com
normalized=admin@example.com
group_key=email:admin@example.com
label=high_priority_target
target=Hidden Forum
url=http://examplehidden.onion/thread/42
channel=discord
```

---

## 13. Watchlist Rules

The watchlist controls what extracted values matter.

Typical record shape:

```json
[
  { "type": "email", "pattern": "test@example.com", "label": "priority" },
  { "type": "domain", "pattern": "mail.ru", "label": "priority" }
]
```

### 13.1 Exact matching
Use exact matching when:
- the value is stable
- you care about a specific identifier
- false positives must be low

Good for:
- exact email
- exact domain
- exact username

### 13.2 Regex matching
Use regex when:
- values vary by pattern
- you need family-level detection
- format matters more than one exact string

Good for:
- internal naming conventions
- account formats
- organization-specific identifier styles

### 13.3 Common watchlist mistakes
- pattern too short
- domain fragment instead of full domain
- broad username regex
- regex without boundaries
- mixing normalization assumptions incorrectly

---

## 14. Matcher Regex Rules

Below are example extraction/matching patterns.  
They are not universally perfect; they are operational starting points.

### 14.1 Email
```regex
[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}
```

Caveat:
- may catch malformed content fragments
- may require additional normalization if punctuation trails the email

### 14.2 Domain
```regex
\b([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}\b
```

Caveat:
- can catch irrelevant public domains
- should usually be matched against normalized lowercase

### 14.3 Phone (KR-style example)
```regex
01[0-9]-?[0-9]{3,4}-?[0-9]{4}
```

Caveat:
- formatting varies
- normalization should remove hyphens before dedupe

### 14.4 IPv4
```regex
\b(?:\d{1,3}\.){3}\d{1,3}\b
```

Caveat:
- regex alone does not ensure octets are valid 0–255
- version-like strings can sometimes be false positives

### 14.5 Username (conservative example)
```regex
\b[a-zA-Z0-9_]{4,32}\b
```

Caveat:
- this is noisy by nature
- should usually be context-aware or watchlist-limited

### 14.6 BTC address
```regex
\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b
```

Caveat:
- does not cover every cryptocurrency format
- should be labeled specifically to avoid confusion with other wallet types

---

## 15. Extractor vs Matcher

These roles must stay separate.

### Extractor
Purpose:
- find all candidate structured values in content

It should answer:
- "What values appear here?"

It should **not** answer:
- "Do we care about this value?"

### Matcher
Purpose:
- evaluate extracted values against watchlist rules

It should answer:
- "Does this extracted value matter operationally?"

It should also:
- normalize values
- build group keys
- decide match labels

If extractor and matcher responsibilities blur together, debugging becomes much harder.

---

## 16. Requirements

### Minimum practical runtime requirements
- Python 3.10+
- PostgreSQL
- Playwright
- Tor (required for `.onion`)
- valid writable storage for evidence paths

---

## 17. Installation

### Local installation
```bash
pip install -r requirements.txt
playwright install
python -m app.init_db
python run.py
```

### Docker installation
Assuming a Compose-based setup:

```bash
docker-compose up --build
```

If the application image does not initialize DB automatically, run init manually inside the container or an init service.

---

## 18. PostgreSQL Configuration

### Local example
```env
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/intel
```

### Docker example
Use the service name instead of localhost:

```env
DATABASE_URL=postgresql://user:password@db:5432/intel
```

Operational note:
- `127.0.0.1` inside a container is the container itself, not the host database
- therefore Docker deployments should use service names

---

## 19. Environment Configuration (`.env`)

Full operational example:

```env
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
TOR_SOCKS_HOST=127.0.0.1
TOR_SOCKS_PORT=9050
TOR_PROXY_URL=socks5h://127.0.0.1:9050

REQUEST_TIMEOUT_SECONDS=60
REVISIT_AFTER_SECONDS=300
```

### Docker variant
Typical differences:

```env
DATABASE_URL=postgresql://user:password@db:5432/intel
TOR_SOCKS_HOST=tor
TOR_PROXY_URL=socks5h://tor:9050
```

---

## 20. Local vs Docker Execution

### 20.1 Local
Use this when:
- developing
- debugging quickly
- testing extractor or matcher changes

Typical stack:
- app on host
- PostgreSQL on host
- optional Tor on host

Local key settings:
```env
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/intel
TOR_PROXY_URL=socks5h://127.0.0.1:9050
```

### 20.2 Docker
Use this when:
- you want environment consistency
- you want cleaner deployment
- multiple services should be isolated

Typical services:
- `app`
- `db`
- optional `tor`

Docker key settings:
```env
DATABASE_URL=postgresql://user:password@db:5432/intel
TOR_PROXY_URL=socks5h://tor:9050
```

### 20.3 Example Docker Compose skeleton
```yaml
version: "3.9"

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: intel
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"

  tor:
    image: dperson/torproxy
    ports:
      - "9050:9050"

  app:
    build: .
    depends_on:
      - db
      - tor
    environment:
      DATABASE_URL: postgresql://user:password@db:5432/intel
      TOR_PROXY_URL: socks5h://tor:9050
    ports:
      - "8000:8000"
```

---

## 21. Tor (.onion) Operation

### Local Tor
Run Tor locally and ensure SOCKS port is reachable.

Typical config:
```bash
tor
```

Typical env:
```env
TOR_PROXY_URL=socks5h://127.0.0.1:9050
```

### Docker Tor
If Tor is containerized:
```env
TOR_PROXY_URL=socks5h://tor:9050
```

### Operational checks
If `.onion` pages never load:
- verify Tor service is up
- verify proxy URL is correct
- confirm fetcher actually routes `.onion` traffic through the proxy
- confirm DNS is not leaking via incorrect proxy scheme

Prefer `socks5h://` so hostname resolution happens through the proxy.

---

## 22. Crawling Behavior

### 22.1 `MAX_DEPTH`
Controls recursive expansion depth.

Interpretation:
- `0` → only seed URL
- `1` → seed URL + links found on seed
- `2` → seed + child links + grandchildren

### 22.2 `MAX_PAGES_PER_HOST`
Protects the crawler from exploding on a single domain.

This helps prevent:
- infinite calendar traps
- massive forum traversals
- accidental overconsumption

### 22.3 `REVISIT_AFTER_SECONDS`
Controls when a target becomes eligible again.

Short values:
- more frequent monitoring
- more DB and network load

Long values:
- less load
- slower rediscovery

### 22.4 Depth not increasing
If depth remains stuck at `0`, common causes are:
- link extraction failure
- links filtered too aggressively
- `MAX_DEPTH` too low
- only off-host links discovered
- queue insertion blocked by dedupe rules

### 22.5 Changed-content behavior
If `content_hash` does not change:
- extraction may be skipped
- alerts may not recur
- system may appear "quiet" even though crawling continues

That is often correct behavior, not failure.

---

## 23. Crawling Constraints

Typical operational constraints include:

- already visited URLs may be skipped
- host-level limits may block expansion
- revisit timing may suppress frequent requeue
- unchanged pages may reduce downstream work
- filtered link patterns may prevent deeper traversal

This means "few alerts" does not automatically mean "the crawler is broken."

---

## 24. Logs (Expected Normal Operation)

Example operational log sequence:

```plaintext
[PRODUCER] due_targets=10
[QUEUE] target_id=1 depth=0 url=http://examplehidden.onion
[WORKER 0] picked depth=0 target_id=1 url=http://examplehidden.onion
[FETCH] status=200 url=http://examplehidden.onion
[EXTRACT] candidates=14
[MATCH] type=email normalized=admin@example.com
[ALERT] sent channel=discord group_key=email:admin@example.com
```

### Interpreting missing stages
- No `QUEUE` → scheduler issue
- No `FETCH` → worker or network issue
- No `EXTRACT` → content parsing issue
- No `MATCH` → watchlist or extraction mismatch
- No `ALERT` → cooldown or delivery issue

---

## 25. Debug Guide

### 25.1 Nothing crawls
Check:
- DB connection
- `targets` table populated
- targets enabled
- scheduler loop active
- revisit timing not suppressing all targets

### 25.2 Pages fetch but no findings
Check:
- extractor patterns
- text dump generation
- content encoding issues
- whether pages are mostly empty / blocked / JS-only

### 25.3 Findings exist but no alerts
Check:
- cooldown still active
- alert channels configured
- send failure in logs
- dedupe logic too aggressive

### 25.4 Depth stays at 0
Check:
- extracted links exist
- links normalize correctly
- host filter not blocking everything
- depth condition written correctly

### 25.5 Alerts feel inconsistent
Check:
- normalization consistency
- group key generation
- same value represented in multiple raw forms
- alert send history

---

## 26. Troubleshooting

### Tor connection fails
Possible causes:
- Tor not running
- wrong proxy host
- wrong port
- `.onion` traffic not routed through proxy
- using `socks5://` instead of `socks5h://` where hostname resolution matters

### Playwright screenshot fails
Possible causes:
- browser binaries not installed
- timeout too low
- page blocks headless browser
- missing OS dependencies in container

Typical fix:
```bash
playwright install
```

### Database writes fail
Possible causes:
- schema mismatch
- missing columns
- invalid transaction handling
- connection pool exhaustion

### App runs but appears idle
Possible causes:
- all targets within revisit window
- unchanged content
- overly strict watchlist
- cooldown suppressing alerts
- no new matched findings

### Many repeated logs but no output growth
Possible causes:
- content hash unchanged
- dedupe suppressing repeated findings
- queue repeatedly revisiting same low-value pages

---

## 27. Operational Recommendations

### Start conservatively
Recommended initial values:
- low `MAX_DEPTH`
- moderate `WORKER_COUNT`
- realistic cooldown
- small watchlist

### Validate each pipeline stage separately
Verify in order:
1. target insertion
2. fetch success
3. evidence save
4. extraction
5. matching
6. finding save
7. alert send

### Monitor tables directly
Useful checks:
- `targets` updates over time
- `pages` count growth
- `findings` inserts / updates
- `alerts` send history

### Keep watchlist disciplined
Too broad:
- alert noise
- operator fatigue

Too narrow:
- missed incidents

### Treat screenshots as evidence, not primary truth
Screenshots are useful, but structured fields and DB records should remain the authoritative operational source.

---

## 28. Recommended Documentation Split

For practical repository use, it is often best to keep two documents:

- `README.md` → short project intro + quick start
- `README_OPERATIONS.md` → detailed operations guide (this document)

This prevents the main README from becoming too heavy while preserving full operational detail.

---

## 29. Summary

Darkweb Monitor is not just a crawler.  
It is an operational pipeline that depends on all of the following being correct at the same time:

- target scheduling
- network fetching
- Tor routing where needed
- evidence preservation
- extraction quality
- matcher accuracy
- database consistency
- deduplication logic
- alert channel delivery

If one layer breaks, the whole pipeline appears degraded.

For that reason, the correct way to operate or debug the system is to think in stages:

```plaintext
targets → fetch → evidence → extract → match → save → dedupe → alert
```

When diagnosing problems, identify **which stage stopped producing output**.  
That is the fastest way to find the real fault.
