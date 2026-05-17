# Task 文档目录整改实施计划

> **给执行开发的 agent：** 本计划只处理文档结构治理，不处理业务代码。执行时以低风险迁移为原则，优先建立规范与索引，再逐步迁移活跃 task。

**目标：** 建立统一的 task 文档目录规范，明确每个 task 的正式入口、目标表达规则和迁移方案。

**架构：** 以 `spec/taskNNN/` 作为每个 task 的唯一正式目录，统一固定 `contract/design/plan/review/done` 命名，并补总索引。

**技术栈：** Markdown、目录规范、低风险文档迁移

---

## 文件结构

**新增：**
- `spec/task005/contract.md`
- `docs/tasks/task005/design.md`
- `docs/tasks/task005/plan.md`

**后续阶段建议新增：**
- `spec/README.md`
- `spec/task003/contract.md`
- `spec/task003/design.md`
- `spec/task003/plan.md`
- `spec/task003/review.md`
- `spec/task004/contract.md`
- `spec/task004/design.md`
- `spec/task004/plan.md`

---

## 任务 1：冻结目录治理规范

**文件：**
- `spec/task005/contract.md`
- `docs/tasks/task005/design.md`

- [ ] **步骤 1：确认正式目录规范**

必须冻结以下规则：

1. 每个 task 的唯一正式目录是 `spec/taskNNN/`
2. 正式文档命名固定为：
   - `contract.md`
   - `design.md`
   - `plan.md`
   - `review.md`
   - `done.md`

- [ ] **步骤 2：确认目标表达规则**

必须冻结以下规则：

1. `contract.md` 必有 `## 任务目标`
2. `design.md` 必有 `## 本轮目标`
3. `plan.md` 开头必须重申本轮目标

- [ ] **步骤 3：提交规范冻结**

```bash
git add spec/task005/contract.md docs/tasks/task005/design.md
git commit -m "docs: freeze task document structure governance"
```

---

## 任务 2：设计总索引结构

**文件：**
- 新增：`spec/README.md`（下一阶段实际创建）

- [ ] **步骤 1：定义总索引字段**

每个 task 至少包含：

1. task 编号
2. 状态
3. 一句话目标
4. 正式入口链接

- [ ] **步骤 2：定义示例格式**

建议格式：

```text
task003
状态：已完成
目标：...
入口：
- contract
- design
- plan
- review
```

- [ ] **步骤 3：确认总索引只做导航，不重复正文**

规则：

1. `spec/README.md` 只做入口和状态导航
2. 不承载 task 正文内容

---

## 任务 3：设计现有 task 的迁移映射

**文件：**
- `docs/tasks/task005/design.md`

- [ ] **步骤 1：列出 task003 映射**

至少明确：

1. `spec/task003/spec.md` -> `spec/task003/contract.md`
2. 设计文档 -> `spec/task003/design.md`
3. 计划文档 -> `spec/task003/plan.md`
4. review 文档 -> `spec/task003/review.md`

- [ ] **步骤 2：列出 task004 映射**

至少明确：

1. `spec/task004/spec.md` -> `spec/task004/contract.md`
2. 设计文档 -> `spec/task004/design.md`
3. 计划文档 -> `spec/task004/plan.md`

- [ ] **步骤 3：定义历史文档处理方式**

规则：

1. 近期活跃 task 优先收拢
2. 历史文档先保留原件
3. 通过索引或说明文件做跳转

---

## 任务 4：设计落地顺序

**文件：**
- `docs/tasks/task005/plan.md`

- [ ] **步骤 1：定义三阶段落地**

阶段 1：
- 建立规范

阶段 2：
- 收拢活跃 task

阶段 3：
- 整理历史 task

- [ ] **步骤 2：定义执行优先级**

推荐：

1. `task003`
2. `task004`
3. `task005`
4. `task001`
5. `task002`

- [ ] **步骤 3：明确 review 规则迁移**

以后统一规定：

1. review 只对 `contract.md` 负责

---

## 审查关卡

### 契约审查

必须检查：

1. 是否定义了统一目录结构
2. 是否定义了目标的固定落点
3. 是否定义了总索引结构

### 质量审查

必须检查：

1. 迁移方案是否低风险
2. 是否避免一次性大规模移动历史文件
3. 是否避免与业务任务混淆

---

## 最终验证

本轮为目录治理设计任务，不运行业务代码。

建议验证：

```bash
find spec -maxdepth 2 -type f | sort
find docs/superpowers/specs -maxdepth 1 -type f | sort
find docs/superpowers/plans -maxdepth 1 -type f | sort
```

---

## 结论

Task005 的成功标准不是“文件已经全部搬完”，而是：

1. 目录规则已建立
2. 目标表达已标准化
3. 索引方案已明确
4. 迁移顺序已可执行
