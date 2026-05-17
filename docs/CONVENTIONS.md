# Documentation Conventions

## 目标

本规范用于约束公开项目文档的命名和放置位置，保证后续新增文档易于理解、检索和维护。

## 目录规则

公开文档只使用以下目录：

1. `docs/operations/`
   - 部署、运维、运行环境说明
2. `docs/architecture/`
   - 长期有效的架构说明、路线图、设计决策
3. `docs/archive/`
   - 历史探索材料，不作为当前实现入口

## 命名规则

1. 优先使用稳定语义名，不再以日期作为主文件名
2. 文件名使用小写字母、数字、短横线
3. 避免使用 `final`、`new`、`latest`、`v2` 作为长期正式文件名
4. 示例配置或模板文件统一使用 `.example`
5. 如果文档是决策记录，优先使用 `*-design.md`、`*-roadmap.md`、`*-guide.md`

## 内容规则

1. 不在公开文档中写入真实密钥、token、webhook
2. 不在公开文档中写入个人机器绝对路径
3. 如果必须展示路径，使用占位符，例如 `{{PROJECT_DIR}}`
4. 示例命令应尽量可直接在新环境复用
5. 历史文档如与当前实现不一致，应明确放入 `docs/archive/`

## 阅读顺序

1. 想快速上手，先读根目录 `README.md`
2. 想部署到服务器，读 `docs/operations/deploy/server-guide.md`
3. 想看 launchd 配置，使用 `docs/operations/launchd/*.example`
4. 想了解长期架构背景，读 `docs/architecture/`

## 发布规则

公开提交边界与筛选规则见：

- [PUBLICATION_POLICY.md](PUBLICATION_POLICY.md)
