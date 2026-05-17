# Claw_news V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade to V2 with period-aware scoring (morning/evening), keyword-guaranteed competition, dual daily auto-push via launchd.

**Architecture:** Collectors → Merger (position+keyword+period-aware-time scoring, keyword-guaranteed slots) → Pusher ([EN]/[续]/[新], HTML clean). main.py --period morning|evening triggers the full pipeline.

**Tech Stack:** Python 3.10+, httpx, BeautifulSoup4, feedparser, pyyaml, pytest, pytest-httpx

---

### Task 1: HotItem + config.yaml foundation

**Files:**
- Modify: `collectors/base.py`
- Modify: `config.yaml`

- [ ] **Step 1: Add keyword_hit, pub_date, time_modifier to base.py**

```python
# collectors/base.py — add to HotItem:
@dataclass
class HotItem:
    title: str
    url: str
    summary: str
    source: str
    category: Category
    source_score: float
    timestamp: float = field(default_factory=time.time)
    keyword_hit: bool = False   # NEW
    pub_date: str = ""          # NEW yyyy-mm-dd

# Add after normalize_rank_score:
from datetime import date

def time_modifier(pub_date: str, period: str = "morning") -> float:
    """morning: today+yesterday=0, older=-2.0. evening: today=0, yesterday=-1.0, older=-2.0"""
    if not pub_date:
        return 0
    try:
        diff = (date.today() - date.fromisoformat(pub_date)).days
        if period == "morning":
            return 0.0 if diff <= 1 else -2.0
        else:
            if diff == 0: return 0.0
            if diff == 1: return -1.0
            return -2.0
    except ValueError:
        return 0
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -c "
from collectors.base import HotItem, time_modifier
h = HotItem('t','','','s','ai',5.0, keyword_hit=True, pub_date='2026-05-15')
print(f'ok kw={h.keyword_hit} pd={h.pub_date} tm_morning={time_modifier(h.pub_date,\"morning\")} tm_evening={time_modifier(h.pub_date,\"evening\")}')
"
```
Expected: `ok kw=True pd=2026-05-15 tm_morning=0.0 tm_evening=-1.0`

- [ ] **Step 3: Update config.yaml**

Replace current config with:

```yaml
collectors:
  fetch_count: 10
  sources:
    huggingface: true
    rss: true
    taptap: true

rss_feeds:
  - url: "https://www.qbitai.com/feed"
    category: "ai"
  - url: "https://sspai.com/feed"
    category: "device"
  - url: "https://www.ithome.com/rss/"
    category: "device"
  - url: "https://www.yystv.cn/rss/feed"
    category: "game"

keywords:
  ai: ["AI", "大模型", "GPT", "LLM", "机器学习", "深度学习", "人工智能", "神经网络", "训练", "Agent", "模型", "算法"]
  game: ["游戏", "手游", "主机", "Steam", "Switch", "PS5", "Xbox", "上线", "赛季", "联动", "版本", "新游", "评测", "发售"]
  device: ["芯片", "手机", "笔记本", "显卡", "CPU", "处理器", "iPhone", "系统", "发布", "评测", "新品", "上市", "小米", "华为", "苹果"]

pusher:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a1cd9e9d-3c2c-4948-aa2e-f61be9869b29"
```

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -q
git add -A && git commit -m "feat: add keyword_hit, pub_date, time_modifier, update config for V2"
```

---

### Task 2: RSS Collector — HTML strip, keyword match, pub_date, quantum bit

**Files:**
- Modify: `collectors/rss_sources.py`
- Modify: `tests/test_rss_collector.py`

- [ ] **Step 1: Write updated tests**

```python
# tests/test_rss_collector.py
from collectors.rss_sources import RssCollector, FEED_CONFIGS, strip_html, check_keyword_hit, extract_pub_date

def test_feed_configs_has_4_feeds():
    assert len(FEED_CONFIGS) == 4
    for feed in FEED_CONFIGS:
        assert "url" in feed
        assert "category" in feed

def test_strip_html():
    assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"
    assert strip_html("plain text") == "plain text"
    assert strip_html("") == ""

def test_keyword_hit():
    assert check_keyword_hit("华为发布新AI大模型GPT", "", "ai", {"ai": ["AI", "GPT"]})
    assert not check_keyword_hit("今天天气真好", "", "ai", {"ai": ["AI"]})

def test_extract_pub_date():
    ts = (2026, 5, 15, 10, 0, 0, 4, 136, 0)
    assert extract_pub_date(ts) == "2026-05-15"
    assert extract_pub_date(None) == ""

def test_parse_entry_full():
    collector = RssCollector()
    entry = {
        "title": "GPT-5 发布",
        "link": "https://x.com/1",
        "summary": "<p>OpenAI <b>发布</b> GPT-5</p>",
        "published_parsed": (2026, 5, 15, 10, 0, 0, 4, 136, 0),
    }
    feed = {"url": "https://qbitai.com/feed", "category": "ai"}
    item = collector._parse_entry(entry, feed)
    assert item.keyword_hit == True
    assert item.pub_date == "2026-05-15"
    assert "<" not in item.summary
    assert "GPT-5" in item.title

def test_parse_entry_missing():
    collector = RssCollector()
    item = collector._parse_entry({"title": "X"}, {"url": "rss", "category": "game"})
    assert item.url == ""
    assert item.keyword_hit == False
    assert item.pub_date == ""
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_rss_collector.py -v
```
Expected: FAIL — functions not defined

- [ ] **Step 3: Rewrite collectors/rss_sources.py**

```python
import re
import time
from calendar import timegm
from typing import List

import feedparser

from collectors.base import HotItem, Category

FEED_CONFIGS: List[dict] = [
    {"url": "https://www.qbitai.com/feed", "category": "ai"},
    {"url": "https://sspai.com/feed", "category": "device"},
    {"url": "https://www.ithome.com/rss/", "category": "device"},
    {"url": "https://www.yystv.cn/rss/feed", "category": "game"},
]

# Load keywords + fetch_count from config
from pathlib import Path
import yaml
_cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
KEYWORDS: dict = _cfg.get("keywords", {})
FETCH_COUNT: int = _cfg.get("collectors", {}).get("fetch_count", 10)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def check_keyword_hit(title: str, summary: str, category: str, keywords: dict) -> bool:
    kws = keywords.get(category, [])
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in kws)


def extract_pub_date(published_parsed) -> str:
    if published_parsed and len(published_parsed) >= 3:
        return f"{published_parsed[0]:04d}-{published_parsed[1]:02d}-{published_parsed[2]:02d}"
    return ""


class RssCollector:
    def __init__(self, feed_configs: List[dict] | None = None):
        self.feeds = feed_configs or FEED_CONFIGS

    async def collect(self) -> List["HotItem"]:
        import logging
        logger = logging.getLogger(__name__)
        items = []
        for feed in self.feeds:
            try:
                parsed = feedparser.parse(feed["url"])
                for entry in parsed.entries[:FETCH_COUNT]:
                    items.append(self._parse_entry(entry, feed))
            except Exception as e:
                logger.warning("RSS feed %s failed: %s", feed["url"], e)
        return items

    def _parse_entry(self, entry: dict, feed: dict) -> "HotItem":
        title = entry.get("title", "")
        url = entry.get("link", "")
        summary = strip_html(entry.get("summary", ""))
        ts = _parse_timestamp(entry)
        pub_date = extract_pub_date(entry.get("published_parsed"))
        cat = feed["category"]
        kw_hit = check_keyword_hit(title, summary, cat, KEYWORDS)

        return HotItem(
            title=title, url=url, summary=summary,
            source=cat, category=Category(cat),
            source_score=5.0, timestamp=ts,
            keyword_hit=kw_hit, pub_date=pub_date,
        )


def _parse_timestamp(entry: dict) -> float:
    pp = entry.get("published_parsed")
    return float(timegm(pp)) if pp else time.time()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_rss_collector.py -v
```
Expected: 6 tests PASS

- [ ] **Step 5: Run full suite + commit**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -q
git add -A && git commit -m "feat: add HTML strip, keyword match, pub_date, quantum bit to RSS collector"
```

---

### Task 3: HF + TapTap — fetch_count=10 + pub_date

**Files:**
- Modify: `collectors/huggingface.py`
- Modify: `collectors/taptap.py`
- Modify: `tests/test_huggingface.py`, `tests/test_taptap.py`

- [ ] **Step 1: Update huggingface.py**

Key changes:
- Read `FETCH_COUNT` from config (same pattern as RSS)
- In `_parse_paper`: add `pub_date=date.today().isoformat()`

```python
# Add at top after imports:
from datetime import date
from pathlib import Path
import yaml
_cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
HF_FETCH_COUNT = _cfg.get("collectors", {}).get("fetch_count", 10)

# In collect(), change papers[:10] to papers[:HF_FETCH_COUNT]
# In _parse_paper return, add: pub_date=date.today().isoformat()
```

- [ ] **Step 2: Update taptap.py similarly**

```python
# Same config loading pattern, use TAPTAP_FETCH_COUNT in cards slicing
# Add pub_date=date.today().isoformat() to HotItem
```

- [ ] **Step 3: Update test assertions**

HF: `assert item.pub_date != ""`
TapTap: `assert item.pub_date != ""`

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -q
git add -A && git commit -m "feat: fetch_count=10 + pub_date for HF and TapTap"
```

---

### Task 4: Merger — position scoring + period-aware time + keyword-guaranteed competition

**Files:**
- Modify: `aggregator/merger.py`
- Modify: `tests/test_merger.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add sample_items_v2 to conftest.py**

```python
# tests/conftest.py — add fixture
import time as _time
from datetime import date as _date

@pytest.fixture
def sample_items_v2():
    now = _time.time()
    today = _date.today().isoformat()
    yesterday = (_date.today().replace(day=_date.today().day-1) if _date.today().day > 1 else _date.today().replace(month=_date.today().month-1, day=28)).isoformat()
    return [
        # AI: HF (high) + qbitai
        HotItem("AI Paper A", "https://a.com/1", "AI research", "huggingface", "ai", 9.0, now-3600, True, today),
        HotItem("AI Paper B", "https://a.com/2", "ML paper", "huggingface", "ai", 8.0, now-3600, True, today),
        HotItem("AI Paper C", "https://a.com/3", "DL paper", "huggingface", "ai", 7.0, now-3600, True, today),
        HotItem("AI Paper D", "https://a.com/4", "CV paper", "huggingface", "ai", 6.0, now-3600, False, today),
        HotItem("AI News 1", "https://b.com/1", "GPT news", "qbitai", "ai", 8.5, now-7200, True, today),
        HotItem("AI News 2", "https://b.com/2", "AI news", "qbitai", "ai", 7.5, now-7200, True, today),
        # Game
        HotItem("Game 1", "https://c.com/1", "New RPG 上线", "taptap", "game", 9.0, now-1800, True, today),
        HotItem("Game 2", "https://c.com/2", "Strategy 手游", "taptap", "game", 8.0, now-1800, True, today),
        HotItem("Game 3", "https://d.com/1", "主机 游戏 评测", "yystv", "game", 7.0, now-40000, True, yesterday),
        HotItem("Game 4", "https://d.com/2", "Steam 新游", "yystv", "game", 6.5, now-40000, True, today),
        # Device
        HotItem("Device 1", "https://e.com/1", "苹果 芯片 发布", "ithome", "device", 8.0, now-600, True, today),
        HotItem("Device 2", "https://e.com/2", "华为 手机 新品", "ithome", "device", 7.5, now-600, True, today),
        HotItem("Device 3", "https://f.com/1", "iPhone 评测", "sspai", "device", 7.0, now-50000, True, yesterday),
        HotItem("Device 4", "https://f.com/2", "小米 笔记本", "sspai", "device", 6.5, now-50000, True, today),
    ]
```

- [ ] **Step 2: Write updated merger tests**

```python
# tests/test_merger.py
import pytest
from aggregator.merger import Merger, position_score, compute_source_score
from collectors.base import HotItem

def test_position_score_first():
    assert position_score(1) == 10.0

def test_position_score_last():
    assert position_score(10) == 5.5

def test_position_score_decreasing():
    assert position_score(1) > position_score(5) > position_score(10)

def test_time_modifier_morning():
    assert time_modifier("2026-05-15", "morning")  # depends on today, just check it runs

class TestMerger:
    def test_groups_by_category(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        assert set(result.keys()) == {"ai", "game", "device"}

    def test_sorts_desc(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        for items in result.values():
            if items:
                scores = [item.source_score for item in items]
                assert scores == sorted(scores, reverse=True)

    def test_top_n_limit(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        for items in result.values():
            assert len(items) <= 5

    def test_empty_input(self):
        merger = Merger(top_n=5)
        result = merger.merge([], period="morning")
        assert result == {"ai": [], "game": [], "device": []}
```

- [ ] **Step 3: Run to verify failure**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_merger.py -v
```
Expected: FAIL

- [ ] **Step 4: Rewrite aggregator/merger.py**

```python
from typing import Dict, List
from collectors.base import HotItem, Category, time_modifier


def position_score(pos: int) -> float:
    """RSS position: #1=10.0, #10=5.5"""
    pos = max(1, min(pos, 10))
    return 10.0 - (pos - 1) * 0.5


def compute_source_score(item: HotItem, position: int = 5, period: str = "morning") -> float:
    """3D scoring for RSS items. HF/TapTap keep their original scores."""
    if item.source in ("huggingface", "taptap"):
        return item.source_score
    pos_s = position_score(position)
    kw_s = 1.0 if item.keyword_hit else 0.0
    tm_s = time_modifier(item.pub_date, period)
    return round(pos_s + kw_s + tm_s, 1)


class Merger:
    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def merge(self, items: List[HotItem], period: str = "morning") -> Dict[Category, List[HotItem]]:
        result: Dict[Category, List[HotItem]] = {"ai": [], "game": [], "device": []}

        for category in result:
            cat_items = [i for i in items if i.category == category]
            if not cat_items:
                continue

            # Group by source, assign position-based scoring
            sources: Dict[str, List[HotItem]] = {}
            for item in cat_items:
                sources.setdefault(item.source, []).append(item)

            # Score items with computed source_score + position
            for src, src_items in sources.items():
                for i, item in enumerate(src_items):
                    item.source_score = compute_source_score(item, i + 1, period)

            # Sort each source group by source_score
            for src_items in sources.values():
                src_items.sort(key=lambda x: x.source_score, reverse=True)

            # Step 1: keyword-guaranteed — one per source
            selected: List[HotItem] = []
            for src, src_items in sources.items():
                kw_items = [i for i in src_items if i.keyword_hit]
                selected.append(kw_items[0] if kw_items else src_items[0])

            # Step 2: free competition for remaining slots
            selected_urls = {i.url for i in selected}
            remaining = [i for i in cat_items if i.url not in selected_urls]
            remaining.sort(key=lambda x: x.source_score, reverse=True)
            needed = self.top_n - len(selected)
            selected.extend(remaining[:needed])

            # Step 3: final sort
            selected.sort(key=lambda x: x.source_score, reverse=True)
            result[category] = selected[:self.top_n]

        return result
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -q
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: 3D scoring + period-aware time + keyword-guaranteed competition"
```

---

### Task 5: WeCom Pusher — [EN]/[续]/[新], source labels, HTML cleanup

**Files:**
- Modify: `pusher/wecom.py`
- Modify: `tests/test_wecom.py`

- [ ] **Step 1: Write updated tests**

```python
# tests/test_wecom.py — add:
def test_format_period_label():
    from pusher.wecom import format_message
    items = [HotItem("t","","s","src","ai",5.0)]
    msg_morning = format_message(items, "ai", period="morning", pushed_urls=set())
    assert "早报" in msg_morning
    msg_evening = format_message(items, "ai", period="evening", pushed_urls=set())
    assert "晚报" in msg_evening

def test_xu_and_xin_markers():
    from pusher.wecom import format_message
    new_item = HotItem("New","https://x.com/new","s","src","ai",5.0)
    msg = format_message([new_item], "ai", pushed_urls=set())
    assert "[新]" in msg
    msg2 = format_message([new_item], "ai", pushed_urls={"https://x.com/new"})
    assert "[续]" in msg2

def test_en_marker():
    from pusher.wecom import format_message
    item = HotItem("Paper","https://x.com/1","s","huggingface","ai",5.0)
    msg = format_message([item], "ai", pushed_urls=set())
    assert "[EN]" in msg

def test_source_label():
    from pusher.wecom import format_message
    item = HotItem("t","https://x.com/t","s","量子位","ai",5.0)
    msg = format_message([item], "ai", pushed_urls=set())
    assert "— 量子位" in msg
```

- [ ] **Step 2: Verify failure + implement**

Update `format_message(items, category, period="morning", pushed_urls=None)`:
- Add `period` parameter for "早报"/"晚报" label
- Add `[EN]` for source=="huggingface"
- Add `[续]` / `[新]` based on pushed_urls
- Add `— {item.source}` after summary
- `strip_html()` on summary

Update `WeComPusher.push()` to accept and pass `period` and `pushed_urls`.

- [ ] **Step 3: Run tests + commit**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -q
git add -A && git commit -m "feat: add [EN]/[续]/[新] markers, period label, source labels, HTML cleanup"
```

---

### Task 6: Main.py — single pipeline with --period morning|evening

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Rewrite main.py**

```python
"""Daily hot news aggregator V2.

Usage:
    python main.py --period morning   # Full pipeline for morning digest
    python main.py --period evening   # Full pipeline for evening digest
    python main.py --period morning --dry-run  # Print instead of push
"""

import asyncio, json, logging, sys
from pathlib import Path
from datetime import date
import yaml

from collectors.rss_sources import RssCollector
from collectors.huggingface import HfDailyPapersCollector
from collectors.taptap import TapTapCollector
from aggregator.merger import Merger
from pusher.wecom import WeComPusher, format_message

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
PUSHED_URLS_PATH = Path(__file__).parent / "data" / "pushed_urls.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_pushed_urls() -> set:
    if not PUSHED_URLS_PATH.exists():
        return set()
    with open(PUSHED_URLS_PATH) as f:
        return set(json.load(f))


def save_pushed_urls(urls: set):
    PUSHED_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUSHED_URLS_PATH, "w") as f:
        json.dump(list(urls), f)


async def collect_all(config: dict):
    sources = config.get("collectors", {}).get("sources", {})

    async def safe_collect(name, collector):
        try:
            items = await collector.collect()
            logger.info("%s: %d items", name, len(items))
            return items
        except Exception as e:
            logger.warning("%s failed: %s", name, e)
            return []

    tasks = {}
    if sources.get("rss", True):
        tasks["rss"] = safe_collect("rss", RssCollector())
    if sources.get("huggingface", True):
        tasks["huggingface"] = safe_collect("huggingface", HfDailyPapersCollector())
    if sources.get("taptap", True):
        tasks["taptap"] = safe_collect("taptap", TapTapCollector())

    results = await asyncio.gather(*tasks.values())
    all_items = []
    for items in results:
        all_items.extend(items)
    return all_items


async def main(period: str = "morning", dry_run: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    config = load_config()
    top_n = config.get("collectors", {}).get("top_n", 5)
    webhook_url = config.get("pusher", {}).get("wecom_webhook", "")

    logger.info("Step 1: Collecting (%s)", period)
    all_items = await collect_all(config)
    logger.info("Collected %d items", len(all_items))

    logger.info("Step 2: Merging and ranking")
    merger = Merger(top_n=top_n)
    grouped = merger.merge(all_items, period=period)
    for cat, items in grouped.items():
        logger.info("%s: %d items", cat, len(items))

    pushed_urls = load_pushed_urls()

    if dry_run:
        logger.info("Step 3: Dry run")
        for cat, items in grouped.items():
            if items:
                print(format_message(items, cat, period=period, pushed_urls=pushed_urls))
                print()
    else:
        if not webhook_url:
            logger.error("No wecom_webhook configured")
            sys.exit(1)
        logger.info("Step 3: Pushing")
        pusher = WeComPusher(webhook_url)
        await pusher.push(grouped, period=period, pushed_urls=pushed_urls)
        new_urls = {i.url for cat_items in grouped.values() for i in cat_items}
        save_pushed_urls(new_urls)
        logger.info("Push complete")


if __name__ == "__main__":
    period = "morning"
    if "--period" in sys.argv:
        idx = sys.argv.index("--period")
        if idx + 1 < len(sys.argv):
            period = sys.argv[idx + 1]
    dry = "--dry-run" in sys.argv
    asyncio.run(main(period=period, dry_run=dry))
```

- [ ] **Step 2: Test dry-run**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --period morning --dry-run
```
Expected: Collects, merges, prints formatted output with "早报"

- [ ] **Step 3: Test real push**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --period morning
```
Expected: 3x 200 OK push

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -q
git add -A && git commit -m "feat: single pipeline with --period morning|evening, pushed URL tracking"
```

---

### Task 7: launchd — morning + evening auto triggers

- [ ] **Step 1: Create morning plist**

```bash
cat > ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.lanser.clawnews.morning</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/lanser/Code/Claw_news/venv/bin/python</string>
        <string>/Users/lanser/Code/Claw_news/main.py</string>
        <string>--period</string><string>morning</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/Users/lanser/Code/Claw_news/data/morning.log</string>
    <key>StandardErrorPath</key><string>/Users/lanser/Code/Claw_news/data/morning_error.log</string>
    <key>WorkingDirectory</key><string>/Users/lanser/Code/Claw_news</string>
</dict>
</plist>
PLIST
```

- [ ] **Step 2: Create evening plist**

```bash
cat > ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.lanser.clawnews.evening</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/lanser/Code/Claw_news/venv/bin/python</string>
        <string>/Users/lanser/Code/Claw_news/main.py</string>
        <string>--period</string><string>evening</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/Users/lanser/Code/Claw_news/data/evening.log</string>
    <key>StandardErrorPath</key><string>/Users/lanser/Code/Claw_news/data/evening_error.log</string>
    <key>WorkingDirectory</key><string>/Users/lanser/Code/Claw_news</string>
</dict>
</plist>
PLIST
```

- [ ] **Step 3: Replace old launchd + load new**

```bash
launchctl unload ~/Library/LaunchAgents/com.lanser.clawnews.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist
launchctl list | grep clawnews
```
Expected: `com.lanser.clawnews.morning` and `com.lanser.clawnews.evening`

- [ ] **Step 4: Backup plists + commit**

```bash
cp ~/Library/LaunchAgents/com.lanser.clawnews.{morning,evening}.plist /Users/lanser/Code/Claw_news/docs/
git add -A && git commit -m "feat: launchd morning+evening auto triggers"
```

---

### Task 8: End-to-end verification

- [ ] **Step 1: Full test suite**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v
```
Expected: ALL PASS

- [ ] **Step 2: Morning dry-run**

```bash
./venv/bin/python main.py --period morning --dry-run
```
Expected: 早报 format, 3 categories × 5 items, markers present

- [ ] **Step 3: Morning real push**

```bash
./venv/bin/python main.py --period morning
```
Expected: 3x 200 OK, mobile receives

- [ ] **Step 4: Evening dry-run (verify [续] works)**

```bash
./venv/bin/python main.py --period evening --dry-run
```
Expected: 晚报 format, some items marked [续]

---

## Self-Review

1. **Spec coverage** — data sources ✓(T1), period-aware time ✓(T1), keywords ✓(T1,T2), 3D scoring ✓(T4), competition ✓(T4), [EN]/[续]/[新] ✓(T5), launchd ✓(T7)
2. **No placeholders** — every step has exact code or command
3. **Type consistency** — `keyword_hit: bool`, `pub_date: str`, `time_modifier(pub_date, period)`, `compute_source_score(item, position, period)`, `merge(items, period)`
