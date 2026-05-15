#!/bin/bash
# Claw_news 部署模板
# 用法: bash deploy.example.sh
#
# 此脚本只做环境安装和 dry-run 验证，不会触发真实推送。
# 如需真实推送，请手动执行: ./venv/bin/python main.py --period morning
#
# 依赖:
#   - Python 3.11+
#   - 已配置 config.yaml 或 PUSHER_WECOM_WEBHOOK 环境变量

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[1/3] 安装依赖...${NC}"
python3 -m venv venv
./venv/bin/pip install -e ".[dev]"

echo -e "${GREEN}[2/3] 运行测试...${NC}"
./venv/bin/pytest -v

echo -e "${YELLOW}[3/3] 验证 dry-run...${NC}"
./venv/bin/python main.py --period morning --dry-run

echo -e "${GREEN}部署验证完成。${NC}"
echo -e "${YELLOW}如需真实推送，请手动执行: ./venv/bin/python main.py --period morning${NC}"
