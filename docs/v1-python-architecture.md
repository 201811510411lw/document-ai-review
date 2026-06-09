# V1 Python Architecture

本文档说明 `document-ai-review` 在 V1 阶段采用的纯 Python 架构。V1 从食品安全证照检测骨架起步，但目标架构是私有化智能审核平台的多场景 Skill Runtime。

`README.md` 仍然是项目唯一主上下文；本文档只承载更细的 V1 架构设计，不替代 README。

---

## 1. 纯 Python V1 架构说明

V1 不引入 Java / Spring Boot，不拆分为 `backend-java` + `ai-service` 两个服务。当前只建设一个 Python 服务：`ai-service`。

```text
业务系统 / 管理后台 / 测试脚本
    ↓
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
Tools / Adapter + Python 规则引擎
    ↓
ReviewResult
    ↓
Repository
```

当前代码中的 `food_license` 是历史 V1 骨架，负责食品安全证照检测最小闭环。后续多场景主线包括：

- `qc_document_review`：QC 证照及批次报告审核。
- `tobacco_license_consistency_review`：营业执照与烟草证一致性校验。
- `contract_review`：法务合同内容审核。

本轮只建立架构骨架和 Stub，不实现完整 QC、烟草证或合同审核规则。

---

## 2. 职责边界

### 2.1 FastAPI

FastAPI 是 HTTP API 边界，负责：

- 健康检查。
- 接收审核请求。
- 解析请求和基础校验。
- 将请求转交给 Service 层。

FastAPI 不直接承载审核规则、模型调用或 workflow 节点调用。

### 2.2 Review Service

Review Service 是审核用例入口，负责：

- 创建审核任务 ID。
- 构造 `ReviewInputContext`。
- 调用 Skill Registry 获取或选择 Skill。
- 调用 `Skill.review(input_context)`。
- 接收 `ReviewResult`。

Review Service 不直接调用 `load_document`、`extract_fields`、`run_rules`、`summarize_risk`、`route_review` 等内部节点。

### 2.3 Skill Registry

Skill Registry 属于 Skill 平台层，位置为 `app/skills/registry.py`。

Registry 负责：

- 显式注册多个内置 Skill。
- 提供 `get(skill_name)`。
- 提供 `list()`。
- 根据 `supports(input_context)` 选择 Skill。

V1 Registry 不做目录扫描、外部 Skill 加载、插件市场、热加载或租户级覆盖。

### 2.4 Agent Skill 描述层

Agent Skill 描述层位于：

```text
.agents/skills/<skill>/SKILL.md
```

它只描述能力边界、输入输出、规则摘要、提示边界和人工复核边界。它不是规则引擎，不保存真实模型配置，也不直接执行 Python workflow。

### 2.5 Python Skill Runtime facade

Python Skill class 是平台运行时 facade，负责实现：

```text
name
version
ruleset_version
supported_document_types
supports(input_context)
review(input_context) -> ReviewResult
```

Skill facade 可以调用对应 workflow，但不应长期承载复杂规则、OCR、LLM 或外部系统接入逻辑。

### 2.6 Workflow Runtime

`app/workflows/` 是 LangGraph / LangChain / OCR / LLM 编排层。它负责将文档加载、字段抽取、字段规范化、规则执行、风险汇总和人工复核路由组合为审核流程。

当前新增目录：

```text
app/workflows/food_license/
app/workflows/qc_document/
app/workflows/tobacco_license/
app/workflows/contract/
```

`food_license` workflow runtime 位于 `app/workflows/food_license/`。历史
`app/skills/food_license/graph.py`、`nodes.py` 和 `state.py` 仅保留兼容导入。

### 2.7 Tools / Adapter

`app/tools/` 封装外部系统和模型能力，包括：

- OCR。
- LLM。
- 文档加载。
- 文件读取。
- PDF 解析。
- 图片解析。
- ERP。
- OA。
- IM 通知。

本轮只提供 Stub，不能接真实 OCR、LLM、ERP、OA、飞书或企微。

### 2.8 Python 规则引擎

Python 规则引擎负责确定性、可解释、可测试的业务规则。

`app/rules/` 放通用规则基础设施，包括规则协议、规则上下文、规则执行状态、执行器、风险聚合和平台 `RuleResult` 映射。具体业务规则放在对应 Skill 包内的 `rules/` 目录。`Skill.md` 可以描述规则摘要，但不能承载规则执行逻辑。

### 2.9 Repository

Repository 层负责数据访问。当前多 Skill 骨架不强制引入数据库实现。后续保存审核任务、审核结果、规则结果、人工复核记录和审计日志时，应保持跨 Skill 的平台结构。

---

## 3. 推荐目录结构

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
    ├── tools/
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

Agent Skill 描述层独立位于：

```text
.agents/skills/
├── qc_document_review/SKILL.md
├── tobacco_license_consistency_review/SKILL.md
└── contract_review/SKILL.md
```

---

## 4. 当前兼容链路

食品安全证照快捷入口继续保留：

```text
POST /api/v1/food-license/reviews
```

实现上仍必须走：

```text
FastAPI
    ↓
ReviewService.review_food_license()
    ↓
ReviewService.review(skill_name="food_license")
    ↓
SkillRegistry.get("food_license")
    ↓
food_license.review(input_context)
```

这保证现有测试和调用方不被破坏，同时为后续通用入口 `ReviewService.review()` 和 `POST /api/v1/reviews` 保留扩展空间。

---

## 5. V1 本轮不做事项

本轮暂不实现：

- 完整 QC 证照及批次报告规则。
- 完整营业执照与烟草证一致性规则。
- 完整法务合同风险条款规则。
- 真实 OCR 接入。
- 真实 LLM 接入。
- 真实 ERP、OA、飞书或企微调用。
- 数据库规则配置。
- 合并 PR #15。

PR #15 只作为只读技术验证参考。后续可以按 Issue 拆分迁移其中的字段抽取、文件输入、规则和持久化思路。

当前尚未创建 `docs/adr/`。建议后续新增 ADR，记录 Skill、workflow、rules 和 Adapter 的长期边界：确定性规则不写入 workflow 或 `SKILL.md`，workflow 只负责编排，LLM 通过 Adapter 接入且不直接决定最终规则判定。
