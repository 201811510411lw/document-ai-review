# Domain Docs

本文档说明 engineering skills 在探索本项目代码库时，应如何读取和使用项目领域文档。

## 探索前先读取

- 仓库根目录的 `README.md`。这是本项目的主要项目上下文。
- 当任务涉及服务边界、系统架构或调用链路时，优先读取 `README.md` 中的架构说明；如果未来重新新增 `docs/architecture.md`，再按需读取。
- 如果未来存在 `docs/adr/`，读取与当前工作区域相关的 ADR。

本项目当前有意不使用 `CONTEXT.md` 或 `CONTEXT-MAP.md`。不要预先建议创建这些文件；应使用 `README.md` 作为项目术语和领域上下文来源。

## 文档布局

单一上下文仓库：

```text
/
├── README.md
├── docs/
└── ai-service/
```

## 使用 README 术语

当输出涉及领域概念、issue 标题、重构建议、诊断假设或测试命名时，使用 `README.md` 中已有的项目术语。

当前重要术语包括：

- Document AI Review Agent / Skill 平台
- 食品安全证照检测
- backend-java
- ai-service
- 审核任务
- 字段抽取
- 规则校验
- 风险报告
- 人工复核
- 审计留痕

## 标明架构冲突

如果输出内容与 `README.md` 或未来的 ADR 冲突，需要明确指出冲突，不要静默覆盖既有约定。
