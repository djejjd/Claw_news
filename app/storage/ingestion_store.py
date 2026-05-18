from __future__ import annotations

import json
import shutil
from dataclasses import asdict, fields as dataclass_fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from app.pipeline.candidate import CandidateItem

_CANDIDATE_FIELD_NAMES = {f.name for f in dataclass_fields(CandidateItem)}


class IngestionStore:
    """文件型候选池：JSONL 追加写入，读取时按 canonical_key 折叠去重。"""

    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
        self.ingestion_dir = root_dir / "data" / "ingestion"

    # ------------------------------------------------------------------
    # append_or_merge
    # ------------------------------------------------------------------

    def append_or_merge(self, items: list, source_failures: list = None) -> dict:
        """追加候选条目到当天 JSONL 并更新 index.json。

        Args:
            items: CandidateItem 实例列表或 dict 列表（会自动标准化）。
            source_failures: 本轮采集失败的 source 名称列表。

        Returns:
            index 字典。
        """
        today = date.today().isoformat()
        now_iso = datetime.now().isoformat()
        day_dir = self._ensure_day_dir(today)

        # ---- 标准化 ----
        candidates: list[CandidateItem] = []
        for item in items:
            candidates.append(self._normalize_item(item, now_iso))

        # ---- 追加 JSONL ----
        jsonl_path = day_dir / "candidates.jsonl"
        with open(jsonl_path, "a", encoding="utf-8") as f:
            for c in candidates:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

        # ---- 更新 index.json ----
        index = self._load_index(day_dir)
        index["date"] = today

        # 合并 seen_keys
        seen = set(index.get("seen_keys", []))
        for c in candidates:
            seen.add(c.canonical_key)
        index["seen_keys"] = sorted(seen)

        # 合并 source_failures
        if source_failures:
            existing_sf = set(index.get("source_failures", []))
            existing_sf.update(source_failures)
            index["source_failures"] = sorted(existing_sf)

        index["item_count"] = index.get("item_count", 0) + len(candidates)
        index["updated_at"] = now_iso

        self._atomic_write_index(day_dir, index)
        return index

    # ------------------------------------------------------------------
    # load_window_candidates
    # ------------------------------------------------------------------

    def load_window_candidates(
        self,
        time_window_start: str,
        time_window_end: str,
        pushed_urls: set = None,
        pushed_keys: set = None,
    ) -> list[CandidateItem]:
        """加载时间窗口内的候选条目，按 canonical_key 折叠并过滤已发布项。

        折叠优先级（高→低）：
            1. published_at 更新
            2. fetched_at 更新
            3. summary 更长
        """
        if pushed_urls is None:
            pushed_urls = set()
        if pushed_keys is None:
            pushed_keys = set()

        start_dt = datetime.fromisoformat(time_window_start)
        end_dt = datetime.fromisoformat(time_window_end)
        start_date = start_dt.date()
        end_date = end_dt.date()

        # 1. 收集窗口内所有原始条目
        raw_items: list[CandidateItem] = []
        if self.ingestion_dir.exists():
            for day_dir in sorted(self.ingestion_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                try:
                    dir_date = date.fromisoformat(day_dir.name)
                except ValueError:
                    continue
                if not (start_date <= dir_date <= end_date):
                    continue

                jsonl_path = day_dir / "candidates.jsonl"
                if not jsonl_path.exists():
                    continue
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            fields = {k: v for k, v in data.items() if k in _CANDIDATE_FIELD_NAMES}
                            item = CandidateItem(**fields)
                            if item.fetched_at:
                                try:
                                    fetched_dt = datetime.fromisoformat(item.fetched_at)
                                except ValueError:
                                    fetched_dt = None
                                if fetched_dt is not None and not (start_dt <= fetched_dt <= end_dt):
                                    continue
                            raw_items.append(item)
                        except (json.JSONDecodeError, TypeError):
                            continue

        # 2. 按 canonical_key 折叠
        folded: dict[str, CandidateItem] = {}
        for item in raw_items:
            key = item.canonical_key
            if not key:
                continue
            if key not in folded:
                folded[key] = item
                continue
            existing = folded[key]

            # 优先级 1：published_at 更新的优先
            cmp = self._compare_str_field(item.published_at, existing.published_at)
            if cmp > 0:
                folded[key] = item
                continue
            if cmp < 0:
                continue

            # 优先级 2：fetched_at 更新的优先
            cmp = self._compare_str_field(item.fetched_at, existing.fetched_at)
            if cmp > 0:
                folded[key] = item
                continue
            if cmp < 0:
                continue

            # 优先级 3：summary 更长的优先
            if len(item.summary or "") > len(existing.summary or ""):
                folded[key] = item

        # 3. 过滤已发布项
        result = []
        for item in folded.values():
            if item.url in pushed_urls:
                continue
            if item.canonical_key in pushed_keys:
                continue
            result.append(item)

        return result

    def load_recent_seen_canonical_keys(self, keep_days: int = 3) -> set[str]:
        """加载最近 keep_days 天内已见过的 canonical_key。"""
        keys: set[str] = set()
        if not self.ingestion_dir.exists():
            return keys

        cutoff = date.today() - timedelta(days=keep_days)
        for day_dir in self.ingestion_dir.iterdir():
            if not day_dir.is_dir():
                continue
            try:
                dir_date = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if dir_date <= cutoff:
                continue

            index_path = day_dir / "index.json"
            if not index_path.exists():
                continue

            try:
                payload = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            for key in payload.get("seen_keys", []):
                if key:
                    keys.add(key)

        return keys

    # ------------------------------------------------------------------
    # prune_expired
    # ------------------------------------------------------------------

    def prune_expired(self, keep_days: int = 3) -> int:
        """删除超过 keep_days 天的 ingestion 目录。

        Returns:
            删除的目录数量。
        """
        if not self.ingestion_dir.exists():
            return 0

        cutoff = date.today() - timedelta(days=keep_days)
        deleted = 0

        for day_dir in self.ingestion_dir.iterdir():
            if not day_dir.is_dir():
                continue
            try:
                dir_date = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if dir_date <= cutoff:
                shutil.rmtree(day_dir)
                deleted += 1

        return deleted

    # ==================================================================
    # internal helpers
    # ==================================================================

    @staticmethod
    def _compare_str_field(a: str, b: str) -> int:
        """比较两个可空字符串。a > b 返回 1, a < b 返回 -1, 相等或均为空返回 0。"""
        if a and b:
            if a > b:
                return 1
            if a < b:
                return -1
            return 0
        if a and not b:
            return 1
        if b and not a:
            return -1
        return 0

    def _normalize_item(self, item, now_iso: str) -> CandidateItem:
        """将 dict 转为 CandidateItem，补全缺失字段。"""
        if isinstance(item, dict):
            valid = {k: v for k, v in item.items() if k in _CANDIDATE_FIELD_NAMES}
            item = CandidateItem(**valid)
        if not item.canonical_key:
            item.canonical_key = CandidateItem.make_canonical_key(item.url)
        if not item.fetched_at:
            item.fetched_at = now_iso
        return item

    def _ensure_day_dir(self, date_str: str) -> Path:
        day_dir = self.ingestion_dir / date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _load_index(self, day_dir: Path) -> dict:
        index_path = day_dir / "index.json"
        if index_path.exists():
            try:
                return json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    @staticmethod
    def _atomic_write_index(day_dir: Path, payload: dict) -> None:
        index_path = day_dir / "index.json"
        tmp_path = index_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(index_path)
