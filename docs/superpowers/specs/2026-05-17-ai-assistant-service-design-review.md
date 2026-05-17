# AI 助手服务设计审查结论

## 1. 审查范围

本次审查基于以下文档与当前仓库事实：

1. `spec/task003/spec.md`
2. `docs/superpowers/specs/2026-05-17-ai-assistant-service-design.md`
3. `docs/superpowers/plans/2026-05-17-ai-assistant-service-implementation-plan.md`
4. 当前仓库现状
   - 现有入口：`main.py`
   - 现有采集层：`collectors/`
   - 现有聚合层：`aggregator/`
   - 现有推送层：`pusher/`
   - 现有状态层：`infra/storage/`

本报告只做设计审查，不包含代码实现。

---

## 2. 审查结论

结论：**设计方向成立，可以进入开发，但必须先锁定部署模式和服务内核边界。**

当前方案已经具备可执行性，原因如下：

1. 目标明确
   - RSS 抓取
   - OpenAI-compatible LLM 摘要
   - 企业微信推送
   - FastAPI 手动触发
   - APScheduler 定时触发

2. 复用路径清晰
   - 可复用现有 `collectors/`、`aggregator/`、`infra/storage/` 的稳定能力
   - 已明确哪些部分不能直接复用

3. 范围控制合理
   - 没有引入数据库
   - 没有引入多 Agent 运行时框架
   - 没有引入微信回调、向量库、浏览器自动化

但在进入开发前，仍有少量**阻塞项**必须明确，否则开发会高概率返工。

---

## 3. 阻塞项

以下项为本轮设计阻塞项，未解决前不建议进入正式开发。

### 阻塞项 1：部署模式必须先定一版主路径

当前设计允许两种部署方式：

1. 模式 A：服务器外部定时调用 HTTP
2. 模式 B：服务内 APScheduler

这两种都能跑，但如果开发时不先确定“主路径”，会导致：

1. scheduler 生命周期设计反复变动
2. 锁语义不一致
3. README、compose、部署脚本写两套半成品

审查结论：

1. **本轮开发主路径必须固定为模式 B**
2. 模式 A 只作为迁移过渡方案保留在文档里

阻塞原因：

如果不先固定，开发者很容易同时兼容两套触发模型，最后把逻辑做复杂但不稳定。

### 阻塞项 2：必须先定义服务内核与入口边界

必须先明确：

1. `app/agents/news_agent.py` 是唯一任务内核入口
2. `POST /run/news` 只调用这个内核
3. APScheduler 也只调用这个内核
4. `main.py` 不直接混入新服务逻辑

阻塞原因：

如果这个边界不先锁死，开发时最容易出现：

1. API 走一套逻辑
2. scheduler 走一套逻辑
3. CLI 又保留第三套逻辑

最终仓库会变成三套入口、三套行为。

### 阻塞项 3：必须先定义“单活运行”约束

本轮设计依赖本地 JSON 状态与本地锁，因此必须先明确：

1. 单容器
2. 单 worker
3. 单实例
4. API 与 scheduler 共用同一把锁

阻塞原因：

如果开发期默认不强调这一点，部署时很容易误配成：

1. `uvicorn --workers 2`
2. 两个副本同时启动
3. 外部定时器和内部 scheduler 同时触发

这会直接造成重复推送。

---

## 4. 重要风险

以下不是阻塞设计方向，但开发中必须重点防守。

### P1 风险 1：现有 `main.py` 是脚本，不是服务内核

风险：

1. 当前 `main.py` 使用 `sys.exit()`
2. 当前 `main.py` 管理文件锁、日志初始化、清理动作
3. 这些行为不能直接被 FastAPI 路由复用

要求：

1. 新服务必须抽出独立任务内核
2. 路由层和 scheduler 层只能做薄调用

### P1 风险 2：RSS 解析可能阻塞事件循环

风险：

1. 当前 RSS 解析使用同步 `feedparser.parse()`
2. 在 CLI 下问题不大
3. 在 FastAPI 常驻进程里会影响响应和调度稳定性

要求：

1. 若继续复用现有逻辑，必须线程池隔离
2. 或者后续改为异步拉取 + 解析

### P1 风险 3：状态持久化仍然是本地文件

风险：

1. 当前去重状态与 digest 都是文件存储
2. 容器重启后如果不挂卷，状态会丢失

要求：

1. `docker-compose.yml` 明确挂载 `data/`
2. README 明确说明当前是单机文件状态方案

### P1 风险 4：文档与真实部署很容易漂移

风险：

1. 当前 README 还是旧 CLI 视角
2. 新服务一旦上线，如果 README / compose / `.env.example` / `deploy.example.sh` 不同步，开发和运维会误操作

要求：

1. 文档更新必须和服务代码同批次提交
2. Review 时把文档作为验收的一部分，不允许事后补

---

## 5. 可接受风险

以下风险本轮可以接受，但必须在文档里说清楚，不能伪装成“已经彻底解决”。

### 可接受风险 1：不做多供应商专用 SDK 适配

本轮只做 OpenAI-compatible 接口适配即可。

可接受原因：

1. 已满足“更换更便宜模型供应商”的目标
2. 不需要为每家模型接私有 SDK

### 可接受风险 2：不做数据库

本轮继续使用本地文件状态可接受。

前提：

1. 单实例
2. 单活
3. 有卷挂载

### 可接受风险 3：不做多模型自动切换

本轮不做以下能力：

1. 多 key 轮询
2. 预算调度
3. 失败回退
4. provider 专用路由

这是合理取舍，不构成阻塞。

---

## 6. 设计优点

### 优点 1：迁移成本可控

不是推倒重来，而是同仓新增服务入口，保留旧 CLI。

### 优点 2：能兼容当前“服务器定时触发”的习惯

即使推荐最终走内部 scheduler，也支持迁移期继续使用：

```bash
curl -X POST http://127.0.0.1:8000/run/news
```

这和你原先“服务器上定时触发”的思路是连续的。

### 优点 3：扩展空间够用

后续可以平滑增加：

1. 更多 RSS 源
2. HuggingFace / TapTap 作为可选 source
3. 更多 OpenAI-compatible 模型供应商

---

## 7. 对开发的明确指令

开发必须遵守以下规则：

1. 新服务主路径固定为：
   - `app/main.py`
   - `app/agents/news_agent.py`
   - `app/tools/crawler.py`
   - `app/tools/llm.py`
   - `app/tools/wecom.py`
   - `app/scheduler/jobs.py`

2. 不允许直接把 `main.py` 当服务内核复用

3. 不允许在 `app/` 路径中出现：
   - `sys.exit()`
   - 旧 CLI 专用日志初始化语义
   - 旧 CLI 专用输出格式逻辑

4. 不允许默认部署成：
   - 多 worker
   - 多副本
   - 内部 scheduler + 外部定时器双开

5. 文档必须同步更新：
   - `README.md`
   - `.env.example`
   - `Dockerfile`
   - `docker-compose.yml`
   - `deploy.example.sh`

---

## 8. 推荐开发顺序

推荐顺序如下：

1. 先做配置层 `app/config.py`
2. 再做 `app/tools/crawler.py`
3. 再做 `app/tools/llm.py`
4. 再做 `app/tools/wecom.py`
5. 再做 `app/agents/news_agent.py`
6. 最后做 `app/main.py + app/scheduler/jobs.py + Docker/README`

原因：

1. 先把底层依赖和外部接口做稳定
2. 再做任务编排
3. 最后再挂入口和部署

这样返工最少。

---

## 9. 评审准入条件

开发开始前，必须满足以下条件：

1. 团队确认本轮主部署模式是“模式 B：服务内 APScheduler”
2. 团队接受迁移期可临时使用“模式 A：服务器外部定时调用 HTTP”
3. 团队确认单实例部署约束
4. 团队确认新服务不替换旧 CLI，而是并存

如果以上四项有一项未确认，不建议进入开发。

---

## 10. 最终评审意见

最终评审意见：**有条件通过。**

通过条件：

1. 固定主部署模式为内部 scheduler
2. 固定服务任务内核为 `news_agent.run_once()`
3. 固定单活部署约束
4. 固定文档与部署资产必须同步交付

满足上述条件后，可以进入实际开发。
