# Darkweb OSINT Monitoring System

## Overview

This project is a real-time threat intelligence system designed to collect, analyze, and monitor leaked data from dark web and public web sources.

It implements a full pipeline including crawling, extraction, pattern matching, storage, and evidence collection. The system is built to simulate practical security monitoring scenarios such as data leak detection and OSINT-based intelligence gathering.

---

## Key Capabilities

* **Asynchronous Web Crawling**

  * Multi-worker queue-based architecture
  * Depth-controlled link expansion
  * Target-based scheduling system

* **Data Extraction Engine**

  * Regex-based extraction (emails, domains, phone numbers)
  * Structured parsing from unstructured HTML content

* **Threat Detection (Matcher)**

  * Watchlist-based matching system
  * Detection of sensitive or leaked identifiers

* **Persistent Storage**

  * PostgreSQL-based storage for scalability
  * Structured storage of pages, findings, and targets

* **Evidence Collection**

  * Raw HTML storage
  * Text dump generation
  * Screenshot capture using Playwright

* **API Layer**

  * FastAPI-based REST endpoints
  * Access to targets, pages, and detected findings

---

## System Architecture

```
Scheduler (Producer / Worker)
    ↓
Fetcher (HTTP Client)
    ↓
Extractor (Pattern Parsing)
    ↓
Matcher (Threat Detection)
    ↓
Repository (Database Layer)
    ↓
Evidence Storage (HTML / Screenshot)
```

---

## Tech Stack

* **Language**: Python
* **Frameworks**: FastAPI, Asyncio
* **Database**: PostgreSQL
* **Crawler**: Custom async crawler
* **Browser Automation**: Playwright
* **Parsing**: BeautifulSoup, lxml

---

## Project Structure

```
app/
 ├── api/            # API endpoints (FastAPI)
 ├── core/           # config, DB connection
 ├── crawler/        # crawling engine
 │    ├── scheduler.py
 │    ├── fetcher.py
 │    ├── extractor.py
 │    ├── matcher.py
 │    └── screenshot.py
 ├── repository/     # DB operations
 └── init_db.py      # DB initialization

run.py               # entry point
targets.json         # crawl targets
watchlist.json       # detection rules
```

---

## How It Works

1. Scheduler periodically loads targets and pushes them into a queue
2. Workers fetch pages asynchronously
3. Extractor parses HTML and extracts structured data
4. Matcher compares extracted data against a watchlist
5. Results are stored in the database
6. Evidence (HTML, screenshots) is saved for verification

---

## Key Design Decisions

* **Queue-based architecture** for scalable crawling
* **Depth and host limits** to prevent over-crawling
* **Content hashing** to detect page changes efficiently
* **Separation of concerns** (crawler, extractor, matcher, repository)

---

## Setup

### Local Execution

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.init_db
python run.py
```

---

### Docker

```
docker-compose up --build
```

---

## Configuration

Environment variables:

* `MAX_DEPTH`
* `WORKER_COUNT`
* `REQUEST_TIMEOUT`
* `REVISIT_AFTER_SECONDS`
* `DISCORD_WEBHOOK_URL`

---

## Limitations

* Limited handling of JavaScript-heavy pages (requires Playwright)
* Tor-based crawling may be slow and unstable
* Regex-based detection may produce false positives

---

## Future Work

* Machine learning-based entity detection
* Real-time alerting system (Slack/Discord integration)
* Tor network optimization
* Web dashboard for monitoring

---

## Security Relevance

This project demonstrates:

* OSINT data collection techniques
* Automated leak detection workflows
* Scalable crawler design
* Evidence preservation for incident analysis

---

## License

For educational and research purposes only.
