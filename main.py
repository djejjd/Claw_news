"""每日热点聚合推送 V2

Usage:
    python main.py --period morning    # 早报 — 采集+评分+推送
    python main.py --period evening    # 晚报 — 采集+评分+推送
    python main.py --period morning --dry-run  # 打印不推送
"""

import asyncio
import logging
import shutil
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import portalocker

from aggregator.merger import Merger
from collectors.huggingface import HfDailyPapersCollector
from collectors.rss_sources import FEED_CONFIGS, RssCollector
from collectors.taptap import TapTapCollector
from collectors.utils import safe_collect
from infra.config.settings import Settings
from infra.storage.state_store import StateStore
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
            RssCollector(
                feed_configs=settings.rss_feeds or FEED_CONFIGS,
                keywords=settings.keywords,
                fetch_count=settings.fetch_count,
            ),
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


async def run_push_sequence(grouped, period, pushed_urls, state_store, pusher):
    current_urls = set(pushed_urls)
    for category in ("ai", "game", "device"):
        cat_items = grouped.get(category, [])
        if not cat_items:
            continue

        try:
            result = await pusher.push_category(
                category=category,
                items=cat_items,
                period=period,
                pushed_urls=current_urls,
            )
        except Exception as exc:
            logger.error("push failed for category=%s: %s", category, exc)
            continue

        if result.success:
            current_urls = state_store.merge_pushed_urls(set(result.urls))
            state_store.write_daily_digest_category(
                period=period,
                category=category,
                items=[
                    {
                        "title": item.title,
                        "url": item.url,
                        "summary": item.summary,
                        "source": item.source,
                        "score": item.source_score,
                    }
                    for item in cat_items
                ],
            )
        else:
            logger.error(
                "push failed for category=%s errcode=%s errmsg=%s",
                result.category,
                result.errcode,
                result.errmsg,
            )
    return current_urls


async def main(period: str = "morning", dry_run: bool = False):
    run_id = uuid.uuid4().hex[:8]
    today_dir = DATA_DIR / date.today().isoformat()
    today_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s %(levelname)s [{run_id}]: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(today_dir / "daily.log", encoding="utf-8"),
        ],
    )
    settings = Settings.load(CONFIG_PATH)
    settings.validate_for_run(dry_run=dry_run)
    top_n = settings.top_n
    webhook_url = settings.wecom_webhook

    lock_path = DATA_DIR / ".task.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(lock_path, "w", encoding="utf-8")
    try:
        portalocker.lock(lock_fd, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.LockException:
        logger.warning("已有任务实例运行中，退出")
        sys.exit(0)

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
        await run_push_sequence(
            grouped=grouped,
            period=period,
            pushed_urls=pushed_urls,
            state_store=state_store,
            pusher=pusher,
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
