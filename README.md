# Darkweb OSINT Monitoring System

## Overview

This system is a real-time threat intelligence platform that collects, analyzes, and monitors data leaks from both surface web and dark web sources.

It provides an end-to-end pipeline including crawling, extraction, pattern matching, storage, and evidence collection.

Key additional features:
- Discord alert notifications
- Tor-based crawling for `.onion` dark web targets

---

## Key Features

### Asynchronous Web Crawling
- Multi-worker queue-based architecture
- Depth-based link expansion
- Target scheduling system

### Data Extraction
- Regex-based extraction (email, domain, phone, etc.)
- HTML parsing using BeautifulSoup

### Threat Detection (Matcher)
- Watchlist-based detection
- Deduplicated matching logic

### Storage
- PostgreSQL-based persistence
- Structured schema (targets, pages, findings)

### Evidence Collection
- Raw HTML storage
- Text dump generation
- Screenshot capture (Playwright)

### API Layer
- FastAPI-based REST API
- Access to targets, pages, and findings

### Discord Alert System
- Sends real-time alerts via Discord Webhook when sensitive data is detected

### Tor (.onion) Support
- Crawls `.onion` domains using Tor proxy
- Enables dark web OSINT collection

---

## Tech Stack

- Python (Asyncio)
- FastAPI
- PostgreSQL
- Playwright
- BeautifulSoup / lxml
- httpx (async HTTP client)
- Tor (SOCKS5 proxy)

---

## Project Structure

app/
 ├── api/
 ├── core/
 ├── crawler/
 │    ├── scheduler.py
 │    ├── fetcher.py
 │    ├── extractor.py
 │    ├── matcher.py
 │    └── screenshot.py
 ├── repository/

run.py
targets.json
watchlist.json

---

## Setup

### Install

pip install -r requirements.txt

---

### Initialize Database

python -m app.init_db

---

### Run

python run.py

or (Windows):

run.bat

---

## Configuration (.env)

DATABASE_URL=postgresql://user:pass@localhost:5432/intel
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx
TOR_PROXY=socks5://127.0.0.1:9050

---

## Discord Alerts

- Automatically triggered on detection
- Requires webhook URL configuration

Alert includes:
- URL
- Matched value
- Type (email, domain, etc.)

---

## Tor (.onion) Crawling

### Requirements

Tor must be running (default port: 9050)

tor

or run Tor Browser

---

### Configuration

Use SOCKS5 proxy in fetcher:

socks5://127.0.0.1:9050

This enables:
- Crawling `.onion` domains
- Hybrid surface + dark web monitoring

---

## Notes

- Depth and worker settings are configurable
- Proper transaction and concurrency handling is required
- Deduplication in matcher is critical for performance
