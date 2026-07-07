#!/bin/bash
# 腾讯云正式部署脚本
# 固定部署到 ubuntu@124.223.102.241:/home/ubuntu/code/Claw_news

set -euo pipefail

REMOTE_HOST="ubuntu@124.223.102.241"
REMOTE_DIR="/home/ubuntu/code/Claw_news"
REMOTE_DOCKER_CONFIG="/tmp/docker-no-proxy"
HEALTH_URL="http://127.0.0.1:8000/health"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-https://pypi.org/simple}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "本地工作区不干净，请先提交或清理后再部署。"
  exit 1
fi

if ! git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
  echo "当前目录不是 git 仓库。"
  exit 1
fi

echo "[1/4] 同步代码到 ${REMOTE_HOST}:${REMOTE_DIR}"
rsync -az --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'data' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude '.worktrees' \
  ./ "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "[2/4] 远端构建镜像"
ssh -o BatchMode=yes -o ConnectTimeout=8 "${REMOTE_HOST}" \
  "cd '${REMOTE_DIR}' && mkdir -p '${REMOTE_DOCKER_CONFIG}' && PIP_INDEX_URL='${PIP_INDEX_URL}' PIP_EXTRA_INDEX_URL='${PIP_EXTRA_INDEX_URL}' DOCKER_CONFIG='${REMOTE_DOCKER_CONFIG}' docker compose build claw-news"

echo "[3/4] 重启服务并清理 orphan"
ssh -o BatchMode=yes -o ConnectTimeout=8 "${REMOTE_HOST}" \
  "cd '${REMOTE_DIR}' && DOCKER_CONFIG='${REMOTE_DOCKER_CONFIG}' docker compose up -d --remove-orphans"

echo "[4/4] 健康检查"
ssh -o BatchMode=yes -o ConnectTimeout=8 "${REMOTE_HOST}" \
  "cd '${REMOTE_DIR}' && for attempt in \$(seq 1 12); do if curl -fsS --max-time 10 '${HEALTH_URL}'; then exit 0; fi; sleep 5; done; exit 1"
