#!/usr/bin/env python3
"""只读历史回放 — 模拟推送流程，不写任何生产状态。

用法:
  ./venv/bin/python scripts/replay-content-selection.py \
    --data-dir data --at 2026-07-11T09:00:00+08:00

  ./venv/bin/python scripts/replay-content-selection.py \
    --data-dir data --at 2026-07-11T09:00:00+08:00 --format json
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="只读历史回放：模拟推送流程，输出选材分布")
    parser.add_argument("--data-dir", default="data", help="数据目录路径")
    parser.add_argument("--at", required=True, help="回放时间点，如 2026-07-11T09:00:00+08:00")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="输出格式 (默认 text)"
    )
    parser.add_argument("--lookback-hours", type=int, default=72, help="回看小时数 (默认 72)")
    args = parser.parse_args()

    try:
        from app.tools.content_replay import run_replay

        result = run_replay(
            data_dir=args.data_dir,
            at=args.at,
            lookback_hours=args.lookback_hours,
        )
    except Exception as e:
        print(f"回放失败: {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(f"候选总数:    {result['candidate_count']}")
        print(f"合格候选:    {result['eligible_count']}")
        print(f"最终入选:    {result['selected_count']}")
        print(f"今日入选:    {result['today_count']}")
        print(f"跨日补位:    {result['backfill_count']}")
        print()
        print("来源分布:")
        for src, cnt in sorted(result["source_distribution"].items()):
            print(f"  {src}: {cnt}")
        print()
        print("分类分布:")
        for cat, cnt in sorted(result["category_distribution"].items()):
            print(f"  {cat}: {cnt}")
        print()
        print("拒绝原因:")
        for reason, cnt in sorted(result["rejection_reasons"].items()):
            print(f"  {reason}: {cnt}")
        print()
        print("入选列表:")
        for it in result["selected"]:
            print(f"  [{it['category']}] {it['title'][:50]}  — {it['source']}")


if __name__ == "__main__":
    main()
