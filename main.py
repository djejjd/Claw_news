"""Daily hot news aggregator and push tool.

Usage:
    python main.py              # Run once and push to WeChat Work
    python main.py --dry-run    # Collect and merge only, print to stdout
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
    """Run enabled collectors concurrently"""
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
        logger.info("Step 3: Dry run - printing to stdout")
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
