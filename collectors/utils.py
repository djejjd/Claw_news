from __future__ import annotations

import logging
import traceback


async def safe_collect(name: str, collector):
    logger = logging.getLogger(__name__)
    try:
        items = await collector.collect()
        logger.info("%s: %d items", name, len(items))
        return items
    except Exception:
        logger.error("%s 采集失败:", name)
        logger.error(traceback.format_exc())
        return []
