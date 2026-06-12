---
name: business-license-review
description: 营业执照单证识别与合规审核规则 Skill。用于维护营业执照字段抽取、规则校验、人工复核和结构化输出口径。
---

# business-license-review

## 能力边界

用于维护营业执照单证识别与合规审核的业务规则口径。运行时可将本 Skill 作为规则文本来源，结合 OCR/LLM 抽取字段、SRM/MySQL 来源字段和人工复核上下文，生成结构化审核判断。

本 Skill 维护规则内容，不直接执行规则，不直接调用 OCR、LLM、MySQL、OA、ERP 或 IM。运行时代码负责读取本 Skill、构造提示词、约束结构化输出、保存 `ReviewResult`。

## 支持的输入

- 证照文件识别结果：`extracted_fields`。
- 来源系统字段：供应商名称、统一社会信用代码、声明证照类型、文件来源。
- OCR 原文证据：字段 evidence、OCR 文本片段、页码。
- 审核日期。

## 字段抽取要求

营业执照识别应尽量抽取：

- `document_type`：证照类型，营业执照统一输出 `business_license`。
- `subject_name`：名称、企业名称或主体名称。
- `credit_code`：统一社会信用代码。
- `business_address`：住所或经营场所。
- `legal_person`：法定代表人、经营者或负责人。
- `established_date`：成立日期。
- `valid_from`：营业期限开始日期。
- `valid_to`：营业期限截止日期；长期、永久、无固定期限可输出 `长期`，无法标准化时保留原始证据。
- `issue_authority`：登记机关。
- `issue_date`：发照日期或登记日期。
- `*_evidence`：关键字段的 OCR 原文证据。

不允许因为字段与来源系统不一致就清空识别结果。必须保留 OCR/LLM 识别值，并在规则结果中说明差异。

## 审核规则

### 证照类型

- 若 `document_type` 为 `business_license`，通过。
- 若无法确认是营业执照，判定不通过，需要人工复核。

### 主体名称

- 将来源系统供应商名称与证照识别主体名称进行比对。
- 完全一致，通过。
- 仅存在空白、全角/半角括号、常见中英文标点差异时，视为一致。
- 若核心字号和组织形式一致，但 OCR 存在轻微粘连、断行或标点噪声，可判定通过，并记录说明。
- 若证照识别主体名称缺失，进入人工复核，原因输出“主体名称缺失”。
- 若主体名称明显不一致，判定不通过，保留 `expected`、`actual` 和 OCR 证据。

### 统一社会信用代码

- 将来源系统统一社会信用代码与证照识别统一社会信用代码进行比对。
- 比对前去除空白并统一大小写。
- 一致且长度为 15 或 18 位，通过。
- 缺失、格式异常或不一致，判定不通过；其中不一致或格式异常为高风险。
- 不允许清空识别出的 `credit_code`，即使它与来源系统不一致。

### 有效期

- 若 `valid_to` 为 `长期`、永久、无固定期限，视为长期有效，通过。
- 若没有识别到 `valid_to`，按长期有效处理，通过，并记录 `assumed_long_term=true`。
- 若 `valid_to` 可解析为日期：
  - 截止日期小于审核日期，判定已过期，高风险。
  - 截止日期距审核日期 30 天内，判定临期，需要人工复核。
  - 截止日期超过 30 天，通过。
- 若 `valid_to` 有值但无法解析，进入人工复核，原因输出“有效期无法判断”。

### 关键字段完整性

- 必须具备 `subject_name` 和 `credit_code`。
- `valid_to` 不作为必填字段，因为未识别到有效期时按长期有效处理。
- 关键字段缺失时进入人工复核。

## 输出要求

LLM 根据本 Skill 执行规则时，必须输出结构化 JSON。

状态和风险等级必须同时提供 runtime 字段和中文展示字段：

- `status`：runtime 状态码，固定使用英文枚举，供系统持久化和程序判断。
- `status_label`：中文状态展示值，面向人工查看。
- `risk_level`：runtime 风险等级码，固定使用英文枚举，供系统持久化和程序判断。
- `risk_level_label`：中文风险等级展示值，面向人工查看。

状态码定义：

- `CREATED`：已创建。
- `RUNNING`：审核中。
- `REVIEWED`：已审核。
- `PENDING_MANUAL_REVIEW`：待人工复核。
- `MANUAL_REVIEWED`：人工已复核。
- `FAILED`：审核失败。

风险等级定义：

- `NONE`：无风险。
- `LOW`：低风险。
- `MEDIUM`：中风险。
- `HIGH`：高风险。

注意：不要把 `status` 或 `risk_level` 直接输出为中文；中文值必须放在 `status_label` 和 `risk_level_label`。若面向用户展示，应展示中文字段。

```json
{
  "document_type": "business_license",
  "status": "REVIEWED",
  "status_label": "已审核",
  "risk_level": "LOW",
  "risk_level_label": "低风险",
  "needs_manual_review": false,
  "summary": "营业执照规则校验通过",
  "rule_results": [
    {
      "rule_code": "BUSINESS_LICENSE_SUBJECT_NAME_MATCH",
      "rule_name": "营业执照主体名称匹配",
      "passed": true,
      "risk_level_on_failure": "MEDIUM",
      "message": "主体名称一致",
      "details": {
        "field": "subject_name",
        "expected": "来源系统供应商名称",
        "actual": "证照识别主体名称",
        "evidence": "OCR 原文证据"
      }
    }
  ],
  "manual_review": {
    "status": "NOT_REQUIRED | PENDING",
    "reasons": []
  }
}
```

## 人工复核边界

以下情况应进入人工复核：

- 无法确认文件是营业执照。
- 主体名称缺失或明显不一致。
- 统一社会信用代码缺失、格式异常或不一致。
- 有效期有值但无法解析。
- OCR/LLM 证据不足以支持自动通过。

## 与 Python Runtime 的关系

当前 runtime 入口为 `ai-service/app/use_cases/business_license/use_case.py`，工作流为 `ai-service/app/workflows/business_license/`。

Python Runtime 读取本 Skill 作为规则文本来源，并用结构化输出约束 LLM 审核结果。Python 只负责流程编排、Skill 加载、模型调用、JSON 解析和 `ReviewResult` 组装，不维护营业执照业务规则。
