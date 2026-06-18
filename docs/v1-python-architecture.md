# V1 Python Architecture

本文档说明 `document-ai-review` 当前 V1 Python 服务的目标架构。架构决策以
[ADR 0001](adr/0001-langgraph-langchain-terminal-architecture.md) 为准：后续按
LangGraph + LangChain 驱动的 AI Workflow / Agent Platform 演进，不再把旧
`UseCase + Workflow + Capability` 形态作为兼容目标。

---

## 1. 总体链路

V1 不引入 Java / Spring Boot，不拆分为多服务。当前只有一个 Python 服务：
`ai-service`。

```text
业务系统 / 管理后台 / 测试脚本
    ↓
FastAPI HTTP API
    ↓
Review Service
    ↓
UseCase Thin Entry
    ↓
Workflow Registry / Graph Runtime
    ↓
LangGraph StateGraph
    ↓
LangChain Tools + Domain Rules
    ↓
ReviewResult
    ↓
Repository
```

---

## 2. 职责边界

### FastAPI

FastAPI 是 HTTP 边界，负责接收请求、做基础校验、把审核请求交给
`ReviewService`。FastAPI 不承载规则执行，不直接调用 graph 节点或 tool。

### Review Service

Review Service 负责创建审核任务 ID、构造 `ReviewInputContext`、调用
`ReviewGraphRegistry` runtime entry，并在配置了 repository 时保存
`ReviewResult`。服务层不再保留旧 registry fallback。

### UseCase Thin Entry

UseCase 只作为薄入口：

- 声明 `name`、`version`、`ruleset_version`、`supported_document_types`；
- 接收 `ReviewInputContext`；
- 调用对应 workflow / graph；
- 通过 runtime projection 返回 `ReviewResult`。

UseCase 不再手写流程编排、规则判断或 capability result 组装。

### Workflow / Graph Runtime

`app/workflows/` 是 LangGraph workflow runtime。每个证照或文档场景应提供独立
StateGraph，显式表达节点、边、条件路由和人工复核节点。

当前已按该方向迁移的 workflow：

- `business_license`
- `tobacco_license`
- `food_license`

### LangChain Tools

`app/capabilities/<domain>/tools.py` 承接可复用、无状态、结构化输入输出的工具能力，
例如文档分类、字段抽取、字段标准化。Capability 在终态语义中不是流程层，也不负责
最终合规判断。

### Domain Rules

Domain Rules 负责最终合规判断、风险等级、人工复核需求和 `RuleResult`。LLM 可以
辅助抽取、分类和解释，但不能直接做最终审核决策。

### Agent Skill / Prompt / Policy

`.agents/skills/<skill>/SKILL.md` 是 Prompt / Policy Layer，只描述能力边界、规则
口径、guardrail 和 schema constraint。它不控制 workflow，不直接调用 OCR / LLM /
OA / ERP。

### Repository

Repository 层负责结果保存、查询、人工复核和审计留痕。完整 `ReviewResult` 快照仍是
审计和回放的基础。

---

## 3. 结果模型

`ReviewResult` 仍是平台级输出契约。新代码应优先使用：

- `use_case_name`
- `use_case_version`
- `ruleset_version`
- `capability_names`
- `rule_results`
- `manual_review`
- `skill_result`

`skill_name` / `skill_version` 仍存在于模型中，但不再作为架构主语义扩展点。

---

## 4. 当前迁移状态

已完成的架构迁移切片：

- 终态架构 ADR；
- 统一 `ReviewState` / `ReviewGraphDefinition` / runtime projection；
- `business_license` LangChain tools；
- `business_license` conditional StateGraph routing；
- `business_license` Thin Entry；
- `ReviewGraphRegistry` 基础契约；
- `tobacco_license` 标准 StateGraph 和 Thin Entry；
- `food_license` Thin Entry 和 runtime projection；
- `contract_review` 占位 runtime entry；
- runtime trace/replay 稳定摘要契约。

后续仍需迁移的旧形态：

- `qc_document_review`、`tobacco_license_consistency_review` 仍需按同一 graph runtime 契约收口；
- `contract_review` 仍需从占位 runtime entry 替换为标准业务 graph；
- `ReviewService` 对 `qc_document_review` 和 `tobacco_license_consistency_review` 的旧 registry fallback 仍需删除。
