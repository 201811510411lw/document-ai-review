# 食品安全证照与 QC 文档检测 V1 API 契约

本文档定义食品安全证照与 QC 文档检测 V1 的 FastAPI HTTP API 契约，供后续 `ai-service` 实现、测试脚本和外部系统集成使用。

`README.md` 是项目唯一主上下文；`docs/PRD.md` 是原始产品需求依据。本文档只描述 API 契约，不实现业务代码。

---

## 1. 设计目标

食品安全证照与 QC 文档检测 V1 采用纯 Python 架构，当前只有一个 Python 服务：`ai-service`。

API 契约目标：

- 优先支持食品安全证照和 QC 产品报告审核闭环；
- 为 FastAPI 创建审核任务、查询审核结果和人工复核提供稳定 HTTP 边界；
- 明确请求字段、响应字段、错误语义和状态流转；
- 明确 FastAPI、Review Service、use_case、capability、LangGraph、LangChain、Python 规则引擎和 MySQL 审核结果库的职责边界；
- 明确 `/api/v1/food-license/reviews` 是 `food_license` use_case 快捷入口，`/api/v1/qc/*` 是 QC 聚合查询和商品报告入口，后续 `/api/v1/reviews` 是平台通用入口；
- 为后续文件上传、图片解析和 PDF 解析保留接口扩展空间，但不把它们列为第一阶段必实现能力。

## 2. 职责边界

| 模块 | API 契约中的职责 |
| --- | --- |
| FastAPI | 暴露 HTTP API，完成请求解析、基础校验、响应封装和错误映射 |
| Review Service | 创建审核任务，构造 `input_context`，调用 `ReviewGraphRegistry` runtime entry，协调结果保存和人工复核动作 |
| ReviewGraphRegistry | 显式注册内置 LangGraph workflow runtime entry，按 graph name 或文档类型路由 |
| use_case | Thin Entry，仅负责参数承接、调用 graph runtime、投影 `ReviewResult` |
| LangChain Tool | 无状态能力单元，封装 OCR、字段抽取、标准化和风险评分等可复用能力 |
| LangGraph | 在 `food_license` workflow 内部编排核心流程和节点状态流转 |
| LangChain | 在 capability 或 workflow 内部负责模型调用、Prompt、结构化输出和工具封装 |
| LLM | 只用于字段抽取、结构化输出和摘要建议，不直接做最终规则判定 |
| Python 规则引擎 | 执行确定性规则校验，并基于规则结果汇总最终风险等级 |
| MySQL 审核结果库 | 保存审核任务、审核结果、规则结果、人工复核记录和审计日志 |

平台只调用 `ReviewGraphRegistry` 中的 runtime entry。API 层不得直接实现食品安全证照规则判断，也不得直接调用 `extract_fields`、`run_rules`、`summarize_risk` 或 `route_review` 等 workflow / tool 内部节点。最终风险等级不得由 LLM 直接给出，必须由 Python 规则引擎结果汇总得到。

## 3. 通用约定

### 3.1 Base URL

本地开发默认：

```text
http://localhost:8000
```

食品经营许可证快捷入口使用统一前缀：

```text
/api/v1/food-license
```

QC 证照、产品报告和人工复核聚合接口使用统一前缀：

```text
/api/v1/qc
```

`/api/v1/food-license/reviews` 是 `food_license` use_case 的快捷入口。`/api/v1/qc/product-report/reviews/from-srm` 是 `qc_document_review` 中 `product_report` 的 SRM 拉取入口。后续平台通用入口为：

```text
/api/v1/reviews
```

快捷入口和通用入口都必须经过 Review Service + `ReviewGraphRegistry`，不能维护两套审核逻辑。

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
| `food_production_license` | 食品生产许可证 |
| `product_report` | 商品产品报告 / 第三方检验报告 |
| `batch_report` | 商品批次报告 |
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
| `POST` | `/api/v1/qc/product-report/reviews/from-srm` | 从 SRM 拉取一条商品产品报告并审核 | 必须 |
| `POST` | `/api/v1/qc/batch-report/reviews/from-starrocks` | 从 StarRocks SRM 同步表随机拉取一条商品批次报告并审核 | 必须 |
| `POST` | `/api/v1/tobacco-license/source-files/from-starrocks` | 按门店从 StarRocks OA 快照表查烟草证附件并从本地 NAS 解压落盘 | 必须 |
| `GET` | `/api/v1/tobacco-license/source-files/local/{relative_path}` | 预览或下载已落盘的烟草证文件 | 必须 |
| `GET` | `/api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result` | 获取烟草双证核对的 OA 回传载荷，不主动调用 OA | 必须 |
| `GET` | `/api/v1/qc/reviews` | 查询 QC 审核列表，支持证照和产品报告 | 必须 |
| `GET` | `/api/v1/qc/reviews/{task_id}` | 查询 QC 审核详情 | 必须 |
| `POST` | `/api/v1/qc/reviews/{task_id}/manual-review` | 提交 QC 人工复核动作 | 必须 |
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

## 7. 创建 OCR 文本审核任务

### 7.1 `POST /api/v1/food-license/reviews`

基于 OCR 文本创建食品安全证照审核任务。第一阶段优先实现该接口，用于跑通最小闭环。

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ocr_text` | string | 是 | 食品安全证照 OCR 文本 |
| `supplier.name` | string | 是 | 业务系统中的供应商名称 |
| `supplier.credit_code` | string | 是 | 业务系统中的统一社会信用代码 |
| `supplier.address` | string | 否 | 业务系统中的供应商经营地址 |
| `declared_document_type` | string | 否 | 调用方声明的证照类型，例如 `food_license` |
| `source` | object | 否 | 输入来源元信息 |
| `options` | object | 否 | 审核选项 |

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

#### 响应字段

| 字段 | 说明 |
| --- | --- |
| `task_id` | 审核任务 ID |
| `status` | 审核任务状态 |
| `document_type` | 证照类型识别结果 |
| `use_case_name` | 执行本次审核的 use_case 名称，例如 `food_license` |
| `use_case_version` | 执行本次审核的 use_case 版本 |
| `skill_name` | 兼容字段，短期镜像 `use_case_name` |
| `skill_version` | 兼容字段，短期镜像 `use_case_version` |
| `ruleset_version` | 执行本次审核的规则集版本 |
| `capability_names` | 本次审核使用的 capability 名称列表 |
| `risk_level` | 最终风险等级 |
| `needs_manual_review` | 是否需要人工复核 |
| `rule_results` | Python 规则引擎输出的规则结果；其中 `risk_level_on_failure` 表示该规则未通过时产生的风险等级 |
| `manual_review` | 人工复核状态、原因和后续人工动作信息 |
| `summary` | 摘要建议，可由规则结果和 LLM 辅助生成 |
| `skill_result` | workflow artifact 容器，当前承载食品安全证照的抽取字段、规范化字段和运行证据 |
| `created_at` | 任务创建时间 |
| `updated_at` | 任务更新时间 |

#### 同步完成响应示例

```json
{
  "task_id": "review-task-001",
  "status": "REVIEWED",
  "document_type": "food_license",
  "use_case_name": "food_license",
  "use_case_version": "v1",
  "skill_name": "food_license",
  "skill_version": "v1",
  "ruleset_version": "food-license-rules-v1",
  "capability_names": ["food_license"],
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
- MySQL 审核结果库保存任务、结果、规则结果、人工复核状态和审计日志。

## 8. 创建 SRM 产品报告审核任务

### 8.1 `POST /api/v1/qc/product-report/reviews/from-srm`

从 StarRocks 中同步的 SRM 商品维度产品报告 / 第三方检验报告来源记录拉取一条材料，下载附件并执行 `qc_document_review`。

#### SRM 来源筛选

```sql
select *
from ods_srm_srm_certification_df t1
left join ods_srm_srm_attachment_df t2 on t1.uuid = t2.refId
where t2.tenant = '8560'
  and t1.category = 'sku'
  and t1.typeName = '产品报告'
  and t1.deleted = 0
  and t2.removed = 0
```

#### 输入映射

| SRM 字段 | ReviewInput 字段 | 说明 |
| --- | --- | --- |
| `t1.uuid` | `source.record_id` | SRM 产品报告记录 ID |
| `t2.uuid` | `source.attachment_uuid` | 附件记录 ID |
| `t2.refId` | `source.attachment_ref_id` | 附件关联 ID |
| `t1.tenant` / `t2.tenant` | `source.tenant` | 租户 |
| `t1.vendorName` | `supplier_name` | SRM 供应商名称 |
| `t1.vendorId` | `source.vendor_id` | SRM 供应商 ID |
| `t1.num` / `t1.number` | `source.sku_number` / `source.business_number` | 商品维度业务编号 |
| `t2.attachmentName` | `file.file_name` | 附件名 |
| `t2.url` | `file.file_uri` | 远程 PDF / 图片 URL |
| `t1.typeName='产品报告'` | `declared_document_type='product_report'` | 文档类型声明 |

#### 审核规则摘要

- 报告类型必须为 `product_report`。
- 优先抽取报告编号、样品名称/产品名称、委托单位/生产商、生产日期、签发日期/批准日期、检验结论、检验项目明细。
- 有效期按 `签发日期或批准日期 + 180天` 计算；剩余天数 `<0` 为已过期，`0..30` 为三十天内即将过期，`>30` 为未过期。
- 样品名称/产品名称与 SRM 商品名做模糊匹配；委托单位/生产商与 SRM 供应商名称比对。
- 检验结论包含不合格、不通过、不符合等负向词时判定高风险失败；结论缺失或不明确时进入人工复核。

#### 响应

响应结构与通用 `ReviewResult` 一致，`document_type` 为 `product_report`，`use_case_name` 为 `qc_document_review`。`skill_result.extracted_fields` 至少应包含：

```json
{
  "report_no": "A2260511467101001C",
  "product_name": "鲜切蛋糕(蓝莓风味)",
  "sample_name": "鲜切蛋糕(蓝莓风味)",
  "vendor_name_extracted": "广东乃一口食品有限公司",
  "entrusting_party": "广东乃一口食品有限公司",
  "manufacturer_name": "广东乃一口食品有限公司",
  "production_date": "2026-06-20",
  "issue_date": "2026-06-29",
  "valid_to": "2026-12-26",
  "inspection_conclusion": "所检项目符合要求",
  "inspection_items": []
}
```

### 8.2 `POST /api/v1/qc/batch-report/reviews/from-starrocks`

从 StarRocks 中的 SRM 同步表随机拉取一条商品批次报告来源记录，下载附件并执行 `qc_document_review`。

当前首版默认 `review_date=2026-05-05`，用于验证链路；后续默认值会调整为昨天。调用方可通过查询参数覆盖：

```text
POST /api/v1/qc/batch-report/reviews/from-starrocks?review_date=2026-05-05
```

#### StarRocks 来源筛选

来源表：

```text
ods_srm_srm_orders_df
ods_srm_srm_orderdeliverybatch_df
ods_srm_srm_attachment_df
```

核心筛选：

```sql
t1.tenant = '8560'
and t1.created >= '{review_date} 00:00:00'
and t1.created < '{review_date + 1 day} 00:00:00'
and t1.state = 'finish'
and t3.refType = 'orderDeliveryBatch'
and (t3.removed = 0 or t3.removed is null)
and t3.url is not null
and t3.url <> ''
order by rand()
limit 1
```

#### 输入映射

| StarRocks 字段 | ReviewInput 字段 | 说明 |
| --- | --- | --- |
| `t2.uuid` | `source.record_id` / `source.batch_uuid` | 批次记录 ID |
| `t1.number` | `source.order_number` | 订单号 |
| `t1.vendorName` | `supplier_name` / `source.vendor_name` | 供应商名称 |
| `t2.skuName` | `source.sku_name` | 商品名称 |
| `t2.productionTime` | `source.production_date` | 来源批次生产日期 |
| `t3.uuid` | `source.attachment_uuid` | 附件记录 ID |
| `t3.attachmentName` | `file.file_name` | 附件名 |
| `t3.url` | `file.file_uri` | 远程 PDF / 图片 URL |
| 固定值 | `declared_document_type='batch_report'` | 文档类型声明 |

#### 审核规则摘要

- 抽取厂名/公司名、产品名称、生产批号和生产日期。
- 产品名称与来源商品名比对。
- 厂名/公司名与来源供应商名称比对。
- 报告生产日期需与来源批次生产日期一致；若只识别到生产批号，批号中包含 `YYYYMMDD` 也可视为匹配。
- 附件无法获取可审核文本、关键字段缺失或比对不一致时进入人工复核。

### 8.3 `POST /api/v1/tobacco-license/source-files/from-starrocks`

按门店标识从 StarRocks OA 快照表查询最新烟草证附件元数据，并读取本机 `/data` NAS 挂载路径中的 OA zip 文件，解压到 `ai-service/data/tobacco_license/`。该接口只完成来源文件准备，不执行国家烟草证下载比对和最终审核。

#### 请求示例

```json
{
  "store_identifier": "B65230024"
}
```

#### StarRocks 来源链路

```text
ods_oa_ecology_formtable_main_283_df.ycxsxkz
-> ods_oa_ecology_docdetail_df.ID
-> ods_oa_ecology_docimagefile_df.DOCID / IMAGEFILEID
-> ods_oa_ecology_imagefile_df.IMAGEFILEID / FILEREALPATH
```

核心筛选：

```sql
r.WORKFLOWID = 614
and f.ycxsxkz is not null
and trim(f.ycxsxkz) <> ''
and i.FILEREALPATH is not null
and (
  f.mdbm = '{store_identifier}'
  or f.mdmc = '{store_identifier}'
  or instr(ifnull(f.qsbt, ''), '{store_identifier}') > 0
  or instr(ifnull(f.nrgk, ''), '{store_identifier}') > 0
  or instr(ifnull(r.REQUESTNAME, ''), '{store_identifier}') > 0
)
order by r.CREATEDATE desc, r.CREATETIME desc
```

#### 响应示例

```json
{
  "store_identifier": "B65230024",
  "documents": [
    {
      "source": {
        "requestid": 2801287,
        "store_code": "B65230024",
        "docid": 824576,
        "imagefile_id": 1409517,
        "file_real_path": "/data/oaec/202607/J/38982780-2512-4dd7-8e4d-feb27f5d44bf.zip",
        "is_zip": "1",
        "is_encrypt": "0",
        "is_aes_encrypt": 0
      },
      "files": [
        {
          "file_name": "y.jpg",
          "relative_path": "B65230024/2801287_824576_1409517/y.jpg",
          "content_type": "image/jpeg",
          "preview_url": "/api/v1/tobacco-license/source-files/local/B65230024/2801287_824576_1409517/y.jpg",
          "download_url": "/api/v1/tobacco-license/source-files/local/B65230024/2801287_824576_1409517/y.jpg?download=1"
        }
      ]
    }
  ]
}
```

### 8.4 `GET /api/v1/tobacco-license/source-files/local/{relative_path}`

读取 `ai-service/data/tobacco_license/` 下已解压的烟草证文件。默认用于预览；追加 `?download=1` 时返回附件下载文件名。

## 9. 查询审核任务和结果

### 9.1 `GET /api/v1/food-license/reviews/{task_id}`

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

## 10. 提交人工复核动作

### 10.1 `POST /api/v1/food-license/reviews/{task_id}/manual-review`

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

## 11. 文件上传接口预留

### 11.1 `POST /api/v1/food-license/reviews:upload`

该接口只作为 V1 后续扩展设计保留，不属于第一阶段必实现能力。

建议语义：

- 接收图片或 PDF 文件；
- 接收供应商业务信息；
- 解析文件并生成 OCR 文本；
- 复用 OCR 文本审核任务流程，并继续走 Review Service + Skill Registry。

第一阶段验收不要求实现：

- 图片解析；
- PDF 解析；
- 文件存储；
- 多模态模型直接读取图片；
- 生产级上传大小限制和安全扫描。

## 12. 错误编码

| HTTP 状态码 | 错误编码 | 说明 |
| --- | --- | --- |
| `400` | `VALIDATION_ERROR` | 请求字段缺失、格式错误或枚举值非法 |
| `400` | `EMPTY_OCR_TEXT` | `ocr_text` 为空或只有空白字符 |
| `404` | `REVIEW_TASK_NOT_FOUND` | 审核任务不存在 |
| `409` | `MANUAL_REVIEW_NOT_ALLOWED` | 当前任务状态不允许人工复核 |
| `422` | `UNSUPPORTED_DOCUMENT_TYPE` | 材料无法识别为食品安全相关证照，且策略要求拒绝继续处理 |
| `500` | `WORKFLOW_EXECUTION_FAILED` | LangGraph 工作流执行失败 |
| `500` | `PERSISTENCE_ERROR` | 审核任务或结果保存失败 |

### 12.1 空 OCR 文本错误示例

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

## 13. 数据保存要求

API 实现应通过 Service / Repository 将以下数据保存到 MySQL 审核结果库：

- 审核任务：任务 ID、输入来源、供应商信息、任务状态、创建时间、更新时间；
- 审核结果：证照类型、`use_case_name`、`use_case_version`、`capability_names`、`ruleset_version`、最终风险等级、审核建议、是否需要人工复核；
- 过渡字段：短期继续保存 `skill_name`、`skill_version`，其值镜像 runtime graph 身份；
- workflow artifact：通过 `skill_result` 保存食品安全证照结构化字段、规范化字段和运行证据；
- 规则结果：Python 规则引擎输出的规则编码、规则名称、是否通过、未通过时产生的风险等级和提示信息；
- 人工复核记录：复核动作、复核人、复核备注、复核时间；
- 审计日志：任务创建、use_case 路由、工作流开始、节点执行、规则校验、风险汇总、人工复核等关键事件。

每个 `ReviewResult` 和审计日志都应记录 `use_case_name`、`use_case_version`、`capability_names` 和 `ruleset_version`。`skill_name`、`skill_version` 和 `skill_result` 当前作为兼容字段继续保留。

## 14. 验收标准

- API 契约明确第一阶段优先支持 OCR 文本输入闭环；
- API 契约包含健康检查、创建 OCR 文本审核任务、查询审核结果和人工复核接口；
- API 契约明确请求字段包括 `ocr_text`、供应商名称、统一社会信用代码、供应商经营地址和可选证照类型；
- API 契约明确响应字段包括任务状态、证照类型、use_case 身份信息、capability 名称、规则结果、最终风险等级、人工复核标记、摘要建议和 `skill_result` 兼容容器；
- API 契约明确食品安全证照抽取字段和规范化字段当前属于 `skill_result`，不是长期平台顶层字段；
- API 契约明确规则结果使用 `risk_level_on_failure` 表示该规则未通过时产生的风险等级；
- API 契约明确 FastAPI 只负责 HTTP API 边界；
- API 契约明确 `/api/v1/food-license/reviews` 是 `food_license` use_case 快捷入口；
- API 契约明确后续 `/api/v1/reviews` 是平台通用入口；
- API 契约明确所有入口都必须走 Review Service + `ReviewGraphRegistry`；
- API 契约明确平台只调用 workflow runtime entry；
- API 契约明确 `ReviewGraphRegistry` V1 使用显式注册内置 LangGraph workflow；
- API 契约明确 LangGraph 负责食品安全证照检测 V1 workflow 编排；
- API 契约明确 LangChain / LLM 只负责字段抽取、结构化输出和摘要建议；
- API 契约明确 LLM 不直接做最终规则判定；
- API 契约明确 Python 规则引擎负责规则判断和最终风险等级汇总；
- API 契约明确 `app/rules/` 只放通用规则基础设施，具体业务规则和 `rules.yaml` 放在 capability 内部；
- API 契约明确人工复核基础设施属于平台，复核决策由 use_case / workflow 根据规则结果决定；
- API 契约明确 MySQL 审核结果库保存审核任务、审核结果、规则结果、人工复核和审计日志；
- API 契约没有把 Java / Spring Boot 或任何 Java 模块放入 V1 技术栈或实现范围；
- 本文档只描述契约，不要求实现接口代码。
