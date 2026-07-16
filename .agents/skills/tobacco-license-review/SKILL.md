---
name: tobacco-license-review
description: 烟草专卖零售许可证单证识别、来源文件准备与基础合规审核规则 Skill。用于维护烟草证字段抽取、OA/StarRocks 附件来源口径、规则校验、人工复核和结构化输出口径。
---

# tobacco-license-review

## 能力边界

用于维护烟草专卖零售许可证单证识别与基础合规审核规则。当前阶段已支持从 OA 同步到 StarRocks 的来源表查询烟草证附件元数据，并从本地 NAS `/data` 解压文件到项目数据目录供前端预览和下载。

本 Skill 维护规则和口径，不直接调用 OCR、LLM、StarRocks、OA、NAS、国家烟草证平台或前端接口。运行时代码负责读取来源数据、解压文件、执行 OCR/LLM、组装 `ReviewResult`。

国家烟草证下载、官网真伪核验和外部平台比对不属于当前阶段。

## 当前来源文件准备口径

来源系统为 OA e-cology，StarRocks ODS 表命名为 `_df` 每日全量快照：

```text
ods_oa_ecology_formtable_main_283_df
ods_oa_ecology_workflow_requestbase_df
ods_oa_ecology_docdetail_df
ods_oa_ecology_docimagefile_df
ods_oa_ecology_imagefile_df
```

烟草证流程：

- `workflow_requestbase.WORKFLOWID = 614`。
- 表单主表为 `formtable_main_283`。
- 烟草证附件 ID 字段为 `formtable_main_283.ycxsxkz`。
- 持证主体营业执照附件 ID 字段已确认是 `formtable_main_283.yyzz`；烟草证与营业执照需按各自字段关联文档链路，并标记材料角色。
- 加盟/联营/场地授权材料、多址证明均来自同一 OA 表单的其他附件字段；当前不预设其技术字段名。日任务启用前，仍必须配置 `tobacco_consistency.oa_relationship_evidence_field` 与 `oa_multi_address_evidence_field`。
- 附件链路：`ycxsxkz -> docdetail.ID -> docimagefile.DOCID/IMAGEFILEID -> imagefile.IMAGEFILEID/FILEREALPATH`。
- OA 文件优先使用本地 NAS 挂载路径 `/data` 读取。
- `ISZIP=1` 时按 zip 解压；`ISENCRYPT=0` 且 `ISAESENCRYPT=0` 时可直接读取。
- 解压后的文件保存到 `ai-service/data/tobacco_license/{store}/{requestid}_{docid}_{imagefile_id}/`。

来源文件准备只负责拿到可预览/下载的证照文件，不代表审核通过。

## 支持的输入

- 证照文件识别结果：`document_classification`、`extracted_fields`、`normalized_fields`。
- OA/StarRocks 来源字段：门店编码、门店名称、流程标题、申请内容、`requestid`、`docid`、`imagefile_id`、`FILEREALPATH`、有效期字段。
- OCR/LLM 原文证据：字段 evidence、OCR 文本片段、页码或图片区域。
- 审核日期。

## 字段抽取要求

OCR/LLM 字段抽取只能依据烟草证图片、PDF 页面或 OCR 文本中的可见文字，不得使用文件名、门店编码、OA 申请内容或来源系统字段猜测补全；无法确认时输出 `null`。

- `document_type`：烟草专卖零售许可证统一输出 `tobacco_license`。
- `document_type_raw`：证照图片上可见的大标题原文，例如“烟草专卖零售许可证”。
- `subject_name`：企业名称、字号名称、经营主体名称。
- `business_address`：经营场所、经营地址。
- `legal_person`：负责人、经营者或法定代表人。
- `license_no`：许可证号、许可证编号。
- `valid_from`：有效期起始日期，规范为 `YYYY-MM-DD`。
- `valid_to`：有效期截止日期，规范为 `YYYY-MM-DD`；无法确认输出 `null`。
- `issue_authority`：发证机关。
- `issue_date`：发证日期、核发日期。
- `ocr_text`：证照图片可见文字，按阅读顺序尽量完整保留。
- `*_evidence`：关键字段的 OCR 原文证据。

不允许因为字段与来源系统不一致就清空识别结果。必须保留 OCR/LLM 识别值，并在规则结果中说明差异。

## 审核规则

### 营业执照与烟草证一致性

一致性审核支持两种互斥模式：

- `standard`：标准门店模式。营业执照与烟草证的主体名称、经营地址、负责人必须一致。
- `store_in_store`：店中店模式。加盟商主体可以与烟草证持证主体不同，必须以“持证主体营业执照 + 加盟/联营/场地授权凭证 + 地址覆盖”组成可追溯证据链。

店中店规则：

- 烟草证主体名称必须与选定的持证主体营业执照主体名称一致；双方均识别到负责人时，负责人必须一致。
- 加盟商营业执照不与烟草证主体直接比较；它仅用于加盟、联营或场地授权材料中的关联主体校验。
- 加盟/联营/场地授权材料必须可识别出加盟商和持证主体，并能关联当前经营门店或烟草证经营地址；缺失或无法识别时进入人工复核。
- 地址默认要求烟草证地址与持证主体营业执照登记地址标准化后一致。一照多址仅在补充材料明确列出烟草证地址且可关联持证主体时通过；不得以地址近似或包含关系自动通过。
- 同一批附件中的其他营业执照可以标记为未采用候选材料，不单独构成失败。存在多个可匹配持证主体、证据冲突或角色无法确定时进入人工复核。

### 证照类型

- `document_type=tobacco_license` 时通过。
- 无法确认是烟草专卖零售许可证时进入人工复核，风险等级 `HIGH`。

### 关键字段完整性

- 必须识别到 `subject_name`、`business_address`、`legal_person`、`license_no`。
- 任一关键字段缺失时进入人工复核，风险等级 `MEDIUM`。
- 有识别值但缺少对应 OCR 原文证据时，不允许自动通过，进入人工复核。

### 有效期

- `valid_to` 未识别到时，当前基础审核按长期有效处理并记录 `assumed_long_term=true`；后续接入外部核验后应重新评估。
- `valid_to` 有值但无法解析时进入人工复核，风险等级 `MEDIUM`。
- `valid_to` 小于审核日期时判定已过期，风险等级 `HIGH`。
- `valid_to` 距审核日期 0 到 30 天内时判定临期，风险等级 `MEDIUM`。
- `valid_to` 距审核日期超过 30 天时通过。

### 来源文件可用性

- StarRocks 未查到门店烟草证附件记录时，不创建自动审核通过结果。
- `FILEREALPATH` 为空、本地 NAS 文件不存在、zip 无法解压或附件加密时，进入人工复核或返回来源文件准备失败。
- OA zip 内文件无扩展名时，可使用 `imagefile.IMAGEFILENAME` 或 `docimagefile.IMAGEFILENAME` 作为落盘文件名。

## 输出要求

LLM 根据本 Skill 执行规则时，只输出结构化 JSON：

```json
{
  "document_type": "tobacco_license",
  "status": "REVIEWED | PENDING_MANUAL_REVIEW | FAILED",
  "risk_level": "NONE | MEDIUM | HIGH",
  "needs_manual_review": false,
  "summary": "烟草证规则校验通过",
  "manual_review_reasons": [],
  "rule_results": [
    {
      "rule_code": "TOBACCO_LICENSE_TYPE_MATCH",
      "rule_name": "烟草证类型匹配",
      "passed": true,
      "risk_level_on_failure": "HIGH",
      "message": "材料已识别为烟草专卖零售许可证",
      "details": {
        "expected": "tobacco_license",
        "actual": "tobacco_license",
        "evidence": "OCR 原文证据"
      }
    }
  ]
}
```

全部规则通过且 `needs_manual_review=false` 时，`risk_level` 必须为 `NONE`。存在字段缺失、证据不足、临期或来源文件异常时，根据规则输出 `MEDIUM` 或 `HIGH`。

## 人工复核边界

- 无法确认文件是烟草专卖零售许可证。
- 主体名称、经营场所、负责人或许可证号缺失。
- 关键字段缺少 OCR 原文证据。
- 有效期无法解析、已过期或临期。
- 来源附件缺失、加密、无法读取或无法解压。
- OCR/LLM 证据不足以支持自动通过。

## 与 Python Runtime 的关系

当前 runtime 入口为 `ai-service/app/use_cases/tobacco_license/use_case.py`，工作流为 `ai-service/app/workflows/tobacco_license/`。现有基础规则代码仍在 workflow 中；后续将 LLM/Skill 规则审核接入烟草证时，应以本 Skill 为业务规则来源。

当前来源文件准备接口为 `POST /api/v1/tobacco-license/source-files/from-starrocks`，实现位于 `ai-service/app/api/tobacco_license_sources.py`、`ai-service/app/integrations/starrocks/tobacco_license_sources.py` 和 `ai-service/app/services/tobacco_license_files.py`。
