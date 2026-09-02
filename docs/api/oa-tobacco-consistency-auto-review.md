# OA 烟草证一致性审核接口（现行）

本文档说明 Web Console 使用的 OA 来源烟草证一致性审核链路。OA 自动节点的专用触发、
鉴权和轮询契约见 [OA 烟草证一致性自动审核接口](oa-tobacco-license-consistency.md)。

## 1. 当前链路

```text
OA 来源记录直接从 ecology MySQL 查询
  -> OA 按 workflow_id + requestid 精确触发，或控制台查询待处理门店
  -> 查询待处理门店
  -> 获取营业执照和烟草证附件
  -> 文档识别与字段抽取
  -> 确定性一致性规则
  -> 可选的影刀官网验真
  -> 保存 ReviewResult 和烟草报告
  -> 固定地址回调 OA，或由 OA 轮询结果载荷
```

控制台接口使用 Web Console Bearer token 或企业微信 session cookie。OA 专用触发和轮询
使用 `X-OA-Token`。系统只向服务端配置的固定 URL 主动推送结果，不接受请求中提供的任意 URL。

## 2. 查询待处理门店

```text
GET /api/v1/tobacco-license-consistency/pending-stores
```

查询参数：

| 参数 | 默认值 | 约束 | 说明 |
| --- | --- | --- | --- |
| `page` | `1` | `>= 1` | 页码 |
| `page_size` | `20` | `1..100` | 每页数量 |

成功响应：

```json
{
  "stores": [],
  "page": 1,
  "page_size": 20,
  "has_more": false
}
```

OA ecology 源库不可用时返回 HTTP `503` 和 `OA_SOURCE_UNAVAILABLE`，不会静默回退到 demo 数据。

## 3. 创建单门店一致性审核

```text
POST /api/v1/tobacco-license-consistency/reviews
```

请求体：

```json
{
  "store_identifier": "store-code-or-request-id",
  "review_mode": "standard",
  "franchisee_name": "OA 加盟商主体名称",
  "business_license_fields": {},
  "franchisee_business_license_fields": {},
  "tobacco_license_fields": {},
  "store_in_store": {},
  "selected_files": []
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `store_identifier` | 是 | 门店编码、OA request ID 或来源查询支持的其他标识 |
| `review_mode` | 否 | `standard` 或 `store_in_store` |
| `franchisee_name` | 单店是 | OA 加盟商主体名称；不得用门店名称替代 |
| `business_license_fields` | 否 | 人工确认或补充的营业执照字段 |
| `franchisee_business_license_fields` | 店中店否 | 人工确认或补充的加盟店营业执照字段；优先使用附件识别结果 |
| `tobacco_license_fields` | 否 | 人工确认或补充的烟草证字段 |
| `store_in_store` | 否 | 店中店同址证明信息，使用 `same_premises_evidence` |
| `selected_files` | 否 | 前端选择的来源文件信息 |

证照字段优先来自附件识别结果。OA 门店名称只能作为来源上下文，不能代替证照主体字段或
`franchisee_name`。店中店的持证主体营业执照与烟草证核对名称、负责人和地址；加盟店营业执照
不与烟草证核对名称和负责人，只核对材料完整性和同址关系。地址不同写法转人工核验证明。

成功响应包含：

```json
{
  "task_id": "review-task-id",
  "summary": "审核摘要",
  "status": "REVIEWED",
  "risk_level": "NONE",
  "needs_manual_review": false,
  "report": {
    "overall_result": "通过",
    "rule_results": [],
    "source_request_id": "oa-request-id",
    "oa": {}
  }
}
```

一致性规则完成后先形成 OA 预判。只有预判为 `pass`、RPA 能力已启用且抽取到许可证号时，
创建审核才继续执行官网验真并把结果写入同一个 Review Result。预判为 `reject`、
`manual_review` 或 `exception` 时直接返回并跳过 RPA，RPA 技术异常不会覆盖已形成的业务
拒绝原因，也不会被转换成假证结论。

常见错误：

| HTTP | Code | 说明 |
| --- | --- | --- |
| `400` | `STORE_IDENTIFIER_EMPTY` | 门店标识为空 |
| `400` | 来源任务错误码 | 来源记录字段或附件不符合要求 |
| `404` | `SOURCE_RECORD_NOT_FOUND` | 没有找到该门店的来源记录 |
| `500` | `CONSISTENCY_REVIEW_FAILED` | 一致性 Workflow 执行失败 |

## 4. 批量审核

```text
POST /api/v1/tobacco-license-consistency/reviews/batch
```

```json
{
  "store_identifiers": ["store-001", "store-002"]
}
```

一次最多提交 20 个标识。服务去重后逐项执行；单项失败记录在对应 item 中，不中止其他
门店。

```json
{
  "total": 2,
  "completed": 1,
  "failed": 1,
  "items": [
    {
      "store_identifier": "store-001",
      "status": "completed",
      "task_id": "review-task-id",
      "report": {}
    },
    {
      "store_identifier": "store-002",
      "status": "failed",
      "error": {
        "code": "SOURCE_RECORD_NOT_FOUND",
        "message": "未找到该门店的烟草证来源记录"
      }
    }
  ]
}
```

## 5. 人工复核

```text
POST /api/v1/tobacco-license-consistency/reviews/{task_id}/manual-review
```

```json
{
  "decision": "APPROVE",
  "comment": "已核对来源附件"
}
```

`decision` 支持 `APPROVE`、`REJECT` 和 `REQUEST_MORE_INFO`。报告不存在时返回 HTTP `404`
和 `REVIEW_NOT_FOUND`。OA 来源任务人工复核完成后会回调最终人工结论。

超时或回调投递异常时，工作台可在不改变审核结论、不重新执行 OCR/RPA 的前提下重发
当前已持久化结果：

```text
POST /api/v1/tobacco-license-consistency/reviews/{task_id}/oa-callback
```

该接口要求 Web 控制台登录态。非 OA 任务返回 HTTP `422` 和 `OA_IDENTITY_MISSING`；
回调投递失败返回 HTTP `502` 和 `OA_CALLBACK_FAILED`。超时任务重发的仍是
`decision=exception`、`retryable=true`，不会被改写为业务驳回。

## 6. 读取 OA 结果载荷

```text
GET /api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result
```

该接口从结果库读取一致性 Rule Result 和 RPA 验真结果，返回适合 OA adapter 继续映射的
`code / message / data.callback` 数据，要求 `X-OA-Token`。它只读取结果，不主动调用 OA，
也不执行状态流转。

综合语义：

| 条件 | `review_status` | 说明 |
| --- | --- | --- |
| 一致性规则通过且 RPA 通过或未启用 | `通过` | 自动审核正向结果 |
| 一致性规则存在业务不通过 | `不通过` | 返回未通过规则 |
| RPA 为 `FAILED`、`SUSPECTED` 或 `NOT_FOUND` | `不通过` | 官网已形成业务负面结果 |
| RPA 为 `ERROR` | `异常` | 技术执行未可靠完成，应重试或人工处理 |
| 证据不足或 Workflow 要求人工复核 | `待校验` | 不能自动形成最终结论 |

审核结果不存在时返回 HTTP `404` 和 `REVIEW_NOT_FOUND`。

## 7. 前端详情

Web Console 使用以下已实现接口展示烟草报告：

```text
GET /api/tobacco/reports
GET /api/tobacco/reports/{task_id}
```

详情响应包含字段比对、Rule Result、来源证据、人工复核信息和已保存的 RPA 状态。OA 对接方
不应依赖前端投影字段作为长期外部契约；需要回传时读取上一节的 OA 结果载荷。

## 8. 当前边界

- 没有独立的烟草一致性详情 V1 路由；详情由 Web Console 报告接口提供。
- OA 专用入口立即返回 `processing`；领域结果和轮询保持四态，向当前三态 OA 接收端回调 `pass`、`reject` 或 `exception`。自动产生的 `manual_review` 映射为带 `REVIEW_REQUIRES_MANUAL_REVIEW` 的非重试 transport `exception`，并携带 `review_decision=manual_review`、`next_node_review_required=true`，由 OA 进入专用人工审批节点；人工明确要求补件时同样使用非重试 `exception`，但设置 `next_node_review_required=false`。
- OA callback 在兼容期内保留完整 `rule_results`，并为失败规则补充非空 `suggestion`；OA 使用 `reject_reason_text` 或 `manual_review_reason_text` 写入流转意见，并从原因项的 `suggestion` 展示处理建议。
- 后台任务为进程内任务，不是持久化队列；Pod 重启后的结果恢复依赖 `oa-result` 轮询。
