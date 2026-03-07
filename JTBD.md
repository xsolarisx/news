# Jobs to Be Done — News Digest

> Feature context: A self-hosted CLI tool that aggregates RSS feeds from 18+ international sources,
> deduplicates stories, translates non-English content, scores importance, tags sentiment,
> and delivers output as a terminal digest, HTML newsletter, or Markdown file on a daily schedule.

---

## Core Job Statement

**When** I start my day (or check in mid-day) and want to know what is happening in the world — specifically in Switzerland, Poland, Europe, tech, and global affairs —

**I want to** consume a concise, deduplicated, already-translated summary of the most important stories from sources I trust, without opening a browser, dismissing ads, or switching between 10 different apps,

**So I can** stay meaningfully informed in under five minutes and get on with my actual work.

---

## Job Map

### 1. Define — What do I need to understand first?
- Which topics matter to me today (Switzerland local, Poland, EU politics, tech, world)
- Which sources are credible and cover those topics
- How much time I have to read

### 2. Locate — What inputs and resources are needed?
- RSS feeds from trusted outlets in multiple languages
- A way to resolve language barriers (DE, PL → EN)
- A reliable runtime that runs without manual intervention

### 3. Prepare — How do I get ready?
- Confirm the tool is scheduled and running (systemd timer)
- Confirm API keys are in place for translation and AI summaries
- Confirm output is going somewhere accessible (HTML file, email, terminal)

### 4. Confirm — How do I verify readiness before consuming?
- Check source health report (`--health`) to see if any feeds are dead
- Know that deduplication has run — I won't see the same story 4 times from 4 sources
- Know that stories are ranked: cross-source coverage = higher importance

### 5. Execute — The core action
- Read the digest: scan category headers, read headlines, optionally read summaries
- Click through to full article only if something warrants deeper attention
- Spot the sentiment tag to gauge tone before reading

### 6. Monitor — How do I track progress?
- Timer fires twice daily; I know the digest is always fresh
- Source health report catches dead feeds before they silently drop a category
- `source_count` badge shows which stories are widely covered vs. single-source

### 7. Modify — How do I adjust?
- Filter to a single category (`--category Poland`) when I only have 2 minutes
- Disable translation temporarily (`--no-translate`) to save API cost
- Add or remove feeds via `config.toml` without touching source code
- Adjust `similarity_threshold` if too many or too few duplicates slip through

### 8. Conclude — How do I finish the job?
- Close terminal / browser tab with the digest
- Know I have not missed anything important
- Move on with my day without residual "did I miss something?" anxiety

---

## Context & Circumstances

### Functional
- Runs on a home Proxmox cluster — no cloud subscription, no tracking, no paywalls
- Must work unattended (systemd timer); no daily manual invocation
- Handles multilingual sources natively; German and Polish speakers in my network
- Output must be usable on any device: terminal on desktop, HTML on phone via browser

### Emotional
- Relief from information overload — curated, not firehose
- Confidence that the digest is objective (multiple sources, not one outlet's framing)
- Satisfaction of running a self-hosted tool rather than depending on a commercial aggregator
- Mild anxiety that something important could be missed — addressed by source health monitoring

### Social
- The digest is shareable (HTML, email mode) — can forward to family or colleagues
- Multi-country coverage reflects a cross-border lifestyle (CH + PL + EU)
- Tech category serves professional awareness needs alongside personal news

---

## Success Criteria

| Outcome | Target |
|---------|--------|
| Time to read digest | < 5 minutes |
| Stories per category | 8–10, deduplicated |
| Duplicate stories seen | 0 (same event from 2+ sources → 1 item with source count badge) |
| Fetch time | < 10 seconds (async, all feeds parallel) |
| Freshness | Max 30 minutes stale (cache TTL) |
| Language barrier | 0 — all non-EN content translated before display |
| Missed feed failures | 0 — health report flags dead sources |
| Manual daily effort | 0 — fully automated via systemd timer |

---

## Pain Points

### Before this tool existed
- **Tab sprawl**: opening NZZ, SRF, BBC, TVN24, Onet separately — 10+ browser tabs
- **Language switching**: reading DE and PL articles without translation layer
- **Duplicate noise**: the same Ukraine ceasefire story appearing on BBC, CNN, Spiegel, and SRF
- **No priority signal**: all headlines appear equal; no way to tell which story is broadly important vs. single-source
- **No schedule**: had to remember to check news; often forgot for a day, then caught up poorly

### Workarounds employed previously
- Google News — works, but: tracks behaviour, surfaces clickbait, no language preference control
- Feedly — requires account, limited free tier, no translation, no deduplication
- Reading each site manually — time-consuming, language-barrier friction
- RSS reader apps — fetch but don't deduplicate, translate, or score importance

### Unmet needs that remain partially open
- Sentiment analysis depth — keyword matching misses sarcasm and nuanced framing
- Topic clustering — stories are in categories but not grouped into named events ("Gaza ceasefire talks", "Swiss energy vote")
- Historical tracking — no way to follow a multi-day story across runs
- Mobile-native output — HTML works in browser but a dedicated mobile push would be better

---

## Competing Solutions

| Solution | Why it falls short |
|----------|--------------------|
| Google News | No self-hosting, behavioural tracking, no DE/PL translation control, ad-driven ranking |
| Apple News | Apple ecosystem only, no RSS control, no self-hosting |
| Feedly (free) | Limited feeds, no translation, no dedup, no terminal/HTML export |
| NewsBlur | Better RSS but no translation, no importance scoring, no self-hosting easy path |
| Manual browsing | Full control but 20–30 min/day, language friction, no dedup |
| Telegram news bots | Good for single sources, but no aggregation, no dedup, no importance scoring |
| Daily newsletter services (e.g. TLDR) | Curated by someone else, English-only, no Swiss/Polish coverage, no customisation |

---

## Related Jobs (Adjacent)

- **Share the digest** — forward today's HTML digest to a family member who doesn't speak German
- **Archive for reference** — save digests over time to track how a story evolved week-over-week
- **Brief a team** — use the AI executive summary per category as a team standup input
- **Monitor a topic** — run `--category Poland` before a call with Warsaw colleagues
