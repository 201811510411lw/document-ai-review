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
      "mismatch_count": 0,
      "mismatch_rejection_threshold": 3,
      "field_differences": [],
      "next_node_review_required": false,
      "rule_results": [
        {
          "rule_code": "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
          "rule_name": "主体名称一致",
          "passed": true,
          "risk_level_on_failure": "MEDIUM",
          "message": "主体名称一致通过",
          "details": {
            "field": "subject_name",
            "expected": "成都示例商贸有限公司",
            "actual": "成都示例商贸有限公司",
            "difference": null,
            "evidence": {
              "expected_source": "business_license",
              "actual_source": "tobacco_license"
            }
          }
        },
        {
          "rule_code": "BUSINESS_TOBACCO_ADDRESS_MATCH",
          "rule_name": "经营地址一致",
          "passed": true,
          "risk_level_on_failure": "MEDIUM",
          "message": "经营地址一致通过",
          "details": {
            "field": "business_address",
            "expected": "成都市高新区示例路1号",
            "actual": "成都市高新区示例路1号",
            "difference": null,
            "evidence": {
              "expected_source": "business_license",
              "actual_source": "tobacco_license"
            }
          }
        },
        {
          "rule_code": "BUSINESS_TOBACCO_PERSON_MATCH",
          "rule_name": "法定代表人/负责人一致",
          "passed": true,
          "risk_level_on_failure": "MEDIUM",
          "message": "法定代表人/负责人一致通过",
          "details": {
            "field": "legal_person",
            "expected": "张三",
            "actual": "张三",
            "difference": null,
            "evidence": {
              "expected_source": "business_license",
              "actual_source": "tobacco_license"
            }
          }
        },
        {
          "rule_code": "BUSINESS_TOBACCO_TOBACCO_VALIDITY",
          "rule_name": "烟草证有效期",
          "passed": true,
          "risk_level_on_failure": "HIGH",
          "message": "烟草证在有效期内",
          "details": {
            "field": "valid_to",
            "expected": "not_expired",
            "actual": "2028-12-31",
            "difference": null,
            "days_until_expiry": 852,
            "evidence": {
              "actual_source": "tobacco_license"
            }
          }
        }
      ],
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
`rule_results` 保留完整规则执行结果。每项至少包含规则编码、规则名称、是否通过、失败风险、
结果说明和 `details`；字段比对规则的 `details` 同时包含营业执照侧 `expected`、烟草证侧
`actual`、`difference` 及证据来源，OA 可直接逐项展示，不需要根据摘要反推审核过程。

字段差异阈值为 3。`0..2` 项普通字段不匹配时当前机器人节点仍返回 `pass`，由 OA
流转到下一节点复核；达到 3 项时返回 `reject`。烟草证明确已过期属于硬性拒绝条件，
即使总差异少于 3 项也返回 `reject`。证照类型、许可证号、主体名称、经营地址、
负责人和有效期纳入字段差异计数，过程状态和证据完整性规则不计数。`field_differences`
逐项提供 `field`、`field_label`、`expected`、`actual`、`difference`、`rule_code`、
`rule_name` 和 `message`，放行与驳回回调都会携带该列表。

一致性规则完成后先形成 OA 预判。预判为 `reject`、`manual_review` 或 `exception` 时立即
保存并回调，不调用 RPA；只有预判为 `pass` 且已识别许可证号时才执行官网验真。因此字段
差异达到拒绝阈值时，RPA 技术异常不会覆盖已经形成的 `reject_reasons`。

`decision` 取值：

- `pass`：没有字段差异，或字段差异少于 3 项；OA 流转下一节点。存在差异时
  `next_node_review_required=true`，下一节点根据 `field_differences` 复核。
- `reject`：字段差异达到 3 项、烟草证明确已过期，或官网真伪核验明确失败；OA 退回申请人。
  自动拒绝摘要使用“`一致性核对未通过，共 N 项问题`”，`reject_reasons` 逐项保留
  `rule_code`、`rule_name`、`message` 和完整 `details`。
- `manual_review`：人工明确要求补件或需要停留当前节点的处置结果；OA 停留当前节点等待处理。
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
