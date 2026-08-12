# Task007 Design: SSH 反向隧道代理外国源

## 背景

项目部署在腾讯云国内服务器（Ubuntu，Docker），境外数据源 `huggingface.co` 和 `github.com` 被墙。采集器 `HfDailyPapersCollector` 和 `GitHubCollector` 无法直连，每次采集触发 15 秒 TCP 超时，日志显示 `curl_cffi.requests.exceptions.Timeout: Failed to perform, curl: (28) Connection timed out`。

项目已在 `collectors/huggingface.py` 中预留 `proxy` 参数，在 `app/scheduler/jobs.py:run_ingest()` 中通过 `os.getenv("HF_PROXY", "").strip() or None` 读取环境变量。本设计聚焦于**提供可用的代理地址**，不修改任何项目代码。

## 方案选择

| 方案 | 代理来源 | 成本 | 维护 | 选用 |
|------|---------|------|------|------|
| A. SSH 反向隧道 | 本地 Clash Verge | 免费 | 需本地保持在线 | ✅ |
| B. 服务器装代理客户端 | 代理订阅链接 | 免费 | 需管理服务器端客户端 | ❌ |
| C. 第三方代理服务 | 付费中转服务 | 按月付费 | 无需维护 | ❌ |

选用方案 A，原因是：本地已有 Clash Verge 运行，零成本；SSH 已在日常使用，3 条命令即可完成；隧道基于 127.0.0.1 环回，安全可靠。

## 架构

```
┌──────────────────────┐    SSH -R 8899:127.0.0.1:7897  ┌──────────────────┐
│  腾讯云服务器         │◄──────────────────────────────►│  本地 Mac        │
│  Ubuntu 22.04        │                                │  Clash Verge     │
│                      │                                │                  │
│  .env:               │                                │  127.0.0.1:7897  │
│  HF_PROXY=           │                                │  (HTTP/SOCKS5)   │
│  http://127.0.0.1:8899│                               │       │          │
│       │              │                                │       ▼          │
│       ▼              │                                │  境外出口节点    │
│  Docker 容器:        │                                │  ────────────────│
│  curl_cffi ──────────│── proxy request ── SSH 加密 ─────► huggingface.co │
│  httpx     ──────────│── proxy request ── SSH 加密 ─────► github.com     │
└──────────────────────┘                                └──────────────────┘
```

## 数据流

1. Docker 容器内 `HfDailyPapersCollector.collect()` 调用 `curl_cffi.AsyncSession().get()`
2. `proxies={"http": "127.0.0.1:8899", "https": "127.0.0.1:8899"}` 设定代理
3. Docker 容器（host 网络）通过 `127.0.0.1:8899` 连接到宿主机 SSHD 监听的端口
4. SSHD 反向转发到本地 Mac `127.0.0.1:7897`
5. Clash Verge 根据规则匹配，将 `huggingface.co` 流量路由到境外节点
6. 响应原路返回容器

## 安全

- 隧道仅监听 `127.0.0.1`，不暴露到公网
- SSH 加密保护数据传输
- 腾讯云侧只能看到 SSH 流，无法识别代理内容
- 对腾讯云来说，服务器访问的是一台 Mac 家用宽带（SSH 客户端），不存在出境流量
- 出口 IP 是本地 Mac IP，非腾讯云 IP

## 容错设计

- HuggingFace 单源采集失败 → `safe_collect()` 捕获，不影响 RSS/GitHub 等其他源
- SSH 隧道断开 → Docker 容器内代理请求返回 connection refused，非 hang
- 本地 Mac 关机/休眠 → 同断开情况，服务降级但继续运行
- 容器的 `source_failures` 会记录失败原因，可通过日志排查

## 关键技术点

### SSH 反向隧道

```bash
ssh -R 8899:127.0.0.1:7897 -N -o ServerAliveInterval=60 user@server
```

`-R` 参数语义：服务器监听 `127.0.0.1:8899`，该端口的任意连接被转发回本地机器，再由本地机器连接到 `127.0.0.1:7897`。

### 心跳保活

`ServerAliveInterval=60` 每 60 秒发送 SSH 心跳包。配合客户端 `ServerAliveCountMax=3`，3 次无响应则断开。autossh 可在此基础上自动重连。

### Docker 网络注意

Docker 容器内的 `127.0.0.1:8899` 应能访问宿主机端口，前提是容器未使用自定义 bridge 网络导致 127.0.0.1 指向容器自身。当前 `docker-compose.yml` 使用默认网络，`ports` 映射到宿主机，容器内访问宿主机环回需要确认网络模式。如遇不通，可改为 `host.docker.internal` 或使用宿主机内网 IP。
