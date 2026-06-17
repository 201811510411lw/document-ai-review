# Document AI Review Runtime 架构边界

本文档细化当前 runtime 命名边界。终态架构决策以
[ADR 0001](adr/0001-langgraph-langchain-terminal-architecture.md) 为准。

---

## 1. 终态对象

| 层级 | 位置 | 职责 |
| --- | --- | --- |
| UseCase Thin Entry | `ai-service/app/use_cases/<name>/` | 输入组装、调用 graph、返回 `ReviewResult` |
| Workflow / Graph Runtime | `ai-service/app/workflows/<domain>/` | LangGraph StateGraph 编排、条件路由、人工复核节点 |
| LangChain Tools | `ai-service/app/capabilities/<domain>/tools.py` | 无状态结构化能力：分类、抽取、标准化等 |
| Domain Rules | `ai-service/app/workflows/<domain>/` 或后续 domain module | 最终合规判断、风险、人工复核需求、`RuleResult` |
| Agent Skill / Prompt / Policy | `.agents/skills/<skill>/SKILL.md` | 提示词、规则口径、guardrail、schema constraint |

Capability 不再是流程层对象，也不再负责组装平台级结果。

---

## 2. 平台调用契约

当前逐步收口到 runtime graph 契约：

```text
ReviewInputContext
    ↓
LangGraph StateGraph
    ↓
ReviewState
    ↓
runtime projection
    ↓
ReviewResult
```

平台层不得直接调用内部节点，例如：

- `load_document`
- `classify_document`
- `extract_fields`
- `normalize_fields`
- `run_rules`
- `summarize_risk`
- `manual_review`
- `reviewed`
- `reject`

这些名称可以作为 graph 内部节点存在，但不是平台公共接口。

---

## 3. Agent Skill 边界

`.agents/skills/<skill>/SKILL.md` 只描述：

- 能力边界；
- 支持的输入；
- 输出结构摘要；
- 规则摘要；
- prompt / policy / guardrail；
- 人工复核边界。

不做：

- 不写规则执行逻辑；
- 不写 workflow 编排逻辑；
- 不绕过 ReviewService 或 Graph Runtime；
- 不直接调用 OCR / LLM / OA / ERP；
- 不直接充当 runtime 入口。

---

## 4. ReviewResult 边界

`ReviewResult` 是平台级审核结果契约。当前仍包含：

```text
task_id
document_type
use_case_name
use_case_version
skill_name
skill_version
ruleset_version
capability_names
status
risk_level
needs_manual_review
manual_review
rule_results
summary
created_at
updated_at
skill_result
```

新架构语义：

- `use_case_name` / `use_case_version`：业务入口身份；
- `ruleset_version`：规则口径版本；
- `capability_names`：本次执行使用的 LangChain tool/domain capability 名称；
- `skill_result`：结构化领域 payload 和 trace/replay 所需材料；
- `skill_name` / `skill_version`：模型字段仍保留，但不作为新扩展点。

---

## 5. 当前状态

已按终态架构迁移：

- `business_license`；
- `tobacco_license`；
- `food_license`；
- `contract_review` 占位 runtime entry。

仍待迁移：

- `qc_document_review`；
- `tobacco_license_consistency_review`；
- `contract_review` 标准业务 graph；
- `ReviewService` 对 `qc_document_review` 和 `tobacco_license_consistency_review` 的旧 registry fallback。
