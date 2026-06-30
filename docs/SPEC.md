# 技术规范文档

本文档描述 `document-ai-review` 当前 demo 的技术实现方式，回答“怎么做”。产品背景和业务需求以 `docs/PRD.md` 为准；接口细节以 `docs/API.md` 为准。

## 1. 系统架构

### 1.1 架构目标

`document-ai-review` 面向企业内部文档智能审核场景，把营业执照、食品证照、烟草证、QC 报告、合同等非结构化材料转成可抽取、可校验、可追溯、可人工复核的结构化审核结果。

当前 demo 不拆分 Java / Spring Boot 服务，后端统一由 Python `ai-service` 承担 HTTP API、审核编排、规则执行、结果保存和人工复核。

当前工作流主线采用 LangGraph + LangChain：用 LangGraph 表达审核流程和人工复核路由，用 LangChain 封装 OCR、字段抽取、字段标准化等结构化工具能力。

### 1.2 总体链路

```text
业务系统 / 前端控制台 / 测试脚本
    ↓
FastAPI HTTP API
    ↓
Review Service
    ↓
UseCase Thin Entry
    ↓
Workflow Registry / Graph Runtime
    ↓
LangGraph StateGraph
    ↓
LangChain Tools + Domain Rules
    ↓
ReviewResult
    ↓
Repository
```

### 1.3 前后端交互

```text
web-console
    ↓ HTTP JSON
ai-service FastAPI
    ↓
ReviewService
    ↓
UseCase / Workflow
    ↓
Repository
```

交互约定：

- 前端通过 HTTP API 创建审核任务、查询审核结果、提交人工复核动作。
- 后端返回统一 JSON 结构，核心结果使用 `ReviewResult`。
- 后端可通过 repository 保存完整审核快照和业务投影表。
- 企业微信登录、通知 worker、SRM 来源任务当前作为 demo 集成边界存在。

### 1.4 服务职责边界

| 模块 | 职责 | 不做什么 |
| --- | --- | --- |
| FastAPI | HTTP API、参数解析、基础校验、错误响应 | 不执行审核规则，不直接调用 graph 节点 |
| ReviewService | 创建任务 ID、构造 `ReviewInputContext`、调用 graph runtime、保存结果 | 不手写业务流程 |
| UseCase Thin Entry | 声明用例身份、版本、规则集，调用对应 workflow | 不编排节点，不做最终规则判断 |
| Workflow / Graph Runtime | 使用 LangGraph 编排节点、条件路由、人工复核 | 不持久化业务投影 |
| LangChain Tools / Capability | OCR、视觉解析、字段抽取、字段标准化、文档分类等无状态能力 | 不负责组装平台级 `ReviewResult` |
| Domain Rules | 最终合规判断、风险等级、人工复核需求、`RuleResult` | 不把最终结论交给 LLM |
| Agent Skill | 维护 Prompt / Policy / 规则口径 | 不直接调用 OCR / LLM / OA / ERP |
| Repository | 保存完整结果、查询、人工复核、审计、通知队列 | 不重新计算审核结论 |

核心约束：

- LLM 可辅助字段抽取、解释和结构化输出，但最终合规结论应逐步收口到确定性 Domain Rules。
- Capability 不再是流程层对象，也不负责组装平台级 `ReviewResult`。
- 证照专属内容放入 `skill_result` 和对应投影表，平台顶层结果保持通用结构。

### 1.5 架构决策

Status: Accepted

当前终态架构：

```text
API Layer
  -> UseCase = Thin Entry
  -> Workflow = LangGraph StateGraph
  -> Capability = LangChain Tools
  -> Skill = Prompt / Policy Layer
  -> Domain Rules = Final Compliance Decision
```

This is a breaking change. We do not preserve the old capability-as-workflow-layer architecture as a compatibility target. In short: do not preserve the old capability-as-workflow-layer architecture.

Guardrails:

- LLM must not make the final compliance decision.
- LangChain agent must not replace deterministic workflow control.
- Capability tools must not contain workflow orchestration.
- Do not mix multiple tool systems for the same runtime extension point.
- Prompt and Skill text must not become hidden control flow.
- Graph routing decisions must be testable from typed state and domain rule outputs.

## 2. 技术选型

### 2.1 后端

| 技术 | 用途 | 选择理由 |
| --- | --- | --- |
| Python 3.12 | 后端主语言 | 适合快速接入 OCR、LLM、文档解析和 AI workflow |
| FastAPI | HTTP API | 类型友好、自动 OpenAPI、适合 demo 到服务化演进 |
| Pydantic v2 | 请求、结果、领域模型 | 保持结构化输入输出，降低 dict 传递风险 |
| LangGraph | 审核 workflow 编排 | 显式表达节点、边、条件路由、人工复核 |
| LangChain | LLM tool / prompt / structured output | 统一封装模型调用和结构化工具 |
| pytest | 后端测试 | 已覆盖 API、workflow、repository、规则边界 |
| PyMySQL | MySQL 访问 | 用于 SRM 来源任务和审核结果库 |
| SQLite | 本地 demo 样例数据 | 便于本地快速验证，不依赖外部数据库 |
| pypdf / pdf2image / Pillow | PDF / 图片处理 | 支持证照文件解析和视觉识别输入 |

### 2.2 前端

| 技术 | 用途 | 选择理由 |
| --- | --- | --- |
| Vue 3 | 前端 UI | 当前项目已使用，适合中后台页面 |
| Vite | 开发构建 | 启动快、配置轻 |
| Pinia | 前端状态管理 | 管理用户和页面状态 |
| Axios | HTTP 请求 | 调用后端 API |
| Vant | 移动端 / 企业微信页面组件 | 适合企微内嵌工作台样式 |

### 2.3 外部集成

| 集成 | 当前状态 | 说明 |
| --- | --- | --- |
| OpenAI / 兼容模型 API | 通过环境变量配置 | 用于 LLM 抽取、结构化输出、规则解释 |
| 阿里云 OCR / Qwen OCR | 通过 adapter 预留和测试 | 用于证照图片/PDF 识别 |
| SRM MySQL | 通过 `SRM_MYSQL_*` 配置 | 拉取食品证照、生产许可证等来源记录 |
| Review Result MySQL | 通过 `REVIEW_RESULT_MYSQL_*` 配置 | 保存审核结果、投影表、人工复核和通知队列 |
| 企业微信 | 通过 `WECOM_*` 配置 | 登录、通知 worker、前端工作台 |

## 3. 数据模型

### 3.1 核心领域模型

核心模型位于 `ai-service/app/models/review.py`。

#### ReviewInput

审核请求输入。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ocr_text` | `str \| None` | OCR 文本输入；部分证照流程已要求改用文件输入 |
| `file` / `document` | `ReviewDocumentInput \| None` | 文件输入，支持本地路径、远程 URI、文件名、MIME 类型 |
| `supplier_name` | `str` | 供应商名称 |
| `supplier_credit_code` | `str` | 供应商统一社会信用代码 |
| `supplier_address` | `str \| None` | 供应商地址 |
| `declared_document_type` | `str \| None` | 调用方声明的文档类型 |
| `source` | `dict` | 来源系统记录，例如 SRM 记录 ID、附件 ID、租户 |
| `options` | `dict` | 调用选项 |

#### ReviewInputContext

运行时上下文。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | `str` | 审核任务 ID |
| `input` | `ReviewInput` | 原始审核输入 |
| `use_case_name` | `str` | 用例名称 |
| `use_case_version` | `str` | 用例版本 |
| `ruleset_version` | `str` | 规则集版本 |

#### ReviewResult

平台级审核结果。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | `str` | 审核任务 ID |
| `use_case_name` | `str` | 用例名称 |
| `use_case_version` | `str` | 用例版本 |
| `skill_name` / `skill_version` | `str` | 兼容字段，不作为新架构扩展点 |
| `ruleset_version` | `str` | 规则集版本 |
| `capability_names` | `list[str]` | 本次使用的能力名称 |
| `document_type` | `str` | 文档类型 |
| `status` | `ReviewStatus` | 审核状态 |
| `risk_level` | `RiskLevel` | 风险等级 |
| `needs_manual_review` | `bool` | 是否需要人工复核 |
| `rule_results` | `list[RuleResult]` | 规则执行结果 |
| `summary` | `str` | 审核摘要 |
| `manual_review` | `ManualReview` | 人工复核状态 |
| `audit_events` | `list[AuditEvent]` | 审计事件 |
| `created_at` / `updated_at` | `datetime` | 创建和更新时间 |
| `skill_result` | `dict` | 证照专属结构化结果和运行证据 |

#### 枚举

| 枚举 | 取值 |
| --- | --- |
| `RiskLevel` | `HIGH` / `MEDIUM` / `LOW` / `NONE` |
| `ReviewStatus` | `CREATED` / `RUNNING` / `REVIEWED` / `PENDING_MANUAL_REVIEW` / `MANUAL_REVIEWED` / `FAILED` |
| `ManualReviewStatus` | `NOT_REQUIRED` / `PENDING` / `COMPLETED` |

### 3.2 结果库表结构

当前 repository 会保存一份完整 JSON 快照，并按业务场景写入投影表，便于列表查询、筛选、人工复核和通知。

#### `review_results`

完整审核结果快照表。

| 字段 | 说明 |
| --- | --- |
| `task_id` | 主键，审核任务 ID |
| `payload_json` | 完整 `ReviewResult` JSON |
| `created_at` | 创建时间 |

#### `business_license_reviews`

营业执照审核投影表。

| 字段 | 说明 |
| --- | --- |
| `task_id` | 主键 |
| `source_record_id` / `source_attachment_ref_id` / `source_url` / `tenant` | 来源系统信息 |
| `document_type` | 文档类型 |
| `business_name` / `credit_code` / `business_address` / `legal_person` | 营业执照主体字段 |
| `valid_from` / `valid_to` / `issue_authority` / `issue_date` | 证照有效期和签发信息 |
| `review_status` / `risk_level` / `needs_manual_review` / `summary` | 审核结论 |
| `rule_results_json` | 规则结果 |
| `extracted_fields_json` / `normalized_fields_json` | 抽取字段和标准化字段 |
| `extraction_metadata_json` / `source_evidence_json` | 抽取元数据和证据 |
| `manual_review_*` | 人工复核状态、结论、备注、复核人、复核时间 |
| `created_at` / `updated_at` | 时间字段 |

#### `food_license_reviews`

食品经营许可证审核投影表。

| 字段 | 说明 |
| --- | --- |
| `task_id` | 主键 |
| `source_record_id` / `source_attachment_ref_id` / `source_url` / `tenant` | 来源系统信息 |
| `document_type` | 文档类型 |
| `subject_name` / `credit_code` / `license_no` | 主体和许可证编号 |
| `business_address` / `legal_person` / `business_items_json` | 经营地址、负责人、经营项目 |
| `valid_from` / `valid_to` / `issue_authority` / `issue_date` | 有效期和签发信息 |
| `review_status` / `risk_level` / `needs_manual_review` / `summary` | 审核结论 |
| `rule_results_json` / `extracted_fields_json` / `normalized_fields_json` | 规则和字段结果 |
| `extraction_metadata_json` / `source_evidence_json` | 抽取元数据和证据 |
| `manual_review_*` / `created_at` / `updated_at` | 人工复核和时间字段 |

#### `food_production_license_reviews`

食品生产许可证审核投影表。

| 字段 | 说明 |
| --- | --- |
| `task_id` | 主键 |
| `source_record_id` / `source_attachment_ref_id` / `source_url` / `tenant` | 来源系统信息 |
| `document_type` | 文档类型 |
| `supplier_name` / `credit_code` | 供应商主体信息 |
| `review_status` / `risk_level` / `needs_manual_review` / `summary` | 审核结论 |
| `rule_results_json` / `extracted_fields_json` / `normalized_fields_json` | 规则和字段结果 |
| `extraction_metadata_json` / `source_evidence_json` | 抽取元数据和证据 |
| `manual_review_*` / `created_at` / `updated_at` | 人工复核和时间字段 |

#### `tobacco_license_reviews`

烟草证审核投影表。

| 字段 | 说明 |
| --- | --- |
| `task_id` | 主键 |
| `source_record_id` / `source_attachment_ref_id` / `source_url` / `tenant` | 来源系统信息 |
| `document_type` | 文档类型 |
| `subject_name` / `business_address` / `legal_person` / `license_no` | 烟草证主体字段 |
| `valid_from` / `valid_to` | 有效期 |
| `review_status` / `risk_level` / `needs_manual_review` / `summary` | 审核结论 |
| `rule_results_json` / `extracted_fields_json` / `normalized_fields_json` | 规则和字段结果 |
| `extraction_metadata_json` / `source_evidence_json` | 抽取元数据和证据 |
| `manual_review_*` / `created_at` / `updated_at` | 人工复核和时间字段 |

#### `tobacco_consistency_reviews`

营业执照与烟草证一致性审核投影表。

| 字段 | 说明 |
| --- | --- |
| `task_id` | 主键 |
| `source_record_id` / `source_attachment_ref_id` / `source_url` / `tenant` | 来源系统信息 |
| `document_type` / `subject_name` | 文档类型和主体名称 |
| `review_status` / `risk_level` / `needs_manual_review` / `summary` | 审核结论 |
| `rule_results_json` | 规则结果 |
| `comparison_json` | 双证字段比对结果 |
| `business_license_fields_json` / `tobacco_license_fields_json` | 双证字段 |
| `source_evidence_json` | 来源证据 |
| `manual_review_*` / `created_at` / `updated_at` | 人工复核和时间字段 |

#### `product_report_reviews` 与 `product_report_inspection_items`

QC 商品批次报告 / 第三方检验报告投影表。

| 表 | 说明 |
| --- | --- |
| `product_report_reviews` | 保存商品名称、供应商、批号、生产日期、签发日期/批准日期、有效截止日、检验结论、审核结论等 |
| `product_report_inspection_items` | 保存检验项目明细，主键为 `task_id + item_index` |

产品报告首期来源为当前 SRM MySQL 商品维度材料：

```sql
select *
from srm.certification t1
left join srm.attachment t2 on t1.uuid = t2.refId
where t2.tenant = '8560'
  and t1.category = 'sku'
  and t1.typeName = '产品报告'
  and t1.deleted = 0
  and t2.removed = 0
```

`typeName='产品报告'` 统一映射为 `declared_document_type='product_report'`，由 `qc_document_review` 处理。该来源属于商品维度材料，不与供应商证照 source task 混用命名或业务语义。

产品报告有效期规则：优先使用报告中的签发日期/批准日期，计算 `有效截止日 = 签发日期或批准日期 + 180天`；`有效截止日 - 核验当天日期 < 0` 为已过期，`0..30` 天为三十天内即将过期，`>30` 天为未过期。

#### `business_license_review_audit_events`

营业执照审核审计事件表。

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `task_id` | 审核任务 ID |
| `event_type` / `message` / `occurred_at` | 事件类型、描述、发生时间 |
| `actor_id` / `actor_username` | 操作人 |
| `details_json` | 事件详情 |

#### `wecom_notification_queue`

企业微信通知队列表。

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `channel` / `status` / `template` | 通知渠道、状态、模板 |
| `to_user_ids_json` / `recipient_names_json` | 接收人 |
| `message` | 通知文本 |
| `task_id` / `document_type` / `detail_url` | 关联审核任务 |
| `attempts` / `error` / `next_retry_at` / `sent_at` | 重试和发送状态 |
| `created_at` / `updated_at` | 时间字段 |

### 3.3 业务边界

#### business_license

business_license capability 只负责营业执照单证审核。

当前范围：

- 来源记录标准化、远程文档获取、规则执行、`ReviewResult` 映射、MySQL 审核结果库投影。

当前不做：

- 不实现烟草证字段模型。
- 不实现双证一致性规则。
- 不实现 OA 回写。
- 不实现企微通知。

## 4. API 接口

### 4.1 通用约定

| 项 | 约定 |
| --- | --- |
| Base URL | 本地默认 `http://localhost:8000` |
| 请求格式 | JSON；文件输入通过 `file.local_path`、`file.file_path` 或 `file.file_uri` 描述 |
| 响应格式 | JSON |
| 时间格式 | ISO 8601 或 `YYYY-MM-DD` |
| 认证 | 本地账号密码 token、企业微信 SSO、部分 worker 使用 Bearer token |

错误响应使用 FastAPI `HTTPException`，`detail` 中包含：

```json
{
  "code": "ERROR_CODE",
  "message": "错误说明"
}
```

### 4.2 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 返回服务状态、服务名、版本、时间戳 |

### 4.3 认证接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | 本地账号密码登录 |
| `GET` | `/api/v1/auth/providers` | 查询可用登录提供方 |
| `GET` | `/api/v1/auth/sso/start` | 发起企业微信 SSO |
| `GET` | `/api/v1/auth/sso/callback` | 企业微信 SSO 回调 |
| `GET` | `/api/v1/auth/me` | 查询当前登录用户 |

### 4.4 营业执照审核接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/business-license/reviews` | 创建营业执照审核任务 |
| `POST` | `/api/v1/business-license/reviews/from-srm` | 从 SRM 拉取一条营业执照来源记录并审核 |
| `GET` | `/api/v1/business-license/reviews` | 查询营业执照审核列表 |
| `GET` | `/api/v1/business-license/reviews/{task_id}` | 查询营业执照审核详情 |
| `POST` | `/api/v1/business-license/reviews/{task_id}/manual-review` | 提交营业执照人工复核 |

创建审核请求示例：

```json
{
  "supplier_name": "成都示例商贸有限公司",
  "supplier_credit_code": "91510100MA0000000X",
  "declared_document_type": "business_license",
  "file": {
    "local_path": "/tmp/business-license.pdf",
    "file_name": "business-license.pdf",
    "mime_type": "application/pdf"
  },
  "source": {
    "record_id": "srm-001",
    "tenant": "demo"
  }
}
```

### 4.5 食品经营许可证审核接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/food-license/reviews` | 创建食品经营许可证审核任务 |
| `POST` | `/api/v1/food-license/reviews/from-srm` | 从 SRM 拉取一条食品经营许可证来源记录并审核 |

当前食品经营许可证审核要求文件输入，不支持 `ocr_text` 或 `file.stub_text`。

### 4.6 QC 审核接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/qc/food-production-license/reviews/from-srm` | 从 SRM 拉取一条食品生产许可证来源记录并审核 |
| `POST` | `/api/v1/qc/product-report/reviews/from-srm` | 从 SRM 拉取一条商品产品报告 / 第三方检验报告来源记录并审核 |
| `GET` | `/api/v1/qc/reviews` | 查询 QC 审核列表 |
| `GET` | `/api/v1/qc/reviews/{task_id}` | 查询 QC 审核详情 |
| `POST` | `/api/v1/qc/reviews/{task_id}/manual-review` | 提交 QC 人工复核 |

### 4.7 企业微信前端工作台接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/dashboard/stats` | 工作台统计 |
| `GET` | `/api/dashboard/daily` | 每日趋势 |
| `GET` | `/api/dashboard/history` | 历史统计 |
| `GET` | `/api/review/list` | 审核列表 |
| `GET` | `/api/review/{task_id}` | 审核详情 |
| `POST` | `/api/review/{task_id}/confirm` | 确认审核通过 |
| `POST` | `/api/review/{task_id}/flag` | 标记审核异常 |
| `POST` | `/api/query` | 查询占位接口 |
| `POST` | `/api/query/batch` | 批量查询占位接口 |
| `POST` | `/api/query/excel` | Excel 查询占位接口 |
| `POST` | `/api/query/download` | 下载占位接口 |
| `GET` | `/api/query/recent` | 最近查询记录 |
| `GET` | `/api/admin/notify-users` | 查询通知用户 |
| `PUT` | `/api/admin/notify-users` | 更新通知用户 |
| `POST` | `/api/admin/check-expiry` | 触发过期检查 |
| `GET` | `/api/records` | 查询记录 |
| `DELETE` | `/api/records/{record_id}` | 删除记录 |
| `GET` | `/api/tobacco/reports` | 烟草报告列表占位 |
| `GET` | `/api/contract/reports` | 合同报告列表占位 |

### 4.8 企业微信通知接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` / `GET` | `/api/v1/wecom/notifications/worker` | 触发通知队列 worker，需要 `WECOM_WORKER_TOKEN` |

## 5. 目录结构

### 5.1 根目录

```text
document-ai-review/
├── AGENTS.md            # Codex 项目说明
├── README.md            # 项目主上下文
├── ai-service/          # Python FastAPI 后端
├── web-console/         # Vue 前端控制台
├── docs/                # PRD / SPEC / 架构 / API 文档
├── .agents/skills/      # 业务规则口径
└── ci-config/           # Dockerfile / Jenkinsfile
```

### 5.2 后端目录

```text
ai-service/
├── app/
│   ├── api/             # FastAPI 路由
│   ├── capabilities/    # LangChain tools / 结构化能力
│   ├── core/            # 配置、环境变量
│   ├── integrations/    # SRM、MySQL、企业微信等外部集成
│   ├── models/          # Pydantic 领域模型
│   ├── repositories/    # 审核结果保存、查询、人工复核
│   ├── services/        # ReviewService、通知服务
│   ├── tools/           # OCR、文件识别、规则审核等工具适配
│   ├── use_cases/       # 业务用例 Thin Entry
│   └── workflows/       # LangGraph workflow 和 runtime
├── data/                # 本地 demo 数据
├── scripts/             # 本地验证脚本
├── tests/               # pytest 测试
├── pytest.ini
└── requirements.txt
```

### 5.3 前端目录

```text
web-console/
├── src/
│   ├── api/             # Axios API 封装
│   ├── components/      # 通用组件
│   ├── router/          # Vue Router
│   ├── store/           # Pinia store
│   ├── utils/           # 工具函数
│   └── views/           # 页面
├── index.html
├── package.json
└── vite.config.js
```

### 5.4 文档目录

```text
docs/
├── PRD.md               # 产品需求
├── SPEC.md              # 技术规范
└── API.md               # API 契约
```

## 6. 本地运行与验证

### 6.1 Python 环境

默认使用：

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python
```

### 6.2 后端

安装依赖：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pip install -r requirements.txt
```

启动服务：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

运行测试：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest
```

### 6.3 前端

启动开发服务：

```bash
cd web-console
npm run dev
```

构建：

```bash
cd web-console
npm run build
```

## 7. 非功能约束

- 安全：`.env`、数据库密码、API key、GitHub token 不进入代码仓库。
- 可追溯：完整审核结果必须保留在 `review_results.payload_json`。
- 可复核：需要人工确认的结果必须进入 `manual_review` 状态，并记录复核人、复核动作和备注。
- 可扩展：新增证照类型时，应新增 use case、workflow、capability/domain rules、skill 规则口径和投影表。
- 可测试：新增业务规则、API、repository 投影必须补充 pytest。
- 架构一致：不要重新引入 Java / Spring Boot；不要让 LLM 直接给出最终合规结论；不要用 LangChain agent 替代 deterministic workflow。
