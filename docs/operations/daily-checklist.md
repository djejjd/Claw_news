# 日常巡检清单

每天上午推送后（约 09:05），登录服务器完成以下检查。

## 1. 看服务状态

```bash
ssh ubuntu@124.223.102.241 "curl -sS http://127.0.0.1:8000/health"
```

| 状态 | 含义 | 动作 |
|---|---|---|
| `healthy` | 一切正常 | 跳过 |
| `degraded` | 某个源降级或失败 | 看 `sources` 字段，确认哪个源有问题 |
| `unhealthy` | 推送失败且源失败 | 立即排查，看 `failed_sources` 和 `last_publish` |

重点关注 `ingest_fresh`（应为 `true`）和 `last_publish.status`。

## 2. 看源状态

```bash
ssh ubuntu@124.223.102.241 "curl -sS http://127.0.0.1:8000/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d[\"sources\"], indent=2))'"
```

| 源状态 | 含义 |
|---|---|
| `ok` | 最近一轮采集正常 |
| `failed` | 最近一轮完全失败 |
| `degraded` | 部分 feed 失败或标记为可选跳过 |

正常情况：rss=ok, github=ok，huggingface=degraded（超时），taptap=failed（已知 405）。

异常：qbitai/leiphone 等核心源出现 failed。

## 3. 看推送内容

```bash
ssh ubuntu@124.223.102.241 "python3 -c '
import json, os
dd = \"/home/ubuntu/code/Claw_news/data\"
for d in sorted(os.listdir(dd), reverse=True):
    p = f\"{dd}/{d}/ai_digest.json\"
    if os.path.exists(p):
        with open(p) as f:
            d = json.load(f)
        items = d.get(\"headline_items\", [])
        cats = {}
        for it in items:
            cats[it.get(\"display_category\",\"AI\")] = cats.get(it.get(\"display_category\",\"AI\"),0)+1
        print(f\"日期: {d[\"date\"]} | 条数: {len(items)} | 分布: {cats}\")
        for it in items:
            print(f\"  [{it.get(\"display_category\",\"?\")}] [{it.get(\"topic_label\",\"\")}] {it.get(\"title\",\"\")[:50]}\")
        gh = d.get(\"github_projects\", [])
        if gh:
            print(f\"GitHub: {len(gh)} 个项目\")
            for g in gh:
                print(f\"  {g.get(\"full_name\",\"?\")} | {g.get(\"recommendation\",\"\")}\")
        break
'"
```

| 检查项 | 正常 | 异常 |
|---|---|---|
| 总数 | 5-10 条 | <3 或 =0 |
| 分类分布 | 三类都有 | 某类缺失 |
| GitHub | 3 个项目 | 0 个或都是低星 |

## 4. 看候选池规模

```bash
ssh ubuntu@124.223.102.241 "wc -l /home/ubuntu/code/Claw_news/data/ingestion/\$(date +%Y-%m-%d)/candidates.jsonl 2>/dev/null"
```

正常应有 50+ 候选。如果 <20，说明源大面积失效。

## 5. 快速综合检查

```bash
bash scripts/quick-verify.sh
```
