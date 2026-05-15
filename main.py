"""每日热点聚合推送 V2

Usage:
    python main.py --period morning    # 早报 — 采集+评分+推送
    python main.py --period evening    # 晚报 — 采集+评分+推送
    python main.py --period morning --dry-run  # 打印不推送
"""

import asyncio
import logging
import sys
from pathlib import Path
import shutil
from datetime import date, timedelta

from infra.config.settings import Settings
from infra.storage.state_store import StateStore

from collectors.rss_sources import RssCollector
from collectors.huggingface import HfDailyPapersCollector
from collectors.taptap import TapTapCollector
from collectors.utils import safe_collect
from aggregator.merger import Merger
from pusher.wecom import WeComPusher, format_message

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent / "config.yaml"
DATA_DIR = Path(__file__).parent / "data"


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


async def collect_all(settings: Settings):
    sources = settings.collector_sources

    tasks = {}
    if sources.rss:
        tasks["rss"] = safe_collect(
            "rss",
            RssCollector(keywords=settings.keywords, fetch_count=settings.fetch_count),
        )
    if sources.huggingface:
        tasks["huggingface"] = safe_collect(
            "huggingface",
            HfDailyPapersCollector(fetch_count=settings.fetch_count),
        )
    if sources.taptap:
        tasks["taptap"] = safe_collect(
            "taptap",
            TapTapCollector(fetch_count=settings.fetch_count),
        )

    results = await asyncio.gather(*tasks.values())
    all_items = []
    for items in results:
        all_items.extend(items)
    return all_items


async def main(period: str = "morning", dry_run: bool = False):
    today_dir = DATA_DIR / date.today().isoformat()
    today_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(today_dir / "daily.log", encoding="utf-8"),
        ],
    )
    settings = Settings.load(CONFIG_PATH)
    settings.validate_for_run(dry_run=dry_run)
    top_n = settings.top_n
    webhook_url = settings.wecom_webhook

    logger.info("Step 1: 采集数据 (%s)", period)
    all_items = await collect_all(settings)
    logger.info("采集到 %d 条", len(all_items))

    logger.info("Step 2: 合并排序")
    merger = Merger(top_n=top_n)
    grouped = merger.merge(all_items, period=period)
    for cat, items in grouped.items():
        logger.info("%s: %d items after merge", cat, len(items))

    state_store = StateStore(DATA_DIR)
    pushed_urls = state_store.load_pushed_urls()

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
        state_store.merge_pushed_urls(new_urls)
        # Write daily digest per category
        for cat, items in grouped.items():
            if items:
                state_store.write_daily_digest_category(
                    period=period,
                    category=cat,
                    items=[{
                        "title": i.title, "url": i.url, "summary": i.summary,
                        "source": i.source, "score": i.source_score
                    } for i in items],
                )
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
