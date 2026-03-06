# News Digest

A command-line news aggregator that fetches RSS feeds from multiple international sources, categorizes stories, and optionally translates non-English content to English using the OpenAI API.

## Features

- Fetches from 15+ RSS feeds across Switzerland, Poland, Europe, and the World
- Scrapes Bluewin.ch (no public RSS) via HTML parsing
- Categorizes stories into: **Switzerland & Bern**, **Poland**, **Europe**, **World**, **Tech**
- Deduplicates stories both by exact title overlap and by semantic similarity (Jaccard) to avoid the same topic appearing multiple times from different sources
- Translates German and Polish articles to English via `gpt-4o-mini` (optional)
- Pretty terminal output with source attribution

## Requirements

```
pip install feedparser requests
```

Optional — for translation:
```
export OPENAI_API_KEY=sk-...
```

## Usage

```bash
python3 news_digest.py
```

## Sources

| Source | Language | Category focus |
|--------|----------|----------------|
| BBC, CNN, Spiegel International | English | World / Europe |
| Wired, Hackaday, BuzzFeed | English | Tech / World |
| NZZ, SRF, 20min | German (auto-translated) | Switzerland |
| Bluewin | German (auto-translated, scraped) | Switzerland |
| Onet, TVN24, RMF24 | Polish (auto-translated) | Poland |

## Configuration

Edit the constants at the top of `news_digest.py`:

| Constant | Default | Purpose |
|----------|---------|---------|
| `MAX_PER_CAT` | `8` | Max stories per category |
| `CAT_LIMITS` | `{"Tech": 10}` | Per-category overrides |
| `WIDTH` | `88` | Terminal output width |
| `SIMILARITY_THRESHOLD` | `0.5` | Jaccard similarity cutoff for dedup |

## Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  NEWS DIGEST  ·  Friday, 06 March 2026  14:30
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ▌ SWITZERLAND & BERN
  ────────────────────────────────────────────────────────────────────────────────────────

   1. Swiss parliament approves new energy legislation
      [NZZ(DE→EN)]
      The Swiss National Council voted 120 to 70 in favour of expanding solar...
```

## Notes

- `20min.ch` and `blue.news` direct RSS no longer work (JS-rendered / geo-blocked); partner feed URLs are used instead
- Bluewin scraping depends on their HTML structure and may break if they redesign the site
- Translation is performed only on items that make it into the final display buckets (cost-efficient)
