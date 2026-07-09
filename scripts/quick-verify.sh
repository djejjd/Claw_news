#!/bin/bash
# Claw_news 快速只读验证脚本
# 用法：ssh ubuntu@124.223.102.241 "bash -s" < scripts/quick-verify.sh
# 或登录服务器后直接运行：bash scripts/quick-verify.sh
#
# 本脚本只读，不触发发布、不重启服务、不写任何数据。

set -euo pipefail

HOST="${CLAW_HOST:-127.0.0.1}"
DATA_DIR="${CLAW_DATA:-/home/ubuntu/code/Claw_news/data}"
TODAY="$(date +%Y-%m-%d)"

echo "========================================"
echo "  Claw_news 快速验证 — ${TODAY}"
echo "========================================"
echo ""

# ---- 1. 容器状态 ----
echo "--- 容器状态 ---"
if docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -q claw-news; then
    docker ps --format '{{.Names}}  {{.Status}}' | grep claw-news
else
    echo "WARN: claw-news 容器未运行或 docker 不可用"
fi
echo ""

# ---- 2. /health ----
echo "--- /health ---"
HEALTH=$(curl -sS --max-time 10 "http://${HOST}:8000/health" 2>&1) || {
    echo "ERROR: /health 不可达: ${HEALTH}"
    exit 1
}
STATUS=$(echo "$HEALTH" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","?"))' 2>/dev/null || echo "?")
echo "  status: ${STATUS}"

INGEST_FRESH=$(echo "$HEALTH" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ingest_fresh","?"))' 2>/dev/null || echo "?")
echo "  ingest_fresh: ${INGEST_FRESH}"

echo "  sources:"
echo "$HEALTH" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for name, state in d.get("sources",{}).items():
    print(f"    {name}: {state}")
' 2>/dev/null
echo ""

# ---- 3. publish_status ----
echo "--- 最近 publish ---"
PS_FILE="${DATA_DIR}/publish_status.json"
if [ -f "$PS_FILE" ]; then
    python3 -c "
import json
with open('${PS_FILE}') as f:
    d=json.load(f)
print(f\"  status: {d.get('status','?')}  selected: {d.get('selected_count',0)}  pushed: {d.get('pushed','?')}\")
print(f\"  errors: {d.get('errors',[])}\")
print(f\"  recorded: {d.get('recorded_at','?')}\")
" 2>/dev/null
else
    echo "  (尚无 publish 记录)"
fi
echo ""

# ---- 4. 候选池 ----
echo "--- 候选池 ---"
CAND_FILE="${DATA_DIR}/ingestion/${TODAY}/candidates.jsonl"
if [ -f "$CAND_FILE" ]; then
    CAND_COUNT=$(wc -l < "$CAND_FILE" | tr -d ' ')
    echo "  今日候选: ${CAND_COUNT} 条"
    python3 -c "
import json
from collections import Counter
with open('${CAND_FILE}') as f:
    items = [json.loads(l) for l in f]
cats = Counter(i['category'] for i in items)
print(f'  分类: {dict(cats)}')
" 2>/dev/null
else
    echo "  (今日尚无候选)"
fi
echo ""

# ---- 5. 最新 digest ----
echo "--- 最新 digest ---"
python3 -c "
import json, os
dd = '${DATA_DIR}'
found = False
for d in sorted(os.listdir(dd), reverse=True):
    p = os.path.join(dd, d, 'ai_digest.json')
    if os.path.exists(p):
        with open(p) as f:
            data = json.load(f)
        items = data.get('headline_items', [])
        cats = {}
        for it in items:
            cats[it.get('display_category','AI')] = cats.get(it.get('display_category','AI'),0)+1
        print(f'  日期: {data[\"date\"]} | 条数: {len(items)} | 分布: {cats}')
        empty_labels = sum(1 for it in items if not it.get('topic_label'))
        if empty_labels:
            print(f'  topic_label 为空: {empty_labels}/{len(items)}')
        gh = data.get('github_projects', [])
        if gh:
            print(f'  GitHub: {len(gh)} 项目')
            for g in gh:
                print(f'    {g.get(\"full_name\",\"?\")} 推荐: {g.get(\"recommendation\",\"-\")}')
        found = True
        break
if not found:
    print('  (无 digest 记录)')
" 2>/dev/null
echo ""

# ---- 6. GitHub 曝光 ----
echo "--- GitHub 曝光记录 ---"
EXP_FILE="${DATA_DIR}/github/exposure.json"
if [ -f "$EXP_FILE" ]; then
    EXP_COUNT=$(python3 -c "import json; print(len(json.load(open('${EXP_FILE}'))))" 2>/dev/null || echo "?")
    echo "  已曝光项目: ${EXP_COUNT}"
else
    echo "  (无曝光记录)"
fi
echo ""

echo "========================================"
echo "  验证完成"
echo "========================================"
