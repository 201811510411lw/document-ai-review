# OA 烟草证一致性自动审核接口

## 概述

OA 工作流在"烟草商品建档申请"（workflow_id=614）中增加**自动审核节点**，该节点调用本系统 API 进行营业执照与烟草证的一致性自动核对，根据核对结果决定流程走向：

- ✅ **通过** → 流转至下一个法务节点
- ❌ **驳回** → 退回申请人节点，附带原因与修改建议
- ⚠️ **异常** → 标记需人工处理，停留在当前节点

---

## 1. 触发自动审核

```
POST /api/v1/tobacco-license-consistency/oa-auto-review
```

### 请求头

| 字段 | 值 |
|---|---|
| `Content-Type` | `application/json` |
| `X-OA-Token` | `<共享密钥>` |

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `requestid` | integer | 是 | OA 流程请求 ID |
| `store_code` | string | 是 | 门店编码（`mdbm`） |
| `store_name` | string | 否 | 门店名称（`mdmc`） |
| `workflow_id` | integer | 否 | 默认为 614 |
| `callback_url` | string | 否 | 异步模式回调地址（见下文） |

```json
{
  "requestid": 123456,
  "store_code": "STORE001",
  "store_name": "XX便利店",
  "workflow_id": 614
}
```

### 响应

#### ✅ 通过

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "decision": "pass",
    "task_id": "tc-a1b2c3d4e5f6g7h8",
    "summary": "营业执照与烟草证一致性校验通过",
    "rule_results": [
      {
        "rule_code": "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        "rule_name": "主体名称一致",
        "passed": true,
        "message": "主体名称一致通过"
      },
      {
        "rule_code": "BUSINESS_TOBACCO_ADDRESS_MATCH",
        "rule_name": "经营地址一致",
        "passed": true,
        "message": "经营地址一致通过"
      },
      {
        "rule_code": "BUSINESS_TOBACCO_PERSON_MATCH",
        "rule_name": "法定代表人/负责人一致",
        "passed": true,
        "message": "法定代表人/负责人一致通过"
      },
      {
        "rule_code": "BUSINESS_TOBACCO_TOBACCO_VALIDITY",
        "rule_name": "烟草证有效期",
        "passed": true,
        "message": "烟草证在有效期内"
      }
    ]
  }
}
```

OA 工作流收到 `decision: "pass"` 后，将流程推进至法务节点。

#### ❌ 驳回

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "decision": "reject",
    "task_id": "tc-a1b2c3d4e5f6g7h8",
    "summary": "一致性核对未通过，共 2 项问题",
    "reject_reasons": [
      {
        "rule_code": "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        "rule_name": "主体名称一致",
        "message": "营业执照主体名称「XX便利店」与烟草证主体名称「XX便利店（一分店）」不一致",
        "suggestion": "请确认营业执照与烟草专卖零售许可证的主体名称一致；如已完成名称变更，请上传更新后的证照"
      },
      {
        "rule_code": "BUSINESS_TOBACCO_TOBACCO_VALIDITY",
        "rule_name": "烟草证有效期",
        "message": "烟草证有效期至 2026-06-30，已过期",
        "suggestion": "请前往烟草专卖局办理烟草证续期，续期后重新提交申请"
      }
    ],
    "rule_results": [
      { "rule_code": "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH", "rule_name": "主体名称一致", "passed": false },
      { "rule_code": "BUSINESS_TOBACCO_ADDRESS_MATCH",   "rule_name": "经营地址一致", "passed": true },
      { "rule_code": "BUSINESS_TOBACCO_PERSON_MATCH",    "rule_name": "法定代表人/负责人一致", "passed": true },
      { "rule_code": "BUSINESS_TOBACCO_TOBACCO_VALIDITY", "rule_name": "烟草证有效期", "passed": false }
    ]
  }
}
```

OA 工作流收到 `decision: "reject"` 后，将流程退回申请人节点，在审批意见中展示 `reject_reasons` 数组中的 `message` 和 `suggestion`。

#### ⚠️ 异常

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "decision": "exception",
    "task_id": "tc-a1b2c3d4e5f6g7h8",
    "summary": "系统无法自动完成核对，需人工处理",
    "exception": "OCR 识别失败：附件文件无法解析",
    "needs_manual_review": true
  }
}
```

OA 工作流收到 `decision: "exception"` 后，停留在当前节点，标记为需人工处理。

---

## 2. 查询审核结果（OA 回调/轮询）

```
GET /api/v1/tobacco-license-consistency/reviews/{task_id}/oa-result
```

### 请求头

| 字段 | 值 |
|---|---|
| `X-OA-Token` | `<共享密钥>` |

### 响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "callback": {
      "requestid": 123456,
      "review_task_id": "tc-a1b2c3d4e5f6g7h8",
      "review_mode": "standard",
      "review_status": "通过",
      "risk_level": "NONE",
      "needs_manual_review": false,
      "summary": "营业执照与烟草证一致性校验通过",
      "rule_results": [
        { "rule_code": "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH", "rule_name": "主体名称一致", "passed": true },
        { "rule_code": "BUSINESS_TOBACCO_ADDRESS_MATCH", "rule_name": "经营地址一致", "passed": true },
        { "rule_code": "BUSINESS_TOBACCO_PERSON_MATCH", "rule_name": "法定代表人/负责人一致", "passed": true },
        { "rule_code": "BUSINESS_TOBACCO_TOBACCO_VALIDITY", "rule_name": "烟草证有效期", "passed": true }
      ],
      "completed_at": "2026-07-21 14:30:00"
    }
  }
}
```

---

## 3. 详细比对结果（人工复核入口，供前端使用）

```
GET /api/v1/tobacco-license-consistency/reviews/{task_id}/details
```

### 响应

返回字段比对详情、规则明细、OA 附件清单、人工复核状态等完整数据。此接口主要供本系统前端展示使用，结构参考现有 `GET /api/tobacco/reports/{task_id}`。

---

## 规则与解决方案对照

| 规则码 | 规则名称 | 建议解决方案 |
|---|---|---|
| `BUSINESS_TOBACCO_SUBJECT_NAME_MATCH` | 主体名称一致 | 请确认营业执照与烟草专卖零售许可证的主体名称一致；如已变更请上传更新后的证照 |
| `BUSINESS_TOBACCO_ADDRESS_MATCH` | 经营地址一致 | 请确认营业执照登记地址与烟草证经营地址一致；如属**店中店**模式请提供加盟/场地授权协议 |
| `BUSINESS_TOBACCO_PERSON_MATCH` | 法定代表人/负责人一致 | 请确认两证的法定代表人或负责人一致；如已变更请上传更新后的证照 |
| `BUSINESS_TOBACCO_TOBACCO_VALIDITY` | 烟草证有效期 | 烟草证已过期或临近过期，请前往烟草专卖局办理续期 |
| `TYPE_FOR_CONSISTENCY` | 证照类型 | 请确认上传的证照类型正确（营业执照/烟草专卖零售许可证） |

---

## 店中店模式额外规则

| 规则码 | 规则名称 | 建议解决方案 |
|---|---|---|
| `STORE_IN_STORE_HOLDER_NAME_MATCH` | 持证主体名称一致 | 请确认加盟店实际经营者名称与烟草证主体名称一致 |
| `STORE_IN_STORE_HOLDER_PERSON_MATCH` | 持证主体负责人一致 | 请确认加盟店负责人信息与协议一致 |
| `STORE_IN_STORE_RELATIONSHIP_EVIDENCE` | 加盟/联营/场地授权凭证 | 请上传完整的加盟协议、联营合同或场地授权证明，需包含持证方签章 |
| `STORE_IN_STORE_ADDRESS_COVERAGE` | 持证经营地址覆盖 | 请确认烟草证经营地址在持证主体营业执照登记地址或多地址备案范围内 |

---

## 同步模式 vs 异步模式

### 同步模式（推荐）

OA 工作流节点调用 `POST /oa-auto-review`，**同步等待**返回结果（通常 10-30 秒）。本系统在请求超时时间内完成 OCR → LLM 提取 → 一致性比对全部流程，一次性返回 `decision`。

- OA 侧需设置 HTTP 超时 ≥ 60 秒
- 适合首次对接

### 异步模式

如果 OA 无法接受长时间同步等待：

1. OA 调用 `POST /oa-auto-review`，携带 `callback_url`
2. 本系统立即返回 `{ "status": "processing", "task_id": "..." }`
3. 本系统异步完成后，POST 结果到 OA 的 `callback_url`
4. OA 也可轮询 `GET .../oa-result` 获取结果

---

## 对接步骤

1. OA 开发人员在"烟草商品建档申请"流程中新增**自动审核节点**
2. 节点配置 HTTP 调用：`POST https://<本系统域名>/api/v1/tobacco-license-consistency/oa-auto-review`
3. 请求体中传入 `requestid`（OA 流程 ID）和 `store_code`（门店编码）
4. 根据响应的 `decision` 字段路由流程：
   - `pass` → 流转至法务节点
   - `reject` → 退回申请人，审批意见中填入 `reject_reasons`
   - `exception` → 流程挂起，标记需人工处理
5. 本系统运维提供共享密钥 `X-OA-Token`
