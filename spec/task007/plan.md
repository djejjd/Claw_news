# Task007 Plan: SSH 反向隧道代理实施

## 前置确认

- [ ] 本地 Clash Verge 已开启「允许局域网连接」
- [ ] 本地可 SSH 到服务器：`ssh user@server-ip`
- [ ] 服务器项目路径：`~/code/Claw_news`

## 步骤

### 步骤 1：验证 Clash 代理可用

在本地 Mac 终端执行：

```bash
# 测试 Clash 代理是否工作
curl -x http://127.0.0.1:7897 -I https://huggingface.co
# 预期: HTTP/2 200 或 HTTP/2 302
```

### 步骤 2：建立 SSH 反向隧道

在本地 Mac 终端执行（新开一个窗口，保持运行）：

```bash
ssh -R 8899:127.0.0.1:7897 -N -o ServerAliveInterval=60 user@server-ip
```

- `-R 8899:127.0.0.1:7897`：服务器 `127.0.0.1:8899` 的流量转发到本机 `127.0.0.1:7897`
- `-N`：不执行远程命令
- `ServerAliveInterval=60`：每 60 秒发送心跳包

### 步骤 3：服务器验证隧道连通

SSH 登录服务器，另开一个终端：

```bash
# 验证代理隧道是否连通
curl -x http://127.0.0.1:8899 -I https://huggingface.co
# 预期: HTTP/2 200 或 HTTP/2 302（首请求可能较慢）

# 如果失败（Connection refused），检查：
ss -tlnp | grep 8899  # 确认 SSH 已监听该端口
```

### 步骤 4：配置服务器 .env

在服务器上：

```bash
cd ~/code/Claw_news
echo '
HF_PROXY=http://127.0.0.1:8899
' >> .env

# 确认配置
grep HF_PROXY .env
```

### 步骤 5：重建容器并验证

```bash
cd ~/code/Claw_news
docker compose up -d --build

# 看 HuggingFace 采集结果
docker compose logs --tail=50 | grep -E "huggingface|candidates"
# 预期: 不再出现 Timeout 错误，item_count 中应包含 HF 条目
```

### 步骤 6：安装并配置 autossh 保活（可选）

```bash
brew install autossh

# 替代步骤 2 的 ssh 命令，自动重连
autossh -M 0 \
  -o "ServerAliveInterval=60" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -R 8899:127.0.0.1:7897 \
  -N user@server-ip
```

`-M 0`：禁用 autossh 自身监控端口，仅依赖 SSH 心跳。

### 步骤 7：验证 HF 候选池

```bash
# 等 ingest 跑完一轮，检查候选池索引
cat ~/code/Claw_news/data/ingestion/$(date +%F)/index.json | python3 -m json.tool
# source_failures 中不应有 huggingface 失败记录
```

## 最终验证

```bash
# 服务器上
curl -x http://127.0.0.1:8899 -I https://huggingface.co
docker compose logs | grep -i "huggingface" | grep -v "failure\|error\|timeout"
ls data/ingestion/$(date +%F)/candidates.jsonl && wc -l data/ingestion/$(date +%F)/candidates.jsonl
```

## 验收标准

1. `curl -x http://127.0.0.1:8899 -I https://huggingface.co` 返回 HTTP 200/302
2. `HF_PROXY=http://127.0.0.1:8899` 已写入服务器 `.env`
3. Docker 容器日志中不再出现 `curl_cffi.requests.exceptions.Timeout` for HuggingFace
4. 候选池 `candidates.jsonl` 中包含 `huggingface` 来源条
