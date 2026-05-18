# Task007 Plan: SSH 反向隧道代理实施

## 前置确认

- [ ] 本地 Clash Verge 已开启「允许局域网连接」（Settings → Allow LAN）
- [ ] 本地可 SSH 到服务器：`ssh user@server-ip`
- [ ] 服务器项目已部署：`~/code/Claw_news`
- [ ] 服务器 `.env` 中其他配置已就绪（LLM_API_KEY 等）

## 步骤 1：验证本地 Clash 代理可用

**位置：** 本地 Mac 终端

```bash
curl -x http://127.0.0.1:7897 -I https://huggingface.co
```

预期：`HTTP/2 200` 或 `HTTP/2 302`

失败处理：确认 Clash Verge 已开启 Allow LAN，端口号是否为 7897。

## 步骤 2：验证服务器 SSH 隧道配置

**位置：** 服务器终端

```bash
# 检查 SSHD 是否允许 GatewayPorts（反向隧道需要此配置）
sudo grep -i 'GatewayPorts\|AllowTcpForwarding' /etc/ssh/sshd_config

# 若 GatewayPorts 为 no 或无此行，添加：
echo 'GatewayPorts yes' | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
```

如果不允许（或不想）修改服务器 SSHD 配置，可跳过。`GatewayPorts yes` 只影响能否让非 localhost 的连接访问转发端口，对于本方案（仅 localhost 访问）不是必需的。

## 步骤 3：建立 SSH 反向隧道

**位置：** 本地 Mac 终端（新开一个窗口，保持运行）

```bash
ssh -R 8899:127.0.0.1:7897 -N -o ServerAliveInterval=60 user@server-ip
```

参数说明：
- `-R 8899:127.0.0.1:7897`：远端 8899 → 本机 7897
- `-N`：不执行远程命令，仅做转发
- `ServerAliveInterval=60`：每 60 秒心跳

确认隧道存活：本地终端不报错即为成功。

## 步骤 4：服务器验证隧道连通

**位置：** 服务器终端（另开一个窗口）

```bash
# 测试代理连通性
curl -x http://127.0.0.1:8899 -I https://huggingface.co

# 确认端口在监听
ss -tlnp | grep 8899
```

预期：curl 返回 HTTP 200/302，ss 显示 127.0.0.1:8899 在 LISTEN。

若 `Connection refused`：确认步骤 3 的 SSH 隧道仍在运行。

## 步骤 5：配置服务代理

**位置：** 服务器终端

```bash
cd ~/code/Claw_news

# 追加代理配置
grep -q 'HF_PROXY' .env \
  && sed -i 's|^HF_PROXY=.*|HF_PROXY=http://127.0.0.1:8899|' .env \
  || echo 'HF_PROXY=http://127.0.0.1:8899' >> .env

# 确认结果
grep HF_PROXY .env
```

## 步骤 6：重建容器

**位置：** 服务器终端

```bash
cd ~/code/Claw_news
docker compose up -d --build
```

## 步骤 7：验证 HuggingFace 采集

**位置：** 服务器终端

```bash
# 等 30 秒让 ingest 跑一轮
sleep 30

# 查看日志中 HuggingFace 相关
docker compose logs --tail=100 | grep -i huggingface

# 预期: 不再出现 "Connection timed out" 或 "Timeout" 错误
# 预期: 可能看到 HF paper 标题或采集成功的记录
```

## 步骤 8：验证候选池

```bash
# 检查今日候选池
cat data/ingestion/$(date +%F)/index.json 2>/dev/null | python3 -m json.tool

# 预期: item_count > 0, source_failures 中无 huggingface
```

## 步骤 9：安装 autossh 保活（推荐）

**位置：** 本地 Mac

```bash
# 安装
brew install autossh

# 替代步骤 3 的 ssh 命令（先 Ctrl+C 关掉原隧道）
autossh -M 0 \
  -o "ServerAliveInterval=60" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -R 8899:127.0.0.1:7897 \
  -N user@server-ip
```

`-M 0`：禁用 autossh 监控端口（高版本推荐），仅依赖 SSH 自身心跳。

## 最终验证清单

- [ ] `curl -x http://127.0.0.1:8899 -I https://huggingface.co` 返回 200/302
- [ ] `HF_PROXY=http://127.0.0.1:8899` 存在于 `.env`
- [ ] 容器日志无 `curl_cffi.requests.exceptions.Timeout` for HuggingFace
- [ ] `data/ingestion/YYYY-MM-DD/candidates.jsonl` 含 `huggingface` 来源条
- [ ] `data/ingestion/YYYY-MM-DD/index.json` 的 `source_failures` 无 huggingface

## 回滚

如遇问题，删除 `.env` 中 `HF_PROXY` 行，重建容器即可回退：

```bash
sed -i '/^HF_PROXY=/d' .env
docker compose up -d --build
```

HuggingFace 采集恢复为超时失败，不影响其他采集器。
