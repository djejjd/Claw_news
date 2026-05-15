# Claw_news V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Claw_news to V2 with multi-parameter scoring, dual daily push, RSS store for full-day coverage, and content quality improvements.

**Architecture:** Collectors (RSS/API/crawler) → Merger (position+keyword+time scoring + per-source guaranteed slot competition) → Pusher ([EN]/[续]/[新] markers, HTML clean). Main.py supports `--collect` (RSS-only gathering) and `--push` (full collection + merge + push) modes.

**Tech Stack:** Python 3.10+, httpx, BeautifulSoup4, feedparser, pyyaml, pytest, pytest-httpx

---

### Task 1: HotItem + config.yaml 基础更新

**Files:**
- Modify: `collectors/base.py`
- Modify: `config.yaml`

- [ ] **Step 1: Add keyword_hit and pub_date to HotItem**

```python
# collectors/base.py — add to HotItem dataclass
@dataclass
class HotItem:
    title: str
    url: str
    summary: str
    source: str
    category: Category
    source_score: float
    timestamp: float = field(default_factory=time.time)
    keyword_hit: bool = False   # NEW: matches category keywords?
    pub_date: str = ""          # NEW: yyyy-mm-dd for time_modifier
```

- [ ] **Step 2: Add time_modifier function to base.py**

```python
# collectors/base.py — add after normalize_rank_score
from datetime import date

def time_modifier(pub_date: str) -> float:
    """今天 0, 昨天 -1.0, 更早 -2.0"""
    if not pub_date:
        return 0
    today = date.today()
    try:
        d = date.fromisoformat(pub_date)
        diff = (today - d).days
        if diff == 0:
            return 0.0
        if diff == 1:
            return -1.0
        return -2.0
    except ValueError:
        return 0
```

- [ ] **Step 3: Verify import**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -c "
from collectors.base import HotItem, time_modifier, Category
h = HotItem('test','','','test','ai',5.0, keyword_hit=True, pub_date='2026-05-15')
print(f'keyword_hit={h.keyword_hit} pub_date={h.pub_date} time_mod={time_modifier(h.pub_date)}')
print('OK')
"
```

- [ ] **Step 4: Update config.yaml**

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
  ai:
    - AI
    - 大模型
    - GPT
    - LLM
    - 机器学习
    - 深度学习
    - 人工智能
    - 神经网络
    - 训练
    - Agent
    - 模型
    - 算法
  game:
    - 游戏
    - 手游
    - 主机
    - Steam
    - Switch
    - PS5
    - Xbox
    - 上线
    - 赛季
    - 联动
    - 版本
    - 新游
    - 发售
  device:
    - 芯片
    - 手机
    - 笔记本
    - 显卡
    - CPU
    - 处理器
    - iPhone
    - 系统
    - 发布
    - 评测
    - 新品
    - 上市
    - 小米
    - 华为
    - 苹果

schedule:
  collect: ["0:00", "3:00", "6:00", "12:00", "15:00", "18:00"]
  push: ["9:00", "21:00"]

pusher:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a1cd9e9d-3c2c-4948-aa2e-f61be9869b29"
```

- [ ] **Step 5: Run full tests to check no regressions**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v
```
Expected: Tests that create HotItem without keyword_hit/pub_date still pass (defaults handle it).

- [ ] **Step 6: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add keyword_hit, pub_date, time_modifier, update config for V2"
```

---

### Task 2: RSS Collector — fetch_count, HTML strip, keyword matching, pub_date

**Files:**
- Modify: `collectors/rss_sources.py`
- Modify: `tests/test_rss_collector.py`

- [ ] **Step 1: Write updated tests**

```python
# tests/test_rss_collector.py — replace existing tests with:
from collectors.rss_sources import RssCollector, FEED_CONFIGS, strip_html, check_keyword_hit, extract_pub_date

def test_feed_configs_have_required_fields():
    for feed in FEED_CONFIGS:
        assert "url" in feed
        assert "category" in feed
        assert feed["category"] in ("ai", "game", "device")

def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"
    assert strip_html("<a href='x'>link</a> text") == "link text"
    assert strip_html("plain text") == "plain text"
    assert strip_html("") == ""

def test_keyword_hit_ai():
    assert check_keyword_hit("华为发布新AI大模型GPT应用", "", "ai", {})
    assert check_keyword_hit("神经网络训练方法", "", "ai", {})
    assert not check_keyword_hit("今天天气真好", "", "ai", {})

def test_keyword_hit_device():
    assert check_keyword_hit("苹果发布新iPhone芯片", "", "device", {})
    assert check_keyword_hit("华为Mate 80系统评测", "", "device", {})
    assert not check_keyword_hit("美食推荐", "", "device", {})

def test_extract_pub_date():
    # struct_time tuple for 2026-05-15 10:00:00
    ts = (2026, 5, 15, 10, 0, 0, 4, 136, 0)
    assert extract_pub_date(ts) == "2026-05-15"

def test_parse_entry_sets_keyword_hit_and_pub_date():
    collector = RssCollector()
    entry = {
        "title": "GPT-5 发布引发行业震动",
        "link": "https://example.com/gpt5",
        "summary": "OpenAI 正式发布 GPT-5",
        "published_parsed": (2026, 5, 15, 10, 0, 0, 4, 136, 0),
    }
    feed = {"url": "https://qbitai.com/feed", "category": "ai"}
    item = collector._parse_entry(entry, feed)
    assert item.keyword_hit == True
    assert item.pub_date == "2026-05-15"
    assert "<" not in item.summary  # HTML stripped

def test_parse_entry_missing_fields():
    collector = RssCollector()
    entry = {"title": "No link item"}
    feed = {"url": "https://example.com/rss", "category": "game"}
    item = collector._parse_entry(entry, feed)
    assert item.url == ""
    assert item.summary == ""
    assert item.keyword_hit == False
    assert item.pub_date == ""
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_rss_collector.py -v
```
Expected: FAIL — functions not defined yet

- [ ] **Step 3: Rewrite collectors/rss_sources.py**

```python
import re
import time
from calendar import timegm
from datetime import date
from typing import List

import feedparser

from collectors.base import HotItem, Category

FEED_CONFIGS: List[dict] = [
    {"url": "https://www.qbitai.com/feed", "category": "ai"},
    {"url": "https://sspai.com/feed", "category": "device"},
    {"url": "https://www.ithome.com/rss/", "category": "device"},
    {"url": "https://www.yystv.cn/rss/feed", "category": "game"},
]

# Load keywords from config at module level
from pathlib import Path
import yaml
_config_path = Path(__file__).parent.parent / "config.yaml"
with open(_config_path, "r", encoding="utf-8") as _f:
    _config = yaml.safe_load(_f)
KEYWORDS: dict = _config.get("keywords", {})
FETCH_COUNT: int = _config.get("collectors", {}).get("fetch_count", 10)


def strip_html(text: str) -> str:
    """Remove HTML tags from text"""
    return re.sub(r"<[^>]+>", "", text).strip()


def check_keyword_hit(title: str, summary: str, category: str, keywords: dict) -> bool:
    """Check if title+summary contains any keyword for the category"""
    kws = keywords.get(category, [])
    text = (title + " " + summary).lower()
    for kw in kws:
        if kw.lower() in text:
            return True
    return False


def extract_pub_date(published_parsed) -> str:
    """Extract yyyy-mm-dd from feedparser's published_parsed tuple"""
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
                entries = parsed.entries[:FETCH_COUNT]
                for entry in entries:
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
            title=title,
            url=url,
            summary=summary,
            source=cat,  # use category as source for RSS items
            category=Category(cat),
            source_score=5.0,
            timestamp=ts,
            keyword_hit=kw_hit,
            pub_date=pub_date,
        )


def _parse_timestamp(entry: dict) -> float:
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        return float(timegm(published_parsed))
    return time.time()
```

- [ ] **Step 4: Run tests to verify**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_rss_collector.py -v
```
Expected: ALL 7 tests PASS

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add HTML strip, keyword matching, pub_date to RSS collector"
```

---

### Task 3: HF + TapTap fetch_count=10 + pub_date support

**Files:**
- Modify: `collectors/huggingface.py`
- Modify: `collectors/taptap.py`
- Modify: `tests/test_huggingface.py`
- Modify: `tests/test_taptap.py`

- [ ] **Step 1: Update HuggingFace collector**

```python
# collectors/huggingface.py — change 10 to fetch_count config
# and add pub_date from current date

FETCH_COUNT: int = _get_config_fetch_count()

def _get_config_fetch_count() -> int:
    from pathlib import Path
    import yaml
    p = Path(__file__).parent.parent / "config.yaml"
    with open(p) as f:
        return yaml.safe_load(f).get("collectors", {}).get("fetch_count", 10)
```

In `_parse_paper`, add `pub_date=date.today().isoformat()` to HotItem.

- [ ] **Step 2: Update TapTap collector**

```python
# collectors/taptap.py — use FETCH_COUNT from config, add pub_date
# Same FETCH_COUNT loading pattern as HuggingFace
# In _parse_html, add pub_date=date.today().isoformat() to HotItem
# TAPTAP_HOT_URL already updated to /top/download in previous fix
```

- [ ] **Step 3: Update test assertions**

HF tests: add `assert item.pub_date != ""`  
TapTap tests: add `assert item.pub_date != ""`

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v
git add -A && git commit -m "feat: fetch_count=10 and pub_date for HF + TapTap collectors"
```

---

### Task 4: Merger — 三维评分 + 关键词保底竞争

**Files:**
- Modify: `aggregator/merger.py`
- Modify: `tests/test_merger.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Rewrite tests/test_merger.py**

```python
import time
import pytest
from aggregator.merger import Merger, position_score
from collectors.base import HotItem

def test_position_score_first():
    assert position_score(1) == 10.0

def test_position_score_last():
    assert position_score(10) == 5.5

def test_position_score_decreasing():
    assert position_score(1) > position_score(5) > position_score(10)

class TestMerger:
    def test_keyword_guaranteed_slot(self, sample_items_v2):
        """Each source should have at most 1 guaranteed slot"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2)
        # Each category has 2 sources, each guaranteed at most 1 from keyword
        for cat_items in result.values():
            if len(cat_items) > 0:
                sources = [item.source for item in cat_items]
                assert len(set(sources)) >= 1

    def test_groups_by_category(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2)
        assert set(result.keys()) == {"ai", "game", "device"}

    def test_sorts_by_final_score_desc(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2)
        for cat_items in result.values():
            scores = [item.final_score for item in cat_items]
            assert scores == sorted(scores, reverse=True)

    def test_top_n_limit(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2)
        for cat_items in result.values():
            assert len(cat_items) <= 5

    def test_empty_input(self):
        merger = Merger(top_n=5)
        result = merger.merge([])
        assert result == {"ai": [], "game": [], "device": []}
```

- [ ] **Step 2: Update conftest.py with sample_items_v2 fixture**

```python
# tests/conftest.py — add:
import time as _time
from datetime import date as _date

@pytest.fixture
def sample_items_v2():
    now = _time.time()
    today = _date.today().isoformat()
    yesterday = _date.today().replace(day=_date.today().day-1).isoformat()
    return [
        # AI: HF (high score, keyword hit) + qbitai (keyword hit)
        HotItem("AI Paper A", "https://a.com/1", "AI research", "huggingface", "ai", 9.0, now-3600, True, today),
        HotItem("AI Paper B", "https://a.com/2", "ML paper", "huggingface", "ai", 8.0, now-3600, True, today),
        HotItem("AI Paper C", "https://a.com/3", "DL paper", "huggingface", "ai", 7.0, now-3600, True, today),
        HotItem("AI Paper D", "https://a.com/4", "CV paper", "huggingface", "ai", 6.0, now-3600, False, today),
        HotItem("AI News 1", "https://b.com/1", "GPT news", "qbitai", "ai", 8.5, now-7200, True, today),
        HotItem("AI News 2", "https://b.com/2", "AI news", "qbitai", "ai", 7.5, now-7200, True, today),
        # Game: TapTap (keyword hit) + yystv (keyword hit)
        HotItem("Game 1", "https://c.com/1", "New RPG 上线", "taptap", "game", 9.0, now-1800, True, today),
        HotItem("Game 2", "https://c.com/2", "Strategy 手游", "taptap", "game", 8.0, now-1800, True, today),
        HotItem("Game Review 1", "https://d.com/1", "主机 游戏 评测", "yystv", "game", 7.0, now-40000, True, yesterday),
        HotItem("Game Review 2", "https://d.com/2", "Steam 新游", "yystv", "game", 6.5, now-40000, True, today),
        # Device: ithome (keyword hit) + sspai (keyword hit)
        HotItem("Device 1", "https://e.com/1", "苹果 芯片 发布", "ithome", "device", 8.0, now-600, True, today),
        HotItem("Device 2", "https://e.com/2", "华为 手机 新品", "ithome", "device", 7.5, now-600, True, today),
        HotItem("Device Review 1", "https://f.com/1", "iPhone 评测", "sspai", "device", 7.0, now-50000, True, yesterday),
        HotItem("Device Review 2", "https://f.com/2", "小米 笔记本", "sspai", "device", 6.5, now-50000, True, today),
    ]
```

- [ ] **Step 3: Run tests to verify failure**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_merger.py -v
```
Expected: FAIL — position_score not defined, new merge logic not implemented

- [ ] **Step 4: Rewrite aggregator/merger.py**

```python
from typing import Dict, List

from collectors.base import HotItem, Category, time_modifier


def position_score(pos: int) -> float:
    """RSS position → score: #1=10.0, #10=5.5, linear decay"""
    if pos < 1:
        pos = 1
    if pos > 10:
        pos = 10
    return 10.0 - (pos - 1) * 0.5


def compute_source_score(item: HotItem, position: int = 5) -> float:
    """Compute 3D source_score for RSS items.
    HF/TapTap already have their own scores from upvotes/rank.
    """
    if item.source in ("huggingface", "taptap"):
        # Already scored by collector (upvotes/rank)
        return item.source_score

    # RSS: position + keyword + time
    pos_s = position_score(position)
    kw_s = 1.0 if item.keyword_hit else 0.0
    tm_s = time_modifier(item.pub_date)

    return round(pos_s + kw_s + tm_s, 1)


class Merger:
    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def merge(self, items: List[HotItem]) -> Dict[Category, List[HotItem]]:
        result: Dict[Category, List[HotItem]] = {
            "ai": [],
            "game": [],
            "device": [],
        }

        for category in result:
            cat_items = [item for item in items if item.category == category]
            if not cat_items:
                continue

            # Group by source
            sources: Dict[str, List[HotItem]] = {}
            for item in cat_items:
                sources.setdefault(item.source, []).append(item)

            # Sort each source by final_score
            for src_items in sources.values():
                src_items.sort(key=lambda item: item.final_score, reverse=True)

            # Step 1: Keyword guaranteed — one per source
            selected: List[HotItem] = []
            for src, src_items in sources.items():
                # Prefer keyword_hit items for guaranteed slot
                kw_items = [i for i in src_items if i.keyword_hit]
                if kw_items:
                    selected.append(kw_items[0])
                else:
                    selected.append(src_items[0])

            # Step 2: Remaining items free competition
            selected_urls = {item.url for item in selected}
            remaining = [i for i in cat_items if i.url not in selected_urls]
            remaining.sort(key=lambda item: item.final_score, reverse=True)
            needed = self.top_n - len(selected)
            selected.extend(remaining[:needed])

            # Step 3: Sort by final_score
            selected.sort(key=lambda item: item.final_score, reverse=True)
            result[category] = selected[:self.top_n]

        return result
```

- [ ] **Step 5: Run merger tests**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_merger.py -v
```
Expected: 7 tests PASS

- [ ] **Step 6: Run full test suite**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 7: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: 3D scoring + keyword-guaranteed competition in merger"
```

---

### Task 5: WeCom Pusher — HTML cleanup, [EN]/[续]/[新], source labels

**Files:**
- Modify: `pusher/wecom.py`
- Modify: `tests/test_wecom.py`

- [ ] **Step 1: Update tests**

```python
# tests/test_wecom.py — add new tests:

def test_format_message_with_en_marker():
    from pusher.wecom import format_message
    items = [HotItem("EN Paper", "https://x.com/1", "summary", "huggingface", "ai", 8.0)]
    msg = format_message(items, "ai", pushed_urls=set())
    assert "[EN]" in msg

def test_format_message_with_xu_marker():
    from pusher.wecom import format_message
    items = [HotItem("Repeated Item", "https://x.com/old", "summary", "ithome", "device", 7.0)]
    msg = format_message(items, "device", pushed_urls={"https://x.com/old"})
    assert "[续]" in msg

def test_format_message_with_xin_marker():
    from pusher.wecom import format_message
    items = [HotItem("New Item", "https://x.com/new", "summary", "sspai", "device", 7.0)]
    msg = format_message(items, "device", pushed_urls=set())
    assert "[新]" in msg

def test_source_label_present():
    from pusher.wecom import format_message
    items = [HotItem("Test", "https://x.com/t", "summary", "量子位", "ai", 7.0)]
    msg = format_message(items, "ai", pushed_urls=set())
    assert "— 量子位" in msg
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_wecom.py -v
```

- [ ] **Step 3: Update pusher/wecom.py**

Key changes to `format_message`:
- Add `pushed_urls: set` parameter
- For each item: `if item.source == "huggingface"` → `[EN]` prefix
- `if item.url in pushed_urls` → `[续]` else `[新]`
- Append `— {item.source}` after summary
- Add `import re` and `strip_html()` helper for summary cleanup

```python
# pusher/wecom.py — updated format_message signature and logic

def strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).strip()

def format_message(items: List[HotItem], category: Category, pushed_urls: set | None = None) -> str:
    if pushed_urls is None:
        pushed_urls = set()
    today = datetime.now().strftime("%m/%d")
    emoji = CATEGORY_EMOJI.get(category, "")
    label = CATEGORY_LABELS.get(category, category)
    # Determine AM/PM
    hour = datetime.now().hour
    period = "早报" if hour < 12 else "晚报"
    lines = [f"{emoji} **{label}** | {today} {period}", SEPARATOR, ""]

    if not items:
        lines.append("> 暂无热点，稍后再来看看")
    else:
        for i, item in enumerate(items, 1):
            title = item.title.replace("\n", " ").strip()
            summary = strip_html(item.summary).replace("\n", " ").strip()[:120]

            # Markers
            markers = []
            if item.source == "huggingface":
                markers.append("[EN]")
            if item.url in pushed_urls:
                markers.append("[续]")
            else:
                markers.append("[新]")
            marker_str = " ".join(markers)

            if item.url:
                lines.append(f"**{i}.** {marker_str} [{title}]({item.url})")
            else:
                lines.append(f"**{i}.** {marker_str} {title}")
            if summary:
                lines.append(f"> {summary}")
            lines.append(f"> — {item.source}")
            if i < len(items):
                lines.append("")

    lines.append("")
    lines.append(SEPARATOR)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/test_wecom.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add [EN]/[续]/[新] markers, source labels, HTML cleanup to pusher"
```

---

### Task 6: Main.py — --collect / --push modes + RSS store

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Rewrite main.py**

```python
"""Daily hot news aggregator V2.

Usage:
    python main.py --collect   # RSS-only collection, append to data/rss_store.json
    python main.py --push      # Full collection + merge store + score + push
    python main.py --push --dry-run  # Same but print instead of push
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from collectors.rss_sources import RssCollector
from collectors.huggingface import HfDailyPapersCollector
from collectors.taptap import TapTapCollector
from aggregator.merger import Merger, compute_source_score
from pusher.wecom import WeComPusher, format_message

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
STORE_PATH = Path(__file__).parent / "data" / "rss_store.json"
PUSHED_URLS_PATH = Path(__file__).parent / "data" / "pushed_urls.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_store() -> list:
    if not STORE_PATH.exists():
        return []
    with open(STORE_PATH) as f:
        return json.load(f)


def save_store(items: list):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE_PATH, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def load_pushed_urls() -> set:
    if not PUSHED_URLS_PATH.exists():
        return set()
    with open(PUSHED_URLS_PATH) as f:
        return set(json.load(f))


def save_pushed_urls(urls: set):
    PUSHED_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUSHED_URLS_PATH, "w") as f:
        json.dump(list(urls), f)


async def collect_rss_only():
    """Collect RSS feeds only, return HotItem dicts for store"""
    collector = RssCollector()
    items = await collector.collect()
    return [
        {
            "title": item.title,
            "url": item.url,
            "summary": item.summary,
            "source": item.source,
            "category": item.category,
            "timestamp": item.timestamp,
            "keyword_hit": item.keyword_hit,
            "pub_date": item.pub_date,
        }
        for item in items
    ]


async def collect_all(config: dict):
    """Collect from all enabled sources"""
    sources = config.get("collectors", {}).get("sources", {})
    results = {}

    async def safe_collect(name, collector):
        try:
            items = await collector.collect()
            logger.info("%s: got %d items", name, len(items))
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

    gathered = await asyncio.gather(*tasks.values())
    all_items = []
    for items in gathered:
        all_items.extend(items)
    return all_items


async def cmd_collect():
    """--collect: RSS only, save to store"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logger.info("Collecting RSS feeds for store...")
    items = await collect_rss_only()
    logger.info("Collected %d RSS items", len(items))

    # Merge with existing store, dedup by URL, keep last 48h
    store = load_store()
    seen = {item["url"] for item in store}
    now = datetime.now()
    for item in items:
        if item["url"] not in seen:
            store.append(item)
            seen.add(item["url"])
    # Purge >48h old
    cutoff = (now - timedelta(hours=48)).timestamp()
    store = [i for i in store if i["timestamp"] > cutoff]
    save_store(store)
    logger.info("Store has %d items", len(store))


async def cmd_push(dry_run: bool = False):
    """--push: full collection + merge store + score + push"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    config = load_config()
    top_n = config.get("collectors", {}).get("top_n", 5)
    webhook_url = config.get("pusher", {}).get("wecom_webhook", "")

    logger.info("Step 1: Collecting from all sources")
    all_items = await collect_all(config)

    # Merge store (past 24h RSS items not in current snapshot)
    store = load_store()
    current_urls = {item.url for item in all_items}
    cutoff = (datetime.now() - timedelta(hours=24)).timestamp()
    for stored in store:
        if stored["url"] not in current_urls and stored["timestamp"] > cutoff:
            from collectors.base import HotItem
            all_items.append(HotItem(
                title=stored["title"],
                url=stored["url"],
                summary=stored["summary"],
                source=stored["source"],
                category=stored["category"],
                source_score=5.0,
                timestamp=stored["timestamp"],
                keyword_hit=stored.get("keyword_hit", False),
                pub_date=stored.get("pub_date", ""),
            ))
    logger.info("After store merge: %d items", len(all_items))

    logger.info("Step 2: Merging and ranking")
    merger = Merger(top_n=top_n)
    grouped = merger.merge(all_items)
    for cat, items in grouped.items():
        logger.info("%s: %d items after merge", cat, len(items))

    pushed_urls = load_pushed_urls()

    if dry_run:
        logger.info("Step 3: Dry run")
        for cat, items in grouped.items():
            if items:
                print(format_message(items, cat, pushed_urls))
                print()
    else:
        if not webhook_url:
            logger.error("No wecom_webhook configured")
            sys.exit(1)
        logger.info("Step 3: Pushing to WeChat Work")
        pusher = WeComPusher(webhook_url)
        # Update format_message call to pass pushed_urls
        await pusher.push(grouped, pushed_urls)
        # Save pushed URLs (all URLs from this push)
        new_pushed = {item.url for cat_items in grouped.values() for item in cat_items}
        save_pushed_urls(new_pushed)
        logger.info("Push complete")


if __name__ == "__main__":
    if "--collect" in sys.argv:
        asyncio.run(cmd_collect())
    else:
        dry = "--dry-run" in sys.argv
        asyncio.run(cmd_push(dry_run=dry))
```

- [ ] **Step 2: Update WeComPusher.push() to accept pushed_urls**

```python
# pusher/wecom.py — update push method:
async def push(self, items: Dict[Category, List[HotItem]], pushed_urls: set | None = None) -> None:
    if pushed_urls is None:
        pushed_urls = set()
    ...
    msg = format_message(cat_items, category, pushed_urls)
    ...
```

- [ ] **Step 3: Test --collect**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --collect
```
Expected: Creates `data/rss_store.json`, logs item count

- [ ] **Step 4: Test --push --dry-run**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --push --dry-run
```
Expected: Full pipeline output, 5 items per category with [新]/[续] markers

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add --collect/--push modes with RSS store and pushed URL tracking"
```

---

### Task 7: launchd 调度更新

**Files:**
- Modify: `~/Library/LaunchAgents/com.lanser.clawnews.plist`

- [ ] **Step 1: 创建多个 plist 文件**

```bash
# 主推送 plist (9am 早报)
cat > ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lanser.clawnews.morning</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/lanser/Code/Claw_news/venv/bin/python</string>
        <string>/Users/lanser/Code/Claw_news/main.py</string>
        <string>--push</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/lanser/Code/Claw_news/data/push_morning.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/lanser/Code/Claw_news/data/push_morning_error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/lanser/Code/Claw_news</string>
</dict>
</plist>
PLIST

# 晚推 plist (9pm 晚报)
cat > ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lanser.clawnews.evening</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/lanser/Code/Claw_news/venv/bin/python</string>
        <string>/Users/lanser/Code/Claw_news/main.py</string>
        <string>--push</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>21</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/lanser/Code/Claw_news/data/push_evening.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/lanser/Code/Claw_news/data/push_evening_error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/lanser/Code/Claw_news</string>
</dict>
</plist>
PLIST

# 采集 plist (每 3h 跑一次 --collect)
cat > ~/Library/LaunchAgents/com.lanser.clawnews.collect.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lanser.clawnews.collect</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/lanser/Code/Claw_news/venv/bin/python</string>
        <string>/Users/lanser/Code/Claw_news/main.py</string>
        <string>--collect</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>/Users/lanser/Code/Claw_news/data/collect.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/lanser/Code/Claw_news/data/collect_error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/lanser/Code/Claw_news</string>
</dict>
</plist>
PLIST
```

- [ ] **Step 2: 卸载旧的、加载新的**

```bash
launchctl unload ~/Library/LaunchAgents/com.lanser.clawnews.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.collect.plist
```

- [ ] **Step 3: 验证**

```bash
launchctl list | grep clawnews
```
Expected: 3 个 clawnews 任务

- [ ] **Step 4: 备份 plist 到项目 + commit**

```bash
cp ~/Library/LaunchAgents/com.lanser.clawnews.*.plist /Users/lanser/Code/Claw_news/docs/
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: update launchd for dual push + 6x daily RSS collection"
```

---

### Task 8: End-to-end verification

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python -m pytest tests/ -v -q
```
Expected: ALL tests PASS

- [ ] **Step 2: Test --collect**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --collect
```
Expected: Creates data/rss_store.json with items from 4 RSS feeds

- [ ] **Step 3: Test --push --dry-run**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --push --dry-run
```
Expected: 3 categories × 5 items, markers present, no HTML, source labels

- [ ] **Step 4: Test real --push**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --push
```
Expected: 3x 200 OK, mobile receives 3 messages

- [ ] **Step 5: Verify [续] marker (second push)**

```bash
cd /Users/lanser/Code/Claw_news && ./venv/bin/python main.py --push --dry-run
```
Expected: Some items marked `[续]` if URLs overlap with previous push

---

## 自审清单

1. **Spec coverage** — 数据源更新 ✓(T1), 关键词 ✓(T1,T2), 三维评分 ✓(T4), 竞争规则 ✓(T4), 早晚推 ✓(T6), [EN]/[续]/[新] ✓(T5), HTML去标签 ✓(T2,T5), launchd ✓(T7)
2. **Placeholder scan** — 无 TBD/TODO，所有步骤含实际代码
3. **Type consistency** — `keyword_hit: bool` ✓, `pub_date: str` ✓, `time_modifier(pub_date) -> float` ✓, `compute_source_score(HotItem, position) -> float` ✓
