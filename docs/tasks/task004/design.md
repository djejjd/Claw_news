# AI 助手服务交付完善设计文档

## 1. 设计目标

本阶段不再扩核心功能，而是解决 Task003 通过后留下的三个交付问题：

1. 原文链接在企业微信中是否真的可直接使用
2. 部署时如何显式控制内部 scheduler 开关
3. 服务模式如何形成完整验证闭环

---

## 2. 设计结论

### 2.1 链接可用性

当前风险在于：

1. 摘要内容中使用 Markdown 链接语法
2. 但推送方式是 WeCom `text`
3. `text` 消息不一定把 Markdown 链接渲染为可点击

因此本阶段推荐策略：

1. 默认继续使用 `text`
2. 但把每条新闻输出改成：
   - 标题
   - 原文链接
   - 核心内容
   - 重要性
   - 趋势判断

这样即使企业微信不渲染 Markdown，用户也仍能直接复制或点击 URL。

### 2.2 调度模式

当前文档里已经有两种模式，但没有代码开关：

1. 模式 A：内部 scheduler
2. 模式 B：外部 HTTP 调度

因此本阶段必须引入显式配置：

1. `ENABLE_INTERNAL_SCHEDULER=true|false`

建议默认：

1. 默认 `true`
2. 与当前推荐部署模式保持一致

行为定义：

1. `true`
   - `lifespan` 启动 scheduler
2. `false`
   - 服务只暴露 HTTP
   - scheduler 不启动

### 2.3 验证闭环

当前最大问题不是代码结构，而是验证链路还不够强。

因此本阶段要形成三层验证：

1. 单元测试
   - 链接输出格式
   - scheduler 开关行为
2. API 测试
   - `/health`
   - `/run/news`
3. CI / 文档一致性
   - CI 跑通服务模式测试
   - README、`.env.example`、`deploy.example.sh` 同步更新

---

## 3. 设计边界

本阶段不做：

1. 改数据库
2. 多模型调度
3. 多 key 轮询
4. 新 source 扩展

本阶段只解决“服务能不能稳定交付、部署、验证”。

---

## 4. 组件设计

### 4.1 `app/config.py`

新增：

1. `enable_internal_scheduler: bool`

行为：

1. 从环境变量 `ENABLE_INTERNAL_SCHEDULER` 读取
2. 默认值为 `true`

### 4.2 `app/main.py`

调整：

1. `lifespan` 启动前判断 `config.enable_internal_scheduler`
2. 为 `false` 时不启动 scheduler

### 4.3 `app/tools/llm.py`

调整目标：

1. 摘要模板不要依赖“Markdown 链接一定可点击”
2. 每条新闻必须显式输出原文 URL

推荐格式：

```text
1. 标题
   - 原文链接：https://...
   - 核心内容：...
   - 重要性：...
   - 趋势判断：...
```

### 4.4 `app/tools/wecom.py`

保持：

1. 继续使用 `text`，除非开发方决定切换到 `markdown`

如果改成 `markdown`：

1. 必须补验证证据，证明企业微信里链接可点击

### 4.5 文档与部署

需要同步更新：

1. `README.md`
2. `.env.example`
3. `deploy.example.sh`

必须说明：

1. 内部 scheduler 模式
2. 外部 HTTP 调度模式
3. 如何切换
4. 哪种模式是默认值

---

## 5. 验证设计

### 5.1 链接验证

测试要求：

1. 新闻摘要中每条都含原文链接字段或可点击链接

### 5.2 调度开关验证

测试要求：

1. `ENABLE_INTERNAL_SCHEDULER=true` 时 scheduler 启动
2. `ENABLE_INTERNAL_SCHEDULER=false` 时 scheduler 不启动

### 5.3 CI 验证

要求：

1. 新增服务测试进入 CI
2. 依赖安装后可执行

---

## 6. 结论

Task004 不扩业务能力，只做交付完善。

交付标准不是“功能更多”，而是：

1. 原文链接真正可用
2. 调度模式真正可控
3. 服务模式真正可验证
