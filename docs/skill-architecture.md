# Document AI Review Skill 架构边界

本文档明确 `document-ai-review` 的多场景 Skill 架构边界。`README.md` 仍然是项目唯一主上下文；本文档细化 Agent Skill 描述层、Python Runtime、workflow、rules、tools 和平台入口之间的关系。

---

## 1. Skill 分层定义

Skill 是平台中的一等业务能力对象，但不同层的 Skill 职责不同，不能混为一个文件或一个类。

| 层级 | 位置 | 职责 |
| --- | --- | --- |
| Agent Skill 描述层 | `.agents/skills/<skill>/SKILL.md` | 描述能力边界、输入输出、规则摘要、提示边界和人工复核边界 |
| Python Skill Runtime facade | `ai-service/app/skills/<skill>/skill.py` | 实现平台可调用的 `Skill.review(input_context)` 入口 |
| Workflow Runtime | `ai-service/app/workflows/<domain>/` | 编排 LangGraph、LangChain、OCR、LLM、规则执行和人工复核路由 |
| Business Rule 规则层 | `ai-service/app/rules/` 和 `ai-service/app/skills/<skill>/rules/` | 执行确定性、可测试的业务规则 |
| Tool / Adapter 层 | `ai-service/app/tools/` | 封装 OCR、LLM、PDF、图片、ERP、OA、IM 等外部能力 |
| API / Service 平台层 | `ai-service/app/api/`、`ai-service/app/services/`、`ai-service/app/skills/registry.py` | 解析请求、选择 Skill、执行统一 review 入口并返回平台结果 |

`Skill.md` 可以描述规则摘要，但不能承载规则执行逻辑。具体业务规则必须保留在 rules 目录，并通过测试验证。

---

## 2. 平台调用契约

平台只调用稳定的 Skill 级接口：

```text
name
version
ruleset_version
supported_document_types
supports(input_context)
review(input_context) -> ReviewResult
```

平台不得直接调用 Skill 内部节点或步骤，例如：

- `load_document`
- `extract_fields`
- `run_rules`
- `summarize_risk`
- `route_review`

这些名称可以作为 Skill 内部 workflow 节点或函数存在，但不是平台公共接口。

统一执行链路：

```text
FastAPI HTTP API
    ↓
Review Service
    ↓
Skill Registry
    ↓
Skill.review(input_context)
    ↓
Workflow Runtime
    ↓
Rules / Tools
    ↓
ReviewResult
```

快捷入口和通用入口都必须复用这条链路，不能维护两套审核逻辑。

---

## 3. 多场景 Skill

目标产品至少包含三个主线场景：

| Skill | 场景 | 状态 |
| --- | --- | --- |
| `qc_document_review` | QC 证照及批次报告审核 | 本轮创建 Agent Skill 描述和 Runtime 占位 |
| `tobacco_license_consistency_review` | 营业执照与烟草证一致性校验 | 本轮创建 Agent Skill 描述和 Runtime 占位 |
| `contract_review` | 法务合同内容审核 | 本轮创建 Agent Skill 描述和 Runtime 占位 |
| `food_license` | 食品安全证照检测 V1 骨架 | 历史兼容 Skill，短期保留 |

`food_license` 是历史 V1 骨架。后续可以演进为 `qc_document_review` 的子能力，或作为兼容 Skill 保留快捷入口。迁移必须分 Issue 进行，不能在多 Skill 架构骨架中直接删除。

---

## 4. Registry 边界

V1 Skill Registry 继续采用显式注册内置 Skill。

V1 不做：

- 目录扫描。
- 外部 Skill 加载。
- 插件市场。
- 热加载。
- 租户级 Skill 覆盖。
- 运行时动态启停 Skill。

Registry 负责：

- 注册多个内置 Skill。
- 提供 `get(skill_name)` 和 `list()`。
- 根据 `supports(input_context)` 选择 Skill。
- 将请求路由到 `Skill.review(input_context)`。
- 在结果和审计日志中保留 Skill 身份信息。

Registry 不执行业务规则，不调用 workflow 节点，也不直接访问 OCR、LLM、ERP、OA 或 IM Adapter。

---

## 5. 目录边界

推荐多场景结构：

```text
ai-service/
└── app/
    ├── api/
    ├── core/
    ├── models/
    ├── repositories/
    ├── services/
    │   └── review_service.py
    ├── rules/
    │   ├── engine.py
    │   ├── protocol.py
    │   └── result.py
    ├── tools/
    │   ├── ocr_adapter.py
    │   ├── llm_adapter.py
    │   ├── document_loader.py
    │   ├── file_adapter.py
    │   ├── pdf_adapter.py
    │   ├── image_adapter.py
    │   ├── erp_adapter.py
    │   ├── oa_adapter.py
    │   └── im_adapter.py
    ├── workflows/
    │   ├── food_license/
    │   ├── qc_document/
    │   ├── tobacco_license/
    │   └── contract/
    └── skills/
        ├── base.py
        ├── registry.py
        ├── food_license/
        ├── qc_document_review/
        ├── tobacco_license_consistency_review/
        └── contract_review/
```

`app/rules/` 只放通用规则基础设施。具体业务规则放在对应 Skill 包内，例如：

- `app/skills/food_license/rules/`
- `app/skills/qc_document_review/rules/`
- `app/skills/tobacco_license_consistency_review/rules/`
- `app/skills/contract_review/rules/`

本轮只建立骨架，不实现完整业务规则。

---

## 6. ReviewResult 边界

`ReviewResult` 是平台级返回契约，必须保留稳定的跨 Skill 字段：

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

`skill_result` 用于承载 Skill 专属 payload。平台字段不能被某个业务场景的专属字段污染。

---

## 7. Agent Skill 描述层

`.agents/skills/<skill>/SKILL.md` 只描述：

- Skill 名称。
- 能力边界。
- 支持的输入。
- 输出结构摘要。
- 规则摘要。
- 人工复核边界。
- 禁止事项。
- 与 Python Runtime 的关系。

`SKILL.md` 不做：

- 不写 `if/else` 规则执行逻辑。
- 不保存真实模型配置。
- 不引用公有云 API 作为必需依赖。
- 不绕过 ReviewService 或 SkillRegistry。
- 不直接调用 workflow 节点。

---

## 8. Tools / Adapter 边界

`app/tools/` 封装外部能力，当前只提供 Stub。

Adapter 可以表示：

- OCR。
- LLM。
- 文档加载。
- 文件读取。
- PDF 解析。
- 图片解析。
- ERP 查询或回写。
- OA 回写。
- IM 通知。

Adapter Stub 必须可以本地测试，不依赖外部服务。真实接入必须后续单独 Issue 完成。

---

## 9. 规则约束

确定性业务规则必须位于 rules 目录并可测试。LLM 可以辅助字段抽取、摘要和修改建议，但不能直接替代最终规则判定。

V1 不做：

- 数据库规则管理。
- 外部规则覆盖。
- 热加载规则。
- 租户级规则覆盖。
- 运行时动态编辑规则。
