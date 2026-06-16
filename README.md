# document-ai-review

企业内部 AI 文档智能审核系统。当前主线已经从 `food_license` 单场景技术验证，收口为 **`use_cases + capabilities + Agent Skills`** 的私有化多场景审核架构。

`README.md` 是项目唯一主上下文。当前不使用 `CONTEXT.md` / `CONTEXT-MAP.md`，也不要求创建 `AGENTS.md` / `CLAUDE.md`。

---

## 1. 项目定位

`document-ai-review` 面向企业内部文档审核场景，目标是把证照、批次报告、检验报告、合同等非结构化材料转为可校验、可追溯、可复核的结构化审核结果。

平台不是单一 OCR 工具，也不是单一 `food_license` 审核服务。OCR、LLM、PDF、图片解析、OA 回写和 IM 通知都只是底层 Adapter。平台核心是：

- 用 Agent Skill 沉淀审核语义边界和业务规则口径；
- 用 runtime use_case 承接业务场景入口；
- 用 runtime capability 组织可复用执行能力；
- 用 workflow 编排字段抽取、规则执行、风险汇总和人工复核路由；
- 用统一 `ReviewResult` 输出结构化审核结果。

核心术语：

- Agent Skill：位于 `.agents/skills/<skill>/SKILL.md` 的描述层，只定义能力边界、输入输出、规则摘要和人工复核边界。
- use_case：位于 `ai-service/app/use_cases/` 的运行时业务入口，负责承接平台请求并启动对应 workflow。
- capability：位于 `ai-service/app/capabilities/` 的运行时能力单元，负责字段 schema、提示边界、规则归属和能力结果构造。
- workflow：位于 `ai-service/app/workflows/` 的 LangGraph 编排层，负责编排文档加载、字段抽取、Skill 规则审核、风险汇总和人工复核路由。
- RuleResult：Skill/LLM 规则审核输出的结构化规则结果。
- ReviewResult：平台级审核结果契约。

---

## 2. 当前主线

当前主线优先做架构收口，不继续扩展 `food_license` 业务能力。运行时结构已经固定为：

```text
ReviewService
    ↓
use_case_registry
    ↓
use_case.review(input_context)
    ↓
workflow
    ↓
capabilities
    ↓
Agent Skills + tools adapter
    ↓
ReviewResult
```

当前内置 use_case：

- `food_license`
- `qc_document_review`
- `tobacco_license_consistency_review`
- `contract_review`

其中：

- `food_license` 是历史 V1 兼容 use_case，继续保留快捷入口；
- `qc_document_review`
- `tobacco_license_consistency_review`
- `contract_review`

目前都还是主线占位 use_case，尚未进入完整业务规则实现。

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

### 3.2 runtime use_cases

路径：

```text
ai-service/app/use_cases/
```

职责：

- 作为平台可调用的业务场景入口；
- 定义 `name`、`version`、`ruleset_version`、`supported_document_types`；
- 实现 `supports(input_context)`；
- 实现 `review(input_context) -> ReviewResult`；
- 启动对应 workflow；
- 组装平台级 `ReviewResult`。

当前平台入口不再把 `Skill` 作为业务运行时对象；主入口对象是 use_case。

### 3.3 runtime capabilities

路径：

```text
ai-service/app/capabilities/
```

职责：

- 组织字段抽取逻辑；
- 组织提示词与结构化 schema；
- 组织 capability 专属字段 schema 和结果 payload；
- 为 workflow 提供可复用执行能力。

当前首个样板是：

```text
ai-service/app/capabilities/food_license/
```

其中包含：

- `prompt.py`
- `schemas.py`
- `executor.py`

---

## 4. 服务边界

| 模块 | 职责 |
| --- | --- |
| FastAPI | 提供 HTTP API、解析请求、做基础校验 |
| Review Service | 创建任务 ID、构造 `ReviewInputContext`、调用 `use_case_registry` |
| use_case_registry | 显式注册和选择 use_case |
| use_cases | 承接业务入口，调用 workflow，组装 `ReviewResult` |
| workflows | 编排 LangGraph / OCR / LLM / Skill 规则审核 / 人工复核路由 |
| capabilities | 承接字段 schema、提示边界和能力结果构造 |
| Agent Skills | 维护业务规则口径，供 runtime 读取并约束 LLM 结构化审核 |
| tools adapter | OCR、LLM、PDF、图片、ERP、OA、IM 等外部能力 Stub |
| repositories | 保存审核结果及后续人工复核、审计数据 |

平台层不能直接调用 workflow 或 capability 内部节点，例如：

- `load_document`
- `extract_fields`
- `run_rules`
- `summarize_risk`
- `route_review`

这些都属于内部实现细节。

---

## 5. `food_license` 兼容入口

当前保留的兼容链路：

```text
POST /api/v1/food-license/reviews
    ↓
ReviewService.review_food_license()
    ↓
ReviewService.review(use_case_name="food_license")
    ↓
use_case_registry.get("food_license")
    ↓
food_license use_case.review(input_context)
    ↓
food_license workflow
    ↓
food_license capability
    ↓
ReviewResult
```

这条链路必须继续保留，用于兼容现有调用方和测试。

---

## 6. 结果模型边界

当前 `ReviewResult` 已同时包含主线字段和兼容字段：

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

- `use_case_name` / `use_case_version`：主入口身份字段；
- `capability_names`：本次执行用到的 capability；
- `skill_name` / `skill_version`：兼容字段，当前短期镜像 use_case 身份；
- `skill_result`：兼容容器，当前承载 capability 专属 payload。

这意味着：

- 新文档和新代码优先使用 `use_case_*` 与 `capability_names`；
- 现有 API 和持久化暂不移除 `skill_*` / `skill_result`。

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
- workflow：只编排 Skill 规则审核，不内嵌业务规则。

---

## 8. 当前约束

当前主线明确不做：

- 不引入 Java / Spring Boot；
- 不接真实 OCR / LLM / OA / ERP；
- 不删除 `food_license` 兼容入口；
- 不继续扩展 `food_license` 规则；
- 不把 Agent Skill、use_case、capability 混成一个对象。

---

## 9. 当前状态

当前 `main` 已完成：

- runtime 入口从旧 `app/skills` 迁移到 `app/use_cases`；
- 新增 `app/capabilities`，并将 `food_license` 的真实能力迁入 capability 层；
- `ReviewService` 已切换到 `use_case_registry`；
- `ReviewInputContext`、`ReviewResult` 已新增 `use_case_*` 和 `capability_names`；
- `.agents/skills` 继续保留为 Agent Skill 描述层；
- `food_license` 兼容 API 和测试仍保留。

后续优先级：

1. 收口 README 和架构文档的旧 Skill 术语；
2. 收口测试与 stub 命名残留；
3. 再讨论 `ReviewResult.skill_*` / `skill_result` 的兼容迁移策略。

---

## 10. 相关文档

- [docs/skill-architecture.md](docs/skill-architecture.md)
- [docs/v1-python-architecture.md](docs/v1-python-architecture.md)
- [docs/product-requirements-ai-review.md](docs/product-requirements-ai-review.md)
- [docs/prd-food-license-v1.md](docs/prd-food-license-v1.md)
- [docs/api-food-license-v1.md](docs/api-food-license-v1.md)
