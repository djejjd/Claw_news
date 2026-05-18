# AI Source Expansion Design

## 1. Goal

Extend the unified AI digest pipeline in two bounded ways:

1. turn AI RSS ingestion from an effectively single-source path into a configurable multi-source path
2. add GitHub repositories as a supplemental digest section, without letting repository items compete with the core news TopN

This work must preserve the current service-first architecture and keep the existing news ranking model intact.

## 2. Current State

The formal ingest job currently runs:

1. `RssCollector()`
2. `HfDailyPapersCollector()`

`RssCollector()` has four built-in feeds, but only `qbitai` is tagged `category="ai"`. The publish path is intentionally `ai_only`, so `sspai` / `ithome` / `yystv` are filtered before entering the AI candidate pool. In practice, when HuggingFace is unreachable, the formal AI digest collapses to a single RSS source.

GitHub is not currently implemented as a collector. Task006 explicitly left “GitHub 热点正式接入” out of scope so the pipeline merge could land before adding a new source family.

## 3. Design Decision

### 3.1 AI RSS: defaults plus environment overrides

Introduce a dedicated AI RSS source configuration layer:

1. keep a small built-in default set so a fresh deployment is not single-source by default
2. allow `.env` configuration to append or fully override the built-in AI RSS set
3. require each configured AI RSS source to keep both:
   - a stable `source` name
   - an explicit `category="ai"`

Recommended public configuration shape:

```dotenv
AI_RSS_FEEDS=qbitai|https://www.qbitai.com/feed,openai_blog|https://openai.com/news/rss.xml
AI_RSS_MODE=append
```

Rules:

1. `AI_RSS_MODE=append` keeps built-ins and appends configured sources
2. `AI_RSS_MODE=replace` uses only configured sources
3. unknown or malformed entries are rejected at load time rather than silently producing anonymous feeds
4. legacy `NEWS_RSS_URLS` is not reused for this purpose because URL-only config loses `source` identity and category semantics

### 3.2 GitHub: supplemental section, not ranking competitor

Add a new `GitHubCollector` that fetches AI-relevant repositories from GitHub Search API and returns repository DTOs separate from `CandidateItem`.

Recommended first-pass query policy:

1. query topic-scoped AI repositories, such as `topic:llm`, `topic:artificial-intelligence`, and `topic:machine-learning`
2. sort by recent activity or stars through Search API parameters
3. keep a small capped result set
4. require enough repository metadata to render a useful digest row:
   - name
   - URL
   - description
   - stars
   - primary language

GitHub items do **not** enter `Merger(top_n=5)`. They become a separate supplemental section rendered after the main headline digest, for example:

```text
今日值得看项目
1. owner/repo — short description
```

This preserves the product meaning of the main digest: headline news remains news, GitHub remains a discovery appendix.

### 3.3 Pipeline shape

```text
High-frequency ingest
├─ AI RSS collectors -> CandidateItem pool
└─ GitHub collector   -> GitHub snapshot store

Publish pipeline
├─ AI Candidate pool -> classifier -> merger -> LLM -> headline digest
├─ GitHub snapshot   -> supplemental renderer input
└─ one WeCom markdown message containing both sections
```

The main digest remains one WeCom markdown message.

## 4. Data Model

### 4.1 AI RSS config

Use a small config DTO or helper result containing:

1. `source`
2. `url`
3. `category="ai"`

### 4.2 GitHub repository item

Introduce a dedicated repository model, separate from `CandidateItem`:

1. `full_name`
2. `url`
3. `description`
4. `stars`
5. `language`
6. `fetched_at`

Reason for separation: repository discovery is supplemental content, not a news article. Reusing `CandidateItem` would blur semantics and tempt future ranking shortcuts.

### 4.3 Persistence

Use a lightweight file-backed GitHub snapshot parallel to ingestion storage, for example:

```text
data/github/YYYY-MM-DD/repos.json
```

This keeps:

1. GitHub fetches decoupled from publish timing
2. GitHub data inspectable on the server
3. state model simple and aligned with the existing file-backed architecture

## 5. Failure Handling

1. AI RSS source failure remains local to that source
2. GitHub failure must not block the main AI digest
3. If GitHub snapshot is unavailable, publish the normal digest without the supplemental section
4. HuggingFace remains best-effort; blocked networks should degrade gracefully

## 6. Testing Strategy

1. AI RSS config parsing:
   - defaults only
   - append mode
   - replace mode
   - malformed config rejection
2. ingest coverage:
   - configured AI RSS sources enter the AI candidate pool
3. GitHub collector:
   - parses API payload into repo DTOs
   - tolerates empty and failed responses
4. rendering:
   - main digest unchanged when no GitHub items exist
   - supplemental GitHub section appears when items exist
5. publish behavior:
   - GitHub items never enter headline TopN selection
   - GitHub failure does not fail the main digest

## 7. Explicit Non-Goals

This iteration does not include:

1. GitHub Trending HTML scraping
2. repository README summarization
3. making GitHub repositories compete with news headlines
4. database-backed persistence
5. adding a broad content taxonomy beyond the current AI digest scope
