# Docs Index

本目录用于承载公开项目文档。

如果你只是想了解如何使用或部署项目，优先阅读：

1. 根目录 `README.md`
2. [operations/deploy/server-guide.md](operations/deploy/server-guide.md)
3. [CONVENTIONS.md](CONVENTIONS.md)
4. [operations/daily-checklist.md](operations/daily-checklist.md)（日常巡检与只读内容回放）
5. [operations/troubleshooting.md](operations/troubleshooting.md)（回放和运行故障排查）

## 目录说明

### `docs/operations/`

放部署、运维和运行环境相关文档。

当前包括：

1. 服务器部署指南
2. launchd 模板
3. 日常巡检清单（含只读内容选材回放命令）
4. 故障排查速查（含回放结果解释）

内容选材回放使用以下只读命令，不触发真实推送，也不写入生产发布状态：

```bash
./venv/bin/python scripts/replay-content-selection.py \
  --data-dir data --at 2026-07-11T09:00:00+08:00 --format json
```

回放只用于比较来源/分类分布、跨日补位和拒绝原因；不得提交生产 `data/`、候选原文、运行时 `feeds.yaml` 或任何凭据。

### `docs/architecture/`

放跨功能的长期架构说明和设计决策。

适合阅读的内容：

1. 架构路线图
2. 清理与公开化决策

### `docs/archive/`

放历史探索材料。

说明：

1. 该目录不是当前功能说明入口
2. 其中部分文档仅用于保留历史背景，不保证与当前实现一致

## 文档规范

项目公开文档的命名与放置规则见：

- [CONVENTIONS.md](CONVENTIONS.md)
- [PUBLICATION_POLICY.md](PUBLICATION_POLICY.md)
