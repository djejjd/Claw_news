# Task 文档目录整改设计文档

## 1. 本轮目标

本轮目标不是整改业务代码，而是整改任务文档结构。

要解决的问题是：当前仓库中 task 契约、设计、计划、review、归档散落在多个目录，且大量文件只按日期命名，导致无法快速识别：

1. 哪份文档是某个 task 的唯一正式契约
2. 哪份文档是当前生效的设计
3. 哪份文档是开发执行依据
4. 哪份文档是 review 结论
5. 本轮 task 的目标到底是什么

---

## 2. 当前问题

### 2.1 文档散落

当前任务文档分散在：

1. `spec/task001/`、`spec/task002/`、`spec/task003/` ...
2. `docs/tasks/`
3. `docs/architecture/` / `docs/operations/`

### 2.2 命名方式不稳定

大量文件采用：

1. 日期命名
2. 临时语义命名
3. task 编号与文档类型不统一

结果是：

1. 一眼看不出谁对应谁
2. review 时很难判断哪份是正式入口

### 2.3 目标不够显式

虽然多数 task 文档里有目标描述，但没有形成强约束：

1. 每个 task 必须单独写“本轮目标”
2. 且目标必须在固定位置出现

这会让开发与 review 在长期演进后逐渐失焦。

---

## 3. 设计结论

### 3.1 统一正式入口

以后每个 task 的正式文档统一收敛到：

```text
spec/taskNNN/
```

### 3.2 固定文档命名

每个 task 统一使用：

```text
spec/taskNNN/
├── contract.md
├── design.md
├── plan.md
├── review.md
├── done.md
└── attachments/
```

说明：

1. `contract.md`
   - 唯一正式验收契约
2. `design.md`
   - 当前 task 的主设计文档
3. `plan.md`
   - 当前 task 的实施计划
4. `review.md`
   - 当前 task 的 review 结论
5. `done.md`
   - 当前 task 的最终归档
6. `attachments/`
   - 草稿、补充材料、截图、一次性说明

### 3.3 目标必须显式出现

这是本轮整改里最重要的新增规则。

必须要求：

1. `contract.md` 中必须有 `## 任务目标`
2. `design.md` 中必须有 `## 本轮目标`
3. `plan.md` 开头必须再次重申本轮目标

这样做的目的：

1. reviewer 看契约时知道本轮到底交付什么
2. 开发看设计时知道为什么这样设计
3. 执行计划时不至于只看步骤、不看目标

### 3.4 总索引

在 `spec/README.md` 中建立总索引。

每个 task 至少包含：

1. task 编号
2. 状态
3. 一句话目标
4. 正式文档入口

推荐格式：

```text
task003
状态：已完成
目标：在不破坏旧 CLI 的前提下，为仓库新增 AI 助手服务 MVP。
入口：
- contract
- design
- plan
- review
```

### 3.5 `docs/superpowers/*` 的角色调整

建议以后：

1. `spec/taskNNN/` 只承载 task 级正式文档
2. `docs/tasks/` 承载 task 级详细原文
3. `docs/architecture/` 与 `docs/operations/` 承载跨 task 与运维文档

也就是说：

1. task 专属正式文档不再长期散落在 `docs/superpowers/*`

---

## 4. 迁移策略

### 4.1 不一次性暴力迁移

本轮建议先做“规范建立 + 映射方案”，不要立刻大规模移动所有历史文件。

原因：

1. 历史 task 已有引用关系
2. 一次性迁移容易破坏链接
3. 目录治理本身不应演变成高风险改造

### 4.2 推荐迁移顺序

先迁移最近、最活跃的 task：

1. `task003`
2. `task004`
3. `task005`
4. 再回收 `task001`
5. 再回收 `task002`

### 4.3 当前文档映射建议

#### task003

建议映射为：

1. `spec/task003/spec.md` -> `spec/task003/contract.md`
2. `...ai-assistant-service-design.md` -> `spec/task003/design.md`
3. `...ai-assistant-service-one-page.md` -> `spec/task003/one-page.md`
4. `...ai-assistant-service-design-review.md` -> `spec/task003/review.md`
5. `...ai-assistant-service-implementation-plan.md` -> `spec/task003/plan.md`

#### task004

建议映射为：

1. `spec/task004/spec.md` -> `spec/task004/contract.md`
2. `...delivery-hardening-design.md` -> `spec/task004/design.md`
3. `...delivery-hardening-plan.md` -> `spec/task004/plan.md`

#### task005

本轮目录治理 task 直接从一开始就按新规范建立。

---

## 5. 推荐落地方式

### 5.1 第一阶段：建立规范

交付：

1. task005 的 `contract`
2. task005 的 `design`
3. task005 的 `plan`
4. `spec/README.md` 草案

### 5.2 第二阶段：迁移当前活跃 task

交付：

1. `task003` 正式收拢
2. `task004` 正式收拢

### 5.3 第三阶段：清理历史分散文档

交付：

1. 历史文件加跳转说明
2. 决定哪些保留在 `attachments/`
3. 决定哪些只保留索引不搬迁

---

## 6. 结论

本次目录整改的核心不是“移动文件”，而是建立一套稳定规则：

1. 每个 task 有唯一正式目录
2. 每个 task 的正式文档类型固定
3. 每个 task 的本轮目标必须单独写清楚
4. review 以后只对 `contract.md` 负责

只要这四条建立起来，后续 task 数量继续增长时，文档结构也不会再失控。
