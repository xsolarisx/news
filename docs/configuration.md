# Configuration Reference — config.toml

All runtime settings for News Digest are controlled by a TOML file. The default path is `config.toml` in the working directory. Override it with `--config <path>`.

---

## Sections

- `[digest]` — core digest behaviour (limits, deduplication, caching)
- `[output]` — output formatting
- `[email]` — SMTP delivery
- `[ai]` — AI model settings
- `[[feeds]]` — feed list (array of tables)

---

## [digest]

Core digest behaviour settings.

| Key | Type | Default | Description |
|---|---|---|---|
| `max_per_cat` | integer | `8` | Maximum number of stories to show per category. Applies to all categories unless overridden by `cat_limits`. |
| `cat_limits` | table | `{Tech = 10}` | Per-category overrides for `max_per_cat`. Key is the category name (exact match), value is the integer limit. |
| `similarity_threshold` | float | `0.5` | Jaccard similarity threshold for within-category deduplication. Range 0.0–1.0. Lower values deduplicate more aggressively. |
| `cache_db` | string | `"cache.db"` | Path to the SQLite cache database file. Relative paths are resolved from the working directory. |
| `cache_ttl_seconds` | integer | `3600` | Time-to-live for cached feed responses in seconds. Feeds fetched within this window are served from cache. |
| `max_entries_per_feed` | integer | `40` | Maximum number of entries to read from each RSS feed. |
| `hn_top_n` | integer | `20` | Number of Hacker News top stories to fetch. |

---

## [output]

Controls rendering of the digest.

| Key | Type | Default | Description |
|---|---|---|---|
| `width` | integer | `88` | Character width for terminal output (affects separators and text wrapping). |
| `default_mode` | string | `"terminal"` | Default output mode when `--output` is not passed. One of: `terminal`, `html`, `markdown`. |
| `show_sentiment` | boolean | `true` | Whether to include sentiment tags (`[positive]` / `[neutral]` / `[negative]`) in the output. |
| `show_source_count` | boolean | `true` | Whether to show the `[sources: N]` importance label when a story is covered by more than one source. |
| `html_title` | string | `"News Digest"` | Title used in the HTML document `<title>` tag and top header. |

---

## [email]

SMTP delivery settings. Required only when using `--email`.

| Key | Type | Default | Description |
|---|---|---|---|
| `smtp_host` | string | (none) | SMTP server hostname. Example: `"smtp.gmail.com"`. |
| `smtp_port` | integer | `587` | SMTP port. Use `587` for STARTTLS, `465` for SSL. |
| `smtp_user` | string | (none) | SMTP authentication username. |
| `smtp_password` | string | (none) | SMTP authentication password. Consider storing this in `/etc/news-digest/env` instead of the config file. |
| `from_address` | string | (none) | Sender address shown in the `From:` header. |
| `to_addresses` | array of strings | `[]` | List of recipient email addresses. |
| `subject_prefix` | string | `"News Digest"` | Prefix prepended to the email subject. The final subject is `"<prefix> — <date>"`. |
| `use_tls` | boolean | `true` | Whether to use STARTTLS. Set to `false` only for local relay servers without TLS. |

---

## [ai]

Settings for OpenAI translation and Anthropic AI summaries.

| Key | Type | Default | Description |
|---|---|---|---|
| `openai_model` | string | `"gpt-4o-mini"` | OpenAI model used for batch translation. |
| `openai_temperature` | float | `0.1` | Sampling temperature for the translation model. Lower values produce more consistent output. |
| `anthropic_model` | string | `"claude-haiku-4-5-20251001"` | Anthropic model used for per-category executive summaries. |
| `summary_max_tokens` | integer | `256` | Maximum tokens for each AI-generated category summary. |
| `openai_api_key` | string | (env) | OpenAI API key. If set here, overrides the `OPENAI_API_KEY` environment variable. It is recommended to use the environment variable instead. |
| `anthropic_api_key` | string | (env) | Anthropic API key. If set here, overrides the `ANTHROPIC_API_KEY` environment variable. It is recommended to use the environment variable instead. |

---

## [[feeds]]

The feed list is expressed as an array of tables. Each `[[feeds]]` block defines one source. This section is optional; if omitted, the built-in default feed list is used. If any `[[feeds]]` blocks are present, they replace the entire default list.

Each feed entry supports:

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Short display name (e.g. `"NZZ"`, `"BBC"`). Shown in story attribution. |
| `url` | string | Yes | Full URL of the RSS/Atom feed. |
| `language` | string | No | ISO 639-1 language code (e.g. `"de"`, `"pl"`). If set, overrides language auto-detection. Used to determine whether translation is needed. |
| `category_hint` | string | No | Preferred category for stories from this source when keyword matching is ambiguous. Must match a category name exactly. |

---

## Complete Example config.toml

```toml
# News Digest — configuration file

[digest]
max_per_cat = 8
cat_limits = { Tech = 10, "Switzerland & Bern" = 10 }
similarity_threshold = 0.5
cache_db = "cache.db"
cache_ttl_seconds = 3600
max_entries_per_feed = 40
hn_top_n = 20

[output]
width = 88
default_mode = "terminal"
show_sentiment = true
show_source_count = true
html_title = "Morning News Digest"

[email]
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "user@example.com"
smtp_password = "app-password-here"
from_address = "digest@example.com"
to_addresses = ["alice@example.com", "bob@example.com"]
subject_prefix = "News Digest"
use_tls = true

[ai]
openai_model = "gpt-4o-mini"
openai_temperature = 0.1
anthropic_model = "claude-haiku-4-5-20251001"
summary_max_tokens = 256
# API keys are read from OPENAI_API_KEY and ANTHROPIC_API_KEY env vars by default.
# Uncomment only if you cannot use environment variables:
# openai_api_key = "sk-..."
# anthropic_api_key = "sk-ant-..."

[[feeds]]
name = "BBC"
url = "http://feeds.bbci.co.uk/news/rss.xml"
language = "en"

[[feeds]]
name = "CNN"
url = "http://rss.cnn.com/rss/edition.rss"
language = "en"

[[feeds]]
name = "Reuters"
url = "https://feeds.reuters.com/reuters/topNews"
language = "en"

[[feeds]]
name = "Spiegel"
url = "https://www.spiegel.de/international/index.rss"
language = "en"

[[feeds]]
name = "Wired"
url = "https://www.wired.com/feed/rss"
language = "en"

[[feeds]]
name = "Hackaday"
url = "https://hackaday.com/feed/"
language = "en"

[[feeds]]
name = "Ars Technica"
url = "https://feeds.arstechnica.com/arstechnica/index"
language = "en"

[[feeds]]
name = "NZZ"
url = "https://www.nzz.ch/recent.rss"
language = "de"

[[feeds]]
name = "NZZ-CH"
url = "https://www.nzz.ch/schweiz.rss"
language = "de"
category_hint = "Switzerland & Bern"

[[feeds]]
name = "NZZ-ZH"
url = "https://www.nzz.ch/zuerich.rss"
language = "de"
category_hint = "Switzerland & Bern"

[[feeds]]
name = "SRF"
url = "https://www.srf.ch/news/bnf/rss/1646"
language = "de"

[[feeds]]
name = "SRF-CH"
url = "https://www.srf.ch/news/bnf/rss/1890"
language = "de"
category_hint = "Switzerland & Bern"

[[feeds]]
name = "20min"
url = "https://partner-feeds.20min.ch/rss/20minuten"
language = "de"

[[feeds]]
name = "20min-CH"
url = "https://partner-feeds.20min.ch/rss/20minuten/schweiz"
language = "de"
category_hint = "Switzerland & Bern"

[[feeds]]
name = "Blick"
url = "https://www.blick.ch/news/rss.xml"
language = "de"

[[feeds]]
name = "Onet"
url = "https://wiadomosci.onet.pl/.feed"
language = "pl"

[[feeds]]
name = "TVN24"
url = "https://tvn24.pl/najnowsze.xml"
language = "pl"

[[feeds]]
name = "RMF24"
url = "https://www.rmf24.pl/feed"
language = "pl"
```

---

## Notes

- Boolean values in TOML are lowercase: `true` / `false`.
- String values must be quoted.
- `to_addresses` must be a TOML array even if there is only one address: `["user@example.com"]`.
- Sensitive values (`smtp_password`, API keys) should be stored in `/etc/news-digest/env` and loaded as environment variables rather than written into `config.toml`, especially in shared or version-controlled environments.
- If `[[feeds]]` blocks are present in the config, they fully replace the built-in default feed list. To add a feed to the defaults, you must reproduce the full default list plus your addition.
