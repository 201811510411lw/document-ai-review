---
name: food-license-review
description: 食品经营许可证单证识别与合规审核规则 Skill。用于维护食品经营许可证字段抽取、规则校验、人工复核和结构化输出口径。
---

# food-license-review

## 能力边界

用于维护食品经营许可证单证识别与合规审核规则。运行时读取本 Skill，结合 OCR/LLM 抽取字段、供应商主数据和审核日期，由大模型输出结构化审核结果。

本 Skill 维护规则内容，不直接调用 OCR、LLM、数据库或外部系统。

## 支持的输入

- `document_type`：识别出的证照类型。
- `extracted_fields` / `normalized_fields`：食品经营许可证字段。
- 来源系统字段：供应商名称、统一社会信用代码。
- 审核日期。

## 字段抽取要求

- `document_type`：食品经营许可证统一输出 `food_license`。
- `subject_name`：经营者名称、主体名称。
- `credit_code`：统一社会信用代码。
- `license_no`：许可证编号。
- `business_address`：经营场所。
- `legal_person`：法定代表人、负责人或经营者。
- `business_items`：经营项目。
- `valid_from`：有效期起始日期。
- `valid_to`：有效期截止日期；未识别到时按长期有效处理。
- `issue_authority`：发证机关。
- `issue_date`：签发日期。

## 审核规则

### 证照类型

- `document_type=food_license` 时通过。
- 缺失或不是 `food_license` 时进入人工复核或判定不通过。

### 主体名称

- 证照主体名称需与来源系统供应商名称一致。
- 比对前应忽略空白、全角/半角括号和常见标点差异。
- 主体名称缺失时进入人工复核。
- 主体名称明显不一致时判定不通过，风险等级 `MEDIUM`。

### 统一社会信用代码

- 证照统一社会信用代码需与来源系统统一社会信用代码一致。
- 比对前去除空白并统一大小写。
- 缺失、不一致或格式异常时判定不通过，风险等级 `HIGH`。

### 有效期

- 未识别到 `valid_to` 时按长期有效处理，通过，并记录 `assumed_long_term=true`。
- `valid_to` 有值但无法解析时进入人工复核。
- `valid_to` 小于审核日期时判定已过期，风险等级 `HIGH`。
- `valid_to` 距审核日期 30 天内时判定临期，风险等级 `MEDIUM`。
- `valid_to` 距审核日期超过 30 天时通过。

## 输出要求

只输出结构化 JSON：

```json
{
  "status": "REVIEWED | PENDING_MANUAL_REVIEW | FAILED",
  "risk_level": "NONE | LOW | MEDIUM | HIGH",
  "needs_manual_review": false,
  "summary": "食品经营许可证规则校验通过",
  "manual_review_reasons": [],
  "rule_results": [
    {
      "rule_code": "FOOD_LICENSE_TYPE_MATCH",
      "rule_name": "证照类型是否为食品经营许可证",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "材料已识别为食品经营许可证。",
      "details": {}
    }
  ]
}
```

## 人工复核边界

- 证照类型无法判断。
- 主体名称、信用代码等关键字段缺失。
- 有效期有值但无法解析。
- OCR/LLM 证据不足以支持自动通过。
