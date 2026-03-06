#!/usr/bin/env python3
"""
News Digest — Switzerland/Bern, Poland, Europe, World, Tech

Fetches RSS feeds from nzz, srf, cnn, bbc, spiegel, wired, hackaday,
buzzfeed, onet, tvn24, rmf24 and prints a categorized digest.

Non-English items (German/Polish) are auto-translated to English
using OpenAI gpt-4o-mini when OPENAI_API_KEY is set in the environment.

Note: 20min.ch and blue.news have no public RSS (JS-rendered / geo-blocked).

Requires:  pip install feedparser
Run:       python3 news_digest.py
"""

import json
import os
import re
import sys
import textwrap
from collections import defaultdict
from datetime import datetime

import requests

try:
    import feedparser
except ImportError:
    sys.exit("Missing dependency — run:  pip install feedparser")

# ── Sources ────────────────────────────────────────────────────────────────────

FEEDS = [
    # International (English)
    ("BBC",       "http://feeds.bbci.co.uk/news/rss.xml"),
    ("CNN",       "http://rss.cnn.com/rss/edition.rss"),
    ("Spiegel",   "https://www.spiegel.de/international/index.rss"),
    # Tech (English)
    ("Wired",     "https://www.wired.com/feed/rss"),
    ("Hackaday",  "https://hackaday.com/feed/"),
    ("BuzzFeed",  "https://www.buzzfeed.com/world.xml"),
    # Switzerland — German feeds (will be translated)
    # blue.ch = Swisscom TV (no news RSS); blue.news = NXDOMAIN
    ("NZZ",       "https://www.nzz.ch/recent.rss"),
    ("NZZ-CH",    "https://www.nzz.ch/schweiz.rss"),
    ("NZZ-ZH",    "https://www.nzz.ch/zuerich.rss"),
    ("SRF",       "https://www.srf.ch/news/bnf/rss/1646"),   # all news
    ("SRF-CH",    "https://www.srf.ch/news/bnf/rss/1890"),   # Schweiz section
    ("20min",     "https://partner-feeds.20min.ch/rss/20minuten"),
    ("20min-CH",  "https://partner-feeds.20min.ch/rss/20minuten/schweiz"),
    # Poland — Polish feeds (will be translated)
    ("Onet",      "https://wiadomosci.onet.pl/.feed"),
    ("TVN24",     "https://tvn24.pl/najnowsze.xml"),
    ("RMF24",     "https://www.rmf24.pl/feed"),
]

# Sources whose content is not in English → language tag for translation notice
NON_ENGLISH = {
    "NZZ": "DE", "NZZ-CH": "DE", "NZZ-ZH": "DE",
    "SRF": "DE", "SRF-CH": "DE",
    "20min": "DE", "20min-CH": "DE",
    "Bluewin": "DE",
    "Onet": "PL", "TVN24": "PL", "RMF24": "PL",
}

# ── Category keywords (English + German + Polish) ──────────────────────────────
# All keywords use whole-word matching (\b boundaries) to avoid false positives

CATEGORIES = {
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
        "openai", "chatgpt", "gemini", "anthropic",
        "technology", "software", "hardware",
        "apple", "google", "microsoft", "meta", "amazon", "tesla",
        "cybersecurity", "ransomware", "malware",
        "chip", "semiconductor", "quantum",
        "robot", "spacex", "nasa",
        "startup", "silicon valley",
    ],
}

MAX_PER_CAT = 8
CAT_LIMITS = {"Tech": 10}   # per-category overrides
WIDTH = 88
SIMILARITY_THRESHOLD = 0.5  # Jaccard similarity cutoff for within-category dedup

# Common words excluded from title fingerprinting
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


# ── RSS helpers ────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def shorten(text: str, n: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "…"


def _title_fingerprint(title: str) -> frozenset[str]:
    """Return a set of content words (no stopwords, length > 2) for similarity comparison."""
    words = re.sub(r"[^\w\s]", " ", title.lower()).split()
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)


def _is_similar(fp: frozenset, seen: list) -> bool:
    """Return True if fp is Jaccard-similar to any fingerprint in seen."""
    for existing in seen:
        union = len(fp | existing)
        if union and len(fp & existing) / union >= SIMILARITY_THRESHOLD:
            return True
    return False


def categorize(title: str, summary: str) -> list[str]:
    blob = (title + " " + summary).lower()
    hits = []
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", blob):
                hits.append(cat)
                break
    return hits if hits else ["World"]


def fetch(name: str, url: str) -> list[tuple]:
    try:
        feed = feedparser.parse(
            url,
            request_headers={"User-Agent": "Mozilla/5.0 (compatible; NewsDigest/1.0)"},
        )
        results = []
        for e in feed.entries[:40]:
            title = strip_html(getattr(e, "title", ""))
            raw = getattr(e, "summary", getattr(e, "description", ""))
            summary = shorten(strip_html(raw))
            if title:
                results.append((name, title, summary))
        return results
    except Exception as ex:
        print(f"  [skip] {name}: {ex}", file=sys.stderr)
        return []


def fetch_bluewin() -> list[tuple]:
    """
    Scrape bluewin.ch/de/news — no public RSS, parsed from rendered HTML.
    Returns list of (source, title, summary) tuples tagged as 'Bluewin'.
    """
    BLUEWIN_SECTIONS = [
        "https://www.bluewin.ch/de/news/schweiz.html",
        "https://www.bluewin.ch/de/news/international.html",
        "https://www.bluewin.ch/de/news/wissen-technik.html",
    ]
    results = []
    seen_titles: set[str] = set()
    try:
        for url in BLUEWIN_SECTIONS:
            r = requests.get(url, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0"})
            teasers = re.findall(
                r'<(?:div|article)[^>]+m-teaser-v2[^>]+data-t-name="Teaser"[^>]*>(.*?)'
                r'(?=<(?:div|article)[^>]+m-teaser-v2[^>]+data-t-name="Teaser"|$)',
                r.text, re.DOTALL
            )
            for block in teasers:
                lead_m = re.search(
                    r'class="m-teaser__lead"[^>]*>(.*?)</p>', block, re.DOTALL
                )
                lead = shorten(strip_html(lead_m.group(1))) if lead_m else ""
                before = block[: lead_m.start()] if lead_m else block
                chunks = [
                    t.strip()
                    for t in re.sub(r"<[^>]+>", "\n", before).split("\n")
                    if len(t.strip()) > 15 and not t.strip().startswith("{")
                ]
                from html import unescape
                title = unescape(chunks[-1]) if chunks else ""
                if title and len(title) > 10 and title not in seen_titles:
                    seen_titles.add(title)
                    results.append(("Bluewin", title, lead))
    except Exception as ex:
        print(f"  [skip] Bluewin: {ex}", file=sys.stderr)
    return results


# ── Translation ────────────────────────────────────────────────────────────────

def translate_batch(items: list[dict], api_key: str) -> list[dict]:
    """
    Send a batch of {id, title, summary} dicts to OpenAI and get back
    the same structure with English text. Returns original list on failure.
    """
    payload = json.dumps(items, ensure_ascii=False)
    prompt = (
        "Translate each item's 'title' and 'summary' fields to English. "
        "Keep proper nouns, party names, and place names as-is. "
        "Return ONLY a valid JSON array with the same structure (id, title, summary). "
        "Do not add any explanation.\n\n" + payload
    )
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if model wraps output
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        translated = json.loads(content)
        # Build lookup by id
        by_id = {t["id"]: t for t in translated}
        return [by_id.get(it["id"], it) for it in items]
    except Exception as ex:
        print(f"  [translate] error: {ex}", file=sys.stderr)
        return items


def translate_buckets(
    buckets: dict[str, list], api_key: str
) -> dict[str, list]:
    """
    Translate only the items that made it into display buckets.
    Much cheaper — at most MAX_PER_CAT * len(CATEGORIES) items total.
    """
    # Collect every non-English item across all buckets
    to_translate = []
    for cat, items in buckets.items():
        for pos, (source, title, summary) in enumerate(items):
            lang = NON_ENGLISH.get(source.split("(")[0])   # handle already-tagged
            if lang:
                to_translate.append({
                    "id": f"{cat}|{pos}",
                    "title": title,
                    "summary": summary,
                })

    if not to_translate:
        return buckets

    print(f"  Translating {len(to_translate)} displayed items via OpenAI…", file=sys.stderr)
    translated = translate_batch(to_translate, api_key)
    by_id = {t["id"]: t for t in translated}

    # Rebuild buckets with translated text
    new_buckets: dict[str, list] = {}
    for cat, items in buckets.items():
        new_items = []
        for pos, (source, title, summary) in enumerate(items):
            key = f"{cat}|{pos}"
            base_source = source.split("(")[0]
            lang = NON_ENGLISH.get(base_source)
            if lang and key in by_id:
                t = by_id[key]
                new_items.append((f"{base_source}({lang}→EN)", t["title"], t.get("summary", summary)))
            else:
                new_items.append((source, title, summary))
        new_buckets[cat] = new_items
    return new_buckets


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\nFetching feeds from {len(FEEDS)} sources + Bluewin (scraped)…", file=sys.stderr)

    all_items: list[tuple] = []
    for name, url in FEEDS:
        items = fetch(name, url)
        print(f"  {name:<12} {len(items):>3} items", file=sys.stderr)
        all_items.extend(items)

    bluewin_items = fetch_bluewin()
    print(f"  {'Bluewin':<12} {len(bluewin_items):>3} items  (scraped)", file=sys.stderr)
    all_items.extend(bluewin_items)

    # Bucket items into categories; deduplicate by title prefix then by semantic similarity
    buckets: dict[str, list] = defaultdict(list)
    seen_prefix: set[str] = set()
    cat_fingerprints: dict[str, list] = defaultdict(list)

    for source, title, summary in all_items:
        # Stage 1: global exact-prefix dedup (first 7 tokens)
        key = " ".join(title.lower().split()[:7])
        if key in seen_prefix:
            continue
        seen_prefix.add(key)

        fp = _title_fingerprint(title)
        for cat in categorize(title, summary):
            limit = CAT_LIMITS.get(cat, MAX_PER_CAT)
            if len(buckets[cat]) >= limit:
                continue
            # Stage 2: per-category semantic dedup (Jaccard similarity)
            if fp and _is_similar(fp, cat_fingerprints[cat]):
                continue
            buckets[cat].append((source, title, summary))
            if fp:
                cat_fingerprints[cat].append(fp)

    # Translate only items that made it into the buckets (fast — few items)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        buckets = translate_buckets(buckets, api_key)

    # ── Render ─────────────────────────────────────────────────────────────────

    now = datetime.now().strftime("%A, %d %B %Y  %H:%M")
    bar_thick = "━" * WIDTH
    bar_thin  = "─" * WIDTH

    print(f"\n{bar_thick}")
    print(f"  NEWS DIGEST  ·  {now}")
    print(bar_thick)

    for cat in CATEGORIES:
        items = buckets.get(cat, [])
        if not items:
            continue
        print(f"\n  ▌ {cat.upper()}")
        print(f"  {bar_thin}")
        for i, (src, title, summary) in enumerate(items, 1):
            print(f"\n  {i:>2}. {title}")
            print(f"      [{src}]")
            if summary:
                wrapped = textwrap.fill(
                    summary,
                    width=WIDTH - 6,
                    initial_indent="      ",
                    subsequent_indent="      ",
                )
                print(wrapped)

    print(f"\n{bar_thick}\n")


if __name__ == "__main__":
    main()
