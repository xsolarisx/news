#!/usr/bin/env python3
"""
News Digest — Switzerland/Bern, Poland, Europe, World, Tech

Features:
  • Async RSS fetching via aiohttp (~5x faster than sequential)
  • SQLite caching with configurable TTL
  • TOML configuration (config.toml)
  • Two-stage deduplication: prefix match + Jaccard similarity
  • Story importance scoring (cross-source coverage count)
  • Language auto-detection via langdetect
  • Translation via OpenAI gpt-4o-mini
  • AI executive summary per category via Claude API
  • Sentiment tagging (keyword-based)
  • Output: rich terminal, HTML newsletter, Markdown
  • Email delivery via SMTP
  • CLI: --category, --output, --output-file, --email, --no-cache,
         --no-translate, --health, --config
  • Source health monitoring

Run:  python3 news_digest.py [OPTIONS]
Req:  pip install aiohttp feedparser rich langdetect anthropic requests
"""

# ── Standard library ──────────────────────────────────────────────────────────
import argparse
import asyncio
import json
import os
import re
import smtplib
import sqlite3
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import requests

# ── Optional third-party ──────────────────────────────────────────────────────
try:
    import tomllib                          # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib             # pip install tomli
    except ImportError:
        tomllib = None                      # Config file disabled

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import feedparser
except ImportError:
    sys.exit("Missing dependency — run:  pip install feedparser")

try:
    from rich.console import Console
    HAS_RICH = True
    _console = Console()
except ImportError:
    HAS_RICH = False
    _console = None

try:
    from langdetect import detect as _langdetect
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


# ── Default config ────────────────────────────────────────────────────────────

_DEFAULT_CFG = {
    "digest": {
        "max_per_category": 8,
        "width": 88,
        "similarity_threshold": 0.5,
        "cache_ttl_minutes": 30,
        "cache_path": "~/.cache/news_digest.db",
    },
    "output": {
        "default_mode": "terminal",
        "output_dir": "~/news-output",
    },
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "from_addr": "",
        "to_addrs": [],
        "subject": "Daily News Digest",
    },
    "ai": {
        "translation_model": "gpt-4o-mini",
        "summary_model": "claude-haiku-4-5-20251001",
        "enable_translation": True,
        "enable_ai_summary": False,
        "enable_sentiment": True,
    },
}


def load_config(path: str = "config.toml") -> dict:
    cfg = json.loads(json.dumps(_DEFAULT_CFG))   # deep copy
    p = Path(path)
    if p.exists() and tomllib:
        with open(p, "rb") as f:
            user = tomllib.load(f)
        for section, values in user.items():
            if section in cfg and isinstance(values, dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
    return cfg


# ── Default feeds ─────────────────────────────────────────────────────────────

DEFAULT_FEEDS: list[tuple[str, str, str]] = [
    # International (English)
    ("BBC",       "http://feeds.bbci.co.uk/news/rss.xml",                   "en"),
    ("CNN",       "http://rss.cnn.com/rss/edition.rss",                     "en"),
    ("Spiegel",   "https://www.spiegel.de/international/index.rss",         "en"),
    ("Reuters",   "https://feeds.reuters.com/reuters/topNews",               "en"),
    # Tech (English)
    ("Wired",     "https://www.wired.com/feed/rss",                         "en"),
    ("Hackaday",  "https://hackaday.com/feed/",                             "en"),
    ("Ars",       "https://feeds.arstechnica.com/arstechnica/index",        "en"),
    # Switzerland — German feeds (translated)
    ("NZZ",       "https://www.nzz.ch/recent.rss",                          "de"),
    ("NZZ-CH",    "https://www.nzz.ch/schweiz.rss",                         "de"),
    ("NZZ-ZH",    "https://www.nzz.ch/zuerich.rss",                         "de"),
    ("SRF",       "https://www.srf.ch/news/bnf/rss/1646",                   "de"),
    ("SRF-CH",    "https://www.srf.ch/news/bnf/rss/1890",                   "de"),
    ("20min",     "https://partner-feeds.20min.ch/rss/20minuten",            "de"),
    ("20min-CH",  "https://partner-feeds.20min.ch/rss/20minuten/schweiz",   "de"),
    ("Blick",     "https://www.blick.ch/news/rss.xml",                      "de"),
    # Poland — Polish feeds (translated)
    ("Onet",      "https://wiadomosci.onet.pl/.feed",                       "pl"),
    ("TVN24",     "https://tvn24.pl/najnowsze.xml",                         "pl"),
    ("RMF24",     "https://www.rmf24.pl/feed",                              "pl"),
]

_SOURCE_LANG = {name: lang for name, _, lang in DEFAULT_FEEDS}
_SOURCE_LANG["Bluewin"] = "de"
_SOURCE_LANG["HackerNews"] = "en"


# ── Categories ────────────────────────────────────────────────────────────────

CATEGORIES: dict[str, list[str]] = {
    "Switzerland & Bern": [
        "switzerland", "swiss", "schweiz", "schweizerisch",
        "bern", "berne", "zurich", "zürich", "geneva", "genf", "genève",
        "basel", "lausanne", "luzern", "lugano", "winterthur",
        "bundesrat", "nationalrat", "ständerat", "bundesgericht",
        "svp", "swisscom", "ubs", "helvetia", "eidgenoss",
    ],
    "Poland": [
        "poland", "polish", "polska", "polskie", "polskich",
        "warsaw", "warszawa", "krakow", "kraków", "gdansk", "gdańsk",
        "wroclaw", "wrocław", "lodz", "łódź", "poznan", "poznań",
        "tusk", "sejm", "rzeczpospolita",
    ],
    "Europe": [
        "europe", "european", "europa", "europäisch",
        "eu", "european union", "europäische union",
        "nato", "ukraine", "ukrainian", "ukraina", "kyiv",
        "germany", "deutschland",
        "france", "frankreich",
        "italy", "italien",
        "spain", "spanien",
        "brussels", "brüssel", "bruxelles", "strasbourg",
        "berlin", "paris",
        "macron", "scholz", "von der leyen", "meloni",
    ],
    "World": [
        "china", "chinese", "beijing", "peking",
        "russia", "russian", "moscow", "kremlin",
        "iran", "iranian", "tehran",
        "israel", "israeli", "gaza", "hamas", "palestin",
        "united states", "trump", "biden", "white house", "congress",
        "united nations", "g7", "g20",
        "climate", "global warming",
        "japan", "india", "korea", "africa",
        "conflict", "war", "krieg", "sanction",
    ],
    "Tech": [
        "artificial intelligence", "machine learning", "llm",
        "openai", "chatgpt", "gemini", "anthropic", "claude",
        "technology", "software", "hardware",
        "apple", "google", "microsoft", "meta", "amazon", "tesla",
        "cybersecurity", "ransomware", "malware",
        "chip", "semiconductor", "quantum",
        "robot", "spacex", "nasa",
        "startup", "silicon valley",
        "open source", "linux", "raspberry",
    ],
}

CAT_LIMITS: dict[str, int] = {"Tech": 10}
MAX_PER_CAT = 8

# ── Sentiment keywords ────────────────────────────────────────────────────────

_POSITIVE_KW = {
    "breakthrough", "success", "growth", "record", "won", "win", "peace",
    "agreement", "deal", "recovery", "improve", "boost", "celebrate",
    "launch", "innovation", "advance", "rescue", "save", "award",
}
_NEGATIVE_KW = {
    "crash", "crisis", "death", "kill", "war", "attack", "bomb", "terror",
    "sanction", "recession", "collapse", "flood", "fire", "disaster",
    "protest", "riot", "arrest", "fraud", "hack", "breach", "threat",
    "conflict", "strike", "victim", "casualties", "explosion", "shooting",
}

# ── Stopwords for title fingerprinting ───────────────────────────────────────

_STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "this", "that", "these", "those", "with", "from", "by", "as", "into",
    "up", "out", "over", "after", "before", "about", "between", "through",
    "its", "their", "his", "her", "our", "your", "my", "it", "he", "she",
    "we", "they", "who", "what", "how", "when", "where", "which", "not",
    "new", "says", "said", "say", "just", "also", "more", "than", "s",
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    url: str = ""
    published: Optional[datetime] = None
    language: str = "en"
    categories: list = field(default_factory=list)
    source_count: int = 1
    sentiment: str = "neutral"
    fingerprint: frozenset = field(default_factory=frozenset)
    translated: bool = False


# ── SQLite cache ──────────────────────────────────────────────────────────────

class FeedCache:
    def __init__(self, db_path: str, ttl_minutes: int):
        self.db = Path(db_path).expanduser()
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(minutes=ttl_minutes)
        self.con = sqlite3.connect(str(self.db))
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                url  TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
        """)
        self.con.commit()

    def get(self, url: str) -> Optional[str]:
        row = self.con.execute(
            "SELECT data, fetched_at FROM cache WHERE url = ?", (url,)
        ).fetchone()
        if not row:
            return None
        fetched = datetime.fromisoformat(row[1]).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched > self.ttl:
            return None
        return row[0]

    def put(self, url: str, data: str) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
            (url, data, datetime.now(timezone.utc).isoformat()),
        )
        self.con.commit()

    def close(self):
        self.con.close()


# ── Text utilities ────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def shorten(text: str, n: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "…"


def _fingerprint(title: str) -> frozenset:
    words = re.sub(r"[^\w\s]", " ", title.lower()).split()
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _is_similar(fp: frozenset, seen: list, threshold: float) -> bool:
    return any(_jaccard(fp, ex) >= threshold for ex in seen)


def detect_language(title: str, source: str) -> str:
    if HAS_LANGDETECT and title:
        try:
            return _langdetect(title)
        except Exception:
            pass
    return _SOURCE_LANG.get(source, "en")


def score_sentiment(title: str, summary: str) -> str:
    blob = (title + " " + summary).lower()
    pos = sum(1 for w in _POSITIVE_KW if w in blob)
    neg = sum(1 for w in _NEGATIVE_KW if w in blob)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def categorize(title: str, summary: str) -> list[str]:
    blob = (title + " " + summary).lower()
    hits = []
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", blob):
                hits.append(cat)
                break
    return hits if hits else ["World"]


# ── Async fetchers ────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewsDigest/2.0)"}
_TIMEOUT = aiohttp.ClientTimeout(total=15) if HAS_AIOHTTP else None


async def _fetch_feed(
    session: "aiohttp.ClientSession",
    name: str,
    url: str,
    lang: str,
    cache: Optional[FeedCache],
) -> list[NewsItem]:
    try:
        raw = cache.get(url) if cache else None
        if raw is None:
            async with session.get(url, headers=_HEADERS, timeout=_TIMEOUT) as resp:
                raw = await resp.text(errors="replace")
            if cache and raw:
                cache.put(url, raw)

        feed = feedparser.parse(raw)
        items = []
        for e in feed.entries[:40]:
            title = strip_html(getattr(e, "title", ""))
            summary = shorten(strip_html(getattr(e, "summary", getattr(e, "description", ""))))
            url_e = getattr(e, "link", "")
            pub = None
            if hasattr(e, "published_parsed") and e.published_parsed:
                try:
                    pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            if title:
                detected = detect_language(title, name) if lang != "en" else "en"
                items.append(NewsItem(
                    source=name, title=title, summary=summary,
                    url=url_e, published=pub, language=detected,
                    fingerprint=_fingerprint(title),
                ))
        return items
    except Exception as ex:
        print(f"  [skip] {name}: {ex}", file=sys.stderr)
        return []


async def _fetch_bluewin(
    session: "aiohttp.ClientSession",
    cache: Optional[FeedCache],
) -> list[NewsItem]:
    sections = [
        "https://www.bluewin.ch/de/news/schweiz.html",
        "https://www.bluewin.ch/de/news/international.html",
        "https://www.bluewin.ch/de/news/wissen-technik.html",
    ]
    results: list[NewsItem] = []
    seen: set[str] = set()
    try:
        for url in sections:
            raw = cache.get(url) if cache else None
            if raw is None:
                async with session.get(
                    url, headers=_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    raw = await resp.text(errors="replace")
                if cache:
                    cache.put(url, raw)
            teasers = re.findall(
                r'<(?:div|article)[^>]+m-teaser-v2[^>]+data-t-name="Teaser"[^>]*>(.*?)'
                r'(?=<(?:div|article)[^>]+m-teaser-v2[^>]+data-t-name="Teaser"|$)',
                raw, re.DOTALL,
            )
            for block in teasers:
                lead_m = re.search(r'class="m-teaser__lead"[^>]*>(.*?)</p>', block, re.DOTALL)
                lead = shorten(strip_html(lead_m.group(1))) if lead_m else ""
                before = block[: lead_m.start()] if lead_m else block
                chunks = [
                    t.strip()
                    for t in re.sub(r"<[^>]+>", "\n", before).split("\n")
                    if len(t.strip()) > 15 and not t.strip().startswith("{")
                ]
                from html import unescape
                title = unescape(chunks[-1]) if chunks else ""
                if title and len(title) > 10 and title not in seen:
                    seen.add(title)
                    results.append(NewsItem(
                        source="Bluewin", title=title, summary=lead,
                        language="de", fingerprint=_fingerprint(title),
                    ))
    except Exception as ex:
        print(f"  [skip] Bluewin: {ex}", file=sys.stderr)
    return results


async def _fetch_hackernews(
    session: "aiohttp.ClientSession",
    cache: Optional[FeedCache],
) -> list[NewsItem]:
    try:
        cached_ids = cache.get("hn_top") if cache else None
        if cached_ids is None:
            async with session.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                ids = (await resp.json())[:25]
            if cache:
                cache.put("hn_top", json.dumps(ids))
        else:
            ids = json.loads(cached_ids)

        async def _story(sid: int) -> Optional[dict]:
            ck = f"hn_{sid}"
            raw = cache.get(ck) if cache else None
            if raw is None:
                async with session.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    data = await r.json()
                if cache and data:
                    cache.put(ck, json.dumps(data))
                return data
            return json.loads(raw)

        stories = await asyncio.gather(*[_story(i) for i in ids], return_exceptions=True)
        items = []
        for s in stories:
            if isinstance(s, Exception) or not s or s.get("type") != "story":
                continue
            title = s.get("title", "")
            score = s.get("score", 0)
            url_s = s.get("url", f"https://news.ycombinator.com/item?id={s.get('id')}")
            if title and score > 50:
                items.append(NewsItem(
                    source="HackerNews", title=title,
                    summary=f"Score: {score}",
                    url=url_s, language="en",
                    fingerprint=_fingerprint(title),
                ))
        return items
    except Exception as ex:
        print(f"  [skip] HackerNews: {ex}", file=sys.stderr)
        return []


async def fetch_all(
    feeds: list[tuple[str, str, str]],
    cache: Optional[FeedCache],
) -> tuple[list[NewsItem], dict[str, int]]:
    """Fetch all feeds concurrently. Returns (items, health_counts)."""
    if not HAS_AIOHTTP:
        print("  [warn] aiohttp not installed — fetching sequentially", file=sys.stderr)
        items: list[NewsItem] = []
        health: dict[str, int] = {}
        for name, url, lang in feeds:
            feed = feedparser.parse(url, request_headers=_HEADERS)
            batch = []
            for e in feed.entries[:40]:
                title = strip_html(getattr(e, "title", ""))
                summary = shorten(strip_html(getattr(e, "summary", "")))
                if title:
                    batch.append(NewsItem(
                        source=name, title=title, summary=summary,
                        language=lang, fingerprint=_fingerprint(title),
                    ))
            health[name] = len(batch)
            items.extend(batch)
        return items, health

    async with aiohttp.ClientSession() as session:
        feed_coros = [_fetch_feed(session, n, u, l, cache) for n, u, l in feeds]
        extra_coros = [_fetch_bluewin(session, cache), _fetch_hackernews(session, cache)]
        all_coros = feed_coros + extra_coros
        results = await asyncio.gather(*all_coros, return_exceptions=True)

    names = [n for n, _, _ in feeds] + ["Bluewin", "HackerNews"]
    all_items: list[NewsItem] = []
    health: dict[str, int] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(f"  [error] {name}: {result}", file=sys.stderr)
            health[name] = 0
        else:
            health[name] = len(result)
            all_items.extend(result)
    return all_items, health


# ── Bucketing ─────────────────────────────────────────────────────────────────

def bucket_items(all_items: list[NewsItem], cfg: dict) -> dict[str, list[NewsItem]]:
    """
    Categorize, deduplicate (2-stage), and score items.

    Stage 1 (global):  skip if first-7-word prefix already seen.
    Stage 1b (global): if near-duplicate found, increment its source_count.
    Stage 2 (per-cat): skip if Jaccard similarity >= threshold within bucket.
    Final:             sort each bucket by source_count desc.
    """
    threshold: float = cfg["digest"]["similarity_threshold"]
    buckets: dict[str, list[NewsItem]] = defaultdict(list)
    seen_prefix: set[str] = set()

    # Enrichment + source-count merge pass
    merged: list[NewsItem] = []
    for item in all_items:
        prefix = " ".join(item.title.lower().split()[:7])
        if prefix in seen_prefix:
            # Increment source_count on the first matching item
            for existing in merged:
                if _jaccard(item.fingerprint, existing.fingerprint) >= threshold:
                    existing.source_count += 1
                    break
            continue
        seen_prefix.add(prefix)
        item.sentiment = score_sentiment(item.title, item.summary)
        item.categories = categorize(item.title, item.summary)
        merged.append(item)

    # Per-category bucketing with semantic dedup
    cat_fps: dict[str, list] = defaultdict(list)
    for item in merged:
        for cat in item.categories:
            limit = CAT_LIMITS.get(cat, cfg["digest"]["max_per_category"])
            if len(buckets[cat]) >= limit:
                continue
            if item.fingerprint and _is_similar(item.fingerprint, cat_fps[cat], threshold):
                continue
            buckets[cat].append(item)
            if item.fingerprint:
                cat_fps[cat].append(item.fingerprint)

    # Sort: most cross-source coverage first
    for cat in buckets:
        buckets[cat].sort(key=lambda x: x.source_count, reverse=True)

    return dict(buckets)


# ── Translation ───────────────────────────────────────────────────────────────

def translate_buckets(buckets: dict, api_key: str, model: str) -> dict:
    to_translate = []
    for cat, items in buckets.items():
        for pos, item in enumerate(items):
            if item.language != "en" and not item.translated:
                to_translate.append({
                    "id": f"{cat}|{pos}",
                    "title": item.title,
                    "summary": item.summary,
                })
    if not to_translate:
        return buckets

    print(f"  Translating {len(to_translate)} items via OpenAI…", file=sys.stderr)
    payload = json.dumps(to_translate, ensure_ascii=False)
    prompt = (
        "Translate each item's 'title' and 'summary' fields to English. "
        "Keep proper nouns, party names, and place names as-is. "
        "Return ONLY a valid JSON array with the same structure (id, title, summary). "
        "Do not add any explanation.\n\n" + payload
    )
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model, "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        by_id = {t["id"]: t for t in json.loads(content)}
        for cat, items in buckets.items():
            for pos, item in enumerate(items):
                key = f"{cat}|{pos}"
                if key in by_id:
                    t = by_id[key]
                    item.title = t["title"]
                    item.summary = t.get("summary", item.summary)
                    item.translated = True
                    item.source = f"{item.source.split('(')[0]}({item.language.upper()}→EN)"
    except Exception as ex:
        print(f"  [translate] error: {ex}", file=sys.stderr)
    return buckets


# ── AI summaries (Claude) ─────────────────────────────────────────────────────

def ai_summaries(buckets: dict, api_key: str, model: str) -> dict[str, str]:
    """Generate a 2-sentence executive summary per category."""
    if not HAS_ANTHROPIC:
        print("  [ai] pip install anthropic to enable summaries", file=sys.stderr)
        return {}
    client = anthropic.Anthropic(api_key=api_key)
    summaries: dict[str, str] = {}
    for cat, items in buckets.items():
        if not items:
            continue
        headlines = "\n".join(f"- {item.title}" for item in items)
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": (
                        f"These are today's top {cat} headlines:\n{headlines}\n\n"
                        "Write a 2-sentence executive summary of the key themes. "
                        "Be concise and factual."
                    ),
                }],
            )
            summaries[cat] = msg.content[0].text.strip()
        except Exception as ex:
            print(f"  [ai-summary] {cat}: {ex}", file=sys.stderr)
    return summaries


# ── Terminal renderer ─────────────────────────────────────────────────────────

_SENTIMENT_ICON  = {"positive": "+", "negative": "!", "neutral": " "}
_SENTIMENT_COLOR = {"positive": "green", "negative": "red", "neutral": "white"}


def render_terminal(
    buckets: dict,
    cat_summaries: dict,
    cfg: dict,
) -> None:
    width = cfg["digest"].get("width", 88)
    bar_thick = "━" * width
    bar_thin  = "─" * width
    now = datetime.now().strftime("%A, %d %B %Y  %H:%M")

    if HAS_RICH:
        _console.print(f"\n[bold]{bar_thick}[/bold]")
        _console.print(f"  [bold cyan]NEWS DIGEST[/bold cyan]  ·  {now}")
        _console.print(f"[bold]{bar_thick}[/bold]")
        for cat in CATEGORIES:
            items = buckets.get(cat, [])
            if not items:
                continue
            _console.print(f"\n  [bold yellow]▌ {cat.upper()}[/bold yellow]")
            _console.print(f"  {bar_thin}")
            if cat in cat_summaries:
                _console.print(f"\n  [italic dim]{cat_summaries[cat]}[/italic dim]")
            for i, item in enumerate(items, 1):
                icon  = _SENTIMENT_ICON[item.sentiment]
                color = _SENTIMENT_COLOR[item.sentiment]
                src   = item.source + (f" +{item.source_count - 1}" if item.source_count > 1 else "")
                _console.print(f"\n  [bold]{i:>2}.[/bold] [{color}]{icon}[/{color}] {item.title}")
                _console.print(f"      [dim]\\[{src}][/dim]")
                if item.summary:
                    wrapped = textwrap.fill(
                        item.summary, width=width - 6,
                        initial_indent="      ", subsequent_indent="      ",
                    )
                    _console.print(f"[dim]{wrapped}[/dim]")
        _console.print(f"\n[bold]{bar_thick}[/bold]\n")
    else:
        print(f"\n{bar_thick}")
        print(f"  NEWS DIGEST  ·  {now}")
        print(bar_thick)
        for cat in CATEGORIES:
            items = buckets.get(cat, [])
            if not items:
                continue
            print(f"\n  ▌ {cat.upper()}")
            print(f"  {bar_thin}")
            if cat in cat_summaries:
                print(f"\n  Summary: {cat_summaries[cat]}")
            for i, item in enumerate(items, 1):
                icon = _SENTIMENT_ICON[item.sentiment]
                src  = item.source + (f" +{item.source_count - 1}" if item.source_count > 1 else "")
                print(f"\n  {i:>2}. [{icon}] {item.title}")
                print(f"      [{src}]")
                if item.summary:
                    print(textwrap.fill(
                        item.summary, width=width - 6,
                        initial_indent="      ", subsequent_indent="      ",
                    ))
        print(f"\n{bar_thick}\n")


# ── HTML renderer ─────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>News Digest — {date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f1117; color: #e2e8f0; line-height: 1.6; }}
  .wrap {{ max-width: 800px; margin: 0 auto; padding: 24px 16px; }}
  header {{ border-bottom: 2px solid #3b82f6; padding-bottom: 16px; margin-bottom: 24px; }}
  header h1 {{ font-size: 1.4rem; color: #60a5fa; letter-spacing: 0.1em; }}
  .date {{ color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }}
  .cat {{ margin-bottom: 32px; }}
  .cat h2 {{ font-size: 0.9rem; font-weight: 700; letter-spacing: 0.15em;
             color: #fbbf24; border-left: 3px solid #fbbf24;
             padding-left: 10px; margin-bottom: 6px; }}
  .ai-sum {{ font-size: 0.82rem; color: #94a3b8; font-style: italic;
             margin: 0 0 12px 13px; }}
  .item {{ border-left: 2px solid #1e293b; padding: 10px 0 10px 14px;
           margin-bottom: 6px; }}
  .item:hover {{ border-left-color: #3b82f6; }}
  .title {{ font-size: 0.97rem; font-weight: 600; color: #f1f5f9; }}
  .title a {{ color: inherit; text-decoration: none; }}
  .title a:hover {{ color: #60a5fa; }}
  .meta {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
           font-size: 0.75rem; color: #64748b; margin: 3px 0; }}
  .badge {{ padding: 1px 7px; border-radius: 9999px;
            font-size: 0.7rem; font-weight: 600; }}
  .positive {{ background: #064e3b; color: #34d399; }}
  .negative {{ background: #450a0a; color: #f87171; }}
  .neutral  {{ background: #1e293b; color: #94a3b8; }}
  .multi    {{ background: #1e3a5f; color: #93c5fd; }}
  .sum {{ font-size: 0.82rem; color: #94a3b8; margin-top: 4px; }}
  footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #1e293b;
            font-size: 0.75rem; color: #475569; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>NEWS DIGEST</h1>
    <div class="date">{date}</div>
  </header>
  {body}
  <footer>Generated by News Digest &middot; {date}</footer>
</div>
</body>
</html>"""


def render_html(buckets: dict, cat_summaries: dict) -> str:
    from html import escape
    now = datetime.now().strftime("%A, %d %B %Y  %H:%M")
    body_parts = []
    for cat in CATEGORIES:
        items = buckets.get(cat, [])
        if not items:
            continue
        ai_html = (
            f'<div class="ai-sum">{escape(cat_summaries[cat])}</div>'
            if cat in cat_summaries else ""
        )
        items_html = []
        for item in items:
            title_html = (
                f'<a href="{escape(item.url)}">{escape(item.title)}</a>'
                if item.url else escape(item.title)
            )
            badges = f'<span class="badge {item.sentiment}">{item.sentiment}</span>'
            if item.source_count > 1:
                badges += f' <span class="badge multi">{item.source_count} sources</span>'
            sum_html = f'<div class="sum">{escape(item.summary)}</div>' if item.summary else ""
            items_html.append(
                f'<div class="item">'
                f'<div class="title">{title_html}</div>'
                f'<div class="meta">{badges} <span>{escape(item.source)}</span></div>'
                f'{sum_html}'
                f'</div>'
            )
        body_parts.append(
            f'<div class="cat"><h2>{escape(cat)}</h2>'
            f'{ai_html}{"".join(items_html)}</div>'
        )
    return _HTML_TEMPLATE.format(date=now, body="\n".join(body_parts))


# ── Markdown renderer ─────────────────────────────────────────────────────────

def render_markdown(buckets: dict, cat_summaries: dict) -> str:
    now = datetime.now().strftime("%A, %d %B %Y  %H:%M")
    lines = [f"# News Digest — {now}", ""]
    for cat in CATEGORIES:
        items = buckets.get(cat, [])
        if not items:
            continue
        lines.append(f"## {cat}")
        if cat in cat_summaries:
            lines.append(f"\n> {cat_summaries[cat]}\n")
        for item in items:
            src = item.source + (f" +{item.source_count - 1}" if item.source_count > 1 else "")
            title_md = f"[{item.title}]({item.url})" if item.url else item.title
            lines.append(f"### {title_md}")
            lines.append(f"**{src}** · _{item.sentiment}_")
            if item.summary:
                lines.append(f"\n{item.summary}")
            lines.append("")
        lines += ["---", ""]
    return "\n".join(lines)


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(html_body: str, cfg: dict) -> None:
    ec = cfg["email"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = ec["subject"]
    msg["From"]    = ec["from_addr"]
    msg["To"]      = ", ".join(ec["to_addrs"])
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as smtp:
            smtp.starttls()
            smtp.login(ec["smtp_user"], ec["smtp_password"])
            smtp.sendmail(ec["from_addr"], ec["to_addrs"], msg.as_string())
        print(f"  Email sent to {', '.join(ec['to_addrs'])}", file=sys.stderr)
    except Exception as ex:
        print(f"  [email] error: {ex}", file=sys.stderr)


# ── Source health ─────────────────────────────────────────────────────────────

def print_health(health: dict[str, int]) -> None:
    print("\n  Source health report:", file=sys.stderr)
    for name, count in sorted(health.items()):
        status = "OK  " if count > 0 else "DEAD"
        print(f"    {name:<14} {count:>3} items  [{status}]", file=sys.stderr)
    dead = [n for n, c in health.items() if c == 0]
    if dead:
        print(f"\n  [warn] Dead/empty sources: {', '.join(dead)}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Categorized news digest from RSS feeds.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--category", "-c", metavar="CAT",
                   help="Show only categories matching this string (case-insensitive)")
    p.add_argument("--output", "-o",
                   choices=["terminal", "html", "markdown"],
                   help="Output format (default: from config or 'terminal')")
    p.add_argument("--output-file", metavar="FILE",
                   help="Write rendered output to this file")
    p.add_argument("--email", action="store_true",
                   help="Send digest via SMTP (requires [email] config)")
    p.add_argument("--no-cache", action="store_true",
                   help="Bypass cache and fetch fresh data")
    p.add_argument("--no-translate", action="store_true",
                   help="Skip translation even if OPENAI_API_KEY is set")
    p.add_argument("--health", action="store_true",
                   help="Print per-source item counts after fetching")
    p.add_argument("--config", default="config.toml", metavar="FILE",
                   help="Path to TOML config file (default: config.toml)")
    return p


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _build_parser().parse_args()
    cfg  = load_config(args.config)
    mode = args.output or cfg["output"]["default_mode"]

    # Cache
    cache: Optional[FeedCache] = None
    if not args.no_cache:
        cache = FeedCache(cfg["digest"]["cache_path"], cfg["digest"]["cache_ttl_minutes"])

    # Feeds: from config if present, else builtin defaults
    feeds: list[tuple[str, str, str]] = []
    if "feeds" in cfg:
        for f in cfg["feeds"]:
            feeds.append((f["name"], f["url"], f.get("language", "en")))
    else:
        feeds = DEFAULT_FEEDS

    print(f"\nFetching {len(feeds)} RSS feeds + Bluewin + HackerNews…", file=sys.stderr)
    t0 = datetime.now()
    all_items, health = asyncio.run(fetch_all(feeds, cache))
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"  {len(all_items)} items in {elapsed:.1f}s", file=sys.stderr)

    if args.health:
        print_health(health)

    # Categorize + deduplicate + score
    buckets = bucket_items(all_items, cfg)

    # Category filter
    if args.category:
        kw = args.category.lower()
        buckets = {k: v for k, v in buckets.items() if kw in k.lower()}

    # Translate
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key and not args.no_translate and cfg["ai"]["enable_translation"]:
        buckets = translate_buckets(buckets, openai_key, cfg["ai"]["translation_model"])

    # AI category summaries
    cat_sums: dict[str, str] = {}
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key and cfg["ai"]["enable_ai_summary"]:
        print("  Generating AI summaries…", file=sys.stderr)
        cat_sums = ai_summaries(buckets, anthropic_key, cfg["ai"]["summary_model"])

    if cache:
        cache.close()

    # Render
    if mode == "html":
        content = render_html(buckets, cat_sums)
        if args.output_file:
            Path(args.output_file).write_text(content, encoding="utf-8")
            print(f"  HTML written to {args.output_file}", file=sys.stderr)
        else:
            print(content)
        if args.email and cfg["email"]["enabled"]:
            send_email(content, cfg)

    elif mode == "markdown":
        content = render_markdown(buckets, cat_sums)
        if args.output_file:
            Path(args.output_file).write_text(content, encoding="utf-8")
            print(f"  Markdown written to {args.output_file}", file=sys.stderr)
        else:
            print(content)

    else:
        render_terminal(buckets, cat_sums, cfg)
        if args.email and cfg["email"]["enabled"]:
            send_email(render_html(buckets, cat_sums), cfg)


if __name__ == "__main__":
    main()
