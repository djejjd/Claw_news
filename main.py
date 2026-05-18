"""每日热点聚合推送 — 统一 pipeline 兼容壳

Usage:
    python main.py --period morning    # 早报
    python main.py --period morning --dry-run  # 打印不推送
"""

import asyncio
import logging
import shutil
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import portalocker

from app.config import load_config
from app.pipeline.context import RunContext
from app.pipeline.news_pipeline import run_pipeline

logger = logging.getLogger(__name__)
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


async def _run_pipeline():
    """核心 pipeline 调用，供 main() 使用。"""
    config = load_config()
    now = datetime.now()
    ctx = RunContext(
        trigger_mode="cli_compat",
        time_window_start=now.strftime("%Y-%m-%dT00:00:00"),
        time_window_end=now.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    return await run_pipeline(ctx, config)


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

    config = load_config()

    if not dry_run and not config.wecom_webhook_url:
        logger.error("未配置 wecom_webhook")
        sys.exit(1)

    lock_path = DATA_DIR / ".task.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(lock_path, "w", encoding="utf-8")
    try:
        portalocker.lock(lock_fd, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.LockException:
        logger.warning("已有任务实例运行中，退出")
        sys.exit(0)

    logger.info("统一发布 pipeline (%s)", period)

    if dry_run:
        logger.info("Dry-run 模式: 跳过推送")
        return

    result = await _run_pipeline()

    if result.status == "ok":
        logger.info("推送完成")
        cleanup_old_digests()
    elif result.status == "skipped":
        logger.info("无候选项，跳过")
    else:
        logger.error("推送失败: %s", result.errors)
        sys.exit(1)


if __name__ == "__main__":
    period = "morning"
    if "--period" in sys.argv:
        idx = sys.argv.index("--period")
        if idx + 1 < len(sys.argv):
            period = sys.argv[idx + 1]
    dry = "--dry-run" in sys.argv
    asyncio.run(main(period=period, dry_run=dry))
