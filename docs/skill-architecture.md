# Document AI Review Runtime 架构边界

本文档基于 `main` 最新代码，明确 `document-ai-review` 当前主线的三层边界：Agent Skill 描述层、runtime use_case、runtime capability。

`README.md` 是项目唯一主上下文；本文档只细化运行时职责和命名边界。

---

## 1. 三层对象

当前主线不能再把所有运行时对象都叫做 Skill，而必须区分三层：

| 层级 | 位置 | 职责 |
| --- | --- | --- |
| Agent Skill 描述层 | `.agents/skills/<skill>/SKILL.md` | 描述能力边界、输入输出、规则摘要、提示边界和人工复核边界 |
| runtime use_case | `ai-service/app/use_cases/<use_case>/` | 承接平台入口，负责选择 workflow 并组装 `ReviewResult` |
| runtime capability | `ai-service/app/capabilities/<capability>/` | 承接字段 schema、提示边界、规则归属、能力结果构造等可复用执行能力 |

这三层的区别：

- Agent Skill 面向“怎么描述一种审核能力”；
- use_case 面向“平台从哪里进入一个业务场景”；
- capability 面向“workflow 里面真正复用哪些执行能力”。

---

## 2. 平台调用契约

平台当前只调用稳定的 use_case 级契约：

```text
name
version
ruleset_version
supported_document_types
supports(input_context)
review(input_context) -> ReviewResult
```

统一执行链路：

```text
FastAPI HTTP API
    ↓
Review Service
    ↓
use_case_registry
    ↓
use_case.review(input_context)
    ↓
workflow
    ↓
capabilities
    ↓
rules / tools
    ↓
ReviewResult
```

平台层不得直接调用内部节点，例如：

- `load_document`
- `extract_fields`
- `run_rules`
- `summarize_risk`
- `route_review`

这些名称可以在 workflow 内部存在，但不是平台公共接口。

---

## 3. use_case 边界

路径：

```text
ai-service/app/use_cases/
```

当前内置 use_case：

- `food_license`
- `qc_document_review`
- `tobacco_license_consistency_review`
- `contract_review`

职责：

- 对外暴露 runtime 业务入口；
- 声明支持的文档类型；
- 接收 `ReviewInputContext`；
- 调用 workflow；
- 将 workflow 结果映射为平台级 `ReviewResult`。

当前主线中：

- `food_license` 是历史 V1 兼容 use_case；
- 其他三个 use_case 当前仍以占位实现为主。

---

## 4. capability 边界

路径：

```text
ai-service/app/capabilities/
```

当前首个 capability 样板：

```text
ai-service/app/capabilities/food_license/
```

当前结构：

```text
food_license/
├── __init__.py
├── prompt.py
├── schemas.py
├── executor.py
├── extractor.py
└── rules/
```

职责：

- 定义 capability 自身 schema；
- 组织提示边界；
- 组织字段抽取逻辑；
- 挂载 capability 专属规则；
- 构造 capability 结果。

capability 不直接充当平台入口，也不替代 workflow。

---

## 5. workflow 边界

路径：

```text
ai-service/app/workflows/<domain>/
```

职责：

- 编排 LangGraph 主流程；
- 组织文档加载、字段抽取、规则执行、风险汇总和人工复核路由；
- 调用 capability 与 tools adapter；
- 不承载平台入口职责。

当前 `food_license` workflow 已经与 capability 分离：

- workflow 负责编排；
- capability 负责能力结果和规则归属。

---

## 6. rules 与 tools 边界

通用规则基础设施：

```text
ai-service/app/rules/
```

具体业务规则：

```text
ai-service/app/capabilities/<capability>/rules/
```

当前约定：

- `app/rules/` 只放通用规则协议、上下文、执行器、聚合逻辑；
- capability 自带自己的 `rules/`；
- Agent Skill 只描述规则摘要；
- workflow 不内嵌业务规则实现。

`app/tools/` 只封装外部能力 Stub：

- OCR
- LLM
- 文档加载
- 文件读取
- PDF 解析
- 图片解析
- ERP
- OA
- IM

当前主线不接真实外部服务。

---

## 7. ReviewResult 边界

当前 `ReviewResult` 同时包含主线字段和兼容字段：

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

当前解释：

- `use_case_name` / `use_case_version`：当前主入口字段；
- `capability_names`：执行中用到的 capability；
- `skill_name` / `skill_version`：兼容字段；
- `skill_result`：兼容容器，当前承载 capability 专属 payload。

因此文档和新代码应优先使用：

- `use_case_*`
- `capability_names`

而不是继续把 `skill_*` 当作主字段语义。

---

## 8. Agent Skill 描述层边界

`.agents/skills/<skill>/SKILL.md` 只描述：

- 能力边界；
- 支持的输入；
- 输出结构摘要；
- 规则摘要；
- 人工复核边界；
- 与 runtime use_case / capability 的关系。

不做：

- 不写规则执行逻辑；
- 不写 workflow 编排逻辑；
- 不绕过 ReviewService 或 `use_case_registry`；
- 不直接调用 OCR / LLM / OA / ERP；
- 不直接充当 runtime 入口。

---

## 9. 当前主线约束

当前收口阶段不做：

- 不重新把 runtime 入口命名回 `app/skills`；
- 不引入 Java / Spring Boot；
- 不接真实 OCR / LLM / OA / ERP；
- 不删除 `food_license` 兼容入口；
- 不继续扩展 `food_license` 规则；
- 不把 capability 上升为平台入口。
