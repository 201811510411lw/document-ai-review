# food_license MVP 审核流程

当前 MVP 目标是打通食品经营许可证审核流程，不代表完整合规规则已经完成。

## 支持输入

直接 OCR 文本：

```json
{
  "ocr_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000",
  "supplier_name": "成都示例食品有限公司",
  "supplier_credit_code": "91510100MA00000000",
  "declared_document_type": "food_license"
}
```

PDF metadata + stub_text：

```json
{
  "file": {
    "file_uri": "s3://private-bucket/licenses/example.pdf",
    "file_name": "example.pdf",
    "mime_type": "application/pdf",
    "document_format": "pdf",
    "stub_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000"
  },
  "supplier_name": "成都示例食品有限公司",
  "supplier_credit_code": "91510100MA00000000",
  "declared_document_type": "food_license"
}
```

图片 metadata 使用相同结构，`mime_type` 可为 `image/png` 或 `image/jpeg`。

空输入会被 API 稳定拒绝：`ocr_text` 和 `file.stub_text` 不能同时为空，也不能同时传入。

## 输出位置

平台级 `ReviewResult` 顶层结构保持不变。food_license 专属结果放在 `skill_result`：

- `skill_result.document_input`：输入来源摘要。
- `skill_result.document_classification`：文档类型识别结果。
- `skill_result.extracted_fields`：正则优先抽取出的证照字段。
- `skill_result.normalized_fields`：规范化后的字段。
- `skill_result.extraction_metadata`：LLM Stub 是否补字段和 fallback 信息。

## 当前 Stub 限制

- 不解析真实 PDF。
- 不解析真实图片。
- 不接真实 OCR 服务。
- 不接真实 LLM 服务，也不读取真实 API Key。
- LLM Stub 只补缺失字段，不覆盖正则已抽取字段，不决定风险等级。
- 规则链路当前仍执行 `FOOD_LICENSE_RULE_ENGINE_STUB`，只验证通用 `RuleExecutor` 接入。
- SQLite repository 是最小样例，只保存 `ReviewResult` JSON payload，不是生产数据库设计。

后续真实食品经营许可证规则应放在 `app/skills/food_license/rules/`，通用规则基础设施继续保留在 `app/rules/`。
