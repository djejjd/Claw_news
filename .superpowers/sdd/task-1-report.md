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
