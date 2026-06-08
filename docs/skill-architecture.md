# Document AI Review Skill 架构边界

本文档明确 `document-ai-review` 的 Skill 架构边界。`README.md` 仍然是项目唯一主上下文；本文档作为 Skill 运行时、目录组织和扩展约束的细化说明。

---

## 1. Skill 定义

Skill 是平台中的一等业务能力对象，不只是 Prompt、规则文件或 LangGraph 工作流的别名。

一个 Skill 同时承担三类边界：

- 运行时边界：平台通过稳定接口发现、路由并执行 Skill；
- 组织边界：配置、Prompt、规则、模型、工作流、节点和文档按 Skill 纵向组织；
- 业务边界：一个 Skill 对应一种可独立演进的文档审核能力，例如 `food_license`。

V1 的第一个内置 Skill 是：

```text
food_license
```

它负责食品安全证照检测，不把食品安全证照的业务规则散落到平台横向模块中。

---

## 2. 平台调用契约

平台只调用稳定的 Skill 级接口：

```text
name
version
supported_document_types
supports(input_context)
review(input_context) -> ReviewResult
```

平台不得直接调用 Skill 内部节点或步骤，例如：

- `extract_fields`
- `run_rules`
- `summarize_risk`
- `route_review`

这些名称可以作为 Skill 内部 LangGraph 节点或工作流约定存在，但不是平台对 Skill 的公共调用接口。

平台入口的统一执行链路是：

```text
FastAPI HTTP API
    ↓
Review Service
    ↓
Skill Registry
    ↓
Skill.review(input_context)
    ↓
ReviewResult
```

所有审核入口都必须经过 Review Service 和 Skill Registry，不能绕过 Registry 直接调用某个具体 Skill。

---

## 3. Registry V1

V1 Skill Registry 只支持显式注册内置 Skill。

V1 不做：

- 目录扫描；
- 外部 Skill 加载；
- 插件市场；
- 热加载；
- 租户级 Skill 覆盖；
- 运行时动态启停 Skill。

Registry 负责：

- 加载并校验内置 Skill 的 `metadata.yaml`；
- 根据 `supported_document_types`、`input_modes` 和 `supports(input_context)` 选择 Skill；
- 提供 `get` / `list` 等 Skill 查询入口；
- 将请求路由到 `Skill.review(input_context)`；
- 在结果和审计日志中保留 Skill 身份信息。

`app/skills/base.py` 是 Skill 基础接口 / 协议，定义平台可依赖的 Skill 级契约。`app/skills/registry.py` 是显式注册内置 Skill、加载并校验 `metadata.yaml`、提供 `get` / `list` 的入口。

Review Service 依赖 Skill Registry，但 Registry 本身属于 Skill 平台层，不放在 `app/services/` 下。

---

## 4. metadata.yaml

`metadata.yaml` 是 Skill 的运行时 manifest，也是 Skill 元信息的权威来源。

V1 至少应表达：

```yaml
name: food_license
version: v1
display_name: 食品安全证照检测
supported_document_types:
  - food_license
input_modes:
  - ocr_text
ruleset_version: food-license-rules-v1
```

代码、API 文档和审计日志中的 Skill 名称、版本、支持文档类型和规则集版本，应以 `metadata.yaml` 为准。

---

## 5. 目录边界

V1 采用平台横向基础设施 + Skill 纵向包结构。

推荐结构：

```text
ai-service/
└── app/
    ├── api/
    ├── core/
    ├── models/
    ├── repositories/
    ├── services/
    │   ├── review_service.py
    │   └── manual_review_service.py
    ├── rules/
    │   ├── engine.py
    │   ├── protocol.py
    │   └── result.py
    └── skills/
        ├── base.py
        ├── registry.py
        └── food_license/
            ├── skill.py
            ├── metadata.yaml
            ├── README.md
            ├── models.py
            ├── prompts/
            ├── chains/
            ├── graphs/
            ├── nodes/
            ├── review_policy.py
            └── rules/
                ├── rules.yaml
                └── rule_defs.py
```

`app/rules/` 只放通用规则基础设施，例如规则协议、规则引擎、通用结果结构和默认风险汇总辅助函数。

`app/rules/` 不放具体业务规则，例如：

- `FOOD_LICENSE_EXISTS`
- `FOOD_LICENSE_EXPIRED`
- `SUBJECT_NAME_MATCH`
- `CREDIT_CODE_MATCH`

这些食品安全证照规则定义和 `rules.yaml` 必须放在 `app/skills/food_license/rules/` 内。

---

## 6. ReviewResult 边界

`ReviewResult` 是平台级返回契约，必须保留稳定的跨 Skill 字段。

推荐平台级字段：

```text
task_id
status
document_type
skill_name
skill_version
ruleset_version
risk_level
needs_manual_review
manual_review
rule_results
summary
created_at
updated_at
skill_result
```

`skill_result` 用于承载 Skill 专属 payload。食品安全证照 V1 中，以下内容应放在 `skill_result` 内：

- `extracted_fields`
- `normalized_fields`
- 食品安全证照专属解释信息；
- Skill 内部工作流需要返回给调用方的其他结构化结果。

长期演进时，不应把食品安全证照专属字段固化为所有 Skill 都必须具备的顶层字段。

---

## 7. 人工复核边界

人工复核基础设施属于平台，包括：

- 人工复核状态；
- 人工复核动作；
- 复核人和备注；
- 人工复核记录保存；
- 人工复核审计日志。

是否需要人工复核、初始人工复核状态和复核原因由 Skill 在 `review(input_context)` 中根据规则结果和审核策略决定。

V1 人工复核状态枚举：

- `NOT_REQUIRED`
- `PENDING`
- `COMPLETED`

---

## 8. API 入口边界

V1 保留食品安全证照快捷入口：

```text
POST /api/v1/food-license/reviews
```

该入口是 `food_license` Skill 的便捷 API，但实现上仍必须走：

```text
FastAPI
    ↓
Review Service
    ↓
Skill Registry
    ↓
food_license.review(input_context)
```

后续平台通用入口为：

```text
POST /api/v1/reviews
```

通用入口根据输入上下文、声明文档类型和 Registry 路由到合适的 Skill。快捷入口和通用入口不能维护两套审核逻辑。

---

## 9. V1 规则约束

V1 只支持 Skill 包内静态 `rules.yaml`。

V1 不做：

- 数据库规则管理；
- 外部规则覆盖；
- 热加载规则；
- 租户级规则覆盖；
- 运行时动态编辑规则。

`rules.yaml` 必须包含 `ruleset_version`。每个 `ReviewResult` 和审计日志都应记录：

- `skill_name`
- `skill_version`
- `ruleset_version`

LLM 不能做最终规则决策。最终风险等级必须由确定性规则结果汇总得到。
