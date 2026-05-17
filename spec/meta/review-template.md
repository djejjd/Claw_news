# Review Template

## 评审规则

请只基于 `contract.md` 审查本次 diff。

1. 只判断是否满足 contract
2. 不允许提出 contract 外的新需求作为阻塞项
3. 所有 contract 外建议放入 `next_task`
4. Review 结论只能是：
   - `PASS`
   - `FAIL`：列出违反 contract 的具体项
5. 每个 `FAIL` 必须引用 contract 中的验收标准或 Review Checklist

## 输出结构

验收结论：`PASS / FAIL`

Spec 符合情况：
- [x] 验收标准 1
- [x] 验收标准 2
- [ ] 验收标准 3

阻塞问题：
1. 问题：
   对应 spec：
   需要修改：

非阻塞建议：
1. 建议：
   放入 `next_task`：

## 历史来源

原始版本来自：

- [spec/task001/attachments/gpt_review.md](/Users/lanser/Code/Claw_news/spec/task001/attachments/gpt_review.md)
