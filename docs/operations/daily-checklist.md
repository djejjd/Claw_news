# 日常巡检清单

每天上午推送后（约 09:05），登录服务器完成以下检查。

## 1. 看服务状态

```bash
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool
```

| 状态 | 含义 | 动作 |
|---|---|---|
| `healthy` | 一切正常 | 跳过 |
| `degraded` | 某个源降级或失败 | 看 `sources` 字段，确认哪个源有问题 |
| `unhealthy` | 推送失败且源失败 | 立即排查，看 `failed_sources` 和 `last_publish` |

重点关注 `ingest_fresh`（应为 `true`）和 `last_publish.status`。

## 2. 看源状态

在 `/health` 输出中直接看 `sources` 块，每个源单独一行。

正常情况：rss=ok, github=ok，huggingface=degraded（超时），taptap=failed（已知 405）。

异常：qbitai/leiphone 等核心源出现 failed。

## 3. 看推送内容

```bash
python3 << 'PYEOF'
import json, os
dd = '/home/ubuntu/code/Claw_news/data'
for d in sorted(os.listdir(dd), reverse=True):
    p = f'{dd}/{d}/ai_digest.json'
    if os.path.exists(p):
        with open(p) as f:
            data = json.load(f)
        items = data.get('headline_items', [])
        cats = {}
        for it in items:
            dc = it.get('display_category', 'AI')
            cats[dc] = cats.get(dc, 0) + 1
        print(f"日期: {data['date']} | 条数: {len(items)} | 分布: {cats}")
        for it in items:
            src = it.get('source', '?')
            lbl = it.get('topic_label', '')
            dc = it.get('display_category', '?')
            print(f"  [{dc}] [{lbl}] {it['title'][:50]}  — {src}")
        gh = data.get('github_projects', [])
        if gh:
            print(f"GitHub: {len(gh)} 个项目")
            for g in gh:
                print(f"  {g.get('full_name','?')} | {g.get('recommendation','')}")
        break
PYEOF
```

| 检查项 | 正常 | 异常 |
|---|---|---|
| 总数 | 5-10 条 | <3 或 =0 |
| 分类分布 | 三类都有 | 某类缺失 |
| topic_label | 大部分不为空 | 全空 |
| GitHub | 3 个项目 | 0 个或都是低星 |

## 4. 看候选池规模

```bash
wc -l /home/ubuntu/code/Claw_news/data/ingestion/$(date +%Y-%m-%d)/candidates.jsonl 2>/dev/null
```

正常应有 50+ 候选。如果 <20，说明源大面积失效。

## 5. 快速综合检查

```bash
bash /home/ubuntu/code/Claw_news/scripts/quick-verify.sh
```

## 6. 离线内容选材回放（只读）

当来源或分类分布需要复核时，在项目根目录运行固定时间点的离线回放：

```bash
./venv/bin/python scripts/replay-content-selection.py \
  --data-dir data --at 2026-07-11T09:00:00+08:00 --format json
```

该命令只读取 `data/ingestion/` 与同级 `feeds.yaml`，不会触发 LLM、企业微信推送，也不会写入已发布状态、digest、metrics 或 publish status。输出中的 `source_distribution`、`category_distribution`、`today_count`、`backfill_count` 和 `rejection_reasons` 用于复核来源分布、分类保底、跨日补位和过滤结果。

若需保存回放结果用于讨论，只保存脱敏后的汇总输出；不得把生产候选原文、运行时 `data/`、`feeds.yaml`、webhook 或密钥提交到仓库。常见失败与结果异常的处理见 [troubleshooting.md](troubleshooting.md)。
