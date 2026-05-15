#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/Claw_news"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Claw_news 部署定时推送${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ---- 1. 检查目录 ----
if [ ! -f "$INSTALL_DIR/main.py" ]; then
    echo -e "${RED}未找到项目文件，请先 clone:${NC}"
    echo "  cd /opt && git clone https://github.com/djejjd/Claw_news.git"
    exit 1
fi
cd "$INSTALL_DIR"

# ---- 2. 创建 venv + 装依赖 ----
echo -e "${YELLOW}[1/4] 安装依赖...${NC}"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt
echo -e "  ${GREEN}✓${NC} 完成"

# ---- 3. 配置文件 ----
echo -e "${YELLOW}[2/4] 检查配置...${NC}"
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo -e "  ${RED}请先编辑 config.yaml 填入 webhook key，然后重新运行此脚本${NC}"
    echo "  vim $INSTALL_DIR/config.yaml"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} config.yaml 就绪"

# ---- 4. 设置 crontab ----
echo -e "${YELLOW}[3/4] 设置 crontab...${NC}"
CRON_MORNING="0 9 * * * cd $INSTALL_DIR && ./venv/bin/python main.py --period morning >> $INSTALL_DIR/data/cron.log 2>&1"
CRON_EVENING="0 21 * * * cd $INSTALL_DIR && ./venv/bin/python main.py --period evening >> $INSTALL_DIR/data/cron.log 2>&1"

TMP_CRON=$(mktemp)
crontab -l 2>/dev/null | grep -v "Claw_news\|main.py --period" > "$TMP_CRON" || true
echo "$CRON_MORNING" >> "$TMP_CRON"
echo "$CRON_EVENING" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm "$TMP_CRON"
echo -e "  ${GREEN}✓${NC} 每天 9:00 早报 / 21:00 晚报"

# ---- 5. 测试推送 ----
echo -e "${YELLOW}[4/4] 测试推送...${NC}"
./venv/bin/python main.py --period morning 2>&1

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  部署完成，去手机确认收到消息${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  日志:  tail -f $INSTALL_DIR/data/cron.log"
echo "  手动:  cd $INSTALL_DIR && ./venv/bin/python main.py --period evening"
