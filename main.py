"""每日热点聚合推送 V2

Usage:
    python main.py --period morning    # 早报 — 采集+评分+推送
    python main.py --period evening    # 晚报 — 采集+评分+推送
    python main.py --period morning --dry-run  # 打印不推送
"""

import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
import shutil
from datetime import date, datetime, timedelta

import yaml

from collectors.rss_sources import RssCollector
from collectors.huggingface import HfDailyPapersCollector
from collectors.taptap import TapTapCollector
from aggregator.merger import Merger
from pusher.wecom import WeComPusher, format_message

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
PUSHED_URLS_PATH = Path(__file__).parent / "data" / "pushed_urls.json"
LOG_PATH = Path(__file__).parent / "data" / "daily.log"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_pushed_urls() -> set:
    if not PUSHED_URLS_PATH.exists():
        return set()
    try:
        with open(PUSHED_URLS_PATH) as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_pushed_urls(urls: set):
    PUSHED_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUSHED_URLS_PATH, "w") as f:
        json.dump(list(urls), f)


DATA_DIR = Path(__file__).parent / "data"


def save_daily_digest(grouped: dict, period: str):
    """保存当日推送内容到 data/YYYY-MM-DD/{period}.json"""
    today = date.today().isoformat()
    day_dir = DATA_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "period": period,
        "date": today,
        "pushed_at": datetime.now().isoformat(),
    }
    for cat, items in grouped.items():
        record[cat] = [
            {"title": i.title, "url": i.url, "summary": i.summary,
             "source": i.source, "score": i.source_score}
            for i in items
        ]

    with open(day_dir / f"{period}.json", "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    logger.info("已保存到 %s/%s.json", today, period)


def cleanup_old_digests():
    """删除超过 2 天的历史目录（只保留今天、昨天、前天）"""
    cutoff = date.today() - timedelta(days=2)
    if not DATA_DIR.exists():
        return
    for entry in DATA_DIR.iterdir():
        if not entry.is_dir():
            continue
        try:
            d = date.fromisoformat(entry.name)
            if d < cutoff:
                shutil.rmtree(entry)
                logger.info("清理过期数据: %s", entry.name)
        except ValueError:
            pass  # 非日期目录，跳过


async def collect_all(config: dict):
    sources = config.get("collectors", {}).get("sources", {})

    async def safe_collect(name, collector):
        try:
            items = await collector.collect()
            logger.info("%s: %d items", name, len(items))
            return items
        except Exception:
            logger.error("%s 采集失败:", name)
            logger.error(traceback.format_exc())
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
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )
    config = load_config()
    top_n = config.get("collectors", {}).get("top_n", 5)
    webhook_url = config.get("pusher", {}).get("wecom_webhook", "")

    logger.info("Step 1: 采集数据 (%s)", period)
    all_items = await collect_all(config)
    logger.info("采集到 %d 条", len(all_items))

    logger.info("Step 2: 合并排序")
    merger = Merger(top_n=top_n)
    grouped = merger.merge(all_items, period=period)
    for cat, items in grouped.items():
        logger.info("%s: %d items after merge", cat, len(items))

    pushed_urls = load_pushed_urls()

    if dry_run:
        logger.info("Step 3: Dry-run 输出")
        for cat, items in grouped.items():
            if items:
                print(format_message(items, cat, period=period, pushed_urls=pushed_urls))
                print()
    else:
        if not webhook_url:
            logger.error("未配置 wecom_webhook")
            sys.exit(1)
        logger.info("Step 3: 推送中")
        pusher = WeComPusher(webhook_url)
        await pusher.push(grouped, period=period, pushed_urls=pushed_urls)
        new_urls = {i.url for cat_items in grouped.values() for i in cat_items}
        save_pushed_urls(new_urls)
        save_daily_digest(grouped, period)
        cleanup_old_digests()
        logger.info("推送完成")


if __name__ == "__main__":
    period = "morning"
    if "--period" in sys.argv:
        idx = sys.argv.index("--period")
        if idx + 1 < len(sys.argv):
            period = sys.argv[idx + 1]
    dry = "--dry-run" in sys.argv
    asyncio.run(main(period=period, dry_run=dry))
