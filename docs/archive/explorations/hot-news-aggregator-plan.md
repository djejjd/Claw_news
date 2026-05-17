# 每日热点信息聚合与推送工具 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Python CLI 工具，每日从 RSS/API/爬虫多源采集 AI、游戏、数码设备热点，合并排序后通过企业微信 Bot 推送。

**Architecture:** 三层结构 — 采集层（每个源一个模块，统一输出 HotItem）、聚合层（按分类合并/去重/排序）、推送层（格式化为 Markdown 推送至企业微信）。入口 main.py 用 asyncio 并发执行采集，launchd 每日定时触发。

**Tech Stack:** Python 3.10+, httpx, BeautifulSoup4, feedparser, pyyaml, pytest, launchd (macOS)

---

## 文件结构总览

```
Claw_news/
├── main.py                    # 入口：加载配置、协调采集/聚合/推送
├── config.yaml                # 源开关、Webhook URL、推送参数
├── requirements.txt           # httpx, bs4, feedparser, pyyaml
├── collectors/
│   ├── __init__.py
│   ├── base.py                # HotItem 数据模型 + 时间衰减/归一化工具函数
│   ├── rss_sources.py         # RSS 多源采集（机器之心、少数派、游研社）
│   ├── huggingface.py         # HuggingFace Daily Papers API
│   ├── taptap.py              # TapTap 热门榜爬虫
│   └── ithome.py              # IT之家热榜爬虫
├── aggregator/
│   ├── __init__.py
│   └── merger.py              # 按分类合并、URL 去重、综合排序、取 Top N
├── pusher/
│   ├── __init__.py
│   └── wecom.py               # 企业微信 Markdown 格式化 + webhook 发送
├── data/                      # 运行时自动创建，存放历史记录
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_rss_collector.py
│   ├── test_huggingface.py
│   ├── test_taptap.py
│   ├── test_ithome.py
│   ├── test_merger.py
│   └── test_wecom.py
└── docs/superpowers/
    ├── specs/2026-05-15-hot-news-aggregator-design.md
    └── plans/2026-05-15-hot-news-aggregator-plan.md
```

---

### Task 1: 项目骨架与数据模型

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `collectors/__init__.py`
- Create: `collectors/base.py`
- Create: `aggregator/__init__.py`
- Create: `pusher/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建 requirements.txt**

```bash
cat > /Users/lanser/Code/Claw_news/requirements.txt << 'EOF'
httpx>=0.27.0
beautifulsoup4>=4.12.0
feedparser>=6.0.0
pyyaml>=6.0
pytest>=8.0.0
pytest-httpx>=0.30.0
EOF
```

- [ ] **Step 2: 安装依赖**

```bash
cd /Users/lanser/Code/Claw_news && pip install -r requirements.txt
```
Expected: 全部安装成功，无报错。

- [ ] **Step 3: 创建 config.yaml**

```yaml
collectors:
  sources:
    huggingface: true
    rss: true
    taptap: true
    ithome: true
  top_n: 5

rss_feeds:
  - url: "https://www.jiqizhixin.com/rss"
    category: "ai"
  - url: "https://sspai.com/feed"
    category: "device"
  - url: "https://www.yystv.cn/rss/feed"
    category: "game"

pusher:
  wecom_webhook: ""

schedule:
  time: "09:00"
```

- [ ] **Step 4: 创建 collectors/base.py — 数据模型与工具函数**

```python
from dataclasses import dataclass, field
from typing import Literal
import time

Category = Literal["ai", "game", "device"]


@dataclass
class HotItem:
    title: str
    url: str
    summary: str
    source: str
    category: Category
    source_score: float  # 0.0-10.0, 来源于自身热度/排名
    timestamp: float = field(default_factory=time.time)

    @property
    def final_score(self) -> float:
        """综合得分 = 来源热度分 + 时间衰减分"""
        return self.source_score + time_decay_bonus(self.timestamp)


def time_decay_bonus(ts: float, now: float | None = None) -> float:
    """24h 内 +2，24-48h +1，48-72h 0，之后每 12h -1"""
    if now is None:
        now = time.time()
    age_hours = (now - ts) / 3600
    if age_hours <= 24:
        return 2.0
    if age_hours <= 48:
        return 1.0
    if age_hours <= 72:
        return 0.0
    return -((age_hours - 72) // 12)


def normalize_rank_score(rank: int, total: int = 10) -> float:
    """排名转 0-10 分：第 1 名 = 10，按比例递减"""
    if total <= 1:
        return 10.0
    return max(0.0, 10.0 - (rank - 1) * (10.0 / (total - 1)))
```

- [ ] **Step 5: 创建空的 __init__.py 文件**

```bash
touch /Users/lanser/Code/Claw_news/collectors/__init__.py \
      /Users/lanser/Code/Claw_news/aggregator/__init__.py \
      /Users/lanser/Code/Claw_news/pusher/__init__.py \
      /Users/lanser/Code/Claw_news/tests/__init__.py
```

- [ ] **Step 6: 创建 tests/conftest.py**

```python
import pytest
from collectors.base import HotItem


@pytest.fixture
def sample_items():
    """创建跨分类的样本数据用于聚合器测试"""
    import time
    now = time.time()
    return [
        HotItem("AI Paper A", "https://a.com/1", "Summary A", "huggingface", "ai", 9.0, now - 3600),
        HotItem("AI News B", "https://b.com/2", "Summary B", "rss", "ai", 5.0, now - 7200),
        HotItem("Game News C", "https://c.com/3", "Summary C", "taptap", "game", 8.0, now - 1800),
        HotItem("Game News D", "https://d.com/4", "Summary D", "rss", "game", 5.0, now - 40000),
        HotItem("Device E", "https://e.com/5", "Summary E", "ithome", "device", 7.0, now - 600),
        HotItem("Device F", "https://f.com/6", "Summary F", "rss", "device", 5.0, now - 50000),
        # Duplicate URL - should be deduped
        HotItem("AI Paper A dup", "https://a.com/1", "Dup", "rss", "ai", 3.0, now - 3600),
    ]
```

- [ ] **Step 7: 运行测试确认骨架可用**

```bash
cd /Users/lanser/Code/Claw_news && python -c "from collectors.base import HotItem, time_decay_bonus, normalize_rank_score; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git init && git add -A && git commit -m "feat: project skeleton with HotItem data model and config"
```

---

### Task 2: RSS 多源采集器

**Files:**
- Create: `collectors/rss_sources.py`
- Create: `tests/test_rss_collector.py`

- [ ] **Step 1: 编写失败测试 tests/test_rss_collector.py**

```python
from collectors.rss_sources import RssCollector, FEED_CONFIGS


def test_feed_configs_have_required_fields():
    """每个 feed 配置包含 url 和 category"""
    for feed in FEED_CONFIGS:
        assert "url" in feed
        assert "category" in feed
        assert feed["category"] in ("ai", "game", "device")


def test_parse_entry_to_hotitem():
    """从 RSS entry 字典正确构造 HotItem"""
    collector = RssCollector()
    entry = {
        "title": "GPT-5 发布引发行业震动",
        "link": "https://example.com/gpt5",
        "summary": "OpenAI 今日正式发布 GPT-5...",
        "published_parsed": (2026, 5, 15, 10, 0, 0, 4, 136, 0),
    }
    feed = {"url": "https://example.com/rss", "category": "ai"}
    item = collector._parse_entry(entry, feed)
    assert item.title == "GPT-5 发布引发行业震动"
    assert item.url == "https://example.com/gpt5"
    assert item.category == "ai"
    assert item.source == "rss"
    assert item.source_score == 5.0


def test_parse_entry_missing_fields():
    """缺少字段时使用默认值不会崩溃"""
    collector = RssCollector()
    entry = {"title": "No link item"}
    feed = {"url": "https://example.com/rss", "category": "game"}
    item = collector._parse_entry(entry, feed)
    assert item.title == "No link item"
    assert item.url == ""
    assert item.summary == ""
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_rss_collector.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'collectors.rss_sources'`

- [ ] **Step 3: 实现 collectors/rss_sources.py**

```python
import time
from calendar import timegm
from typing import List

import feedparser

from collectors.base import HotItem, Category

# 每个 feed: url + 归属分类
FEED_CONFIGS: List[dict] = [
    {"url": "https://www.jiqizhixin.com/rss", "category": "ai"},
    {"url": "https://sspai.com/feed", "category": "device"},
    {"url": "https://www.yystv.cn/rss/feed", "category": "game"},
]


class RssCollector:
    """RSS 多源采集器。遍历 FEED_CONFIGS，每个 feed 取最近 10 条，转为 HotItem。"""

    def __init__(self, feed_configs: List[dict] | None = None):
        self.feeds = feed_configs or FEED_CONFIGS

    async def collect(self) -> List["HotItem"]:
        items = []
        for feed in self.feeds:
            parsed = feedparser.parse(feed["url"])
            entries = parsed.entries[:10]
            for entry in entries:
                items.append(self._parse_entry(entry, feed))
        return items

    def _parse_entry(self, entry: dict, feed: dict) -> "HotItem":
        title = entry.get("title", "")
        url = entry.get("link", "")
        summary = entry.get("summary", "")
        ts = _parse_timestamp(entry)

        return HotItem(
            title=title,
            url=url,
            summary=summary,
            source="rss",
            category=Category(feed["category"]),
            source_score=5.0,
            timestamp=ts,
        )


def _parse_timestamp(entry: dict) -> float:
    """从 feedparser entry 提取时间戳，失败则用当前时间"""
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        return float(timegm(published_parsed))
    return time.time()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_rss_collector.py -v
```
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add RSS multi-source collector"
```

---

### Task 3: HuggingFace Daily Papers API 采集器

**Files:**
- Create: `collectors/huggingface.py`
- Create: `tests/test_huggingface.py`

- [ ] **Step 1: 编写失败测试 tests/test_huggingface.py**

```python
import json
import pytest
from collectors.huggingface import HfDailyPapersCollector, HF_API_URL


def test_parse_paper_to_hotitem():
    """从 API 返回的 paper 字典正确构造 HotItem"""
    collector = HfDailyPapersCollector()
    paper = {
        "title": "Scaling Laws for Multimodal Models",
        "paper": {"id": "abc123"},
        "upvotes": 150,
        "summary": "We study scaling laws across modalities...",
    }
    item = collector._parse_paper(paper)
    assert item.title == "Scaling Laws for Multimodal Models"
    assert item.url == "https://huggingface.co/papers/abc123"
    assert item.category == "ai"
    assert item.source == "huggingface"
    # 150 upvotes should give a reasonable score
    assert 5.0 <= item.source_score <= 10.0


def test_parse_paper_minimal():
    """最简 paper 数据不会崩溃"""
    collector = HfDailyPapersCollector()
    paper = {"title": "Minimal Paper", "paper": {"id": "min1"}}
    item = collector._parse_paper(paper)
    assert item.title == "Minimal Paper"
    assert item.url == "https://huggingface.co/papers/min1"
    assert item.summary == ""


def test_normalize_upvotes_zero():
    """0 票映射到最低分"""
    collector = HfDailyPapersCollector()
    score = collector._upvotes_to_score(0, max_votes=200)
    assert score == 0.0


def test_normalize_upvotes_max():
    """最高票映射到 10 分"""
    collector = HfDailyPapersCollector()
    score = collector._upvotes_to_score(200, max_votes=200)
    assert score == 10.0


@pytest.mark.asyncio
async def test_collect_returns_list(httpx_mock):
    """API 正常返回时得到 HotItem 列表"""
    mock_papers = [
        {"title": f"Paper {i}", "paper": {"id": f"id{i}"}, "upvotes": 100 - i * 10}
        for i in range(5)
    ]
    httpx_mock.add_response(url=HF_API_URL, json=mock_papers)

    collector = HfDailyPapersCollector()
    items = await collector.collect()
    assert len(items) == 5
    assert all(item.category == "ai" for item in items)
    # 票数高的排前面
    assert items[0].source_score >= items[-1].source_score
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_huggingface.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 collectors/huggingface.py**

```python
from typing import List

import httpx

from collectors.base import HotItem

HF_API_URL = "https://huggingface.co/api/daily_papers"


class HfDailyPapersCollector:
    """HuggingFace Daily Papers API 采集器。按社区投票排序，取 Top 10。"""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.get(HF_API_URL, timeout=30.0)
            resp.raise_for_status()
            papers = resp.json()
        finally:
            if self._client is None:
                await client.aclose()

        max_votes = max((p.get("upvotes", 0) for p in papers), default=1)
        items = [self._parse_paper(p, max_votes) for p in papers[:10]]
        return items

    def _parse_paper(self, paper: dict, max_votes: int | None = None) -> HotItem:
        title = paper.get("title", "")
        paper_id = paper.get("paper", {}).get("id", "")
        upvotes = paper.get("upvotes", 0)
        summary = paper.get("summary", "")

        if max_votes is None:
            max_votes = max(upvotes, 1)

        return HotItem(
            title=title,
            url=f"https://huggingface.co/papers/{paper_id}",
            summary=summary,
            source="huggingface",
            category="ai",
            source_score=self._upvotes_to_score(upvotes, max_votes),
        )

    def _upvotes_to_score(self, upvotes: int, max_votes: int) -> float:
        """票数归一化到 0-10。max_votes 映射到 10，0 映射到 0。"""
        if max_votes <= 0:
            return 0.0
        ratio = upvotes / max_votes
        return round(ratio * 10.0, 1)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_huggingface.py -v
```
Expected: ALL PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add HuggingFace Daily Papers API collector"
```

---

### Task 4: TapTap 热门榜爬虫

**Files:**
- Create: `collectors/taptap.py`
- Create: `tests/test_taptap.py`

- [ ] **Step 1: 编写失败测试 tests/test_taptap.py**

```python
import pytest
from collectors.taptap import TapTapCollector, TAPTAP_HOT_URL


SAMPLE_HTML = """
<html>
<body>
<div class="tap-top-list">
  <a class="game-card" href="/app/12345">
    <h3>原神</h3>
    <span class="game-genre">角色扮演</span>
  </a>
  <a class="game-card" href="/app/67890">
    <h3>崩坏：星穹铁道</h3>
    <span class="game-genre">回合制</span>
  </a>
  <a class="game-card" href="/app/11111">
    <h3>绝区零</h3>
    <span class="game-genre">动作</span>
  </a>
</div>
</body>
</html>
"""


def test_parse_html_to_items():
    """从 TapTap 热门页 HTML 提取游戏列表"""
    collector = TapTapCollector()
    items = collector._parse_html(SAMPLE_HTML)
    assert len(items) == 3
    assert items[0].title == "原神"
    assert items[0].url == "https://www.taptap.cn/app/12345"
    assert items[0].category == "game"
    assert items[0].source == "taptap"
    assert items[0].source_score > items[1].source_score  # 排名1 > 排名2


def test_parse_html_empty():
    """空页面返回空列表"""
    collector = TapTapCollector()
    items = collector._parse_html("<html></html>")
    assert items == []


@pytest.mark.asyncio
async def test_collect_mocked(httpx_mock):
    """模拟 HTTP 响应，验证 collect 完整流程"""
    httpx_mock.add_response(url=TAPTAP_HOT_URL, html=SAMPLE_HTML)
    collector = TapTapCollector()
    items = await collector.collect()
    assert len(items) == 3
    assert all(item.category == "game" for item in items)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_taptap.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 collectors/taptap.py**

```python
from typing import List

import httpx
from bs4 import BeautifulSoup

from collectors.base import HotItem, normalize_rank_score

TAPTAP_HOT_URL = "https://www.taptap.cn/top/hot"


class TapTapCollector:
    """TapTap 热门榜爬虫。解析热门页 HTML，提取游戏名和链接。"""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        try:
            resp = await client.get(TAPTAP_HOT_URL, timeout=30.0)
            resp.raise_for_status()
            items = self._parse_html(resp.text)
        finally:
            if self._client is None:
                await client.aclose()
        return items

    def _parse_html(self, html: str) -> List[HotItem]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a.game-card")
        items = []
        for i, card in enumerate(cards[:10]):
            title_el = card.select_one("h3")
            title = title_el.get_text(strip=True) if title_el else ""
            href = card.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.taptap.cn{href}"

            items.append(HotItem(
                title=title,
                url=href,
                summary="",
                source="taptap",
                category="game",
                source_score=normalize_rank_score(i + 1, total=min(len(cards), 10)),
            ))
        return items
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_taptap.py -v
```
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add TapTap hot list crawler"
```

---

### Task 5: IT之家热榜爬虫

**Files:**
- Create: `collectors/ithome.py`
- Create: `tests/test_ithome.py`

- [ ] **Step 1: 编写失败测试 tests/test_ithome.py**

```python
import pytest
from collectors.ithome import ItHomeCollector, ITHOME_RANK_URL


SAMPLE_HTML = """
<html>
<body>
<div class="rank-box">
  <div class="rank-item">
    <a class="title" href="https://www.ithome.com/0/800/001.htm">苹果发布 M5 芯片</a>
  </div>
  <div class="rank-item">
    <a class="title" href="https://www.ithome.com/0/800/002.htm">华为 Mate 80 系列曝光</a>
  </div>
  <div class="rank-item">
    <a class="title" href="https://www.ithome.com/0/800/003.htm">RTX 5090 性能测试出炉</a>
  </div>
</div>
</body>
</html>
"""


def test_parse_html_to_items():
    """从 IT之家热榜 HTML 提取条目"""
    collector = ItHomeCollector()
    items = collector._parse_html(SAMPLE_HTML)
    assert len(items) == 3
    assert items[0].title == "苹果发布 M5 芯片"
    assert items[0].category == "device"
    assert items[0].source == "ithome"
    assert items[0].source_score > items[1].source_score


def test_parse_html_empty():
    """空页面返回空列表"""
    collector = ItHomeCollector()
    items = collector._parse_html("<html></html>")
    assert items == []


@pytest.mark.asyncio
async def test_collect_mocked(httpx_mock):
    """模拟 HTTP 响应"""
    httpx_mock.add_response(url=ITHOME_RANK_URL, html=SAMPLE_HTML)
    collector = ItHomeCollector()
    items = await collector.collect()
    assert len(items) == 3
    assert all(item.category == "device" for item in items)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_ithome.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 collectors/ithome.py**

```python
from typing import List

import httpx
from bs4 import BeautifulSoup

from collectors.base import HotItem, normalize_rank_score

ITHOME_RANK_URL = "https://m.ithome.com/rank/"


class ItHomeCollector:
    """IT之家热榜爬虫。解析移动端热榜 HTML。"""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
        )
        try:
            resp = await client.get(ITHOME_RANK_URL, timeout=30.0)
            resp.raise_for_status()
            items = self._parse_html(resp.text)
        finally:
            if self._client is None:
                await client.aclose()
        return items

    def _parse_html(self, html: str) -> List[HotItem]:
        soup = BeautifulSoup(html, "html.parser")
        rank_items = soup.select(".rank-item")
        items = []
        for i, item in enumerate(rank_items[:10]):
            link = item.select_one("a.title")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")

            items.append(HotItem(
                title=title,
                url=href,
                summary="",
                source="ithome",
                category="device",
                source_score=normalize_rank_score(i + 1, total=min(len(rank_items), 10)),
            ))
        return items
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_ithome.py -v
```
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add ITHome hot list crawler"
```

---

### Task 6: 聚合器 — 合并、去重、排序

**Files:**
- Create: `aggregator/merger.py`
- Create: `tests/test_merger.py`

- [ ] **Step 1: 编写失败测试 tests/test_merger.py**

```python
import time
import pytest
from aggregator.merger import Merger
from collectors.base import HotItem


class TestMerger:
    def test_dedup_by_url_keeps_higher_score(self, sample_items):
        """相同 URL 的去重保留 source_score 更高的那条"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items)
        ai_items = result["ai"]
        # sample_items 有两个 https://a.com/1 (score 9.0 和 3.0)
        # 应该只保留 score 9.0 的
        titles = [item.title for item in ai_items]
        assert "AI Paper A" in titles
        assert "AI Paper A dup" not in titles

    def test_groups_by_category(self, sample_items):
        """按分类分组返回 dict"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items)
        assert set(result.keys()) == {"ai", "game", "device"}
        assert all(item.category == "ai" for item in result["ai"])
        assert all(item.category == "game" for item in result["game"])
        assert all(item.category == "device" for item in result["device"])

    def test_sorts_by_final_score_desc(self, sample_items):
        """每个分类内按 final_score 降序"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items)
        for cat_items in result.values():
            scores = [item.final_score for item in cat_items]
            assert scores == sorted(scores, reverse=True)

    def test_top_n_limit(self, sample_items):
        """每个分类最多取 top_n 条"""
        merger = Merger(top_n=2)
        result = merger.merge(sample_items)
        for cat_items in result.values():
            assert len(cat_items) <= 2

    def test_empty_input(self):
        """空输入返回空 dict"""
        merger = Merger(top_n=5)
        result = merger.merge([])
        assert result == {"ai": [], "game": [], "device": []}

    def test_single_category(self):
        """只有一个分类的数据"""
        now = time.time()
        items = [
            HotItem("AI 1", "https://x.com/1", "", "huggingface", "ai", 8.0, now),
            HotItem("AI 2", "https://x.com/2", "", "rss", "ai", 5.0, now),
        ]
        merger = Merger(top_n=5)
        result = merger.merge(items)
        assert len(result["ai"]) == 2
        assert result["game"] == []
        assert result["device"] == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_merger.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现 aggregator/merger.py**

```python
from typing import Dict, List

from collectors.base import HotItem, Category


class Merger:
    """聚合器：合并多源数据，按分类去重排序，取每个分类的 Top N。"""

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
            deduped = self._dedup_by_url(cat_items)
            deduped.sort(key=lambda item: item.final_score, reverse=True)
            result[category] = deduped[:self.top_n]

        return result

    def _dedup_by_url(self, items: List[HotItem]) -> List[HotItem]:
        """URL 去重，保留 source_score 最高的一条"""
        seen: Dict[str, HotItem] = {}
        for item in items:
            if not item.url:
                continue
            if item.url not in seen or item.source_score > seen[item.url].source_score:
                seen[item.url] = item
        return list(seen.values())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_merger.py -v
```
Expected: ALL PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add aggregator with merge, dedup, and ranking"
```

---

### Task 7: 企业微信 Bot 推送器

**Files:**
- Create: `pusher/wecom.py`
- Create: `tests/test_wecom.py`

- [ ] **Step 1: 编写失败测试 tests/test_wecom.py**

```python
import time
import pytest
from pusher.wecom import WeComPusher, format_message, CATEGORY_LABELS, CATEGORY_EMOJI
from collectors.base import HotItem


def make_item(title, url, summary, category, score):
    return HotItem(title, url, summary, f"test-{category}", category, score, time.time())


class TestFormatMessage:
    def test_single_item(self):
        items = [make_item("Test Title", "https://x.com/1", "A short summary", "ai", 8.0)]
        msg = format_message(items, "ai")
        assert "AI" in msg
        assert "Test Title" in msg
        assert "https://x.com/1" in msg
        assert "A short summary" in msg
        # Markdown link format
        assert "[Test Title](https://x.com/1)" in msg

    def test_empty_items(self):
        msg = format_message([], "game")
        assert "暂无" in msg or msg != ""

    def test_category_labels(self):
        assert CATEGORY_LABELS["ai"] == "AI 热点"
        assert CATEGORY_LABELS["game"] == "游戏热点"
        assert CATEGORY_LABELS["device"] == "数码硬件"


class TestWeComPusher:
    @pytest.mark.asyncio
    async def test_push_sends_post(self, httpx_mock):
        """验证向 webhook URL 发送 POST"""
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        httpx_mock.add_response(url=webhook, json={"errcode": 0, "errmsg": "ok"})

        pusher = WeComPusher(webhook)
        items = {
            "ai": [make_item("AI Test", "https://x.com/ai", "summary", "ai", 8.0)],
            "game": [],
            "device": [],
        }
        await pusher.push(items)
        # 应有 POST 请求发送
        assert len(httpx_mock.get_requests()) >= 1

    @pytest.mark.asyncio
    async def test_push_skips_empty_category(self, httpx_mock):
        """空分类不发送消息"""
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        httpx_mock.add_response(url=webhook, json={"errcode": 0})

        pusher = WeComPusher(webhook)
        items = {"ai": [], "game": [], "device": []}
        await pusher.push(items)
        # 空分类不应发送请求
        assert len(httpx_mock.get_requests()) == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_wecom.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现 pusher/wecom.py**

```python
from datetime import datetime
from typing import Dict, List

import httpx

from collectors.base import HotItem, Category

CATEGORY_LABELS = {
    "ai": "AI 热点",
    "game": "游戏热点",
    "device": "数码硬件",
}

CATEGORY_EMOJI = {
    "ai": "🤖",
    "game": "🎮",
    "device": "📱",
}

SEPARATOR = "━━━━━━━━━━━━━━━━━━━"


def format_message(items: List[HotItem], category: Category) -> str:
    """将某分类的热点列表格式化为企业微信 Markdown 消息"""
    today = datetime.now().strftime("%m/%d")
    emoji = CATEGORY_EMOJI.get(category, "")
    label = CATEGORY_LABELS.get(category, category)
    lines = [f"{emoji} **{label}** | {today}", SEPARATOR, ""]

    if not items:
        lines.append("> 暂无热点，稍后再来看看")
    else:
        for i, item in enumerate(items, 1):
            title = item.title.replace("\n", " ").strip()
            if item.url:
                lines.append(f"**{i}.** [{title}]({item.url})")
            else:
                lines.append(f"**{i}.** {title}")
            if item.summary:
                summary = item.summary.replace("\n", " ").strip()[:120]
                lines.append(f"> {summary}")
            if i < len(items):
                lines.append("")

    lines.append("")
    lines.append(SEPARATOR)
    return "\n".join(lines)


class WeComPusher:
    """企业微信 Bot 推送器。逐分类发送 Markdown 消息。"""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None):
        self.webhook_url = webhook_url
        self._client = client

    async def push(self, items: Dict[Category, List[HotItem]]) -> None:
        client = self._client or httpx.AsyncClient()
        try:
            for category in ("ai", "game", "device"):
                cat_items = items.get(category, [])
                if not cat_items:
                    continue
                msg = format_message(cat_items, category)
                payload = {"msgtype": "markdown", "markdown": {"content": msg}}
                resp = await client.post(self.webhook_url, json=payload, timeout=15.0)
                resp.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/test_wecom.py -v
```
Expected: ALL PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add WeChat Work Bot pusher with Markdown formatting"
```

---

### Task 8: 主入口 — main.py

**Files:**
- Create: `main.py`

- [ ] **Step 1: 实现 main.py**

```python
"""每日热点信息聚合与推送工具。

用法:
    python main.py              # 手动执行一次
    python main.py --dry-run    # 只采集聚合，不推送（打印到终端）
"""

import asyncio
import logging
import sys
from pathlib import Path

import yaml

from collectors.rss_sources import RssCollector
from collectors.huggingface import HfDailyPapersCollector
from collectors.taptap import TapTapCollector
from collectors.ithome import ItHomeCollector
from aggregator.merger import Merger
from pusher.wecom import WeComPusher, format_message

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path: str | None = None) -> dict:
    path = path or CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_collectors(config: dict):
    """按配置并发执行已启用的采集器"""
    sources = config.get("collectors", {}).get("sources", {})
    tasks = {}

    async def safe_collect(name, collector):
        try:
            items = await collector.collect()
            logger.info("%s: got %d items", name, len(items))
            return items
        except Exception as e:
            logger.warning("%s failed: %s", name, e)
            return []

    if sources.get("rss", True):
        tasks["rss"] = safe_collect("rss", RssCollector())
    if sources.get("huggingface", True):
        tasks["huggingface"] = safe_collect("huggingface", HfDailyPapersCollector())
    if sources.get("taptap", True):
        tasks["taptap"] = safe_collect("taptap", TapTapCollector())
    if sources.get("ithome", True):
        tasks["ithome"] = safe_collect("ithome", ItHomeCollector())

    results = await asyncio.gather(*tasks.values())
    all_items = []
    for items in results:
        all_items.extend(items)
    return all_items


async def main(dry_run: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()
    top_n = config.get("collectors", {}).get("top_n", 5)
    webhook_url = config.get("pusher", {}).get("wecom_webhook", "")

    logger.info("Step 1: Collecting from sources")
    all_items = await run_collectors(config)
    logger.info("Collected %d items total", len(all_items))

    logger.info("Step 2: Merging and ranking")
    merger = Merger(top_n=top_n)
    grouped = merger.merge(all_items)
    for cat, items in grouped.items():
        logger.info("%s: %d items after merge", cat, len(items))

    if dry_run:
        logger.info("Step 3: Dry run — printing to stdout")
        for cat, items in grouped.items():
            if items:
                print(format_message(items, cat))
                print()
    else:
        if not webhook_url:
            logger.error("No wecom_webhook configured. Set it in config.yaml")
            sys.exit(1)
        logger.info("Step 3: Pushing to WeChat Work")
        pusher = WeComPusher(webhook_url)
        await pusher.push(grouped)
        logger.info("Push complete")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry))
```

- [ ] **Step 2: 验证导入和 dry-run**

```bash
cd /Users/lanser/Code/Claw_news && python main.py --dry-run
```
Expected: 看到采集日志和终端输出（格式化的 Markdown）。若某源不可达会有 warning 但不中断。

- [ ] **Step 3: Commit**

```bash
cd /Users/lanser/Code/Claw_news && git add -A && git commit -m "feat: add main entry point with async collection and dry-run"
```

---

### Task 9: launchd 定时调度

**Files:**
- Create: `~/Library/LaunchAgents/com.lanser.clawnews.plist`

- [ ] **Step 1: 创建 plist 文件**

```bash
cat > ~/Library/LaunchAgents/com.lanser.clawnews.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lanser.clawnews</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/lanser/Code/Claw_news/main.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/lanser/Code/Claw_news/data/cron.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/lanser/Code/Claw_news/data/cron_error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/lanser/Code/Claw_news</string>
</dict>
</plist>
PLIST
```

- [ ] **Step 2: 加载 plist 到 launchd**

```bash
mkdir -p /Users/lanser/Code/Claw_news/data
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.plist
```
Expected: 无输出（成功）。验证：`launchctl list | grep clawnews` 应显示该任务。

- [ ] **Step 3: 确认调度状态**

```bash
launchctl list | grep clawnews
```
Expected: 显示 `com.lanser.clawnews` 及其 PID/状态。

- [ ] **Step 4: 完成提示**

告知用户：
- 修改推送时间：编辑 plist 中的 `Hour`/`Minute`，然后 `launchctl unload` → `launchctl load`
- 卸载：`launchctl unload ~/Library/LaunchAgents/com.lanser.clawnews.plist`
- 手动触发：`python main.py`（随时可用，不依赖定时器）
- 日志位置：`data/cron.log` 和 `data/cron_error.log`

---

### Task 10: 端到端冒烟测试

- [ ] **Step 1: 运行 dry-run 验证全链路**

```bash
cd /Users/lanser/Code/Claw_news && python main.py --dry-run 2>&1
```
Expected: 
- 看到每个采集器的日志（成功或 warning）
- 最终打印三个分类的 Markdown 内容
- 无崩溃

- [ ] **Step 2: 运行全部单元测试**

```bash
cd /Users/lanser/Code/Claw_news && python -m pytest tests/ -v
```
Expected: ALL PASS（约 17 个测试）

- [ ] **Step 3: 配置 webhook 后的真实推送验证**

用户需在 `config.yaml` 中填入企业微信 Bot Webhook URL，然后运行：
```bash
cd /Users/lanser/Code/Claw_news && python main.py
```
Expected: 手机企业微信收到三条消息（AI / 游戏 / 数码各一条）。

---

## 自审清单

1. **Spec coverage** — 数据源（RSS/API/爬虫）✓，三层架构 ✓，排序算法 ✓，推送格式 ✓，launchd 调度 ✓，配置管理 ✓
2. **Placeholder scan** — 无 TBD/TODO/placeholder，所有步骤包含实际代码
3. **Type consistency** — `HotItem` 字段在采集器和聚合器中使用一致；`Category` Literal 类型全链路一致；`Merger.merge()` 返回 `Dict[Category, List[HotItem]]` 与 `WeComPusher.push()` 接收一致
