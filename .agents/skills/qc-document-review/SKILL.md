---
name: qc-document-review
description: QC 证照、产品报告、批次报告和第三方检验报告审核规则 Skill。用于维护 QC 文档字段抽取、规则校验、人工复核和结构化输出口径。
---

# qc-document-review

## 能力边界

用于维护 QC 文档审核规则。当前 runtime 支持 `product_report` 产品检验报告审核和 `batch_report` 商品批次报告审核；后续可扩展供应商证照和更多第三方检验报告版式。

本 Skill 维护规则内容，不直接调用 OCR、LLM、ERP、OA、IM 或数据库。

## 支持的输入

- `declared_document_type`：来源系统声明文档类型。
- `extracted_fields`：产品报告字段抽取结果。
- 来源系统字段：供应商名称、商品名、批次或生产日期。
- OCR 文本证据和抽取 metadata。

## batch_report 字段抽取要求

- `document_type`：商品批次报告统一输出 `batch_report`。
- `producer_name` / `company_name`：厂名、公司名、生产商、生产单位或生产企业。
- `product_name`：产品名称、商品名称或品名。
- `batch_no`：生产批号、批号、批次号或批次。
- `production_date`：生产日期、生产时间或制造日期，统一为 `YYYY-MM-DD`。

## batch_report 审核规则

### 0. 文档文本完整性

- 规则编码: `BATCH_REPORT_TEXT_PRESENT`
- 核对项: 是否成功获取到 PDF 文本内容（`has_document_text`）。
- 文本为空时进入人工复核，风险等级 `MEDIUM`。

### 1. 文档类型匹配

- 规则编码: `BATCH_REPORT_TYPE_MATCH`
- 核对项: `declared_document_type` 是否为 `batch_report`。
- 不匹配时判定不通过，风险等级 `HIGH`。

### 2. 商品名称匹配（语义比对）

- 规则编码: `BATCH_REPORT_PRODUCT_NAME_MATCH`
- 核对项: 报告中的 `product_name` 与来源系统 `sku_name`。
- **LLM 需语义比对**：
  - 剔除品牌名、规格包装（如"500g"、"1L"、"xx牌"）后做核心名匹配。
  - "火锅底料（麻辣）" ≈ "火锅底料" ✓
  - "纯牛奶（全脂）250ml" ≈ "纯牛奶" ✓
  - "农心辛拉面" ≠ "辛拉面" ❌（不同品牌层级需业务判断）
  - "可口可乐330ml" ≈ "可口可乐" ✓（规格不同但品名一致，标注规格差异）
- 缺失或明显不匹配时进入人工复核，风险等级 `MEDIUM`。
- **输出要求**：details 中附带 `match_reason`（说明匹配依据或差异详情）和 `confidence`（HIGH / MEDIUM / LOW）。

### 3. 生产者名称匹配（语义比对）

- 规则编码: `BATCH_REPORT_PRODUCER_NAME_MATCH`
- 核对项: 报告中的 `producer_name`/`company_name` 与来源系统 `supplier_name`/`vendor_name`。
- **LLM 需语义比对**：
  - "XX食品有限公司" ≈ "XX食品股份有限公司"（核心实体一致）
  - "四川XX食品有限公司" ≈ "XX食品有限公司"（省名省略属常见变体，视为匹配）
  - 支持简称匹配："蒙牛" ≈ "内蒙古蒙牛乳业（集团）股份有限公司"
  - 注意区分**生产商**和**供应商**：若报告厂名匹配系统生产商而非直接供应商，标注为"生产商名称一致（非供应商）"，仍视为匹配。
- 缺失或明显不匹配时进入人工复核，风险等级 `MEDIUM`。
- **输出要求**：details 中附带 `match_reason`（说明匹配逻辑，如"核心实体名一致，'有限公司'vs'股份有限公司'属同一实体"）和 `confidence`。

### 4. 生产日期或批号匹配

- 规则编码: `BATCH_REPORT_PRODUCTION_DATE_MATCH`
- 核对项: 报告的 `production_date` 或 `batch_no` 与来源系统批次明细的 `production_date`。
- 优先用 `production_date` 做日期精确比对。
- 若报告只有 `batch_no`，检查批号中是否嵌入 `YYYYMMDD` 格式的来源生产日期。
- 缺失且无替代证据时进入人工复核，风险等级 `MEDIUM`。
- **输出要求**：details 中附带 `match_reason`（如"批次号20260615包含生产日期2026-06-15"）。

### 5. 生产日期时效性检查

- 规则编码: `BATCH_REPORT_EXPIRY_CHECK`
- 核对项: 当系统提供了 `expired_time`（到期/过期时间）时，判断报告生产日期对应的产品是否仍在保质期内。
  - 已过期（当前日期 > expired_time）→ 不通过，风险等级 `HIGH`。
  - 临期（expired_time - 当前日期 ≤ 30天）→ 进入人工复核，风险等级 `MEDIUM`。
  - 正常（expired_time - 当前日期 > 30天）→ 通过。
  - 若系统未提供 expired_time 则跳过此规则（视为通过）。
- 此规则要求 `extracted_fields` 中有 `production_date` 或 `batch_no` 作为辅助参照。

### 6. 关键字段完整性

- 规则编码: `BATCH_REPORT_KEY_FIELD_INTEGRITY`
- 核对项: `product_name`、`producer_name`、`production_date` 三个关键字段是否至少识别到 2 个。
- 缺失 ≥2 个关键字段时进入人工复核，风险等级 `MEDIUM`。

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
  "summary": "产品检验报告 / 商品批次报告规则校验通过",
  "manual_review_reasons": [],
  "rule_results": [
    {
      "rule_code": "PRODUCT_REPORT_CONCLUSION_PASS",
      "rule_name": "结论正向/负向/不明确",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "检验结论为正向",
      "details": {
        "expected": "XXX",
        "actual": "XXX"
      }
    }
  ]
}
```

### batch_report 输出的特殊要求

batch_report 的每条 rule_result 的 details 中必须包含：

- `expected` — 来源系统的期望值（如 sku_name、supplier_name、production_date）。
- `actual` — 报告中的识别值（如提取的 product_name、producer_name）。
- `match_reason` — **字符串，用业务语言说明匹配/不匹配的依据**。举例：
  - "核心实体名'海底捞'一致，'四川'省名省略属常见变体"
  - "产品名'纯牛奶250ml'剔除规格后核心名'纯牛奶'与 sku_name 一致"
  - "报告生产日期2026-06-15与批次明细日期2026-06-15完全一致"
  - "批号'20260615ABC'中包含生产日期20260615日期串"
  - "厂名'宏源食品厂'与供应商'四川宏源食品有限公司'核心实体一致"
- `confidence` — 审核置信度：`HIGH | MEDIUM | LOW`。
  - `HIGH`: 字段值清晰匹配，无需人工确认。
  - `MEDIUM`: 存在合理的不确定性（如简称匹配、省略部分信息），建议人工快速确认。
  - `LOW`: 匹配依据较弱，强烈建议人工复核。

### 状态判定逻辑汇总

- **FAILED**：存在任意风险等级为 `HIGH` 且未通过的规则。example: 类型不匹配、已过期。
- **PENDING_MANUAL_REVIEW**：存在未通过的规则，但风险等级均为 `MEDIUM` 或 `LOW`。或者跳过此规则（比如无 expired_time 数据）。
- **REVIEWED**：全部规则通过，无需人工介入。

## 人工复核边界

- 文档类型不匹配。
- 供应商名称、产品名称、批次/生产日期缺失。
- 检验结论缺失、不明确或为负向。
- OCR/LLM 证据不足以支持自动通过。
- 商品批次报告附件无法获取可审核文本。
- 商品批次报告商品名、厂名匹配置信度为 `LOW`。
- 商品批次报告生产日期临期（到期前 ≤30 天）。
