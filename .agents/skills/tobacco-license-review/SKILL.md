---
name: tobacco-license-review
description: 烟草专卖零售许可证单证识别、来源文件准备与基础合规审核规则 Skill。用于维护烟草证字段抽取、OA/StarRocks 附件来源口径、规则校验、人工复核和结构化输出口径。
---

# tobacco-license-review

## 能力边界

用于维护烟草专卖零售许可证单证识别与基础合规审核规则。当前阶段已支持从 OA 同步到 StarRocks 的来源表查询烟草证附件元数据，并从本地 NAS `/data` 解压文件到项目数据目录供前端预览和下载。

本 Skill 维护规则和口径，不直接调用 OCR、LLM、StarRocks、OA、NAS、国家烟草证平台或前端接口。运行时代码负责读取来源数据、解压文件、执行 OCR/LLM、组装 `ReviewResult`。

当前运行时已支持通过影刀 RPA 发起国家烟草证官网真伪核验；本 Skill 只维护验真编排口径，不直接调用官网或影刀接口。

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

- OA 自动审核必须显式传入正整数 `workflow_id`，来源任务由 `workflow_id + requestid` 精确定位，禁止按门店名称、标题包含或最新记录回退；当前“烟草商品建档申请”流程传 `614`。
- OA 的 `store_code` 只用于与来源记录交叉校验，不作为证照字段或模糊查询依据。
- 两类证照子审核完成且业务字段均一致时可无差异流转；存在少量字段差异时按下述阈值携带明细流转到 OA 下一节点复核。
- 自动一致性审核通常按字段差异数量决定 OA 流转：证据可靠时，`0..2` 项普通字段不匹配由当前机器人节点返回 `pass` 并进入下一节点复核，`>=3` 项时返回 `reject`。字段差异只统计证照类型、许可证号、主体名称、经营地址、负责人和有效期等业务字段；子审核状态、证据完整性等过程规则不计入字段差异数量。烟草证明确已过期属于硬性拒绝条件，即使总差异少于 3 项也返回 `reject`。
- 子审核未形成可靠自动结论、关键字段缺少 OCR 原文证据或候选材料冲突时必须优先返回 `manual_review`，不得使用这些不可靠字段触发差异阈值自动驳回。数据库、NAS、OCR、LLM、持久化或 RPA 技术故障返回 `exception`。官网真伪核验明确失败仍可直接返回 `reject`，不参与字段差异阈值计算。
- 领域结果、持久化和轮询接口保留 `pass`、`reject`、`manual_review`、`exception` 四态；当前 OA 接收端只支持 `pass`、`reject`、`exception` 三态，因此 callback 传输投影将内部 `manual_review` 映射为非重试 `exception`，并使用 `error.code=REVIEW_REQUIRES_MANUAL_REVIEW` 明确表示人工处理，而不是技术故障或业务驳回。该投影必须继续携带 `manual_review_reasons` 和 `manual_review_reason_text`。
- `pass`、`reject` 回调均必须包含 `mismatch_count`、阈值和结构化 `field_differences`，逐项给出字段名、字段中文名、营业执照侧/期望值、烟草证侧/实际值、差异类型和规则信息，供 OA 下一节点展示和复核。`reject` 回调还必须包含决定性 `reject_reasons`、非空 `suggestion` 和可直接写入 OA 流转意见的 `reject_reason_text`。兼容期内 callback 保留完整 `rule_results`，并为其中的失败规则补充非空 `suggestion`；审核结果和轮询详情继续保留原始完整规则。
- OA 重复调用必须按 `workflow_id + requestid` 幂等返回，不重复执行文件下载、OCR 或 RPA。
- OA 触发接口受理后在后台执行审核，最终三态 callback 传输投影必须携带原始 `workflow_id`、`requestid` 和 `store_code`；回调投递失败或三态映射不得改变已经形成并持久化的四态业务审核结论。
- 人工通过的领域结果为 `pass`，摘要必须明确为人工复核通过；人工驳回为 `reject`，必须携带人工填写的驳回原因；要求补件的领域结果必须保持 `manual_review` 并携带补件要求，只允许在 OA 三态 callback 投影中映射为专用、非重试的 `exception`。
- 回调的 HTTP 2xx 只证明传输送达。响应正文明确表示失败时必须记为失败；空响应或无法识别的 2xx 响应必须标记为业务未确认，不得宣称 OA 节点已经推进。
- 每次新回调必须保留可审计记录，包括脱敏后的目标地址、实际请求 JSON、触发来源、尝试次数、HTTP 状态、限长响应正文、业务接受状态、错误和时间；不得保存 Authorization、token、cookie、密码或其他凭据。

一致性审核支持两种互斥模式：

- `standard`：标准门店模式。营业执照与烟草证的主体名称、经营地址、负责人必须一致。
- `store_in_store`：店中店模式。加盟商主体可以与烟草证持证主体不同，必须以“持证主体营业执照 + 加盟/联营/场地授权凭证 + 地址覆盖”组成可追溯证据链。

店中店规则：

- 烟草证主体名称必须与选定的持证主体营业执照主体名称一致；双方均识别到负责人时，负责人必须一致。
- 加盟商营业执照不与烟草证主体直接比较；它仅用于加盟、联营或场地授权材料中的关联主体校验。
- 加盟/联营/场地授权材料必须可识别出加盟商和持证主体，并能关联当前经营门店或烟草证经营地址；缺失或无法识别时进入人工复核。
- 地址默认要求烟草证地址与持证主体营业执照登记地址标准化后一致。一照多址仅在补充材料明确列出烟草证地址且可关联持证主体时通过；不得以地址近似或包含关系自动通过。
- 同一批附件中的其他营业执照可以标记为未采用候选材料，不单独构成失败。存在多个可匹配持证主体、证据冲突或角色无法确定时进入人工复核。

### 官网真伪核验编排

- OA 一致性审核先从烟草证与营业执照附件抽取字段，完成主体、地址、负责人和有效期等确定性一致性校验。
- 一致性审核中的烟草证附件抽取子流程必须设置 `skip_rpa_verification=true`，不得在字段抽取阶段调用官网验真。
- 一致性校验完成后必须先形成 OA 预判；预判为 `reject`、`manual_review` 或 `exception` 时直接返回对应结果并跳过 RPA，保留完整拒绝原因或错误信息。
- 只有一致性预判为 `pass` 且识别到烟草证许可证号时，才由上层一致性审核流程统一发起一次影刀 RPA 官网验真。
- 独立烟草证审核不设置跳过标记时，可以执行其工作流中的官网验真节点。
- 官网验真异常或超时不得被解释为证照不真实；只有明确的未通过、疑似伪造或未查询到结果才进入相应风险处置。

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
- `valid_to` 小于审核日期时判定已过期，风险等级 `HIGH`，OA 自动审核直接返回 `reject`，不受普通字段差异数量阈值限制。
- `valid_to` 距审核日期 0 到 30 天内时判定临期，风险等级 `MEDIUM`。
- `valid_to` 距审核日期超过 30 天时通过。

### 来源文件可用性

- StarRocks 未查到门店烟草证附件记录时，不创建自动审核通过结果。
- StarRocks、审核结果数据库或 NAS 不可用时必须返回真实错误，不得回退到内置 demo 门店、报告或附件。
- `FILEREALPATH` 为空、本地 NAS 文件不存在、zip 无法解压或附件加密时，进入人工复核或返回来源文件准备失败。
- OA zip 内文件无扩展名时，可使用 `imagefile.IMAGEFILENAME` 或 `docimagefile.IMAGEFILENAME` 作为落盘文件名。
- `yyzz` 附件中标题或文件名明确包含“承诺函”的材料属于补充材料，不进入营业执照 OCR 候选或两证字段比对；该预过滤只用于排除明确的非证照材料，不得用文件名推断或补全证照字段。

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
