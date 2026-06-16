# Domain Docs

本文档说明 engineering skills 在探索本项目代码库时，应如何读取和使用项目领域文档。

## 探索前先读取

- 仓库根目录的 `README.md`。这是本项目的主要项目上下文。
- 当任务涉及服务边界、系统架构或调用链路时，优先读取 `README.md` 中的架构说明；如果需要更细的 V1 架构上下文，再读取 `docs/v1-python-architecture.md`。
- 如果未来存在 `docs/adr/`，读取与当前工作区域相关的 ADR。

本项目当前有意不使用 `CONTEXT.md` 或 `CONTEXT-MAP.md`。不要预先建议创建这些文件；应使用 `README.md` 作为项目术语和领域上下文来源。

## 文档布局

单一上下文仓库：

```text
/
├── README.md
├── docs/
├── ai-service/
├── rules/
└── scripts/
```

## 使用 README 术语

当输出涉及领域概念、issue 标题、重构建议、诊断假设或测试命名时，使用 `README.md` 中已有的项目术语。

当前重要术语包括：

- Document AI Review Agent / Skill 平台
- 食品安全证照检测
- ai-service
- FastAPI
- LangGraph
- LangChain
- Skill 规则审核
- 审核任务
- 字段抽取
- 字段规范化
- 规则校验
- 风险报告
- 人工复核
- 审计留痕

## V1 架构约定

当前 V1 以纯 Python `ai-service` 为主，不拆分 Java / Spring Boot 后端服务。

- FastAPI 负责 HTTP API。
- LangGraph 是食品安全证照检测 V1 审核流程的核心编排方式。
- LangChain 负责模型调用、Prompt、结构化输出和工具封装。
- Agent Skill 维护规则口径，Python Runtime 读取 Skill 并调用 LLM 输出结构化规则结果。
- Python 服务同时承担审核任务管理、审核结果保存、人工复核和审计日志。
- 后续企业系统可以通过 HTTP API 调用该 Python 服务。

## 标明架构冲突

如果输出内容与 `README.md` 或未来的 ADR 冲突，需要明确指出冲突，不要静默覆盖既有约定。
