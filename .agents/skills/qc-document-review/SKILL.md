---
name: qc-document-review
description: QC 证照、产品报告、批次报告和第三方检验报告审核规则 Skill。用于维护 QC 文档字段抽取、规则校验、人工复核和结构化输出口径。
---

# qc-document-review

## 能力边界

用于维护 QC 文档审核规则。当前 runtime 首期支持 `product_report` 产品检验报告审核；后续可扩展供应商证照、批次报告和第三方检验报告。

本 Skill 维护规则内容，不直接调用 OCR、LLM、ERP、OA、IM 或数据库。

## 支持的输入

- `declared_document_type`：来源系统声明文档类型。
- `extracted_fields`：产品报告字段抽取结果。
- 来源系统字段：供应商名称、商品名、批次或生产日期。
- OCR 文本证据和抽取 metadata。

## product_report 字段抽取要求

- `document_type`：产品检验报告统一输出 `product_report`。
- `report_no`：报告编号。
- `product_name` / `sample_name`：产品名称或样品名称。
- `vendor_name_extracted` / `entrusting_party` / `manufacturer_name`：供应商、委托单位或生产单位。
- `batch_no`：批次号。
- `production_date`：生产日期。
- `issue_date` / `sign_date` / `approval_date`：签发日期、签署日期或批准日期。
- `valid_to`：报告有效截止日，按签发日期/批准日期加 180 天计算。
- `inspection_conclusion` / `inspection_result`：检验结论。
- `inspection_items`：检测项目和结果。

### 常见版式兼容

- 支持冒号版式：`报告编号：A226...`、`样品名称：xxx`、`批准日期：2026 年 06 月 29 日`。
- 支持表格版式：`生产日期 2026/6/20 样品状态 完好`、`样品批号 / 样品规格 /`、`生产商 xxx`。
- 日期格式需兼容 `YYYY年MM月DD日`、`YYYY-MM-DD`、`YYYY.MM.DD`、`YYYY/M/D`。
- `样品批号 /`、`批号 /`、`批次 /` 表示报告未提供批号，不应把 `/` 当作有效批号。
- 第三方检测报告可能将标题拆成竖排文本，例如 `检 / 测 / 结 / 论`，结论正文为后续的 `经检测，所检项目符合...要求。`，应抽取为 `inspection_conclusion`。
- 检测项目抽取只取“检测结果”表格中的项目行；报告声明、备注、查询说明等编号条款不应作为检测项目。

## product_report 审核规则

### 文档类型

- `declared_document_type=product_report` 且识别为产品报告时通过。
- 类型不匹配时判定不通过，风险等级 `HIGH`。

### 供应商名称

- 识别出的供应商、委托单位或生产单位需与来源系统供应商名称一致。
- 比对前忽略空白、全角/半角括号和常见标点差异。
- 缺失时进入人工复核。
- 明显不一致时判定不通过，风险等级 `MEDIUM`。

### 产品名称

- 必须识别到产品名称或样品名称。
- 与来源系统商品名称比对时，允许剔除品牌名、规格包装、空白和常见标点后做模糊匹配。
- 缺失或明显不匹配时进入人工复核，风险等级 `MEDIUM`。

### 报告有效期

- 优先使用 `issue_date`、`approval_date` 或 `sign_date` 计算有效期。
- `valid_to = 签发日期/批准日期 + 180 天`。
- `valid_to` 早于核验当天日期时判定不通过，风险等级 `HIGH`。
- `valid_to` 与核验当天日期相差 0 到 30 天时进入人工复核，风险等级 `MEDIUM`。
- `valid_to` 晚于核验当天日期 30 天以上时通过。
- 签发日期、批准日期和签署日期均缺失时进入人工复核，风险等级 `MEDIUM`。

### 批次或生产日期

- 必须识别到批次号或生产日期。
- 二者均缺失时进入人工复核，风险等级 `MEDIUM`。

### 检验结论

- 结论包含“不合格”“不通过”“不符合”时判定不通过，风险等级 `HIGH`。
- 结论包含“合格”“通过”“符合”时通过。
- 结论缺失或不明确时进入人工复核，风险等级 `MEDIUM`。

## 输出要求

只输出结构化 JSON：

```json
{
  "status": "REVIEWED | PENDING_MANUAL_REVIEW | FAILED",
  "risk_level": "NONE | LOW | MEDIUM | HIGH",
  "needs_manual_review": false,
  "summary": "产品检验报告规则校验通过",
  "manual_review_reasons": [],
  "rule_results": [
    {
      "rule_code": "PRODUCT_REPORT_CONCLUSION_PASS",
      "rule_name": "结论正向/负向/不明确",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "检验结论为正向",
      "details": {}
    }
  ]
}
```

## 人工复核边界

- 文档类型不匹配。
- 供应商名称、产品名称、批次/生产日期缺失。
- 检验结论缺失、不明确或为负向。
- OCR/LLM 证据不足以支持自动通过。
