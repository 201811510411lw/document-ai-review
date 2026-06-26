# document-ai-review

企业内部 AI 文档智能审核系统。当前主线已经确认升级为 **LangGraph + LangChain 驱动的 AI Workflow / Agent Platform**；后续按 breaking change 路线演进，不再把旧 `UseCase + Workflow + Capability` 形态作为兼容目标。当前交付主线优先迁移 **营业执照单证审核 `business_license`**，再用烟草证等第二条证照链路验证多证照扩展方式。

`README.md` 是项目唯一主上下文。当前不使用 `CONTEXT.md` / `CONTEXT-MAP.md`，也不要求创建 `AGENTS.md` / `CLAUDE.md`。

---

## 1. 项目定位

`document-ai-review` 面向企业内部文档审核场景，目标是把证照、批次报告、检验报告、合同等非结构化材料转为可校验、可追溯、可复核的结构化审核结果。

平台不是单一 OCR 工具，也不是单一证照审核服务。OCR、LLM、PDF、图片解析、OA 回写和 IM 通知都只是底层 Adapter。平台终态核心是：

- 用 UseCase 作为 Thin Entry，只负责输入组装、必要校验、调用 graph 和返回结果；
- 用 LangGraph StateGraph 作为 workflow runtime，编排字段抽取、规则执行、条件路由和人工复核；
- 用 LangChain Tools 组织 OCR、视觉解析、字段抽取、字段标准化、文档分类等无状态能力；
- 用 Agent Skill / Prompt / Policy Layer 沉淀提示词、规则约束、guardrail 和 schema constraint；
- 用 Domain Rules 承担最终合规判断、风险汇总和人工复核决策；
- 用统一 `ReviewResult` 输出结构化审核结果。

核心术语：

- UseCase：Thin Entry，负责承接平台请求、组装输入、调用对应 LangGraph workflow、返回 `ReviewResult`。
- Workflow：LangGraph StateGraph，负责显式节点、边、条件路由、人工复核节点和可追踪执行。
- LangChain Tool：无状态能力接口，负责 OCR/视觉解析、字段抽取、字段标准化、文档分类等结构化输入输出能力。
- Agent Skill：位于 `.agents/skills/<skill>/SKILL.md` 的 Prompt / Policy Layer，只定义能力边界、输入输出、规则摘要、提示约束和人工复核边界。
- Domain Rules：确定性业务规则层，负责最终合规判断、风险等级、人工复核需求和 `RuleResult` 生成。
- RuleResult：Domain Rules 输出的结构化规则结果；LLM 可以辅助解释和抽取，但不能直接做最终审核决策。
- ReviewResult：平台级审核结果契约。

---

## 2. 当前主线

当前主线优先完成 `business_license` 的 LangGraph + LangChain 架构迁移，再用 `tobacco_license` 作为第二条标准 workflow 验证多证照扩展方式。终态运行时结构固定为：

```text
ReviewService
    ↓
UseCase Thin Entry
    ↓
Workflow Registry
    ↓
LangGraph StateGraph
    ↓
LangChain Tools + Domain Rules
    ↓
Agent Skills / Prompt / Policy
    ↓
ReviewResult
```

当前内置 use_case：

- `business_license`
- `food_license`
- `tobacco_license`
- `qc_document_review`
- `tobacco_license_consistency_review`
- `contract_review`

其中：

- `business_license` 是第一条迁移主线，用于跑通 LangGraph StateGraph、LangChain Tools、Domain Rules、`ReviewResult` 生成、持久化、查询和人工复核；
- `tobacco_license` 是第二条迁移主线，用于验证多证照 Graph 扩展方式；
- `food_license` 已接入 Thin Entry / runtime projection / Workflow Registry；
- `contract_review` 已接入 Workflow Registry，占位业务能力后续再按标准 graph 实现；
- `qc_document_review`、`tobacco_license_consistency_review` 后续按同一终态架构改造，不再以旧兼容形态继续扩展。

---

## 3. 三层边界

### 3.1 Agent Skills

路径：

```text
.agents/skills/<skill>/SKILL.md
```

职责：

- 描述能力边界；
- 描述支持的输入；
- 描述输出结构摘要；
- 维护业务规则口径；
- 描述人工复核边界；
- 说明与 runtime 的关系。

不做：

- 不直接执行规则；
- 不直接调用 workflow 节点；
- 不直接调用 OCR / LLM / OA / ERP / IM；
- 不充当平台运行时入口。

### 3.2 UseCase Thin Entry

路径：

```text
ai-service/app/use_cases/
```

职责：

- 作为平台可调用的薄入口；
- 定义 `name`、`version`、`ruleset_version`、`supported_document_types`；
- 实现 `supports(input_context)`；
- 调用对应 LangGraph workflow；
- 通过 runtime projection 返回 `ReviewResult`。

UseCase 不承载流程编排、规则判断或 capability result 组装。

### 3.3 LangChain Tools

路径：

```text
ai-service/app/capabilities/
```

职责：

- 组织无状态结构化工具；
- 承接文档分类、字段抽取、字段标准化等能力；
- 使用 Pydantic / TypedDict 等结构化输入输出；
- 供 LangGraph workflow 节点调用。

当前已迁移：

```text
ai-service/app/capabilities/business_license/
ai-service/app/capabilities/tobacco_license/
```

Capability 不再是流程层对象，也不负责组装平台级 `ReviewResult`。

---

## 4. 服务边界

| 模块 | 职责 |
| --- | --- |
| FastAPI | 提供 HTTP API、解析请求、做基础校验 |
| Review Service | 创建任务 ID、构造 `ReviewInputContext`、调用薄入口并保存结果 |
| Workflow Registry | 注册和选择 graph definition |
| UseCase Thin Entry | 调用 workflow 并通过 runtime projection 返回 `ReviewResult` |
| workflows | 编排 LangGraph StateGraph、条件路由、人工复核节点 |
| LangChain Tools | 承接分类、抽取、标准化等无状态结构化能力 |
| Domain Rules | 承担最终合规判断、风险等级和人工复核需求 |
| Agent Skills | 维护 Prompt / Policy / guardrail / schema constraint |
| tools adapter | 远程文件、OCR/视觉识别、规则审核、企微通知等外部能力 Adapter |
| repositories | 保存审核结果及后续人工复核、审计数据 |

平台层不能直接调用 workflow 或 capability 内部节点，例如：

- `load_document`
- `extract_fields`
- `run_rules`
- `summarize_risk`
- `manual_review`
- `reviewed`
- `reject`

这些都属于内部实现细节。

---

## 5. 迁移状态

已按终态架构迁移：

- `business_license`：LangGraph StateGraph、LangChain Tools、conditional routing、Thin Entry、runtime projection；
- `tobacco_license`：第二条标准 LangGraph workflow、LangChain Tools、Thin Entry、runtime projection；
- `food_license`：既有 LangGraph workflow 已接入 Thin Entry、runtime projection 和 Workflow Registry；
- `ReviewGraphRegistry`：已具备注册、获取、选择 graph definition 的基础契约；
- trace/replay：已具备稳定 JSON 摘要契约。

仍待迁移：

- `qc_document_review`；
- `tobacco_license_consistency_review`；
- `contract_review` 标准业务 graph 实现；
- `ReviewService` 对 `qc_document_review` 和 `tobacco_license_consistency_review` 的旧 registry fallback。

---

## 6. 结果模型边界

当前 `ReviewResult` 包含：

- `use_case_name`
- `use_case_version`
- `skill_name`
- `skill_version`
- `ruleset_version`
- `capability_names`
- `rule_results`
- `manual_review`
- `summary`
- `skill_result`

当前语义约定：

- `use_case_name` / `use_case_version`：业务入口身份字段；
- `capability_names`：本次执行用到的 LangChain tool/domain capability 名称；
- `skill_name` / `skill_version`：模型字段仍保留，但不作为新扩展点；
- `skill_result`：结构化领域 payload 和 trace/replay 所需材料。

这意味着：

- 新文档和新代码优先使用 `use_case_*`、`capability_names`、`ruleset_version` 和 `skill_result`；
- 不再把 `skill_*` 当作架构扩展点。

---

## 7. 推荐目录结构

```text
document-ai-review/
├── .agents/
│   └── skills/
├── ai-service/
│   ├── app/
│   │   ├── api/
│   │   ├── capabilities/
│   │   ├── core/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── tools/
│   │   ├── use_cases/
│   │   └── workflows/
│   ├── tests/
│   └── pytest.ini
├── docs/
└── README.md
```

规则边界：

- `.agents/skills/<skill>/SKILL.md`：业务规则口径；
- `ai-service/app/tools/skill_rule_review.py`：读取 Skill、调用 LLM、解析结构化审核结果；
- workflow：编排 LangGraph 节点、条件路由和人工复核节点；
- Domain Rules：承担最终合规判断。

---

## 8. 当前约束

当前主线明确不做：

- 不引入 Java / Spring Boot；
- 不接真实 OCR / LLM / OA / ERP；
- 不让 LLM 直接做最终合规决策；
- 不用 LangChain agent 替代 deterministic workflow；
- 不把 Agent Skill、UseCase、Workflow、LangChain Tool、Domain Rules 混成一个对象。

---

## 9. 当前状态

当前已完成：

- 终态架构 ADR；
- 统一 `ReviewState` / `ReviewGraphDefinition` / runtime projection；
- `business_license` 与 `tobacco_license` 标准 LangGraph workflow；
- `business_license`、`tobacco_license`、`food_license`、`qc_document_review` 与 `tobacco_license_consistency_review` Thin Entry / runtime projection；
- `business_license` 与 `tobacco_license` LangChain Tools；
- `ReviewService` 已切换为只调用 `ReviewGraphRegistry` runtime entry，不再保留旧 registry fallback；
- 营业执照审核已具备 PDF/图片/远程文件接入边界、视觉识别 adapter、字段抽取和标准化结果容器、规则审核、`ReviewResult` 输出；
- 营业执照审核结果已具备 MySQL 完整 payload 保存、投影表保存、列表查询、详情查询和轻量人工复核写回接口；
- `ReviewInputContext`、`ReviewResult` 已新增 `use_case_*` 和 `capability_names`；
- `.agents/skills` 继续保留为 Agent Skill 描述层；
- runtime trace/replay 稳定摘要契约。

后续优先级：

1. 将 `contract_review` 占位 runtime entry 替换为标准业务 graph；
2. 将更多最终合规判断从 LLM 规则审核过渡到 deterministic Domain Rules；
3. 收口 `skill_*` 字段的长期模型语义。

---

## 10. 相关文档

- [docs/PRD.md](docs/PRD.md)
- [docs/SPEC.md](docs/SPEC.md)
- [docs/API.md](docs/API.md)
