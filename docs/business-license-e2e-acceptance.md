# 营业执照单证审核端到端验收说明

本文档说明当前 `business_license` 交付主线的本地端到端验收路径。它补充 `docs/prd-business-license-review-v1.md` 和 `docs/prd-business-license-review-workbench-v1.md`，不替代 `README.md`。

## 验收目标

营业执照单证审核最小闭环必须证明：

1. 业务系统或工作台可以创建一条营业执照审核任务；
2. 系统可以从本地文件、远程文件或 SRM 来源记录取得营业执照文件；
3. workflow 可以完成文档加载、文档类型识别、字段抽取、字段标准化、Skill 规则审核和人工复核路由；
4. use_case 可以输出统一 `ReviewResult`；
5. repository 可以保存完整 payload 和 `business_license_reviews` 投影；
6. 工作台 API 可以查询列表、查看详情并提交轻量人工复核结论。

## 本轮范围

本轮只验收 `business_license` 单证审核。

不验收：

- 烟草证解析；
- 营业执照与烟草证一致性比对；
- QC 文档审核；
- 合同审核；
- 真实 OCR、真实 LLM、OA 回写、企微消息卡片；
- Excel/PDF 导出、字段编辑、重新识别。

## 本地环境

Python 命令优先使用：

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python
```

后端测试目录：

```bash
cd ai-service
```

本地验收默认使用测试内置 fake vision adapter、fake Skill 规则审核 adapter 和 MySQL repository stub，不依赖真实 MySQL、真实 OCR 或真实 LLM。

## 创建审核任务

普通创建接口：

```text
POST /api/v1/business-license/reviews
```

最小输入必须包含：

- `file.local_path` 或 `file.file_uri`；
- `supplier_name`；
- `supplier_credit_code`；
- `declared_document_type=business_license`。

文本输入不是营业执照审核入口。`ocr_text` 或 `file.stub_text` 应返回稳定错误或进入明确人工复核语义，避免绕过文件识别链路。

SRM 来源入口：

```text
POST /api/v1/business-license/reviews/from-srm
```

验收重点：

- SQL 来源记录可以标准化为 `ReviewInput`；
- `record_id`、`attachment_ref_id`、`tenant`、`file_store_key`、原始来源 payload 可以进入 `source_evidence`；
- 远程文件 URL 可以进入 `document_input.source_url` 和投影表 `source_url`。

## 审核结果契约

创建接口返回的 `ReviewResult` 至少需要验证：

- `use_case_name=business_license`；
- `document_type=business_license`；
- `capability_names=["business_license"]`；
- `status` 为 `REVIEWED`、`PENDING_MANUAL_REVIEW` 或 `FAILED` 之一；
- `risk_level` 与失败规则的风险等级一致；
- `needs_manual_review` 与 `manual_review.status` 一致；
- `rule_results` 包含营业执照类型、主体名称、统一社会信用代码等规则结果；
- `skill_result.extracted_fields` 保留原始识别字段；
- `skill_result.normalized_fields` 保留规则审核使用的标准化字段；
- `skill_result.source_evidence` 保留来源追溯信息和 Skill 规则审核 metadata。

## 持久化验收

保存审核结果后，需要验证：

- `review_results` 中保存完整 `ReviewResult` payload；
- `business_license_reviews` 投影表保存列表和详情所需字段；
- 投影表至少包含 `task_id`、`source_record_id`、`source_attachment_ref_id`、`source_url`、`tenant`、`business_name`、`credit_code`、`review_status`、`risk_level`、`needs_manual_review`、`rule_results_json`、`extracted_fields_json`、`normalized_fields_json`、`source_evidence_json`；
- 再次读取 `get_by_task_id(task_id)` 得到的 payload 与保存结果一致；
- `get_business_license_snapshot(task_id)` 可以返回解析后的字段快照和规则快照。

## 工作台 API 验收

列表接口：

```text
GET /api/v1/business-license/reviews
```

支持查询参数：

- `business_name`
- `credit_code`
- `risk_level`
- `review_status`
- `needs_manual_review`
- `created_from`
- `created_to`
- `page`
- `page_size`

响应需包含：

- `items`
- `metrics`
- `page`
- `page_size`
- `total`
- `total_pages`

详情接口：

```text
GET /api/v1/business-license/reviews/{task_id}
```

响应需包含投影字段、解析后的 `rule_results`、`extracted_fields`、`normalized_fields`、`extraction_metadata`、`source_evidence`、人工复核原因和完整 `payload`。

人工复核接口：

```text
POST /api/v1/business-license/reviews/{task_id}/manual-review
```

请求体：

```json
{
  "decision": "approved",
  "comment": "已核对原始营业执照，允许通过。",
  "reviewer_id": "wecom-reviewer-001"
}
```

验收重点：

- `decision` 只接受 `approved` 或 `rejected`；
- `comment` 和 `reviewer_id` 不允许空白；
- 成功后投影表状态更新为 `MANUAL_REVIEWED`；
- 完整 `ReviewResult` payload 同步更新为 `MANUAL_REVIEWED`；
- 写入 `BUSINESS_LICENSE_MANUAL_REVIEW` 审计事件；
- 详情接口可以读取复核结论和审计事件。

## 推荐验证命令

运行 business_license 相关后端测试：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pytest \
  tests/test_business_license_review_api.py \
  tests/test_business_license_persistence.py \
  tests/test_business_license_review_query_api.py \
  tests/test_business_license_use_case.py \
  tests/test_business_license_vision_adapter.py \
  tests/test_business_license_source_tasks.py \
  tests/test_business_license_srm_entrypoint.py \
  tests/test_business_license_extension_boundaries.py \
  tests/test_review_one_srm_business_license_script.py
```

如需确认未影响其他 use_case，可进一步运行：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pytest
```

## 关键异常路径

至少需要覆盖：

- 空文件输入；
- 文本输入；
- 本地文件不存在；
- 文件超过大小限制；
- PDF 页数超过限制；
- 图片像素超过限制；
- 远程文件下载失败；
- 视觉模型未配置；
- 视觉模型调用失败；
- 结构化字段为空；
- 非营业执照文档类型；
- 主体名称缺失或不一致；
- 统一社会信用代码缺失、格式异常或不一致；
- 有效期无法解析、过期或临期。
