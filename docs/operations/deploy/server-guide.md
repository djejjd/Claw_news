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

## 2. 服务器初始化

### 安装 Docker（Ubuntu/Debian）

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sudo sh

# 将当前用户加入 docker 组（免 sudo）
sudo usermod -aG docker $USER

# 重新登录使权限生效，或执行
newgrp docker

# 验证
docker --version
docker compose version
```

CentOS/RHEL 使用 `sudo yum install -y docker`，其余步骤相同。

### 开放端口（如有防火墙）

```bash
# ufw
sudo ufw allow 8000/tcp

# firewalld
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --reload
```

> 如果只在服务器本地调用（外部 cron curl），不需要开放端口。

## 3. 部署代码

### 方式 A：git clone（推荐，方便更新）

```bash
cd /opt
git clone https://github.com/djejjd/Claw_news.git
cd Claw_news
```

### 方式 B：scp 上传

```bash
# 在本地执行
scp -r /path/to/Claw_news user@your-server:/opt/Claw_news
```

## 4. 配置文件

### 4.1 创建 .env

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
```

### 4.2 创建 config.yaml（旧 CLI 备用）

```bash
cp config.example.yaml config.yaml
# 编辑 webhook 或通过环境变量 PUSHER_WECOM_WEBHOOK 覆盖
```

### 4.3 权限

```bash
chmod 600 .env config.yaml   # 防止其他用户读取密钥
```

## 5. 启动服务

```bash
cd /opt/Claw_news
docker compose up -d --build
```

首次构建约 2-3 分钟。之后更新代码只需要：

```bash
git pull
docker compose up -d --build
```

## 6. 验证服务

```bash
# 健康检查
curl http://127.0.0.1:8000/health
# 预期: {"status":"healthy"}

# 服务信息
curl http://127.0.0.1:8000/
# 预期: {"service":"Claw_news AI Assistant",...}

# 手动触发一次
curl -X POST http://127.0.0.1:8000/run/news
```

## 7. 日常运维

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
git pull
docker compose up -d --build
```

### 定时触发验证

APScheduler 在服务内自动运行（09:00 / 14:00 / 20:00），无需外部 cron。要确认定时任务在运行，看日志中是否有：

```
Added job "NewsAgent.run_once" to job store "default"
Scheduler started
```

## 8. 可选：外部 cron 触发

如果不想用内部 scheduler，而是用服务器 cron：

编辑 `app/main.py`，注释掉 lifespan 中的 `scheduler.start()`，然后：

```bash
crontab -e
```

```
0 9 * * * curl -X POST http://127.0.0.1:8000/run/news
0 14 * * * curl -X POST http://127.0.0.1:8000/run/news
0 20 * * * curl -X POST http://127.0.0.1:8000/run/news
```

> 注意：同时启用内部 scheduler 和外部 cron 会导致重复推送！

## 9. 常见问题

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

## 10. LLM 供应商示例

只要支持 OpenAI-compatible 接口即可，修改 `.env` 中的三个变量：

| 供应商 | LLM_BASE_URL | LLM_MODEL 示例 |
|--------|-------------|---------------|
| DeepSeek | https://api.deepseek.com | deepseek-chat |
| 通义千问 | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| 智谱 GLM | https://open.bigmodel.cn/api/paas/v4 | glm-4-flash |
| OpenAI | https://api.openai.com/v1 | gpt-4.1-mini |
| Ollama（本地） | http://localhost:11434/v1 | qwen2.5:7b |
