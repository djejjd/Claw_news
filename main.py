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
    try:
        with open(PUSHED_URLS_PATH) as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
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
        logger.info("推送完成")


if __name__ == "__main__":
    period = "morning"
    if "--period" in sys.argv:
        idx = sys.argv.index("--period")
        if idx + 1 < len(sys.argv):
            period = sys.argv[idx + 1]
    dry = "--dry-run" in sys.argv
    asyncio.run(main(period=period, dry_run=dry))
