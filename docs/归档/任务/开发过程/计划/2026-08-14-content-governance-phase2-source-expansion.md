# 内容治理 Phase 2 - 已批准来源接入任务

**任务编号：** CG-P2-02  
**依赖任务：** CG-P2-01（四分类任务，待审核）  
**允许并行任务：** 无  
**预计修改文件：** `collectors/ai_rss.py`、`feeds.example.yaml`、`docs/研究/来源清单.md`、`docs/架构/来源管理.md`、来源配置和策略测试  
**不得修改文件：** 分类器、评分常量、选材算法、投递恢复、消息协议、数据库/网站 API  
**完成状态：** completed

## 1. 背景

Phase 1 已建立来源上限与健康基线，CG-P2-01 已建立四分类契约，但候选池的来源仍偏少。批准方案第 6 节已列出生产容器实测可达的公开 RSS/Atom 来源。

## 2. 目标

将批准清单中的公开 RSS/Atom 来源按四分类接入默认配置和示例配置，并为每个来源声明保留期、质量权重、过滤档位和快讯上限，不改变既有采集器或评分常量。

## 3. 前置依赖

CG-P2-01 提供 `digital` 运行时分类；批准设计为 `docs/计划/内容治理方案.md` 第 6、8 节。

## 4. 输入与输出契约

输入为批准清单的公开 feed URL。输出为 `load_all_rss_feeds()` 中带稳定 source 名、分类和完整来源策略的配置项。V2EX、cnBeta 保持 `fast_news`、24 小时、硬上限 2；其他来源按批准方案定义的保守层级和过滤档位接入。单个 feed 失败继续由 RSS collector 隔离。

## 5. 修改范围

仅新增 OSCHINA、V2EX、Hacker News、cnBeta、9to5Mac、TechCrunch、GamesIndustry、Nintendo Life、InfoQ、HF Blog、arXiv cs.AI、arXiv cs.CL 的配置、测试与中文来源说明。禁止新增未批准来源、RSSHub、代理、数据库字段或抓取逻辑。

## 6. 禁止事项

不得把新来源直接加入用户本地 `feeds.yaml` 或生产 `data/`；不得修改质量评分公式、单源上限语义、动态分类、LLM 或投递链路；不得将本机网络失败静默写为来源无效。

## 7. 执行要求

测试先行：先断言默认来源集合、分类和快讯上限，确认失败后写最小配置。每个 URL 做只读 HTTP 可达性探测；结果只记录 HTTP/解析结论，不保存文章正文。海外源本机失败需如实标记为待生产容器代理复验。

## 8. 实施步骤

- [x] 新增失败测试，约束十二个来源、稳定 source 名、分类和 V2EX/cnBeta 上限。
- [x] 更新默认 RSS 与 `feeds.example.yaml`，保持环境变量 `append/replace` 语义。
- [x] 更新来源清单和来源管理说明，写明每源策略与观察边界。
- [x] 对每个 URL 做只读可达性探测，记录结果和未验证项。
- [x] 运行精确测试、全量测试、lint、format 与 diff 检查；已完成独立代码审查。

## 9. 验收标准

1. 批准清单的十二个 feed 均具备稳定 source 名、分类和完整策略。
2. V2EX、cnBeta 使用 `fast_news`、24 小时和最大 2 条；其他来源不突破已定硬上限语义。
3. 默认加载、示例配置、来源策略 registry 和来源文档保持一致。
4. 单个 URL 网络不可达不会改变代码配置或阻断其他来源；未验证项明确记录。
5. 指定检查命令全部通过。

## 10. 检查命令

```bash
./venv/bin/pytest tests/test_ai_rss.py tests/test_source_policy.py tests/test_feeds_ithome_policy.py -v
./venv/bin/pytest -v
./venv/bin/ruff check .
./venv/bin/ruff format --check .
git diff --check
```

## 11. 交付前自检

- [x] 已阅读任务、批准设计、`AGENTS.md`、来源文档和相关加载器。
- [x] 只接入批准来源，未改采集器、评分和投递语义。
- [x] 每源有策略、测试和中文说明；网络未验证项未被表述为已验证。
- [x] 示例配置未含密钥、生产数据或机器路径。
- [x] 已检查完整 diff；未提交、未推送、未合并，已完成独立代码审核。

## 12. 交付格式

按 `AGENTS.md` 固定十段格式，额外列出来源/分类/策略矩阵、URL 可达性结论、未验证生产环境项及代码审查结论。
