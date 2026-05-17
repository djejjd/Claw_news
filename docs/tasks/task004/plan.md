# AI 助手服务交付完善实施计划

> **给执行开发的 agent：** 本计划只覆盖 Task004，目标是交付完善，不是功能扩张。执行时必须逐任务推进，并在每个任务后做契约审查与质量审查。

**目标：** 让 AI 助手服务在链接可用性、调度模式切换、验证闭环三个方面达到可交付状态。

**架构：** 保持 Task003 既有服务结构不变，只在配置、推送格式、入口控制、文档与测试上做增强。

**技术栈：** Python 3.11、FastAPI、APScheduler、httpx、pytest、Docker、GitHub Actions

---

## 文件结构

**重点修改：**
- `app/config.py`
- `app/main.py`
- `app/tools/llm.py`
- `app/tools/wecom.py`
- `.env.example`
- `README.md`
- `deploy.example.sh`
- `.github/workflows/ci.yml`
- `tests/test_app_llm.py`
- `tests/test_app_wecom.py`
- `tests/test_app_api.py`

---

## 任务 1：增加 scheduler 显式开关

**文件：**
- 修改：`app/config.py`
- 修改：`app/main.py`
- 修改：`.env.example`
- 修改：`tests/test_app_api.py`

- [ ] **步骤 1：先写失败测试**

测试必须覆盖：
- scheduler 开关开启时启动
- scheduler 开关关闭时不启动

- [ ] **步骤 2：实现配置项**

新增：
- `ENABLE_INTERNAL_SCHEDULER`

默认值：
- `true`

- [ ] **步骤 3：在 `app.main` 中接入开关**

要求：
- `true` 时启动 scheduler
- `false` 时不启动 scheduler

- [ ] **步骤 4：运行测试**

```bash
pytest tests/test_app_api.py -v
```

- [ ] **步骤 5：提交**

```bash
git add app/config.py app/main.py .env.example tests/test_app_api.py
git commit -m "feat: add internal scheduler toggle"
```

---

## 任务 2：修正原文链接可用性

**文件：**
- 修改：`app/tools/llm.py`
- 按需修改：`app/tools/wecom.py`
- 修改：`tests/test_app_llm.py`
- 修改：`tests/test_news_agent.py`

- [ ] **步骤 1：先写失败测试**

测试必须覆盖：
- 每条新闻在最终消息中都包含可直接使用的原文链接

- [ ] **步骤 2：调整摘要模板**

推荐输出：

```text
1. 标题
   - 原文链接：https://...
   - 核心内容：...
   - 重要性：...
   - 趋势判断：...
```

- [ ] **步骤 3：若改消息类型，补充验证**

如果从 `text` 改到 `markdown`：
- 必须补测试与文档证据

- [ ] **步骤 4：运行测试**

```bash
pytest tests/test_app_llm.py tests/test_news_agent.py -v
```

- [ ] **步骤 5：提交**

```bash
git add app/tools/llm.py app/tools/wecom.py tests/test_app_llm.py tests/test_news_agent.py
git commit -m "feat: make source links directly usable in pushed messages"
```

---

## 任务 3：补齐验证闭环与文档

**文件：**
- 修改：`README.md`
- 修改：`deploy.example.sh`
- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：更新 README**

必须写清楚：
- `ENABLE_INTERNAL_SCHEDULER` 的含义
- 两种部署模式
- 默认模式
- 原文链接的展示方式

- [ ] **步骤 2：更新部署脚本**

必须说明：
- 如何切换 scheduler 模式
- 外部 HTTP 调度如何配置

- [ ] **步骤 3：更新 CI**

要求：
- 服务模式测试纳入 CI
- 依赖安装步骤与本地说明一致

- [ ] **步骤 4：验证**

```bash
pytest -q
docker compose config
```

- [ ] **步骤 5：提交**

```bash
git add README.md deploy.example.sh .github/workflows/ci.yml
git commit -m "docs: harden service delivery docs and verification"
```

---

## 审查关卡

### 契约审查

必须检查：

1. 是否增加了显式 scheduler 开关
2. 原文链接是否真正可用
3. 文档是否与实现一致

### 质量审查

必须检查：

1. 测试是否覆盖新行为
2. 未引入 Task004 范围外能力
3. 未破坏 Task003 既有链路

---

## 最终验证

```bash
pytest -q
python main.py --period morning --dry-run
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/run/news
docker compose config
```

---

## 结论

Task004 完成后，服务不会“功能更多”，但会：

1. 更容易部署
2. 更容易切换调度模式
3. 更容易验证
4. 更符合实际使用场景
