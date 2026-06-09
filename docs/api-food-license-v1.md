# 食品安全证照检测 V1 API 契约

本文档定义食品安全证照检测 V1 的 FastAPI HTTP API 契约，供后续 `ai-service` 实现、测试脚本和外部系统集成使用。

`README.md` 是项目唯一主上下文；`docs/prd-food-license-v1.md` 是本文档的产品依据。本文档只描述 API 契约，不实现业务代码。

---

## 1. 设计目标

食品安全证照检测 V1 采用纯 Python 架构，当前只有一个 Python 服务：`ai-service`。

API 契约目标：

- 优先支持 OCR 文本输入跑通食品安全证照审核闭环；
- 为 FastAPI 创建审核任务、查询审核结果和人工复核提供稳定 HTTP 边界；
- 明确请求字段、响应字段、错误语义和状态流转；
- 明确 FastAPI、Review Service、Skill Registry、Skill、LangGraph、LangChain、Python 规则引擎和 SQLite / MySQL 的职责边界；
- 明确 `/api/v1/food-license/reviews` 是 `food_license` Skill 快捷入口，后续 `/api/v1/reviews` 是平台通用入口；
- 为后续文件上传、图片解析和 PDF 解析保留接口扩展空间，但不把它们列为第一阶段必实现能力。

## 2. 职责边界

| 模块 | API 契约中的职责 |
| --- | --- |
| FastAPI | 暴露 HTTP API，完成请求解析、基础校验、响应封装和错误映射 |
| Review Service | 创建审核任务，构造 `input_context`，调用 Skill Registry，协调结果保存和人工复核动作 |
| Skill Registry | 显式注册内置 Skill，加载 `metadata.yaml`，路由到 `Skill.review(input_context)` |
| Skill | 运行时一等业务对象，封装配置、Prompt、规则、模型、工作流和 Skill 文档 |
| LangGraph | 在 `food_license` Skill 内部编排核心流程和节点状态流转 |
| LangChain | 在 Skill 内部负责模型调用、Prompt、结构化输出和工具封装 |
| LLM | 只用于字段抽取、结构化输出和摘要建议，不直接做最终规则判定 |
| Python 规则引擎 | 执行确定性规则校验，并基于规则结果汇总最终风险等级 |
| SQLite / MySQL | 保存审核任务、审核结果、规则结果、人工复核记录和审计日志 |

平台只调用 `Skill.review(input_context) -> ReviewResult`。API 层不得直接实现食品安全证照规则判断，也不得直接调用 `extract_fields`、`run_rules`、`summarize_risk` 或 `route_review` 等 Skill 内部节点。最终风险等级不得由 LLM 直接给出，必须由 Python 规则引擎结果汇总得到。

## 3. 通用约定

### 3.1 Base URL

本地开发默认：

```text
http://localhost:8000
```

所有 V1 食品安全证照接口建议使用统一前缀：

```text
/api/v1/food-license
```

`/api/v1/food-license/reviews` 是 `food_license` Skill 的快捷入口。后续平台通用入口为：

```text
/api/v1/reviews
```

快捷入口和通用入口都必须经过 Review Service + Skill Registry，不能维护两套审核逻辑。

### 3.2 Content Type

第一阶段 OCR 文本输入接口使用 JSON：

```http
Content-Type: application/json
Accept: application/json
```

后续文件上传接口可以使用 `multipart/form-data`，但不属于第一阶段必实现范围。

### 3.3 时间格式

API 中的日期和时间使用：

- 日期：`YYYY-MM-DD`
- 时间戳：ISO 8601，例如 `2026-06-08T14:30:00+08:00`

### 3.4 枚举值

#### 任务状态

| 值 | 说明 |
| --- | --- |
| `CREATED` | 审核任务已创建 |
| `RUNNING` | 审核工作流执行中 |
| `REVIEWED` | 自动审核已完成 |
| `PENDING_MANUAL_REVIEW` | 等待人工复核 |
| `MANUAL_REVIEWED` | 人工复核已完成 |
| `FAILED` | 审核任务执行失败 |

#### 证照类型

| 值 | 说明 |
| --- | --- |
| `food_license` | 食品安全相关证照 |
| `unknown` | 无法识别或暂不支持的材料 |

#### 风险等级

| 值 | 说明 |
| --- | --- |
| `HIGH` | 高风险 |
| `MEDIUM` | 中风险 |
| `LOW` | 低风险 |
| `NONE` | 无明显风险 |

#### 人工复核动作

| 值 | 说明 |
| --- | --- |
| `APPROVE` | 人工通过 |
| `REJECT` | 人工驳回 |
| `REQUEST_MORE_INFO` | 要求补充材料或信息 |

#### 人工复核状态

| 值 | 说明 |
| --- | --- |
| `NOT_REQUIRED` | 不需要人工复核 |
| `PENDING` | 等待人工复核 |
| `COMPLETED` | 人工复核已完成 |

## 4. 通用响应结构

成功响应直接返回业务对象。

错误响应统一结构：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不合法",
    "details": [
      {
        "field": "ocr_text",
        "message": "ocr_text 不能为空"
      }
    ],
    "request_id": "req-20260608-000001"
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `error.code` | 稳定错误编码 |
| `error.message` | 面向调用方的错误说明 |
| `error.details` | 字段级或上下文级错误详情 |
| `error.request_id` | 请求追踪 ID |

## 5. 接口清单

| 方法 | 路径 | 说明 | 第一阶段优先级 |
| --- | --- | --- | --- |
| `GET` | `/health` | 健康检查 | 必须 |
| `POST` | `/api/v1/food-license/reviews` | 基于 OCR 文本创建审核任务 | 必须 |
| `GET` | `/api/v1/food-license/reviews/{task_id}` | 查询审核任务和审核结果 | 必须 |
| `POST` | `/api/v1/food-license/reviews/{task_id}/manual-review` | 提交人工复核动作 | 必须 |
| `POST` | `/api/v1/food-license/reviews:upload` | 上传图片或 PDF 创建审核任务 | 保留设计，低优先级 |
| `POST` | `/api/v1/reviews` | 平台通用审核入口 | 后续扩展 |

## 6. 健康检查

### 6.1 `GET /health`

用于确认 `ai-service` 是否可用。

#### 响应示例

```json
{
  "status": "ok",
  "service": "ai-service",
  "version": "v1",
  "timestamp": "2026-06-08T14:30:00+08:00"
}
```

#### 验收要求

- 返回 HTTP `200` 表示服务进程可响应；
- 不要求检查模型、数据库或外部依赖的生产级健康状态；
- 不暴露敏感配置、模型密钥或数据库连接信息。

## 7. 创建审核任务

### 7.1 `POST /api/v1/food-license/reviews`

基于 OCR 文本创建食品安全证照审核任务。当前 V1 继续优先支持 `ocr_text`，用于跑通可验证闭环。

同一 JSON 入口也保留文件输入边界：调用方可以传入 PDF / 图片文件元信息和测试用 stub OCR 文本，用于验证 `food_license` Skill 内部 document loader / OCR adapter 边界。该边界不代表生产级图片/PDF OCR 已完成。

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ocr_text` | string | 否 | 食品安全证照 OCR 文本；当前 V1 推荐输入方式 |
| `file.filename` | string | 否 | PDF / 图片文件名；用于 V1 下一阶段文件输入边界 |
| `file.content_type` | string | 否 | `application/pdf`、`image/png`、`image/jpeg` 等 |
| `file.content_base64` | string | 否 | 文件内容 base64；当前仅作为接口边界或测试 fixture，不做生产级文件存储 |
| `supplier.name` | string | 是 | 业务系统中的供应商名称 |
| `supplier.credit_code` | string | 是 | 业务系统中的统一社会信用代码 |
| `supplier.address` | string | 否 | 业务系统中的供应商经营地址 |
| `declared_document_type` | string | 否 | 调用方声明的证照类型，例如 `food_license` |
| `source` | object | 否 | 输入来源元信息 |
| `options` | object | 否 | 审核选项；测试中可包含 `stub_ocr_text` 以驱动 fake OCR |

`ocr_text` 和 `file` 至少提供一个。若同时提供，Skill 内部 document loader 优先使用 `ocr_text`。

#### 请求示例

```json
{
  "ocr_text": "食品经营许可证\\n经营者名称：成都示例食品有限公司\\n统一社会信用代码：91510100MA00000000\\n许可证编号：JY15101000000000\\n经营项目：预包装食品销售、散装食品销售\\n有效期至：2028-01-01",
  "supplier": {
    "name": "成都示例食品有限公司",
    "credit_code": "91510100MA00000000",
    "address": "成都市示例区示例路 100 号"
  },
  "declared_document_type": "food_license",
  "source": {
    "input_type": "ocr_text",
    "external_reference_id": "supplier-doc-001"
  },
  "options": {
    "sync": true
  }
}
```

#### 文件输入边界示例

```json
{
  "file": {
    "filename": "food-license.pdf",
    "content_type": "application/pdf",
    "content_base64": "..."
  },
  "supplier": {
    "name": "成都示例食品有限公司",
    "credit_code": "91510100MA00000000"
  },
  "declared_document_type": "food_license",
  "source": {
    "input_type": "pdf",
    "external_reference_id": "supplier-doc-002"
  },
  "options": {
    "stub_ocr_text": "食品经营许可证\\n经营者名称：成都示例食品有限公司\\n统一社会信用代码：91510100MA00000000\\n许可证编号：JY15101000000000"
  }
}
```

文件输入必须继续走 `FastAPI -> Review Service -> Skill Registry -> food_license.review(input_context)`。FastAPI 不直接调用 OCR、LangChain、LangGraph 节点、LLM 或 Skill 内部规则。OCR / document loader adapter 位于 `app/skills/food_license/` 内部，当前只提供 stub / fake OCR 边界用于测试。

### 7.2 字段抽取链路与 LLM 配置

当前 `food_license` Skill 内部字段抽取链路为：

```text
PDF / 图片
-> food_license OCR adapter
-> OCR text
-> regex extraction
-> optional LangChain LLM supplement for missing fields
-> normalize_fields
-> deterministic rules
```

`extract_fields` 节点先执行确定性正则抽取，输出模型为 `FoodLicenseExtractedFields`。如果关键字段已完整，不调用 LLM。只有关键字段缺失，且 `FOOD_LICENSE_LLM_ENABLED=true` 时，才尝试 LangChain LLM 结构化抽取。LLM 结果只能补充正则缺失字段，不覆盖已由正则稳定抽出的关键字段。LLM 未配置 API Key、调用失败或输出解析失败时，不应导致审核接口失败，主流程继续使用正则结果。

真实 LLM 只在环境变量启用并配置完整时运行：

| 环境变量 | 说明 |
| --- | --- |
| `FOOD_LICENSE_LLM_ENABLED` | `true` 时允许尝试真实 LLM；默认 `false` |
| `FOOD_LICENSE_LLM_PROVIDER` | `openai` 或 `compatible` |
| `FOOD_LICENSE_LLM_MODEL` | 模型名称 |
| `FOOD_LICENSE_LLM_BASE_URL` | OpenAI-compatible 服务地址；OpenAI 官方默认可不填 |
| `FOOD_LICENSE_LLM_API_KEY` | API Key，禁止写死在代码或测试中 |

测试默认不调用真实 LLM，不依赖 API Key 或网络。测试可以使用 LangChain fake LLM 或自定义 Runnable 验证结构化抽取边界。

抽取方式只能作为 Skill 专属 payload 放入 `skill_result.extraction_metadata`，不得提升到 `ReviewResult` 顶层。`extraction_mode` 当前取值为 `regex_only`、`regex_with_llm_supplement` 或 `regex_fallback_after_llm_failed`。

#### 响应字段

| 字段 | 说明 |
| --- | --- |
| `task_id` | 审核任务 ID |
| `status` | 审核任务状态 |
| `document_type` | 证照类型识别结果 |
| `skill_name` | 执行本次审核的 Skill 名称，例如 `food_license` |
| `skill_version` | 执行本次审核的 Skill 版本 |
| `ruleset_version` | 执行本次审核的规则集版本 |
| `risk_level` | 最终风险等级 |
| `needs_manual_review` | 是否需要人工复核 |
| `rule_results` | Python 规则引擎输出的规则结果；其中 `risk_level_on_failure` 表示该规则未通过时产生的风险等级 |
| `manual_review` | 人工复核状态、原因和后续人工动作信息 |
| `summary` | 摘要建议，可由规则结果和 LLM 辅助生成 |
| `skill_result` | Skill 专属 payload，例如食品安全证照的抽取字段和规范化字段 |
| `created_at` | 任务创建时间 |
| `updated_at` | 任务更新时间 |

#### 同步完成响应示例

```json
{
  "task_id": "review-task-001",
  "status": "REVIEWED",
  "document_type": "food_license",
  "skill_name": "food_license",
  "skill_version": "v1",
  "ruleset_version": "food-license-rules-v1",
  "risk_level": "NONE",
  "needs_manual_review": false,
  "rule_results": [
    {
      "rule_code": "FOOD_LICENSE_EXISTS",
      "rule_name": "证照是否存在",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "已检测到可审核的 OCR 文本"
    },
    {
      "rule_code": "CREDIT_CODE_MATCH",
      "rule_name": "统一社会信用代码是否一致",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "证照信用代码与供应商信用代码一致"
    }
  ],
  "manual_review": {
    "status": "NOT_REQUIRED",
    "reasons": [],
    "reviewer": null,
    "action": null,
    "comment": null,
    "reviewed_at": null
  },
  "summary": "未发现明显风险，可自动通过。",
  "skill_result": {
    "extracted_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "business_address": "成都市示例区示例路 100 号",
      "legal_person": null,
      "business_items": ["预包装食品销售", "散装食品销售"],
      "valid_from": null,
      "valid_to": "2028-01-01",
      "issue_authority": null,
      "issue_date": null
    },
    "normalized_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "business_address": "成都市示例区示例路100号",
      "legal_person": null,
      "business_items": ["预包装食品销售", "散装食品销售"],
      "valid_from": null,
      "valid_to": "2028-01-01",
      "issue_authority": null,
      "issue_date": null
    }
  },
  "created_at": "2026-06-08T14:30:00+08:00",
  "updated_at": "2026-06-08T14:30:03+08:00"
}
```

#### 等待人工复核响应示例

```json
{
  "task_id": "review-task-002",
  "status": "PENDING_MANUAL_REVIEW",
  "document_type": "food_license",
  "skill_name": "food_license",
  "skill_version": "v1",
  "ruleset_version": "food-license-rules-v1",
  "risk_level": "HIGH",
  "needs_manual_review": true,
  "rule_results": [
    {
      "rule_code": "FOOD_LICENSE_EXPIRED",
      "rule_name": "证照是否过期",
      "passed": false,
      "risk_level_on_failure": "HIGH",
      "message": "当前日期超过证照有效期截止日期"
    }
  ],
  "manual_review": {
    "status": "PENDING",
    "reasons": ["证照已过期"],
    "reviewer": null,
    "action": null,
    "comment": null,
    "reviewed_at": null
  },
  "summary": "发现高风险问题，建议人工复核证照有效期。",
  "skill_result": {
    "extracted_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "business_items": ["预包装食品销售"],
      "valid_to": "2025-01-01"
    },
    "normalized_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "business_items": ["预包装食品销售"],
      "valid_to": "2025-01-01"
    }
  },
  "created_at": "2026-06-08T14:30:00+08:00",
  "updated_at": "2026-06-08T14:30:03+08:00"
}
```

#### 处理语义

- FastAPI 完成 JSON 解析和基础字段校验；
- Review Service 创建审核任务并记录任务初始状态；
- Review Service 调用 Skill Registry；
- Skill Registry 路由到 `food_license` Skill；
- `food_license.review(input_context)` 执行 Skill 内部 LangGraph 工作流；
- LangChain / LLM 在 Skill 内部负责字段抽取、结构化输出和摘要建议；
- Python 规则引擎负责规则判断，具体食品安全证照规则来自 `food_license` Skill 内部 `rules.yaml`；
- 最终风险等级由 Python 规则引擎结果汇总得到；
- SQLite / MySQL 保存任务、结果、规则结果、人工复核状态和审计日志。

## 8. 查询审核任务和结果

### 8.1 `GET /api/v1/food-license/reviews/{task_id}`

用于查询审核任务状态、审核结果、规则结果和人工复核状态。

#### 路径参数

| 参数 | 说明 |
| --- | --- |
| `task_id` | 审核任务 ID |

#### 响应示例

```json
{
  "task_id": "review-task-002",
  "status": "PENDING_MANUAL_REVIEW",
  "document_type": "food_license",
  "skill_name": "food_license",
  "skill_version": "v1",
  "ruleset_version": "food-license-rules-v1",
  "risk_level": "HIGH",
  "needs_manual_review": true,
  "supplier": {
    "name": "成都示例食品有限公司",
    "credit_code": "91510100MA00000000",
    "address": "成都市示例区示例路 100 号"
  },
  "rule_results": [
    {
      "rule_code": "FOOD_LICENSE_EXPIRED",
      "rule_name": "证照是否过期",
      "passed": false,
      "risk_level_on_failure": "HIGH",
      "message": "当前日期超过证照有效期截止日期"
    }
  ],
  "manual_review": {
    "status": "PENDING",
    "reasons": ["证照已过期"],
    "reviewer": null,
    "action": null,
    "comment": null,
    "reviewed_at": null
  },
  "summary": "发现高风险问题，建议人工复核证照有效期。",
  "skill_result": {
    "normalized_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "business_items": ["预包装食品销售"],
      "valid_to": "2025-01-01"
    }
  },
  "created_at": "2026-06-08T14:30:00+08:00",
  "updated_at": "2026-06-08T14:30:03+08:00"
}
```

#### 处理语义

- 查询接口只读取已保存的审核任务和结果；
- 查询接口不重新执行 LangGraph 工作流；
- 查询接口不重新调用 LLM；
- 查询接口不重新计算规则结果，除非后续明确增加重新审核接口。
- 查询响应中的食品安全证照专属字段通过 `skill_result` 返回。

## 9. 提交人工复核动作

### 9.1 `POST /api/v1/food-license/reviews/{task_id}/manual-review`

用于审核人员对需要人工复核的任务提交复核动作。

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `action` | string | 是 | `APPROVE`、`REJECT` 或 `REQUEST_MORE_INFO` |
| `reviewer` | string | 是 | 复核人标识 |
| `comment` | string | 否 | 复核备注 |

#### 请求示例

```json
{
  "action": "REJECT",
  "reviewer": "reviewer-001",
  "comment": "证照已过期，需供应商重新提供有效证照。"
}
```

#### 响应示例

```json
{
  "task_id": "review-task-002",
  "status": "MANUAL_REVIEWED",
  "manual_review": {
    "status": "COMPLETED",
    "reviewer": "reviewer-001",
    "action": "REJECT",
    "comment": "证照已过期，需供应商重新提供有效证照。",
    "reviewed_at": "2026-06-08T15:10:00+08:00"
  },
  "risk_level": "HIGH",
  "needs_manual_review": false,
  "updated_at": "2026-06-08T15:10:00+08:00"
}
```

#### 处理语义

- 人工复核动作不覆盖原始规则结果；
- 原始规则结果、最终风险等级和摘要建议应保留审计记录；
- 人工复核结论作为人工决策结果保存；
- 每次人工复核动作都应写入审计日志。
- 人工复核基础设施属于平台；是否进入人工复核、初始状态和 `reasons` 由 Skill 在 `review(input_context)` 中决定。

## 10. 文件上传接口预留

### 10.1 `POST /api/v1/food-license/reviews:upload`

该接口仍作为 V1 后续扩展设计保留，不属于当前小步实现的生产接口。

建议语义：

- 接收图片或 PDF 文件；
- 接收供应商业务信息；
- 由 `food_license` Skill 内部 document loader / OCR adapter 解析文件并生成 OCR 文本；
- 复用 OCR 文本审核任务流程，并继续走 Review Service + Skill Registry。

当前小步已经定义并测试文件输入边界：

- `ReviewInput.file` 可表达 PDF / 图片输入；
- Skill 内部存在 document loader / OCR adapter 边界；
- 测试可通过 fake OCR / `stub_ocr_text` 返回固定 OCR 文本；
- `extract_fields` 节点优先执行确定性正则抽取，并保留可配置 LangChain LLM 结构化补充边界；
- 真实 LLM 仅在 `FOOD_LICENSE_LLM_ENABLED=true` 且 API Key、模型等配置完整时运行；
- 测试默认使用 fake LLM / stub，不依赖真实 API Key 或网络；
- API 层不得直接调用 OCR、LangChain、LangGraph 节点或规则实现。

当前仍不要求实现：

- 生产级图片 OCR；
- 生产级 PDF 图片页 OCR；
- 文件存储；
- 多模态模型直接读取图片；
- 生产级上传大小限制和安全扫描。

## 11. 错误编码

| HTTP 状态码 | 错误编码 | 说明 |
| --- | --- | --- |
| `400` | `VALIDATION_ERROR` | 请求字段缺失、格式错误或枚举值非法 |
| `400` | `EMPTY_OCR_TEXT` | `ocr_text` 为空或只有空白字符 |
| `404` | `REVIEW_TASK_NOT_FOUND` | 审核任务不存在 |
| `409` | `MANUAL_REVIEW_NOT_ALLOWED` | 当前任务状态不允许人工复核 |
| `422` | `UNSUPPORTED_DOCUMENT_TYPE` | 材料无法识别为食品安全相关证照，且策略要求拒绝继续处理 |
| `500` | `WORKFLOW_EXECUTION_FAILED` | LangGraph 工作流执行失败 |
| `500` | `PERSISTENCE_ERROR` | 审核任务或结果保存失败 |

### 11.1 空 OCR 文本错误示例

```json
{
  "error": {
    "code": "EMPTY_OCR_TEXT",
    "message": "ocr_text 不能为空",
    "details": [
      {
        "field": "ocr_text",
        "message": "请提供食品安全证照 OCR 文本"
      }
    ],
    "request_id": "req-20260608-000002"
  }
}
```

### 11.2 任务不存在错误示例

```json
{
  "error": {
    "code": "REVIEW_TASK_NOT_FOUND",
    "message": "审核任务不存在",
    "details": [
      {
        "field": "task_id",
        "message": "未找到 review-task-999"
      }
    ],
    "request_id": "req-20260608-000003"
  }
}
```

## 12. 数据保存要求

API 实现应通过 Service / Repository 将以下数据保存到 SQLite / MySQL：

- 审核任务：任务 ID、输入来源、供应商信息、任务状态、创建时间、更新时间；
- 审核结果：证照类型、`skill_name`、`skill_version`、`ruleset_version`、最终风险等级、审核建议、是否需要人工复核；
- Skill 专属结果：通过 `skill_result` 保存 LangChain / LLM 输出的食品安全证照结构化字段、规范化字段和其他 Skill 专属 payload；
- 规则结果：Python 规则引擎输出的规则编码、规则名称、是否通过、未通过时产生的风险等级和提示信息；
- 人工复核记录：复核动作、复核人、复核备注、复核时间；
- 审计日志：任务创建、Skill 路由、工作流开始、节点执行、规则校验、风险汇总、人工复核等关键事件。

每个 `ReviewResult` 和审计日志都应记录 `skill_name`、`skill_version` 和 `ruleset_version`。这些值来自 Skill `metadata.yaml` 和 Skill 包内静态 `rules.yaml`。

## 13. 验收标准

- API 契约明确第一阶段优先支持 OCR 文本输入闭环；
- API 契约明确 PDF / 图片文件输入是 V1 下一阶段边界或 stub，不代表生产 OCR 已完成；
- API 契约包含健康检查、创建 OCR 文本审核任务、查询审核结果和人工复核接口；
- API 契约明确请求字段包括 `ocr_text`、`file`、供应商名称、统一社会信用代码、供应商经营地址和可选证照类型；
- API 契约明确响应字段包括任务状态、证照类型、Skill 身份信息、规则结果、最终风险等级、人工复核标记、摘要建议和 `skill_result`；
- API 契约明确食品安全证照抽取字段和规范化字段属于 `skill_result`，不是长期平台顶层字段；
- API 契约明确规则结果使用 `risk_level_on_failure` 表示该规则未通过时产生的风险等级；
- API 契约明确 FastAPI 只负责 HTTP API 边界；
- API 契约明确 `/api/v1/food-license/reviews` 是 `food_license` Skill 快捷入口；
- API 契约明确后续 `/api/v1/reviews` 是平台通用入口；
- API 契约明确所有入口都必须走 Review Service + Skill Registry；
- API 契约明确平台只调用 `Skill.review(input_context) -> ReviewResult`；
- API 契约明确 `metadata.yaml` 是 Skill 运行时 manifest；
- API 契约明确 Registry V1 使用显式注册内置 Skill；
- API 契约明确 LangGraph 负责食品安全证照检测 V1 Skill 内部流程编排；
- API 契约明确 LangChain / LLM 只负责字段抽取、结构化输出和摘要建议；
- API 契约明确真实 LLM 通过 `FOOD_LICENSE_LLM_*` 环境变量启用，测试默认不调用真实 LLM；
- API 契约明确 LLM 抽取失败、解析失败或未配置时必须继续使用确定性正则结果；
- API 契约明确 LLM 不直接做最终规则判定；
- API 契约明确 Python 规则引擎负责规则判断和最终风险等级汇总；
- API 契约明确 `app/rules/` 只放通用规则基础设施，具体业务规则和 `rules.yaml` 放在 Skill 内部；
- API 契约明确人工复核基础设施属于平台，复核决策由 Skill 决定；
- API 契约明确 SQLite / MySQL 保存审核任务、审核结果、规则结果、人工复核和审计日志；
- API 契约没有把 Java / Spring Boot 或任何 Java 模块放入 V1 技术栈或实现范围；
- 本文档只描述契约，不要求实现接口代码。
