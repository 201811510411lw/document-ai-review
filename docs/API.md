# document-ai-review 当前 API 契约

本文档描述当前 FastAPI 服务已经实现的 HTTP 行为。原始产品设想见
[PRD.md](PRD.md)，全部 operation 的机器生成清单见
[api/openapi-operations.md](api/openapi-operations.md)。

## 1. 事实源与维护方式

- 当前 HTTP 路由以 FastAPI `app.main:app` 生成的 OpenAPI 为事实源。
- `docs/api/openapi-operations.md` 是生成产物，不手工编辑。
- 请求体和响应模型以运行中的 `/docs`、`/openapi.json` 和本文件的业务约定为准。
- 未实现接口不能混入当前契约；未来设计必须显式标记为 `proposed`。

生成并校验 operation 清单：

```bash
cd ai-service
python scripts/generate_api_operation_inventory.py
python scripts/generate_api_operation_inventory.py --check
```

## 2. 通用约定

### 2.1 Base URL

本地默认地址：

```text
http://127.0.0.1:8000
```

### 2.2 请求与时间

- JSON 请求使用 `Content-Type: application/json`。
- 文件由受信任的本地路径或远程 URI 描述；当前审核创建接口不是 multipart 上传接口。
- 日期使用 `YYYY-MM-DD`，时间戳使用 ISO 8601。
- 列表接口的分页参数通常为 `page` 和 `page_size`，具体范围以 OpenAPI 为准。

### 2.3 认证

Web Console 支持两种会话凭据：

- `Authorization: Bearer <access_token>`；
- 企业微信 SSO 回调设置的 HttpOnly session cookie。

来源查询、结果查询、人工复核、工作台和 RPA 手动操作通常要求 Web Console
会话。通知 worker 使用独立的 `WECOM_WORKER_TOKEN`。影刀 callback 是供应商回调入口，
当前应用层不校验 Web Console 会话，生产部署必须在网关或网络边界限制来源。

### 2.4 统一审核结果

审核执行结果使用 `ReviewResult`，核心字段包括：

| 字段 | 说明 |
| --- | --- |
| `task_id` | Review Task 唯一标识 |
| `use_case_name` / `use_case_version` | Review Use Case 及版本 |
| `ruleset_version` | 规则集版本 |
| `document_type` | 实际审核文档类型 |
| `status` | Review Task 状态 |
| `risk_level` | `HIGH`、`MEDIUM`、`LOW` 或 `NONE` |
| `needs_manual_review` | 是否需要人工复核 |
| `rule_results` | 确定性 Domain Rule 结果 |
| `manual_review` | 人工复核状态、原因和结论 |
| `audit_events` | 审核审计事件 |
| `skill_result`（兼容字段名） | 文档类型专属结构化结果 |

任务状态为 `CREATED`、`RUNNING`、`REVIEWED`、
`PENDING_MANUAL_REVIEW`、`MANUAL_REVIEWED` 或 `FAILED`。

### 2.5 错误响应

业务错误通常由 FastAPI `HTTPException` 返回：

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "错误说明"
  }
}
```

参数模型校验错误由 FastAPI 返回 `422`。调用方必须同时处理字符串形式和对象形式的
`detail`；当前 API 尚未把所有路由收口到单一错误 envelope。

## 3. 健康检查与认证

### 3.1 健康检查

```text
GET /health
```

该接口不依赖数据库或外部系统，只表示 API 进程可响应。

### 3.2 本地登录与企业微信 SSO

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | 使用本地账号密码换取 Bearer token |
| `GET` | `/api/v1/auth/providers` | 查询企业微信等登录提供方是否已配置 |
| `GET` | `/api/v1/auth/sso/start` | 生成企业微信授权地址 |
| `GET` | `/api/v1/auth/sso/callback` | 处理企业微信 OAuth 回调并设置 session cookie |
| `GET` | `/api/v1/auth/me` | 返回当前已认证用户 |
| `GET` | `/auth/profile` | 返回前端使用的用户资料投影 |

本地登录请求：

```json
{
  "username": "reviewer",
  "password": "<configured password>"
}
```

## 4. 营业执照审核

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/business-license/reviews` | 使用指定文件创建审核 |
| `POST` | `/api/v1/business-license/reviews/from-srm` | 获取一条 SRM 来源记录并审核 |
| `GET` | `/api/v1/business-license/reviews` | 分页查询营业执照审核结果 |
| `GET` | `/api/v1/business-license/reviews/{task_id}` | 查询详情、规则、人工复核和审计事件 |
| `POST` | `/api/v1/business-license/reviews/{task_id}/manual-review` | 提交人工复核 |

文件审核请求示例：

```json
{
  "supplier_name": "示例商贸有限公司",
  "supplier_credit_code": "91510000EXAMPLE001",
  "declared_document_type": "business_license",
  "file": {
    "file_uri": "https://files.example.test/business-license.pdf",
    "file_name": "business-license.pdf",
    "mime_type": "application/pdf"
  },
  "source": {
    "record_id": "source-record-id"
  }
}
```

当前接口要求 `file.local_path`、`file.file_path` 或 `file.file_uri` 至少存在一个，且拒绝
`ocr_text` 和 `file.stub_text`。本地路径只适用于受信任的服务端调用场景。

营业执照人工复核的 `decision` 为 `approved` 或 `rejected`，并要求非空的
`comment` 和 `reviewer_id`。

## 5. 食品经营许可证审核

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/food-license/reviews` | 使用指定文件创建食品经营许可证审核 |
| `POST` | `/api/v1/food-license/reviews/from-srm` | 获取一条 SRM 来源记录并审核 |

输入结构沿用 `ReviewInput`，但当前只接受 PDF、JPG、JPEG 或 PNG 等真实文件输入。
`ocr_text` 和 `file.stub_text` 会返回 `UNSUPPORTED_TEXT_DOCUMENT_INPUT`；没有本地路径或
远程 URI 会返回 `EMPTY_DOCUMENT_INPUT`。

食品经营许可证目前没有独立的结果查询和人工复核 HTTP 入口。需要结果工作台能力时，
应以当前产品流程和持久化投影为准，不能假设存在食品证专属路径。

## 6. QC 审核

QC 路由承载食品生产许可证、产品报告和批次报告的来源审核，并提供共享的结果查询和人工
复核入口。

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/qc/food-production-license/reviews/from-srm` | 审核一条食品生产许可证来源记录 |
| `POST` | `/api/v1/qc/product-report/reviews/from-srm` | 审核一条 SKU 产品报告来源记录 |
| `POST` | `/api/v1/qc/batch-report/reviews/from-starrocks` | 按 `review_date` 审核一个订单中的一条商品批次附件；可传订单/订单行/SKU 精确选择 |
| `GET` | `/api/v1/qc/reviews` | 按主体、证件号、类型、风险、状态和时间分页查询 |
| `GET` | `/api/v1/qc/reviews/{task_id}` | 查询投影详情和完整 `ReviewResult` payload |
| `POST` | `/api/v1/qc/reviews/{task_id}/manual-review` | 提交 QC 人工复核 |

批次报告来源审核默认先随机选择一个符合日期条件的订单，再只选择该订单的一条
`orderLineUuid` 批次明细及其附件。需要精确重试时，可在请求体传入以下任一组合：

```json
{
  "order_number": "10102605050175",
  "orderline_uuid": "订单行 UUID",
  "sku_code": "商品编码"
}
```

QC 人工复核请求：

```json
{
  "decision": "approved",
  "comment": "材料与来源信息一致",
  "reviewer_id": "reviewer-id"
}
```

`decision` 当前只接受 `approved` 或 `rejected`。

## 7. 烟草证来源文件

```text
POST /api/v1/tobacco-license/source-files/from-starrocks
GET /api/v1/tobacco-license/source-files/local/{relative_path}
```

来源请求使用：

```json
{
  "store_identifier": "store-code-or-request-id"
}
```

服务从 OA ecology MySQL 中查询来源附件，将可用文件准备到受控目录，再返回预览和下载地址。
本地文件接口只接受文件存储服务生成的相对路径；`download=1` 会设置下载文件名。

## 8. 烟草证一致性审核

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/tobacco-license-consistency/pending-stores` | 分页查询有待处理 OA 流程的门店 |
| `POST` | `/api/v1/tobacco-license-consistency/oa-auto-review` | 受理 `workflow_id + requestid` OA 自动审核并后台回调结果 |
| `POST` | `/api/v1/tobacco-license-consistency/reviews` | 获取来源文件并执行单门店一致性审核 |
| `POST` | `/api/v1/tobacco-license-consistency/reviews/batch` | 批量执行最多 20 个门店审核 |
| `POST` | `/api/v1/tobacco-license-consistency/reviews/{task_id}/manual-review` | 对报告提交人工复核 |
| `POST` | `/api/v1/tobacco-license-consistency/reviews/{task_id}/oa-callback` | 手动重发当前已持久化的 OA 审核结果 |
| `GET` | `/api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result` | 读取可供 OA 适配器使用的结果载荷 |

OA 两个接口使用独立请求头 `X-OA-Token`，密钥由 `OA_AUTO_REVIEW_TOKEN` 配置。
自动审核要求显式传入正整数 `workflow_id`，当前“烟草商品建档申请”流程传 `614`；系统以 `workflow_id + requestid` 生成稳定任务 ID；
`store_code` 只做来源记录交叉校验。外部决策为 `pass`、`reject`、
`manual_review`、`exception`。最终结果以无认证 JSON POST 到服务端配置的固定回调地址，
并携带原始 `workflow_id`、`requestid` 和 `store_code`。完整请求和响应见
[`docs/api/oa-tobacco-license-consistency.md`](api/oa-tobacco-license-consistency.md)。
证据可靠且字段差异少于 3 项时当前机器人节点返回 `pass` 并流转下一节点，达到 3 项时返回
`reject`；子审核未就绪或关键证据缺失时优先返回 `manual_review`。回调通过 `mismatch_count`
和 `field_differences` 携带具体差异字段及两侧值，使用 `reject_reason_text` 或
`manual_review_reason_text` 提供可直接写入 OA 流转意见的原因文本；完整 `rule_results` 不在
callback 中重复发送，仍可通过结果轮询和系统详情查看。
人工驳回和要求补件必须提供非空 `comment`。详情响应包含 `oa_callback` 和
`oa_callback_history`，用于查看实际请求 JSON、目标地址、HTTP 状态、接收端响应和业务确认结果。

单门店请求：

```json
{
  "store_identifier": "store-code-or-request-id",
  "review_mode": "standard",
  "business_license_fields": {},
  "tobacco_license_fields": {},
  "store_in_store": {},
  "selected_files": []
}
```

`review_mode` 为 `standard` 或 `store_in_store`。请求中的字段只作为人工确认或补充值，
系统优先使用来源文件抽取结果，不能用 OA 门店名称伪造证照主体字段。

批量请求使用 `store_identifiers` 数组；返回每个门店的 `completed` 或 `failed` 结果，单项
失败不会中止其余项目。

控制台审核接口使用 Web Console 会话认证；OA 专用入口使用 `X-OA-Token`。系统只向
服务端配置的固定 OA 回调地址推送最终结果，不接受请求方指定任意 callback URL。更完整的对接说明见
[api/oa-tobacco-consistency-auto-review.md](api/oa-tobacco-consistency-auto-review.md)。

## 9. 影刀 RPA 官网验真

当前 operation：

```text
GET /api/v1/tobacco-license/rpa-verify-capability
POST /api/v1/tobacco-license/rpa-verify
POST /api/v1/tobacco-license/rpa-verify-callback
GET /api/v1/tobacco-license/rpa-verify/{task_id}
```

### 9.1 能力探测

调用方必须先读取 capability。未启用时，手动触发返回 HTTP `400` 和
`RPA_VERIFICATION_DISABLED`，这不是供应商调用失败。

### 9.2 手动触发

```json
{
  "task_id": "review-task-id",
  "certificate_no": "license-number",
  "store_name": "门店名称",
  "requestid": "oa-request-id"
}
```

该接口同步启动影刀任务并轮询终态，然后把验真结果写入对应 Review Result 的文档专属
结果（兼容字段名 `skill_result`）。
不要用同一审核任务重复触发真实 RPA 作业。

### 9.3 状态语义

| 状态 | 业务含义 | 处理建议 |
| --- | --- | --- |
| `PENDING` | 尚未开始 | 等待触发 |
| `IN_PROGRESS` | 影刀任务执行中 | 继续等待或查询 |
| `AUTHENTIC` | 官网请求完成且验真通过 | 可作为正向证据 |
| `FAILED` | 官网请求完成但验真未通过 | 业务负面结果，进入人工处理 |
| `SUSPECTED` | 返回信息不一致 | 业务负面结果，进入人工处理 |
| `NOT_FOUND` | 官网未查询到证照 | 业务负面结果，进入人工处理 |
| `ERROR` | 任务未可靠完成或技术链路异常 | 可重试，不能宣称证照为假 |

影刀输出 `parameter=false` 只有在存在非空 `responseId` 时映射为 `FAILED`；缺少
`responseId` 表示官网请求没有形成可判定结果，映射为 `ERROR`。

### 9.4 Callback

callback 是同步轮询之外的结果兜底。服务按 `jobUuid` 查找已登记的 Review Task；找不到
关联任务或缺少证照号时仍返回接收成功，但不会创建新审核任务。callback 不应作为任意调用
方创建任务的入口。

## 10. Web Console 与通知

`/api/dashboard/*` 提供统计和趋势；`/api/review/*` 提供统一审核工作台列表、详情、确认和
异常标记；`/api/query/*` 提供单条、批量、Excel 查询及下载；`/api/admin/*` 提供通知用户、
导入预览、每日同步和来源时间回填；`/api/records*` 提供结果记录查询、导出和删除；
`/api/tobacco/reports*` 提供烟草报告列表与详情。

前端使用的全部路径以生成的
[FastAPI operation 清单](api/openapi-operations.md)为准。`/api/contract/reports` 当前只返回
占位合同报告数据，不能视为合同审核已经实现。

通知 worker：

```text
GET /api/v1/wecom/notifications/worker
POST /api/v1/wecom/notifications/worker
```

两个方法行为相同，必须使用独立 Bearer token。响应包含 `processed`、`sent`、`failed` 和
`retried` 计数。

## 11. 当前边界

- 尚无平台通用的 `/api/v1/reviews` 创建入口。
- 食品经营许可证尚无专属查询和人工复核 HTTP 入口。
- 合同审核仍是占位 Review Use Case。
- OpenAPI operation 存在不等于外部依赖已配置；来源数据库、OCR、LLM、企业微信和影刀
  都可能因配置关闭或不可用而返回业务错误。
- 本文档不承诺 proposed 接口。新增路由时必须重新生成 operation 清单并同步对应业务说明。
