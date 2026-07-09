# 发版后验证指南

每次 `bash deploy-prod.sh` 完成后，按以下步骤验收。

## 第 1 步：确认容器已启动（30 秒）

```bash
docker ps --format '{{.Names}} {{.Status}}' | grep claw-news
```

预期输出类似：

```
claw-news Up 2 minutes
```

如果容器不存在或反复重启，查看日志：

```bash
docker logs claw-news --tail 30
```

## 第 2 步：确认 /health 可达且有意义

```bash
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool
```

| 字段 | 通过标准 | 不通过则查 |
|---|---|---|
| `status` | `healthy` 或 `degraded` | 如果 `unhealthy`，看 `sources` 和 `last_publish` |
| `ingest_fresh` | `true` | 如果 `false`，说明 ingest 未运行，检查容器日志 |
| `sources.rss` | `ok` | 如果 `failed`，检查 RSS feed 可达性 |

刚部署完刚启动时，`last_publish` 可能为空（尚未推送过），这是正常的。

## 第 3 步：手动触发一次推送

```bash
curl -sS -X POST http://127.0.0.1:8000/run/news | python3 -m json.tool
```

| 字段 | 通过标准 | 不通过则查 |
|---|---|---|
| `status` | `ok` 或 `degraded` | 如果 `failed`，看 `errors` |
| `fetched_count` | ≥ 3 | 如果 =0，看候选池是否为空 |
| `pushed` | `true` | 如果 `false`，看 `errors` 中的推送错误码 |

关注 `errors` 字段。`source_metrics_write_failed` 是已知的非阻塞问题，可以忽略。

## 第 4 步：确认推送内容分布

检查刚才触发的推送结果：

```bash
cat /home/ubuntu/code/Claw_news/data/publish_status.json | python3 -m json.tool
```

确认 `status` 不是 `failed`。

然后看 digest：

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
            cats[it.get('display_category','AI')] = cats.get(it.get('display_category','AI'),0)+1
        print(f"分类分布: {cats}")
        print(f"topic_label 有空: {sum(1 for it in items if not it.get('topic_label'))}/{len(items)}")
        gh = data.get('github_projects', [])
        print(f"GitHub: {len(gh)} 个项目")
        for g in gh:
            print(f"  {g.get('full_name','?')} | {g.get('recommendation','')}")
        break
PYEOF
```

| 检查项 | 通过标准 |
|---|---|
| 分类分布 | AI / 工具 / 游戏 三类都出现 |
| topic_label | 不全为空 |
| GitHub | 3 个项目，推荐理由不为空 |
| 内容可读 | 快速浏览标题，无乱码或明显垃圾 |

## 第 5 步：快速综合检查

```bash
bash /home/ubuntu/code/Claw_news/scripts/quick-verify.sh
```
