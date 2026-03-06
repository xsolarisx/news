# News Digest — Reverse-Engineered Specification

This document describes the behaviour of `news_digest.py` as observed from the source code.

---

## 1. Purpose

Produce a formatted, categorized news digest in the terminal by aggregating RSS feeds from Swiss, Polish, and international news sources. Non-English stories are optionally machine-translated.

---

## 2. Data Sources

### 2.1 RSS Feeds

Fetched via `feedparser`. Up to 40 entries are read per feed.

| Name | URL | Language |
|------|-----|----------|
| BBC | http://feeds.bbci.co.uk/news/rss.xml | EN |
| CNN | http://rss.cnn.com/rss/edition.rss | EN |
| Spiegel | https://www.spiegel.de/international/index.rss | EN |
| Wired | https://www.wired.com/feed/rss | EN |
| Hackaday | https://hackaday.com/feed/ | EN |
| BuzzFeed | https://www.buzzfeed.com/world.xml | EN |
| NZZ | https://www.nzz.ch/recent.rss | DE |
| NZZ-CH | https://www.nzz.ch/schweiz.rss | DE |
| NZZ-ZH | https://www.nzz.ch/zuerich.rss | DE |
| SRF | https://www.srf.ch/news/bnf/rss/1646 | DE |
| SRF-CH | https://www.srf.ch/news/bnf/rss/1890 | DE |
| 20min | https://partner-feeds.20min.ch/rss/20minuten | DE |
| 20min-CH | https://partner-feeds.20min.ch/rss/20minuten/schweiz | DE |
| Onet | https://wiadomosci.onet.pl/.feed | PL |
| TVN24 | https://tvn24.pl/najnowsze.xml | PL |
| RMF24 | https://www.rmf24.pl/feed | PL |

### 2.2 Scraped Source: Bluewin

- No public RSS feed exists for bluewin.ch
- Three sections are scraped: `/de/news/schweiz.html`, `/de/news/international.html`, `/de/news/wissen-technik.html`
- HTML is parsed with regex looking for `m-teaser-v2` / `data-t-name="Teaser"` blocks
- Title: last non-empty text chunk before the lead paragraph (>15 chars, not JSON)
- Summary: content of `m-teaser__lead` paragraph
- Intra-source deduplication: seen_titles set per scrape run

---

## 3. Item Representation

Each news item is a 3-tuple: `(source: str, title: str, summary: str)`

- `source`: feed name string (e.g., `"NZZ"`, `"BBC"`)
- `title`: HTML-stripped, non-empty
- `summary`: HTML-stripped, whitespace-normalized, truncated to 240 characters at a word boundary

---

## 4. Categorization

### 4.1 Categories (in display order)

1. Switzerland & Bern
2. Poland
3. Europe
4. World
5. Tech

### 4.2 Algorithm

- Concatenate `title + " " + summary`, lowercased
- For each category, test each keyword with `\b<keyword>\b` (whole-word regex)
- An item is assigned to **all** matching categories
- If no category matches → assigned to "World"

### 4.3 Keywords (abbreviated)

- **Switzerland & Bern**: switzerland, swiss, schweiz, bern, zurich, zürich, geneva, ubs, svp, …
- **Poland**: poland, polish, polska, warsaw, tusk, sejm, …
- **Europe**: europe, eu, nato, ukraine, germany, france, macron, scholz, …
- **World**: china, russia, iran, israel, trump, united nations, climate, war, …
- **Tech**: artificial intelligence, llm, openai, apple, google, cybersecurity, chip, …

---

## 5. Deduplication

Two-stage deduplication prevents showing the same story multiple times.

### 5.1 Stage 1 — Exact prefix match (global)

Key: first 7 lowercase title tokens joined by space.
Items with a matching key are skipped globally regardless of source.

### 5.2 Stage 2 — Semantic similarity (per category)

Jaccard similarity is computed between the content-word fingerprints of titles within the same category bucket.

- **Fingerprint**: set of non-stopword words (length > 2, after stripping punctuation)
- **Threshold**: 0.5 — if `|A ∩ B| / |A ∪ B| ≥ 0.5`, the new item is considered a duplicate within that category and is skipped
- This ensures the same story reported by BBC, CNN, and NZZ does not occupy 3 slots in a category

---

## 6. Bucket Limits

| Category | Max items |
|----------|-----------|
| Switzerland & Bern | 8 |
| Poland | 8 |
| Europe | 8 |
| World | 8 |
| Tech | 10 |

---

## 7. Translation

### 7.1 Trigger

Active only when `OPENAI_API_KEY` environment variable is non-empty.

### 7.2 Scope

Only items that make it into the final display buckets are translated (lazy — minimizes API cost).

### 7.3 Batch API call

- Endpoint: `POST https://api.openai.com/v1/chat/completions`
- Model: `gpt-4o-mini`
- Temperature: `0.1`
- Prompt: instructs translation of `title` and `summary` fields; proper nouns/place names preserved
- Input/output format: JSON array of `{id, title, summary}` objects
- IDs use `"<category>|<position>"` format for reassembly
- Markdown code fences in the response are stripped before JSON parsing

### 7.4 Source labelling

Translated items have their source renamed: `"NZZ"` → `"NZZ(DE→EN)"`.

### 7.5 Failure handling

Translation errors are printed to stderr; original (untranslated) items are used as fallback.

---

## 8. Output Format

Printed to stdout. Terminal width: 88 characters.

```
━━━ (88 chars) ━━━
  NEWS DIGEST  ·  <DayName, DD Month YYYY  HH:MM>
━━━ (88 chars) ━━━

  ▌ <CATEGORY NAME>
  ─── (88 chars) ───

  <n>. <title>
      [<source>]
      <wrapped summary (width 82, indent 6)>

━━━ (88 chars) ━━━
```

Categories with zero items are omitted from output.

---

## 9. Error Handling

- `feedparser` import failure → `sys.exit` with install instructions
- Per-feed fetch errors → printed to stderr, feed skipped
- Bluewin scrape failure → printed to stderr, no items from Bluewin
- Translation failure → stderr, original items used

---

## 10. External Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `feedparser` | RSS parsing | Yes |
| `requests` | HTTP (Bluewin scrape + OpenAI API) | Yes |
| `openai` SDK | Not used — raw `requests` to OpenAI API | N/A |

All other imports are Python standard library (`json`, `os`, `re`, `sys`, `textwrap`, `collections`, `datetime`, `html`).
