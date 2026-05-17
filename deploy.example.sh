#!/bin/bash
# Claw_news 部署参考模板
# 用法: bash deploy.example.sh
#
# 此脚本展示两种部署方式的验证步骤，不负责完整部署到生产环境。

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[验证] 旧 CLI 模式${NC}"
echo "  旧 CLI 入口仍可用于验证:"
echo "  ./venv/bin/python main.py --period morning --dry-run"
echo ""

echo -e "${GREEN}[方式 A] 服务内 APScheduler (推荐)${NC}"
echo "  1. 配置 .env 文件:"
echo "     cp .env.example .env"
echo "     # 编辑 .env 填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / WECOM_WEBHOOK_URL"
echo ""
echo "  2. 启动服务:"
echo "     docker compose up -d --build"
echo ""
echo "  3. 检查健康:"
echo "     curl http://127.0.0.1:8000/health"
echo ""
echo "  4. 查看日志:"
echo "     docker compose logs -f"
echo ""
echo "  服务会自动在 09:00 / 14:00 / 20:00 运行新闻流水线"
echo ""

echo -e "${YELLOW}[方式 B] 外部 HTTP 调度 (迁移过渡)${NC}"
echo "  如果当前不想启用内部 scheduler，可以在服务器上用 cron / systemd timer:"
echo "    curl -X POST http://127.0.0.1:8000/run/news"
echo ""
echo "  注意: 同时启用内部 scheduler 和外部定时器会导致重复推送。"
echo "  如果使用外部调度，请确保容器只运行 uvicorn 不带 scheduler。"
echo ""

echo -e "${GREEN}本脚本只是参考模板，不等于唯一生产方案。${NC}"
