# Documentation Publication Policy

## 目标

本规则用于区分哪些文档可以进入公开 GitHub 仓库，哪些文档必须继续保留为内部材料。

以后新增文档时，先按本文件判断，再决定是否提交到公开仓库。

## 公开文档白名单

以下类型默认允许公开：

1. 根目录 `README.md`
2. `docs/operations/` 下的公开部署与运维说明
3. `docs/operations/launchd/*.example`
4. `docs/architecture/` 下的长期架构说明和设计决策
5. `docs/README.md`
6. `docs/CONVENTIONS.md`
7. 本文件 `docs/PUBLICATION_POLICY.md`

## 内部文档黑名单

以下类型默认不公开：

1. `spec/` 全部
2. `spec/meta/` 全部
3. `spec/taskNNN/attachments/` 全部
4. `docs/tasks/` 全部
5. `docs/archive/` 全部
6. `docs/operations/launchd/*.plist` 非 example 文件

## 必须拦截的内容

任何文档只要出现以下内容，就不能直接公开：

1. 真实密钥、token、webhook、cookie
2. 个人机器绝对路径
3. 内部协作规则
4. reviewer / agent / worker 角色指令
5. 私有部署细节或只适用于个人环境的命令

## 公开前检查清单

每次准备公开提交文档时，至少检查：

1. 是否引用了 `spec/`
2. 是否引用了 `docs/tasks/`
3. 是否引用了 `docs/archive/`
4. 是否包含 `/Users/...`、`C:\\...` 等绝对路径
5. 是否包含真实 webhook / key / token
6. 是否包含内部评审或 agent 协作措辞

## 推荐流程

1. 先判断文档属于公开白名单还是内部黑名单
2. 如果属于公开文档，再执行敏感信息检查
3. 如果文档同时承担内部和公开用途，拆成两份：
   - 内部版保留原文
   - 公开版保留结果和必要说明

## 当前公开提交建议

当前仓库文档建议公开的范围：

1. `README.md`
2. `docs/README.md`
3. `docs/CONVENTIONS.md`
4. `docs/PUBLICATION_POLICY.md`
5. `docs/operations/deploy/server-guide.md`
6. `docs/operations/launchd/*.example`
7. `docs/architecture/roadmap/*.md`
8. `docs/architecture/decisions/*.md`
