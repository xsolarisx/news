# News Digest — Reverse-Engineered Specification

This document describes the full behaviour of `news_digest.py` as inferred from the source code and feature set.

---

## 1. Purpose

Produce a formatted, categorized news digest by aggregating RSS feeds and scraped content from 18+ international sources. Non-English stories are auto-detected, optionally machine-translated, deduplicated, scored by importance, sentiment-tagged, and rendered in one of three output formats (terminal, HTML, Markdown). Optional email delivery is supported. All configuration is external (TOML file).

---

## 2. Data Model

### 2.1 NewsItem dataclass

Each story is represented as a `NewsItem` dataclass with the following fields:

| Field | Type | Description |
|---|---|---|
| `source` | `str` | Feed name (e.g. `"NZZ"`, `"BBC"`) |
| `title` | `str` | HTML-stripped story title |
| `summary` | `str` | HTML-stripped, whitespace-normalized, truncated to ~240 chars |
| `url` | `str` | Story permalink (from feed entry) |
| `published` | `datetime \| None` | Publication timestamp, if available in feed |
| `language` | `str` | ISO 639-1 code detected by `langdetect` (e.g. `"de"`, `"pl"`, `"en"`) |
| `translated` | `bool` | True if title/summary were machine-translated |
| `sentiment` | `str` | `"positive"`, `"neutral"`, or `"negative"` |
| `source_count` | `int` | Number of independent sources covering this story (importance score) |
| `categories` | `list[str]` | All matched categories (may be multiple) |

---

## 3. Data Sources

### 3.1 Async RSS Fetching

All RSS feeds are fetched concurrently using `aiohttp` (asyncio event loop). This replaces sequential `feedparser` calls and yields approximately 5x throughput improvement.

Up to 40 entries are read per feed. A `User-Agent` header mimicking a browser is sent with each request.

| Name | URL | Language |
|---|---|---|
| BBC | http://feeds.bbci.co.uk/news/rss.xml | EN |
| CNN | http://rss.cnn.com/rss/edition.rss | EN |
| Reuters | (configured in config.toml) | EN |
| Spiegel | https://www.spiegel.de/international/index.rss | EN |
| Wired | https://www.wired.com/feed/rss | EN |
| Hackaday | https://hackaday.com/feed/ | EN |
| Ars Technica | https://feeds.arstechnica.com/arstechnica/index | EN |
| NZZ | https://www.nzz.ch/recent.rss | DE |
| NZZ-CH | https://www.nzz.ch/schweiz.rss | DE |
| NZZ-ZH | https://www.nzz.ch/zuerich.rss | DE |
| SRF | https://www.srf.ch/news/bnf/rss/1646 | DE |
| SRF-CH | https://www.srf.ch/news/bnf/rss/1890 | DE |
| 20min | https://partner-feeds.20min.ch/rss/20minuten | DE |
| 20min-CH | https://partner-feeds.20min.ch/rss/20minuten/schweiz | DE |
| Blick | (configured in config.toml) | DE |
| Onet | https://wiadomosci.onet.pl/.feed | PL |
| TVN24 | https://tvn24.pl/najnowsze.xml | PL |
| RMF24 | https://www.rmf24.pl/feed | PL |

Feeds can be added, removed, or overridden via `[[feeds]]` entries in `config.toml`.

### 3.2 Hacker News

Top stories are fetched from the Hacker News Firebase JSON API (`https://hacker-news.firebaseio.com/v0/topstories.json`). The top N story IDs are retrieved, then each story's JSON is fetched individually to obtain title, URL, and score.

### 3.3 Bluewin (scraped)

Bluewin publishes no public RSS feed. Three sections are scraped via `requests`:

- `/de/news/schweiz.html`
- `/de/news/international.html`
- `/de/news/wissen-technik.html`

HTML is parsed with regex patterns targeting `m-teaser-v2` / `data-t-name="Teaser"` blocks. Title extraction: last non-empty text chunk before the lead paragraph (length > 15 chars, not JSON-looking). Summary: content of `m-teaser__lead` paragraph. Intra-source deduplication uses a `seen_titles` set per scrape run.

---

## 4. Caching

### 4.1 Storage

Raw feed responses are cached in an SQLite database (default path: `cache.db`, configurable in `config.toml`).

### 4.2 Schema

```
table: feed_cache
  url       TEXT PRIMARY KEY
  content   TEXT
  fetched_at INTEGER   -- Unix timestamp
```

### 4.3 TTL

On each fetch, if a cached entry exists and `(now - fetched_at) < cache_ttl_seconds`, the cached content is used without a network request. Default TTL: 3600 seconds. Overridden with `--no-cache` flag.

---

## 5. Categorization

### 5.1 Categories (display order)

1. Switzerland & Bern
2. Poland
3. Europe
4. World
5. Tech

### 5.2 Algorithm

- Concatenate `title + " " + summary`, lowercased
- For each category, test each keyword with `\b<keyword>\b` (whole-word regex)
- An item is assigned to **all** matching categories
- If no category matches, the item is assigned to "World"

### 5.3 Keywords (representative subset)

- **Switzerland & Bern**: switzerland, swiss, schweiz, bern, zurich, zürich, geneva, ubs, svp, bundesrat, nationalrat, ständerat
- **Poland**: poland, polish, polska, warsaw, warszawa, tusk, sejm, rzeczpospolita
- **Europe**: europe, european, eu, nato, ukraine, kyiv, germany, france, macron, scholz, von der leyen, brussels
- **World**: china, russia, iran, israel, gaza, trump, united nations, climate, war, conflict
- **Tech**: artificial intelligence, llm, openai, chatgpt, anthropic, apple, google, cybersecurity, chip, semiconductor, spacex

---

## 6. Deduplication

Two-stage deduplication prevents showing the same story multiple times.

### 6.1 Stage 1 — Global prefix match

Key: first 7 lowercase title tokens joined by space. Items with a matching key are skipped globally, regardless of source. This catches near-identical headlines from different wires.

### 6.2 Stage 2 — Per-category Jaccard similarity

Within each category bucket, Jaccard similarity is computed between the content-word fingerprints of candidate titles and all already-accepted titles.

- **Fingerprint**: `frozenset` of words with length > 2 and not in the stopword list, after stripping punctuation and lowercasing
- **Threshold**: 0.5 — if `|A ∩ B| / |A ∪ B| >= 0.5`, the candidate is considered a duplicate within that category and is skipped
- **Scope**: per-category (same story can still appear in two different categories if it matches both)

---

## 7. Importance Scoring

For each story that survives deduplication, the `source_count` field is incremented each time an additional source is found covering a Jaccard-similar story. Stories with `source_count > 1` are considered higher importance and displayed with a `[sources: N]` label in terminal output.

---

## 8. Language Detection

`langdetect` is applied to each `title + " " + summary` string to populate the `language` field (ISO 639-1). Detection runs before translation. If detection raises an exception (short text, ambiguous), the language defaults to `"en"`.

---

## 9. Translation

### 9.1 Trigger

Active when `OPENAI_API_KEY` is non-empty in environment or `config.toml`, and `--no-translate` is not passed.

### 9.2 Scope

Only items that survive deduplication and make it into the final display buckets are translated. This minimizes API calls and cost.

### 9.3 Batch API call

- Endpoint: `POST https://api.openai.com/v1/chat/completions`
- Model: `gpt-4o-mini` (configurable)
- Temperature: `0.1`
- Prompt: instructs translation of `title` and `summary` fields; proper nouns, party names, and place names must be preserved
- Input/output format: JSON array of `{id, title, summary}` objects
- IDs use `"<category>|<position>"` format for reassembly
- Markdown code fences in the response are stripped before JSON parsing

### 9.4 Source labelling

Translated items have their source renamed: `"NZZ"` becomes `"NZZ(DE->EN)"`.

### 9.5 Failure handling

Translation errors are printed to stderr. Original (untranslated) items are used as fallback.

---

## 10. Sentiment Tagging

Each `NewsItem` receives a `sentiment` field: `"positive"`, `"neutral"`, or `"negative"`.

Sentiment is assigned by keyword matching on the lowercased concatenation of title and summary:

- **Positive keywords** (representative): breakthrough, recovery, agreement, peace, growth, investment, success, approved, launched, improved
- **Negative keywords** (representative): killed, dead, crash, attack, crisis, war, explosion, arrest, collapse, disaster, scandal, fraud
- **Neutral**: neither or both sets match

Sentiment is determined before translation (applied to original text) to avoid artifacts introduced by the translation model.

---

## 11. AI Executive Summaries

### 11.1 Trigger

Active when `ANTHROPIC_API_KEY` is non-empty and at least one story exists in the category bucket.

### 11.2 Model

Anthropic `claude-haiku-4-5-20251001` (configurable in `config.toml`).

### 11.3 Prompt

For each category, the translated titles and summaries of all stories in the bucket are passed to the model. The prompt requests a concise one-paragraph executive summary of the key developments in that category.

### 11.4 Output placement

The summary is rendered immediately below the category heading and above the individual story list, visually distinguished (italic in terminal, blockquote in Markdown, styled `<div>` in HTML).

### 11.5 Failure handling

API errors are caught; if summary generation fails, the category is rendered without a summary.

---

## 12. Bucket Limits

Default limits (overridable in `config.toml`):

| Category | Default max items |
|---|---|
| Switzerland & Bern | 8 |
| Poland | 8 |
| Europe | 8 |
| World | 8 |
| Tech | 10 |

---

## 13. Output Formats

### 13.1 Terminal (`--output terminal`, default)

Uses `rich` for colored, bold output. Terminal width defaults to 88 characters (configurable).

Structure:
```
━━━━━ (width chars) ━━━━━
  NEWS DIGEST  ·  <DayName, DD Month YYYY  HH:MM>
━━━━━ (width chars) ━━━━━

  ▌ <CATEGORY NAME>
  ───── (width chars) ─────

  <AI summary paragraph, italic>

  <n>. <title>   [sources: N]  [sentiment]
      [<source>]
      <wrapped summary (width-6, indent 6)>

━━━━━ (width chars) ━━━━━
```

Categories with zero items are omitted.

### 13.2 HTML (`--output html`)

Produces a self-contained HTML document with inline CSS. Suitable for use as an email newsletter body or static page. Structure: header section with date, one `<section>` per category, AI summary in a styled `<div>`, story list as `<ol>` with source and sentiment badge.

### 13.3 Markdown (`--output markdown`)

Produces standard GitHub-flavored Markdown. Structure: H1 title with date, H2 per category, AI summary as blockquote, numbered list of stories with bold title, source in backticks, sentiment in italics.

---

## 14. Email Delivery

### 14.1 Trigger

`--email` flag. Requires `[email]` section in `config.toml`.

### 14.2 Implementation

Uses Python `smtplib` with STARTTLS. The digest is first rendered in the selected `--output` mode, then the rendered string is sent as the email body (HTML or plain text depending on output mode).

### 14.3 Configuration keys

`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `from_address`, `to_addresses` (list).

---

## 15. Source Health Monitoring

### 15.1 Trigger

`--health` flag. Prints a report and exits without rendering the digest.

### 15.2 Report contents

For each configured source:

- Fetch status: OK / TIMEOUT / HTTP <code> / ERROR
- Item count returned
- Cache status: HIT / MISS
- Last fetched timestamp (from cache)

---

## 16. CLI Arguments

| Flag | Type | Default | Description |
|---|---|---|---|
| `--category` | str | (all) | Show only stories in this category |
| `--output` | str | `terminal` | Output mode: `terminal`, `html`, `markdown` |
| `--output-file` | path | stdout | Write output to file |
| `--email` | flag | off | Send via SMTP after rendering |
| `--no-cache` | flag | off | Skip SQLite cache |
| `--no-translate` | flag | off | Skip OpenAI translation |
| `--health` | flag | off | Print source health report and exit |
| `--config` | path | `config.toml` | Config file path |

---

## 17. Error Handling

- Per-feed async fetch errors: printed to stderr, feed skipped, zero items contributed
- Bluewin scrape failure: printed to stderr, no items from Bluewin
- Cache read/write errors: non-fatal; falls back to live fetch
- Language detection failure: defaults to `"en"`
- Translation failure: stderr, original items used unchanged
- AI summary failure: stderr, category rendered without summary
- Email send failure: stderr, digest still written to output-file or stdout if specified
- Missing `OPENAI_API_KEY`: translation silently skipped (no error)
- Missing `ANTHROPIC_API_KEY`: AI summaries silently skipped

---

## 18. External Dependencies

| Package | Purpose | Required |
|---|---|---|
| `aiohttp` | Async HTTP feed fetching | Yes |
| `feedparser` | RSS/Atom parsing | Yes |
| `rich` | Terminal color output | Yes |
| `langdetect` | Language detection | Yes |
| `anthropic` | Claude API for AI summaries | Yes |
| `requests` | Bluewin scraping, OpenAI API | Yes |
| `tomli` | TOML config parsing on Python < 3.11 | Python < 3.11 |
| `sqlite3` | Feed cache | stdlib |
| `smtplib` | Email delivery | stdlib |
| `asyncio` | Async event loop | stdlib |
| `argparse` | CLI argument parsing | stdlib |
