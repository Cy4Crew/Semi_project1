from __future__ import annotations

import re
from hashlib import sha256

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,24}\b")
ONION_RE = re.compile(r"\b[a-z2-7]{16,56}\.onion\b", re.IGNORECASE)
DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]{1,63}\.)+[A-Za-z]{2,24}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,16}\d)(?!\w)")
USERNAME_RE = re.compile(r"(?<![\w@.])@[a-zA-Z0-9_]{4,24}\b")
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
DATE_LIKE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:\s+\d{2}(?::\d{2}(?::\d{2})?)?)?\b")

URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
TELEGRAM_RE = re.compile(r"(?:https?://)?t\.me/[a-zA-Z0-9_]{3,64}", re.IGNORECASE)
BTC_RE = re.compile(r"\b(?:bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9._-]{10,}\.[a-zA-Z0-9._-]{10,}\b")
MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
SHA1_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")

BAD_DOMAIN_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".zip", ".rar", ".7z", ".pdf", ".xml",
}
BAD_DOMAIN_VALUES = {
    "localhost", "example.com", "example.org", "example.net",
    "w3.org", "schema.org",
}
BAD_USERNAMES = {"admin", "root", "user", "guest", "support"}


def normalize_value(item_type: str, value: str) -> str:
    v = value.strip().strip(".,:;()[]{}<>\"'").lower()

    if item_type == "phone":
        v = re.sub(r"\D+", "", v)
    elif item_type == "username" and v.startswith("@"):
        v = v[1:]
    elif item_type == "telegram":
        v = v.removeprefix("https://").removeprefix("http://").lower()
    elif item_type == "url":
        v = v.rstrip("/")

    return v


def group_key(item_type: str, normalized: str) -> str:
    return sha256(f"{item_type}:{normalized}".encode("utf-8")).hexdigest()


def _valid_domain(v: str) -> bool:
    if v in BAD_DOMAIN_VALUES:
        return False
    if v.endswith(".onion"):
        return False
    if any(v.endswith(s) for s in BAD_DOMAIN_SUFFIXES):
        return False
    if v.count(".") < 1:
        return False
    return True


def _looks_like_ip(raw: str) -> bool:
    return IPV4_RE.fullmatch(raw.strip()) is not None


def _looks_like_date(raw: str) -> bool:
    return DATE_LIKE_RE.fullmatch(raw.strip()) is not None


def _valid_phone(raw: str, normalized: str) -> bool:
    raw = raw.strip()

    if "." in raw:
        return False
    if _looks_like_ip(raw):
        return False
    if _looks_like_date(raw):
        return False
    if not (8 <= len(normalized) <= 15):
        return False
    if re.fullmatch(r"(\d)\1{7,}", normalized):
        return False
    return True


def _valid_hash(raw: str) -> bool:
    s = raw.lower()
    if len(set(s)) <= 2:
        return False
    return True


def extract_indicators(text: str) -> list[dict[str, str]]:
    found: dict[tuple[str, str], dict[str, str]] = {}

    emails = set(EMAIL_RE.findall(text))
    email_domains = {e.split("@", 1)[1].lower() for e in emails}
    onions = set(ONION_RE.findall(text))
    ipv4s = set(IPV4_RE.findall(text))

    patterns = {
        "email": emails,
        "onion": onions,
        "domain": DOMAIN_RE.findall(text),
        "phone": PHONE_RE.findall(text),
        "username": USERNAME_RE.findall(text),
        "ipv4": ipv4s,
        "url": URL_RE.findall(text),
        "telegram": TELEGRAM_RE.findall(text),
        "btc": BTC_RE.findall(text),
        "api_key": AWS_KEY_RE.findall(text) + JWT_RE.findall(text),
        "hash": MD5_RE.findall(text) + SHA1_RE.findall(text) + SHA256_RE.findall(text),
    }

    for item_type, values in patterns.items():
        for raw in values:
            normalized = normalize_value(item_type, raw)
            if not normalized:
                continue

            if item_type == "domain":
                if normalized in email_domains or "@" in raw or not _valid_domain(normalized):
                    continue

            elif item_type == "phone":
                if not _valid_phone(raw, normalized):
                    continue

            elif item_type == "username":
                if normalized in BAD_USERNAMES:
                    continue

            elif item_type == "telegram":
                if not normalized.startswith("t.me/"):
                    continue

            elif item_type == "url":
                if normalized.startswith("http://localhost") or normalized.startswith("https://localhost"):
                    continue

            elif item_type == "hash":
                if not _valid_hash(raw):
                    continue

            key = (item_type, normalized)
            found[key] = {
                "type": item_type,
                "raw": raw,
                "normalized": normalized,
                "group_key": group_key(item_type, normalized),
            }

    return list(found.values())