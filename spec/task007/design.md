# Task007 Design: SSH 反向隧道代理外国源

## 背景

项目部署在腾讯云国内服务器上，无法直接访问 HuggingFace API（`huggingface.co`）和 GitHub API。项目采集器（`HfDailyPapersCollector`）已内置 `proxy` 参数支持，`HF_PROXY` 环境变量可传递代理地址。本设计聚焦于如何提供这个代理，而不是修改项目代码。

## 架构

```
┌─────────────────┐     SSH -R 8899:127.0.0.1:7897     ┌──────────────────┐
│  腾讯云服务器    │ ◄──────────────────────────────────► │  本地 Mac        │
│  (Ubuntu)      │                                      │  (macOS)        │
│                 │                                      │                  │
│  HF_PROXY=      │                                      │  Clash Verge     │
│  127.0.0.1:8899 │                                      │  127.0.0.1:7897  │
│       │         │                                      │       │          │
│       ▼         │                                      │       ▼          │
│  Docker 容器    │                                      │  境外代理出口    │
│  curl_cffi ─────┼─ socks/http proxy ── SSH 隧道 ────────┼─► huggingface.co│
│                 │                                      │  github.com      │
└─────────────────┘                                      └──────────────────┘
```

## 组件

### 本地 Mac 侧

| 组件 | 说明 |
|------|------|
| Clash Verge | 代理客户端，监听 `127.0.0.1:7897`，提供 HTTP/SOCKS5 代理 |
| SSH 客户端 | 建立反向隧道，`ssh -R` 将远程端口映射到本地 |
| autossh（可选） | SSH 隧道保活，断开自动重连 |

### 服务器侧

| 组件 | 说明 |
|------|------|
| SSH 服务端 | 接受反向隧道连接，需启用 `GatewayPorts` |
| `.env` | 配置 `HF_PROXY=http://127.0.0.1:8899` |
| Docker 容器 | 通过 `.env` 读入代理配置，传递给 `curl_cffi` 请求 |

## 数据流

```
1. Docker 容器内 HfDailyPapersCollector 发起采集
2. curl_cffi.AsyncSession 读取 proxies={"http": "127.0.0.1:8899", "https": "127.0.0.1:8899"}
3. 请求经环境变量注入的代理地址 → 服务器 127.0.0.1:8899
4. SSH 隧道反向转发到本地 Mac 127.0.0.1:7897
5. Clash Verge 通过规则匹配，将 huggingface.co 走境外节点
6. 响应原路返回
```

## 安全考量

- 隧道仅在本地回环地址（127.0.0.1）上监听，不暴露到公网
- SSH 加密保护传输内容
- 腾讯云只能看到 SSH 加密流，无法识别代理内容
- 出口 IP 是本地 Mac 的宽带 IP，非腾讯云 IP
- 不触发腾讯云违规检测

## 容错

- HuggingFace 采集失败 → `safe_collect()` 捕获，记录到 `source_failures`，不影响 RSS 等其他采集器
- SSH 隧道断开 → autossh 自动重连，或手动重建
- 本地 Mac 关机 → HuggingFace 采集降级为超时失败，服务继续提供 RSS 源的 AI 日报
