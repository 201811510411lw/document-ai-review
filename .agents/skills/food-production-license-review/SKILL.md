---
name: food-production-license-review
description: 食品生产许可证单证识别与合规审核规则 Skill。用于维护食品生产许可证字段抽取、规则校验、人工复核和结构化输出口径。
---

# food-production-license-review

## 能力边界

用于维护食品生产许可证单证识别与合规审核规则。运行时读取本 Skill，结合 OCR/LLM 抽取字段、供应商主数据和审核日期，输出结构化审核结果。

本 Skill 维护规则内容，不直接调用 OCR、LLM、数据库或外部系统。

## 支持的输入

- `document_type`：识别出的证照类型。
- `extracted_fields` / `normalized_fields`：食品生产许可证字段。
- 来源系统字段：供应商名称、统一社会信用代码。
- 审核日期。

## 字段抽取要求

OCR/LLM 字段抽取只能依据证照图片、PDF 页面或 OCR 文本中的可见文字，不得使用文件名、来源系统字段、上下文、常识或猜测补全；字段无法确认时输出 `null` 或空数组。

- `document_type`：食品生产许可证统一输出 `food_production_license`。
- `document_type_raw`：从证照图片上能直接看到的证照大标题文字，例如"食品生产许可证""食品小作坊登记证"。优先取页面最上方、字号最大的文字。这是必填字段，不要输出 null，如果看到任何类似标题的文字就原样填写。
- `producer_name`：生产者名称、企业名称、主体名称。
- `credit_code`：统一社会信用代码。
- `license_no`：许可证编号，通常以 `SC` 开头。
- `production_address`：住所、生产地址或生产场所。
- `legal_person`：法定代表人、负责人；常见标签为“法定代表人”“负责人”“法定代表人/负责人”。
- `food_categories`：食品类别、品种明细、生产范围。
- `valid_from`：有效期起始日期。
- `valid_to`：有效期截止日期；常见标签为“有效期至”“有效日期至”；长期、未识别到截止日期时按长期有效处理。
- `issue_authority`：发证机关。
- `issue_date`：发证日期、签发日期。
- `ocr_text`：从证照图片上能看到的所有文字内容，按从上到下、从左到右的顺序原样拼接，包括标题、标签、数值和说明文字。这个字段用于提取字段抽取未能覆盖的文字，请完整输出。

字段抽取只输出结构化 JSON，不输出 Markdown。字段包括：

```json
{
  "document_type": "food_production_license",
  "document_type_raw": "",
  "ocr_text": "",
  "producer_name": null,
  "credit_code": null,
  "license_no": null,
  "production_address": null,
  "legal_person": null,
  "food_categories": [],
  "valid_from": null,
  "valid_to": null,
  "issue_authority": null,
  "issue_date": null
}
```

抽取约束：

- `credit_code` 只提取统一社会信用代码；不要把许可证编号、附件 ID、供应商 ID 或业务流水号当成统一社会信用代码。
- `license_no` 提取许可证编号，常见为 `SC` 开头。
- `food_categories` 输出数组。
- 日期字段必须规范为 `YYYY-MM-DD` 后输出，例如 `2023年11月09日` 输出为 `2023-11-09`，`2028年11月08日` 输出为 `2028-11-08`；长期、永久、无固定期限输出 `长期`；无法确定输出 `null`。
- 日期字段比对、规则判断和前台展示均以规范化后的 `YYYY-MM-DD` 为准；同一天的中文日期、斜杠日期和 ISO 日期视为一致，不因格式差异判为不匹配。

## 审核规则

### 证照类型

- `document_type=food_production_license` 时通过。
- 缺失或不是 `food_production_license` 时进入人工复核或判定不通过，风险等级 `HIGH`。

### 生产者名称

- 证照生产者名称需与来源系统供应商名称一致。
- 比对前应忽略空白、全角/半角括号和常见标点差异。
- 生产者名称缺失时进入人工复核。
- 生产者名称明显不一致时判定不通过，风险等级 `MEDIUM`。

### 统一社会信用代码

- 证照统一社会信用代码需与来源系统统一社会信用代码一致。
- 比对前去除空白并统一大小写。
- 缺失、不一致或格式异常时判定不通过，风险等级 `HIGH`。

### 有效期

- 未识别到 `valid_to` 时按长期有效处理，通过，并记录 `assumed_long_term=true`。
- `valid_to` 有值但无法解析时进入人工复核。
- `valid_to` 小于或等于审核日期时判定已过期，风险等级 `HIGH`。
- `valid_to` 距审核日期 30 天内时判定临期，风险等级 `MEDIUM`。
- `valid_to` 距审核日期超过 30 天时通过。

## 输出要求

只输出结构化 JSON：

```json
{
  "status": "REVIEWED | PENDING_MANUAL_REVIEW | FAILED",
  "risk_level": "NONE | LOW | MEDIUM | HIGH",
  "needs_manual_review": false,
  "summary": "食品生产许可证规则校验通过",
  "manual_review_reasons": [],
  "rule_results": [
    {
      "rule_code": "FOOD_PRODUCTION_LICENSE_TYPE_MATCH",
      "rule_name": "证照类型是否为食品生产许可证",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "材料已识别为食品生产许可证。",
      "details": {}
    }
  ]
}
```

## 人工复核边界

- 证照类型无法判断。
- 生产者名称、信用代码等关键字段缺失。
- 有效期有值但无法解析。
- OCR/LLM 证据不足以支持自动通过。
