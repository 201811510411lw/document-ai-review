# OA 烟草证一致性自动审核接口

## 触发审核

`POST /api/v1/tobacco-license-consistency/oa-auto-review`

请求头：`Content-Type: application/json`、`X-OA-Token: <shared-secret>`。

```json
{
  "requestid": 584412,
  "store_code": "00001",
  "store_name": "示例门店",
  "workflow_id": 614
}
```

`requestid` 和 `store_code` 必填，`workflow_id` 只能为 `614`。为兼容现有 OA 调用，
`callback_url` 可传空字符串并会被忽略，非空 URL 会被拒绝；接口不接受证照字段。
任务 ID 固定为 `tc-oa-614-{requestid}`，重复请求返回
已持久化结果，不重复执行审核。

并发请求由结果库中的原子任务占位协调。审核尚未完成时返回
`exception` 和 `REVIEW_IN_PROGRESS`，OA 应稍后轮询，不能据此推进流程。

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "decision": "pass",
    "task_id": "tc-oa-614-584412",
    "summary": "营业执照与烟草证一致性校验通过",
    "rule_results": [],
    "needs_manual_review": false
  }
}
```

`decision` 取值：

- `pass`：证据完整，确定性规则通过；OA 流转下一节点。
- `reject`：证据完整且存在明确业务不符合；OA 退回申请人。
- `manual_review`：证据不足、候选冲突或临近到期；OA 停留当前节点等待人工复核。
- `exception`：StarRocks、NAS、OCR、LLM、持久化或 RPA 技术失败；OA 停留当前节点，可根据 `data.error.retryable` 重试。

HTTP 请求已被正常处理时 `code` 为 `0`；鉴权失败返回 HTTP 401，参数校验失败返回
HTTP 422。`exception` 仍使用 HTTP 200，避免 OA 将业务分支误当成传输失败。

## 轮询结果

`GET /api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result`

请求头：`X-OA-Token: <shared-secret>`。响应使用相同的
`code / message / data` 包装，最终决策位于 `data.callback.decision`。

## 运维配置

```dotenv
OA_AUTO_REVIEW_TOKEN=<strong-random-secret>
```

OA 调用地址必须指向实际部署且 OA 网络可达的服务。连接超时发生在 HTTP 建连阶段，
与请求 JSON 或审核规则无关；应从 OA 服务器验证域名解析、目标端口、防火墙、反向代理
和服务监听状态。首次同步对接建议 OA 读取超时不少于 60 秒。
