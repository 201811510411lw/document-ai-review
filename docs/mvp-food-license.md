# food_license MVP 审核流程

当前 MVP 目标是打通食品经营许可证审核流程，并实现一组基础确定性合规规则。它仍不是完整食品经营许可证审核系统。

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

本地开发 / 测试环境可以传入本地 PDF 路径。`local_path` / `file_path` 只面向本地调试，当前仅允许读取服务当前工作目录或系统临时目录下的 `.pdf` 文件：

```json
{
  "file": {
    "local_path": "/tmp/licenses/example.pdf",
    "file_name": "example.pdf",
    "mime_type": "application/pdf",
    "document_format": "pdf"
  },
  "supplier_name": "成都示例食品有限公司",
  "supplier_credit_code": "91510100MA00000000",
  "declared_document_type": "food_license"
}
```

图片 metadata 使用相同结构，`mime_type` 可为 `image/png` 或 `image/jpeg`。

空输入会被 API 稳定拒绝：`ocr_text`、`file.stub_text` 或 `file.local_path` 至少提供一个。`ocr_text` 和文件输入不能同时传入。

## 输出位置

平台级 `ReviewResult` 顶层结构保持不变。food_license 专属结果放在 `skill_result`：

- `skill_result.document_input`：输入来源摘要。
- `skill_result.document_classification`：文档类型识别结果。
- `skill_result.extracted_fields`：正则优先抽取出的证照字段。
- `skill_result.normalized_fields`：规范化后的字段。
- `skill_result.extraction_metadata`：LLM Stub 是否补字段和 fallback 信息。

`ReviewResult.rule_results` 输出通用规则执行结果，`risk_level` 由 Python `RuleExecutor` 汇总失败规则风险得到，`needs_manual_review` 由规则执行结果和审核路由决定。顶层 `ReviewResult` 结构不变。

## 基础规则

规则实现位于 `ai-service/app/skills/food_license/rules/`，当前规则集版本为 `food-license-rules-v1`。

| 规则编码 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `FOOD_LICENSE_TYPE_MATCH` | `document_classification.document_type` | `passed` / `failed` / `error` | 校验证照类型是否识别为 `food_license`。类型缺失进入人工复核，类型不匹配产生高风险。 |
| `FOOD_LICENSE_SUBJECT_NAME_MATCH` | `normalized_fields.subject_name`、`input.supplier_name` | `passed` / `failed` / `error` | 去除空白后比对主体名称和供应商名称。字段缺失进入人工复核，不一致产生中风险。 |
| `FOOD_LICENSE_CREDIT_CODE_MATCH` | `normalized_fields.credit_code`、`input.supplier_credit_code` | `passed` / `failed` / `error` | 去除空白并转大写后比对统一社会信用代码。字段缺失进入人工复核，不一致产生高风险。 |
| `FOOD_LICENSE_VALIDITY_PERIOD` | `normalized_fields.valid_to`、运行日期 | `passed` / `failed` / `error` | 校验证照有效期截止日期。已过期产生高风险，三十天内到期产生中风险，缺失或无法解析进入人工复核。 |

`FOOD_LICENSE_RULE_ENGINE_STUB` 仍作为规则执行器接入占位通过规则保留，用于验证通用 `RuleExecutor` 链路；合规判断由上述确定性规则完成。

缺字段、无法解析日期或无法判断类型时，规则输出 `error` 状态并触发人工复核。LLM Stub 只能补充缺失字段，不能覆盖正则已抽取字段，也不能直接设置规则结果、最终 `risk_level` 或 `needs_manual_review`。

## PDF 输入与字段补充

PDF metadata + `stub_text` 仍走 Stub Document Loader，不访问真实对象存储或外部文件系统。`local_path` / `file_path` 仅支持本地开发和测试环境下的 PDF 文件，当前只解析 PDF 内嵌文本；扫描件或无内嵌文本的 PDF 会标记 `pdf_loader.needs_ocr=true`，不调用真实 OCR。

字段抽取先使用正则，缺少主体名称、信用代码、许可证编号、经营项目或有效期时才调用 LLM Stub 补字段。补字段只填补正则未抽到的空字段，不能覆盖正则字段，不能输出合规结论。

## 当前限制

- 仅支持本地 PDF 内嵌文本解析；如果 PDF 是扫描件或不含可抽取文本，只标记需要 OCR，不接真实 OCR。
- 不解析真实图片。
- 不接真实 OCR 服务。
- 不接真实 LLM 服务，也不读取真实 API Key。
- LLM Stub 只补缺失字段，不覆盖正则已抽取字段，不决定风险等级。
- 不接公有云、ERP、OA、IM 或其他外部系统。
- 不修改 `ReviewResult` 顶层结构。
- 不包含经营项目覆盖、经营地址相似度、许可证编号必填以外的完整证照合法性规则。
- SQLite repository 是最小样例，只保存 `ReviewResult` JSON payload，不是生产数据库设计。

后续扩展食品经营许可证规则仍应放在 `app/skills/food_license/rules/`，通用规则基础设施继续保留在 `app/rules/`。
