# OA 烟草证一致性审核接口（现行）

本文档说明当前已经实现的 OA 来源烟草证一致性审核链路。文件名保留历史链接，但正文只描述
FastAPI 当前可调用的接口；未来的 OA 专用自动节点或主动 callback 不属于现行契约。

## 1. 当前链路

```text
OA 来源记录同步到 StarRocks
  -> 查询待处理门店
  -> 获取营业执照和烟草证附件
  -> 文档识别与字段抽取
  -> 确定性一致性规则
  -> 可选的影刀官网验真
  -> 保存 ReviewResult 和烟草报告
  -> Web Console 人工复核或读取 OA 结果载荷
```

当前接口使用 Web Console Bearer token 或企业微信 session cookie。系统尚未实现独立的
`X-OA-Token` 认证入口，也不会向请求中提供的任意 URL 主动推送结果。

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

StarRocks 不可用时返回 HTTP `503` 和 `STARROCKS_UNAVAILABLE`，不会静默回退到 demo 数据。

## 3. 创建单门店一致性审核

```text
POST /api/v1/tobacco-license-consistency/reviews
```

请求体：

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

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `store_identifier` | 是 | 门店编码、OA request ID 或来源查询支持的其他标识 |
| `review_mode` | 否 | `standard` 或 `store_in_store` |
| `business_license_fields` | 否 | 人工确认或补充的营业执照字段 |
| `tobacco_license_fields` | 否 | 人工确认或补充的烟草证字段 |
| `store_in_store` | 否 | 店中店模式的关系和证明信息 |
| `selected_files` | 否 | 前端选择的来源文件信息 |

证照字段优先来自附件识别结果。OA 门店名称只能作为来源上下文，不能代替证照主体字段。

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

当 RPA 能力已启用且抽取到许可证号时，创建审核会继续执行官网验真并把结果写入同一个
Review Result。RPA 技术异常不会被转换成假证结论。

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
和 `REVIEW_NOT_FOUND`。

## 6. 读取 OA 结果载荷

```text
GET /api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result
```

该接口从结果库读取一致性 Rule Result 和 RPA 验真结果，返回适合 OA adapter 继续映射的
`callback` 数据。它只读取结果，不主动调用 OA，也不执行状态流转。

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

## 8. 当前未实现

- 没有 OA 专用的“一次调用后按 pass/reject/exception 自动推进流程”入口。
- 没有独立的烟草一致性详情 V1 路由；详情由 Web Console 报告接口提供。
- 没有接收 `callback_url` 后异步主动推送 OA 的后台任务。
- 没有 `X-OA-Token` 鉴权实现。

需要上述能力时，应先新增明确需求、路由、认证、持久化和回归测试，再更新本文档。
