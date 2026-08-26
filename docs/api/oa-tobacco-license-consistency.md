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

`requestid`、`store_code` 和正整数 `workflow_id` 均为必填。当前“烟草商品建档申请”流程
传 `614`；接口使用调用方提供的流程 ID 精确查询来源记录。为兼容现有 OA 调用，
`callback_url` 可传空字符串并会被忽略，非空 URL 会被拒绝；接口不接受证照字段。
任务 ID 固定为 `tc-oa-{workflow_id}-{requestid}`。接口受理后立即返回任务身份，审核在后台
执行；重复任务仍由结果库幂等占位保护，不重复执行文件下载、OCR 或 RPA。

并发请求由结果库中的原子任务占位协调。触发响应不包含最终审核决定：

```json
{
  "code": 0,
  "message": "accepted",
  "data": {
    "status": "processing",
    "task_id": "tc-oa-614-584412",
    "workflow_id": 614
  }
}
```

## 结果回调

审核完成后，服务使用 `application/json`、无认证方式向服务端配置的
`oa_auto_review.callback_url` 发起 `POST`。当前 UAT 地址为
`https://oa.lsym.cn:8080/api/bicallback/result`。请求体如下：

```json
{
  "workflow_id": 614,
  "requestid": 584412,
  "store_code": "00001",
  "result": {
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
}
```

网络错误、HTTP 408/429 和 5xx 最多尝试三次。HTTP 2xx 只表示请求已送达；响应 JSON
明确返回失败时，本次回调仍记为失败。空响应或无法识别的响应记为“HTTP 已投递、OA 业务未确认”。
审核详情保存并展示回调目标、实际请求 JSON、尝试次数、HTTP 状态、脱敏且限长的响应正文、
业务接受状态和错误。历史版本未保存的请求正文不会被重建为真实发送记录。
OA 应按 `task_id` 幂等消费可能重复的回调，并根据 `result.data.decision` 执行流程分支。

`decision` 取值：

- `pass`：证据完整，确定性规则通过；OA 流转下一节点。
- `reject`：证据完整且存在明确业务不符合；OA 退回申请人。
- `manual_review`：证据不足、候选冲突或临近到期；OA 停留当前节点等待人工复核。
- `exception`：StarRocks、NAS、OCR、LLM、持久化或 RPA 技术失败；OA 停留当前节点，可根据 `data.error.retryable` 重试。

控制台人工驳回和要求补件必须填写处理说明。人工通过回调使用“人工复核通过”摘要；人工驳回
使用“人工复核驳回”摘要并包含 `MANUAL_REVIEW_REJECTED` 原因；要求补件保持
`decision=manual_review`，不得改写为技术异常。

触发请求已被正常受理时 `code` 为 `0`；鉴权失败返回 HTTP 401，参数校验失败返回
HTTP 422，回调地址未配置返回 HTTP 503。最终 `exception` 作为回调业务结果发送。

## 本地调用样例

仓库提供 OA 调用方模拟脚本，用于在不改动 OA 系统的前提下验证鉴权、触发和轮询契约。
该脚本不会伪造 StarRocks、NAS 或 OCR 数据，需使用真实可用的 OA `requestid` 与门店编码。

```bash
cd ai-service
export OA_AUTO_REVIEW_TOKEN='<shared-secret>'
python scripts/oa_auto_review_smoke_test.py \
  --base-url http://127.0.0.1:8000 \
  --requestid 584412 \
  --store-code 00001 \
  --poll
```

Windows PowerShell 可改为 `$env:OA_AUTO_REVIEW_TOKEN = '<shared-secret>'`。只有触发响应为
`REVIEW_IN_PROGRESS` 时，`--poll` 才会继续请求结果接口。

## 轮询结果

`GET /api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result`

请求头：`X-OA-Token: <shared-secret>`。响应使用相同的
`code / message / data` 包装，最终决策位于 `data.callback.decision`。

## 运维配置

```dotenv
OA_AUTO_REVIEW_TOKEN=<strong-random-secret>
```

```yaml
oa_auto_review:
  callback_url: https://oa.lsym.cn:8080/api/bicallback/result
```

OA 调用地址必须指向实际部署且 OA 网络可达的服务，Pod 也必须能够访问回调地址。
当前后台任务不是持久化队列；Pod 在审核或投递期间重启可能中断回调，此时 OA 使用轮询接口
恢复结果。回调使用明文 HTTP 且没有认证，只应在受控网络中使用。
