# Task 1 Report: 扩展内容源配置并收口历史分类

## 已完成内容

- 在 `collectors/ai_rss.py` 中新增并收口了三组默认源配置：
  - `DEFAULT_AI_RSS_FEEDS`
  - `DEFAULT_TOOL_RSS_FEEDS`
  - `DEFAULT_GAME_RSS_FEEDS`
- 新增了三个加载函数：
  - `load_tool_rss_feeds()`
  - `load_game_rss_feeds()`
  - `load_all_rss_feeds()`
- 保持既有的 `AI_RSS_FEEDS` / `AI_RSS_MODE` 解析模式不变，并将其抽成通用 `_load_feeds()`，方便三类源复用。
- 在 `collectors/rss_sources.py` 中将 `FEED_CONFIGS` 扩展为 ai + tool + game 的组合默认源。
- 将历史 `device` 分类在本任务触达的测试中统一收口为 `tool`。

## 测试结果

- `venv/bin/pytest tests/test_ai_rss.py tests/test_rss_collector.py -q`
- `venv/bin/pytest -q`

结果：全部通过，`322 passed`.

## 备注

- 本次修改没有引入已知遗留问题。

## Review Fix Addendum

- 修复了 `tool -> device` 的兼容桥，避免 Task 1 新增的 `tool` feed 在当前下游运行路径中被丢弃：
  - `collectors/base.py` 扩展分类字面量，并新增 `to_legacy_category()`。
  - `aggregator/merger.py` 在 legacy merge 路径中将 `tool` 项收口到既有 `device` bucket。
  - `pusher/wecom.py` 同时接受 `tool` bucket，并在推送时继续使用 legacy `device` 语义与展示。
- 修复了 `RssCollector()` 默认路径未接入 loader 的问题：
  - `collectors/rss_sources.py` 现在在实例化时调用 `load_all_rss_feeds()`，而不是依赖导入时快照。
  - 这样 `AI_RSS_*` / `TOOL_RSS_*` / `GAME_RSS_*` 环境变量会在默认构造路径中生效。
- 新增回归测试：
  - `tests/test_rss_collector.py::test_rss_collector_defaults_use_runtime_loader_feeds`
  - `tests/test_merger.py::TestMerger::test_tool_items_flow_into_legacy_device_bucket`
  - `tests/test_wecom.py::TestWeComPusher::test_push_accepts_tool_bucket_alias`

### 验证

- Red:
  - `venv/bin/pytest tests/test_rss_collector.py tests/test_merger.py tests/test_wecom.py -q`
  - 结果：按预期失败，暴露默认 loader 未生效与 `tool` bucket 被丢弃的问题。
- Green:
  - `venv/bin/pytest tests/test_ai_rss.py tests/test_rss_collector.py tests/test_merger.py tests/test_wecom.py -q`
  - 结果：`82 passed`
