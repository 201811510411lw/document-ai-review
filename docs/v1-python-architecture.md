# V1 Python Architecture

本文档说明 `document-ai-review` 在 V1 阶段采用的纯 Python 架构。当前 `main` 已经完成第一轮 runtime 收口，主线语义为：

- Agent Skills 描述层
- runtime use_cases
- runtime capabilities

---

## 1. V1 总体链路

V1 不引入 Java / Spring Boot，不拆分为多服务。当前只有一个 Python 服务：`ai-service`。

```text
业务系统 / 管理后台 / 测试脚本
    ↓
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
capabilities + tools + rules
    ↓
ReviewResult
    ↓
Repository
```

当前内置 use_case：

- `food_license`
- `qc_document_review`
- `tobacco_license_consistency_review`
- `contract_review`

其中 `food_license` 是当前唯一较完整的兼容样板。

---

## 2. 职责边界

### 2.1 FastAPI

FastAPI 是 HTTP 边界，负责：

- 健康检查；
- 接收审核请求；
- 基础校验；
- 把请求转交给 Review Service。

FastAPI 不直接承载规则执行，也不直接调用 workflow 或 capability 节点。

### 2.2 Review Service

Review Service 负责：

- 创建审核任务 ID；
- 构造 `ReviewInputContext`；
- 调用 `use_case_registry` 获取或选择 use_case；
- 调用 `use_case.review(input_context)`；
- 接收并返回 `ReviewResult`。

### 2.3 use_case_registry

`use_case_registry` 位于：

```text
ai-service/app/use_cases/registry.py
```

职责：

- 显式注册多个内置 use_case；
- 提供 `get(use_case_name)`；
- 提供 `list()`；
- 根据 `supports(input_context)` 选择 use_case。

当前不做：

- 目录扫描；
- 外部 use_case 加载；
- 插件市场；
- 热加载；
- 租户级覆盖。

### 2.4 Agent Skill 描述层

Agent Skill 描述层位于：

```text
.agents/skills/<skill>/SKILL.md
```

它只描述：

- 能力边界；
- 输入输出摘要；
- 规则摘要；
- 人工复核边界；
- 与 runtime 的关系。

它不是规则引擎，也不是 runtime 入口。

### 2.5 runtime use_case

runtime use_case 位于：

```text
ai-service/app/use_cases/
```

职责：

- 作为平台业务入口；
- 调用 workflow；
- 将 workflow 结果映射为平台 `ReviewResult`。

### 2.6 runtime capability

runtime capability 位于：

```text
ai-service/app/capabilities/
```

职责：

- 定义 capability 自身 schema；
- 组织提示词；
- 承接字段抽取逻辑；
- 挂载 capability 自身规则；
- 构造 capability 结果 payload。

当前首个 capability 样板是：

```text
ai-service/app/capabilities/food_license/
```

### 2.7 workflow

`app/workflows/` 是 LangGraph 编排层，负责：

- 文档加载；
- 字段抽取；
- 字段规范化；
- 规则执行；
- 风险汇总；
- 人工复核路由。

workflow 负责编排，不承接平台入口职责。

### 2.8 tools / adapter

`app/tools/` 封装外部能力 Stub，包括：

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

### 2.9 rules

通用规则基础设施位于：

```text
ai-service/app/rules/
```

具体业务规则位于：

```text
ai-service/app/capabilities/<capability>/rules/
```

`SKILL.md` 只描述规则摘要，不承载规则执行逻辑。

### 2.10 Repository

Repository 层负责数据访问。当前已具备审核结果持久化基础，后续人工复核和审计日志应继续沿用平台级结构。

---

## 3. 推荐目录结构

```text
ai-service/
└── app/
    ├── api/
    ├── capabilities/
    ├── core/
    ├── models/
    ├── repositories/
    ├── rules/
    ├── services/
    ├── tools/
    ├── use_cases/
    └── workflows/
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

执行链路：

```text
FastAPI
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

这条兼容链路必须继续保留。

---

## 5. 当前结果模型语义

当前 `ReviewResult` 已新增：

- `use_case_name`
- `use_case_version`
- `capability_names`

同时继续保留：

- `skill_name`
- `skill_version`
- `skill_result`

当前约定：

- `use_case_*` 是主入口字段；
- `capability_names` 表示执行能力；
- `skill_*` 和 `skill_result` 仍是兼容字段。

---

## 6. 当前 V1 已具备能力

当前代码已经具备：

- FastAPI 服务骨架；
- ReviewService 审核入口；
- `use_case_registry` 显式注册骨架；
- `food_license` Python use_case facade；
- `food_license` runtime capability 样板；
- `food_license` LangGraph 工作流；
- `ReviewResult` 平台级返回契约；
- `skill_result` 承载 capability 专属 payload 的兼容边界；
- 食品安全证照 OCR 文本、本地 PDF、文件输入边界的测试闭环。

---

## 7. 当前不做事项

本轮不做：

- 完整 QC 证照及批次报告规则；
- 完整营业执照与烟草证一致性规则；
- 完整法务合同风险条款规则；
- 真实 OCR 接入；
- 真实 LLM 接入；
- 真实 ERP / OA / 飞书 / 企微调用；
- 规则热加载或租户级规则覆盖；
- 删除 `food_license` 兼容入口。
