# Claw_news 服务器部署指南

## 1. 服务器要求

| 项目 | 最低配置 |
|------|----------|
| OS | Ubuntu 20.04+ / Debian 11+ / CentOS 8+ |
| CPU | 1 核 |
| 内存 | 512 MB |
| 磁盘 | 2 GB |
| 网络 | 能访问外网（RSS 源 + LLM API + 企微 webhook） |
| 软件 | Docker 20.10+ + docker compose v2 |

## 2. 服务器环境检查

登录服务器后，先跑一遍状态检查：

```bash
echo "=== OS ===" && cat /etc/os-release | head -2
echo "=== git ===" && git --version 2>&1 || echo "【未安装】"
echo "=== Docker ===" && docker --version 2>&1 || echo "【未安装】"
echo "=== docker compose ===" && docker compose version 2>&1 || echo "【未安装】"
echo "=== curl ===" && curl --version | head -1 2>&1 || echo "【未安装】"
echo "=== 磁盘 ===" && df -h /opt 2>/dev/null || df -h /
```

## 3. 安装所需工具

| 工具 | 用途 | 必装 | 安装命令 |
|------|------|------|----------|
| git | 拉代码、更新 | **是** | `sudo apt install -y git` |
| Docker | 容器运行 | **是** | 见下方详细步骤 |
| docker compose | 服务编排 | **是** | Docker 自带（`docker compose`） |
| curl | 健康检查、手动触发 | 建议 | `sudo apt install -y curl` |

### 3.1 一行装齐 git + curl

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y git curl

# CentOS / RHEL
sudo yum install -y git curl
```

### 3.2 安装 Docker

```bash
# 官方脚本（自动适配发行版）
curl -fsSL https://get.docker.com | sudo sh

# 将当前用户加入 docker 组（否则每次要 sudo）
sudo usermod -aG docker $USER
# 退出重新 SSH 登录使权限生效
```

### 3.3 验证安装

```bash
docker --version        # 应 >= 20.10
docker compose version  # 应出现版本号
docker run hello-world  # 冒烟测试
```

### 3.4 开放端口（如有防火墙）

```bash
sudo ufw allow 8000/tcp       # ufw
sudo firewall-cmd --add-port=8000/tcp --permanent && sudo firewall-cmd --reload  # firewalld
```

> 如果只在服务器本地调用（外部 cron curl），不需要开放端口。

## 4. 部署代码

不再推荐把“服务器直接 `git pull` GitHub”作为主部署路径，尤其是在腾讯云等云服务器访问 GitHub 不稳定时。

推荐顺序：

1. **方案 A：本地或 CI 拉代码，再用 `scp/rsync` 同步到服务器**（推荐）
2. **方案 B：GitHub Actions 构建后交付到服务器**（进阶）
3. **方案 C：服务器直接 `git pull`**（仅作备选）

### 4.0 本次推荐流程

如果你采用“本地 pull，然后上传到服务器”的方式，建议固定为下面这条链路：

1. 本地仓库切到 `main`
2. 本地执行 `git pull --ff-only origin main`
3. 用 `rsync` 同步工作区到服务器
4. 服务器恢复 `.env`
5. 服务器执行 `docker compose up -d --build`
6. 用 `/health` 验证服务状态

这条流程的优点是：

1. 不依赖服务器直接访问 GitHub
2. 不会因为云主机网络波动卡在 `git pull`
3. 可以明确区分“代码同步”和“运行配置恢复”

如果你已经确认正式环境固定使用当前这台腾讯云主机，可以直接使用仓库里的正式部署脚本：

```bash
bash deploy-prod.sh
```

脚本会做四件事：

1. 检查本地工作区是否干净
2. 用 `rsync` 同步代码到 `/home/ubuntu/code/Claw_news`
3. 在远端用 `DOCKER_CONFIG=/tmp/docker-no-proxy` 构建并重启 `claw-news`
4. 用 `/health` 验证服务状态

默认情况下，`deploy-prod.sh` 会为腾讯云构建阶段传入：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_EXTRA_INDEX_URL=https://pypi.org/simple
```

如果你已经有可用的企业代理或自建 PyPI 源，可以在本地执行脚本前覆盖这两个变量。

### 4.1 方案 A：`scp/rsync` 同步代码到服务器（推荐）

适用场景：

1. 服务器访问 GitHub 不稳定
2. 你本地或 CI 能稳定访问 GitHub
3. 你希望服务器只负责运行，不直接依赖 GitHub 网络

首次同步：

```bash
# 在本地执行
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude '.env' \
  --exclude 'data' \
  ./ user@your-server:/opt/Claw_news/
```

后续更新：

```bash
# 在本地执行
git pull
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude '.env' \
  --exclude 'data' \
  ./ user@your-server:/opt/Claw_news/
```

如果没有 `rsync`，也可以使用：

```bash
scp -r /path/to/Claw_news user@your-server:/opt/Claw_news
```

同步完成后，在服务器执行：

```bash
cd /opt/Claw_news
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_EXTRA_INDEX_URL=https://pypi.org/simple
docker compose up -d --build
```

如果服务器上原本依赖一个备份 `.env`，先恢复配置再启动：

```bash
cp /path/to/backup/.env /opt/Claw_news/.env
chmod 600 /opt/Claw_news/.env
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_EXTRA_INDEX_URL=https://pypi.org/simple
docker compose up -d --build
```

### 4.2 方案 B：GitHub Actions / CI 交付到服务器（进阶）

适用场景：

1. 你希望减少手工部署
2. 你已经有 CI/CD 密钥和服务器凭据管理
3. 你希望服务器不直接依赖 GitHub 联通性

常见做法：

1. GitHub Actions 拉代码并跑测试
2. 生成构建产物或准备部署目录
3. 通过 `scp`、`rsync` 或 SSH 发布到服务器
4. 在服务器上执行 `docker compose up -d --build`

推荐原则：

1. CI 负责“拉代码和校验”
2. 服务器负责“接收产物和运行”

### 4.3 方案 C：服务器直接 `git pull`（备选）

只在以下条件同时满足时使用：

1. 服务器访问 GitHub 稳定
2. 认证链路稳定
3. 你接受服务器直接依赖 GitHub 可用性

全新服务器：

```bash
cd /opt
git clone https://github.com/djejjd/Claw_news.git
cd Claw_news
```

已有代码的服务器：

```bash
cd /opt/Claw_news
git pull
```

> 如果 `curl -I https://github.com` 或 `git fetch origin` 在服务器上卡住，就不要继续使用本方案，切回方案 A 或方案 B。

## 5. 配置文件

### 5.1 创建 .env（新服务用）

```bash
cd /opt/Claw_news
cp .env.example .env
```

编辑 `.env`，填入真实值：

```bash
vim .env
```

```dotenv
# ---- 新 AI 助手服务配置 ----
LLM_API_KEY=sk-your-real-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE
TZ=Asia/Shanghai
NEWS_RSS_URLS=https://www.qbitai.com/feed,https://sspai.com/feed
AI_RSS_MODE=append
AI_RSS_FEEDS=openai_blog|https://openai.com/news/rss.xml
```

如果服务器上有历史 `.env` 备份，优先恢复备份，再按需补差异字段，而不是直接从模板重建。这样可以避免把已有的 LLM / WeCom / RSS 配置误删。

### 5.2 准备验证环境配置

正式环境使用 `.env + docker-compose.yml`。  
验证环境使用 `.env.verify + docker-compose.verify.yml`：

```bash
cp .env.example .env.verify
# 编辑 .env.verify，填入验证环境使用的 LLM 与 WeCom 配置
```

### 5.3 权限

```bash
chmod 600 .env .env.verify   # 防止其他用户读取密钥
```

## 6. 启动服务

```bash
cd /opt/Claw_news
docker compose up -d --build
```

首次构建约 2-3 分钟。

后续更新方式：

1. 方案 A：先在本地 `rsync/scp` 同步，再在服务器执行 `docker compose up -d --build`
2. 方案 B：由 CI 发布后，在服务器执行 `docker compose up -d --build`
3. 方案 C：先 `git pull`，再 `docker compose up -d --build`

## 7. 验证服务

```bash
# 健康检查
curl http://127.0.0.1:8000/health
# 预期: 返回 status=healthy，并带有最近一次 ingest 的时间、条数、成功源、失败源

# 服务信息
curl http://127.0.0.1:8000/
# 预期: {"service":"Claw_news AI Assistant",...}

# 手动触发一次
curl -X POST http://127.0.0.1:8000/run/news
```

验证环境可用下面的组合命令单独启动：

```bash
docker compose --env-file .env.verify -f docker-compose.yml -f docker-compose.verify.yml up -d --build
```

## 8. 日常运维

### 查看日志

```bash
docker compose logs -f              # 实时跟踪
docker compose logs --tail=100      # 最近 100 行
docker compose logs | grep ERROR    # 只看错误
```

### 重启服务

```bash
docker compose restart              # 快速重启
docker compose down && docker compose up -d  # 完全重建
```

### 停止服务

```bash
docker compose down
```

### 更新代码

```bash
cd /opt/Claw_news
docker compose up -d --build
```

如果你使用方案 A，再先在本地同步代码到服务器；如果你使用方案 C，再先执行：

```bash
git pull
```

建议把更新流程固定成：

1. 本地拉最新 `main`
2. 本地同步到服务器
3. 服务器恢复 `.env`
4. 服务器重建容器
5. 检查 `/health`

### 定时触发验证

APScheduler 在服务内自动运行：09:00 发布，每 30 分钟采集候选池，无需外部 cron。要确认定时任务在运行，看日志中是否有：

```text
Added job "NewsAgent.run_once" to job store "default"
Scheduler started
```

## 9. 可选：外部 cron 触发

如果不想用内部 scheduler，而是用服务器 cron：

编辑 `app/main.py`，注释掉 lifespan 中的 `scheduler.start()`，然后：

```bash
crontab -e
```

```text
0 9 * * * curl -X POST http://127.0.0.1:8000/run/news
0 14 * * * curl -X POST http://127.0.0.1:8000/run/news
0 20 * * * curl -X POST http://127.0.0.1:8000/run/news
```

> 注意：同时启用内部 scheduler 和外部 cron 会导致重复推送！

## 10. 常见问题

### 服务起不来

```bash
# 看启动日志
docker compose logs --tail=50

# 常见原因：
# 1. .env 未创建或缺少必填字段 → 检查 .env
# 2. 端口 8000 被占用 → lsof -i :8000
# 3. Docker 权限不足 → sudo usermod -aG docker $USER
```

### 抓取不到新闻

```bash
# 查看容器内是否能访问 RSS 源
docker compose exec claw-news curl -I https://www.qbitai.com/feed

# 手动触发看日志
curl -X POST http://127.0.0.1:8000/run/news
docker compose logs --tail=20
```

### LLM 调用失败

检查 `.env` 中的 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 是否正确，以及服务器能否访问该 API：

```bash
docker compose exec claw-news curl -I $LLM_BASE_URL
```

### 企业微信推送失败

确认 `WECOM_WEBHOOK_URL` 中的 key 未过期。在企微群里重新添加机器人获取新 key。

### 磁盘空间

`data/` 目录存储运行状态，定期检查：

```bash
du -sh /opt/Claw_news/data/
```

## 11. LLM 供应商示例

只要支持 OpenAI-compatible 接口即可，修改 `.env` 中的三个变量：

| 供应商 | LLM_BASE_URL | LLM_MODEL 示例 |
|--------|-------------|---------------|
| DeepSeek | https://api.deepseek.com | deepseek-chat |
| 通义千问 | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| 智谱 GLM | https://open.bigmodel.cn/api/paas/v4 | glm-4-flash |
| OpenAI | https://api.openai.com/v1 | gpt-4.1-mini |
| Ollama（本地） | http://localhost:11434/v1 | qwen2.5:7b |
