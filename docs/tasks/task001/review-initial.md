# Claw_news M1+M2 实现检视报告

## 1. 检视范围

本次检视范围为 `origin/main..HEAD` 的待 push 提交，共 8 个提交：

- `92adf78 feat: add settings boundary for runtime config`
- `b5c67b0 feat: add state store for pushed urls and daily digests`
- `d879be0 refactor: share safe_collect helper between runtime and tests`
- `7124f00 feat: add category-level wecom push transactions`
- `56f8359 feat: orchestrate category-level push commits with task locking`
- `cace43f chore: add packaging and local workflow tooling`
- `bf42fac docs: align ci, readme, and deploy safety`
- `16e85a0 style: fix ruff lint issues (import order, line length, unused vars)`

对照文档：

- `docs/tasks/task001/design.md`
- `docs/tasks/task001/plan.md`

检视重点：

1. 是否符合任务目标
2. 是否有过度修改
3. 是否破坏现有功能
4. 是否有安全风险
5. 是否需要补测试

---

## 2. 总体结论

这批改动的大方向是正确的，已经完成了大部分 M1/M2 目标：

- `Settings`、`StateStore`、`safe_collect` 边界已经落地
- `pyproject.toml`、`Makefile`、CI、README 已补齐
- venv 环境下 `pytest` 与 `ruff` 都能通过

但当前实现 **还不能通过 review**，原因不是风格问题，而是 **M1 最核心的“category 级事务失败处理”没有真正闭环**：

- 真实 `push_category()` 失败时会抛异常
- `main.py` 的编排层没有捕获这个真实失败路径
- 当前测试只覆盖了一个“假失败返回值”的 stub 路径，没有覆盖真实异常路径

因此当前状态下，部分失败场景仍可能直接中断任务流程，和设计目标不一致。

---

## 3. 必须修改

## 3.1 `run_push_sequence()` 没有处理真实推送失败异常

### 位置

- `main.py:84-114`
- `pusher/wecom.py:140-148`

### 问题描述

`WeComPusher.push_category()` 的真实失败行为是：

- HTTP 非 2xx → `resp.raise_for_status()` 直接抛异常
- HTTP 200 但 `errcode != 0` → 抛 `WeComError`

但 `run_push_sequence()` 当前实现没有 `try/except`，只处理了：

```python
if result.success:
    ...
else:
    logger.error(...)
```

这意味着真实运行时，`push_category()` 一旦失败，流程会直接被异常打断，根本不会进入 `result.success is False` 分支。

### 后果

- 任务在某个 category 失败时直接中断
- 后续 category 不会继续处理
- 设计要求的“记录失败但保留已成功 category 状态”并未真正实现
- 当前测试会给出错误安全感

### 为什么必须改

这是 M1 的核心目标之一：**按 category 独立提交状态**。  
如果真实失败路径没处理，这个目标没有达成。

### 推荐修改

在 `run_push_sequence()` 中按 category 包裹真实调用：

```python
try:
    result = await pusher.push_category(...)
except Exception as exc:
    logger.error("push failed for category=%s: %s", category, exc)
    continue
```

然后只在成功时提交：

- merge `pushed_urls`
- 写 category 级日报

### 是否值得现在修改

必须现在修改，否则不应 push。

---

## 3.2 `tests/test_main.py` 的失败 stub 与真实实现不一致

### 位置

- `tests/test_main.py:8-25`
- `pusher/wecom.py:143-148`

### 问题描述

测试里的 `StubPusher` 在失败时返回：

```python
PushResult(success=False, ...)
```

但真实 `WeComPusher.push_category()` 在失败时是 `raise WeComError(...)`，不是返回失败对象。

### 后果

- 编排层测试没有覆盖真实失败路径
- `run_push_sequence()` 即使对真实异常完全没处理，测试仍然通过
- 事务模型看似被验证，实际上没有

### 为什么必须改

这是当前 review 最关键的测试缺口。  
必须让测试行为与真实实现一致。

### 推荐修改

补至少一个真实异常路径测试：

1. 第一个 category 成功
2. 第二个 category 成功
3. 第三个 category `raise WeComError`
4. 断言：
   - 前两个 category 的 URL 已写入 `pushed_urls.json`
   - 失败 category 的 URL 未写入
   - `run_push_sequence()` 没有整体崩掉

### 是否值得现在修改

必须现在修改。

---

## 3.3 `Settings.rss_feeds` 已加载，但 `main.py` 没有注入给 `RssCollector`

### 位置

- `infra/config/settings.py:23,46`
- `collectors/rss_sources.py:38-46`
- `main.py:55-58`

### 问题描述

设计和计划都要求：

- `Settings` 统一加载 `rss_feeds`
- `RssCollector` 支持 `feed_configs` 注入
- `main.py` 负责把配置注入 collector

但当前 `main.py` 中实际调用是：

```python
RssCollector(keywords=settings.keywords, fetch_count=settings.fetch_count)
```

没有传 `feed_configs=settings.rss_feeds`。

### 后果

- `rss_feeds` 仍是死配置
- 配置边界没有真正闭环
- 当前实现偏离设计与计划

### 为什么必须改

如果不接上这一步，M1/M2 的配置边界仍然是不完整的。

### 推荐修改

改为：

```python
RssCollector(
    feed_configs=settings.rss_feeds,
    keywords=settings.keywords,
    fetch_count=settings.fetch_count,
)
```

并补一个测试，验证自定义 feed 配置会生效。

### 是否值得现在修改

必须修改，因为它属于当前任务范围内的明确目标。

---

## 4. 建议修改

## 4.1 README 中 `.env` 的说明可以再收紧

### 位置

- `README.md:40-55`

### 问题描述

README 先写：

```bash
cp .env.example .env
```

后面又写：

- 程序不会自动加载 `.env`

这虽然不算错误，但会让使用者产生轻微困惑：既然不会自动加载，为什么还要先复制 `.env`？

### 推荐修改

二选一：

1. 只保留 `export PUSHER_WECOM_WEBHOOK=...`
2. 继续保留 `.env.example`，但明确它只是“人工参考模板”

### 是否值得现在修改

建议本轮一起修掉，成本很低。

---

## 4.2 `push_category()` 的类型签名建议更严格

### 位置

- `pusher/wecom.py:124-130`

### 问题描述

当前签名：

```python
async def push_category(self, category: str, items: list, ...)
```

相较设计文档里期望的 `Category` / `list[HotItem]`，这里类型更宽松。

### 后果

- 静态约束较弱
- 可维护性略差
- IDE / lint 无法更好辅助

### 推荐修改

改为：

```python
async def push_category(
    self,
    category: Category,
    items: list[HotItem],
    ...
) -> PushResult:
```

### 是否值得现在修改

建议修改，但不是阻塞项。

---

## 4.3 `deploy.example.sh` 是计划外的新入口，建议明确其角色

### 位置

- `deploy.example.sh`

### 问题描述

当前新增了 `deploy.example.sh`，它本身没有明显错误，也比旧的 `deploy.sh` 安全，但这属于计划外新增文件。

### 风险

- 使用者可能误解为官方唯一部署入口
- 和 README 中的 `launchd` 路径形成双入口

### 推荐修改

至少在 README 或 docs 中明确：

- 这是模板
- 不是默认生产部署方式
- 仅用于本地/服务器初始化参考

### 是否值得现在修改

建议修改，但不是阻塞项。

---

## 4.4 clean 环境下直接 `pytest -q` 仍然失败，建议在 README 明确新契约

### 现象

- 系统 Python 下直接 `pytest -q` 失败
- 仓库 venv 下 `./venv/bin/pytest -q` 通过
- `./venv/bin/ruff check .` 通过

### 问题描述

这不一定是代码 bug，因为当前工程契约已经改成：

- `make install`
- `pip install -e ".[dev]"`

但如果 README 不强调，维护者还是会习惯直接跑系统 `pytest`。

### 推荐修改

在 README 中明确：

- 不要假设系统 Python 具备依赖
- 标准入口是 `make install` 后再跑测试

### 是否值得现在修改

建议修改。

---

## 5. 可以接受

以下改动目前看是可接受的：

### 5.1 `StateStore` 的最小实现方向正确

位置：

- `infra/storage/state_store.py`

评价：

- `pushed_urls.json` 保持 `list[str]` 结构不变
- 合并写入有去重
- 每 category 写日报的思路符合设计

### 5.2 `Settings` 的环境变量覆盖和 webhook 校验方向正确

位置：

- `infra/config/settings.py`

评价：

- `PUSHER_WECOM_WEBHOOK` 优先级高于 YAML
- live-run 校验逻辑已经加上
- dry-run 允许缺失 webhook

### 5.3 非业务文件上的格式化改动可以接受

位置：

- `aggregator/merger.py`
- `collectors/base.py`
- `tests/conftest.py`
- `tests/test_merger.py`

评价：

- 当前看都是 import 顺序、换行、格式化收敛
- 未发现业务行为变化

### 5.4 M2 工程化基础整体方向正确

位置：

- `pyproject.toml`
- `Makefile`
- `.github/workflows/ci.yml`
- `.env.example`

评价：

- 主安装入口已建立
- CI 已能验证 install → lint → test
- 本地开发体验明显改善

---

## 6. 是否有过度修改

整体上 **没有明显的高风险过度修改**，但有两点需要注意：

1. `deploy.example.sh` 属于计划外扩展，虽然无害，但应明确角色
2. 文档类文件一次性新增较多，后续要注意与实现保持同步

当前最需要担心的不是“改太多”，而是“核心失败路径还没真正打通”。

---

## 7. 是否破坏现有功能

### 明确结论

存在潜在功能破坏风险，主要集中在推送失败路径。

### 具体风险

如果某个 category 真实推送失败：

- 现在流程会因异常直接中断
- 而不是按设计那样记录失败并继续/保留已提交状态

这会影响：

- 任务稳定性
- 失败恢复语义
- 与设计文档的一致性

---

## 8. 是否有安全风险

当前没有发现新增的明显安全漏洞，且本轮改动在安全方向上是正向的：

- webhook 增加了校验
- `.env` 不自动加载，运行语义更明确
- `deploy.example.sh` 默认只做 dry-run

但安全工作仍未完全闭环：

- 需要确保仓库历史中不存在真实 webhook
- 需要确保 README / docs 中没有残留真实 secret

这部分建议继续人工复核一次。

---

## 9. 是否需要补测试

需要，且是必须补。

### 必补测试 1：真实异常路径的 category 级事务测试

目标：

- 模拟 `push_category()` 抛出 `WeComError`
- 验证前面成功 category 已提交
- 验证失败 category 未提交
- 验证流程不被整条打崩

### 必补测试 2：`rss_feeds` 注入生效测试

目标：

- 构造自定义 `Settings.rss_feeds`
- 验证 `RssCollector` 实际使用的是注入配置，而不是硬编码默认值

### 建议补测试 3：live-run 缺配置失败路径

目标：

- `Settings.validate_for_run(dry_run=False)` 对空 webhook / 非法 webhook 失败
- `main.py` 对配置错误能明确退出

### 建议补测试 4：任务锁的行为测试

目标：

- 第二个实例拿不到锁时退出码为 0
- 有清晰 warning 日志

---

## 10. 最终结论

## 是否通过

**不通过**

### 不通过原因

不是因为代码风格，也不是因为工程化不够，而是因为：

1. 真实推送失败异常没有在编排层正确处理
2. 关键事务测试只覆盖了假的失败返回值，没有覆盖真实异常路径
3. `rss_feeds` 配置注入没有真正接上线

### 通过条件

满足以下三项后，可重新 review：

1. `run_push_sequence()` 捕获并正确处理 `push_category()` 的真实异常
2. 补上真实异常路径测试
3. `main.py` 把 `settings.rss_feeds` 注入 `RssCollector`，并补测试验证

---

## 11. 验证记录

本次 review 期间的验证结果：

- `git status --short`：工作树干净
- `git log origin/main..HEAD`：待 push 共 8 个提交
- `./venv/bin/pytest -q`：**通过**
- `./venv/bin/ruff check .`：**通过**
- 系统 Python 下 `pytest -q`：**失败**
  - 原因是系统环境未安装运行依赖 / dev 依赖
  - 当前工程主契约已改为 `make install` / `pip install -e ".[dev]"`，因此这不是直接阻塞项
