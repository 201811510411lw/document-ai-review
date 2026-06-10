---
name: qc_document_review
description: QC 证照及批次报告审核的 Agent Skill 描述层。
---

# qc_document_review

## 能力边界

用于描述 QC 证照及批次报告审核能力。覆盖供应商证照、营业执照、食品经营许可证、食品生产许可证、商品批次报告和第三方检验报告的审核语义。

本 Skill 描述层只定义能力边界、输入输出、规则摘要和人工复核边界。确定性规则由 Python Runtime 的 rules 目录执行。

## 支持的输入

- OCR 文本。
- 图片或 PDF 文件引用。
- 文件路径或对象存储引用。
- 供应商名称、统一社会信用代码、经营地址等主数据。
- 商品、批次、报告类型等业务上下文。

## 输出结构摘要

- 文档类型识别结果。
- 关键字段抽取结果。
- 字段规范化结果。
- 规则校验结果摘要。
- 风险等级。
- 审核摘要。
- 人工复核状态和原因。

## 规则摘要

- 证照或报告是否存在并可识别。
- 主体名称和统一社会信用代码是否与供应商主数据一致。
- 证照有效期是否满足审核要求。
- 经营范围或生产范围是否覆盖当前业务。
- 批次报告是否匹配商品、批次和供应商。
- 第三方检验报告是否包含必要检测结论和有效签章信息。

## 人工复核边界

当材料无法识别、关键字段缺失、规则结果存在中高风险、批次报告无法匹配或检验结论不明确时，应进入人工复核。

## 禁止事项

- 不在 `SKILL.md` 中编写规则执行逻辑。
- 不直接调用 OCR、LLM、ERP、OA 或 IM 服务。
- 不声明公有云 API 为必需依赖。
- 不绕过 ReviewService 和 use case registry。
- 不直接调用 workflow 内部节点。

## 与 Python Runtime 的关系

Python Runtime facade 对应 `ai-service/app/use_cases/qc_document_review/skill.py`。平台通过 use case 入口调用 Runtime。后续 workflow 位于 `ai-service/app/workflows/qc_document/`；如需要可执行能力拆分，应落在 `ai-service/app/capabilities/`。
