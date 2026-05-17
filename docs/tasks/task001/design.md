# Claw_news M1+M2 优化设计

## 概述

基于 `2026-05-16-architecture-review-and-optimization-roadmap.md`，采用方案 B（适度收敛）：
在修复安全与正确性问题的同时，轻量抽取三个关键边界（Settings / StateStore / safe_collect），
为 M3 可维护性重构打好基础。

- **M1 安全与正确性**：webhook 安全、推送事务、企微业务校验、任务锁、deploy.sh 加固
- **M2 工程化基础**：pyproject.toml、Makefile、CI、依赖整理、lint 配置、README 同步

本设计文档的目标不是描述方向，而是直接指导开发实现。因此下面所有设计都以“接口清晰、迁移平滑、最小破坏”为原则。

---

## 设计原则

### 1. 不在 M1/M2 做大重构

本期不改业务评分逻辑，不改采集器业务规则，不引入数据库，不改消息格式。  
本期只补四类系统工程边界：

- 配置边界
- 状态边界
- 推送事务边界
- 开发/CI 契约边界

### 2. 先兼容现有行为，再收紧实现

除明确修复的行为外，本期必须保持以下外部行为不变：

- `main.py --period morning|evening [--dry-run]` 语义不变
- `data/` 目录结构不变
- `pushed_urls.json` 文件格式保持为 `list[str]`
- `[新]` / `[续]` 仍然按“上一次成功推送的全局 URL 集合”判断
- dry-run 不要求 webhook

### 3. 先把接口写实，再写代码

本期最容易返工的点是：

- `StateStore` 的数据模型
- `WeComPusher` 的提交时机
- `.env` 是否自动加载
- `pyproject.toml` 的安装契约

下面会对这几个点给出最终约束，开发阶段不要再各自发挥。

---

## M1：安全与正确性

### 1.1 Webhook Secret 安全

**现状**：`config.example.yaml` 中已有占位符。`config.yaml` 在 `.gitignore`。但没有环境变量兜底和启动校验。

**变更**：

1. **新增 `.env.example`**

```
PUSHER_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE
```

不新增 `.env` 文件，`.env` 已在 `.gitignore` 或通过 `.env.example` 说明自行创建。

2. **Settings 对象支持环境变量覆盖**

`Settings` 加载优先级：环境变量 > config.yaml > 默认值。webhook URL 从 `PUSHER_WECOM_WEBHOOK` 环境变量读取，如果存在则覆盖 YAML。

3. **启动时 webhook URL 格式校验**

非 dry-run 模式下，校验 webhook URL 必须以 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=` 开头，key 部分非空。不通过时打印错误信息并 `sys.exit(1)`。

4. **本期不自动读取 `.env`**

`.env.example` 只作为环境变量模板，不引入 `python-dotenv`。  
程序只读取真实环境变量，不主动解析 `.env` 文件。

这样做的原因：

- 避免为 M1 引入新的运行时依赖
- 避免 `launchd` / `cron` / shell 三种环境下出现不一致行为
- 把 `.env` 保持为“开发者本地参考文件”，不是应用运行时机制

### Settings 接口约束

建议新增 `infra/config/settings.py`，提供最小但完整的配置边界：

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class CollectorSourceFlags:
    rss: bool = True
    huggingface: bool = True
    taptap: bool = True

@dataclass(frozen=True)
class Settings:
    fetch_count: int
    top_n: int
    collector_sources: CollectorSourceFlags
    rss_feeds: list[dict]
    keywords: dict[str, list[str]]
    wecom_webhook: str

    @classmethod
    def load(cls, config_path: Path) -> "Settings": ...
    def validate_for_run(self, dry_run: bool) -> None: ...
```

### Settings 行为约束

- `load()` 负责读取 YAML 和环境变量覆盖
- `validate_for_run(dry_run=False)` 负责 webhook 校验
- 校验失败抛 `ValueError`，由 `main.py` 负责打印并退出
- `rss_feeds` 本期可以先保留为“已加载但不完全接管所有采集器行为”，但所有采集器都不能再自行打开 `config.yaml`

### 采集器配置注入统一方案

当前 **三个采集器都有独立的 `_load_config()` 函数**，设计文档必须明确各自的注入路径：

| 采集器 | 当前读配置的位置 | 注入方式 |
|---|---|---|
| `RssCollector` | `__init__` 中读 `keywords` + `fetch_count` | `__init__` 已有 `feed_configs` 参数，新增 `fetch_count` + `keywords` 参数 |
| `HfDailyPapersCollector` | `collect()` 第 57 行实时读 `fetch_count` | `__init__` 新增 `fetch_count` 参数 |
| `TapTapCollector` | `_parse_html()` 第 43 行实时读 `fetch_count` | `__init__` 新增 `fetch_count` 参数 |

统一原则：`fetch_count` 在 `__init__` 注入，`main.py` 从 `Settings` 取值后传给各采集器。

`collectors/rss_sources.py` 中的 `FEED_CONFIGS`（硬编码 RSS 源列表）本期暂时保留，但 `RssCollector.__init__` 的 `feed_configs` 参数可以从 `Settings.rss_feeds` 传入，对接路径已通。

### 启动失败策略

- dry-run 下：允许 webhook 为空
- live run 下：webhook 缺失或格式错误，直接失败退出
- 配置文件缺失：live/dry-run 都失败退出，并打印明确路径

### README 必须写清楚

README 中不能写成“程序会自动读取 `.env`”。必须明确表述：

```bash
cp .env.example .env
export PUSHER_WECOM_WEBHOOK=...
```

或在 `launchd` / shell 环境中显式注入该变量。

---

### 1.2 推送事务：按 category 独立提交

**现状**：`WeComPusher.push()` 三个 category 串行推送，`main.py` 在所有推送完成后统一写 `pushed_urls.json`。部分成功场景导致状态丢失。

**变更**：

1. **`pushed_urls.json` 的数据模型保持不变**

本期不把 `pushed_urls.json` 改成按 category 分组。  
仍然保持当前格式：

```json
[
  "https://example.com/a",
  "https://example.com/b"
]
```

原因：

- 当前 `[新]` / `[续]` 判断逻辑依赖“全局上次推送 URL 集合”
- 改成分 category 会同时牵动 `format_message()`、历史兼容和迁移逻辑
- M1 目标是修事务一致性，不是重做状态模型

因此，`StateStore` 本期只维护“全局 URL 集合”，不提供 category 维度的持久化抽象。

2. **`WeComPusher.push()` 不返回 `list[PushResult]`，改为单分类发送接口**

```python
# pusher/wecom.py
from dataclasses import dataclass

@dataclass
class PushResult:
    category: str
    success: bool
    urls: list[str]        # 本次推送涉及的 URL
    error: str | None = None
```

推荐将当前 `push()` 拆成两个层次：

```python
class WeComPusher:
    async def push_category(
        self,
        category: Category,
        items: list[HotItem],
        period: str = "morning",
        pushed_urls: set[str] | None = None,
    ) -> PushResult:
        ...
```

`main.py` 自己循环 `("ai", "game", "device")`，每次调用一次 `push_category()`。  
不要让 `WeComPusher` 同时承担“分类循环 + 事务协调 + 状态提交”三件事。

这样做的原因：

- 调用方可以在单个 category 成功后立即提交状态
- 如果第三个 category 推送时进程崩溃，前两个 category 的状态已经提交
- 事务边界清晰，测试也更简单

3. **`main.py` 每 category 推送成功后立即写状态**

调用方按分类循环：

- 成功 → 立即把该 category 的 URL merge 到全局 `pushed_urls` 集合，并立即落盘
- 成功 → 立即把该 category 的日报写入当日 `{period}.json`
- 失败 → 记录错误日志，不写该 category 的 URL

注意：这里的“立即写状态”指的是在单个 category 成功后马上提交，而不是等所有 category 完成。

4. **`StateStore` 提供原子写入**

- 写 `pushed_urls`：先写临时文件，再 `os.replace()`（POSIX 原子操作）
- 只提供全局集合接口：`load_pushed_urls()` / `merge_pushed_urls(urls)`
- 底层存储保持 JSON 文件格式不变

### StateStore 最终接口

建议 `infra/storage/state_store.py` 最终只提供以下最小接口：

```python
from pathlib import Path

class StateStore:
    def __init__(self, data_dir: Path): ...

    def load_pushed_urls(self) -> set[str]: ...
    def merge_pushed_urls(self, urls: set[str]) -> set[str]: ...
    def write_daily_digest_category(
        self,
        period: str,
        category: str,
        items: list[dict],
    ) -> None: ...
```

### `daily_digest` 写入策略

当前 `save_daily_digest()` 是一次性写完整记录。  
为了支持单 category 成功后立即提交，本期需要把它收紧为：

- 第一次成功 category：创建当日 `{period}.json` 骨架
- 每成功一个 category：只更新该 category 对应字段
- 失败 category：不写该字段

最终文件允许是“部分完成日报”，例如只有 `ai` 和 `game` 字段，没有 `device`。  
这是正确行为，不算脏数据，因为它真实反映了外部发送结果。

### `main.py` 伪代码

```python
pushed_urls = state_store.load_pushed_urls()

for category in ("ai", "game", "device"):
    cat_items = grouped.get(category, [])
    if not cat_items:
        continue

    result = await pusher.push_category(
        category=category,
        items=cat_items,
        period=period,
        pushed_urls=pushed_urls,
    )

    if result.success:
        pushed_urls = state_store.merge_pushed_urls(set(result.urls))
        state_store.write_daily_digest_category(
            period=period,
            category=category,
            items=[...],
        )
    else:
        logger.error("category=%s push failed: %s", category, result.error)
```

### 不要做的事

- 不要在 `WeComPusher` 内部直接写状态文件
- 不要在本期把 `pushed_urls.json` 改成分类结构
- 不要把 category 级事务和全局汇总事务混在一个方法里

---

### 1.3 企微响应业务校验

**现状**：`wecom.py` 只 `resp.raise_for_status()`，不检查企微 JSON 中的 `errcode`。

**变更**：

在 `WeComPusher.push()` 中，每个 category 发送后：

```python
resp_data = resp.json()
if resp_data.get("errcode") != 0:
    raise WeComError(
        errcode=resp_data.get("errcode"),
        errmsg=resp_data.get("errmsg", "unknown"),
        category=category,
    )
```

新增 `WeComError` 异常类，包含 errcode、errmsg、category。调用方捕获后记录详细日志并标记该 category 失败。

已知 errcode：
- `0` 成功
- `93000` 无 webhook 发送权限
- `45009` 接口调用频率限制
- `44004` 消息内容为空

### 企微错误处理策略

本期不要对不同 errcode 做复杂分流，只做以下分级：

- `errcode == 0`：成功
- 其他 errcode：失败，记录 category、errcode、errmsg

不要在 M1 引入自动重试，因为这会把事务语义和速率限制策略复杂化。  
本期目标是“识别失败且不写错状态”，不是“自动恢复所有失败”。

### `PushResult` 推荐字段

```python
@dataclass
class PushResult:
    category: str
    success: bool
    urls: list[str]
    errcode: int | None = None
    errmsg: str | None = None
```

这样调用方无需解析异常字符串，也便于测试断言。

### `format_message()` 不受影响

`format_message()` 保持纯函数语义不变：接收 `items` + `category` + `period` + `pushed_urls` 参数，返回格式化字符串。不需要任何修改。

### `test_wecom.py` 迁移说明

当前测试调用 `await pusher.push(items)`，需要同步迁移为 `await pusher.push_category(...)` 接口。新测试需要覆盖：

- HTTP 200 + `errcode=0` → `PushResult(success=True)`
- HTTP 200 + `errcode!=0` → `PushResult(success=False, errcode=..., errmsg=...)`
- HTTP 非 2xx → `PushResult(success=False)`

---

### 1.4 任务锁：防止并发重入

**现状**：无任何锁机制。launchd 误配置或人工补跑可能重叠执行，导致状态文件竞态损坏。

**变更**：

1. **引入 `portalocker`**

在 `requirements.txt`（或 `pyproject.toml`）中添加 `portalocker>=2.0`。

2. **在 `main()` 入口获取排他文件锁**

```python
import portalocker

lock_path = DATA_DIR / "task.lock"
try:
    lock_fd = open(lock_path, "w")
    portalocker.lock(lock_fd, portalocker.LOCK_EX | portalocker.LOCK_NB)
except (portalocker.LockException, IOError):
    logger.warning("已有任务实例运行中，退出")
    sys.exit(0)
```

锁在进程退出时由 OS 自动释放（`lock_fd` 随进程关闭）。不依赖 `atexit`。

3. **不采用 `flock`**

`flock` 在 macOS 和 Linux 行为有差异，`portalocker` 跨平台一致。

### 锁文件路径约束

锁文件路径统一使用：

```python
DATA_DIR / ".task.lock"
```

不要用仓库根目录锁文件，避免影响不同数据目录的未来演进。

### 锁的行为约束

- 拿不到锁：记录 warning，退出码为 `0`
- dry-run 和 live-run 都要拿锁
- 锁获取必须发生在真正采集前

这样可以防止“有人正在 live-run，另一个 dry-run 也进来改状态或打乱日志”。

---

### 1.5 日志 run_id

原始评审将"在日志中加入 `run_id`"列为低成本高收益项。实现极简：在 `main()` 启动时生成一个 UUID，注入到 logger 的格式中。

```python
import uuid

run_id = uuid.uuid4().hex[:8]
logging.basicConfig(
    ...
    format=f"%(asctime)s %(levelname)s [{run_id}]: %(message)s",
    ...
)
```

收益：当排查"这次推送为什么少了一个 category"或"是否并发执行了"时，日志行可以直接对应到具体 run。

---

### 1.6 deploy.sh 加固

**变更**：

- `deploy.sh` 顶部添加环境检查注释
- 默认执行 `--dry-run` 验证，需要显式传 `--live` 才执行真实推送
- 或者更简单：移除 `deploy.sh` 中的真实推送命令，只保留环境安装和验证步骤

由于 `deploy.sh` 已在 `.gitignore`，实际修改取决于用户当前文件内容。

### 最终建议

本期采用更保守的方案：

- `deploy.sh` 只做安装和环境检查
- 不在 `deploy.sh` 中执行真实推送
- 如果保留验证步骤，只允许 `--dry-run`

这样可以避免部署脚本本身变成生产消息入口。

### 提供 `deploy.example.sh` 模板

`deploy.sh` 在 `.gitignore` 中，无法查看或版本控制。本期新增 `deploy.example.sh`（不在 gitignore），作为标准化部署模板：

- 只包含环境安装 + `--dry-run` 验证
- 通过注释说明 live-run 需要手动操作
- 与 `Makefile` 中的 install/test/dry-run 目标保持一致

---

## M2：工程化基础

### 2.1 pyproject.toml

替换 `requirements.txt` 的角色，统一管理项目元数据、依赖、工具配置。

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "claw-news"
version = "0.2.0"
description = "每日热点聚合推送"
requires-python = ">=3.11"
readme = "README.md"

dependencies = [
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
    "feedparser>=6.0.0",
    "pyyaml>=6.0",
    "curl-cffi>=0.7.0",
    "deep-translator>=1.11.0",
    "portalocker>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-httpx>=0.30.0",
    "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.ruff.format]
quote-style = "double"
```

### 为什么必须有 `[build-system]`

本期的 `Makefile install` 和 CI 都会调用：

```bash
pip install -e ".[dev]"
```

如果没有 `[build-system]`，editable install 的行为依赖环境猜测，不应作为工程契约。

### 包安装策略

本项目当前不是要发布到 PyPI，只是希望获得统一安装入口。  
因此这里的目标不是“打包分发”，而是“本地和 CI 可重复安装”。

### `requirements.txt` 处理策略

保留 `requirements.txt`，保持开源项目依赖可见性。内容以 `pyproject.toml` 为权威来源，手动同步 runtime 依赖。dev 依赖不需要出现在 `requirements.txt` 中。

主安装入口统一为：

```bash
pip install -e ".[dev]"
```

README、CI、Makefile 都以它为准。`requirements.txt` 作为辅助参考，方便不熟悉 `pyproject.toml` 的用户快速了解依赖。

**依赖整理**：

| 包 | 类型 | 说明 |
|---|---|---|
| httpx | runtime | HTTP 客户端 |
| beautifulsoup4 | runtime | HTML 解析 |
| feedparser | runtime | RSS 解析 |
| pyyaml | runtime | 配置解析 |
| curl-cffi | runtime | TLS 指纹模拟 |
| deep-translator | runtime | HF 摘要翻译 |
| portalocker | runtime | 文件锁（新增） |
| pytest | dev | 测试框架 |
| pytest-asyncio | dev | 异步测试支持 |
| pytest-httpx | dev | HTTP mock |
| ruff | dev | Lint + 格式化 |

`requirements.txt` 保留为 `pyproject.toml` 导出的最小安装文件，或直接删除。

---

### 2.2 Makefile

```makefile
.PHONY: install test lint format run-morning run-evening dry-run clean clean-data

install:
	python3 -m venv venv
	./venv/bin/pip install -e ".[dev]"

test:
	./venv/bin/pytest -v

lint:
	./venv/bin/ruff check .

format:
	./venv/bin/ruff format .

run-morning:
	./venv/bin/python main.py --period morning

run-evening:
	./venv/bin/python main.py --period evening

dry-run:
	./venv/bin/python main.py --period morning --dry-run

clean:
	rm -rf venv/ .pytest_cache/ .ruff_cache/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-data:
	rm -rf data/
```

### 为什么要拆分 `clean` / `clean-data`

`data/` 下包含：

- `pushed_urls.json`
- 历史日报
- 运行日志

这些不是普通缓存，而是运行状态和排障证据。  
如果 `make clean` 默认删除它们，会导致下一次所有条目重新变成 `[新]`，并丢失历史线索。

---

### 2.3 CI（GitHub Actions）

`.github/workflows/ci.yml`：

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff format --check .
      - run: ruff check .
      - run: pytest -v
```

CI 只跑 lint + pytest，不含真实网络请求。

### CI 契约

- CI 只验证“干净环境能安装、lint、测试”
- CI 不依赖本地 `venv`
- CI 不读取真实 webhook
- CI 不允许任何真实网络副作用

如果未来某些测试会访问网络，必须在本期顺手把它们 mock 化，而不是在 CI 中放开外网。

---

### 2.4 测试契约修复

**现状问题**：
- 系统 Python 下 `pytest -q` 跑不通，根因包括：
  - 缺少 runtime / dev 依赖安装入口
  - 缺少 `pytest-asyncio` 配置，导致异步测试 warning
- `tests/test_resilience.py` 复制了 `safe_collect` 逻辑（影子实现）

**变更**：

1. 用 `pyproject.toml` 提供统一依赖安装入口
2. `pyproject.toml` 中配置 `asyncio_mode = "auto"`，消除 `pytest.mark.asyncio` warning
3. 将 `safe_collect` 从 `main.py` 提取到 `collectors/utils.py`
4. `tests/test_resilience.py` 改为 import `collectors.utils.safe_collect`，删除本地复制版

### `safe_collect` 最终接口

```python
async def safe_collect(name: str, collector) -> list[HotItem]:
    ...
```

要求：

- 保持当前“异常时记录日志并返回空列表”的语义
- 不引入复杂重试逻辑
- `main.py` 和测试必须共用同一实现

### `strip_html` 是否一起提取

本期不强制把所有 `strip_html` 合并到同一个 util 文件。  
如果提取 `safe_collect` 顺手需要收拢重复逻辑，可以做；如果会扩大改动面，则先只提 `safe_collect`。

---

### 2.5 README 同步

清理以下与代码不一致的项：

- 删除 `ithome.py` 引用（文件已在 `9fcfc7a` 中移除）
- 项目结构树与当前实际文件一致
- 快速开始命令改为 `make install && make test` 为首选方式
- 添加 `.env` 配置说明
- 明确 `.env.example` 只是模板，不会被程序自动加载

### README 中必须新增的“易错点说明”

- live run 依赖环境变量或 `config.yaml`
- dry-run 不要求 webhook
- `make clean` 不删除 `data/`
- `make clean-data` 才会删除状态文件
- CI 和本地安装入口统一为 `pip install -e ".[dev]"`

---

### 2.6 .env.example（已在 M1 中说明）

内容：

```
# 企业微信机器人 Webhook（必填，覆盖 config.yaml）
PUSHER_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE
```

---

### 2.7 .gitignore 补充

在现有基础上增加：

```
.env
task.lock
.ruff_cache/
```

---

## 新增/修改文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `infra/__init__.py` | **新增** | 包初始化 |
| `infra/config/__init__.py` | **新增** | 包初始化 |
| `infra/config/settings.py` | **新增** | 配置集中加载 + 校验 |
| `infra/storage/__init__.py` | **新增** | 包初始化 |
| `infra/storage/state_store.py` | **新增** | 全局 `pushed_urls` + category 级日报写入 + 原子写入 |
| `collectors/utils.py` | **新增** | 提取 `safe_collect` |
| `tests/test_settings.py` | **新增** | Settings 加载和校验测试 |
| `tests/test_state_store.py` | **新增** | StateStore 原子写入和容错测试 |
| `tests/test_main.py` | **新增** | main 编排层事务和锁测试 |
| `pyproject.toml` | **新增** | 项目元数据 + 依赖 + 工具配置 |
| `Makefile` | **新增** | 统一命令入口 |
| `.github/workflows/ci.yml` | **新增** | CI |
| `.env.example` | **新增** | 环境变量模板 |
| `deploy.example.sh` | **新增** | 标准化部署模板（非 gitignore） |
| `main.py` | **修改** | Settings/StateStore，按 category 提交状态，任务锁，run_id |
| `pusher/wecom.py` | **修改** | `push_category()`、`PushResult`、errcode 校验、`WeComError` |
| `collectors/rss_sources.py` | **修改** | `__init__` 注入 `fetch_count`+`keywords`，不再读 config.yaml |
| `collectors/huggingface.py` | **修改** | `__init__` 注入 `fetch_count`，删除 `_load_config()` |
| `collectors/taptap.py` | **修改** | `__init__` 注入 `fetch_count`，删除 `_load_config()` |
| `tests/test_resilience.py` | **修改** | 删除 `safe_collect` 影子实现，改为 import |
| `tests/test_wecom.py` | **修改** | `push()` → `push_category()` 迁移，新增 errcode 测试 |
| `requirements.txt` | **保留** | 添加 `portalocker`，保持开源项目依赖可见性 |
| `README.md` | **修改** | 清理漂移，更新快速开始 |
| `.gitignore` | **修改** | 增加 `.env`、`task.lock`、`.ruff_cache/` |
| `config.example.yaml` | 不变 | 已有占位符 |
| `aggregator/merger.py` | 不变 | 本期不改 |
| `pusher/wecom.py` 中的 `format_message()` | 不变 | 纯函数，接口不变 |

---

## 不变的部分

- 采集器**业务采集逻辑**不动（huggingface 的 API 调用/翻译、taptap 的 HTML 解析、rss_sources 的 feedparser 解析）
- `aggregator/merger.py` 不动 — 评分和竞争逻辑已经清晰
- `pusher/wecom.py` 中的 `format_message()` 不动 — 纯函数，接口不变
- `main.py` 保留 `--period` / `--dry-run` 的 CLI 入口语义
- `data/` 目录结构不变（YYYY-MM-DD 日报 + pushed_urls.json）
- 推送格式和标准不变
- `pushed_urls.json` 保持 `list[str]` 结构不变

---

## 实现顺序

```
M1-1  infra/ 目录 + __init__.py      ← 建立新包结构
M1-2  Settings + .env.example        ← 建立配置边界
M1-3  StateStore                     ← 建立状态边界
M1-4  portalocker 任务锁            ← 加锁
M1-5  采集器注入 fetch_count         ← 三个采集器统一去掉 _load_config()
M1-6  push_category + errcode 校验  ← 修推送事务边界
M1-7  main.py 按 category 提交      ← 接上 StateStore + run_id
M1-8  safe_collect 提取             ← 消影子实现
M2-1  pyproject.toml + requirements.txt ← 工程化
M2-2  test_resilience.py 去影子化   ← 修测试
M2-3  Makefile                       ← 统一命令
M2-4  CI (GitHub Actions)            ← 自动化验证
M2-5  补充测试 (settings/state_store/main) ← 新测试保护
M2-6  README 同步                    ← 文档对齐
M2-7  deploy.example.sh              ← 标准化部署模板
```

---

## 验证标准

完成后必须全部通过：

```bash
make install    # 新环境一次装好
make test       # 所有 pytest 通过，无警告
make lint       # ruff 零错误
make dry-run    # 无异常退出
```

M1 行为验证：
- 无 webhook 或 webhook 非法格式 → 非 dry-run 时拒绝启动
- 故意给错误 webhook → 推送失败时不写 pushed_urls
- 并发执行第二个实例 → 日志提示"已有任务运行"并退出
- 中间 category 推送失败 → 成功的那几个 category 的 URL 已写入 pushed_urls

### 需要补充的测试

除了现有测试外，本期建议新增以下测试，否则关键改动没有保护：

| 测试文件 | 测试内容 | 操作 |
|---|---|---|
| `tests/test_settings.py` | **新增** | `Settings.load()` 环境变量覆盖、dry-run 不校验 webhook、live-run 校验非法 webhook 失败 |
| `tests/test_state_store.py` | **新增** | `load_pushed_urls()` 兼容不存在文件、`merge_pushed_urls()` 保持去重、原子写入不会写出半截 JSON、`write_daily_digest_category()` 可从空文件逐步写出部分日报 |
| `tests/test_wecom.py` | **修改** | HTTP 200 + `errcode=0` 成功、HTTP 200 + `errcode!=0` 失败、HTTP 非 2xx 失败、`push()` → `push_category()` 接口迁移 |
| `tests/test_main.py` | **新增** | 单个 category 成功后立即提交状态、第二个 category 失败不会回滚第一个、任务锁重入退出 |
| `tests/test_resilience.py` | **修改** | 删除本地 `safe_collect` 复制，改为 `from collectors.utils import safe_collect` |

---

## 开发注意事项

### 1. 不要把 M1 做成半个 M3

本期不要顺手：

- 引入数据库
- 重写 CLI
- 改评分逻辑
- 做统一 notifier 抽象
- 改消息模板

这些都属于后续阶段。

### 2. 允许“部分成功”的真实状态存在

如果 AI、Game 成功，Device 失败，那么：

- `pushed_urls.json` 包含 AI + Game 的 URL
- 当日 `{period}.json` 只包含 AI + Game 字段
- 日志中明确记录 Device 失败

这不是异常设计，而是本期事务模型的目标行为。

### 3. 先实现接口，再切换调用方

建议开发顺序：

1. 先加 `Settings`
2. 再加 `StateStore`
3. 再加 `push_category()`
4. 最后修改 `main.py` 编排

这样每一步都容易验证，不会一次改太多。
