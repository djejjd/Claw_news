# 异常归因速查

按症状 → 归属 → 检查项组织，用于快速定位问题。

## 症状：推送没收到

**可能性排序：源问题 > 推送问题 > 采集问题**

### 先看 publish 状态

```bash
cat /home/ubuntu/code/Claw_news/data/publish_status.json | python3 -m json.tool
```

| status | 归属 | 下一步 |
|---|---|---|
| 文件不存在 | 推送从未成功过 | 手动触发 `curl -sS -X POST http://127.0.0.1:8000/run/news` |
| `ok` | 推送已发出 | 检查企业微信是否收到 |
| `degraded` | 推送成功但状态落盘部分失败 | 看 `errors` |
| `failed` | 推送失败 | 看 `errors`，常见：`push_failed`(WeCom 拒绝)、`llm_parse`(LLM 异常) |
| `skipped` | 没有候选 | 看候选池 |

### 再看候选池

```bash
wc -l /home/ubuntu/code/Claw_news/data/ingestion/$(date +%Y-%m-%d)/candidates.jsonl
```

| 候选数 | 归属 | 下一步 |
|---|---|---|
| 0 | 采集问题 | 看 `/health` 的 `ingest`，确认 ingest 是否在跑 |
| < 20 | 源大面积失效 | 逐个测 RSS feed 可达性 |
| ≥ 50 但推送 skipped | 所有候选已被推送过 | 看 pushed_urls 是否把所有 URL 都吞了 |

---

## 症状：三类分布失衡（某类完全缺失）

**归属：候选分布 > 评分权重**

先看候选池中的分类分布：

```bash
python3 << 'PYEOF'
import json
from collections import Counter
from datetime import date
p = f"/home/ubuntu/code/Claw_news/data/ingestion/{date.today().isoformat()}/candidates.jsonl"
with open(p) as f:
    items = [json.loads(l) for l in f]
cats = Counter(i['category'] for i in items)
print(dict(cats))
PYEOF
```

如果某类候选不足：
- 查对应 RSS feed 是否可达：`curl -sS -o /dev/null -w "%{http_code}" <feed_url>`
- 查 ingest 日志中该 feed 是否报错

如果候选充足但推送中没有：
- 检查 P0 分类保底是否生效（看 digest 中是否每类至少 1 条）

---

## 症状：GitHub 项目质量差（低星/spam）

**归属：GitHub 采集 > 评分过滤**

看候选池质量：

```bash
python3 << 'PYEOF'
import json
from datetime import date
p = f"/home/ubuntu/code/Claw_news/data/github/{date.today().isoformat()}/repos.json"
with open(p) as f:
    repos = json.load(f)
low = [r for r in repos if r['stars'] < 10]
print(f"总数: {len(repos)}, 低星(<10): {len(low)}")
for r in low[:3]:
    print(f"  {r['full_name']} ★{r['stars']}")
PYEOF
```

如果低星项目出现在推送中：
- 检查 `stars >= 10` 过滤是否生效（`app/github_ranking.py`）
- 检查是否有新的 spam 用 10+ stars 绕过了过滤

如果正常项目也无法入选：
- 检查 GitHub API 配额是否耗尽
- 检查 exposure 惩罚是否过度

---

## 症状：/health 显示 unhealthy

**归属：综合判定**

先看完整 `/health`：

```bash
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool
```

归因：
- `sources` 中有 `failed` 且 `last_publish.status=failed` → 双向故障，先修源
- 只有 sources.failed → 降级运行，不阻塞推送
- 只有 publish.failed → 源正常但推送失败，查 WeCom webhook 和企业微信机器人状态

---

## 症状：手动触发超时或没响应

**归属：LLM 超时 > 采集超时**

```bash
docker logs claw-news --tail 20
```

常见原因：
- LLM API（DeepSeek）超时或 401 → 检查 `.env` 中 `LLM_API_KEY`
- 某 RSS feed 挂起 → curl 逐个 feed 测试
- 候选池太大（>300）导致全量评分慢 → 正常，等几秒

---

## 症状：需要复核选材分布、跨日补位或过滤原因

**归属：离线回放，不是实际推送。**

在项目根目录运行：

```bash
./venv/bin/python scripts/replay-content-selection.py \
  --data-dir data --at 2026-07-11T09:00:00+08:00 --format json
```

结果解释：

| 字段 | 含义 | 异常时处理 |
|---|---|---|
| `source_distribution` | 最终入选的来源分布 | 先对照候选数量，确认高频源数量未直接变成最终多数 |
| `category_distribution` | 最终入选的 AI / tool / game 分布 | 检查对应分类的候选、相关性拒绝和有效期 |
| `today_count` / `backfill_count` | 当日入选与历史分类补位数 | 历史项只能补分类最低目标，不能作为今日自由竞争 |
| `rejection_reasons` | 过期或相关性拒绝原因计数 | `expired` 表示超过来源有效期；其他原因按相关性规则排查 |

常见错误：

- `数据目录不存在`：确认 `--data-dir` 指向包含 `ingestion/` 的目录。
- `非法时间参数`：使用包含时区的 ISO 8601 时间，例如 `2026-07-11T09:00:00+08:00`。
- 分布与预期不符：确认 `data_dir` 同级的 `feeds.yaml` 含来源的 `tier`、`retention_hours`、`quality_weight` 与 `filter_profile`。

回放严格只读：不要通过它修复或清理生产状态，不要增加 webhook 参数，也不要提交生产 `data/`、候选原文、运行时配置或任何凭据。日常入口见 [daily-checklist.md](daily-checklist.md)。
